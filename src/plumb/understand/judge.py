"""The judge job kind (JUDGE, SR-102, spec 4.2).

A model independent of the coding agent is asked, for every record a capture wrote or changed
(one job per capture) or the backlog pass covers (one job per intent): *would the owner object
to this record, given their words?* The record's premise is the owner's whole logged message or
messages (``understand.premise``), the stored question for a short answer, and the parent
intent when the owner confirmed it, next to the owner's confirmed records it
relates to. Labelled assumptions are shown and left out of what is judged.

``apply`` logs one ``verdict`` per record (the score is the model's confidence for
``supported``, 0 otherwise), approves ``by: auto-jev`` what the fast track takes, and writes
the judge model's questions about the owner's intent to ``judge_questions.json`` for the
question tool (SR-248, SR-267); a record no question covers waits with the waiting line
(SR-245). After a question round (the premise holds the owner's answers at the record's
version) a record is approved citing those answers: ``by: auto-jev`` when JEV clears it,
else ``by: auto-model`` when the judge model says the intent is clear (its confidence is
logged, never compared, DEC-141); otherwise the next questions follow. An escalated spec set
is one approval, written when every record of it is clear at its version (P6). No trial or
read-back card is raised (SR-252 EX-6). Each source of a judged premise (the owner's message,
a question-tool answer) is kept once as a ``pre-intent`` with its question, options and the
reply it answered, and every approval names those sources in its ``trail`` (SR-208, SR-209).
A record the owner's latest words contradict is sent back for the agent to reword (SR-209
EX-2). When the judge says an answer corrects its reading, one ``capture-error`` rejection
pins the record at the asked hash with the premise, the parts and JEV's score, a real 'no'
for calibration (SR-252 EX-4). It returns the log entries: the worker writes them.
The kind registers the handlers of the trial, beyond and contradicts cards (``effects``; old
cards of those kinds are still answered)."""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from plumb.approvals import approval_items
from plumb.contracts import Applied, Job
from plumb.judgment.verdict import BY
from plumb.present import owner_text
from plumb.understand import backlog, cards, files, premise, trial
from plumb.understand import verdict as verdict_cascade

kind = "judge"
SCHEMA_ID = "judge.v1"
HERE = Path(__file__).resolve().parent
KINDS_JUDGED = ("intent", "requirement", "decision")
RELATED_MAX = 12
TEXT_WIDTH = 1200
VERDICTS = ("supported", "beyond", "contradicts", "waiting")
QUESTIONS_FILE = "judge_questions.json"
REWORDED_FILE = "reworded.json"     # SR-362: the agent's wording of the judge's questions
HEADER_MAX = 12          # the question tool's chip
_MARKER = re.compile(r"\s*\(recommended\)", re.IGNORECASE)
_PLUMB_WORDS = re.compile(r"\b(?:proposed|settled|trial|records?|judge[sd]?)\b",
                          re.IGNORECASE)
_LEFT_IN = re.compile(r"(?<![\w-])(?:INT|SR|DEC|FEAT|NC|IC)-\d+|sha256:"
                      r"|\b[0-9a-f]{12,}\b")      # a record id or a digest left in


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "judge.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"id": SCHEMA_ID, **data}


def _lenient(full: Mapping[str, Any]) -> Mapping[str, Any]:
    """SR-299 EX-1, EX-3: the schema dispatchers and the worker check an answer against. The
    model is asked for records and 2-4 options (schemas/judge.json, the judge's instructions);
    a question short of them must not reject the whole answer: ``apply`` fills the records,
    and the cascade retries the question once, then writes a debug case."""
    out = json.loads(json.dumps(full))
    item = out.get("properties", {}).get("questions", {}).get("items", {})
    item["required"] = ["question"]
    item.get("properties", {}).get("options", {}).pop("minItems", None)
    return out


schema: Mapping[str, Any] = _lenient(_load_schema())


# --------------------------------------------------------------------------- record texts


def _flat(value: Any) -> str:
    return " ".join(str(value or "").split())


def _items(raw: Any) -> list[str]:
    from plumb.capture.triage import _items

    return _items(raw)


def record_text(record: Any) -> str:
    """What a record asserts as the owner's (assumptions are not part of it)."""
    fields = record.fields
    if record.kind == "intent":
        lines = [_flat(fields.get("readback") or record.title)]
        lines += [f"will: {w}" for w in _items(fields.get("will"))]
        lines += [f"won't: {w}" for w in _items(fields.get("wont"))]
        return "\n".join(lines)
    if record.kind == "requirement":
        lines = [_flat(fields.get("statement") or record.title)]
        lines += [f"{e.id}: given {e.given}, when {e.when}, then {e.then}"
                  for e in record.examples]
        return "\n".join(lines)
    if record.kind == "decision":
        return f"question: {_flat(fields.get('question'))}\nchosen: {_flat(fields.get('chosen'))}"
    return _flat(record.title)


def _clip(text: str, width: int = TEXT_WIDTH) -> str:
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."


