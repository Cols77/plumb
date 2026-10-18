"""The landing job (SR-296): after a merge into the default branch, in the background, in
order: the tidy of what the landed records supersede (SR-286), the log compaction (SR-287),
the finished worktrees removed (DEC-190), the judge backlog queued (SR-298), then every count the status still shows written down as
debug cases (SR-300). Each step's failure is itself a case and the next step still runs.

It writes only main's tree and log (SR-301): never another worktree (but a finished, clean one it removes), another session's loop,
gate or cards, and it keeps a path an in-flight branch changed. A marker under
``.plumb/cache/landed/`` makes a second run for the same landing change nothing; the marker
holds the line the next turn reads (``lines``)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Collection, Iterable, Mapping
from pathlib import Path
from typing import Any

_ID = re.compile(r"^(?:INT|SR|DEC|FEAT|NC)-\d+$")
# kinds that state a setting or a gate: never compacted, whatever their age
NEVER = frozenset({"config", "jev-setup", "calibration", "gate", "intent-gate"})
# shortcut: only these record-less kinds are compacted by age (no hook reads them by age);
# widen once every hook reader of another kind is known not to need its old entries
BY_AGE = frozenset({"merge-evidence", "prompt", "job-note", "mod-hello"})


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=True)
    return result.stdout


def marker(root: Path, head: str) -> Path:
    return Path(root) / ".plumb" / "cache" / "landed" / f"{head}.json"


# --------------------------------------------------------------------------- start


def spawn(root: Path, head: str, before: str) -> bool:
    """From the post-merge hook: run ``land`` in a detached process, so the hook returns at
    once. Never raises; nothing started for a landing already done."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("PLUMB_FAKE_DISPATCH"):
        return False
    if marker(root, head).exists():
        return False
    try:
        from plumb.background import popen_options

        subprocess.Popen([sys.executable, "-m", "plumb.boundary.landing", "--head", head,
                          "--before", before], **popen_options(root))
    except Exception:  # noqa: BLE001 - a hook calls this
        return False
    return True


# --------------------------------------------------------------------------- tidy (SR-286)


def worktrees(root: Path) -> list[Path]:
    """The other worktrees of this repository (SR-301: the landing never writes them)."""
    here = Path(root).resolve()
    listed = [Path(line[len("worktree "):]).resolve() for line in
              _git(root, "worktree", "list", "--porcelain").splitlines()
              if line.startswith("worktree ")]
    return [w for w in listed if w != here]


def inflight_paths(root: Path) -> set[str]:
    """The paths the local branches not yet merged into HEAD changed since they forked, and
    the paths changed but not committed in another worktree (they land later)."""
    out: set[str] = set()
    for branch in _git(root, "for-each-ref", "--no-merged=HEAD", "--format=%(refname:short)",
                       "refs/heads").split():
        out |= set(_git(root, "diff", "--name-only", f"HEAD...{branch}").split("\n")) - {""}
    for tree in worktrees(root):
        try:
            listed = _git(tree, "status", "--porcelain", "-z", "--untracked-files=all")
        except (OSError, subprocess.CalledProcessError):
            continue  # a pruned or unreadable worktree changes nothing here
        items = iter(listed.split("\0"))
        for item in items:
            if len(item) > 3:
                out.add(item[3:])
                if item[0] in "RC":  # -z gives a rename's old path as the next bare item
                    out.add(next(items, ""))
        out.discard("")
    return out


def inflight_ids(paths: Iterable[str]) -> set[str]:
    """The record ids whose files ``paths`` (``inflight_paths``) name: records not landed."""
    return {Path(p).stem for p in paths if p.startswith(".plumb/") and _ID.match(Path(p).stem)}


def _landed_decisions(core: Any, before: str, head: str) -> list[Any]:
    changed = set(_git(core.root, "diff", "--name-only", before, head, "--",
                       ".plumb").split("\n"))
    return [r for r in core.index().values()
            if r.kind == "decision" and r.path in changed and r.fields.get("tidy")]


