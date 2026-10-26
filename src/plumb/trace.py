"""Untraced changes: changed source paths that no requirement owns (spec 5.11, 6.4).

A requirement owns a path through an ``implemented_by`` or ``verified_by`` end (a test node
end owns its file). A changed source path that no requirement owns is work that escaped the
translation chain: no read-back, no examples, nothing for the owner to confirm. The stop hook
tells the agent to read it back and record it as a proposed SR; the merge boundary puts it to
the owner with the unconfirmed touched requirements.

``is_code_path`` is the one definition of "source" that the trace (stop hook, prompt hook,
merge boundary) and the verify lane's covering-test selection share:

- a file under a ``source_dirs`` entry that is not a test directory. With a source directory
  of ``.``, documentation (``*.md``, ``*.rst``, ``*.txt``, ``docs/``) and dot directories are
  left out;
- when ``.plumb/config.yaml`` does not name ``source_dirs`` (the default), also any code file
  (by suffix) anywhere outside the test directories, ``docs/`` and dot directories, so a flat
  layout (``mypkg/``) or a root-level module is never invisible.

Test directories, plumb's own state (``.plumb/``, ``.git/``, ``.claude/``) and generated files
(``__pycache__``, ``*.pyc``, tool caches, build output) are never source. For the trace, shared
test infrastructure (``verify.infra_globs``) and the owner's ``trace.exempt`` globs are left
out too. Pure string work over the record index: cheap enough per turn.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import Any

from plumb.hashing import clean_rel_path, target_path

OWNING_KINDS = ("implemented_by", "verified_by")
_DOC_SUFFIXES = (".md", ".rst", ".txt")
_NEVER = (".plumb/", ".git/", ".claude/")
# SR-374 EX-10: vendored example files shipped inside templates are never untraced
DEFAULT_EXEMPT = ("**/templates/**/vendor/**",)
_GENERATED_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                              "node_modules", ".venv", "venv", "build", "dist"})
_GENERATED_SUFFIXES = (".pyc", ".pyo")
# code files that count as source outside ``source_dirs`` when the layout is not configured
CODE_SUFFIXES = frozenset({
    ".py", ".pyi", ".pyx", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".go", ".rs",
    ".java", ".kt", ".scala", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".rb", ".php",
    ".swift", ".lua", ".sh", ".ps1", ".sql"})


def owning_end(link: Any) -> str | None:
    """``implemented_by src/x.py``: the key of an owning link's end, or None for other links.

    A symbol or test-node end keeps its name, so a new symbol in an owned file is a new end."""
    if link.kind not in OWNING_KINDS:
        return None
    target = link.target
    end = target.test or target_path(target)
    rel = clean_rel_path(end) if end else None
    if not rel:
        return None
    if target.symbol and not target.test:
        rel = f"{rel}#{target.symbol}"
    return f"{link.kind} {rel}"


def owning_ends(record: Any) -> list[str]:
    """The sorted owning ends of a requirement (empty for other kinds)."""
    if record.kind != "requirement":
        return []
    return sorted({e for e in (owning_end(link) for link in record.links) if e})


def owned_paths(core: Any) -> set[str]:
    """Every path a requirement's ``implemented_by`` or ``verified_by`` end names."""
    out: set[str] = set()
    for record in core.index().values():
        if record.kind != "requirement":
            continue
        for link in record.links:
            if link.kind not in OWNING_KINDS:
                continue
            end = target_path(link.target)
            rel = clean_rel_path(end) if end else None
            if rel:
                out.add(rel)
    return out


def _under(rel: str, directory: str) -> bool:
    directory = directory.strip("/")
    return directory in ("", ".") or rel == directory or rel.startswith(directory + "/")


def _matches(rel: str, globs: Iterable[str]) -> bool:
    folded = rel.casefold()
    for pattern in globs:
        pattern = str(pattern).casefold()
        if pattern.startswith("**/"):
            tail = pattern[3:]
            if fnmatch.fnmatchcase(folded, tail) or fnmatch.fnmatchcase(folded, "*/" + tail):
                return True
        elif fnmatch.fnmatchcase(folded, pattern):
            return True
    return False


def _doc_or_dot(rel: str) -> bool:
    return (rel.endswith(_DOC_SUFFIXES) or rel.startswith("docs/")
            or any(part.startswith(".") for part in rel.split("/")))


