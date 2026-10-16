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
(SR-245). No trial or read-back card is raised (SR-252 EX-6). It returns the log entries: the
worker writes them. The kind registers the handlers of the trial, beyond and contradicts
cards (``effects``; old cards of those kinds are still answered)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
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
HEADER_MAX = 12          # the question tool's chip
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


schema: Mapping[str, Any] = _load_schema()


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
    """The inputs rebuilt from the logs, as they stand when the worker runs the job."""
    if core is None:
        return None
    ids = [str(r.get("id")) for r in job.inputs.get("records") or () if isinstance(r, Mapping)]
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


def _auto_jev(core: Any, job: Job, record: Any, item: Mapping[str, Any],
              auto: Mapping[str, Any], known: set[Any]) -> list[Mapping[str, Any]]:
    """The ``by: auto-jev`` approval of ``record`` (written by the worker, carrying the
    session), after the prompt event it cites when none is logged yet."""
    messages = [m for m in (item.get("premise") or {}).get("messages") or ()
                if isinstance(m, Mapping) and m.get("digest")]
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
    out.append({"kind": "approval", "payload": {
        "records": approval_items(core, [record.id]), "by": "auto-jev",
        "prompt_digest": digest, "quote": None, "quote_digest": None,
        "session": job.session, "job": job.id, "auto": dict(auto)}})
    return out


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


def open_questions(core: Any, session: str) -> list[Mapping[str, Any]]:
    """The judge questions still waiting for the owner: not answered yet (no question-answer
    entry with the same key), and asking about a record still unconfirmed at the version
    asked."""
    asked = _logged_questions(core.root, session)
    if not asked:
        return []
    index, statuses = core.index(), core.status()
    answered = {question_key(str(e.payload.get("question") or "")) for e in core.events()
                if e.kind == "question-answer" and e.payload.get("session") == session}
    return [q for q in asked if q.get("key") not in answered and any(
        str(r.get("id")) in index and index[str(r.get("id"))].hash == r.get("hash")
        and statuses[str(r.get("id"))].confirmation != "confirmed"
        for r in q.get("records") or () if isinstance(r, Mapping))]


def _shaped(raw: Any, job: Job, judged: Mapping[str, str], index: Mapping[str, Any]
            ) -> tuple[dict[str, Any] | None, str]:
    """A judge question as the question tool shows it, or ``(None, why it waits)`` (SR-245
    EX-7, SR-267 EX-4): its request folded into the question, the reason into the recommended
    option; record numbers in the owner's terms; plumb's own words never shown."""
    if not isinstance(raw, Mapping):
        return None, "a question is out of schema"
    ids = [i for i in dict.fromkeys(str(r) for r in raw.get("records") or ()) if i in judged]
    options = [o for o in raw.get("options") or () if isinstance(o, Mapping)]
    request = raw.get("request") if isinstance(raw.get("request"), Mapping) else {}
    words, date = _flat(request.get("words")), _flat(request.get("date"))
    shown = [cards.plain(_flat(v), index) for v in (
        raw.get("question"), raw.get("header"), raw.get("recommended_reason"),
        *(o.get(k) for o in options for k in ("label", "consequence")))]
    if not ids or not words or not 2 <= len(options) <= 4 or not all(shown):
        return None, ("a question lacks its records, the request, two to four options, their "
                      "consequences or the reason for the recommended one")
    if any(_PLUMB_WORDS.search(t) or _LEFT_IN.search(t) for t in shown):
        return None, "a question names plumb's own words"
    text, header, reason, *rest = shown
    said = f'You said on {date}: "{words}"' if date else f'You said: "{words}"'
    question = f"{text}\n\n{said}"
    pairs = list(zip(rest[::2], rest[1::2], strict=True))
    return {"key": question_key(question), "job": job.id,
            "records": [{"id": i, "hash": judged[i]} for i in ids],
            "question": question, "header": header[:HEADER_MAX].strip(),
            "options": [{"label": f"{label} (Recommended)" if n == 0 else label,
                         "description": f"{consequence} Recommended: {reason}" if n == 0
                         else consequence}
                        for n, (label, consequence) in enumerate(pairs)]}, ""


def _questions(job: Job, answer: Mapping[str, Any], judged: Mapping[str, str],
               index: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """The judge's questions shaped for the owner, and why the others wait."""
    shaped: list[dict[str, Any]] = []
    why: list[str] = []
    for raw in answer.get("questions") or ():
        made, reason = _shaped(raw, job, judged, index)
        if made is None:
            why.append(reason)
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
    prompts_known = {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}
    judged: dict[str, str] = {}             # the records judged at their current version
    waits: dict[str, str] = {}              # record id -> why it waits
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
            payload.update(jev_score=jev.get("score"), jev_clears=bool(jev.get("clears")))
            if record is not None and not partial:
                from plumb.capture.triage import _Prompts, premise_problem

                reason = premise_problem(_Prompts(core), index, record)
                if reason:              # SR-248 EX-6: not the owner's verified words
                    payload.update(premise="quote-only", premise_reason=reason)
        entries.append({"kind": "verdict", "payload": payload})
        if record is None or record.hash != item["hash"]:
            notes.append(f"{item['id']} changed while it was judged; it is judged again")
            continue
        judged[record.id] = record.hash
        auto = _fast_tracked(core, record, raw, jev)
        if auto is not None:                # SR-248: approved on JEV's score, no question
            confirmed += _auto_jev(core, job, record, item, auto, prompts_known)
        elif verdict == "waiting":          # SR-267 EX-9: the agent's own doubt asks nothing
            waits[record.id] = payload["reason"] or "the judge could not settle it"
    for item_id in asked:
        if not any(e["payload"]["id"] == item_id for e in entries):
            notes.append(f"the judge gave no verdict for {item_id}")
    approved = {str(i.get("id")) for e in confirmed if e["kind"] == "approval"
                for i in e["payload"]["records"]}
    shaped, refused = _questions(job, answer, {
        i: h for i, h in judged.items() if i not in approved and i not in waits}, index)
    _write_questions(core, job, set(judged), shaped)
    covered = {i for q in [*shaped, *open_questions(core, job.session)] for i in _ids_of(q)}
    why = "; ".join(refused) or "the judge asked no question about it"
    waits.update({i: why for i in judged if i not in approved | covered | set(waits)})
    if waits:
        notes.append(_say_waiting(core, job.session, waits))
    if job.inputs.get("pass") == backlog.PASS:
        notes.extend(backlog.after_job(core, job, verdicts=[
            e["payload"] for e in entries if e["kind"] == "verdict"]).notes)
    return Applied(job=job.id, entries=(*entries, *confirmed), notes=tuple(notes))


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