def _related(core: Any, record: Any, index: Mapping[str, Any],
             statuses: Mapping[str, Any]) -> list[dict[str, str]]:
    """The owner's confirmed records ``record`` relates to: those it links to,
    those linking to it, and the requirements of its feature."""
    near: list[str] = []

    def add(record_id: str) -> None:
        if record_id != record.id and record_id in index and record_id not in near:
            near.append(record_id)

    for link in record.links:
        if link.target.record:
            add(link.target.record)
    for other in index.values():
        if any(link.target.record == record.id for link in other.links):
            add(other.id)
    feature = record.fields.get("feature")
    if feature:
        for other in index.values():
            if other.kind == record.kind and other.fields.get("feature") == feature:
                add(other.id)
    out: list[dict[str, str]] = []
    for record_id in near:
        state = statuses.get(record_id)
        if state is None or state.confirmation != "confirmed":
            continue
        out.append({"id": record_id, "status": "confirmed",
                    "text": _clip(record_text(index[record_id]), 600)})
        if len(out) >= RELATED_MAX:
            break
    return out


def entry_for(core: Any, record: Any, statuses: Mapping[str, Any],
              known: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """The judge input of one record."""
    index = core.index()
    return {"id": record.id, "hash": record.hash, "kind": record.kind,
            "text": _clip(record_text(record)),
            "assumptions": _items(record.fields.get("assumptions")),
            "premise": premise.premise_of(core, record, statuses=statuses,
                                          known=known).as_input(),
            "related": _related(core, record, index, statuses)}


def entries_for(core: Any, ids: Sequence[str]) -> list[dict[str, Any]]:
    index = core.index()
    wanted = [i for i in dict.fromkeys(ids) if i in index and index[i].kind in KINDS_JUDGED]
    if not wanted:
        return []
    statuses = core.status()
    known = premise.committed(core)
    return [entry_for(core, index[i], statuses, known) for i in wanted]


# --------------------------------------------------------------------------- the kind


def build(core: Any, session: str, **context: Any) -> Job | None:
    """One judge job covering ``records`` (ids), or None when none can be judged. ``pass`` and
    ``total`` mark a backlog job (the pass covers ``total`` records)."""
    ids = [str(i) for i in context.get("records") or ()]
    if core is None or not ids:
        return None
    records = entries_for(core, ids)
    if not records:
        return None
    inputs: dict[str, Any] = {"records": records}
    if context.get("pass"):
        inputs["pass"] = str(context["pass"])
        inputs["total"] = int(context.get("total") or len(records))
    return files.make_job(kind, session, SCHEMA_ID, inputs)


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    """The inputs rebuilt from the logs, as they stand when the worker runs the job. A bare job
    (the question-answer hook's) names its records by id alone."""
    if core is None:
        return None
    ids = [str(r.get("id")) if isinstance(r, Mapping) else str(r)
           for r in job.inputs.get("records") or ()]
    records = entries_for(core, ids)
    if not records:
        return None
    return {**{k: v for k, v in job.inputs.items() if k != "records"}, "records": records}


def describe(job: Job) -> str:
    records = job.inputs.get("records") or ()
    if not records:
        return owner_text.STEP_CHECKING
    if job.inputs.get("pass") == "backlog":
        return owner_text.STEP_JUDGING_BACKLOG
    return owner_text.STEP_JUDGING.format(n=len(records))


Waiting = verdict_cascade.Waiting


def cascade(core: Any, job: Job, **context: Any) -> Any:
    """SR-182: who answers this job. JEV first where its probability clears the calibrated
    threshold, the judge model for the rest; ``Waiting`` when neither can be reached."""
    return verdict_cascade.cascade(core, job, **context)


def _confidence(value: Any) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 6)
    except (TypeError, ValueError):
        return 0.0


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [_flat(v) for v in value or () if _flat(v)]


