"""The merge-time safety net: git's ``pre-merge-commit`` and ``prepare-commit-msg`` hooks
(sp6 10, R17; SR-077).

R17 (owner, 2026-10-07): a CHEAP merge-time check holds a merge carrying a leftover intent
conflict, unconfirmed requirements or undeclared files, WITHOUT running the test suite; the
single full suite runs at push (the pre-push hook). Never run the suite twice.

The guarantee: no commit that records another line's work is made while what it records
carries an open intent conflict (and, for a merge, a touched requirement not yet confirmed,
a file no requirement declares or two records holding one ID). Its entry points, all
through ``check``:

- ``git merge`` (and ``git pull``) committing on its own: the ``pre-merge-commit`` hook.
- ``git commit`` or ``git merge --continue`` finishing a merge (after a text conflict or
  ``--no-commit``), and every commit of a rebase, cherry-pick or revert: the
  ``prepare-commit-msg`` hook, the one hook git runs for each of them (a rebase runs neither
  pre-commit nor commit-msg). Its shell lines exit at once outside such an operation, so
  ordinary commits pay no Python start; under ``git merge`` they leave the check to the
  pre-merge-commit hook when that one is plumb's.
- Under a rebase, a cherry-pick or a revert the record merge driver exits 1 on an intent
  conflict, so git stops on the record (``driver.main``); the commit that continues it is
  checked here.

The check judges what git will record: it reads the work tree, so it first holds when a
file under ``.plumb/`` differs from the index being committed (``git status``, which reads
the ``GIT_INDEX_FILE`` git points at that index inside the hook), and when a record file
cannot be read (a text merge left in it). A merge is checked in full (``HEAD`` against the
incoming commits); a rebase, cherry-pick or revert step only for open intent conflicts (its
own requirements are its branch's business until that branch merges).

No test run, no verification evidence, no judgment backend call (cards show a judgment only
when one is already logged: ``conflict_rows(hook=True)``), no log write, no log-integrity
diff: a few git calls and the record index. A non-zero exit refuses the commit; the
operation stays in progress until it is settled, then the owner says "finish the merge" (or
"continue the rebase").

``plumb hooks install`` and ``plumb init`` install both hooks by default (R17); ``plumb
merge-check --install-pre-merge-commit`` and ``--uninstall-pre-merge-commit`` install and
remove both, like the pre-push hook: the shared hooks directory, a marker line, a foreign
hook left untouched (its ``hook_line`` in ``--json``). ``git merge --no-verify`` bypasses the
pre-merge-commit hook; git has no such switch for prepare-commit-msg, so ``git -c
plumb.mergeHold=false commit`` (or ``... rebase --continue``) bypasses that one.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.boundary.prepush import ForeignHookError
from plumb.present import owner_text

HOOK = "pre-merge-commit"
HOOK_MARKER = "# plumb pre-merge-commit hook"
COMMIT_HOOK = "prepare-commit-msg"
COMMIT_HOOK_MARKER = "# plumb prepare-commit-msg hook"
MARKERS = {HOOK: HOOK_MARKER, COMMIT_HOOK: COMMIT_HOOK_MARKER}
HOLD_KEY = "plumb.mergeHold"
CAP = 10


def _git(root: Path, *args: str, check: bool = False) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        if check:
            raise subprocess.CalledProcessError(out.returncode, ["git", *args], out.stdout,
                                                out.stderr)
        return None
    return out.stdout


def hook_path(root: Path, hook: str = HOOK) -> Path:
    out = (_git(Path(root), "rev-parse", "--git-path", f"hooks/{hook}", check=True) or "")
    path = Path(out.strip())
    return path if path.is_absolute() else Path(root) / path


def commit_hook_path(root: Path) -> Path:
    return hook_path(root, COMMIT_HOOK)


def _exe(interpreter: str) -> str:
    return interpreter.replace("\\", "/")


def hook_line(interpreter: str, hook: str = HOOK) -> str:
    """The line an owner's own hook runs to call plumb (``--json``'s ``hook_line``)."""
    return f'"{_exe(interpreter)}" -m plumb merge-check --hook {hook} || exit $?'


def hook_text(interpreter: str) -> str:
    return (f"#!/bin/sh\n{HOOK_MARKER} (written by plumb; a quick check, no test run)\n"
            f'exec "{_exe(interpreter)}" -m plumb merge-check --hook {HOOK}\n')


def commit_hook_text(interpreter: str) -> str:
    """prepare-commit-msg: exits at once unless a merge, rebase, cherry-pick or revert is in
    progress, or when ``plumb.mergeHold`` is false; under ``git merge`` with plumb's
    pre-merge-commit hook, that hook already checked."""
    return (f"#!/bin/sh\n{COMMIT_HOOK_MARKER} (written by plumb; holds a commit that finishes "
            "a merge, rebase, cherry-pick or revert; a quick check, no test run)\n"
            'd=$(git rev-parse --absolute-git-dir 2>/dev/null) || exit 0\n'
            '[ -f "$d/MERGE_HEAD" ] || [ -f "$d/CHERRY_PICK_HEAD" ] || [ -f "$d/REVERT_HEAD" ] '
            '|| [ -d "$d/rebase-merge" ] || [ -d "$d/rebase-apply" ] || exit 0\n'
            f'[ "$(git config --bool {HOLD_KEY})" = false ] && exit 0\n'
            "if env | grep -q '^GITHEAD_' && grep -qs '" + HOOK_MARKER + "' "
            f'"$(git rev-parse --git-path hooks/{HOOK})"; then exit 0; fi\n'
            f'exec "{_exe(interpreter)}" -m plumb merge-check --hook {COMMIT_HOOK}\n')


def _is_plumb(path: Path, hook: str = HOOK) -> bool:
    try:
        return MARKERS[hook] in path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ForeignHookError(f"cannot read the existing hook {path}: {exc}") from exc


def _install(root: Path, interpreter: str, hook: str) -> Path:
    path = hook_path(Path(root), hook)
    if path.exists() and not _is_plumb(path, hook):
        raise ForeignHookError(owner_text.FOREIGN_HOOK if hook == HOOK
                               else owner_text.FOREIGN_COMMIT_HOOK)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = hook_text(interpreter) if hook == HOOK else commit_hook_text(interpreter)
    path.write_bytes(text.encode("utf-8"))
    try:
        path.chmod(0o755)
    except OSError:
        pass
    return path


def install_hook(root: Path, interpreter: str) -> Path:
    """Write plumb's pre-merge-commit hook (idempotent); a foreign hook raises
    ``ForeignHookError`` and is left untouched."""
    return _install(root, interpreter, HOOK)


def install_commit_hook(root: Path, interpreter: str) -> Path:
    """Write plumb's prepare-commit-msg hook (idempotent); a foreign hook raises
    ``ForeignHookError`` and is left untouched."""
    return _install(root, interpreter, COMMIT_HOOK)


def uninstall_hook(root: Path, hook: str = HOOK) -> bool:
    """Remove plumb's hook; False (and left) when it is foreign or absent."""
    path = hook_path(Path(root), hook)
    if not path.exists() or not _is_plumb(path, hook):
        return False
    path.unlink()
    return True


