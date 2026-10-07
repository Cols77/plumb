"""Read and tamper with plumb's logs in tests, whatever their format (SP6 plan 3.2 item 7).

Tests never open ``events.jsonl`` or ``evidence.jsonl`` themselves: they go through these
helpers, so the log format (one file per entry under ``.plumb/log/<kind>/``, plus the legacy
JSONL lines during the transition) changes in one place.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from plumb import log
from plumb.paths import PlumbPaths


def entries(root: Path, stream: str) -> list[dict[str, Any]]:
    """Every entry of ``stream`` as a dict (``v``, ``kind``, ``at``, ``marker``, ``payload``,
    ``prev``, ``digest``, ``name``), in the order plumb reads them."""
    return [{"v": log.SCHEMA, "kind": e.kind, "at": e.at, "marker": e.marker,
             "payload": dict(e.payload), "prev": e.prev, "digest": e.digest, "name": e.name}
            for e in log.read(PlumbPaths(root), stream)]  # type: ignore[arg-type]


def kinds(root: Path, stream: str = "events") -> list[str]:
    return [e["kind"] for e in entries(root, stream)]


def _location(root: Path, name: str) -> tuple[Path, int | None]:
    """The file holding entry ``name`` and, for a legacy line, its 1-based line number."""
    paths = PlumbPaths(root)
    if "/" in name:
        return paths.log_dir / name, None
    file_name, _, number = name.rpartition(":")
    return paths.log_dir / file_name, int(number)


def raw_entries(root: Path, stream: str) -> list[tuple[str, str]]:
    """``(name, exact text on disk)`` of every entry of ``stream``, in read order."""
    out: list[tuple[str, str]] = []
    for entry in entries(root, stream):
        path, number = _location(root, entry["name"])
        text = path.read_text(encoding="utf-8")
        if number is not None:
            text = text.splitlines()[number - 1]
        out.append((entry["name"], text.rstrip("\n")))
    return out


def tamper(root: Path, stream: str, index: int, mutate: Callable[[str], str]) -> str:
    """Rewrite entry ``index`` (read order; negative counts from the end) in place with
    ``mutate(text)``, without recomputing anything; returns the entry's name."""
    name = entries(root, stream)[index]["name"]
    path, number = _location(root, name)
    if number is None:
        path.write_text(mutate(path.read_text(encoding="utf-8").rstrip("\n")) + "\n",
                        encoding="utf-8", newline="\n")
    else:
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[number - 1] = mutate(lines[number - 1])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return name


def delete(root: Path, stream: str, index: int) -> str:
    """Remove entry ``index`` (read order) from disk; returns its name."""
    name = entries(root, stream)[index]["name"]
    path, number = _location(root, name)
    if number is None:
        path.unlink()
    else:
        lines = path.read_text(encoding="utf-8").splitlines()
        del lines[number - 1]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8",
                        newline="\n")
    return name


def write_legacy(root: Path, stream: str, raws: list[dict[str, Any]]) -> None:
    """Append raw entries as legacy JSONL lines (the format before SP6)."""
    from plumb.normalize import canonical_json

    path = PlumbPaths(root).log_path(stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        for raw in raws:
            handle.write(canonical_json(raw) + b"\n")


def legacy_entry(kind: str, payload: dict[str, Any], prev: str | None,
                 at: str = "2026-10-05T12:00:00Z") -> dict[str, Any]:
    """A correctly chained legacy entry (digest computed)."""
    raw: dict[str, Any] = {"v": 1, "kind": kind, "at": at, "marker": "none",
                           "payload": payload, "prev": prev}
    raw["digest"] = log.entry_digest(raw)
    return raw


def entry_files(root: Path) -> list[str]:
    """``kind/file`` of every entry file under ``.plumb/log/``."""
    base = PlumbPaths(root).log_dir
    return sorted(p.relative_to(base).as_posix() for p in base.glob("*/*.json"))


def dump(raw: dict[str, Any]) -> str:
    return json.dumps(raw, sort_keys=True)