def _fast_tracked(core: Any, record: Any, raw: Mapping[str, Any],
                  jev: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The ``auto`` payload when JEV's verdict on ``record`` takes the fast track, else None."""
    if record is None or jev is None or raw.get("by") != "jev" or not jev.get("clears"):
        return None
    from plumb.capture.autoapprove import fast_track

    return fast_track(core, record, jev)


def _approve(core: Any, job: Job, ids: Sequence[str], item: Mapping[str, Any], by: str,
             auto: Mapping[str, Any], known: set[Any], answers: Sequence[str] = (),
             **extra: Any) -> list[Mapping[str, Any]]:
    """The worker's ``by`` approval of ``ids`` (carrying the session, the ``trail`` of
    pre-intent sources and, after a question round, the owner's ``answers``: question-answer
    entry digests), after the prompt event of the owner's words it cites when none is logged
    yet."""
    messages = [m for m in (item.get("premise") or {}).get("messages") or ()
                if isinstance(m, Mapping) and m.get("digest") and not m.get("partial")]
    digest = str(messages[0]["digest"]) if messages else ""
    out: list[Mapping[str, Any]] = []
    if digest and digest not in known:
        from plumb.approvals import Refused, find_prompt

        try:
            found = find_prompt(core, digest)
        except Refused:
            found = {}
        out.append({"kind": "prompt", "payload": {"digest": digest,
                                                  "session": found.get("session"),
                                                  "at": found.get("at")}})
        known.add(digest)
    payload = {"records": approval_items(core, ids), "by": by,
               "prompt_digest": digest or (answers[0] if answers else ""), "quote": None,
               "quote_digest": None, "session": job.session, "job": job.id,
               "auto": dict(auto), "trail": _trail([item], _pre_intents(core)), **extra}
    if answers:
        payload["answers"] = list(answers)
    out.append({"kind": "approval", "payload": payload})
    return out


def _pre_intents(core: Any) -> dict[str, Mapping[str, Any]]:
    """Entry digest -> payload of the logged ``pre-intent`` entries."""
    return {e.digest: e.payload for e in core.events() if e.kind == "pre-intent"}


def context_of(core: Any, digest: str) -> str:
    """The excerpt of the reply the owner's message ``digest`` answered: the conversation the
    prompt hook froze for it (``clarify.frozen_context``), read only; '' when none is on file."""
    from plumb.approvals import Refused, find_prompt
    from plumb.understand.clarify import context_path

    try:
        session = str(find_prompt(core, digest).get("session") or "")
    except Refused:
        return ""
    frozen = files.read_json(context_path(Path(core.root), session, digest))
    talk = frozen.get("context") if isinstance(frozen, Mapping) else None
    return str(talk.get("last_reply") or "") if isinstance(talk, Mapping) else ""


def _sources(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The owner's words a judged premise rests on: whole messages, then answers."""
    given = item.get("premise") or {}
    return [*(m for m in given.get("messages") or () if isinstance(m, Mapping)
              and m.get("digest") and not m.get("partial")),
            *(a for a in given.get("answers") or () if isinstance(a, Mapping)
              and a.get("digest"))]


def _trail(items: Sequence[Mapping[str, Any]], pre: Mapping[str, Mapping[str, Any]]
           ) -> list[str]:
    """The pre-intents an approval rests on, each named by its source (one pre-intent per
    source; a read pre-intent cited as an answer is named by the message it keeps)."""
    out = [str(pre[s["digest"]].get("source")) if s["digest"] in pre else str(s["digest"])
           for item in items for s in _sources(item)]
    return list(dict.fromkeys(out))


def _new_pre_intents(core: Any, session: str, items: Sequence[Mapping[str, Any]]
                     ) -> list[Mapping[str, Any]]:
    """One ``pre-intent`` per premise source of ``items`` not logged yet (SR-208 EX-4, SR-212):
    the owner's words verbatim with the question, the options and the reply they answered.
    A read pre-intent cited as an answer is one already."""
    pre = _pre_intents(core)
    known = {str(p.get("source")) for p in pre.values()}
    out: list[Mapping[str, Any]] = []
    for item in items:
        question = str((item.get("premise") or {}).get("question") or "")
        for source in _sources(item):
            digest = str(source["digest"])
            if digest in known or digest in pre:
                continue
            known.add(digest)
            answer = "answer" in source
            out.append({"kind": "pre-intent", "payload": {
                "source": digest, "session": session,
                "text": str(source.get("answer" if answer else "text") or ""),
                "question": str(source.get("question") or "") if answer else question,
                "options": list(source.get("options") or ()) if answer else [],
                "context": "" if answer else context_of(core, digest)}})
    return out


def _correction(job: Job, item: Mapping[str, Any], record: Any, index: Mapping[str, Any],
                jev: Mapping[str, Any] | None, cited: Sequence[str]) -> Mapping[str, Any]:
    """SR-252 EX-4: the owner's answer corrected the judge's reading of ``record``. One
    ``capture-error`` rejection pinned at the asked hash, with the premise and the parts JEV
    was asked about and JEV's score of this judgment, so calibration labels it 'no' with no
    new model call."""
    from plumb.capture.calibrate import _hypotheses

    pinned: dict[str, Any] = {
        "id": record.id, "hash": item["hash"],
        "kind": verdict_cascade.CLAIM_KIND.get(record.kind),
        "premise": verdict_cascade._premise_text(item),
        "hypotheses": list(_hypotheses(index, record)[1])}
    if jev is not None and jev.get("score") is not None:
        pinned["jev_score"] = jev["score"]
    return {"kind": "rejection", "payload": {
        "by": "owner-answer", "session": job.session, "job": job.id, "records": [pinned],
        "reason": "capture-error", "answers": list(cited)}}


def _sent_back(core: Any, session: str, sent: Mapping[str, str]) -> str:
    """SR-209 EX-2: the owner's latest words contradict these records; the agent rewords each
    and the edit goes back to the judge."""
    from plumb.understand import worker

    line = "plumb: the owner's words contradict " + "; ".join(
        f"{i} ({why})" for i, why in sent.items()) + ": reword it to agree with them; " \
        "the edit goes back to the judge"
    worker.say(core.root, session, line)
    return line


def _after_round(core: Any, record: Any, raw: Mapping[str, Any], payload: Mapping[str, Any],
                 jev: Mapping[str, Any] | None, in_set: bool
                 ) -> tuple[str, dict[str, Any]] | None:
    """``(by, auto)`` when the record the owner answered about is clear after the round: a
    ``supported`` verdict with nothing beyond or contradicting, given by JEV clearing it
    (above max(0.9, its calibrated threshold); never alone for a record of an
    escalated set), else by the judge model saying the intent is clear (SR-248 EX-4, EX-5).
    None: the next questions follow."""
    from plumb.capture.autoapprove import after_round
    from plumb.judgment.verdict import JEV

    if payload["verdict"] != "supported" or payload["contradicts"] or payload["beyond"]:
        return None
    if payload.get("answer_corrects"):  # SR-252 EX-4: a corrected reading is never approved
        return None
    if raw.get("by") == JEV and jev is not None and jev.get("clears") and not in_set:
        auto = after_round(core, record, jev)
        if auto is not None:
            return "auto-jev", auto
    if raw.get("clear") is True and raw.get("by") != JEV:
        return "auto-model", {"model": payload["model"],
                              "model_version": str(raw.get("judge") or payload["model"]),
                              "confidence": payload["score"], "clear": True}
    return None


def _clear_before(core: Any, record: Any) -> tuple[float, list[str]] | None:
    """The confidence and cited answers of the latest verdict on ``record`` at its version
    after a round, when it is clear and cites every answer logged about it at that version;
    else None (a set waits for its other records across jobs)."""
    now = [e.digest for e in premise.answer_entries(core, record)]
    for e in reversed(core.events()):
        p = e.payload
        if e.kind == "verdict" and p.get("id") == record.id and p.get("hash") == record.hash \
                and p.get("answers"):
            if p.get("verdict") == "supported" and p.get("clear") is True \
                    and not p.get("contradicts") and not p.get("beyond") \
                    and p.get("answers") == now:
                return _confidence(p.get("score")), now
            return None
    return None


def _set_approvals(core: Any, job: Job, rounds: Mapping[str, tuple[Any, ...]],
                   asked: Mapping[str, Mapping[str, Any]], known: set[Any]
                   ) -> tuple[list[Mapping[str, Any]], dict[str, str]]:
    """The one approval of each escalated set whose every record is clear at its version,
    and the clear records still waiting for their set (id -> anchor)."""
    from plumb.capture.spec import SpecError, current_set_hash, escalated_sets, set_ids

    sets, owner = escalated_sets(core)
    index = core.index()
    out: list[Mapping[str, Any]] = []
    held: dict[str, str] = {}
    for anchor in dict.fromkeys(owner.get(i, i) for i in rounds):
        try:
            whole = set_ids(core, anchor)
        except SpecError:
            whole = []
        clear = {i: (rounds[i][1]["confidence"], rounds[i][2]) for i in whole if i in rounds}
        clear.update({i: c for i in whole if i not in clear
                      and (c := _clear_before(core, index[i])) is not None})
        if not whole or set(whole) - set(clear):
            held.update({i: anchor for i in whole if i in rounds})
            continue
        answers = list(dict.fromkeys(d for i in whole for d in clear[i][1]))
        first = next(i for i in whole if i in rounds)
        auto = {**rounds[first][1], "confidence": min(c for c, _ in clear.values())}
        out += _approve(core, job, whole, asked[first], "auto-model", auto, known, answers,
                        set={"anchor": anchor, "hash": current_set_hash(core, anchor)},
                        trail=_trail([asked[i] for i in whole if i in asked],
                                     _pre_intents(core)))
    return out, held


def question_key(text: str) -> str:
    """The key a question is matched by: lowercase, whitespace collapsed, "(Recommended)" out."""
    return " ".join(str(text).lower().replace("(recommended)", "").split())


def questions_path(root: Any, session: str) -> Path:
    """The session's open judge questions; only the worker writes it."""
    return files.session_dir(Path(root), session) / QUESTIONS_FILE


def _logged_questions(root: Any, session: str) -> list[Mapping[str, Any]]:
    raw = files.read_json(questions_path(root, session))
    return [q for q in raw if isinstance(q, Mapping)] if isinstance(raw, list) else []


def _ids_of(question: Mapping[str, Any]) -> set[str]:
    return {str(r.get("id")) for r in question.get("records") or () if isinstance(r, Mapping)}


def unanswered(core: Any, session: str) -> list[Mapping[str, Any]]:
    """The session's judge questions no question-answer entry answers yet, by its question's
    key or the keys it was matched to (``asked.key``, ``asked.keys``: SR-362, the agent's
    wording covering several); 'Study it first' answers nothing (SR-336); one the judge
    withdrew on the agent's push-back (``question-ruling``) is gone. Reads no record (the hook
    calls it)."""
    asked = _logged_questions(core.root, session)
    if not asked:
        return []
    answered: set[str] = set()
    for e in core.events():
        if e.payload.get("session") != session:
            continue
        if e.kind == "question-answer" and not e.payload.get("study"):
            answered.add(question_key(str(e.payload.get("question") or "")))
            if isinstance(e.payload.get("asked"), Mapping):
                answered.add(str(e.payload["asked"].get("key")))
                answered.update(map(str, e.payload["asked"].get("keys") or ()))
        elif e.kind == "question-ruling" and e.payload.get("ruling") == "withdrawn":
            answered.add(str(e.payload.get("key")))
    return [q for q in asked if q.get("key") not in answered]


def open_questions(core: Any, session: str) -> list[Mapping[str, Any]]:
    """The judge questions still waiting for the owner: not answered yet (``unanswered``),
    asking about a record still unconfirmed and not superseded at the version asked, and not
    answered since by a decision recording the owner's choice (the owner answered in a typed
    message and the agent captured it): never ask what was said."""
    asked = unanswered(core, session)
    if not asked:
        return []
    from plumb.capture.clarify import superseded_ids

    index, statuses = core.index(), core.status()
    closed = superseded_ids(index)   # a superseded record's question is answered by its successor

    def settled(q: Mapping[str, Any]) -> bool:
        # the owner answered it by capture after it was logged: a decision records the answer
        ids = [str(r.get("id")) for r in q.get("records") or () if isinstance(r, Mapping)]
        labels = [_MARKER.sub("", str(o.get("label") or "")) for o in q.get("options") or ()
                  if isinstance(o, Mapping)]
        return bool(labels and _answered_by(core, index, ids, labels))

    return [q for q in asked if not settled(q) and any(
        str(r.get("id")) in index and index[str(r.get("id"))].hash == r.get("hash")
        and str(r.get("id")) not in closed
        and statuses[str(r.get("id"))].confirmation != "confirmed"
        for r in q.get("records") or () if isinstance(r, Mapping))]


def rejudge(core: Any, session: str, logged: Sequence[Any]) -> None:
    """SR-212: the records the logged answers were asked about go back to the judge, one bare
    job (the worker rebuilds their premise from the logs, ``recompute``)."""
    from plumb.understand import queue

    ids = [str(r.get("id")) for e in logged for r in (e.payload.get("asked") or {}).get(
        "records", ()) if isinstance(r, Mapping)]
    if ids:
        queue.enqueue(core, files.make_job(kind, session, SCHEMA_ID, {
            "records": list(dict.fromkeys(ids)), "answered": [e.digest for e in logged]}))


def _whole_words(header: str) -> str:
    """SR-309 EX-1: the header's words that fit the chip, dropped from the end, never cut."""
    words = header.split()
    while len(words) > 1 and len(" ".join(words)) > HEADER_MAX:
        words.pop()
    return " ".join(words)[:HEADER_MAX].strip()   # shortcut: one word over the chip is cut


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\w-]+", text.lower()))


def _answered_by(core: Any, index: Mapping[str, Any], ids: Sequence[str],
                 labels: Sequence[str]) -> str:
    """SR-309 EX-3: the decision that records the owner's answer to this question: it links
    one of the question's records, and what it chose holds the words of one option. SR-335:
    it is confirmed, or quotes the owner's own logged words; one only the agent wrote and
    not yet approved settles nothing."""
    said: list[tuple[str, str]] | None = None
    for rec in index.values():
        if rec.kind != "decision" or not ids or not any(
                ln.target.record in ids for ln in rec.links):
            continue
        chosen = _tokens(_flat(rec.fields.get("chosen")))
        if not any(len(t) > 1 and t <= chosen for t in map(_tokens, labels)):
            continue
        state = core.status([rec.id])[rec.id]
        said = premise.owner_words(core) if said is None else said
        if state.superseded_by is None and (state.confirmation == "confirmed"
                                            or premise.owner_quoted(rec, said)):
            return rec.id
    return ""


def _own_words(core: Any, ids: Sequence[str], index: Mapping[str, Any]) -> str:
    """SR-249 EX-1: with no quote from the judge, an older record's own quoted words, when a
    past session transcript holds them (its first part: ``exact_match`` holds every part)."""
    from plumb.understand import recover

    older = [index[i] for i in ids
             if i in index and not premise.premise_of(core, index[i]).messages]
    messages = recover.owner_messages(core.root) if older else []
    return next((recover.quote_parts(rec)[0] for rec in older
                 if recover.exact_match(rec, messages)), "")


def _said_in(core: Any, ids: Sequence[str], words: str, index: Mapping[str, Any]
             ) -> tuple[bool, str, bool]:
    """SR-309 EX-4, DEC-191: ``(said, date, older)``: ``words`` are in an owner message the
    records rest on (``date`` empty: the judge's own date stands), or, SR-335, in an answer or
    prompt of the owner's logged anywhere (``premise.owner_words``), or in a past session
    transcript the SR-249 search reads (``date`` is that message's day). ``older``: the
    records rest on no logged message at all, so a miss in the transcripts is worth saying."""
    from plumb.understand import recover

    want = _flat(words).lower().rstrip(".")
    logged = [m for i in ids if i in index
              for m in premise.premise_of(core, index[i]).messages]
    if want and any(want in _flat(m.get("text")).lower() for m in logged):
        return True, "", False
    if want:     # shortcut: transcripts are read per question, not cached
        said = [*premise.owner_words(core), *((m.text, m.at)
                                              for m in recover.owner_messages(core.root))]
        for text, at in said:
            if recover.holds(text, words.rstrip(". ")):
                day = datetime.fromisoformat(at.replace("Z", "+00:00")) if at else None
                return True, f"{day.day} {day:%b}" if day else "", False
    return False, "", not logged


def _shaped(core: Any, raw: Any, job: Job, judged: Mapping[str, str], index: Mapping[str, Any]
            ) -> tuple[dict[str, Any] | None, str]:
    """A judge question as the question tool shows it, or ``(None, why it waits)`` (SR-245
    EX-7, SR-267 EX-4): its request folded into the question, the reason into the recommended
    option; record numbers in the owner's terms; plumb's own words never shown."""
    if not isinstance(raw, Mapping):
        return None, "a question is out of schema"
    ids = [i for i in dict.fromkeys(str(r) for r in raw.get("records") or ()) if i in judged]
    ids = ids or list(judged)    # SR-299: a question naming none settles the records of its job
    options = [o for o in raw.get("options") or () if isinstance(o, Mapping)]
    request = raw.get("request") if isinstance(raw.get("request"), Mapping) else {}
    words, date = _flat(request.get("words")), _flat(request.get("date"))
    shown = [cards.plain(_flat(v), index) for v in (
        raw.get("question"), raw.get("header"), raw.get("recommended_reason"),
        *(o.get(k) for o in options for k in ("label", "consequence")))]
    if not ids or not 2 <= len(options) <= 4 or not all(shown):
        return None, ("a question lacks two to four options, their consequences or the "
                      "reason for the recommended one")
    if any(_PLUMB_WORDS.search(t) or _LEFT_IN.search(t) for t in shown):
        return None, "a question names plumb's own words"
    text, header, reason, *rest = shown
    words = words or _own_words(core, ids, index)
    heard, found_on, older = _said_in(core, ids, words, index)
    date = found_on or date
    said = f'You said on {date}: "{words}"' if date else f'You said: "{words}"'
    # DEC-191/192: a quote is optional; an older record's missing words are said so
    question = (f"{text}\n\n{said}" if heard else
                f"{text}\n\nI found none of your words about this in your past sessions."
                if older else text)
    pairs = [(_MARKER.sub("", label).strip(), c)
             for label, c in zip(rest[::2], rest[1::2], strict=True)]
    return {"key": question_key(question), "job": job.id,
            "records": [{"id": i, "hash": judged[i]} for i in ids],
            # SR-334: one answer settles the questions sharing a principle
            "principle": _flat(raw.get("principle")).lower(),
            "blocking": raw.get("blocking") is True,
            "diagram": raw.get("diagram") is True,     # SR-333: it offers the room
            "question": question, "header": _whole_words(header),
            "options": [{"label": f"{label.replace('(Recommended)', '').strip()} (Recommended)"
                         if n == 0 else label,    # the model may have marked it itself
                         "description": f"{consequence} Recommended: {reason}" if n == 0
                         else consequence}
                        for n, (label, consequence) in enumerate(pairs)]}, ""


def _questions(core: Any, job: Job, answer: Mapping[str, Any], judged: Mapping[str, str],
               index: Mapping[str, Any]
               ) -> tuple[list[dict[str, Any]], list[str]]:
    """The judge's questions shaped for the owner, and why the others wait."""
    shaped: list[dict[str, Any]] = []
    why: list[str] = []
    for raw in answer.get("questions") or ():
        made, reason = _shaped(core, raw, job, judged, index)
        done = made and _answered_by(core, index, [r["id"] for r in made["records"]],
                                     [_MARKER.sub("", o["label"]) for o in made["options"]])
        if made is None or done:   # shortcut: an answered question is dropped, its records wait
            why.append(reason or f"the owner already answered it ({done})")
        elif made["key"] not in {q["key"] for q in shaped}:
            shaped.append(made)
    return shaped, why


def _write_questions(core: Any, job: Job, judged: set[str], new: list[dict[str, Any]]) -> None:
    """The open questions file with this job's questions: the same question asked again
    gathers the records of both; a question whose every record this job judged again goes."""
    by_key = {q["key"]: q for q in new}
    old = _logged_questions(core.root, job.session)
    for q in old:
        same = by_key.get(str(q.get("key")))
        if same is not None:
            same["records"] += [r for r in q.get("records") or () if isinstance(r, Mapping)
                                and str(r.get("id")) not in judged | _ids_of(same)]
    kept = [q for q in old if q.get("key") not in by_key and not _ids_of(q) <= judged]
    if new or len(kept) != len(old):
        files.write_json_atomic(questions_path(core.root, job.session), [*kept, *new])


def add_question(core: Any, session: str, question: Mapping[str, Any]) -> None:
    """One question for the question tool from outside a judge job (the debug workflow's,
    SR-300 EX-3), in the shape ``_shaped`` writes. Its ``job`` names the link: a rerun's
    question replaces the earlier one about the same link instead of piling up beside it."""
    kept = [q for q in _logged_questions(core.root, session)
            if q.get("job") != question.get("job")]
    files.write_json_atomic(questions_path(core.root, session), [*kept, dict(question)])


def reworded(root: Any, session: str) -> list[Mapping[str, Any]]:
    """SR-362: the agent's wordings of the session's judge questions (``REWORDED_FILE``), each
    ``{key, question, header, options, covers}``: ``covers`` the judge question keys it asks."""
    raw = files.read_json(files.session_dir(Path(root), session) / REWORDED_FILE)
    return [w for w in raw if isinstance(w, Mapping)] if isinstance(raw, list) else []


def reword(core: Any, session: str, covers: Sequence[str], question: str, header: str,
           options: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """SR-362 EX-1: record the agent's wording of the judge questions ``covers`` (merged when
    they hinge on one principle); the question-answer hook answers each of them with the
    owner's answer to it. The same wording registered again replaces the earlier one."""
    worded = {"key": question_key(question), "question": question, "header": header,
              "options": [dict(o) for o in options], "covers": list(covers)}
    kept = [w for w in reworded(core.root, session) if w.get("key") != worded["key"]]
    files.write_json_atomic(files.session_dir(Path(core.root), session) / REWORDED_FILE,
                            [*kept, worded])
    return worded


def drop_settled_questions(root: Any, still_stale: Collection[str]) -> None:
    """Withdraw, in every session folder, the debug workflow's questions (``job`` is
    ``debug:<link id>``) about links no longer stale: their link was repinned, relinked or
    removed, so the question no longer stands (INT-079)."""
    for path in (Path(root) / ".plumb" / "session").glob(f"*/{QUESTIONS_FILE}"):
        raw = files.read_json(path)
        if not isinstance(raw, list):
            continue
        kept = [q for q in raw if not (isinstance(q, Mapping) and str(q.get("job") or "")
                                       .startswith("debug:")
                                       and str(q["job"])[6:] not in still_stale)]
        if len(kept) != len(raw):
            files.write_json_atomic(path, kept)


def _say_waiting(core: Any, session: str, waits: Mapping[str, str]) -> str:
    """SR-245: the records nobody can settle wait, and the once-per-window line says so."""
    from plumb.judgment import waiting_line

    why = "; ".join(f"{i}: {w}" for i, w in waits.items())
    line = waiting_line(core.root, verdict_cascade.STEP, why) or ""
    if line:
        from plumb.understand import worker

        worker.say(core.root, session, line)
    return f"waiting: {why}"


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    """Log the verdicts (with JEV's score when it gave one); approve ``by: auto-jev`` the
    records the fast track takes; write the judge's questions about the others for the
    question tool (``judge_questions.json``), and say once that a record no question covers
    waits. No card is raised. Returns the log entries in memory; the worker writes them."""
    if core is None:
        return Applied(job=job.id)
    asked = {str(r.get("id")): r for r in job.inputs.get("records") or ()
             if isinstance(r, Mapping)}
    index = core.index()
    model = str(answer.get("model") or core.config.understand.judge_model)
    entries: list[Mapping[str, Any]] = []
    notes: list[str] = []
    confirmed: list[Mapping[str, Any]] = []
    corrections: list[Mapping[str, Any]] = []   # the owner's answers correcting a reading
    prompts_known = {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}
    judged: dict[str, str] = {}             # the records judged at their current version
    waits: dict[str, str] = {}              # record id -> why it waits
    rounds: dict[str, tuple[Any, ...]] = {}  # clear set records: (by, auto, answers)
    sent: dict[str, str] = {}               # contradicted by the owner's answer: reworded
    from plumb.capture.spec import escalated_ids

    in_sets = escalated_ids(core)
    for raw in answer.get("verdicts") or ():
        if not isinstance(raw, Mapping) or str(raw.get("id")) not in asked:
            continue
        item = asked[str(raw["id"])]
        verdict = str(raw.get("verdict") or "").lower()
        if verdict not in VERDICTS:
            notes.append(f"no usable verdict for {raw['id']}")
            continue
        beyond, contradicts = _strings(raw.get("beyond")), _strings(raw.get("contradicts"))
        confidence = _confidence(raw.get("confidence"))
        digest = premise.input_digest(item.get("premise") or {})
        record = index.get(item["id"])
        payload = {"job": job.id, "id": item["id"], "hash": item["hash"], "verdict": verdict,
                   "beyond": beyond, "contradicts": contradicts,
                   "score": confidence if verdict == "supported" else 0,
                   "model": str(raw.get("model") or model), "premise_digest": digest}
        payload.update({k: bool(raw[k]) for k in ("clear", "answer_corrects") if k in raw})
        if verdict == "waiting":
            payload["reason"] = _flat(raw.get("reason"))
        given = item.get("premise") or {}
        partial = bool(given.get("messages")) and all(
            m.get("partial") for m in given["messages"])
        if partial and record is not None:    # SR-190: judged on the quote alone
            from plumb.capture.triage import _Prompts, premise_problem

            payload.update(premise="quote-only", premise_reason=premise_problem(
                _Prompts(core), index, record) or "")
        if raw.get("by") in BY:         # SR-182: who answered; a verdict with none is no JEV's
            payload.update(by=raw["by"], judge=str(raw.get("judge") or ""))
        jev = raw.get("jev") if isinstance(raw.get("jev"), Mapping) else None
        if jev is not None:             # JEV's score, logged even when it does not clear
            payload.update(jev_score=jev.get("score"), jev_clears=bool(jev.get("clears")),
                           jev_version=jev.get("model_version"))
            if record is not None and not partial:
                from plumb.capture.triage import _Prompts, premise_problem

                reason = premise_problem(_Prompts(core), index, record)
                if reason:              # SR-248 EX-6: not the owner's verified words
                    payload.update(premise="quote-only", premise_reason=reason)
        current = record is not None and record.hash == item["hash"]
        cited = [str(a["digest"]) for a in given.get("answers") or ()
                 if isinstance(a, Mapping) and a.get("digest")]   # the answers it was shown
        if cited:                       # judged after a question round, on these answers
            payload["answers"] = cited
        entries.append({"kind": "verdict", "payload": payload})
        if not current:
            notes.append(f"{item['id']} changed while it was judged; it is judged again")
            continue
        if given.get("answers") and cited != [e.digest for e in
                                              premise.answer_entries(core, record)]:
            # an answer logged since the job was built queued its own judge job
            notes.append(f"{item['id']} has an answer the judge was not shown; it is judged "
                         "again")
            continue
        judged[record.id] = record.hash
        if cited and payload.get("answer_corrects"):   # SR-252 EX-4: a real 'no' label
            corrections.append(_correction(job, item, record, index, jev, cited))
        if verdict == "waiting":            # SR-267 EX-9: the agent's own doubt asks nothing
            waits[record.id] = payload["reason"] or "the judge could not settle it"
        elif cited and verdict == "contradicts":    # SR-209 EX-2: the agent rewords it
            sent[record.id] = "; ".join(contradicts) or "the owner's answer says otherwise"
        elif cited:                         # SR-248 EX-4, EX-5: approved after the round
            done = _after_round(core, record, raw, payload, jev, record.id in in_sets)
            if done is not None and record.id in in_sets:
                rounds[record.id] = (*done, cited)  # a set is approved whole (P6)
            elif done is not None:
                confirmed += _approve(core, job, [record.id], item, *done, prompts_known,
                                      cited)
        elif (auto := _fast_tracked(core, record, raw, jev)) is not None:
            confirmed += _approve(core, job, [record.id], item, "auto-jev", auto,
                                  prompts_known)    # SR-248: on JEV's score, no question
    for item_id in asked:
        if not any(e["payload"]["id"] == item_id for e in entries):
            notes.append(f"the judge gave no verdict for {item_id}")
    held: dict[str, str] = {}
    if rounds:
        whole, held = _set_approvals(core, job, rounds, asked, prompts_known)
        confirmed += whole
        notes += [f"{i} is clear and waits for its set ({a})" for i, a in held.items()]
    approved = {str(i.get("id")) for e in confirmed if e["kind"] == "approval"
                for i in e["payload"]["records"]}
    shaped, refused = _questions(core, job, answer, {
        i: h for i, h in judged.items()
        if i not in approved | set(waits) | set(held) | set(sent)}, index)
    _write_questions(core, job, set(judged), shaped)
    covered = {i for q in [*shaped, *open_questions(core, job.session)] for i in _ids_of(q)}
    covered |= set(held) | set(sent)
    why = "; ".join(refused) or "the judge asked no question about it"
    waits.update({i: why for i in judged if i not in approved | covered | set(waits)})
    if waits:
        notes.append(_say_waiting(core, job.session, waits))
    if sent:
        notes.append(_sent_back(core, job.session, sent))
    if job.inputs.get("pass") == backlog.PASS:
        notes.extend(backlog.after_job(core, job, verdicts=[
            e["payload"] for e in entries if e["kind"] == "verdict"]).notes)
    kept = _new_pre_intents(core, job.session, [asked[i] for i in judged])
    return Applied(job=job.id, entries=(*entries, *corrections, *kept, *confirmed),
                   notes=tuple(notes))


# --------------------------------------------------------------------------- capture


def queue_for_capture(core: Any, result: Any, *, prompt_digest: str | None = None) -> None:
    """Queue the one judge job that covers every record a capture wrote or changed. The
    worker runs it; nothing here waits for it."""
    if core is None or result is None:
        return None
    ids = [str(i) for i in (*getattr(result, "written", ()), *getattr(result, "updated", ()))]
    session = files.CLI_SESSION
    if prompt_digest:
        from plumb.approvals import Refused, find_prompt

        try:
            session = str(find_prompt(core, prompt_digest).get("session") or session)
        except Refused:
            pass
    job = build(core, session, records=ids)
    if job is None:
        return None
    from plumb.understand import queue

    queue.enqueue(core, job)
    return None


# --------------------------------------------------------------------------- the evaluation set


def system_prompt() -> str:
    try:
        return (HERE / "agents" / "judge.md").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def matches(answer: Mapping[str, Any], expect: Mapping[str, Any]) -> bool:
    """Whether a judge ``answer`` meets a frozen case's ``expect``: every expected record has
    the expected verdict and, for ``beyond``, names each of the expected mentions
    (``beyond_mentions``, matched as case-insensitive words in what it says goes beyond)."""
    got = {str(v.get("id")): v for v in answer.get("verdicts") or () if isinstance(v, Mapping)}
    for wanted in expect.get("verdicts") or ():
        found = got.get(str(wanted.get("id")))
        if found is None or str(found.get("verdict")) != str(wanted.get("verdict")):
            return False
        said = " ".join(_strings(found.get("beyond"))).lower()
        if any(str(m).lower() not in said for m in wanted.get("beyond_mentions") or ()):
            return False
    return True


def evaluate_case(dispatcher: Any, case: Mapping[str, Any]) -> tuple[bool, Mapping[str, Any]]:
    """Run one frozen case through ``dispatcher`` as the worker would (the agent prompt, the
    inputs as the user message) and compare the answer with the case's ``expect``."""
    inputs = dict(case.get("inputs") or {})
    job = Job(id=f"eval-judge-{case.get('name', '')}", kind=kind, schema=SCHEMA_ID,
              inputs=inputs)
    answer = dict(dispatcher.run(job, system=system_prompt(), user=json.dumps(inputs),
                                 schema=schema, on_step=lambda step: None))
    return matches(answer, case.get("expect") or {}), answer


# --------------------------------------------------------------------------- the cards' effects


def _beyond_effect(*, entry: Mapping[str, Any], accepted: bool = False, confirm: Any = None,
                   **_: Any) -> Applied | None:
    """A "goes beyond your words" card answered: keeping it confirms the record the owner
    has now seen with the addition; dropping or rewording confirms nothing (the reader's
    ``rejected`` and ``change`` answers do the rest)."""
    if accepted and entry.get("record") and entry.get("hash") and confirm is not None:
        confirm(str(entry["record"]), str(entry["hash"]), str(entry.get("evidence") or ""),
                float(entry.get("confidence") or 0))
    return None


def _contradicts_effect(**_: Any) -> Applied | None:
    """A contradicts card answered: the reader maps the owner's pick to a change of the
    record; nothing is confirmed by a bare yes."""
    return None


def _register() -> None:
    from plumb.understand import effects

    effects.register("trial", trial.effect)
    effects.register("beyond", _beyond_effect)
    effects.register("contradicts", _contradicts_effect)


_register()
