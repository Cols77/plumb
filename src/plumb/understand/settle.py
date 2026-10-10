"""Settling (JUDGE, SR-106, spec 7): which supported records may settle, and what happens to
the ones that do not.

J4 form: eligibility only. A decision, a member of an escalated set, an edit of a record the
owner confirmed, and a record whose premise is an option picked among several are never settled:
they wait as a trial or confirm card (``ineligible`` says which)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from plumb.contracts import CardState, Job

# why a supported record is asked on its own and never settled
DECISION, SET_MEMBER, EDIT, OPTION = "decision", "set", "edit", "option"


@dataclass(frozen=True)
class Supported:
    """A record the judge found supported, at the version judged."""

    record: Any
    score: float
    premise: Mapping[str, Any]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class Waiting:
    """A supported record that is not settled: ``reason`` is why it is asked on its own
    ('' when it simply waits for a trial batch)."""

    item: Supported
    reason: str = ""


@dataclass
class Routed:
    entries: list[Mapping[str, Any]] = field(default_factory=list)
    cards: list[CardState] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    waiting: list[Waiting] = field(default_factory=list)


def _quote(record: Any) -> str:
    quote = record.fields.get("quote")
    if isinstance(quote, (list, tuple)):
        return " ".join(str(q) for q in quote)
    return str(quote or "")


def option_picked(core: Any, record: Any) -> bool:
    """Whether the record's premise is an option picked among several: a short answer to a
    stored question that is not a plain yes (SR-091 EX-3; a yes to one proposal shown whole
    may settle, EX-4)."""
    from plumb.capture.records import is_short_answer
    from plumb.confirm import affirmation_in

    index = core.index()
    if record.kind == "intent":
        sources = [record]
    else:
        sources = [index[link.target.record] for link in record.links
                   if link.kind == "derives_from" and link.target.record in index
                   and index[link.target.record].kind == "intent"]
    affirmations = core.config.approve.affirmations
    for source in sources:
        quote = _quote(source)
        if (" ".join(str(source.fields.get("question") or "").split())
                and is_short_answer(quote) and affirmation_in(quote, affirmations) is None):
            return True
    return False


def ineligible(core: Any, record: Any, *, status: Any = None,
               approved: set[str] | None = None, escalated: Any = None) -> str:
    """'' when ``record`` may settle, else why it never does (``DECISION``, ``SET_MEMBER``,
    ``EDIT``, ``OPTION``)."""
    from plumb.capture.spec import escalated_ids, set_of
    from plumb.capture.triage import approved_before

    if record.kind not in ("intent", "requirement"):
        return DECISION
    held = escalated_ids(core) if escalated is None else escalated
    if record.id in held or record.id in set_of(core):
        return SET_MEMBER
    state = status if status is not None else core.status([record.id])[record.id]
    before = approved_before(core) if approved is None else approved
    if record.id in before and state.confirmation != "confirmed":
        return EDIT
    if option_picked(core, record):
        return OPTION
    return ""


def route(core: Any, job: Job, supported: list[Supported], *, model: str = "") -> Routed:
    """Send each supported record to settling or to a trial or confirm card. (J5 adds
    settling; until then every one waits.)"""
    routed = Routed()
    if not supported:
        return routed
    statuses = core.status([s.record.id for s in supported])
    from plumb.capture.spec import escalated_ids
    from plumb.capture.triage import approved_before

    approved, escalated = approved_before(core), escalated_ids(core)
    for item in supported:
        reason = ineligible(core, item.record, status=statuses[item.record.id],
                            approved=approved, escalated=escalated)
        routed.waiting.append(Waiting(item, reason))
    return routed
