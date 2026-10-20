"""The question job kind (SR-167): the agent's last reply asks the owner something whose answer
would confirm, reject or change a record, choose a conflict's side or settle a stale link.

``build`` and ``recompute`` take that reply and the records it seems to touch; ``apply`` raises
the question as a choice card (its options from the reply) and names it to the agent in its
next prompt. ``card`` is also how the request check raises the card of a question the owner
answered before any turn end did (``clarify.apply``). A question that changes no record raises
none. ``to_room`` and ``answered_in_room``: a judge question the owner chose to study in the
room (SR-333)."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, CardState, Choice, Job
from plumb.present import owner_text
from plumb.understand import cards, cardstore, files, read

kind = "question"
SCHEMA_ID = "question.v1"
HERE = Path(__file__).resolve().parent
EFFECTS = ("accepted", "rejected", "change")
ROOM_WAITS = "room_waits.json"     # the band's 'a question waits in the room' (DEC-294)


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "question.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**data, "id": SCHEMA_ID}


schema: Mapping[str, Any] = _load_schema()


def card(core: Any, asked: Mapping[str, Any], branch: str = "") -> CardState | None:
    """The choice card of a question ``{question, options: [{label, effect, consequence}],
    records}`` the model read from a reply; None without a question or two options. The first
    named record that exists is the one the question changes; the same question is always the
    same card."""
    question = str(asked.get("question") or "").strip()
    options = [o for o in asked.get("options") or () if isinstance(o, Mapping)
               and str(o.get("label") or "").strip() and o.get("effect") in EFFECTS]
    if not question or len(options) < 2:
        return None
    index = core.index()
    named = [str(r) for r in asked.get("records") or () if str(r) in index]
    record = index[named[0]] if named else None
    choices = [Choice(str(o["label"]).strip(), o["effect"],
                      str(o["label"]).strip() if o["effect"] == "change" else None,
                      str(o.get("consequence") or "")) for o in options]
    topic = record.title if record is not None else cards.clip(question, 60)
    about = [f"About: {', '.join(named)}"] if named else []
    made = cards._card("choice", cards.card_id("choice", "question", question), topic, question,
                       "\n".join(["Asked by the agent in its reply", *about]), choices,
                       [(question, record)])
    return dataclasses.replace(made, branch=branch)


def to_room(core: Any, session: str, asked: Mapping[str, Any]) -> CardState | None:
    """SR-333 EX-3, DEC-294: a judge question the owner chose to study in the room becomes
    its card in the store (every option, a diagram to draw when it needs one), and the band's
    mark ``ROOM_WAITS`` names it until the owner's press opens the room on it."""
    from plumb.understand import clarify

    root = Path(core.root)
    made = card(core, {"question": asked.get("question"), "options": [
        {"label": o.get("label"), "effect": "change", "consequence": o.get("description")}
        for o in asked.get("options") or () if isinstance(o, Mapping)], "records": [
        r.get("id") for r in asked.get("records") or () if isinstance(r, Mapping)]},
        clarify.repository(root)["branch"])
    if made is None:
        return None
    if asked.get("diagram"):
        made = dataclasses.replace(made, diagram=f".plumb/session/{session}/diagrams/"
                                                 f"{made.id.split(':')[-1]}.html")
    cardstore.save(root, session, [*(c for c in cardstore.own_cards(root, session)
                                     if c.id != made.id), made])
    files.write_json_atomic(files.session_dir(root, session) / ROOM_WAITS, {"card": made.id})
    return made


def answered_in_room(core: Any, session: str, card_id: str, label: str) -> None:
    """SR-333 EX-5: the owner's press in the room on a judge question's card is their answer
    to that question: logged as a question-tool answer to it (the tool put it to them) and
    judged again, as the question-answer hook does."""
    from plumb.understand import judge

    moved = next((e.payload["room"] for e in core.events() if e.kind == "question-answer"
                  and e.payload.get("session") == session
                  and isinstance(e.payload.get("room"), Mapping)
                  and e.payload["room"].get("card") == card_id), None)
    if moved is None:
        return
    logged = core.log_append("events", "question-answer", {
        "session": session, "question": moved["question"], "options": moved["options"],
        "answer": label, "via": "question-tool",
        "asked": {k: moved.get(k) for k in ("job", "key", "records")}})
    judge.rejudge(core, session, [logged])


def _inputs(core: Any, reply: str) -> dict[str, Any] | None:
    if not reply.strip():
        return None
    index = core.index()
    found = [rid for rid, _ in core.relevant(reply, 8) if rid in index]
    statuses = core.status(found) if found else {}
    return {"reply": reply, "records": [
        {"id": i, "status": statuses[i].confirmation, "text": read.record_text(index[i])}
        for i in found]}


def build(core: Any, session: str, **context: Any) -> Job | None:
    inputs = _inputs(core, str(context.get("reply") or "")) if core is not None else None
    return None if inputs is None else files.make_job(kind, session, SCHEMA_ID, inputs)


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    return _inputs(core, str(job.inputs.get("reply") or "")) if core is not None else None


def describe(job: Job) -> str:
    return owner_text.STEP_QUESTIONS


def enqueue(core: Any, session: str, transcript: Any) -> None:
    """Queue the job for the agent's reply of this turn; it never waits for the model."""
    from plumb.understand import clarify, queue

    talk = clarify.conversation(transcript, "")
    job = build(core, session, reply=(talk or {}).get("last_reply", ""))
    if job is not None:
        queue.enqueue(core, job)


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    from plumb.understand import clarify, summary

    branch = clarify.repository(Path(core.root))["branch"]
    own = {c.id for c in cardstore.own_cards(Path(core.root), job.session)}
    raised = [c for q in answer.get("questions") or () if isinstance(q, Mapping)
              if (c := card(core, q, branch)) is not None and c.id not in own][:1]
    for c in raised:
        summary.tell_agent(core, job.session, c)    # the next prompt names it (SR-116 EX-4)
    return Applied(job=job.id, cards=tuple(raised))
