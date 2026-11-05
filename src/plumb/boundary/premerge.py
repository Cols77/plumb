"""The merge-time safety net: git's ``pre-merge-commit``, ``prepare-commit-msg`` and
``post-merge`` hooks (sp6 10, R17; SR-077).

R17 (owner, 2026-10-07): a CHEAP merge-time check, WITHOUT running the test suite; the
single full suite runs at push (the pre-push hook). Never run the suite twice.

What holds (SR-260, DEC-252, DEC-255 to DEC-257), first of 1, 5, 4: integrity (exit 1:
unstaged or unreadable record files, a settled-once conflict, colliding ids, new stale links,
new links to untested files, validate errors, a broken log); what the report's
``verification_holds`` holds on, read from the recorded evidence (SR-254: a failing or
regressed acceptance test, one with no passing run on the current code, a full run pending,
unreadable evidence), so both forms exit alike (EX-10), and for a merge into the default branch a
delivered requirement (an incoming SR trailer) whose proof is not shown working or not
confirmed by the owner (exit 5); an open intent conflict, a contradiction the judge is sure
of, or a question waiting for the owner on a required record (exit 4). Records waiting on a
judge, paths no trailer declares and a claims policy the check cannot read are listed, never
held.

The guarantee: no commit that records another line's work is made (or, for a fast-forward
of the default branch, stays) while what it records carries one of those. Its entry points,
all through ``check``:

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

No test run (a failing test is read from the recorded evidence), no judgment backend call
(cards show a judgment only when one is already logged: ``conflict_rows(hook=True)``), no
log-integrity diff: a few git calls and the record index. Its one write: an intent conflict
the owner already answered before work began is settled with that answer (R17, ``check``).
A non-zero exit refuses the commit; the operation stays in progress until it is settled, then the owner says
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

from plumb import launcher
from plumb.boundary.prepush import ForeignHookError
from plumb.present import owner_text

HOOK = "pre-merge-commit"
HOOK_MARKER = "# plumb pre-merge-commit hook"
COMMIT_HOOK = "prepare-commit-msg"
COMMIT_HOOK_MARKER = "# plumb prepare-commit-msg hook"
POST_HOOK = "post-merge"
POST_HOOK_MARKER = "# plumb post-merge hook"
LAND_HOOK = "post-commit"          # a merge finished by `git commit` fires no post-merge (SR-296)
LAND_HOOK_MARKER = "# plumb post-commit hook"
MARKERS = {HOOK: HOOK_MARKER, COMMIT_HOOK: COMMIT_HOOK_MARKER, POST_HOOK: POST_HOOK_MARKER,
           LAND_HOOK: LAND_HOOK_MARKER}
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
    return f'{launcher.prefix(interpreter)} merge-check --hook {hook} || exit $?'


def hook_text(interpreter: str) -> str:
    return (f"#!/bin/sh\n{HOOK_MARKER} (written by plumb; a quick check, no test run)\n"
            + launcher.git_hook_line(interpreter, HOOK, f"merge-check --hook {HOOK}"))


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
            + launcher.git_hook_line(interpreter, COMMIT_HOOK,
                                     f"merge-check --hook {COMMIT_HOOK}"))


def post_hook_text(interpreter: str) -> str:
    """post-merge: git runs it after a merge it recorded, a fast-forward included. Its shell
    line exits at once for a squash; every other merge starts Python, which withdraws the
    merged branch's cards (SR-132) whatever ``plumb.mergeHold`` says."""
    return (f"#!/bin/sh{NL}{POST_HOOK_MARKER} (written by plumb; puts the default branch back "
            f"when a fast-forward brings in what the quick merge check holds; no test run){NL}"
            f'[ "$1" = 1 ] && exit 0{NL}'
            + launcher.git_hook_line(interpreter, POST_HOOK,
                                     f"merge-check --hook {POST_HOOK}"))


def land_hook_text(interpreter: str) -> str:
    """post-commit: its shell line exits at once unless the commit has two parents."""
    return (f"#!/bin/sh{NL}{LAND_HOOK_MARKER} (written by plumb; starts the landing job when a "
            f"merge finished by hand lands on the default branch){NL}"
            f'git rev-parse -q --verify HEAD^2 >/dev/null 2>&1 || exit 0{NL}'
            + launcher.git_hook_line(interpreter, LAND_HOOK, f"merge-check --hook {LAND_HOOK}"))


