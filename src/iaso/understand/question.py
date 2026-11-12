"""The question job kind (SR-167): the agent's last reply asks the owner something whose answer
would confirm, reject or change a record, choose a conflict's side or settle a stale link.

``build`` and ``recompute`` take that reply and the records it seems to touch; ``apply`` files
the question as an open judge question (its options from the reply), so the owner's typed answer
is read as the answer to a judge question. A question that names no record files none."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from iaso.contracts import Applied, Job
from iaso.present import owner_text
from iaso.understand import files, judge, read

kind = "question"
SCHEMA_ID = "question.v1"
HERE = Path(__file__).resolve().parent
EFFECTS = ("accepted", "rejected", "change")


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "question.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**data, "id": SCHEMA_ID}


schema: Mapping[str, Any] = _load_schema()


def asked_question(core: Any, asked: Mapping[str, Any], job: Job) -> dict[str, Any] | None:
    """A question ``{question, options: [{label, effect, consequence}], records}`` the model read
    from a reply, as an open judge question; None without a question, two options or a named
    record that exists (the question is about no record then). The same question is always the
    same one."""
    question = str(asked.get("question") or "").strip()
    options = [o for o in asked.get("options") or () if isinstance(o, Mapping)
               and str(o.get("label") or "").strip() and o.get("effect") in EFFECTS]
    index = core.index()
    named = [str(r) for r in asked.get("records") or () if str(r) in index]
    if not question or len(options) < 2 or not named:
        return None
    key = judge.question_key(question)
    return {"key": key, "job": f"reply:{key}", "records": [
        {"id": i, "hash": index[i].hash} for i in named], "principle": "", "blocking": False,
        "diagram": False, "reword": False, "question": question, "header": "Question",
        "options": [{"label": str(o["label"]).strip(),
                     "description": str(o.get("consequence") or "")} for o in options]}


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
    from iaso.understand import clarify, queue

    talk = clarify.conversation(transcript, "")
    job = build(core, session, reply=(talk or {}).get("last_reply", ""))
    if job is not None:
        queue.enqueue(core, job)


def already_known(core: Any, made: Mapping[str, Any]) -> bool:
    """Case report-9316d1a2: the reply only quotes or reports a question the owner already
    has or already answered, so reading it files nothing. That is: the same question was
    answered; a question waiting in any session about one of the same records holds these
    words or is held in them (a note added or dropped changes the key); or it is the proof
    question of records whose proof is confirmed."""
    from iaso.capture import proof

    key, ids = str(made["key"]), {str(r["id"]) for r in made["records"]}
    if key in judge._answered_keys(core):
        return True
    for q in judge.unanswered_anywhere(core):
        other = str(q.get("key") or "")
        if other and (other in key or key in other) and ids & judge._ids_of(q):
            return True
    labels = {str(o["label"]) for o in made["options"]}
    return (proof.YES in labels or key.startswith("did you see")) and all(
        proof.confirmed(core, i) for i in ids)


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    for q in answer.get("questions") or ():
        if isinstance(q, Mapping) and (made := asked_question(core, q, job)) is not None \
                and not already_known(core, made):
            judge.add_question(core, job.session, made)   # the next turn's ask names it
    return Applied(job=job.id)
