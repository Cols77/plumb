"""Settling (JUDGE, SR-106, spec 7): the judge's supported records that need no owner.

A ``supported`` record is **settled** (``by: settled`` approval: job id, model, score, premise
digest, the calibration that allowed it) only when all of these hold: settling is on for its
kind, nothing has suspended it (a new model or prompt waits for the evaluation set and a new
calibration), the record is not one that is always asked on its own (a decision, a member of an
escalated set, an edit of a record the owner confirmed, an option picked among several), and its
score reaches the calibrated threshold for the kind. Every other supported record waits as a
trial or confirm card (``trial``).

The switch is a ``settle-config`` entry per kind. For requirements and their examples it switches
itself on when calibration passes (``via: calibration``, naming the calibration); for intents the
owner is told once and turns it on with the typed ``/plumb settle on intent`` or a button; the
owner switches any kind off the same way, and plumb never switches on again a kind the owner
switched off. Prose changes nothing: an entry of the owner's counts only when it was written
from the owner's own terminal (no agent marker) or carries the owner's typed command."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from plumb.contracts import CardState, Job, LogEntry, SettleState
from plumb.present import owner_text

# why a supported record is asked on its own and never settled
DECISION, SET_MEMBER, EDIT, OPTION = "decision", "set", "edit", "option"
KINDS = ("intent", "requirement")
SELF_SWITCHING = ("requirement",)       # the kinds the agent derives: they switch themselves on
OWNER_VIA = ("typed", "button")

TYPED = re.compile(r"^/plumb\s+settle\s+(on|off)(?:\s+(intent|requirement))?\s*$",
                   re.IGNORECASE)


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


# --------------------------------------------------------------------------- eligibility


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

    if record.kind not in KINDS:
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


# --------------------------------------------------------------------------- the switch


def _prompt_proof(entry: LogEntry, pattern: re.Pattern[str]) -> re.Match[str] | None:
    """The match of the owner's typed command an entry carries as its proof: the quote is the
    command and the prompt digest is the digest of that very text."""
    from plumb.approvals import prompt_digest
    from plumb.normalize import sha256_text

    quote, digest = entry.payload.get("quote"), entry.payload.get("prompt_digest")
    if not isinstance(quote, str) or not isinstance(digest, str):
        return None
    if digest not in (prompt_digest(quote), sha256_text(quote)):
        return None
    return pattern.match(quote.strip())


def owner_written(entry: LogEntry) -> bool:
    """Whether a ``settle-config`` entry of the owner is the owner's: written outside the agent
    session (their own terminal, or a button) or proved by their typed command, which must say
    the same thing (on or off, for that kind or for every kind)."""
    if entry.marker == "none":
        return True
    found = _prompt_proof(entry, TYPED)
    if found is None:
        return False
    kind = entry.payload.get("kind")
    same_word = (found.group(1).lower() == "on") == bool(entry.payload.get("on"))
    return same_word and (found.group(2) or kind).lower() == kind


def _is_offer(entry: LogEntry) -> bool:
    return entry.payload.get("via") == "calibration" and not entry.payload.get("on")


def valid_config(entry: LogEntry, before: Sequence[LogEntry] = ()) -> bool:
    """Whether a ``settle-config`` entry counts. Owner entries (``typed``, ``button``) must be
    the owner's; a ``calibration`` entry may switch on only a self-switching kind and must name
    a passing logged calibration that came before it; the entry that records an offer to the
    owner switches nothing."""
    payload = entry.payload
    kind, via = payload.get("kind"), payload.get("via")
    if kind not in KINDS:
        return False
    if via in OWNER_VIA:
        return owner_written(entry)
    if via == "calibration":
        if _is_offer(entry):
            return True
        if kind not in SELF_SWITCHING:
            return False
        digest = payload.get("calibration")
        found = next((e for e in before if e.kind == "calibration" and e.digest == digest), None)
        return found is not None and passing(found, claim_kind(kind))
    return False


def claim_kind(kind: str) -> str:
    from plumb.capture.calibrate import KINDS as CLAIMS

    return CLAIMS[kind]


def passing(calibration: LogEntry | None, claim: str) -> bool:
    per_kind = calibration.payload.get("per_kind") if calibration is not None else None
    result = per_kind.get(claim) if isinstance(per_kind, Mapping) else None
    return isinstance(result, Mapping) and bool(result.get("passing"))


def configs(entries: Sequence[LogEntry], kind: str) -> list[LogEntry]:
    """The valid ``settle-config`` entries of ``kind`` in log order."""
    out: list[LogEntry] = []
    for position, entry in enumerate(entries):
        if entry.kind == "settle-config" and entry.payload.get("kind") == kind \
                and valid_config(entry, entries[:position]):
            out.append(entry)
    return out


def state_in(entries: Sequence[LogEntry], kind: str) -> SettleState:
    """The switch of ``kind`` as ``entries`` leave it. A kind the owner switched off stays off
    whatever a calibration entry says after it."""
    valid = configs(entries, kind)
    owner = [e for e in valid if e.payload.get("via") in OWNER_VIA]
    standing = [e for e in valid if not _is_offer(e)]
    if owner and not owner[-1].payload.get("on"):
        last = owner[-1]
    elif standing:
        last = standing[-1]
    else:
        return SettleState(kind=kind)
    return SettleState(kind=kind, on=bool(last.payload.get("on")),
                       via=last.payload.get("via") or "",
                       calibration=str(last.payload.get("calibration") or ""))


def state(core: Any, kind: str) -> SettleState:
    """The switch of ``kind``: off by default; ``via`` says who last set it."""
    return state_in(core.events(), kind)


def owner_latest(core: Any, kind: str) -> bool | None:
    """The owner's latest word on ``kind`` (True on, False off), None if they never said."""
    owner = [e for e in configs(core.events(), kind) if e.payload.get("via") in OWNER_VIA]
    return bool(owner[-1].payload.get("on")) if owner else None


