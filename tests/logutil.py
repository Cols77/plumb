"""Read and tamper with iaso's logs in tests, whatever their format (SP6 plan 3.2 item 7).

Tests never open ``events.jsonl`` or ``evidence.jsonl`` themselves: they go through these
helpers, so the log format (one file per entry under ``.iaso/log/<kind>/``, plus the legacy
JSONL lines during the transition) changes in one place.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from iaso import log
from iaso.paths import IasoPaths


def entries(root: Path, stream: str) -> list[dict[str, Any]]:
    """Every entry of ``stream`` as a dict (``v``, ``kind``, ``at``, ``marker``, ``payload``,
    ``prev``, ``digest``, ``name``), in the order iaso reads them."""
    return [{"v": log.SCHEMA, "kind": e.kind, "at": e.at, "marker": e.marker,
             "payload": dict(e.payload), "prev": e.prev, "digest": e.digest, "name": e.name}
            for e in log.read(IasoPaths(root), stream)]  # type: ignore[arg-type]


def kinds(root: Path, stream: str = "events") -> list[str]:
    return [e["kind"] for e in entries(root, stream)]


def _location(root: Path, name: str) -> tuple[Path, int | None]:
    """The file holding entry ``name`` and, for a legacy line, its 1-based line number."""
    paths = IasoPaths(root)
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
    from iaso.normalize import canonical_json

    path = IasoPaths(root).log_path(stream)
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
    """``kind/file`` of every entry file under ``.iaso/log/``."""
    base = IasoPaths(root).log_dir
    return sorted(p.relative_to(base).as_posix() for p in base.glob("*/*.json"))


def dump(raw: dict[str, Any]) -> str:
    return json.dumps(raw, sort_keys=True)


def legacy_relay(root: Path, ids: list[str], digest: str, quote: str, *,
                 self_recorded: bool = False, stated: list[str] | None = None,
                 revoke: bool = False, **extra: Any) -> None:
    """Write an agent-relayed approval (or revocation) as the prose relay wrote it.

    The relay no longer exists (SR-101 EX-9), but the entries it wrote stay in the log, and the
    surfaces that show, count, re-check and label them keep working. Tests of those surfaces
    write such an entry here instead of running the relay."""
    from iaso.api import open_core
    from iaso.approvals import approval_items
    from iaso.normalize import sha256_text

    core = open_core(root)
    if digest not in {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}:
        core.log_append("events", "prompt", {"digest": digest, "session": "s1",
                                             "at": "2026-10-06T03:00:00Z"})
    payload: dict[str, Any] = {"records": approval_items(core, ids), "by": "agent-relayed",
                               "prompt_digest": digest, "quote": quote,
                               "quote_digest": sha256_text(quote), "self_recorded": self_recorded}
    if not revoke:
        payload.update({"affirmation": "ok", "stated_set": stated, "note": ""})
    payload.update(extra)
    core.log_append("events", "revocation" if revoke else "approval", payload)
