"""The status snapshot (``.plumb/session/status.json``) the status line reads (spec 6.6).

Built by the session-start and stop hooks from CoreAPI and VerifyAPI state; the status line
itself recomputes nothing.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import (
    CoreAPI,
    FullPending,
    NodeEvidence,
    RecordStatus,
    StatusSnapshot,
    VerifyAPI,
)
from plumb.hosts.claude_code.hookio import write_json_atomic
from plumb.normalize import utc_now

SNAPSHOT_VERSION = 1


def tests_state(evidence: Mapping[str, NodeEvidence] | None
                ) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """``(tests, failing, regressions)`` for a set of node evidence."""
    if not evidence:
        return "unknown", (), ()
    regressions = tuple(sorted(n for n, e in evidence.items() if e.regression))
    failing = tuple(sorted(n for n, e in evidence.items() if e.state == "fresh-fail"))
    if regressions:
        return "regression", failing, regressions
    if failing:
        return "failing", failing, regressions
    if any(e.state in ("none", "stale") for e in evidence.values()):
        return "not-run", failing, regressions
    return "ok", failing, regressions


def open_conflict_count(core: Any) -> int:
    """sp6 8.3: the open intent conflicts (the record index only; no git, no log)."""
    try:
        from plumb.mergedriver import open_conflicts

        return len(open_conflicts(core))
    except Exception:  # noqa: BLE001 - a lane failure never breaks the snapshot
        return 0


def build_snapshot(core: CoreAPI, *, verify: VerifyAPI | None = None,
                   evidence: Mapping[str, NodeEvidence] | None = None,
                   full_pending: FullPending | None = None,
                   statuses: Mapping[str, RecordStatus] | None = None,
                   deferred: int = 0, fidelity_unjudged: Sequence[str] = (), ask: int = 0,
                   skipped: str | None = None,
                   tests_summary: tuple[str, tuple[str, ...], tuple[str, ...]] | None = None,
                   intent_summary: str = "", auto_approve: str | None = None
                   ) -> StatusSnapshot:
    """``tests_summary`` is a precomputed ``tests_state`` (the cached brief) used in place
    of ``evidence``. The status card's fields (sp5 4.1): ``confirmed_by`` counts the
    confirmed requirements by who confirmed them, ``state`` is the card's state,
    ``intent_summary`` the session's intent in plain words, ``auto_approve`` on, off or
    suspended (CAPTURE's state when that lane is built)."""
    index = core.index()
    statuses = core.status() if statuses is None else statuses
    requirements = [s for i, s in statuses.items()
                    if i in index and index[i].kind == "requirement"]
    links = [state for status in statuses.values() for state in status.links]
    if full_pending is None and verify is not None:
        full_pending = verify.full_pending()
    tests, failing, regressions = (tests_summary if tests_summary is not None
                                   else tests_state(evidence))
    confirmed_by: dict[str, int] = {}
    for status in requirements:
        if status.confirmation == "confirmed" and status.approved_by:
            key = str(status.approved_by)
            confirmed_by[key] = confirmed_by.get(key, 0) + 1
    snapshot = StatusSnapshot(
        at=utc_now(),
        requirements_total=len(requirements),
        requirements_confirmed=sum(s.confirmation == "confirmed" for s in requirements),
        proposed=sum(s.confirmation != "confirmed" and s.superseded_by is None
                     for s in statuses.values()),
        stale_links=sum(state.state == "stale" for state in links),
        dangling_links=sum(state.state == "dangling" for state in links),
        tests=tests,  # type: ignore[arg-type]
        failing=failing,
        regressions=regressions,
        deferred=deferred,
        full_pending=bool(full_pending and full_pending.pending),
        full_pending_reasons=tuple(full_pending.reasons) if full_pending else (),
        fidelity_unjudged=tuple(fidelity_unjudged),
        ask=ask,
        skipped=skipped,
        intent_summary=intent_summary,
        confirmed_by=confirmed_by,
        auto_approve=auto_approve if auto_approve is not None else auto_approve_state(core),
        conflicts=open_conflict_count(core),
    )
    from plumb.present.render import card_state

    return dataclasses.replace(snapshot, state=card_state(snapshot))


def auto_approve_state(core: CoreAPI) -> str:
    """``on``, ``off`` or ``suspended`` from CAPTURE (sp2 8.2); ``off`` without it."""
    try:
        from plumb.capture.api import auto_approve_state as state_of
    except ImportError:
        return "off"
    try:
        state = state_of(core)
    except Exception:  # noqa: BLE001 - an advisory lane never fails the snapshot
        return "off"
    if getattr(state, "suspended", False):
        return "suspended"
    return "on" if getattr(state, "effective", False) else "off"


def snapshot_dict(snapshot: StatusSnapshot) -> dict[str, Any]:
    data = dataclasses.asdict(snapshot)
    data["v"] = SNAPSHOT_VERSION
    return data


def write_snapshot(root: Path, snapshot: StatusSnapshot, *, present: Any = None) -> Path:
    """Write ``status.json``; ``present`` (``config.present``) carries the display
    preferences the status line reads with it (``ascii``, ``card``)."""
    path = Path(root) / ".plumb" / "session" / "status.json"
    data = snapshot_dict(snapshot)
    if present is not None:
        data["present"] = {"ascii": bool(getattr(present, "ascii", False)),
                           "card": str(getattr(present, "card", "compact"))}
    write_json_atomic(path, data)
    return path
