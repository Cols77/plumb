"""The tidy job kind (SR-162): one model reading per change of the open cards against the
owner's confirmed records, so a card the owner already answered, or one that repeats another,
is withdrawn without waiting for them. SR-218: the judge's waiting questions are read the same
way, against the owner's logged answers too (report-ec092f5e: the job read only retired cards).

``build`` and ``recompute`` take the cards and the confirmed records from the logs; ``apply``
withdraws only after exact checks: the record is really confirmed and the quoted words are
really in it, or the other card is really still open. A withdrawal answers and confirms
nothing. Unsure is ``keep``.

SR-172: when several open cards hinge on one principle the job raises it once as one card and
groups them (``cardstore.group``); once a confirmed decision answers it, each grouped card is
settled from the decision's words: withdrawn, its link repinned, or a rewording proposed as an
unconfirmed edit. Each settlement is logged as ``card-settled`` with what ``undo`` needs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, Job
from plumb.present import owner_text
from plumb.understand import cardstore, files, read

kind = "tidy"
SCHEMA_ID = "tidy.v1"
HERE = Path(__file__).resolve().parent


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "tidy.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**data, "id": SCHEMA_ID}


schema: Mapping[str, Any] = _load_schema()


def _confirmed(core: Any) -> dict[str, str]:
    """``{id: text}`` of the records the owner confirmed and nothing replaced, and (SR-335)
    the decisions quoting the owner's own logged words, approved or not."""
    from plumb.understand import premise

    index, said = core.index(), premise.owner_words(core)
    return {i: read.record_text(index[i]) for i, s in core.status(list(index)).items()
            if s.superseded_by is None and i in index and (
                s.confirmation == "confirmed" or premise.owner_quoted(index[i], said))}


def _inputs(core: Any, session: str) -> dict[str, Any] | None:
    grouped = cardstore.grouped(core.root, session)
    cards = [{"id": c.id, "kind": c.kind, "topic": c.topic, "issue": c.issue,
              "questions": [q.text for q in c.questions], "grouped": c.id in grouped}
             for c in cardstore.load(core.root, session)]
    questions = _questions(core)
    # shortcut: every confirmed record is sent, so a very large record set makes a big prompt;
    # upgrade to the records `core.relevant` picks per card when that costs too much
    if not cards and not questions:
        return None
    return {"cards": cards, "questions": questions,
            "answers": _answers(core) if questions else [],
            "confirmed": [{"id": i, "text": t} for i, t in _confirmed(core).items()]}


ANSWERS_MAX = 300    # shortcut: the owner's latest answers only; widen if an older one is missed


def _questions(core: Any) -> list[dict[str, Any]]:
    """SR-218: the judge's open questions of every session: a question lives on after the cards."""
    from plumb.understand import judge

    return [{"id": str(q.get("key")), "question": str(q.get("question") or ""),
             "options": [str(o.get("label") or "") for o in q.get("options") or ()]}
            for q in judge.open_anywhere(core)]


def _answer_entries(core: Any) -> list[Any]:
    return [e for e in core.events() if e.kind == "question-answer"
            and e.payload.get("via") == "question-tool" and not e.payload.get("study")]


def _answers(core: Any) -> list[dict[str, str]]:
    """The owner's question-tool answers, each with the question it answered (SR-335)."""
    return [{"id": e.digest, "question": str(e.payload.get("question") or ""),
             "answer": str(e.payload.get("answer") or "")}
            for e in _answer_entries(core)[-ANSWERS_MAX:]]


def build(core: Any, session: str, **context: Any) -> Job | None:
    inputs = _inputs(core, session) if core is not None else None
    return None if inputs is None else files.make_job("tidy", session, SCHEMA_ID, inputs)


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    return _inputs(core, job.session) if core is not None else None


def describe(job: Job) -> str:
    return owner_text.STEP_TIDYING


def enqueue(core: Any, session: str) -> None:
    """Queue the job for the cards open now; it never waits for the model."""
    from plumb.understand import queue

    job = build(core, session)
    if job is not None:
        queue.enqueue(core, job)


