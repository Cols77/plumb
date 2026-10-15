"""The judge job kind (JUDGE, SR-102, spec 4.2).

A model independent of the coding agent is asked, for every record a capture wrote or changed
(one job per capture) or the backlog pass covers (one job per intent): *would the owner object
to this record, given their words?* The record's premise is the owner's whole logged message or
messages (``understand.premise``), the stored question for a short answer, and the parent
intent when the owner confirmed it, next to the owner's confirmed records it
relates to. Labelled assumptions are shown and left out of what is judged.

``apply`` logs one ``verdict`` per record (the score is the model's confidence for
``supported``, 0 otherwise), puts a line on the request's open read-back card for ``beyond``
and ``contradicts`` (SR-152: the next read-back drawn when none is open), and gives
``supported`` to the trial, which asks the owner (nothing is confirmed from a verdict alone). It
only returns what to write: the worker writes it. The kind registers the handlers of the trial,
beyond and contradicts cards (``effects``; old cards of those kinds are still answered)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, CardState, Job
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
VERDICTS = ("supported", "beyond", "contradicts")


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


def _request_card(index: Mapping[str, Any], record: Any) -> str:
    """The id of the read-back card of the request ``record`` came from ('' when unknown)."""
    from plumb.understand import clarify

    seen: set[str] = set()
    todo = [record]
    while todo:
        r = todo.pop()
        if r.id in seen:
            continue
        seen.add(r.id)
        said = str(r.fields.get("prompt") or "")
        if r.kind == "intent" and len(said) >= 12:
            return clarify.card_id(said)
        todo += [index[link.target.record] for link in r.links
                 if link.kind in ("derives_from", "decides") and link.target.record in index]
    return ""


def doubt_line(index: Mapping[str, Any], record: Any, verdict: str,
               related: Sequence[Any] = (), contradicts: Sequence[str] = ()) -> str:
    """SR-152: the one line a ``beyond`` or ``contradicts`` verdict adds to a read-back."""
    if verdict == "beyond":
        return owner_text.DOUBT_BEYOND.format(title=record.title)
    named = [str(r.get("id")) for r in related if isinstance(r, Mapping)
             and str(r.get("id")) in index and any(
                 re.search(rf"\b{re.escape(str(r.get('id')))}\b", c) for c in contradicts)]
    other = index[named[0]] if named else None      # the record the judge named, not the first
    if other is None:
        return owner_text.DOUBT_CONTRADICTS_UNNAMED.format(title=record.title)
    return owner_text.DOUBT_CONTRADICTS.format(title=record.title, other=other.title)


def pending_lines(core: Any, session: str, card: str) -> list[str]:
    """The doubt lines of the session's judged records of the request whose read-back is
    ``card`` that no card carries yet (still unconfirmed, still as judged)."""
    from plumb import log
    from plumb.understand import cardstore, jobs

    root = Path(core.root)
    judged = {j.id: j for j in jobs.queued(root, session) if j.kind == kind}
    shown = "\n".join(c.evidence for c in cardstore.own_cards(root, session))
    index = core.index()
    out: list[str] = []
    for entry in log.read(core.paths, "events", ["verdict"]):
        p = entry.payload
        job = judged.get(str(p.get("job")))
        record = index.get(str(p.get("id")))
        if (job is None or record is None or record.hash != p.get("hash")
                or _request_card(index, record) != card
                or p.get("verdict") not in ("beyond", "contradicts")
                or core.status([record.id])[record.id].confirmation == "confirmed"):
            continue
        item = next((r for r in job.inputs.get("records") or () if r.get("id") == record.id), {})
        line = doubt_line(index, record, str(p["verdict"]), item.get("related") or (),
                          _strings(p.get("contradicts")))
        if line not in shown and line not in out:
            out.append(line)
    return out


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    """Log the verdicts; add the doubt lines to the read-back cards; give the supported records to the trial.
    Returns it in memory; the worker writes it."""
    if core is None:
        return Applied(job=job.id)
    asked = {str(r.get("id")): r for r in job.inputs.get("records") or ()
             if isinstance(r, Mapping)}
    index = core.index()
    model = str(answer.get("model") or core.config.understand.judge_model)
    entries: list[Mapping[str, Any]] = []
    new_cards: list[CardState] = []
    notes: list[str] = []
    supported: list[trial.Candidate] = []
    fragments: list[Any] = []
    backlog_pass = job.inputs.get("pass") == backlog.PASS
    doubts: dict[str, list[str]] = {}       # read-back card id -> lines
    flagged: list[str] = []                 # every doubt line, for the backlog's end line
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
        given = item.get("premise") or {}
        partial = bool(given.get("messages")) and all(
            m.get("partial") for m in given["messages"])
        if partial and record is not None:    # SR-190: judged on the quote alone
            from plumb.capture.triage import _Prompts, premise_problem

            payload.update(premise="quote-only", premise_reason=premise_problem(
                _Prompts(core), index, record) or "")
        if raw.get("by") in BY:         # SR-182: who answered; a verdict with none is no JEV's
            payload.update(by=raw["by"], judge=str(raw.get("judge") or ""))
        entries.append({"kind": "verdict", "payload": payload})
        if record is None or record.hash != item["hash"]:
            notes.append(f"{item['id']} changed while it was judged; it is judged again")
            continue
        if backlog_pass and partial:
            fragments.append(record)        # the owner's words are not on file: one card says so
        elif verdict in ("beyond", "contradicts"):
            line = doubt_line(index, record, verdict, item.get("related") or (), contradicts)
            doubts.setdefault(_request_card(index, record), []).append(line)
            flagged.append(line)
        else:
            supported.append(trial.Candidate(record, confidence, item["premise"], ""))
    for item_id in asked:
        if not any(e["payload"]["id"] == item_id for e in entries):
            notes.append(f"the judge gave no verdict for {item_id}")
    if backlog_pass:
        done = backlog.after_job(core, job, supported=supported,
                                 verdicts=[e["payload"] for e in entries
                                           if e["kind"] == "verdict"],
                                 fragments=fragments, flagged=flagged)
        new_cards.extend(done.cards)
        notes.extend(done.notes)
    else:
        new_cards.extend(trial.cards_for(core, job.session, supported))
    if doubts:
        from dataclasses import replace

        from plumb.understand import cardstore

        for card in cardstore.own_cards(Path(core.root), job.session):
            more = [d for d in doubts.get(card.id, ()) if d not in card.evidence.splitlines()]
            if card.kind == "clarify" and card.status in cardstore.AWAITING and more:
                new_cards.append(replace(card, evidence="\n".join(
                    [*([card.evidence] if card.evidence else []), *more])))
    return Applied(job=job.id, cards=tuple(new_cards), entries=tuple(entries),
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