def refresh_post_hook(root: Path) -> None:
    """An older post-merge hook exits before Python for a merge commit and with mergeHold
    false; drop those lines so every merge reaches the withdrawal (SR-132)."""
    path = post_hook_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    lines = text.split("\n")
    kept = [ln for ln in lines if "HEAD^2" not in ln and HOLD_KEY not in ln
            and not ln.startswith("o=$(git rev-parse")]
    if POST_HOOK_MARKER in text and len(kept) != len(lines):
        path.write_bytes("\n".join(kept).encode("utf-8"))


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
            POST_HOOK: post_hook_text, LAND_HOOK: land_hook_text}[hook](interpreter)
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


def install_land_hook(root: Path, interpreter: str) -> Path:
    """Write plumb's post-commit hook (idempotent); a foreign hook raises ``ForeignHookError``."""
    return _install(root, interpreter, LAND_HOOK)


def land_hook_path(root: Path) -> Path:
    return hook_path(root, LAND_HOOK)


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
    unconfirmed: tuple[Mapping[str, Any], ...] = ()      # {id, title, state}: listed only
    undeclared: tuple[Mapping[str, Any], ...] = ()       # {commit, path, claims}: listed only
    claims_errors: tuple[str, ...] = ()  # the claims check could not read a range: listed
    questions: tuple[Mapping[str, Any], ...] = ()  # SR-260 EX-30 {key, records, titles} (4)
    failing_tests: tuple[Mapping[str, Any], ...] = ()  # {id, title, test, state} (exit 5)
    verify_lines: tuple[str, ...] = ()  # SR-254: pending, unavailable, regressions (exit 5)
    proofs: tuple[Mapping[str, Any], ...] = ()  # DEC-256 {id, title, why}, into default (5)
    intent_conflicts: tuple[Mapping[str, Any], ...] = ()  # {ic, record, title, card}
    collisions: tuple[Mapping[str, Any], ...] = ()       # {id, line}
    unstaged: tuple[str, ...] = ()       # .plumb/ paths that differ from the index committed
    unreadable: tuple[Mapping[str, Any], ...] = ()       # {path, line}
    settled: tuple[str, ...] = ()        # R17: conflicts the owner's earlier answer settled
    stale_links: tuple[str, ...] = ()    # SR-166: links the merge leaves stale
    untested_links: tuple[str, ...] = ()  # SR-166: links the merge adds to files no test covers
    validate_errors: tuple[str, ...] = ()  # SR-306: every validate error of the result
    contradictions: tuple[str, ...] = ()  # SR-165: new requirements against live ones
    contradiction_notes: tuple[str, ...] = ()  # unsure verdicts: shown, never held on
    judge_note: str = ""                 # set when the contradiction check could not judge
    into_default: bool = True    # DEC-271: tests, questions and proofs hold only into it
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
        # an untracked log entry is the landing job's to commit, never a hold (SR-329): the
        # check's own judge calls write some while it runs
        if y != " " and not (x == "?" and path.startswith(".plumb/log/")):
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
    claims_errors: list[str] = []
    for sha, _ in heads:
        try:
            result = claims_check(root, f"{base}..{sha}")
            for item in result.get("undeclared") or []:
                undeclared.append({"commit": str(item.get("commit")), "path": item.get("path"),
                                   "claims": list(item.get("claims") or [])})
            if load_policy(root).require_trailer:
                for unclaimed in result.get("unclaimed_commits") or []:
                    undeclared.append({"commit": str(unclaimed), "path": None, "claims": []})
            claims_errors += [f"  .plumb/claims.yaml: {p}" for p in result.get("problems") or ()
                              if f"  .plumb/claims.yaml: {p}" not in claims_errors]
        except Exception as exc:  # noqa: BLE001 - listed like the report's (gates.claims_gate)
            claims_errors.append(f"  the claims check could not read {base}..{sha}: {exc}")

    conflicts = conflict_rows(core, hook=True)
    collisions = _collisions(core)
    stale_links, untested_links = _link_problems(core, base, paths, index)
    from plumb.validate import validate

    findings = validate(core)   # one pass, shared by both checks (it re-reads the log chain)
    validate_errors = _errors(core, base, findings)
    contradictions, contradiction_notes, judge_note = _contradictions(core, base, paths, index,
                                                                      findings)
    questions = open_questions_on(core, required)
    from plumb.boundary.report import verification_holds
    from plumb.merge import _verification

    # the report's own reading of the evidence, so both forms hold alike (EX-10); no test run
    verification = _verification(core, touched, paths, base)
    failing_tests = failing_tests_of(core, verification)
    main = ours == default_branch_of(root)   # DEC-271: tests, questions, proofs hold main only
    proofs = delivered_proofs(core, messages) if main else []
    # a settled conflict holds once: git wrote this commit's tree before its hook ran, so
    # the commit that finishes it ("finish the merge") records the settled version
    held = bool(collisions or unstaged or unreadable or settled
                or stale_links or untested_links or validate_errors)
    code = 1 if held else 5 if main and (verification_holds(verification) or proofs) else \
        4 if (conflicts or contradictions or (main and questions)) else 0
    report = PremergeReport(merging=theirs, into=ours, touched=tuple(touched),
                            unconfirmed=tuple(unconfirmed), undeclared=tuple(undeclared),
                            claims_errors=tuple(claims_errors), questions=tuple(questions),
                            failing_tests=tuple(failing_tests), proofs=tuple(proofs),
                            verify_lines=tuple(verification_lines(verification)),
                            intent_conflicts=tuple(conflicts), collisions=tuple(collisions),
                            unstaged=unstaged, unreadable=unreadable, settled=settled,
                            stale_links=tuple(stale_links), untested_links=tuple(untested_links),
                            validate_errors=tuple(validate_errors),
                            contradictions=tuple(contradictions),
                            contradiction_notes=tuple(contradiction_notes),
                            judge_note=judge_note, into_default=main,
                            operation=operation, exit=code)
    return _with_lines(report)


