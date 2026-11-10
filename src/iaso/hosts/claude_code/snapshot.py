"""The status snapshot (``.iaso/session/status.json``) the status line reads (spec 6.6).

Built by the session-start and stop hooks from CoreAPI and VerifyAPI state; the status line
itself recomputes nothing.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from iaso.contracts import (
    CoreAPI,
    FullPending,
    NodeEvidence,
    RecordStatus,
    StatusSnapshot,
    VerifyAPI,
)
from iaso.hosts.claude_code.hookio import write_json_atomic
from iaso.normalize import utc_now

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
        from iaso.mergedriver import open_conflicts

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
                   intent_summary: str = "", auto_approve: str | None = None,
                   awareness: Mapping[str, Any] | None = None
                   ) -> StatusSnapshot:
    """``tests_summary`` is a precomputed ``tests_state`` (the cached brief) used in place
    of ``evidence``. The status card's fields (sp5 4.1): ``confirmed_by`` counts the
    confirmed requirements by who confirmed them, ``state`` is the card's state,
    ``intent_summary`` the session's intent in plain words, ``auto_approve`` on, off or
    suspended (CAPTURE's state when that lane is built). ``awareness``: the overlap fields
    (sp6 9.4); None reads them (``iaso.awareness.snapshot_fields``: no git process)."""
    index = core.index()
    statuses = core.status() if statuses is None else statuses
    requirements = [s for i, s in statuses.items()
                    if i in index and index[i].kind == "requirement"]
    links = [state for status in statuses.values() for state in status.links]
    if full_pending is None and verify is not None:
        full_pending = verify.full_pending()
    tests, failing, regressions = (tests_summary if tests_summary is not None
                                   else tests_state(evidence))
    from iaso.present.cards import judge_label

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
        judge_approved=sum(i in index and judge_label(s) is not None for i, s in statuses.items()),
        auto_approve=auto_approve if auto_approve is not None else auto_approve_state(core),
        conflicts=open_conflict_count(core),
        awaiting=awaiting_count(core),
        **overlap_fields(core, awareness),
    )
    from iaso.present.render import card_state

    return dataclasses.replace(snapshot, state=card_state(snapshot))


def overlap_fields(core: CoreAPI, given: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """``overlaps`` and ``overlap_labels`` (sp6 9.4); nothing when none or on any error."""
    fields = given
    if fields is None:
        try:
            from iaso.awareness.lines import snapshot_fields

            fields = snapshot_fields(core)
        except Exception:  # noqa: BLE001 - awareness is advisory
            fields = {}
    out: dict[str, Any] = {}
    if fields.get("overlaps"):
        out["overlaps"] = int(fields["overlaps"])
        out["overlap_labels"] = tuple(str(b) for b in fields.get("overlap_labels") or ())
    return out


def auto_approve_state(core: CoreAPI) -> str:
    """``on``, ``off`` or ``suspended`` from CAPTURE (sp2 8.2); ``off`` without it."""
    try:
        from iaso.capture.api import auto_approve_state as state_of
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


def awaiting_count(core: Any) -> int:
    """SR-337: the questions waiting for the owner, the band's "N await you": every session's
    judge questions not answered yet, each once, the same count /iaso status gives."""
    from iaso.understand import judge

    waiting: set[str] = set()
    sessions = Path(core.root) / ".iaso" / "session"
    for path in sorted(p for p in sessions.glob("*") if p.is_dir()):
        try:
            waiting |= {str(q.get("key")) for q in judge.open_questions(core, path.name)}
        except Exception:  # noqa: BLE001 - a count never fails the snapshot
            continue
    return len(waiting)


# the stop hook's own fields of status.json; the rest are record-wide counts (refresh_counts)
TURN_FIELDS = ("tests", "failing", "regressions", "deferred", "full_pending",
               "full_pending_reasons", "ask", "skipped", "intent_summary")


def write_turn_fields(root: Path, *, present: Any = None, **fields: Any) -> None:
    """SR-375: this turn's fields of ``status.json`` (its tests, the skipped steps, the
    intent), with the record-wide counts as the worker last wrote them (``refresh_counts``):
    the stop hook computes no link state of a record the turn did not touch."""
    from iaso.hosts.claude_code.hookio import read_json
    from iaso.present.render import card_state

    path = Path(root) / ".iaso" / "session" / "status.json"
    data = read_json(path)
    data = data if isinstance(data, dict) else {}
    data.update({k: list(v) if isinstance(v, tuple) else v for k, v in fields.items()},
                at=utc_now(), v=SNAPSHOT_VERSION)
    if present is not None:
        data["present"] = {"ascii": bool(getattr(present, "ascii", False))}
    data["state"] = card_state(data)
    write_json_atomic(path, data)


def refresh_counts(core: Any) -> None:
    """In the background worker (SR-375), and for a turn with no edit (SR-251, SR-337): the
    record-wide counts of ``status.json`` (records, links, the judge's approvals, the
    questions waiting, overlaps) brought up to date, this turn's fields kept."""
    from iaso.hosts.claude_code.hookio import read_json
    from iaso.judgment import recheck_judges
    from iaso.present.render import card_state

    recheck_judges(core)    # SR-359 EX-3: a judge that recovered stops showing red
    path = Path(core.root) / ".iaso" / "session" / "status.json"
    data = read_json(path)
    data = data if isinstance(data, dict) else {}
    fresh = snapshot_dict(build_snapshot(core, tests_summary=("unknown", (), ())))
    fresh.update({k: data[k] for k in (*TURN_FIELDS, "present", "understand_failures")
                  if k in data})
    fresh["state"] = card_state(fresh)
    write_json_atomic(path, fresh)


def write_snapshot(root: Path, snapshot: StatusSnapshot, *, present: Any = None,
                   failures: int | None = None) -> Path:
    """Write ``status.json``; ``present`` (``config.present``) carries the display
    preferences the status line reads with it (``ascii``); ``failures`` is how many
    checks in a row failed (``queue.consecutive_failures``), which the line flags at three
    (SHOW P2, spec 9.1)."""
    path = Path(root) / ".iaso" / "session" / "status.json"
    data = snapshot_dict(snapshot)
    if failures:
        data["understand_failures"] = int(failures)
    if present is not None:
        data["present"] = {"ascii": bool(getattr(present, "ascii", False))}
    write_json_atomic(path, data)
    return path