def is_code_path(config: Any, rel: str) -> bool:
    """Whether ``rel`` is source code by the repository layout (no infra or exemptions)."""
    if rel.startswith(_NEVER) or rel.endswith(_GENERATED_SUFFIXES):
        return False
    if _GENERATED_PARTS & set(rel.split("/")) or ".egg-info/" in rel:
        return False  # generated, never authored: an unignored cache is not a change
    tests = {t.strip("/") for t in config.test_dirs}
    if any(_under(rel, d) for d in tests if d not in ("", ".")):
        return False
    homes = [d for d in config.source_dirs if _under(rel, d) and d.strip("/") not in tests]
    if homes:
        if all(d.strip("/") in ("", ".") for d in homes) and _doc_or_dot(rel):
            return False
        return True
    if getattr(config, "source_dirs_set", True):
        return False
    # no configured layout: a code file anywhere outside tests, docs and dot directories
    return PurePosixPath(rel).suffix.lower() in CODE_SUFFIXES and not _doc_or_dot(rel)


def is_source_path(config: Any, rel: str, *, exempt: Sequence[str] | None = None) -> bool:
    """Whether a change to ``rel`` needs a requirement under ``config``.

    ``exempt`` replaces ``config.trace.exempt`` (the merge boundary honours only the
    exemptions the owner has seen)."""
    if not is_code_path(config, rel):
        return False
    if _matches(rel, config.verify.infra_globs) or _matches(rel, DEFAULT_EXEMPT):
        return False
    return not _matches(rel, config.trace.exempt if exempt is None else exempt)


def is_source(core: Any, rel: str) -> bool:
    """Whether ``rel`` is a source path whose change needs a requirement."""
    return is_source_path(core.config, rel)


def untraced_paths(core: Any, paths: Iterable[str], *, configs: Sequence[Any] | None = None,
                   exempt: Sequence[str] | None = None) -> list[str]:
    """The changed source paths of ``paths`` that no requirement owns, in input order.

    A path counts as source when it is source under any of ``configs`` (default: the current
    config), so a config edit that narrows the layout cannot hide a change at the merge
    boundary; ``exempt`` replaces each config's ``trace.exempt``."""
    owned = owned_paths(core)
    configs = list(configs) if configs else [core.config]
    out: list[str] = []
    for raw in paths:
        rel = clean_rel_path(raw)
        if not rel or rel in out or rel in owned:
            continue
        if any(is_source_path(c, rel, exempt=exempt) for c in configs):
            out.append(rel)
    return out


# The ownership proposals the untraced instruction carries are bounded: at most the shown
# paths, and no new judgment once this much time has gone (a JEV call is 70-500 ms).
PROPOSAL_BUDGET_S = 0.6


def ownership_lines(core: Any, paths: Sequence[str], *, limit: int = 4,
                    budget_s: float = PROPOSAL_BUDGET_S) -> list[str]:
    """The proposed owning requirement of each untraced path (R12.3, SR-044), one line per
    path, from CAPTURE's ``ownership_proposals``: proposals for the agent's read-back only,
    never a link. Bounded by ``limit`` paths and ``budget_s``; empty without CAPTURE."""
    import time

    try:
        from plumb.capture.api import ownership_proposals
    except ImportError:
        return []
    started = time.monotonic()
    out: list[str] = []
    for path in list(paths)[:limit]:
        if time.monotonic() - started > budget_s:
            break
        proposal = ownership_proposals(core, [path]).get(path)
        line = str(getattr(proposal, "line", "") or "")
        if line:
            out.append(line.removeprefix("plumb: "))
    return out


def trace_instruction(paths: list[str], limit: int = 4, *, core: Any = None) -> str:
    """The one-line agent-facing instruction for untraced changes (non-blocking, R1).

    The one builder of the untraced-change instruction (the Claude Code stop and prompt
    hooks, and through them ``plumb turn end`` and every adapter): given ``core``, it carries
    the ownership proposal of each shown path (``ownership_lines``) for the read-back."""
    shown = ", ".join(paths[:limit]) + (f" +{len(paths) - limit} more" if len(paths) > limit
                                         else "")
    text = (f"plumb: untraced change: {shown} changed with no requirement owning it. Read the "
            "change back to the owner in their terms (what will and won't be done, "
            "assumptions labelled), record it as a proposed SR with given/when/then examples "
            "(edge cases too) deriving from an INT, and link it implemented_by those paths.")
    if core is not None:
        try:
            proposals = ownership_lines(core, paths, limit=limit)
        except Exception:  # noqa: BLE001 - a proposal never costs the instruction itself
            proposals = []
        if proposals:
            text += " Proposed owners: " + " | ".join(proposals)
    return text