def open_questions_on(core: Any, required: Sequence[str]) -> list[dict[str, Any]]:
    """SR-260 EX-30: the judge's questions still waiting for the owner, in every session
    (``judge.open_questions``), that ask about a record of ``required``: ``{key, question,
    records, titles}``. Unreadable questions name nothing (the status line's rule)."""
    want = set(required)
    if not want:
        return []
    index = core.index()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted((Path(core.root) / ".plumb" / "session").glob("*/judge_questions.json")):
        try:
            from plumb.understand import judge

            asked = judge.open_questions(core, path.parent.name)
        except Exception:  # noqa: BLE001
            continue
        for question in asked:
            ids = [str(r.get("id")) for r in question.get("records") or ()
                   if isinstance(r, Mapping) and str(r.get("id")) in want]
            key = str(question.get("key") or question.get("question") or "")
            if ids and key not in seen:
                seen.add(key)
                rows.append({"key": key, "question": question.get("question"), "records": ids,
                             "titles": [index[i].title for i in ids if i in index]})
    return rows


def failing_tests_of(core: Any, verification: Mapping[str, Any]) -> list[dict[str, Any]]:
    """SR-260 (c), SR-254: the acceptance tests ``merge._verification`` holds on, read from
    the evidence with no test run (the report's ``failing`` and ``unverified``):
    ``{id, title, test, state}``, ``state`` failing, regression, never run or stale."""
    index = core.index()
    rows: list[dict[str, Any]] = []
    for key in ("failing", "unverified"):
        for record_id, items in (verification.get(key) or {}).items():
            for item in items:
                if key == "failing":
                    state = "regression" if item.get("regression") else "failing"
                else:
                    state = "never run" if item.get("state") == "none" else \
                        "stale since its last pass"
                rows.append({"id": record_id, "test": item.get("test"), "state": state,
                             "title": getattr(index.get(record_id), "title", record_id)})
    return rows


def verification_lines(verification: Mapping[str, Any]) -> list[str]:
    """The rest of what ``report.verification_holds`` holds on, in the owner's words: a
    verification that could not be read, a full run pending, a regression."""
    if not verification.get("available"):
        return [owner_text.PREMERGE_VERIFY_UNAVAILABLE.format(
            error=verification.get("error") or "no verification lane")]
    out = []
    if verification.get("full_pending") and not verification.get("full_waived"):
        out.append(owner_text.PREMERGE_FULL_PENDING.format(
            reasons=", ".join(verification.get("full_pending_reasons") or ())))
    out += [owner_text.PREMERGE_REGRESSION.format(test=t)
            for t in verification.get("regressions") or ()]
    return out


