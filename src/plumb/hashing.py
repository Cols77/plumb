"""Hashes of link ends (spec 5.4).

Records hash through ``model.record_hash``. Whole-file ends hash the file's normalized text
(raw bytes when it is not UTF-8). Symbol and test-node ends (``path::name``) are a SHOULD item
(plan KS4); until it lands they hash the whole file named before ``::``, which is stricter:
any change to that file moves the end.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from plumb.contracts import Record, Target
from plumb.normalize import file_digest


def clean_rel_path(raw: str) -> str | None:
    """A repository-relative POSIX path, or None when absolute or escaping the root.

    Root confinement mirrors pi-agent-factory's ``relations._confined_path``: an absolute
    path or any ``..`` segment is rejected on the string alone.
    """
    if not raw:
        return None
    text = raw.replace("\\", "/").strip()
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        return None
    parts = [p for p in PurePosixPath(text).parts if p != "."]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def hash_path(root: Path, raw: str) -> str | None:
    """Hash of a repository file, or None when it is missing, not a file, or outside."""
    rel = clean_rel_path(raw)
    if rel is None:
        return None
    full = Path(root) / rel
    if not full.is_file():
        return None
    try:
        return file_digest(full)
    except OSError:
        return None


def target_path(target: Target) -> str | None:
    """The file a non-record end lives in (``test`` nodes keep the part before ``::``)."""
    if target.path:
        return target.path
    if target.test:
        return target.test.split("::", 1)[0]
    return None


def hash_target(root: Path, index: Mapping[str, Record], target: Target) -> str | None:
    """Current hash of a link end, or None when it does not exist (dangling)."""
    if target.record is not None:
        record = index.get(target.record)
        return record.hash if record is not None else None
    path = target_path(target)
    if path is None:
        return None
    return hash_path(root, path)
