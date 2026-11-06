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
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plumb.cliutil import EXIT_FINDINGS, EXIT_USAGE, add_common, emit, resolve_root

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


def owner_answers(root: Path, session: str) -> list[tuple[str, str]]:
    """``(at, answer)`` of the owner's question-tool answers in ``session``, oldest first, from
    the log of every checkout (the agent's question is never read)."""
    from plumb.api import open_core

    return sorted((e.at, str(e.payload.get("answer") or "")) for e in open_core(root).events()
                  if e.kind == "question-answer" and e.payload.get("session") == session
                  and e.payload.get("via") == "question-tool")


def names(rows: list[dict[str, Any]], text: str, words: str = "") -> list[dict[str, Any]]:
    """The rows ``text`` (the owner's words) names: by id prefix (6+ hex), INT-### or branch,
    or, when ``words`` (the agent's own) are quoted in the text, those the words find."""
    from plumb.approvals import quote_in_prompt
    from plumb.normalize import normalize_text

    low = normalize_text(text).lower()
    ids = re.findall(r"\b[0-9a-f]{6,12}\b", low)
    said = bool(words.strip()) and quote_in_prompt(normalize_text(words).lower(), low)
    return [r for r in rows if any(r["id"].startswith(i) for i in ids)
            or (r.get("intent") and re.search(rf"\b{re.escape(r['intent'].lower())}\b", low))
            or (r["branch"] not in ("", "main") and r["branch"].lower() in low)
            or (said and all(w in f"{r['goal_full']} {r['branch']}".lower()
                             for w in words.lower().split()))]


def _asked(root: Path, rows: list[dict[str, Any]], row: Mapping[str, Any], session: str,
           words: str) -> bool:
    """Whether the owner's latest message in ``session``, or their latest question-tool answer
    after it, names ``row`` and no other row (SR-394: no session opens unless they ask now)."""
    entries = owner_entries([w.path for w in checkouts(root)], session)
    if not entries:
        return False
    last = entries[-1]
    texts = [str(last.get("text") or "")]
    later = [a for at, a in owner_answers(root, session) if at > str(last.get("at") or "")]
    if later:
        texts.append(later[-1])
    return any([r["id"] for r in names(rows, t, words)] == [row["id"]] for t in texts)


def brief(row: Mapping[str, Any], data: Mapping[str, Any], new_session: str) -> str:
    """The first prompt of the new session: it takes the loop over, then carries on from where
    the loop is, under plumb's own words, never the owner's."""
    from plumb.api import open_core
    from plumb.understand import cmd_intent

    root = Path(str(row["root"]))
    records = cmd_intent._pane(open_core(root), data)["records"]
    kept = [f for f in data.get("files") or () if Path(f).exists()]
    adopt = ["plumb", "intent", "adopt", "--from-session", str(row["session"]), "--digest",
             str(row["id"]), "--session", new_session]
    return "\n".join([
        "<plumb-loop-brief>",
        "plumb reopened an intent loop in this new session; the session that held it is gone.",
        "First take the loop over: " + shlex.join(adopt),
        "Then carry on from this step, following the plumb-intent skill.",
        f"Goal: {row['goal_full']}", f"Step: {row['progress']}",
        f"Done: {', '.join(row['done']) or 'nothing yet'}",
        f"Left: {', '.join(row['left']) or 'nothing'}",
        "Records: " + ("; ".join(f"{r['id']} {r['title']}" for r in records) or "none yet"),
        *([f"Working files: {', '.join(kept)}"] if kept else []),
        f"Branch: {row['branch'] or 'none'}"])


# A terminal window per platform, first one found wins: program and its arguments for a command.
_LINUX = (("ptyxis", lambda cwd, cmd: ["--new-window", "-d", cwd, "--", *cmd]),
          ("gnome-terminal", lambda cwd, cmd: [f"--working-directory={cwd}", "--", *cmd]),
          ("konsole", lambda cwd, cmd: ["--workdir", cwd, "-e", *cmd]),
          ("kitty", lambda cwd, cmd: ["-d", cwd, *cmd]),
          ("alacritty", lambda cwd, cmd: ["--working-directory", cwd, "-e", *cmd]),
          ("wezterm", lambda cwd, cmd: ["start", "--cwd", cwd, "--", *cmd]),
          ("xfce4-terminal", lambda cwd, cmd: ["--working-directory", cwd, "-x", *cmd]),
          ("xterm", lambda cwd, cmd: ["-e", *cmd]))