def _close_questions(core: Any, session: str, verdicts: Any,
                     confirmed: Mapping[str, str]) -> None:
    """SR-218, SR-335: a waiting question the owner's logged answer or a confirmed record settles
    closes, only when the quoted words really are in it; logged as ``answer-bound``, which every
    session reads, and undone by ``plumb question reopen``. Never a model's word alone."""
    from plumb.understand import judge, worker

    waiting = {str(q.get("key")): q for q in judge.open_anywhere(core)}
    said = {e.digest: str(e.payload.get("answer") or "") for e in _answer_entries(core)}
    for verdict in verdicts:
        key, quote = str(verdict.get("question")), str(verdict.get("quote") or "")
        answer, record = str(verdict.get("answer") or ""), str(verdict.get("record") or "")
        source = said.get(answer) if answer else confirmed.get(record)
        asked = waiting.get(key)
        if asked is None or source is None or not read.evidence_in(quote, source):
            continue
        core.log_append_many("events", [("answer-bound", {
            "session": session, "by": "tidy", "quote": quote,
            **({"answer": answer} if answer else {"record": record}),
            "asked": {"job": asked.get("job"), "key": key, "keys": [key],
                      "records": list(asked.get("records") or ())}})])
        del waiting[key]
        worker.say(core.root, session, owner_text.TIDY_QUESTION_CLOSED.format(
            question=str(asked.get("question") or "").split("\n")[0][:120], quote=quote[:160]))


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    confirmed = _confirmed(core)
    for verdict in answer.get("verdicts") or ():
        open_cards = {c.id: c for c in cardstore.load(core.root, job.session)}
        card = open_cards.get(str(verdict.get("card")))
        if card is None:
            continue
        if verdict.get("verdict") == "withdraw_answered":
            record, quote = str(verdict.get("record")), str(verdict.get("quote"))
            if record in confirmed and read.evidence_in(quote, confirmed[record]):
                cardstore.withdraw_card(core, job.session, card, owner_text.TIDY_ANSWERED.format(
                    record=record, quote=quote))
        elif verdict.get("verdict") == "withdraw_duplicate":
            other = open_cards.get(str(verdict.get("other")))
            if other is not None and other.id != card.id:
                cardstore.withdraw_card(core, job.session, card, owner_text.TIDY_DUPLICATE.format(
                    other=other.topic))
    _close_questions(core, job.session, answer.get("questions") or (), confirmed)
    _principles(core, job.session, answer.get("principles") or ())
    _settle(core, job.session, answer.get("settlements") or (), confirmed)
    return Applied(job=job.id)


def _principles(core: Any, session: str, found: Any) -> None:
    """SR-172 EX-1: one card for a principle several open cards hinge on; those cards are
    grouped under it, so the turn end does not draw them."""
    from plumb.contracts import CardState, Choice, ClarifyQuestion

    for item in found:
        open_cards = {c.id: c for c in cardstore.load(core.root, session)
                      if c.id not in cardstore.grouped(core.root, session)}
        ids = [i for i in dict.fromkeys(map(str, item.get("cards") or ())) if i in open_cards]
        options = [str(o) for o in item.get("options") or ()]
        question = " ".join(str(item.get("question") or "").split())
        if len(ids) < 2 or not 2 <= len(options) <= 4 or not question:
            continue
        cid = "principle:" + hashlib.sha256(question.encode("utf-8")).hexdigest()[:10]
        if any(c.id == cid for c in cardstore.own_cards(core.root, session)):
            continue
        choices = tuple(Choice(o, "change", o, owner_text.PRINCIPLE_CONSEQUENCE.format(n=len(ids)))
                        for o in options)
        card = CardState(
            id=cid, kind="principle", topic=question, resolutions=tuple(options),
            issue=owner_text.PRINCIPLE_ISSUE.format(
                n=len(ids), topics="; ".join(open_cards[i].topic for i in ids)),
            questions=(ClarifyQuestion(id=f"{cid}#1", text=question, resolutions=tuple(options),
                                       choices=choices),),
            turn=max(c.turn for c in open_cards.values()))
        cardstore.save(core.root, session, [*cardstore.own_cards(core.root, session), card])
        cardstore.group(core.root, session, cid, ids)


