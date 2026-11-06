"""The list of every loop of the project (SR-390): one place computes it, the command prints it.

``listing`` reads the intent loops of every checkout of the repository on this machine and
changes nothing. A loop is live while its session is among the running ones (``claude agents``);
the rest are idle, listed below the live ones with their last activity. ``touch`` moves the one
change stamp every writer of a loop moves, so a panel can poll one small file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plumb.cliutil import add_common, emit, resolve_root

LIVE_S = 600          # without `claude agents`: a session folder written within this is live
GOAL_CHARS = 100
STAMP = "plumb-loops.stamp"
KINDS = ("intent", "debug", "evaluate")
_HEX = re.compile(r"[0-9a-f]{6,}")


def claude_sessions() -> dict[str, dict[str, Any]] | None:
    """``{session id: {status: busy|idle, cwd}}`` of the running sessions, None when `claude`
    cannot say (missing, failed, too slow)."""
    try:
        done = subprocess.run(["claude", "agents", "--json"], capture_output=True, text=True,
                              timeout=5, check=True)
        return {str(a["sessionId"]): {"status": str(a.get("status") or ""),
                                      "cwd": str(a.get("cwd") or "")}
                for a in json.loads(done.stdout) if isinstance(a, Mapping) and a.get("sessionId")}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return None


def touch(root: Path) -> None:
    """Move the change stamp (in the git common dir, shared by every checkout). Never raises.
    shortcut: a session that starts or ends without writing a loop file moves no stamp; its
    row changes at the next stamp or the panel's next turn end."""
    from plumb.awareness import gitfiles

    try:
        common = gitfiles.common_dir(Path(root))
        if common is not None:
            (common / STAMP).write_text(f"{time.time_ns()} {os.getpid()}\n", encoding="utf-8")
    except OSError:
        pass


def _stamp(root: Path) -> str:
    from plumb.awareness import gitfiles

    common = gitfiles.common_dir(Path(root))
    return (common / STAMP).as_posix() if common is not None else ""


def checkouts(root: Path) -> list[Any]:
    """Every checkout of the repository (``gitfiles.Worktree``), ``root``'s own included."""
    from plumb.awareness import gitfiles

    found = gitfiles.worktrees(root)
    if not any(w.path.resolve() == Path(root).resolve() for w in found):
        found.append(gitfiles.Worktree(Path(root), Path(root) / ".git", None, None))
    return found


def _within(path: Path, parent: Path) -> bool:
    try:
        return path.resolve().is_relative_to(parent.resolve())
    except OSError:
        return False


def session_root(roots: list[Path], session: str, agents: Mapping[str, Any] | None,
                 default: Path | None = None) -> Path | None:
    """The checkout a session's hooks run in (its gate, band and prompt log live there): the
    one holding the cwd ``claude agents`` gives, else the newest holding the session's
    ``host.json``, else ``default``."""
    cwd = str((agents or {}).get(session, {}).get("cwd") or "")
    held = [r for r in roots if cwd and _within(Path(cwd), r)]
    if held:
        return max(held, key=lambda r: len(r.resolve().parts))
    hosted = [(p.stat().st_mtime, r) for r in roots
              if (p := r / ".plumb" / "session" / session / "host.json").is_file()]
    return max(hosted, key=lambda item: item[0])[1] if hosted else default


def owner_entries(roots: list[Path], session: str) -> list[Mapping[str, Any]]:
    """The owner's prompts of ``session`` from every checkout's prompt log, deduped by digest."""
    from plumb.approvals import is_owner_entry

    seen: dict[str, Mapping[str, Any]] = {}
    for root in roots:
        try:
            lines = (root / ".plumb" / "session" / "prompts.jsonl").read_text(
                encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, Mapping) and entry.get("session") == session \
                    and is_owner_entry(entry):
                seen[str(entry.get("digest"))] = entry
    return sorted(seen.values(), key=lambda e: str(e.get("at") or ""))