def tidy(core: Any, before: str, head: str) -> tuple[list[str], list[str], list[dict]]:
    """``(repository paths removed, folders outside removed, cases)``: the paths the landed
    decision records list under ``tidy:``. A path a current record cites stays and becomes
    a case; a path an in-flight branch changed stays until that branch lands."""
    root = Path(core.root)
    decisions = _landed_decisions(core, before, head)
    if not decisions:
        return [], [], []
    statuses = core.status()
    citing = [(r.id, (root / r.path).read_text(encoding="utf-8", errors="replace"))
              for r in core.index().values()
              if r.kind != "decision" or r.id not in {d.id for d in decisions}
              if statuses[r.id].superseded_by is None]
    busy = inflight_paths(root)
    removed: list[str] = []
    outside: list[str] = []
    cases: list[dict] = []
    for decision in decisions:
        named = decision.fields["tidy"]
        for item in [named] if isinstance(named, str) else named:
            path = Path(str(item))
            if path.is_absolute() and root.resolve() not in path.resolve().parents:
                held = [w for w in worktrees(root)
                        if w == path.resolve() or path.resolve() in w.parents
                        or w in path.resolve().parents]
                if held:  # SR-301: never another worktree, nor a folder holding one
                    cases.append({"id": f"tidy-worktree:{item}", "kind": "tidy-worktree",
                                  "target": str(item), "detail": f"{held[0]} is a worktree"})
                elif path.exists():
                    shutil.rmtree(path) if path.is_dir() else path.unlink()
                    outside.append(str(item))
                continue
            rel = (path.resolve().relative_to(root.resolve()) if path.is_absolute()
                   else path).as_posix().rstrip("/")
            if not (root / rel).exists() or rel in busy or any(
                    p == rel or p.startswith(rel + "/") for p in busy):
                continue
            cited = [i for i, text in citing if rel in text]
            if cited:
                cases.append({"id": f"tidy-cited:{rel}", "kind": "tidy-cited", "target": rel,
                              "detail": f"{decision.id} names it superseded but "
                                        f"{', '.join(cited)} still cite it"})
                continue
            try:
                _git(root, "rm", "-r", "-q", "--", rel)
                removed.append(rel)
            except subprocess.CalledProcessError as exc:
                cases.append({"id": f"tidy-failed:{rel}", "kind": "tidy-failed",
                              "target": rel, "detail": (exc.stderr or "").strip()[:200]})
    return removed, outside, cases


# --------------------------------------------------------------------------- compaction (SR-287)


def named_records(payload: Mapping[str, Any]) -> set[str]:
    """The record ids an entry names (``id``, ``subject``, ``record``, ``link``, ``records``)."""
    values: list[Any] = [payload.get(k) for k in ("id", "subject", "record", "link")]
    for item in payload.get("records") or ():
        values.append(item.get("id") if isinstance(item, Mapping) else item)
    return {str(v).split("#")[0] for v in values if v and _ID.match(str(v).split("#")[0])}