def launch(argv: list[str], cwd: Path, *, prepare: Any = None, which: Any = shutil.which,
           spawn: Any = subprocess.Popen, env: Mapping[str, str] | None = None,
           platform: str = sys.platform) -> bool:
    """Open ``argv`` in a new terminal window in ``cwd``, detached, with no session identity of
    the caller's. ``prepare`` (makes the worktree) runs once a window program is found and
    returns an undo for a spawn that fails. False when no window could be opened."""
    from plumb.hosts.common import MARKER_NAME

    cwd_s = str(cwd)
    have = env if env is not None else os.environ
    clean = {k: v for k, v in have.items() if not k.startswith("CLAUDE") and k != MARKER_NAME}
    if platform == "darwin":
        script = f"cd {shlex.quote(cwd_s)} && {shlex.join(argv)}".replace("\\", "\\\\").replace(
            '"', '\\"')
        full = ["osascript", "-e", f'tell application "Terminal" to do script "{script}"']
    elif platform == "win32":
        full = ["wt", "-d", cwd_s, *argv]
    else:
        found = next(((p, f) for p, f in _LINUX if which(p)), None)
        if found is None or not (have.get("DISPLAY") or have.get("WAYLAND_DISPLAY")):
            return False
        full = [found[0], *found[1](cwd_s, argv)]
    undo = prepare() if prepare else None
    try:
        spawn(full, cwd=cwd_s, env=clean, start_new_session=True, stdin=subprocess.DEVNULL,
              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        if undo:
            undo()
        return False
    return True


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def _checkout_for(root: Path, row: Mapping[str, Any]) -> tuple[Path, list[list[str]], list[list[str]]]:
    """Where the reopened loop works: ``(directory, git steps that make it, steps that undo)``.
    A linked worktree is the loop's own; a loop of the main checkout (which refuses edits)
    goes to the branch already carrying its intent, else to a new branch, each in a worktree
    under ``.plumb/wt``."""
    from plumb.api import open_core
    from plumb.awareness import inflight
    from plumb.awareness.publish import default_branch

    found = checkouts(root)
    here = next(w for w in found if w.path.as_posix() == row["root"])
    if not here.main:
        return here.path, [], []
    intent = str(row["intent"])
    slug = intent.lower() if intent else f"loop-{row['id'][:8]}"
    core = open_core(here.path)
    default = default_branch(core)
    _oid, data = inflight.read(here.path, allow_git=True)
    claims = [c for c in inflight.active(here.path, data, default=default, allow_git=True)
              if intent and c.get("branch") != default
              and (c.get("intent") == intent or intent in (c.get("records") or {}))]
    branch = str(max(claims, key=lambda c: str(c.get("at")))["branch"]) if claims \
        else f"intent/{slug}"
    held = next((w.path for w in found if w.branch == branch), None)
    if held is not None:
        return held, [], []
    path = here.path / ".plumb" / "wt" / f"intent-{slug}"
    known = subprocess.run(["git", "rev-parse", "--verify", "-q", branch], cwd=here.path,
                           capture_output=True).returncode == 0
    make = ["worktree", "add", *([str(path), branch] if known else ["-b", branch, str(path)])]
    return path, [make], [["worktree", "remove", "--force", str(path)],
                          *([] if known else [["branch", "-D", branch]])]


def reopen(root: Path, *, words: str = "", loop: str = "", asker: str | None = None,
           agents: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Open the idle intent loop ``words`` (or id ``loop``) name in a new window and session
    (SR-394). ``asker``: the session of an agent, whose owner must have asked for exactly this
    loop just now (PermissionError otherwise); None for the owner's own press. LookupError: no
    such loop or several; ValueError: not reopenable. Answers ``{opened, command, line}``."""
    from plumb.understand import cmd_intent

    root = Path(root)
    rows = listing(root, agents=agents)["rows"]
    row = find(rows, loop or words)
    if row["kind"] != "intent":
        raise ValueError("plumb fixes problems and runs evaluations itself; only an intent loop "
                         "is reopened")
    if row["live"]:
        raise ValueError("a session works on this loop already")
    if asker is not None and not _asked(root, rows, row, asker, "" if loop else words):
        raise PermissionError("the owner did not ask for this loop to be reopened in this session")
    data = next(d for p, d in cmd_intent.loops(Path(row["root"]))
                if p.parent.parent.name == row["session"]
                and str(d["digest"]).removeprefix("sha256:").startswith(row["id"]))
    new = str(uuid.uuid4())
    cwd, make, undo = _checkout_for(root, row)
    command = ["claude", "--session-id", new, "-n", f"plumb: {row['goal'][:40]}",
               brief(row, data, new)]
    main = next(w.path for w in checkouts(root) if w.main) if make else root

    def prepare() -> Any:
        for step in make:
            _git(main, *step)
        return lambda: [subprocess.run(["git", *s], cwd=main, capture_output=True) for s in undo]

    try:
        opened = launch(command, cwd, prepare=prepare if make else None)    # call-time lookup
    except subprocess.CalledProcessError:
        opened = False
    if opened:
        return {"opened": True, "command": command, "line": f"opened a new session for {row['goal']}"}
    by_hand = [shlex.join(["git", *s]) for s in make] + [shlex.join(["cd", str(cwd)]),
                                                          shlex.join(command)]
    return {"opened": False, "command": command,
            "line": "no terminal window could be opened here; open the session by hand:\n"
                    + "\n".join(by_hand)}


def run_reopen(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="plumb loops reopen",
        description="Open an idle intent loop in a new window and session that takes it over. "
                    "An agent runs it only for what the owner asked in their latest message.")
    add_common(parser)
    parser.add_argument("words", nargs="*", help="words naming the loop (its goal or branch)")
    parser.add_argument("--loop", default="", help="the loop's id, from the candidates printed")
    parser.add_argument("--session", default=None, help="the asking agent's session")
    args = parser.parse_args(argv)
    if not args.session:
        print("plumb: name the asking session with --session; nothing opened", file=sys.stderr)
        return EXIT_USAGE
    try:
        done = reopen(resolve_root(args.root), words=" ".join(args.words), loop=args.loop,
                      asker=args.session)
    except PermissionError as exc:
        print(f"plumb: {exc}; nothing opened", file=sys.stderr)
        return EXIT_USAGE
    except (LookupError, ValueError) as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_FINDINGS
    emit(done if args.as_json else [done["line"]], args.as_json)
    return 0 if done["opened"] else EXIT_FINDINGS


def run(command: str, argv: list[str]) -> int:
    if argv[:1] == ["reopen"]:
        return run_reopen(argv[1:])
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
