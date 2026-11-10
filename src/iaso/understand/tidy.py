"""The tidy job kind (SR-216, SR-217, SR-218): one model reading per change of the judge's
waiting questions against the owner's confirmed records, logged answers and later requests, so a
question that no longer needs the owner is closed without waiting for them.

``build`` and ``recompute`` take the questions, the answers, the requests and the confirmed
records from the logs; ``apply`` closes a question only after exact checks: the quoted words are
really in the owner's answer, in the confirmed record or in a request newer than the question,
or the other question is really still waiting. A closing by an answer or a record is logged as
``answer-bound``, the others as ``question-withdrawn`` with their reason; none approves
anything, and ``iaso question reopen`` undoes each. SR-217: a recorded decision may also settle
a stale-link question by refreshing the link or rewording the requirement, logged with what
reopen needs to put back. Unsure leaves the question open."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from iaso.contracts import Applied, Job
from iaso.present import owner_text
from iaso.understand import files, read

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
    from iaso.understand import judge, premise

    index, said = core.index(), premise.owner_words(core)
    return {i: judge.record_text(index[i]) for i, s in core.status(list(index)).items()
            if s.superseded_by is None and i in index and (
                s.confirmation == "confirmed" or premise.owner_quoted(index[i], said))}


def _inputs(core: Any, session: str) -> dict[str, Any] | None:
    questions = _questions(core)
    # shortcut: every confirmed record is sent, so a very large record set makes a big prompt;
    # upgrade to the records `core.relevant` picks per question when that costs too much
    if not questions:
        return None
    return {"questions": questions, "answers": _answers(core), "requests": _requests(core),
            "confirmed": [{"id": i, "text": t} for i, t in _confirmed(core).items()]}


QUESTION_CLOSED = ("iaso: closed a waiting question the owner already answered: \"{question}\" "
                   "(their words: \"{quote}\"); iaso question reopen <its words> undoes it")
QUESTION_DUPLICATE = ("iaso: withdrew a waiting question that repeats another: \"{question}\" "
                      "(the other: \"{other_question}\"); iaso question reopen <its words> "
                      "undoes it")
QUESTION_REPLACED = ("iaso: withdrew a waiting question your newer request replaces: "
                     "\"{question}\" (your words: \"{quote}\"); iaso question reopen <its words> "
                     "undoes it")
QUESTION_SETTLED = "settled from {record}: \"{quote}\""
QUESTION_SETTLED_SAY = ("iaso: settled a waiting question from a decision of yours "
                        "({action}): \"{question}\" ({decision}: \"{quote}\"); iaso question "
                        "reopen <its words> undoes it")
UNREACHABLE = ("iaso: no judge could be reached to tidy the waiting questions; they stay "
               "as they are and reach you with no recommendation")
ANSWERS_MAX = 300    # shortcut: the owner's latest answers only; widen if an older one is missed


def _questions(core: Any) -> list[dict[str, Any]]:
    """SR-218: the judge's open questions of every session."""
    from iaso.understand import judge

    return [{"id": str(q.get("key")), "question": str(q.get("question") or ""),
             "link": (str(q["job"]).partition(":")[2]
                      if str(q.get("job")).startswith("stale:") else ""),
             "asked_at": str(q.get("at") or ""),
             "options": [str(o.get("label") or "") for o in q.get("options") or ()]}
            for q in judge.open_anywhere(core)]


REQUESTS_MAX = 20    # shortcut: the owner's latest requests only


def _requests(core: Any) -> list[dict[str, str]]:
    """SR-216 EX-5: the owner's typed requests, newest last, each with when it was made."""
    return [{"id": str(p.get("at") or ""), "text": str(p.get("text") or "")[:1200]}
            for p in read._prompt_entries(core)[-REQUESTS_MAX:]]


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
    """Queue the job for the questions open now; it never waits for the model."""
    from iaso.understand import queue

    job = build(core, session)
    if job is not None:
        queue.enqueue(core, job)