def hook_state(root: Path, hook: str = HOOK) -> str:
    """``plumb`` | ``non-plumb`` | ``not installed``."""
    try:
        path = hook_path(Path(root), hook)
    except (OSError, subprocess.CalledProcessError):
        return "not installed"
    if not path.exists():
        return "not installed"
    try:
        return "plumb" if _is_plumb(path, hook) else "non-plumb"
    except ForeignHookError:
        return "non-plumb"


# --------------------------------------------------------------------------- the check


@dataclass(frozen=True)
class PremergeReport:
    """The quick merge check (R17): what holds the merge, no test run."""

    merging: str = ""
    into: str = ""
    touched: tuple[str, ...] = ()
    unconfirmed: tuple[Mapping[str, Any], ...] = ()      # {id, title, state}
    undeclared: tuple[Mapping[str, Any], ...] = ()       # {commit, path, claims}
    intent_conflicts: tuple[Mapping[str, Any], ...] = ()  # {ic, record, title, card}
    collisions: tuple[Mapping[str, Any], ...] = ()       # {id, line}
    unstaged: tuple[str, ...] = ()       # .plumb/ paths that differ from the index committed
    unreadable: tuple[Mapping[str, Any], ...] = ()       # {path, line}
    operation: str = "merge"             # merge | rebase | cherry-pick | revert
    skipped: str | None = None
    exit: int = 0
    lines: tuple[str, ...] = field(default_factory=tuple)


def _collisions(core: Any) -> list[dict[str, Any]]:
    try:
        from plumb import ids

        found = ids.collisions(core, None)
        return [{"id": c.id, "paths": list(c.paths)} for c in found]
    except Exception:  # noqa: BLE001 - this build has no allocator: the store's duplicates
        pass
    rows = []
    for problem in core.store.problems() if hasattr(core, "store") else ():
        if problem.startswith("duplicate id "):
            rows.append({"id": problem.split()[2].rstrip(":"), "paths": []})
    return rows


