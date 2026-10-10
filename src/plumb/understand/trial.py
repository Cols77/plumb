"""The trial (JUDGE, SR-106, spec 7).

While no calibration passes for a kind, every ``supported`` record goes to a trial batch card
of up to five instead of being settled: four the judge would settle and one drawn from below the
threshold, asked as "plumb would not settle this; right?" (the threshold is learned on what the
owner answers, so a range cut off at the threshold would teach nothing). A record settling never
reaches (a decision, a set member, an edit of a confirmed record, an option picked among
several) is asked on its own. The owner's yes confirms the record, labelled yes, and a no
rejects it as a misreading: READ applies both when it applies the answer; ``effect`` logs the
batch. Recalibration reads the logged scores (``capture.calibrate``) and calls no model."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from plumb.contracts import Applied, CardState, ClarifyQuestion
from plumb.present import owner_text
from plumb.understand import cards, settle

BATCH = 5
ABOVE = 4
TITLES_IN_TOPIC = 3
WORDS_PER_ITEM = 140


@dataclass(frozen=True)
class Candidate:
    """A supported record waiting for the owner."""

    record: Any
    score: float
    premise: Mapping[str, Any]
    reason: str = ""


# --------------------------------------------------------------------------- thresholds


def claim_kind(record_kind: str) -> str | None:
    from plumb.capture.calibrate import KINDS

    return KINDS.get(record_kind)


def threshold(core: Any, record_kind: str) -> float:
    """The score at which the judge would settle a ``record_kind`` record: the latest judge
    calibration's threshold for the kind when it passes, else the starting value."""
    from plumb.capture.calibrate import judge_calibrations

    start = float(core.config.understand.reader_threshold_start)
    kind = claim_kind(record_kind)
    for calibration in reversed(judge_calibrations(core)):
        per_kind = calibration.payload.get("per_kind")
        result = per_kind.get(kind) if isinstance(per_kind, Mapping) and kind else None
        if isinstance(result, Mapping):
            if result.get("passing") and result.get("threshold") is not None:
                return float(result["threshold"])
            return start
    return start


# --------------------------------------------------------------------------- the pool


def _open_records(core: Any, session: str) -> set[str]:
    from plumb.understand import cardstore

    return {str(q.record) for card in cardstore.own_cards(core.root, session)
            if card.status == "open" and card.kind in ("trial", "backlog")
            for q in card.questions if q.record}


def _rejected(core: Any) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for entry in core.events():
        if entry.kind == "rejection":
            for item in entry.payload.get("records") or ():
                if isinstance(item, Mapping):
                    out.add((str(item.get("id")), str(item.get("hash"))))
    return out


def from_log(core: Any, skip: set[str]) -> list[Candidate]:
    """The supported records of the logged verdicts that still wait: judged at their current
    version, neither confirmed nor rejected, not in ``skip``."""
    from plumb.capture.spec import escalated_ids
    from plumb.capture.triage import approved_before
    from plumb.understand import premise

    latest: dict[str, Mapping[str, Any]] = {}
    for entry in core.events():
        if entry.kind == "verdict":
            latest[str(entry.payload.get("id"))] = entry.payload
    index = core.index()
    wanted = [i for i, v in latest.items() if v.get("verdict") == "supported" and i in index
              and index[i].hash == v.get("hash") and i not in skip]
    if not wanted:
        return []
    statuses = core.status(wanted)
    rejected = _rejected(core)
    approved, escalated = approved_before(core), escalated_ids(core)
    known = premise.committed(core)
    out: list[Candidate] = []
    for record_id in wanted:
        record = index[record_id]
        if statuses[record_id].confirmation == "confirmed" \
                or (record_id, record.hash) in rejected:
            continue
        reason = settle.ineligible(core, record, status=statuses[record_id], approved=approved,
                                   escalated=escalated)
        given = premise.premise_of(core, record, known=known).as_input()
        out.append(Candidate(record, float(latest[record_id].get("score") or 0), given, reason))
    return out


# --------------------------------------------------------------------------- batches


def batches(items: Sequence[Candidate], limit: float) -> list[list[Candidate]]:
    """Batches of up to five: four the judge would settle (score at or above ``limit``, the
    surest first) and one drawn from below it (the closest to it), else five above."""
    above = sorted((i for i in items if i.score >= limit),
                   key=lambda i: (-i.score, i.record.id))
    below = sorted((i for i in items if i.score < limit),
                   key=lambda i: (-i.score, i.record.id))
    out: list[list[Candidate]] = []
    while above or below:
        if below:
            batch = [*above[:ABOVE], below.pop(0)]
            above = above[ABOVE:]
        else:
            batch, above = above[:BATCH], above[BATCH:]
        out.append(batch)
    return out