def delivered_proofs(core: Any, messages: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    """SR-260 (d), DEC-256, EX-28: the requirements the incoming commits' SR trailers name
    (read through every renumber) whose proof is not shown working or not confirmed by the
    owner (``proof.unconfirmed_proofs``). Asked only of a merge into the default branch."""
    from plumb.capture.proof import unconfirmed_proofs
    from plumb.claims import claimed_ids, trailer_aliases

    if not messages:
        return []
    aliases = trailer_aliases(core)
    ids = [i for sha, message in messages for i in claimed_ids(aliases, sha, message)]
    return unconfirmed_proofs(core, ids)


def merged_messages(root: Path, base: str) -> list[tuple[str, str]]:
    """``(commit, message)`` of the commits a merge brings in: those of ``base..HEAD`` not
    on HEAD's first-parent line (what earlier merges brought), and those of a merge in
    progress (``incoming_heads``). A commit made on the branch itself is no delivery
    (DEC-256: a proof holds a merge into the default branch, not a direct commit)."""
    root = Path(root)
    own = set((_git(root, "rev-list", "--first-parent", f"{base}..HEAD") or "").split())
    ranges = [f"{base}..HEAD", *(f"HEAD..{sha}" for sha, _ in incoming_heads(root))]
    out: list[tuple[str, str]] = []
    for rng in ranges:
        for entry in (_git(root, "log", "--format=%H%x1f%B%x00", rng) or "").split("\0"):
            commit, _sep, message = entry.strip("\n").partition("\x1f")
            if commit and message.strip() and commit not in own:
                out.append((commit, message))
    return out


def _link_problems(core: Any, base: str, paths: Sequence[str],
                   index: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """SR-166 EX-3: the stale links of the changed files' records, and the implemented_by
    links this merge adds (not in ``base``) to files no test covers."""
    from plumb import stale

    changed = set(paths)
    try:   # only the links this merge made stale: those already stale at base are old debt
        near = [r for r in stale.stale_rows(core)
                if r.what in changed or getattr(index.get(r.record), "path", "") in changed]
        stale_links = [f"  {r.link} -> {r.what}"
                       for r in stale.new_rows(Path(core.root), base, near)]
    except Exception:  # noqa: BLE001 - an unreadable link state is not this check's hold
        stale_links = []
    untested: list[str] = []
    tmap = None
    before_of: dict[str, str] = {}
    for record in index.values():
        for link in record.links:
            target = link.target.path
            if link.kind != "implemented_by" or not target or not (
                    record.path in changed or target in changed):
                continue
            if record.path not in before_of:   # one read per record, not per link
                before_of[record.path] = _git(Path(core.root), "show",
                                              f"{base}:{record.path}") or ""
            if target in before_of[record.path]:
                continue
            try:
                if tmap is None:
                    from plumb.verify import open_verify

                    tmap = open_verify(core).test_map()
                    if not tmap.test_files:   # a project with no tests: nothing is covered yet
                        return stale_links, []
                covered = tmap.covering(target) or tmap.verified_tests(target)
            except Exception:  # noqa: BLE001 - no test map: cannot tell, so not held
                return stale_links, []
            if not covered:
                untested.append(f"  {link.id} -> {target}")
    return stale_links, untested


def _errors(core: Any, base: str = "", findings: Sequence[Any] | None = None) -> list[str]:
    """SR-306: every validate error of the result, whether or not the base had it. With
    ``base``, SR-322: each committed log entry the result deletes from it that no archive
    segment of its kind keeps."""
    from plumb.validate import validate

    rows = [f"  [{f.code}] {f.subject}: {f.message}"
            for f in (validate(core) if findings is None else findings) if f.severity == "error"]
    return rows + (_deleted_entries(Path(core.root), base) if base else [])


def _deleted_entries(root: Path, base: str) -> list[str]:
    """SR-322: the ``.plumb/log/<kind>/*.json`` entries of a shared kind deleted from
    ``base`` in the checked-out result whose digest is in no archive segment of the result.
    One git call; archives are read only when something was deleted."""
    from plumb import log

    out = _git(root, "diff", "--name-only", "-z", "--diff-filter=D", base, "--",
               ".plumb/log") or ""
    gone = []
    for path in filter(None, out.split("\0")):
        parts = path.split("/")
        if len(parts) == 4 and parts[3].endswith(".json") and parts[2] in log.SHARED_KINDS:
            gone.append(path)
    kept: dict[str, set[str]] = {}
    rows = []
    for path in gone:
        kind = path.split("/")[2]
        if kind not in kept:
            try:
                lines = (root / ".plumb" / "log" / kind / log.SEGMENT).read_bytes().splitlines()
            except OSError:
                lines = []
            kept[kind] = {m for m in (_digest_of(line) for line in lines) if m}
        if _digest_of(_git(root, "show", f"{base}:{path}") or "") not in kept[kind]:
            rows.append(f"  [log] {path}: committed log entry deleted by this merge and "
                        "kept in no archive segment")
    return rows


def _digest_of(text: str | bytes) -> str | None:
    import json

    try:
        raw = json.loads(text)
    except ValueError:
        return None
    return str(raw.get("digest")) if isinstance(raw, dict) else None


def drift_problems(core: Any, base: str, paths: Sequence[str]) -> dict[str, Any]:
    """The stale, untested-link and contradiction sections of a merge into ``base`` (SR-165,
    SR-166), as ``PremergeReport`` fields, for ``merge-check``'s report too."""
    index = core.index()
    stale_links, untested_links = _link_problems(core, base, paths, index)
    contradictions, notes, judge_note = _contradictions(core, base, paths, index)
    return dict(stale_links=tuple(stale_links), untested_links=tuple(untested_links),
                contradictions=tuple(contradictions), contradiction_notes=tuple(notes),
                judge_note=judge_note)


def drift_lines(report: Any) -> list[str]:
    """The lines of ``drift_problems``' sections (a premerge or a merge-check report)."""
    out: list[str] = []
    for rows, header in ((report.contradictions, owner_text.PREMERGE_CONTRADICTIONS_HEADER),
                         (report.contradiction_notes, owner_text.PREMERGE_CONTRADICTIONS_NOTE)):
        if rows:
            out += [header, *_capped(rows)]
    if report.judge_note:
        out.append(report.judge_note)
    for rows, header in ((getattr(report, "validate_errors", ()),
                          owner_text.PREMERGE_VALIDATE_HEADER),
                         (report.stale_links, owner_text.PREMERGE_STALE_HEADER),
                         (report.untested_links, owner_text.PREMERGE_UNTESTED_HEADER)):
        if rows:
            out += [header, *_capped(rows)]
    return out


def _reworded(core: Any, base: str, paths: Sequence[str], index: Mapping[str, Any]
              ) -> list[str]:
    """The requirements in ``paths`` that are new at ``base`` or whose words changed there
    (the record hash leaves the links out, so a repin is not a rewording)."""
    from plumb.model import parse_record

    out = []
    for rid, record in index.items():
        if record.kind != "requirement" or record.path not in set(paths):
            continue
        before = _git(Path(core.root), "show", f"{base}:{record.path}")
        try:
            same = before is not None and parse_record(before, record.path).hash == record.hash
        except Exception:  # noqa: BLE001 - unreadable at base: judge it
            same = False
        if not same:
            out.append(rid)
    return out


def _contradictions(core: Any, base: str, paths: Sequence[str], index: Mapping[str, Any],
                    findings: Sequence[Any] | None = None) -> tuple[list[str], list[str], str]:
    """SR-165 EX-2: the new or reworded requirements that contradict a live one, held only
    on a confident verdict and otherwise only noted (at most 5 each), with validate's
    ``supersedes`` warnings; the note when the judge could not be reached."""
    from plumb.awareness.early import check_live_rows
    from plumb.validate import validate

    ids = _reworded(core, base, paths, index)
    if not ids:
        return [], [], ""
    rows = check_live_rows(core, ids)
    said = [(line, sure) for line, sure in rows if " contradicts " in line]
    out = [f"  {line}" for line, sure in said if sure][:5]
    notes = [f"  {line}" for line, sure in said if not sure][:5]
    if not said and any(k in line for line, _ in rows
                        for k in ("judging unavailable", "no judgment", "not checked")):
        return [], [], owner_text.PREMERGE_NOT_JUDGED
    findings = validate(core) if findings is None else findings
    out += [f"  {f.subject}: {f.message}" for f in findings
            if f.code == "supersedes" and f.subject.split("#")[0] in ids]
    return out, notes, ""


def hold_lines(report: Any, into: str) -> list[str]:
    """The questions, failing tests and unproven deliveries that hold a merge (SR-260 EX-28,
    EX-30), by title (a premerge or a merge-check report)."""
    out: list[str] = []
    held = getattr(report, "into_default", True)   # DEC-271: a work branch only lists them
    questions = getattr(report, "questions", ())
    if questions:
        out.append(owner_text.PREMERGE_QUESTIONS_HEADER.format(
            held=f" ({owner_text.PREMERGE_HELD})" if held else ""))
        out.extend(_capped([owner_text.PREMERGE_QUESTION.format(title=title)
                            for q in questions for title in q.get("titles") or q["records"]]))
    failing = getattr(report, "failing_tests", ())
    if failing:
        out.append(owner_text.PREMERGE_FAILING_HEADER.format(
            held=f"{owner_text.PREMERGE_HELD}; " if held else ""))
        out.extend(_capped([owner_text.PREMERGE_FAILING.format(**r) for r in failing]))
    out.extend(getattr(report, "verify_lines", ()))
    proofs = getattr(report, "proofs", ())
    if proofs:
        out.append(owner_text.PREMERGE_PROOFS_HEADER.format(into=into))
        out.extend(_capped([(owner_text.PREMERGE_PROOF_NOT_SHOWN if r["why"] ==
                             "not shown working" else owner_text.PREMERGE_PROOF_NOT_CONFIRMED)
                            .format(title=r["title"]) for r in proofs]))
    return out


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
    out.extend(hold_lines(report, report.into))
    out.extend(drift_lines(report))
    # SR-374 EX-6: only what holds the merge is printed; records waiting on a judge, undeclared
    # paths and unreadable claims never hold it and stay in the full report (plumb context merge)
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
        return _start_landing(root)
    found = fast_forward_of(root)
    if found is None:
        return _start_landing(root)
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
        return _start_landing(root)
    try:
        _git(root, "reset", "-q", "--keep", before, check=True)
    except subprocess.CalledProcessError as exc:
        why = (exc.stderr or exc.stdout or "").strip().splitlines()
        print(owner_text.FF_NOT_UNDONE.format(into=report.into, merging=name,
                                              why=why[-1] if why else "git refused"))
    return report.exit


def run_post_commit(root: Path) -> int:
    """``plumb merge-check --hook post-commit``: a merge commit made by ``git commit`` (a held
    merge the owner finished) starts the landing job as a ``git merge`` does. ORIG_HEAD is not
    the pre-merge head here, so the first parent is."""
    return _start_landing(Path(root), "HEAD^1")


def _start_landing(root: Path, before_ref: str = "ORIG_HEAD") -> int:
    """SR-296: work that landed on the default branch (a merge commit or a fast-forward)
    starts the landing job, detached, so the hook stays within its time limit."""
    try:
        here = (_git(root, "symbolic-ref", "--short", "-q", "HEAD") or "").strip()
        if here == default_branch_of(root):
            before = (_git(root, "rev-parse", "-q", "--verify", before_ref) or "").strip()
            head = (_git(root, "rev-parse", "HEAD") or "").strip()
            moved = before and head and before != head
            if moved and _git(root, "merge-base", "--is-ancestor", before, head) is not None:
                from plumb.boundary import landing

                landing.spawn(root, head, before)
    except Exception:  # noqa: BLE001 - advisory: never fails the hook
        pass
    return 0


def run_hook(core: Any, hook: str = HOOK) -> int:
    """``plumb merge-check --hook pre-merge-commit`` (or ``prepare-commit-msg``): print the
    report, return its exit."""
    report = check(core, hook=hook)
    for line in report.lines or render(report):
        print(line)
    return report.exit