def incoming_heads(root: Path) -> list[tuple[str, str]]:
    """``[(sha, name)]`` of the commits being merged. Inside the hook git has not written
    ``MERGE_HEAD`` yet: it names each incoming head in a ``GITHEAD_<sha>`` variable. Run by
    hand in the middle of a merge, ``MERGE_HEAD`` holds them."""
    import os
    import re

    heads = [(key[len("GITHEAD_"):].lower(), value) for key, value in os.environ.items()
             if re.fullmatch(r"GITHEAD_[0-9a-fA-F]{40,64}", key)]
    if heads:
        return sorted(heads)
    from plumb.mergedriver.driver import labels_of

    path = (_git(Path(root), "rev-parse", "--git-path", "MERGE_HEAD") or "").strip()
    if not path:
        return []
    target = Path(path) if Path(path).is_absolute() else Path(root) / path
    try:
        shas = target.read_text(encoding="utf-8").split()
    except OSError:
        return []
    theirs = labels_of(Path(root), [])[1]
    return [(sha, theirs if i == 0 else sha[:12]) for i, sha in enumerate(shas)]


def unstaged_plumb(root: Path) -> list[str]:
    """The ``.plumb/`` paths whose work-tree content is not what git will record: changed
    or untracked against the index (inside a commit hook, ``GIT_INDEX_FILE`` names the index
    being committed, which ``git status`` reads). Ignored files (cache, session) are not
    listed. One git call, taking no lock."""
    out = _git(Path(root), "--no-optional-locks", "status", "--porcelain=v1", "-z",
               "--untracked-files=all", "--", ".plumb") or ""
    items = out.split("\0")
    found: list[str] = []
    i = 0
    while i < len(items):
        item = items[i]
        i += 1
        if len(item) < 4:
            continue
        x, y, path = item[0], item[1], item[3:]
        if x in "RC":
            i += 1  # a rename or copy names its source next
        if y != " ":
            found.append(path)
    return sorted(set(found))


def _unreadable(core: Any) -> list[dict[str, Any]]:
    """Record files the index cannot read (a text merge left in them): the check cannot
    judge what they carry, so they hold."""
    from plumb.validate import _text_merged

    rows = []
    for problem in core.store.problems() if hasattr(core, "store") else ():
        if problem.startswith("duplicate id "):
            continue
        path = problem.split(":", 1)[0]
        rows.append({"path": path, "line": "  " + (_text_merged(core, path) or problem)})
    return rows


def check(core: Any, operation: str | None = None) -> PremergeReport:
    """The quick check of the merge, rebase, cherry-pick or revert in progress
    (``GITHEAD_*`` in the pre-merge-commit hook, else ``MERGE_HEAD`` and git's state
    files)."""
    from plumb.claims import claims_check, load_policy
    from plumb.merge import required_records, touched_requirements
    from plumb.mergedriver.conflicts import conflict_rows
    from plumb.mergedriver.driver import git_operation, labels_of

    root = Path(core.root)
    operation = operation or git_operation(root)
    if operation is None:
        return PremergeReport(skipped="no merge in progress")
    unstaged = tuple(unstaged_plumb(root))
    unreadable = tuple(_unreadable(core))
    if operation != "merge":
        conflicts = conflict_rows(core, hook=True)
        code = 1 if (unstaged or unreadable) else 4 if conflicts else 0
        return _with_lines(PremergeReport(
            into=labels_of(root, [])[0], operation=operation,
            intent_conflicts=tuple(conflicts), unstaged=unstaged, unreadable=unreadable,
            exit=code))
    heads = incoming_heads(root)
    if not heads:
        return PremergeReport(skipped="no merge in progress")
    ours = labels_of(root, [])[0]
    theirs = ", ".join(name for _, name in heads)
    staged = _git(root, "diff", "--cached", "--name-only", "-z", "HEAD") or ""
    paths = sorted({p for p in staged.split("\0") if p})
    # (commit, message) pairs: an incoming commit's trailers are read through any renumber
    messages: list[tuple[str, str]] = []
    for sha, _ in heads:
        log = _git(root, "log", "--format=%H%x1f%B%x00", f"HEAD..{sha}") or ""
        for entry in log.split("\0"):
            commit, _sep, message = entry.strip("\n").partition("\x1f")
            if message.strip():
                messages.append((commit, message))

    touched = touched_requirements(core, paths, messages)
    required = required_records(core, touched)
    statuses = core.status(required)
    index = core.index()
    unconfirmed = [{"id": i, "title": index[i].title, "state": statuses[i].confirmation}
                   for i in required if statuses[i].confirmation != "confirmed"]

    undeclared: list[dict[str, Any]] = []
    for sha, _ in heads:
        try:
            result = claims_check(root, f"HEAD..{sha}")
            for item in result.get("undeclared") or []:
                undeclared.append({"commit": str(item.get("commit")), "path": item.get("path"),
                                   "claims": list(item.get("claims") or [])})
            if load_policy(root).require_trailer:
                for unclaimed in result.get("unclaimed_commits") or []:
                    undeclared.append({"commit": str(unclaimed), "path": None, "claims": []})
        except Exception as exc:  # noqa: BLE001 - an unreadable range holds, never crashes
            undeclared.append({"commit": "", "path": None, "claims": [], "error": str(exc)})

    conflicts = conflict_rows(core, hook=True)
    collisions = _collisions(core)
    held = bool(undeclared or collisions or unstaged or unreadable)
    code = 1 if held else 4 if (conflicts or unconfirmed) else 0
    report = PremergeReport(merging=theirs, into=ours, touched=tuple(touched),
                            unconfirmed=tuple(unconfirmed), undeclared=tuple(undeclared),
                            intent_conflicts=tuple(conflicts), collisions=tuple(collisions),
                            unstaged=unstaged, unreadable=unreadable, exit=code)
    return _with_lines(report)


