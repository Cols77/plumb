"""The merge-time safety net: git's ``pre-merge-commit`` hook (sp6 10, R17; SR-077).

R17 (owner, 2026-10-07): a CHEAP merge-time check holds a merge carrying a leftover intent
conflict, unconfirmed requirements or undeclared files, WITHOUT running the test suite; the
single full suite runs at push (the pre-push hook). Never run the suite twice.

``plumb merge-check --hook pre-merge-commit`` is that check. It reads the staged merge result
against ``HEAD`` (the first parent) and the incoming commits ``HEAD..MERGE_HEAD``: the open
intent conflicts (exit 4), the touched requirements not yet confirmed (exit 4), the files the
incoming commits changed without a requirement declaring them (exit 1) and two records
holding one ID (exit 1). No test run, no verification evidence, no judgment backend call
(cards show a judgment only when one is already logged: ``conflict_rows(hook=True)``), no
log write, no log-integrity diff: a few git calls and the record index. A non-zero exit
refuses the merge commit; the merge stays in progress until it is settled, then the owner
says "finish the merge". git runs this hook only when ``git merge`` commits on its own;
a merge finished with ``git commit`` is covered by the pre-push hook (installed with this
one) and ``/plumb merge-check``.

``plumb hooks install`` and ``plumb init`` install it by default (R17); ``plumb merge-check
--install-pre-merge-commit`` and ``--uninstall-pre-merge-commit`` mirror the pre-push hook: the
shared hooks directory, a marker line, a foreign hook left untouched (its ``hook_line`` in
``--json``). ``git merge --no-verify`` bypasses it, like any git hook.
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


def hook_path(root: Path) -> Path:
    out = (_git(Path(root), "rev-parse", "--git-path", f"hooks/{HOOK}", check=True) or "")
    path = Path(out.strip())
    return path if path.is_absolute() else Path(root) / path


def _exe(interpreter: str) -> str:
    return interpreter.replace("\\", "/")


def hook_line(interpreter: str) -> str:
    """The line an owner's own hook runs to call plumb (``--json``'s ``hook_line``)."""
    return f'"{_exe(interpreter)}" -m plumb merge-check --hook {HOOK} || exit $?'


def hook_text(interpreter: str) -> str:
    return (f"#!/bin/sh\n{HOOK_MARKER} (written by plumb; a quick check, no test run)\n"
            f'exec "{_exe(interpreter)}" -m plumb merge-check --hook {HOOK}\n')


def _is_plumb(path: Path) -> bool:
    try:
        return HOOK_MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ForeignHookError(f"cannot read the existing hook {path}: {exc}") from exc


def install_hook(root: Path, interpreter: str) -> Path:
    """Write plumb's pre-merge-commit hook (idempotent); a foreign hook raises
    ``ForeignHookError`` and is left untouched."""
    path = hook_path(Path(root))
    if path.exists() and not _is_plumb(path):
        raise ForeignHookError(owner_text.FOREIGN_HOOK)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(hook_text(interpreter).encode("utf-8"))
    try:
        path.chmod(0o755)
    except OSError:
        pass
    return path


def uninstall_hook(root: Path) -> bool:
    """Remove plumb's hook; False (and left) when it is foreign or absent."""
    path = hook_path(Path(root))
    if not path.exists() or not _is_plumb(path):
        return False
    path.unlink()
    return True


def hook_state(root: Path) -> str:
    """``plumb`` | ``non-plumb`` | ``not installed``."""
    try:
        path = hook_path(Path(root))
    except (OSError, subprocess.CalledProcessError):
        return "not installed"
    if not path.exists():
        return "not installed"
    try:
        return "plumb" if _is_plumb(path) else "non-plumb"
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


def check(core: Any) -> PremergeReport:
    """The quick check of the merge in progress (``GITHEAD_*`` in the hook, else
    ``MERGE_HEAD``)."""
    from plumb.claims import claims_check, load_policy
    from plumb.merge import required_records, touched_requirements
    from plumb.mergedriver.conflicts import conflict_rows
    from plumb.mergedriver.driver import labels_of

    root = Path(core.root)
    heads = incoming_heads(root)
    if not heads:
        return PremergeReport(skipped="no merge in progress")
    ours = labels_of(root, [])[0]
    theirs = ", ".join(name for _, name in heads)
    staged = _git(root, "diff", "--cached", "--name-only", "-z", "HEAD") or ""
    paths = sorted({p for p in staged.split("\0") if p})
    messages: list[str] = []
    for sha, _ in heads:
        log = _git(root, "log", "--format=%B%x00", f"HEAD..{sha}") or ""
        messages += [m for m in log.split("\0") if m.strip()]

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
    code = 1 if (undeclared or collisions) else 4 if (conflicts or unconfirmed) else 0
    report = PremergeReport(merging=theirs, into=ours, touched=tuple(touched),
                            unconfirmed=tuple(unconfirmed), undeclared=tuple(undeclared),
                            intent_conflicts=tuple(conflicts), collisions=tuple(collisions),
                            exit=code)
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
    out = [f"plumb: quick merge check (no test run): {report.merging} into {report.into}"]
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
    if report.exit:
        out.append(owner_text.MERGE_HELD)
    else:
        out.append(owner_text.PREMERGE_OK)
    return out


def run_hook(core: Any) -> int:
    """``plumb merge-check --hook pre-merge-commit``: print the report, return its exit."""
    report = check(core)
    for line in report.lines or render(report):
        print(line)
    return report.exit
