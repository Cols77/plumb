"""Untraced changes: changed source paths that no requirement owns (spec 5.11, 6.4).

A requirement owns a path through an ``implemented_by`` or ``verified_by`` end (a test node
end owns its file). A changed source path that no requirement owns is work that escaped the
translation chain: no read-back, no examples, nothing for the owner to confirm. The stop hook
tells the agent to read it back and record it as a proposed SR; the merge boundary puts it to
the owner with the unconfirmed touched requirements.

Source paths are files under ``source_dirs`` outside ``test_dirs``, minus shared test
infrastructure (``verify.infra_globs``) and the owner's ``trace.exempt`` globs. With a source
directory of ``.``, documentation (``*.md``, ``*.rst``, ``*.txt``, ``docs/``) and dot
directories are left out too, and generated files (``__pycache__``, ``*.pyc``, tool caches,
build output) always. Pure string work over the record index: cheap enough per turn.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable

from plumb.hashing import clean_rel_path, target_path

OWNING_KINDS = ("implemented_by", "verified_by")
_DOC_SUFFIXES = (".md", ".rst", ".txt")
_NEVER = (".plumb/", ".git/", ".claude/")
_GENERATED_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                              "node_modules", ".venv", "build", "dist"})
_GENERATED_SUFFIXES = (".pyc", ".pyo")


def owned_paths(core) -> set[str]:
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


def is_source(core, rel: str) -> bool:
    """Whether ``rel`` is a source path whose change needs a requirement."""
    config = core.config
    if rel.startswith(_NEVER) or rel.endswith(_GENERATED_SUFFIXES):
        return False
    if _GENERATED_PARTS & set(rel.split("/")) or ".egg-info/" in rel:
        return False  # generated, never authored: an unignored cache is not a change
    if any(_under(rel, d) for d in config.test_dirs if d.strip("/") not in ("", ".")):
        return False
    homes = [d for d in config.source_dirs if _under(rel, d)
             and d.strip("/") not in {t.strip("/") for t in config.test_dirs}]
    if not homes:
        return False
    if all(d.strip("/") in ("", ".") for d in homes):
        if rel.endswith(_DOC_SUFFIXES) or rel.startswith("docs/") or rel.startswith("."):
            return False
    if _matches(rel, config.verify.infra_globs):
        return False
    return not _matches(rel, config.trace.exempt)


def untraced_paths(core, paths: Iterable[str]) -> list[str]:
    """The changed source paths of ``paths`` that no requirement owns, in input order."""
    owned = owned_paths(core)
    out: list[str] = []
    for raw in paths:
        rel = clean_rel_path(raw)
        if not rel or rel in out or rel in owned:
            continue
        if is_source(core, rel):
            out.append(rel)
    return out


def trace_instruction(paths: list[str], limit: int = 4) -> str:
    """The one-line agent-facing instruction for untraced changes (non-blocking, R1)."""
    shown = ", ".join(paths[:limit]) + (f" +{len(paths) - limit} more" if len(paths) > limit
                                         else "")
    return (f"plumb: untraced change: {shown} changed with no requirement owning it. Read the "
            "change back to the owner in their terms (what will and won't be done, "
            "assumptions labelled), record it as a proposed SR with given/when/then examples "
            "(edge cases too) deriving from an INT, and link it implemented_by those paths.")