def _with_lines(report: PremergeReport) -> PremergeReport:
    from dataclasses import replace

    return replace(report, lines=tuple(render(report)))


def _capped(rows: Sequence[str]) -> list[str]:
    out = list(rows[:CAP])
    if len(rows) > CAP:
        out.append(f"  +{len(rows) - CAP} more (/plumb merge-check)")
    return out


def render(report: PremergeReport) -> list[str]:
    """The owner's lines: each holding section with its plain-word pointer, then
    ``MERGE_HELD`` when the merge is held."""
    if report.skipped:
        return [f"plumb: merge check skipped ({report.skipped})"]
    merge = report.operation == "merge"
    if merge:
        out = [f"plumb: quick merge check (no test run): {report.merging} into {report.into}"]
        finish = "finish the merge"
    else:
        out = [f"plumb: quick check of this {report.operation} step (no test run): "
               f"{report.into}"]
        finish = f"continue the {report.operation}"
    if report.intent_conflicts:
        out.append(owner_text.CONFLICTS_HEADER)
        for conflict in report.intent_conflicts:
            out.extend(str(line) for line in conflict.get("card") or [])
    if report.unconfirmed:
        out.append("requirements this merge touches wait for your confirmation:")
        out.extend(_capped([owner_text.PREMERGE_UNCONFIRMED.format(record=r["id"],
                                                                   title=r["title"])
                            for r in report.unconfirmed]))
    if report.undeclared:
        out.append("files changed without a requirement that declares them:")
        out.extend(_capped([owner_text.PREMERGE_UNDECLARED.format(
            path=r.get("path") or f"a commit without a requirement ({r['commit'][:12]})")
            for r in report.undeclared]))
    if report.collisions:
        out.append("two different records hold one ID:")
        out.extend(_capped([owner_text.PREMERGE_COLLISION.format(record=r["id"])
                            for r in report.collisions]))
    if report.unreadable:
        out.append(owner_text.PREMERGE_UNREADABLE_HEADER)
        out.extend(_capped([str(r["line"]) for r in report.unreadable]))
    if report.unstaged:
        out.append(owner_text.PREMERGE_UNSTAGED_HEADER)
        out.extend(_capped([owner_text.PREMERGE_UNSTAGED.format(path=path, finish=finish)
                            for path in report.unstaged]))
    if report.exit:
        out.append(owner_text.MERGE_HELD if merge else
                   owner_text.STEP_HELD.format(operation=report.operation))
    else:
        out.append(owner_text.PREMERGE_OK if merge else
                   owner_text.STEP_OK.format(operation=report.operation))
    return out


def commit_hook_skips(root: Path) -> bool:
    """The prepare-commit-msg hook's cheap first look (before the record index is opened):
    no merge, rebase, cherry-pick or revert in progress; ``plumb.mergeHold`` false; or
    ``git merge`` committing on its own with plumb's pre-merge-commit hook, which already
    checked. The hook's shell lines make the same choice; this covers an owner's own hook
    calling ``hook_line``."""
    from plumb.mergedriver.driver import git_operation, under_git_merge

    if git_operation(Path(root)) is None:
        return True
    if (_git(Path(root), "config", "--bool", HOLD_KEY) or "").strip() == "false":
        return True
    return under_git_merge() and hook_state(Path(root), HOOK) == "plumb"


def run_hook(core: Any) -> int:
    """``plumb merge-check --hook pre-merge-commit`` (or ``prepare-commit-msg``): print the
    report, return its exit."""
    report = check(core)
    for line in report.lines or render(report):
        print(line)
    return report.exit