def _words(premise: Mapping[str, Any]) -> str:
    return cards.clip(cards.words_of(premise), WORDS_PER_ITEM)


def _topic(items: Sequence[Candidate]) -> str:
    titles = [i.record.title for i in items]
    shown = ", ".join(titles[:TITLES_IN_TOPIC])
    if len(titles) <= TITLES_IN_TOPIC:
        return shown
    return f"{shown} and {len(titles) - TITLES_IN_TOPIC} more"


def batch_card(items: Sequence[Candidate], limit: float) -> CardState:
    """One trial batch card; the item below ``limit`` (if any) is asked as such."""
    key = "\n".join(sorted(f"{i.record.id}@{i.record.hash}" for i in items))
    cid = "trial:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    options = (owner_text.TRIAL_YES, owner_text.TRIAL_NO)
    questions: list[ClarifyQuestion] = []
    evidence: list[str] = []
    for n, item in enumerate(items, start=1):
        text = (f"{owner_text.TRIAL_BELOW} {item.record.title}" if item.score < limit
                else item.record.title)
        questions.append(ClarifyQuestion(id=f"{cid}#{n}", text=text, resolutions=options,
                                         record=item.record.id))
        evidence.append(f"{item.record.title}: {_words(item.premise)}")
    below = any(i.score < limit for i in items)
    if len(items) == 1:
        issue = owner_text.TRIAL_BELOW if below else owner_text.TRIAL_ISSUE_ONE
    else:
        issue = owner_text.TRIAL_ISSUE.format(what="these")
        if below:
            issue += " " + owner_text.TRIAL_ONE_BELOW
    return CardState(id=cid, kind="trial", topic=_topic(items), issue=issue,
                     evidence=" | ".join(evidence), resolutions=options,
                     questions=tuple(questions))


def individual_card(item: Candidate) -> CardState:
    """A record that never settles, asked on its own."""
    issue = {settle.EDIT: owner_text.EDIT_ISSUE, settle.OPTION: owner_text.OPTION_ISSUE
             }.get(item.reason, owner_text.CONFIRM_ISSUE)
    cid = cards.card_id("trial", item.record.id, item.record.hash)
    options = (owner_text.TRIAL_YES, owner_text.TRIAL_NO)
    return CardState(
        id=cid, kind="trial", topic=item.record.title, issue=issue,
        evidence=cards.words_of(item.premise), resolutions=options,
        questions=(ClarifyQuestion(id=f"{cid}#1", text=item.record.title,
                                   resolutions=options, record=item.record.id),))


def cards_for(core: Any, session: str, waiting: Sequence[settle.Waiting]) -> list[CardState]:
    """The trial and confirm cards for ``waiting`` (this job's supported records that did not
    settle) and every supported record the log still holds back."""
    held = _open_records(core, session)
    now = [Candidate(w.item.record, w.item.score, w.item.premise, w.reason) for w in waiting
           if w.item.record.id not in held]
    seen = {c.record.id for c in now}
    pool = [*now, *from_log(core, held | seen)]
    out = [individual_card(c) for c in pool if c.reason]
    for kind in ("intent", "requirement"):
        group = [c for c in pool if not c.reason and c.record.kind == kind]
        if group:
            limit = threshold(core, kind)
            out.extend(batch_card(batch, limit) for batch in batches(group, limit))
    return out


def top_up(core: Any, session: str) -> list[CardState]:
    """New trial cards for the records still waiting, when no trial card is open (called
    when the turn ends, after a batch was answered)."""
    from plumb.understand import cardstore

    if any(c.kind == "trial" and c.status == "open"
           for c in cardstore.own_cards(core.root, session)):
        return []
    return cards_for(core, session, [])


# --------------------------------------------------------------------------- the answer


def effect(*, core: Any = None, card: CardState | None = None, **_: Any) -> Applied | None:
    """A trial card was answered (READ confirmed the yes items, labelled yes, and rejected
    the no items). When every item has its answer, log the batch."""
    if card is None or core is None:
        return None
    answered = {a.question: a.answer for a in card.answers}
    if not card.questions or any(q.id not in answered for q in card.questions):
        return None
    index = core.index()
    items = [{"id": q.record, "hash": index[q.record].hash if q.record in index else ""}
             for q in card.questions]
    answers = [{"question": q.id, "answer": answered[q.id]} for q in card.questions]
    return Applied(entries=({"kind": "trial", "payload": {
        "card": card.id, "items": items, "answers": answers}},))