def owner_off(core: Any, kind: str) -> bool:
    """Whether the owner's latest word on ``kind`` is off (plumb never switches it on)."""
    return owner_latest(core, kind) is False


def offered(core: Any, kind: str) -> bool:
    """Whether the owner was already told that settling ``kind`` can be turned on."""
    return any(_is_offer(e) for e in configs(core.events(), kind))


# --------------------------------------------------------------------------- suspension


def judge_calibration(entries: Sequence[LogEntry], kind: str) -> LogEntry | None:
    """The latest calibration from the judge's logged scores that measured ``kind``."""
    claim = claim_kind(kind)
    for entry in reversed(entries):
        if entry.kind == "calibration" and entry.payload.get("source") == "logged" \
                and isinstance(entry.payload.get("per_kind"), Mapping) \
                and claim in entry.payload["per_kind"]:
            return entry
    return None


def same_fingerprint(entry: LogEntry | None, now: Mapping[str, Any]) -> bool:
    """Whether a calibration was made under the model and prompt in force. A calibration that
    names neither is taken as current."""
    if entry is None:
        return False
    model, digest = entry.payload.get("model"), entry.payload.get("prompt_digest")
    return (model in (None, now.get("model"))) and (digest in (None, "", now.get("prompt_digest")))


def suspension(core: Any, kind: str) -> str:
    """Why settling ``kind`` is suspended, or ''. A new model or prompt suspends it until the
    evaluation set passes again and calibration is rerun; a calibration that no longer passes
    leaves every supported record to the trial."""
    from plumb.capture.calibrate import fingerprint

    entries = core.events()
    calibration = judge_calibration(entries, kind)
    if calibration is None or not passing(calibration, claim_kind(kind)):
        return "no passing calibration"
    if not same_fingerprint(calibration, fingerprint(core)):
        return "the model or the prompt changed"
    return ""


def active(core: Any, kind: str) -> bool:
    """Whether supported ``kind`` records settle now."""
    return state(core, kind).on and not suspension(core, kind)


# --------------------------------------------------------------------------- routing


def route(core: Any, job: Job, supported: list[Supported], *, model: str = "") -> Routed:
    """Settle the supported records that may settle; the rest wait for the owner."""
    from plumb.approvals import approval_items
    from plumb.capture.spec import escalated_ids
    from plumb.capture.triage import approved_before
    from plumb.understand import premise, trial

    routed = Routed()
    if not supported:
        return routed
    statuses = core.status([s.record.id for s in supported])
    approved, escalated = approved_before(core), escalated_ids(core)
    live = {kind: active(core, kind) for kind in KINDS}
    entries = core.events()
    for item in supported:
        record = item.record
        status = statuses[record.id]
        if status.confirmation == "confirmed":
            continue                                  # the owner (or an earlier settling) has it
        reason = ineligible(core, record, status=status, approved=approved,
                            escalated=escalated)
        if reason or not live.get(record.kind) or item.score < trial.threshold(core, record.kind):
            routed.waiting.append(Waiting(item, reason))
            continue
        calibration = judge_calibration(entries, record.kind)
        digests = sorted(str(m.get("digest")) for m in item.premise.get("messages") or ()
                         if m.get("digest"))
        routed.entries.append({"kind": "approval", "payload": {
            "records": approval_items(core, [record.id]), "by": "settled",
            "session": job.session, "job": job.id, "model": model, "score": item.score,
            "premise_digest": premise.input_digest(item.premise), "premise_digests": digests,
            "calibration": calibration.digest if calibration is not None else ""}})
    return routed


# --------------------------------------------------------------------------- upkeep


