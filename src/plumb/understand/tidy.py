"""The tidy job kind (SR-218): one model reading per change of the judge's waiting questions
against the owner's confirmed records and logged answers, so a question the owner already
answered is closed without waiting for them.

``build`` and ``recompute`` take the questions, the answers and the confirmed records from the
logs; ``apply`` closes a question only after exact checks: the quoted words are really in the
owner's answer or in the confirmed record. A closing is logged as ``answer-bound`` and undone by
``plumb question reopen``. Unsure leaves the question open."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, Job
from plumb.present import owner_text
from plumb.understand import files, read

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
    questions = _questions(core)
    # shortcut: every confirmed record is sent, so a very large record set makes a big prompt;
    # upgrade to the records `core.relevant` picks per question when that costs too much
    if not questions:
        return None
    return {"questions": questions, "answers": _answers(core),
            "confirmed": [{"id": i, "text": t} for i, t in _confirmed(core).items()]}


QUESTION_CLOSED = ("plumb: closed a waiting question the owner already answered: \"{question}\" "
                   "(their words: \"{quote}\"); plumb question reopen <its words> undoes it")
ANSWERS_MAX = 300    # shortcut: the owner's latest answers only; widen if an older one is missed


def _questions(core: Any) -> list[dict[str, Any]]:
    """SR-218: the judge's open questions of every session."""
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
    """Queue the job for the questions open now; it never waits for the model."""
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
        worker.say(core.root, session, QUESTION_CLOSED.format(
            question=str(asked.get("question") or "").split("\n")[0][:120], quote=quote[:160]))


def _read_typed(core: Any, job: Job) -> None:
    """SR-212: this job read the owner's typed replies it was given; a question they did not
    settle comes back to the owner (``judge._typed_unread``)."""
    from plumb.understand import judge

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
    _read_typed(core, job)
    return Applied(job=job.id)


def run(command: str, argv: list[str]) -> int:
    """``plumb understand undo <record id>``: take back a record a model confirmed (SR-191)."""
    import argparse

    from plumb.api import open_core
    from plumb.cliutil import add_common, resolve_root
    from plumb.understand.typed import take_back

    parser = argparse.ArgumentParser(prog="plumb understand undo")
    add_common(parser)
    parser.add_argument("record")
    args = parser.parse_args(argv)
    core = open_core(resolve_root(args.root))
    result = take_back(core, args.record)
    print(*result.lines, sep="\n")
    return 0 if result.confirmed else 1
