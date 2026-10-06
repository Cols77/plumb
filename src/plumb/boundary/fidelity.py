"""Advisory fidelity at the merge boundary (sp3 6, SR-050; R4).

Touched requirements with no judgment for their current hashes, or judged ``drifts`` or
``unsure``, are listed with their ``plumb fidelity`` command. With JEV configured, up to five
packets are scored first (cheapest first, within 5 s) and the score is shown beside each; it
is never recorded, so it is never taken for the host agent's judgment. Nothing here changes
the exit code.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

JEV_MAX_PACKETS = 5
JEV_BUDGET_S = 5.0


class _NoWriteCore:
    """A read-only view of a core: the boundary writes nothing but its merge evidence, so a
    judgment backend handed this view cannot log anything."""

    def __init__(self, core: Any) -> None:
        self._core = core

    def __getattr__(self, name: str) -> Any:
        return getattr(self._core, name)

    def log_append(self, stream: str, kind: str, payload: Mapping[str, Any]) -> None:
        return None

    def write_record(self, *args: Any, **kwargs: Any) -> None:
        raise PermissionError("the merge boundary writes no records")

    def add_link(self, *args: Any, **kwargs: Any) -> None:
        raise PermissionError("the merge boundary writes no links")


def fidelity_rows(core: Any, touched: Sequence[str]) -> list[dict[str, Any]] | None:
    """``[{id, state, command}]`` or None when the judgment lane is not built."""
    try:
        from plumb.judgment.fidelity import fidelity_state, latest_judgments
    except ImportError:
        return None
    index = core.index()
    latest = latest_judgments(core)
    rows = []
    for record_id in touched:
        record = index.get(record_id)
        if record is None or record.kind != "requirement":
            continue
        state = fidelity_state(core, record, latest)
        if state in ("unjudged", "drifts", "unsure"):
            rows.append({"id": record_id, "state": state,
                         "command": f"plumb fidelity {record_id}"})
    return rows


def repinned_unjudged(core: Any, touched: Sequence[str], changed: Sequence[str]) -> list[str]:
    """Confirmed touched requirements whose ``implemented_by`` end changed in the range, is
    pinned again (current), and has no fidelity judgment for the new hashes."""
    try:
        from plumb.judgment.fidelity import fidelity_state, latest_judgments
    except ImportError:
        return []
    from plumb.hashing import clean_rel_path, target_path

    paths = {clean_rel_path(p) or p for p in changed}
    statuses = core.status(touched)
    index = core.index()
    latest = None
    out = []
    for record_id in touched:
        status = statuses.get(record_id)
        if status is None or status.confirmation != "confirmed":
            continue
        moved = False
        for state in status.links:
            end = target_path(state.link.target)
            if (state.link.kind == "implemented_by" and state.state == "current" and end
                    and (clean_rel_path(end) or end) in paths):
                moved = True
        if not moved:
            continue
        if latest is None:
            latest = latest_judgments(core)
        if fidelity_state(core, index[record_id], latest) == "unjudged":
            out.append(record_id)
    return out


def jev_scores(core: Any, rows: list[dict[str, Any]]) -> None:
    """Score up to five rows with JEV when it is the configured backend (in place)."""
    try:
        backend_name = str(core.config.judgment.backend or "").strip().lower()
    except AttributeError:
        return
    if backend_name != "jev" or not rows:
        return
    try:
        import plumb.judgment as judgment
        from plumb.judgment.fidelity import build_packet
        from plumb.verify import open_verify
    except ImportError:
        return
    view = _NoWriteCore(core)
    try:
        backend = judgment.get_backend(view, hook=False)
        verify = open_verify(view)
        packets = [(row, build_packet(view, verify, row["id"])) for row in rows]
    except Exception:
        return
    packets.sort(key=lambda item: len(repr(item[1])))  # cheapest first
    deadline = time.monotonic() + JEV_BUDGET_S
    for row, packet in packets[:JEV_MAX_PACKETS]:
        if time.monotonic() >= deadline:
            break
        try:
            result = backend.fidelity(packet)
        except Exception:
            break
        if str(getattr(result, "backend", "")).startswith("jev"):
            row["jev"] = {"verdict": result.verdict, "confidence": result.confidence,
                          "backend": result.backend}