def revalidate(core: Any) -> list[str]:
    """Withdraw every settling whose premise or footing no longer stands (the premise message
    or its parent changed, the judgment is gone, the record became one that never settles). The
    record returns to proposed: a revocation by ``settled`` is written for it, once. Returns
    the records withdrawn."""
    from plumb.understand import premise, recheck_settled

    entries = core.events()
    done = {(str(r.get("id")), str(r.get("hash")))
            for e in entries if e.kind == "revocation" and e.payload.get("by") in (
                "settled", "undone")
            for r in e.payload.get("records") or () if isinstance(r, Mapping)}
    known = premise.committed(core)
    out: list[str] = []
    for entry in entries:
        if entry.kind != "approval" or entry.payload.get("by") != "settled":
            continue
        reason = recheck_settled.problem(entry, core, known=known)
        if reason is None:
            continue
        pins = [r for r in entry.payload.get("records") or ()
                if isinstance(r, Mapping) and (str(r.get("id")), str(r.get("hash"))) not in done]
        if not pins:
            continue
        core.log_append("events", "revocation", {
            "records": [{"id": r["id"], "hash": r["hash"]} for r in pins], "by": "settled",
            "reason": reason})
        out.extend(str(r["id"]) for r in pins)
    return out


@dataclass
class Refreshed:
    """What a refresh found for the owner: notices ``(key, text)`` to say once, and cards."""

    notices: list[tuple[str, str]] = field(default_factory=list)
    cards: list[CardState] = field(default_factory=list)
    withdrawn: list[str] = field(default_factory=list)
    calibrated: bool = False


def _labels_since_calibration(entries: Sequence[LogEntry]) -> bool:
    """Whether an owner label (a trial batch answered, an owner-words confirmation, a yes, a
    rejection, an undo) came after the latest calibration from logged scores."""
    last = -1
    for position, entry in enumerate(entries):
        if entry.kind == "calibration" and entry.payload.get("source") == "logged":
            last = position
    for entry in entries[last + 1:]:
        if entry.kind in ("trial", "rejection"):
            return True
        if entry.kind == "approval" and entry.payload.get("by") == "owner-words":
            return True
        if entry.kind == "revocation" and entry.payload.get("by") == "undone":
            return True
    return False


def _eval_passed(entries: Sequence[LogEntry], now: Mapping[str, Any]) -> bool:
    for entry in reversed(entries):
        if entry.kind == "eval-run" and not entry.payload.get("compare") \
                and entry.payload.get("model") == now.get("model") \
                and entry.payload.get("prompt_digest") == now.get("prompt_digest"):
            cases = entry.payload.get("cases") or ()
            return bool(cases) and int(entry.payload.get("passed") or 0) >= len(cases)
    return False


def refresh(core: Any, session: str, *, recalibrate: bool = True) -> Refreshed:
    """The upkeep of the turn's end, from the logs alone (no model): withdraw settlings that no
    longer stand, rerun the calibration from the logged scores after an owner label (or after a
    model or prompt change once the evaluation set passed), switch settling on by itself for
    the kinds the agent derives, offer the owner the switch for intents once, and top up the
    trial cards. ``recalibrate=False`` leaves the calibration for a hook with more time."""
    from plumb.capture import calibrate
    from plumb.understand import trial

    out = Refreshed(withdrawn=revalidate(core))
    entries = core.events()
    now = calibrate.fingerprint(core)
    changed = any(judge_calibration(entries, k) is not None
                  and not same_fingerprint(judge_calibration(entries, k), now) for k in KINDS)
    judged = any(e.kind == "verdict" for e in entries)          # a score to calibrate on
    if recalibrate and judged and (_labels_since_calibration(entries)
                                   or (changed and _eval_passed(entries, now))):
        try:
            calibrate.calibrate(core)
            out.calibrated = True
        except Exception:  # noqa: BLE001 - upkeep never fails the turn
            pass
        entries = core.events()
    for kind in KINDS:
        calibration = judge_calibration(entries, kind)
        if calibration is None or not passing(calibration, claim_kind(kind)) \
                or not same_fingerprint(calibration, now) or owner_off(core, kind):
            continue
        current = state(core, kind)
        if kind in SELF_SWITCHING:
            prior = next((e for e in entries if e.digest == current.calibration), None)
            if not current.on or (prior is not None and not same_fingerprint(prior, now)):
                core.log_append("events", "settle-config", {
                    "kind": kind, "on": True, "via": "calibration",
                    "calibration": calibration.digest})
                out.notices.append((f"settle-on:{kind}:{calibration.digest}",
                                    owner_text.SETTLE_ON_REQUIREMENTS))
        elif not current.on and not offered(core, kind):
            core.log_append("events", "settle-config", {
                "kind": kind, "on": False, "via": "calibration",
                "calibration": calibration.digest, "offered": True})
            out.cards.append(offer_card(kind))
    out.cards.extend(trial.top_up(core, session))
    return out


def offer_card(kind: str) -> CardState:
    """The card that tells the owner settling ``kind`` can be turned on (owner-only: neither
    a prose answer nor an agent turns it on)."""
    return CardState(
        id=f"settle_offer:{kind}", kind="settle_offer",
        topic=f"settling your {kind} read-backs", issue=owner_text.SETTLE_OFFER_INTENT,
        evidence="", resolutions=(owner_text.SETTLE_TURN_ON.format(kind=kind),
                                  owner_text.SETTLE_LEAVE_OFF), owner_only=True)