def _withdraw(core: Any, session: str, asked: Mapping[str, Any], reason: str, say: str,
              **detail: Any) -> None:
    from iaso.understand import judge, worker

    judge.withdraw(core, session, str(asked.get("key")), reason, by="tidy", **detail)
    worker.say(core.root, session, say.format(
        question=str(asked.get("question") or "").split("\n")[0][:120], **detail))


def _close_questions(core: Any, session: str, verdicts: Any,
                     confirmed: Mapping[str, str]) -> None:
    """SR-216, SR-218, SR-335: a waiting question closes when the owner's logged answer or a
    confirmed record settles it, a request newer than it replaces it (``replaced``), or it repeats
    another waiting question (``duplicate``), only when the quoted words are really there and the
    other question really waits. Never a model's word alone; unsure verdicts name nothing."""
    from iaso.understand import judge, worker

    waiting = {str(q.get("key")): q for q in judge.open_anywhere(core)}
    said = {e.digest: str(e.payload.get("answer") or "") for e in _answer_entries(core)}
    requests = [(str(p.get("at") or ""), str(p.get("text") or ""))
                for p in read._prompt_entries(core)]
    for verdict in verdicts:
        key, quote = str(verdict.get("question")), str(verdict.get("quote") or "")
        answer, record = str(verdict.get("answer") or ""), str(verdict.get("record") or "")
        other = str(verdict.get("other") or "")
        asked = waiting.get(key)
        if asked is None:
            continue
        if other:
            if other == key or other not in waiting:
                continue
            _withdraw(core, session, asked, "duplicate", QUESTION_DUPLICATE, other=other,
                      other_question=str(waiting[other].get("question") or "").split("\n")[0][:120])
        elif verdict.get("replaced"):
            since = str(asked.get("at") or "")
            if not since or not quote or not any(at > since and read.evidence_in(quote, text)
                                    for at, text in requests):
                continue        # no later request holds those words: it is still asked
            _withdraw(core, session, asked, "replaced", QUESTION_REPLACED, quote=quote)
        else:
            source = said.get(answer) if answer else confirmed.get(record)
            if source is None or not quote or not read.evidence_in(quote, source):
                continue
            core.log_append_many("events", [("answer-bound", {
                "session": session, "by": "tidy", "quote": quote,
                **({"answer": answer} if answer else {"record": record}),
                "asked": {"job": asked.get("job"), "key": key, "keys": [key],
                          "records": list(asked.get("records") or ())}})])
            worker.say(core.root, session, QUESTION_CLOSED.format(
                question=str(asked.get("question") or "").split("\n")[0][:120], quote=quote[:160]))
        del waiting[key]


def _settle(core: Any, session: str, settlements: Any, confirmed: Mapping[str, str]) -> None:
    """SR-217, DEC-434: a recorded decision (confirmed, or the owner's own quoted words) settles a
    waiting stale-link question by refreshing its link (``repin``) or rewording its requirement
    (``reword``, an unconfirmed edit the judge then validates like any capture). The decision's
    words must really hold the quote; a proposed record the agent alone wrote settles nothing.
    Logged as ``question-withdrawn`` (reason ``settled``) with what ``iaso question reopen``
    puts back."""
    from iaso import links
    from iaso.understand import judge, worker

    waiting = {str(q.get("key")): q for q in judge.open_anywhere(core)}
    for item in settlements:
        key, decision = str(item.get("question")), str(item.get("decision"))
        quote, action = str(item.get("quote") or ""), str(item.get("action"))
        asked = waiting.get(key)
        if asked is None or action not in ("repin", "reword") or decision not in confirmed \
                or not read.evidence_in(quote, confirmed[decision]):
            continue
        if not str(asked.get("job") or "").startswith("stale:"):
            if action == "reword" and _reword_contradicting(
                    core, session, asked, item, decision, quote, confirmed):
                waiting.pop(key, None)
            continue
        link_id = str(asked["job"])[6:]
        record = core.index().get(link_id.partition("#")[0])
        link = next((x for x in (record.links if record else ()) if x.id == link_id), None)
        if link is None:
            continue
        why = QUESTION_SETTLED.format(record=decision, quote=quote)
        before = str(record.fields.get("statement") or "")
        if action == "reword":
            changes = links.reword_and_repin(core, record, link,
                                             str(item.get("wording") or ""), why)
        else:
            changes = links.repin(core, link_id, note=why)
        if changes is None:
            continue        # nothing to refresh or reword: the question stays
        _withdraw(core, session, asked, "settled", QUESTION_SETTLED_SAY, decision=decision,
                  quote=quote, action=action, changes=changes, kept=dict(asked),
                  **({"before": before} if action == "reword" else {}))
        waiting.pop(key, None)


