"""The landing job (SR-296): after a merge into the default branch, in the background, in
order: the tidy of what the landed records supersede (SR-286), the log compaction (SR-287),
the finished worktrees removed (DEC-190), the folders of ended sessions removed, the judge backlog queued (SR-298), then every count the status still shows written down as
debug cases (SR-300). Each step's failure is itself a case and the next step still runs.

It writes only main's tree and log (SR-301): never another worktree (but a finished, clean one it removes), another session's loop,
gate or cards (but the folder of a session its SessionEnd hook marked ended), and it keeps a path an in-flight branch changed. A marker under
``.iaso/cache/landed/`` makes a second run for the same landing change nothing; the marker
holds the line the next turn reads (``lines``), and the requirements the landing delivered
whose proof was agreed as post-merge (SR-341), which the next turn tells the agent to show
and ask the owner about until the owner confirmed them."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Collection, Iterable, Mapping
from pathlib import Path
from typing import Any

_ID = re.compile(r"^(?:INT|SR|DEC|FEAT|NC)-\d+$")
# kinds that state a setting or a gate: never compacted, whatever their age
NEVER = frozenset({"config", "jev-setup", "calibration", "gate", "intent-gate"})
# shortcut: only these record-less kinds are compacted by age (no hook reads them by age);
# widen once every hook reader of another kind is known not to need its old entries
BY_AGE = frozenset({"merge-evidence", "prompt", "job-note", "mod-hello"})
RETIRED = frozenset({"offer"})   # SR-403: no reader; its loose files go to the segment


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=True)
    return result.stdout


def marker(root: Path, head: str) -> Path:
    return Path(root) / ".iaso" / "cache" / "landed" / f"{head}.json"


# --------------------------------------------------------------------------- post-merge proofs


def restore_owner_words(root: Path, before: str, head: str) -> list[str]:
    """DEC-116: the owner's-words entries (``log.OWNER_WORDS_KINDS``) that main tracked at
    ``before`` and the merged branch stopped tracking: git removed their files from main's
    working tree with the merge. They are the owner's own words and live nowhere else, so each
    is written back from ``before`` as the untracked file it now is. Returns their paths."""
    from iaso.log import OWNER_WORDS_KINDS

    folders = [f".iaso/log/{kind}/" for kind in sorted(OWNER_WORDS_KINDS)]
    gone = _git(root, "diff", "--name-only", "--diff-filter=D", "-z", before, head,
                "--", *folders).split("\0")
    restored: list[str] = []
    for name in (n for n in gone if n.endswith(".json")):
        target = Path(root) / name
        if target.exists():
            continue
        text = subprocess.run(["git", "show", f"{before}:{name}"], cwd=root,
                              capture_output=True, check=True).stdout
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text)
        restored.append(name)
    return restored


def post_merge_proofs(core: Any, before: str, head: str) -> list[str]:
    """SR-341: the requirements the commits of ``before..head`` deliver (their SR trailers)
    whose proof was agreed as post-merge."""
    from iaso.capture.proof import post_merge
    from iaso.claims import claimed_ids, trailer_aliases

    aliases = trailer_aliases(core)
    index = core.index()
    ids: dict[str, None] = {}
    for entry in _git(Path(core.root), "log", "--format=%H%x1f%B%x00",
                      f"{before}..{head}").split("\0"):
        sha, _sep, message = entry.strip("\n").partition("\x1f")
        for i in claimed_ids(aliases, sha, message) if sha else ():
            record = index.get(i)
            if record is not None and record.kind == "requirement" and post_merge(record):
                ids[i] = None
    return list(ids)


def proof_lines(root: Path, ids: Iterable[str]) -> list[tuple[str, str]]:
    """SR-341 EX-2: for each landed post-merge proof the owner has not yet confirmed, the
    agent's line: show it now and ask the owner."""
    from iaso.api import open_core
    from iaso.capture.proof import confirmed, evaluator_picked, proof_of

    core = open_core(root)
    index = core.index()
    out: list[tuple[str, str]] = []
    for i in ids:
        record = index.get(i)
        if record is None or confirmed(core, i):
            continue
        plan = " ".join(str((proof_of(record) or {}).get("plan") or "").split())
        if evaluator_picked(record):    # SR-396 EX-4
            out.append((f"post-merge-proof:{i}",
                        f"iaso: {i} has landed and its proof was agreed as post-merge; the "
                        f"owner picked the independent evaluator: run iaso evaluate proof "
                        f"{i}; ask the owner only if it could not check"))
            continue
        out.append((f"post-merge-proof:{i}",
                    f"iaso: {i} has landed and its proof was agreed as post-merge: show it "
                    f"now ({plan}), record it (iaso proof {i} --evidence ... --summary ... "
                    f"--passed) and ask the owner whether they saw it working "
                    f"(iaso proof {i} --ask)"))
    return out


