"""The merge-time safety net: git's ``pre-merge-commit``, ``prepare-commit-msg`` and
``post-merge`` hooks (sp6 10, R17; SR-077).

R17 (owner, 2026-10-07): a CHEAP merge-time check holds a merge carrying a leftover intent
conflict, unconfirmed requirements or undeclared files, WITHOUT running the test suite; the
single full suite runs at push (the pre-push hook). Never run the suite twice.

The guarantee: no commit that records another line's work is made (or, for a fast-forward
of the default branch, stays) while what it records carries an open intent conflict (and,
for a merge, a touched requirement not yet confirmed, a file no requirement declares or two
records holding one ID). Its entry points, all through ``check``:

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
- A merge into the default branch that git would FAST-FORWARD (no merge commit, so no
  pre-merge-commit hook): ``ff_hold`` (the one choke point, installed with the hooks) sets
  ``branch.<default>.mergeoptions`` to ``--no-ff``, so a plain ``git merge`` or ``git pull``
  into the default branch records a merge commit and meets the check above; and the
  ``post-merge`` hook, the one hook git runs after a fast-forward (``--ff-only``,
  ``pull.ff=only``), runs the same check over what came in and, when it holds, puts the
  default branch back where it was (``git reset --keep ORIG_HEAD``): nothing held stays
  recorded (``run_post_merge``).

The check judges what git will record: it reads the work tree, so it first holds when a
file under ``.plumb/`` differs from the index being committed (``git status``, which reads
the ``GIT_INDEX_FILE`` git points at that index inside the hook), and when a record file
cannot be read (a text merge left in it). A merge is checked in full (``HEAD`` against the
incoming commits); a rebase, cherry-pick or revert step only for open intent conflicts (its
own requirements are its branch's business until that branch merges).

No test run, no verification evidence, no judgment backend call (cards show a judgment only
when one is already logged: ``conflict_rows(hook=True)``), no log-integrity diff: a few
git calls and the record index. Its one write: an intent conflict the owner already
answered before work began is settled with that answer (R17, ``check``). A non-zero exit
refuses the commit; the operation stays in progress until it is settled, then the owner says
"finish the merge" (or "continue the rebase").

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
POST_HOOK = "post-merge"
POST_HOOK_MARKER = "# plumb post-merge hook"
MARKERS = {HOOK: HOOK_MARKER, COMMIT_HOOK: COMMIT_HOOK_MARKER, POST_HOOK: POST_HOOK_MARKER}
HOLD_KEY = "plumb.mergeHold"
NL = "\n"
NO_FF = "--no-ff"
NO_FF_KEY = "plumb.noFastForward"   # set when plumb added --no-ff (so uninstall removes it)
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


def post_hook_text(interpreter: str) -> str:
    """post-merge: git runs it after a merge it recorded, a fast-forward included. Its shell
    lines exit at once for a squash, with ``plumb.mergeHold`` false, and for the merge
    commit this merge just made (its first parent is ``ORIG_HEAD``: pre-merge-commit
    already checked it); only a fast-forward starts Python."""
    return (f"#!/bin/sh{NL}{POST_HOOK_MARKER} (written by plumb; puts the default branch back "
            f"when a fast-forward brings in what the quick merge check holds; no test run){NL}"
            f'[ "$1" = 1 ] && exit 0{NL}'
            f'[ "$(git config --bool {HOLD_KEY})" = false ] && exit 0{NL}'
            f"o=$(git rev-parse -q --verify ORIG_HEAD) || exit 0{NL}"
            '[ -n "$(git rev-parse -q --verify HEAD^2)" ] && '
            f'[ "$(git rev-parse -q --verify HEAD^1)" = "$o" ] && exit 0{NL}'
            f'exec "{_exe(interpreter)}" -m plumb merge-check --hook {POST_HOOK}{NL}')


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
    text = {HOOK: hook_text, COMMIT_HOOK: commit_hook_text,
            POST_HOOK: post_hook_text}[hook](interpreter)
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


def install_post_hook(root: Path, interpreter: str) -> Path:
    """Write plumb's post-merge hook (idempotent) and make merges into the default branch
    record a merge commit (``ff_hold``); a foreign hook raises ``ForeignHookError`` and is
    left untouched (the merge option is still set)."""
    ff_hold(root)
    return _install(root, interpreter, POST_HOOK)


def post_hook_path(root: Path) -> Path:
    return hook_path(root, POST_HOOK)


def default_branch_of(root: Path) -> str:
    """``merge.default_base`` (``main``) read from ``.plumb/config.yaml`` without a core."""
    from types import SimpleNamespace

    from plumb.boundary.cli import merge_settings

    try:
        return str(merge_settings(SimpleNamespace(root=Path(root), config=None))
                   ["default_base"])
    except Exception:  # noqa: BLE001 - a broken config keeps the default
        return "main"


def _ff_key(root: Path) -> str:
    return f"branch.{default_branch_of(root)}.mergeoptions"


def ff_hold(root: Path, *, dry_run: bool = False) -> bool:
    """The choke point that keeps every merge into the default branch checkable (R17): a
    fast-forward records no merge commit, so git runs no pre-merge-commit hook for it.
    ``branch.<default>.mergeoptions`` gains ``--no-ff`` (``git merge`` and ``git pull`` into
    the default branch then record a merge commit, which the quick check holds), unless the
    owner set a fast-forward option there themselves (``--ff``, ``--ff-only``): the
    post-merge hook still checks those. Idempotent; returns whether it changed the config."""
    root = Path(root)
    key = _ff_key(root)
    current = (_git(root, "config", "--get", key) or "").strip()
    words = current.split()
    if NO_FF in words or "--ff" in words or "--ff-only" in words:
        return False
    if dry_run:
        return True
    _git(root, "config", key, " ".join([*words, NO_FF]), check=True)
    _git(root, "config", "--bool", NO_FF_KEY, "true", check=True)
    return True


def ff_hold_state(root: Path) -> bool:
    words = (_git(Path(root), "config", "--get", _ff_key(Path(root))) or "").split()
    return NO_FF in words


def ff_release(root: Path, *, dry_run: bool = False) -> bool:
    """Remove the ``--no-ff`` plumb added (``plumb.noFastForward``); an owner's own option
    stays. Returns whether it changed the config."""
    root = Path(root)
    if (_git(root, "config", "--bool", "--get", NO_FF_KEY) or "").strip() != "true":
        return False
    key = _ff_key(root)
    words = [w for w in (_git(root, "config", "--get", key) or "").split() if w != NO_FF]
    if dry_run:
        return True
    if words:
        _git(root, "config", key, " ".join(words))
    else:
        _git(root, "config", "--unset", key)
    _git(root, "config", "--unset", NO_FF_KEY)
    return True


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
    settled: tuple[str, ...] = ()        # R17: conflicts the owner's earlier answer settled
    operation: str = "merge"     # merge | fast-forward | rebase | cherry-pick | revert
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


def check(core: Any, operation: str | None = None, *, hook: str | None = None,
          fast_forward: tuple[str, str, str] | None = None) -> PremergeReport:
    """The quick check of the merge, rebase, cherry-pick or revert in progress
    (``GITHEAD_*`` in the pre-merge-commit hook, else ``MERGE_HEAD`` and git's state
    files).

    R17: an intent conflict the owner already answered before work began (a confirmed
    early decision between exactly these two versions) is settled by that answer first
    (``answer.apply_settled``: the chosen version, its log entry, both staged), never
    asked again. git wrote the commit's tree before its hook ran, so the commit is held
    once; the owner's "finish the merge" records the settled version (no new question).
    ``hook`` names the git hook running the check (for the report only).

    ``fast_forward`` ``(before, after, name)``: git already moved the default branch from
    ``before`` to ``after`` (``name``'s work) without a merge commit (the post-merge hook):
    the same check of ``before..after``, nothing settled or staged (``run_post_merge``
    undoes the move when it holds)."""
    from plumb.mergedriver.conflicts import conflict_rows
    from plumb.mergedriver.driver import git_operation, labels_of

    root = Path(core.root)
    if fast_forward is not None:
        before, after, name = fast_forward
        return _merge_check(core, before, [(after, name)], operation="fast-forward")
    operation = operation or git_operation(root)
    if operation is None:
        return PremergeReport(skipped="no merge in progress")
    settled = tuple(_apply_settled(core))
    unstaged = tuple(unstaged_plumb(root))
    unreadable = tuple(_unreadable(core))
    if operation != "merge":
        conflicts = conflict_rows(core, hook=True)
        # git wrote this commit's tree before its hook ran: hold it once, so the commit
        # that finishes it records the settled version
        code = 1 if (unstaged or unreadable or settled) else 4 if conflicts else 0
        return _with_lines(PremergeReport(
            into=labels_of(root, [])[0], operation=operation,
            intent_conflicts=tuple(conflicts), unstaged=unstaged, unreadable=unreadable,
            settled=settled, exit=code))
    heads = incoming_heads(root)
    if not heads:
        return PremergeReport(skipped="no merge in progress")
    return _merge_check(core, "HEAD", heads, unstaged=unstaged, unreadable=unreadable,
                        settled=settled)


def _merge_check(core: Any, base: str, heads: Sequence[tuple[str, str]], *,
                 operation: str = "merge", unstaged: tuple[str, ...] = (),
                 unreadable: tuple[Mapping[str, Any], ...] | None = None,
                 settled: tuple[str, ...] = ()) -> PremergeReport:
    """The check of ``heads`` merging into ``base``: ``HEAD`` and the staged result while a
    merge is in progress; for a fast-forward, the commit it left against the one before."""
    from plumb.claims import claims_check, load_policy
    from plumb.merge import required_records, touched_requirements
    from plumb.mergedriver.conflicts import conflict_rows
    from plumb.mergedriver.driver import labels_of

    root = Path(core.root)
    if unreadable is None:
        unreadable = tuple(_unreadable(core))
    ours = labels_of(root, [])[0]
    theirs = ", ".join(name for _, name in heads)
    if operation == "fast-forward":
        changed = _git(root, "diff", "--name-only", "-z", base, heads[0][0]) or ""
    else:
        changed = _git(root, "diff", "--cached", "--name-only", "-z", base) or ""
    paths = sorted({p for p in changed.split("\0") if p})
    # (commit, message) pairs: an incoming commit's trailers are read through any renumber
    messages: list[tuple[str, str]] = []
    for sha, _ in heads:
        log = _git(root, "log", "--format=%H%x1f%B%x00", f"{base}..{sha}") or ""
        for entry in log.split("\0"):
            commit, _sep, message = entry.strip("\n").partition("\x1f")
            if message.strip():
                messages.append((commit, message))

    touched = touched_requirements(core, paths, messages)
    required = required_records(core, touched)
    statuses = core.status(required)
    index = core.index()
    from plumb.awareness.answer import waiting_on_conflict

    # an early decision whose record carries an open conflict is asked once, by that
    # conflict's card (its answer answers the decision too)
    unconfirmed = [{"id": i, "title": index[i].title, "state": statuses[i].confirmation}
                   for i in required if statuses[i].confirmation != "confirmed"
                   and not waiting_on_conflict(index, i)]

    undeclared: list[dict[str, Any]] = []
    for sha, _ in heads:
        try:
            result = claims_check(root, f"{base}..{sha}")
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
    # a settled conflict holds once: git wrote this commit's tree before its hook ran, so
    # the commit that finishes it ("finish the merge") records the settled version
    held = bool(undeclared or collisions or unstaged or unreadable or settled)
    code = 1 if held else 4 if (conflicts or unconfirmed) else 0
    report = PremergeReport(merging=theirs, into=ours, touched=tuple(touched),
                            unconfirmed=tuple(unconfirmed), undeclared=tuple(undeclared),
                            intent_conflicts=tuple(conflicts), collisions=tuple(collisions),
                            unstaged=unstaged, unreadable=unreadable, settled=settled,
                            operation=operation, exit=code)
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
    merge = report.operation in ("merge", "fast-forward")
    if report.operation == "fast-forward":
        out = [owner_text.FF_HEADER.format(merging=report.merging, into=report.into)]
        finish = "finish the merge"
    elif merge:
        out = [f"plumb: quick merge check (no test run): {report.merging} into {report.into}"]
        finish = "finish the merge"
    else:
        out = [f"plumb: quick check of this {report.operation} step (no test run): "
               f"{report.into}"]
        finish = f"continue the {report.operation}"
    out.extend(report.settled)
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
    if report.exit and report.operation == "fast-forward":
        out.append(owner_text.FF_UNDONE.format(merging=report.merging, into=report.into))
    elif report.exit:
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


def _apply_settled(core: Any) -> list[str]:
    try:
        from plumb.awareness.answer import apply_settled

        return apply_settled(core)
    except Exception:  # noqa: BLE001 - the conflict then holds, and its card asks
        return []


def fast_forward_of(root: Path) -> tuple[str, str, str] | None:
    """``(before, after, name)`` when the merge git just recorded moved the default branch
    to another line's commit without a merge commit of its own (a fast-forward); None for
    any other merge, another branch, a squash or an up-to-date merge. A few git calls."""
    root = Path(root)
    branch = (_git(root, "symbolic-ref", "--short", "-q", "HEAD") or "").strip()
    if not branch or branch != default_branch_of(root):
        return None
    before = (_git(root, "rev-parse", "-q", "--verify", "ORIG_HEAD") or "").strip()
    after = (_git(root, "rev-parse", "-q", "--verify", "HEAD") or "").strip()
    if not before or not after or before == after:
        return None
    parents = (_git(root, "rev-list", "--parents", "-n", "1", after) or "").split()[1:]
    if len(parents) > 1 and parents[0] == before:
        return None  # the merge commit this merge made: pre-merge-commit checked it
    if _git(root, "merge-base", "--is-ancestor", before, after) is None:
        return None
    name = (_git(root, "name-rev", "--name-only", f"--exclude=refs/heads/{branch}",
                 "--exclude=refs/tags/*", after) or "").strip()
    name = name.removeprefix("remotes/").split("~")[0].split("^")[0]
    if not name or name == "undefined":
        subject = (_git(root, "reflog", "-1", "--format=%gs") or "").strip()
        words = subject.split(":", 1)[0].split()
        name = words[-1] if len(words) > 1 and words[0] in ("merge", "pull") else after[:12]
    return before, after, name


def run_post_merge(root: Path) -> int:
    """``plumb merge-check --hook post-merge``: when git fast-forwarded the default branch,
    run the quick check over what came in; when it holds, put the branch back where it was
    (``git reset --keep``: local changes stay) so nothing held stays recorded (R17). git
    ignores this hook's exit; the lines tell the owner what happened."""
    from plumb.api import open_core
    from plumb.mergedriver.driver import labels_of

    root = Path(root)
    if (_git(root, "config", "--bool", HOLD_KEY) or "").strip() == "false":
        return 0
    found = fast_forward_of(root)
    if found is None:
        return 0
    before, _after, name = found
    try:
        report = check(open_core(root), fast_forward=found)
    except Exception as exc:  # noqa: BLE001 - a check that cannot run holds (fail closed)
        into = labels_of(root, [])[0]
        report = _with_lines(PremergeReport(
            merging=name, into=into, operation="fast-forward", exit=1,
            unreadable=({"path": "", "line": f"  the check could not run: {exc}"},)))
    for line in report.lines:
        print(line)
    if not report.exit:
        return 0
    try:
        _git(root, "reset", "-q", "--keep", before, check=True)
    except subprocess.CalledProcessError as exc:
        why = (exc.stderr or exc.stdout or "").strip().splitlines()
        print(owner_text.FF_NOT_UNDONE.format(into=report.into, merging=name,
                                              why=why[-1] if why else "git refused"))
    return report.exit


def run_hook(core: Any, hook: str = HOOK) -> int:
    """``plumb merge-check --hook pre-merge-commit`` (or ``prepare-commit-msg``): print the
    report, return its exit."""
    report = check(core, hook=hook)
    for line in report.lines or render(report):
        print(line)
    return report.exit