def _reword_contradicting(core: Any, session: str, asked: Mapping[str, Any],
                          item: Mapping[str, Any], decision: str, quote: str,
                          confirmed: Mapping[str, str]) -> bool:
    """SR-217 EX-2: a confirmed record the decision contradicts, one of the records the waiting
    question is about, is reworded to agree with it; an unconfirmed edit the judge validates,
    citing the decision. The decision itself is never the one reworded."""
    from iaso.capture.records import rewrite

    target, wording = str(item.get("record") or ""), str(item.get("wording") or "")
    named = {str(r.get("id")) for r in asked.get("records") or () if isinstance(r, Mapping)}
    record = core.index().get(target)
    if (not wording or target == decision or target not in named or record is None
            or "statement" not in record.fields):
        return False
    before = str(record.fields.get("statement") or "")
    rewrite(core, record, {"statement": wording})
    _withdraw(core, session, asked, "settled", QUESTION_SETTLED_SAY, decision=decision,
              quote=quote, action="reword", changes=[], record=target, kept=dict(asked),
              before=before)
    return True


def undo_settlement(core: Any, key: str) -> bool:
    """``iaso question reopen``: put back what the latest settlement of ``key`` changed, a
    reworded statement and the repinned links. False when it settled nothing."""
    from iaso import links
    from iaso.understand import judge

    mine = [e for e in core.events() if e.kind in ("question-withdrawn", "answer-unbound")
            and e.payload.get("key") == key]
    if (not mine or mine[-1].kind != "question-withdrawn"
            or mine[-1].payload.get("reason") != "settled"):
        return False
    event = mine[-1].payload
    changes = event.get("changes") or []
    reworded = str(event.get("record") or (str(changes[0]["link"]).partition("#")[0]
                                           if changes else ""))
    if "before" in event and reworded:
        from iaso.capture.records import rewrite

        rewrite(core, core.index()[reworded], {"statement": event["before"]})
    links.restore_pins(core, changes)
    if event.get("kept"):       # the refreshed link left the file; the question waits again
        judge.add_question(core, str(event.get("session")), event["kept"])
    return True


def _read_typed(core: Any, job: Job) -> None:
    """SR-212: this job read the owner's typed replies it was given; a question they did not
    settle comes back to the owner (``judge._typed_unread``)."""
    from iaso.understand import judge

    given = {str(a.get("id")) for a in job.inputs.get("answers") or ()}
    keys: set[str] = set()
    for e in _answer_entries(core):
        asked = e.payload.get("asked")
        if e.payload.get("free_text") and e.digest in given and isinstance(asked, Mapping):
            keys.update(map(str, (asked.get("key"), *(asked.get("keys") or ()))))
    keys &= judge._typed_unread(core)
    if keys:
        core.log_append_many("events", [("answer-read", {"session": job.session,
                                                         "keys": sorted(keys)})])


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    confirmed = _confirmed(core)
    _close_questions(core, job.session, answer.get("questions") or (), confirmed)
    _settle(core, job.session, answer.get("settlements") or (), confirmed)
    _read_typed(core, job)
    return Applied(job=job.id)


def run(command: str, argv: list[str]) -> int:
    """``iaso understand undo <record id>``: take back a record a model confirmed (SR-191)."""
    import argparse

    from iaso.api import open_core
    from iaso.cliutil import add_common, resolve_root
    from iaso.understand.typed import take_back

    parser = argparse.ArgumentParser(prog="iaso understand undo")
    add_common(parser)
    parser.add_argument("record")
    args = parser.parse_args(argv)
    core = open_core(resolve_root(args.root))
    result = take_back(core, args.record)
    print(*result.lines, sep="\n")
    return 0 if result.confirmed else 1