def _refs(value: Any) -> Iterable[str]:
    """Every ``sha256:`` string inside a payload: the entries it cites."""
    if isinstance(value, str):
        if value.startswith("sha256:"):
            yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _refs(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _refs(item)


def _evidence_kept(entries: list[Any]) -> set[str]:
    """The test-run entries verify still uses: per node its last run and last pass, every run
    of a node with an open regression, and the last full run."""
    from plumb.verify.evidence import _empty_index, apply_entry

    index = _empty_index()
    for entry in entries:
        apply_entry(index, entry.payload, entry.at)
    keep_runs = {str((index.get("full") or {}).get("run_id"))}
    regressed = set()
    for node_id, node in index["nodes"].items():
        for key in ("last", "last_pass"):
            if node.get(key):
                keep_runs.add(str(node[key].get("run_id")))
        if node.get("regressed"):
            regressed.add(node_id)
    return {e.digest for e in entries if not e.payload.get("discarded") and (
        str(e.payload.get("run_id")) in keep_runs
        or any(str(n.get("id")) in regressed for n in e.payload.get("nodes") or ()))}


def compaction(core: Any, since_at: str, tracked: set[str],
               pending: Collection[str] = ()) -> list[str]:
    """The committed entry files (``kind/file``) older than the records they served: every
    record they name superseded or retired; test-run evidence a newer run replaced; an entry
    of a ``BY_AGE`` kind naming no record, older than ``since_at``. An entry a staying entry
    cites (its digest, or its payload's ``digest``) stays, and so on down the chain. A record
    of ``pending`` (an in-flight branch's, SR-301) is not retired for being absent here."""
    index = core.index()
    statuses = core.status()

    def gone(record_id: str) -> bool:
        if record_id not in index:
            return record_id not in pending
        return statuses[record_id].superseded_by is not None

    evidence = [e for e in core.log_read("evidence") if "/" in e.name]
    runs = [e for e in evidence if e.kind == "test-run"]
    kept_runs = _evidence_kept(runs)
    live = [e for e in [*core.events(), *evidence] if ":" not in e.name]
    moving: dict[str, Any] = {}
    for entry in live:
        if entry.name not in tracked or entry.kind in NEVER:
            continue
        named = named_records(entry.payload)
        if entry.kind == "test-run":
            move = entry.digest not in kept_runs
        elif named:
            move = all(gone(i) for i in named)
        else:
            move = entry.kind in BY_AGE and entry.at < since_at
        if move:
            moving[entry.name] = entry
    cited = {r for e in live if e.name not in moving for r in _refs(e.payload)}
    while True:
        back = [n for n, e in moving.items()
                if e.digest in cited or e.payload.get("digest") in cited]
        if not back:
            break
        for name in back:
            cited.update(_refs(moving.pop(name).payload))
    return sorted(moving)


def compact(core: Any, before: str) -> list[str]:
    """Move the compaction's entries into their segments; the paths changed."""
    from plumb import log

    root = Path(core.root)
    stamp = int(_git(root, "log", "-1", "--format=%ct", before).strip())
    since_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stamp))
    tracked = log.tracked_names(root)
    pending = inflight_ids(inflight_paths(root))
    return log.archive(core.paths, compaction(core, since_at, tracked, pending))


# --------------------------------------------------------------------------- counts


def status_cases(core: Any, session: str, queued_line: str) -> list[dict]:
    """What the status still counts, one case each: stale and dangling links, failing or
    unrun acceptance tests, validate errors, records waiting on a judge that cannot be
    queued (``queued_line`` says no judge can be reached)."""
    from plumb.validate import validate

    cases: list[dict] = []
    statuses = core.status()
    for status in statuses.values():
        for state in status.links:
            if state.state in ("stale", "dangling"):
                cases.append({"id": f"{state.state}:{state.link.id}", "kind": f"{state.state}-link",
                              "target": state.link.id, "detail": f"{state.link.kind} link"})
    for finding in validate(core):
        if finding.severity == "error":
            cases.append({"id": f"validate:{finding.code}:{finding.subject}", "kind": "validate",
                          "target": finding.subject, "detail": finding.message})
    try:
        from plumb.verify import open_verify

        verify = open_verify(core)
        mapped = verify.tests_for([i for i, r in core.index().items()
                                   if r.kind == "requirement"])
        nodes = sorted({n for found in mapped.values() for n in found})
        for node, ev in (verify.evidence(nodes) if nodes else {}).items():
            if ev.state in ("fresh-fail", "none"):
                kind = "failing-test" if ev.state == "fresh-fail" else "unrun-test"
                cases.append({"id": f"{kind}:{node}", "kind": kind, "target": node,
                              "detail": "acceptance test"})
    except Exception:  # noqa: BLE001 - VERIFY is optional for the counts
        pass
    if queued_line:
        from plumb.understand import backlog

        for record_id in backlog.waiting(core, session):
            cases.append({"id": f"judge:{record_id}", "kind": "judge-waiting",
                          "target": record_id, "detail": queued_line})
    return cases


# --------------------------------------------------------------------------- the job