def _settle(core: Any, session: str, settlements: Any, confirmed: Mapping[str, str]) -> None:
    """SR-172 EX-2, EX-3: settle each grouped card from a confirmed decision's exact words;
    one the model cannot settle stays, and is told once."""
    from plumb import links

    last: dict[str, str] = {}
    for e in core.log_read("events", ["card-settled", "card-unsettled"]):
        last[str(e.payload.get("card"))] = e.kind
    for item in settlements:
        grouped = cardstore.grouped(core.root, session)
        if last.get(str(item.get("card"))) == "card-unsettled":
            continue        # the owner took this settlement back: it stays open
        card = next((c for c in cardstore.load(core.root, session)
                     if c.id == str(item.get("card")) and c.id in grouped), None)
        if card is None:
            continue
        decision, quote = str(item.get("decision")), str(item.get("quote"))
        action = str(item.get("action"))
        if decision not in confirmed or not read.evidence_in(quote, confirmed[decision]):
            action = "stays"      # an agent-only proposal, or words not in it, settle nothing
        why = owner_text.TIDY_SETTLED.format(record=decision, quote=quote)
        link_id = card.id.removeprefix("stale:") if card.kind == "stale_link" else ""
        index = core.index()
        record = index.get(link_id.partition("#")[0])
        link = next((x for x in (record.links if record else ()) if x.id == link_id), None)
        event: dict[str, Any] = {"card": card.id, "session": session, "topic": card.topic,
                                 "action": action, "decision": decision, "reason": why}
        if action == "withdraw":
            cardstore.withdraw_card(core, session, card, why)
        elif action in ("repin", "reword") and link is not None:
            pin = None if link.pin is None else {"from": link.pin.source, "to": link.pin.target}
            if action == "reword":
                event["before"] = str(record.fields.get("statement") or "")
                changes = links.reword_and_repin(core, record, link, str(item.get("wording")),
                                                 why)
            else:
                changes = links.repin(core, link_id, note=why)
            if changes is None:
                action = event["action"] = "stays"
            else:
                for change in changes:
                    if action == "reword" and change["link"] == link_id:
                        change["old"] = pin     # the pin before the reword, for undo
                event["changes"] = changes
        else:
            action = event["action"] = "stays"
        if action == "stays" and any(
                e.payload.get("card") == card.id for e in core.log_read("events", ["card-settled"])):
            continue
        core.log_append("events", "card-settled", event)


def undo(core: Any, session: str, card_id: str) -> bool:
    """SR-172 EX-4: take back the latest settlement of ``card_id``: the card is open again,
    a reworded statement is put back and a repinned link is stale again. False when there is
    none (``plumb undo`` covers confirmed records only, so this is its own entry point)."""
    from plumb import links

    mine = [e for e in core.log_read("events", ["card-settled", "card-unsettled"])
            if e.payload.get("card") == card_id]
    if not mine or mine[-1].kind != "card-settled" or mine[-1].payload.get("action") == "stays":
        return False
    event = mine[-1].payload
    changes = event.get("changes") or []
    if "before" in event and changes:
        link = changes[0]["link"]
        record = core.index()[link.partition("#")[0]]
        from plumb.capture.records import rewrite

        rewrite(core, record, {"statement": event["before"]})
    links.restore_pins(core, changes)
    cardstore.reopen(core.root, session, card_id)
    cardstore.ungroup(core.root, session, card_id)
    core.log_append("events", "card-unsettled", {"card": card_id, "session": session})
    return True


def run(command: str, argv: list[str]) -> int:
    """``plumb understand undo <card id>``: take back a card plumb settled from a decision
    (SR-172 EX-4); the one entry, as ``plumb undo`` covers confirmed records only."""
    import argparse

    from plumb.api import open_core
    from plumb.cliutil import add_common, resolve_root
    from plumb.stale import current_session

    parser = argparse.ArgumentParser(prog="plumb understand undo")
    add_common(parser)
    parser.add_argument("card")
    parser.add_argument("--session", default="")
    args = parser.parse_args(argv)
    root = resolve_root(args.root)
    core = open_core(root)
    if args.card.startswith(("SR-", "DEC-")):    # SR-191: a record a model confirmed
        from plumb.understand.typed import take_back

        result = take_back(core, args.card)
        print(*result.lines, sep="\n")
        return 0 if result.confirmed else 1
    done = undo(core, args.session or current_session(root), args.card)
    print(f"plumb: {args.card} is open again." if done
          else f"plumb: {args.card} was not settled from a decision; nothing changed.")
    return 0 if done else 1