# --------------------------------------------------------------------------- start


def spawn(root: Path, head: str, before: str) -> bool:
    """From the post-merge hook: run ``land`` in a detached process, so the hook returns at
    once. Never raises; nothing started for a landing already done."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("IASO_FAKE_DISPATCH"):
        return False
    if marker(root, head).exists():
        return False
    try:
        from iaso.background import popen_options

        subprocess.Popen([sys.executable, "-m", "iaso.boundary.landing", "--head", head,
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
    return {Path(p).stem for p in paths if p.startswith(".iaso/") and _ID.match(Path(p).stem)}


def _landed_decisions(core: Any, before: str, head: str) -> list[Any]:
    changed = set(_git(core.root, "diff", "--name-only", before, head, "--",
                       ".iaso").split("\n"))
    return [r for r in core.index().values()
            if r.kind == "decision" and r.path in changed and r.fields.get("tidy")]


def _in_use(path: Path) -> bool:
    """A running process works inside ``path`` (an evaluator's agent or its checks)."""
    for proc in Path("/proc").glob("[0-9]*/cwd"):   # shortcut: Linux only; elsewhere none seen
        try:
            here = proc.resolve()
        except OSError:
            continue
        if here == path or path in here.parents:
            return True
    return False


def sweep_eval_scratch(root: Path, older_than_s: float = 86400, *,
                       now: float | None = None) -> list[str]:
    """Report report-0ab44aff, SR-301: the evaluator's leftover ``iaso-eval-*`` folders in the
    temp folder, untouched for a day, are removed unless one holds a worktree of this repository
    or a running process works in it; the paths removed."""
    import tempfile

    cutoff = (time.time() if now is None else now) - older_than_s
    held = worktrees(root)
    gone: list[str] = []
    for path in sorted(Path(tempfile.gettempdir()).glob("iaso-eval-*")):
        try:
            if not path.is_dir() or path.is_symlink() or path.stat().st_mtime >= cutoff:
                continue
            path = path.resolve()
            if any(w == path or path in w.parents or w in path.parents for w in held):
                continue
            if _in_use(path):
                continue
            shutil.rmtree(path)
            gone.append(str(path))
        except OSError:
            continue   # not ours to remove: left alone
    return gone


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


def _evidence_kept(entries: list[Any], alive: Callable[[str], bool] = lambda n: True) -> set[str]:
    """The test-run entries verify still uses: per node its last run and last pass, every run
    of a node with an open regression, and the last full run. A node ``alive`` rejects (its
    test file is gone: SR-403) needs none of them."""
    from iaso.verify.evidence import _empty_index, apply_entry

    index = _empty_index()
    for entry in entries:
        apply_entry(index, entry.payload, entry.at)
    keep_runs = {str((index.get("full") or {}).get("run_id"))}
    regressed = set()
    for node_id, node in index["nodes"].items():
        if not alive(node_id):
            continue
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
    from iaso import log

    index = core.index()
    statuses = core.status()

    def gone(record_id: str) -> bool:
        if record_id not in index:
            return record_id not in pending
        return statuses[record_id].superseded_by is not None

    evidence = [e for e in core.log_read("evidence") if "/" in e.name]
    runs = [e for e in evidence if e.kind == "test-run"]
    kept_runs = _evidence_kept(runs, lambda n: (Path(core.root) / n.split("::")[0]).exists())
    live = [e for e in [*core.events(), *evidence] if ":" not in e.name]
    moving: dict[str, Any] = {}
    for entry in live:
        telemetry = entry.kind in log.TELEMETRY_KINDS   # local files: tracked or not
        if (entry.name not in tracked and not telemetry) or entry.kind in NEVER:
            continue
        named = named_records(entry.payload)
        if telemetry:
            move = entry.at < since_at
        elif entry.kind in RETIRED:
            move = True
        elif entry.kind == "test-run":
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
    from iaso import log

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
    from iaso.validate import validate

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
        from iaso.verify import open_verify

        verify = open_verify(core)
        mapped = verify.tests_for([i for i, r in core.index().items()
                                   if r.kind == "requirement"])
        # only pytest files count: helpers and the .test.tsx files iaso never runs have no evidence
        nodes = sorted({n for found in mapped.values() for n in found if re.fullmatch(
            r"(test_.*|.*_test)\.py", n.split("::")[0].rsplit("/", 1)[-1])})
        for node, ev in (verify.evidence(nodes) if nodes else {}).items():
            if ev.state in ("fresh-fail", "none"):
                kind = "failing-test" if ev.state == "fresh-fail" else "unrun-test"
                cases.append({"id": f"{kind}:{node}", "kind": kind, "target": node,
                              "detail": "acceptance test"})
    except Exception:  # noqa: BLE001 - VERIFY is optional for the counts
        pass
    if queued_line:
        from iaso.understand import backlog

        for record_id in backlog.waiting(core, session):
            cases.append({"id": f"judge:{record_id}", "kind": "judge-waiting",
                          "target": record_id, "detail": queued_line})
    return cases


# --------------------------------------------------------------------------- the job


def _commit(root: Path, removed: list[str], archived: list[str], head: str) -> None:
    """One tidy commit of exactly these paths (``removed`` already staged by ``git rm``); the
    owner's other staged work stays staged."""
    from iaso import log

    spec = root / ".iaso" / "cache" / f"landing-{head[:12]}.paths"
    spec.parent.mkdir(parents=True, exist_ok=True)
    message = f"iaso: tidy after the landing of {head[:12]}" + chr(10) * 2 + "SR: SR-296"
    paths = log.committable(root, [*removed, *archived])  # the log code picks its own paths
    try:
        for attempt in range(5):  # a git process just after the merge may still hold index.lock
            try:
                log.stage(root, archived)
                spec.write_bytes(chr(0).join(paths).encode("utf-8"))
                done = subprocess.run(["git", "commit", "-q", "--no-verify", "-m", message,
                                       f"--pathspec-from-file={spec}", "--pathspec-file-nul"],
                                      cwd=root, env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"},
                                      capture_output=True, text=True, encoding="utf-8",
                                      errors="replace")
                if done.returncode:
                    raise RuntimeError(f"git commit: {done.stderr.strip()[:200]}")
                return
            except RuntimeError as exc:
                if "index.lock" not in str(exc) or attempt == 4:
                    raise
                time.sleep(2)
    finally:
        spec.unlink(missing_ok=True)


# --------------------------------------------------------------------------- worktrees (DEC-190)


def _loop_reason(root: Path, tree: Path, branch: str) -> str:
    """Why an open loop (not handed on, build stage not passed) keeps the worktree: one lives in
    the worktree's own session (an adopted loop's JSON names no path), or one in ``root``
    names it. shortcut: a text match on the loop file, as loops hold no worktree field;
    upgrade when they do."""
    from iaso.understand.cmd_intent import _passed, loops

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
    from iaso import log

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
                _git(root, "worktree", "remove", "--force", str(tree))   # the branch stays
                removed.append(tree.name)
                continue
        except (OSError, subprocess.CalledProcessError) as exc:
            reason = ((getattr(exc, "stderr", "") or str(exc)).strip().splitlines() or ["?"])[-1][:120]
        kept.append(f"worktree {tree.name} finished but kept: {reason}")
    return removed, kept


def _size_mb(tree: Path) -> int:
    total = 0
    for base, _dirs, names in os.walk(tree):
        for name in names:
            try:
                total += os.lstat(os.path.join(base, name)).st_size
            except OSError:
                pass
    return total // 1_000_000


def idle_debug_copies(root: Path) -> tuple[list[tuple[Path, str, int]], list[str]]:
    """SR-401: ``(idle, kept)``: the debug work copies under ``root``'s ``.iaso/wt`` whose branch
    has no commit of its own and sits in HEAD, with no uncommitted work and no open problem
    naming them, as ``(tree, branch, MB)``, largest first; ``kept`` names those that would be
    idle but for uncommitted work. Any other worktree is never listed."""
    from iaso import debug, log, selfdebug

    root = Path(root).resolve()
    wt_dir = root / ".iaso" / "wt"
    open_slugs = {selfdebug._slug(c["id"]) for c in debug.open_cases(root)}
    idle: list[tuple[Path, str, int]] = []
    kept: list[str] = []
    for block in _git(root, "worktree", "list", "--porcelain").split(chr(10) * 2):
        fields = dict(line.partition(" ")[::2] for line in block.splitlines())
        tree = Path(fields.get("worktree", "")).resolve()
        branch = fields.get("branch", "").removeprefix("refs/heads/")
        if tree.parent != wt_dir or not tree.name.startswith("debug-") or not branch \
                or tree.name.removeprefix("debug-") in open_slugs:
            continue
        own = any(x.startswith("commit") for x in _git(
            root, "reflog", "show", "--format=%gs", f"refs/heads/{branch}").splitlines())
        in_head = subprocess.run(["git", "merge-base", "--is-ancestor", f"refs/heads/{branch}",
                                  "HEAD"], cwd=root, capture_output=True).returncode == 0
        if own or not in_head or _loop_reason(root, tree, branch):
            continue
        dirty = [x for x in _git(tree, "status", "--porcelain", "--untracked-files=all"
                                 ).splitlines() if not log.untracked_own(tree, x)]
        if dirty:
            kept.append(f"debug work copy {tree.name} is idle but kept: uncommitted changes")
        else:
            idle.append((tree, branch, _size_mb(tree)))
    return sorted(idle, key=lambda i: -i[2]), kept


def remove_idle(root: Path) -> tuple[list[tuple[str, int]], list[str]]:
    """SR-401: remove every idle debug work copy (its branch stays): ``([(name, MB)], kept
    lines)``."""
    idle, kept = idle_debug_copies(root)
    removed: list[tuple[str, int]] = []
    for tree, _branch, mb in idle:
        try:
            _git(root, "worktree", "remove", "--force", str(tree))
            removed.append((tree.name, mb))
        except subprocess.CalledProcessError as exc:
            kept.append(f"debug work copy {tree.name} is idle but kept: "
                        f"{(exc.stderr or str(exc)).strip().splitlines()[-1][:120]}")
    return removed, kept


def ended_sessions(root: Path, session: str) -> list[str]:
    """Remove each ``.iaso/session/<id>/`` the SessionEnd hook marked (``ended.json``), never
    ``session``'s own and never an unmarked one (owner, 2026-10-20: no age-based deletion).
    A folder that will not go (a file still open) stays for the next landing, and so does one
    still holding a waiting question (SR-340: its questions are kept)."""
    from iaso.api import open_core
    from iaso.understand import files, judge

    core = open_core(root)
    own = files.session_dir(root, session).name
    gone: list[str] = []
    for folder in sorted((Path(root) / ".iaso" / "session").glob("*/ended.json")):
        folder = folder.parent
        if folder.name == own or judge.unanswered(core, folder.name):
            continue
        shutil.rmtree(folder, ignore_errors=True)
        if not folder.exists():
            gone.append(folder.name)
    return gone


def land(root: Path, head: str, before: str, session: str | None = None) -> dict[str, Any]:
    """Run the landing's steps once; the result is also the marker's content."""
    from iaso import debug
    from iaso.api import open_core
    from iaso.understand import backlog, files, summary

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
    ended: list[str] = []
    proofs: list[str] = []
    words_back: list[str] = []

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
        from iaso import log

        # SR-329: main's uncommitted shared entries ride the tidy commit; judgment entries are
        # not among them (ignored by git), the compaction archives them instead (SR-376)
        shared = log.shared_uncommitted(root)
        if removed or archived or shared:
            _commit(root, removed, [*archived, *shared], head)

    idle: list[tuple[str, int]] = []
    swept: list[str] = []

    def do_worktrees() -> None:
        found = finished_worktrees(root, before, head)
        gone.extend(found[0])
        kept.extend(found[1])
        removed_idle, kept_idle = remove_idle(root)   # SR-401
        idle.extend(removed_idle)
        kept.extend(kept_idle)

    step("owner-words", lambda: words_back.extend(restore_owner_words(root, before, head)))
    step("proofs", lambda: proofs.extend(post_merge_proofs(open_core(root), before, head)))
    step("fixes", lambda: debug.landed(root, head))  # before the worktrees step drops branches
    step("tidy", do_tidy)
    step("eval-scratch", lambda: swept.extend(sweep_eval_scratch(root)))
    step("compaction", do_compact)
    step("commit", do_commit)
    step("worktrees", do_worktrees)
    step("sessions", lambda: ended.extend(ended_sessions(root, session)))
    step("backlog", do_queue)
    step("counts", lambda: cases.extend(status_cases(open_core(root), session, queued_line)))
    moved = sum(1 for p in archived if not p.endswith("archive.jsonl"))
    parts = [f"tidied {', '.join([*removed, *outside])}" if removed or outside
             else "nothing to tidy",
             f"compacted {moved} log entries" if moved else "",
             f"removed finished worktrees {', '.join(gone)}" if gone else "",
             f"removed idle debug work copies {', '.join(n for n, _ in idle)} "
             f"({sum(m for _, m in idle)} MB freed)" if idle else "",
             *kept,
             f"removed {len(ended)} ended session folders" if ended else "",
             f"removed {len(swept)} old evaluator scratch folders" if swept else "",
             f"post-merge proofs to show: {', '.join(proofs)}" if proofs else "",
             f"queued {queued} records for the judge",
             f"{len(cases)} cases went to debugging"]
    line = f"iaso: landing {head[:12]}: " + "; ".join(p for p in parts if p)
    result = {"line": line, "removed": removed, "outside": outside, "archived": moved,
              "queued": queued, "worktrees": gone, "kept": kept, "sessions": ended, "cases": len(cases),
              "post_merge": proofs, "owner_words": len(words_back)}
    summary.write_cases(open_core(root), head,
                        [{**c, "state": "open"} for c in debug.from_landing(root, cases)])
    files.write_json_atomic(done, result)
    return result


def _level_models(root: Path) -> dict[str, str]:
    """SR-389: the levels whose model is not their own name, to pass to the workflow."""
    from iaso.config import load_config

    return {k: v for k, v in load_config(root).understand.levels.items() if k != v}


def lines(root: Path, workflow: str = "") -> list[tuple[str, str]]:
    """``(key, text)`` for the next turn: the latest landing's line, then the open debug cases
    (SR-300) with how many were resolved; ``workflow`` names the shipped workflow (SR-385)."""
    from iaso.understand import summary

    folder = Path(root) / ".iaso" / "cache" / "landed"
    out: list[tuple[str, str]] = []
    try:
        latest = max(folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
        data = json.loads(latest.read_text(encoding="utf-8"))
        if data.get("line"):
            out.append((latest.stem, str(data["line"])))
        out.extend(proof_lines(Path(root), data.get("post_merge") or ()))
    except (OSError, ValueError, AttributeError):
        pass
    open_rows, resolved = summary.open_cases(root)
    if open_rows:
        out.append((f"cases:{len(open_rows)}:{resolved}",
                    summary.cases_text(open_rows, resolved, workflow,
                                       _level_models(root) if workflow else None)))
    return out


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m iaso.boundary.landing")
    parser.add_argument("--head", required=True)
    parser.add_argument("--before", required=True)
    args = parser.parse_args(argv)
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    land(root, args.head, args.before)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