def shared_uncommitted(root: Path) -> list[str]:
    """SR-329: the uncommitted entries of shared log kinds in ``root``, whichever session wrote
    them (local kinds are ignored by git, so they never appear)."""
    from plumb import log

    out = _git(root, "ls-files", "-o", "--exclude-standard", "-z", "--", ".plumb/log")
    return sorted(p for p in out.split(chr(0)) if p.count("/") >= 3
                  and p.split("/")[2] in log.SHARED_KINDS)


def _commit(root: Path, removed: list[str], archived: list[str], head: str) -> None:
    """One tidy commit of exactly these paths (``removed`` already staged by ``git rm``); the
    owner's other staged work stays staged."""
    from plumb import log

    spec = root / ".plumb" / "cache" / f"landing-{head[:12]}.paths"
    spec.parent.mkdir(parents=True, exist_ok=True)
    message = f"plumb: tidy after the landing of {head[:12]}" + chr(10) * 2 + "SR: SR-296"
    try:
        log.stage(root, archived)
        spec.write_bytes(chr(0).join([*removed, *archived]).encode("utf-8"))
        done = subprocess.run(["git", "commit", "-q", "--no-verify", "-m", message,
                               f"--pathspec-from-file={spec}", "--pathspec-file-nul"],
                              cwd=root, env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"},
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        if done.returncode:
            raise RuntimeError(f"git commit: {done.stderr.strip()[:200]}")
    finally:
        spec.unlink(missing_ok=True)


# --------------------------------------------------------------------------- worktrees (DEC-190)


def _loop_reason(root: Path, tree: Path, branch: str) -> str:
    """Why an open loop (not handed on, build stage not passed) keeps the worktree: one lives in
    the worktree's own session (an adopted loop's JSON names no path), or one in ``root``
    names it. shortcut: a text match on the loop file, as loops hold no worktree field;
    upgrade when they do."""
    from plumb.understand.cmd_intent import _passed, loops

    def opened(r: Path) -> list[Any]:
        return [d for _, d in loops(r) if not d.get("handed_to") and not _passed(d, "build")]

    if opened(tree):
        return "an open intent loop lives there"
    needles = {branch, str(tree), tree.as_posix()}
    named = any(n in json.dumps(d) for d in opened(root) for n in needles)
    return "an open intent loop names it" if named else ""


def finished_worktrees(root: Path, before: str, head: str) -> tuple[list[str], list[str]]:
    """``(removed, kept)`` worktree names: every other worktree whose branch has a commit of its
    own and is merged into ``head`` (this landing's or an earlier one's) is removed with its
    branch, unless it has uncommitted work or an open intent loop names it; then it is named in
    ``kept`` with the reason. The main checkout and ``root`` itself are never touched.
    shortcut: ``before`` is unused now; drop it from the signature when callers change."""
    from plumb import log

    removed: list[str] = []
    kept: list[str] = []
    listing = _git(root, "worktree", "list", "--porcelain").split(chr(10) * 2)
    main = Path(listing[0].splitlines()[0][len("worktree "):]).resolve()
    for block in listing[1:]:
        fields = dict(line.partition(" ")[::2] for line in block.splitlines())
        tree = Path(fields.get("worktree", "")).resolve()
        branch = fields.get("branch", "").removeprefix("refs/heads/")
        if not branch or tree in (main, Path(root).resolve()):
            continue
        merged = subprocess.run(
            ["git", "merge-base", "--is-ancestor", f"refs/heads/{branch}", head], cwd=root,
            capture_output=True).returncode == 0
        # a fork's tip is an ancestor of main too, even after a fast-forward merge puts its own
        # commits there; only the branch reflog tells them apart: a real commit entry (a reset
        # or rebase alone is no work of its own)
        own = any(x.startswith("commit") for x in _git(
            root, "reflog", "show", "--format=%gs", f"refs/heads/{branch}").splitlines())
        if not merged or not own:
            continue
        try:
            dirty = [x for x in _git(tree, "status", "--porcelain", "--untracked-files=all"
                                     ).splitlines() if not log.untracked_own(tree, x)]
            reason = "uncommitted changes" if dirty else _loop_reason(root, tree, branch)
            if not reason:
                _git(root, "worktree", "remove", "--force", str(tree))
                _git(root, "branch", "-d", branch)
                removed.append(tree.name)
                continue
        except (OSError, subprocess.CalledProcessError) as exc:
            reason = ((getattr(exc, "stderr", "") or str(exc)).strip().splitlines() or ["?"])[-1][:120]
        kept.append(f"worktree {tree.name} finished but kept: {reason}")
    return removed, kept


def land(root: Path, head: str, before: str, session: str | None = None) -> dict[str, Any]:
    """Run the landing's steps once; the result is also the marker's content."""
    from plumb.api import open_core
    from plumb.understand import backlog, files, summary

    root = Path(root)
    done = marker(root, head)
    if done.exists():
        return {"line": "", "again": True}
    session = session or files.CLI_SESSION
    cases: list[dict] = []
    removed: list[str] = []
    outside: list[str] = []
    archived: list[str] = []
    queued = 0
    queued_line = ""
    gone: list[str] = []
    kept: list[str] = []

    def step(name: str, run: Any) -> None:
        try:
            run()
        except Exception as exc:  # noqa: BLE001 - SR-296 EX-6: the failure is a case
            cases.append({"id": f"landing:{name}", "kind": "landing-step", "target": name,
                          "detail": f"{type(exc).__name__}: {exc}"[:300]})

    def do_tidy() -> None:
        found = tidy(open_core(root), before, head)
        removed.extend(found[0])
        outside.extend(found[1])
        cases.extend(found[2])

    def do_compact() -> None:
        archived.extend(compact(open_core(root), before))

    def do_queue() -> None:
        nonlocal queued, queued_line
        started = backlog.queue_waiting(open_core(root), session, mark=False)
        queued, queued_line = started.records, started.line

    def do_commit() -> None:
        shared = shared_uncommitted(root)
        if removed or archived or shared:
            _commit(root, removed, [*archived, *shared], head)

    def do_worktrees() -> None:
        found = finished_worktrees(root, before, head)
        gone.extend(found[0])
        kept.extend(found[1])

    step("tidy", do_tidy)
    step("compaction", do_compact)
    step("commit", do_commit)
    step("worktrees", do_worktrees)
    step("backlog", do_queue)
    step("counts", lambda: cases.extend(status_cases(open_core(root), session, queued_line)))
    moved = sum(1 for p in archived if not p.endswith("archive.jsonl"))
    parts = [f"tidied {', '.join([*removed, *outside])}" if removed or outside
             else "nothing to tidy",
             f"compacted {moved} log entries" if moved else "",
             f"removed finished worktrees {', '.join(gone)}" if gone else "",
             *kept,
             f"queued {queued} records for the judge",
             f"{len(cases)} cases went to debugging"]
    line = f"plumb: landing {head[:12]}: " + "; ".join(p for p in parts if p)
    result = {"line": line, "removed": removed, "outside": outside, "archived": moved,
              "queued": queued, "worktrees": gone, "kept": kept, "cases": len(cases)}
    summary.write_cases(open_core(root), head, [{**c, "state": "open"} for c in cases])
    files.write_json_atomic(done, result)
    return result


def lines(root: Path) -> list[tuple[str, str]]:
    """``(key, text)`` for the next turn: the latest landing's line, then the open debug cases
    (SR-300) with how many were resolved."""
    from plumb.understand import summary

    folder = Path(root) / ".plumb" / "cache" / "landed"
    out: list[tuple[str, str]] = []
    try:
        latest = max(folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
        data = json.loads(latest.read_text(encoding="utf-8"))
        if data.get("line"):
            out.append((latest.stem, str(data["line"])))
    except (OSError, ValueError, AttributeError):
        pass
    open_rows, resolved = summary.open_cases(root)
    if open_rows:
        out.append((f"cases:{len(open_rows)}:{resolved}",
                    summary.cases_text(open_rows, resolved)))
    return out


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m plumb.boundary.landing")
    parser.add_argument("--head", required=True)
    parser.add_argument("--before", required=True)
    args = parser.parse_args(argv)
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    land(root, args.head, args.before)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