def _one_line(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= GOAL_CHARS else line[:GOAL_CHARS - 1] + "…"


def _readback(checkout: Path, intent: str) -> str:
    import yaml

    from plumb.model import split_frontmatter

    try:
        front, _ = split_frontmatter((checkout / ".plumb" / "intents" / f"{intent}.md")
                                     .read_text(encoding="utf-8"))
        return " ".join(str((yaml.safe_load(front) or {}).get("readback") or "").split())
    except (OSError, ValueError):
        return ""


def _last(data: Mapping[str, Any]) -> str:
    stamps = [str(data.get("opened_at") or ""),
              *(str(s.get("at") or "") for s in data["stages"].values() if isinstance(s, Mapping))]
    tasks = data.get("tasks")
    if isinstance(tasks, Mapping):
        stamps.append(str(tasks.get("started_at") or ""))
    return max(stamps)


def _recent(root: Path | None, session: str, now: datetime) -> bool:
    """No `claude agents`: the session folder's direct entries were written lately."""
    folder = (root or Path()) / ".plumb" / "session" / session
    try:
        newest = max(p.stat().st_mtime for p in folder.iterdir())
    except (OSError, ValueError):
        return False
    return now.timestamp() - newest <= LIVE_S


def intent_rows(root: Path, agents: Mapping[str, Any] | None, now: datetime) -> list[dict[str, Any]]:
    from plumb.api import open_core
    from plumb.capture import proof
    from plumb.understand import clarify, cmd_intent, gate

    found = checkouts(root)
    roots = [w.path for w in found]
    rows: dict[str, dict[str, Any]] = {}
    for tree in found:
        for path, data in cmd_intent.loops(tree.path):
            step = next((s for s in cmd_intent.STAGES if not cmd_intent._passed(data, s)),
                        "proven")
            session, digest = path.parent.parent.name, str(data["digest"])
            last = _last(data)
            if data.get("handed_to") or step == "proven" \
                    or digest in rows and rows[digest]["last"] >= last:
                continue
            intent = str(data.get("intent") or "")
            tasks = data.get("tasks") if isinstance(data.get("tasks"), Mapping) else {}
            left = [str(x) for x in tasks.get("left") or ()]
            if step == "build" and intent:
                core = open_core(tree.path)
                left += ["proof: " + r["title"] for r in proof.not_shown(
                    core, cmd_intent.requirements_of(core, intent))]
            steps = (*cmd_intent.STAGES, "proven")
            left += steps[steps.index(step) + 1:]
            goal = _readback(tree.path, intent) if intent else ""
            if not goal:
                words = next((clarify.commanded_words(str(e.get("text") or ""))
                              for e in owner_entries(roots, session)
                              if e.get("digest") == digest), None)
                goal = words or f"intent loop {digest.removeprefix('sha256:')[:12]}"
            sroot = session_root(roots, session, agents, tree.path)
            waits = ("the " + str(data["stopped"]) if data.get("stopped")
                     else "the owner's answer" if gate.state(sroot, session).state == "closed"
                     else "")
            running = agents.get(session) if agents is not None else None
            live = bool(running) if agents is not None else _recent(sroot, session, now)
            total = tasks.get("total")
            rows[digest] = {
                "kind": "intent", "id": digest.removeprefix("sha256:")[:12], "intent": intent,
                "goal": _one_line(goal), "goal_full": goal,
                "progress": step + (f" · {tasks.get('done') or 0}/{total}" if total else ""),
                "done": [s for s in cmd_intent.STAGES if cmd_intent._passed(data, s)],
                "left": left, "waits": waits, "live": live,
                "state": ("waiting" if (running or {}).get("status") == "idle" else "working")
                if live else "idle",
                "last": last, "idle_since": "" if live else last[:10],
                "branch": tree.branch or "", "root": tree.path.as_posix(), "session": session,
                "reopen": not live, "send": live, "message": None}
    return list(rows.values())


def listing(root: Path, *, agents: Mapping[str, Any] | None = None,
            now: datetime | None = None) -> dict[str, Any]:
    """Every loop of the project, live first (newest first), then idle; reads only."""
    if agents is None:
        agents = claude_sessions()      # looked up at call time: tests replace it
    now = now or datetime.now(timezone.utc)
    from plumb import debug
    from plumb.evaluate import loop as evaluate

    rows = intent_rows(Path(root), agents, now)
    others: dict[tuple[str, str], dict[str, Any]] = {}
    for tree in checkouts(Path(root)):
        for row in [*debug.loop_rows(tree.path), *evaluate.rows(tree.path)]:
            key = (row["kind"], row["id"])      # one run or case seen from two checkouts
            if key not in others or others[key]["last"] < row["last"]:
                others[key] = {**row, "branch": row["branch"] or tree.branch or ""}
    rows += others.values()
    rows.sort(key=lambda r: (not r["live"], [-ord(c) for c in r["last"]]))
    counts = {k: {"live": sum(r["live"] for r in rows if r["kind"] == k),
                  "idle": sum(not r["live"] for r in rows if r["kind"] == k)} for k in KINDS}
    return {"rows": rows, "live": sum(c["live"] for c in counts.values()),
            "idle": sum(c["idle"] for c in counts.values()), "stamp": _stamp(Path(root)),
            "counts": counts}


def find(rows: list[dict[str, Any]], words: str) -> dict[str, Any]:
    """The one row ``words`` name: an id prefix (6+ hex), an INT-### or words found in the goal
    or branch. Several or none: a LookupError listing the candidates, one per line."""
    text = words.strip().lower()
    if _HEX.fullmatch(text):
        hits = [r for r in rows if r["id"].startswith(text)]
    elif re.fullmatch(r"int-\d+", text):
        hits = [r for r in rows if r["intent"].lower() == text]
    else:
        hits = [r for r in rows if all(w in f"{r['goal_full']} {r['branch']}".lower()
                                       for w in text.split())]
    if len(hits) == 1:
        return hits[0]
    raise LookupError(
        (f"'{words}' names more than one loop; name one by its id:" if hits
         else f"'{words}' names no loop; the loops are:")
        + "".join(f"\n  {r['id']}  {r['goal']}  ({r['branch'] or 'no branch'})"
                  for r in hits or rows))


def _row_lines(row: Mapping[str, Any]) -> list[str]:
    since = f" · idle since {row['idle_since']}" if not row["live"] else ""
    lines = [f"{row['kind']} · {row['goal']}",
             f"  {row['progress']} · {row['branch'] or 'no branch'}{since}"]
    if row["left"]:
        lines.append("  left: " + ", ".join(row["left"]))
    if row["waits"]:
        lines.append("  waits for: " + row["waits"])
    return lines


def text(data: Mapping[str, Any]) -> list[str]:
    rows = data["rows"]
    if not rows:
        return ["plumb: no loop is open"]
    out = [line for r in rows if r["live"] for line in _row_lines(r)]
    idle = [r for r in rows if not r["live"]]
    if idle:
        out += ["idle, nobody works on these:", *(line for r in idle for line in _row_lines(r))]
    return out


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="plumb loops",
        description="Every loop of the project, from any session or worktree: what it is meant "
                    "to achieve, how far it is, what is left, what it waits for and where it "
                    "runs. Live loops first, idle ones below. Changes nothing.")
    add_common(parser)
    args = parser.parse_args(argv)
    data = listing(resolve_root(args.root))
    emit(data if args.as_json else text(data), args.as_json)
    return 0
