"""``plumb clarify --wait`` (SHOW S3): the agent's first action on an owner request.

It returns the clarify result for the owner's latest message: it waits up to the timeout
(``understand.clarify_wait_s``, 45 s) for the check the prompt hook queued, or runs the check
itself when none was queued (same inputs, same id, so it never runs twice). A late result
after a timeout is collected by the next ``--wait``. Nothing here opens the
gate: only the check's own result, the owner's answers, or the owner's release do.

An ordinary message is not checked and waits for nothing (SR-378): ``--wait`` hands the judge
jobs queued since the owner last spoke to the detached worker and answers at once, ``ask`` with
the judge's open questions already in the store (SR-248), or ``ready`` with what the judge
approved on the owner's behalf. The questions never close the gate; a request the prompt hook
held on a confirmed record answers ``held``.

Without ``--wait`` the command is today's clarification-depth helper, unchanged."""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Job, JobResult
from plumb.present import owner_text
from plumb.understand import clarify, files, gate

POLL_S = 0.05
WHY_BY_STEP = {
    "dispatch": "no model is available to check it",
    "timeout": "the model took too long",
    "schema": "the model's answer could not be used",
    "needs": "reading your last answer failed first",
    "run": "the model could not be reached",
}
WHY_DEFAULT = "the check failed"
# the check finished, yet the gate stays closed with no question: nothing will change by waiting
WHY_UNSETTLED = "the check finished without a question or a go-ahead"
READY = "Nothing in your request needs asking. You can start building."
SHOW_COULDNT = ("The check of the request could not be made ({why}). Say so once in one line and "
                "work on; nothing is held.")
SHOW_STILL_CHECKING = ("The check of the request is still running. Build nothing yet and run "
                       "clarify --wait again.")
WAITING = "The check of your request is not finished. Do not build yet."
ASK_QUESTIONS = ("Ask these {n} questions with the question tool, all at once, now: put each in "
                 "the owner's terms with `plumb question reword`, merging those on one principle; "
                 "never drop, answer or default one. Each question's `key` is what it takes.")
REWORD_FIRST = ("{n} of them use plumb's own words (`reword: true`): reword those before asking, "
                "with no record id or plumb term.")
UNMATCHED = "Ask these questions as given; the last answer matched none of them."
JUDGING = ("plumb's judge is still reading the records in the background; go on with the "
           "work: its questions reach you as text.")
APPROVED = "approved on your behalf: {title} (judge-approved, {by}, {score})"
HELD = ("plumb: edits are held ({reason}): this request changes a confirmed record and no "
        "intent loop ran for it. /plumb intent opens the loop; the owner's /plumb go releases.")


@dataclasses.dataclass
class Outcome:
    state: str           # ready | ask | couldnt_check | waiting | held
    digest: str = ""
    lines: list[str] = dataclasses.field(default_factory=list)
    questions: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        shown = {"questions": self.questions} if self.state == "ask" else {}
        return {"state": self.state, "message_digest": self.digest,
                "lines": self.lines, **shown}


_BARE_COMMAND = re.compile(r"/\S+")


def latest_prompt(core: Any, session: str | None) -> Mapping[str, Any] | None:
    """The newest owner message of the session (any session when none is named). A bare slash
    command (``/reload-plugins``) is no message of the owner's request: it never hides the
    typed ``/plumb intent`` before it from ``intent open`` and ``--wait``."""
    from plumb.approvals import is_owner_entry

    newest: Mapping[str, Any] | None = None
    import json

    for line in core.paths.prompt_lines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, Mapping) and entry.get("digest") and is_owner_entry(entry) \
                and (session is None or entry.get("session") == session) \
                and not clarify.is_typed_go(str(entry.get("text") or "")) \
                and not _BARE_COMMAND.fullmatch(str(entry.get("text") or "").strip()):
            newest = entry
    return newest


def _jobs_of(root: Path, session: str, kind: str, digest: str) -> list[Job]:
    found: list[Job] = []
    folder = files.jobs_dir(root, session)
    for path in sorted(folder.glob(f"{kind}-*.json")) if folder.is_dir() else ():
        raw = files.read_json(path)
        if not isinstance(raw, Mapping):
            continue
        job = files.job_from_json(raw)
        message = job.inputs.get("message")
        if isinstance(message, Mapping) and message.get("digest") == digest:
            found.append(job)
    return found


def _since(core: Any, session: str, logged: Mapping[str, Any]) -> str:
    """When the owner last spoke in the session: their latest message or question-tool answer."""
    answers = [e.at for e in core.events()
               if e.kind == "question-answer" and e.payload.get("session") == session]
    return max([str(logged.get("at") or ""), *answers])


def _judge_jobs_since(root: Path, session: str, at: str) -> list[Job]:
    """The session's judge jobs queued since ``at``, whatever their records."""
    from plumb.understand import jobs

    return [j for j in jobs.queued(root, session) if j.kind == "judge"
            and j.created >= at]


def _read_jobs_of(root: Path, session: str, digest: str) -> list[Job]:
    """The read jobs of the owner's message ``digest`` (queued by the prompt hook)."""
    from plumb.understand import jobs

    return [j for j in jobs.queued(root, session) if j.kind == "read"
            and isinstance(j.inputs.get("message"), Mapping)
            and j.inputs["message"].get("digest") == digest]


def _approved(core: Any, at: str) -> list[str]:
    """One line per record the judge approved on the owner's behalf since ``at``, by title."""
    index = core.index()
    out: list[str] = []
    for entry in core.events():
        p = entry.payload
        if entry.kind != "approval" or entry.at < at or p.get("by") not in ("auto-jev",
                                                                           "auto-model"):
            continue
        auto = p.get("auto") if isinstance(p.get("auto"), Mapping) else {}
        score = auto.get("score", auto.get("confidence"))
        for item in p.get("records") or ():
            record = index.get(str(item.get("id"))) if isinstance(item, Mapping) else None
            if record is not None:
                out.append(APPROVED.format(title=record.title, by=p["by"], score=score))
    return out


def _by_principle(questions: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """SR-361: every blocking question (even several on one principle), then one question per
    other principle, every principle, the biggest first: no limit per turn."""
    def principle(q: Mapping[str, Any]) -> str:
        return str(q.get("principle") or q.get("key"))

    blocking = [q for q in questions if q.get("blocking")]
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for q in questions:
        if not q.get("blocking") and principle(q) not in map(principle, blocking):
            groups.setdefault(principle(q), []).append(q)
    ordered = sorted(groups.values(), key=lambda g: -len(g))
    return [*blocking, *(g[0] for g in ordered)]


def _open_questions(core: Any, session: str) -> list[Mapping[str, Any]]:
    """SR-223 EX-15: the clarifier's blocking gaps, every one, then the judge's questions
    (one per principle, SR-361): all asked at once with the question tool, never as prose."""
    from plumb.understand import judge

    gaps = clarify.gap_questions(core, session)
    keys = {g["key"] for g in gaps}
    return [*gaps, *(q for q in _by_principle(judge.to_ask(core, session))
                     if q.get("key") not in keys)]


def _options(root: Path, question: Mapping[str, Any]) -> list[Any]:
    """SR-336 EX-1: a question a study serves offers to study it first, last and within the
    tool's four options (one study option at most)."""
    from plumb import study

    options = list(question.get("options") or ())
    if study.serving(root, str(question.get("key"))):
        extra = {"label": owner_text.STUDY_FIRST, "description": owner_text.STUDY_FIRST_NOTE}
    else:
        return options
    return [*options[:3], extra]


def _judged(core: Any, session: str, digest: str, at: str, turn: str = "") -> Outcome:
    """SR-378: answers at once and runs no job: the judge jobs queued since the owner last
    spoke go to the detached worker; ``ask`` with the questions already in the store, else
    ``ready`` with what the judge approved (and a line while jobs still run). The questions
    never close the gate (P6). SR-361: every open question is asked, one per principle."""
    from plumb.understand import judge, worker

    root = Path(core.root)
    since = _judge_jobs_since(root, session, at)
    pending = [j for j in since if result_of(root, session, j.id) is None]
    if pending:
        worker.start_detached(root, session)
    said = [e for e in core.events() if e.kind == "question-answer"
            and e.payload.get("session") == session and e.at >= (turn or at)]
    questions = _open_questions(core, session)   # SR-336 EX-2: less study-held
    failed = [j for j in since if j.kind == "judge"    # a failed push-back keeps the question
              and (r := result_of(root, session, j.id)) is not None and r.status == "error"]
    if failed and not any(q.get("job") in {j.id for j in since} for q in questions):
        # the judge could not read the owner's latest message: what it asked before may be
        # answered by it, so it is not asked again; nothing is held (SR-378 EX-4)
        questions = []
    if questions:
        return _ask(core, session, digest, questions, [e.payload for e in said if e.at >= at])
    return Outcome("ready", digest, [READY, *([JUDGING] if pending else []),
                                     *_approved(core, at)])


def _ask(core: Any, session: str, digest: str, questions: list[Mapping[str, Any]],
         answers: list[Mapping[str, Any]]) -> Outcome:
    from plumb.understand import judge

    root = Path(core.root)
    # SR-212: the agent reworded the question, or asked one of its own; SR-362: a wording
    # it registered (``plumb question reword``) is matched
    worded = {w.get("key") for w in judge.reworded(root, session)}
    missed = bool(answers) and answers[-1].get("via") == "question-tool" \
        and not any(answers[-1].get(k) for k in ("asked", "study")) \
        and judge.question_key(str(answers[-1].get("question") or "")) not in worded
    line = UNMATCHED if missed else ASK_QUESTIONS.format(n=len(questions))
    plumbish = sum(1 for q in questions if q.get("reword"))
    return Outcome("ask", digest, [line, *([REWORD_FIRST.format(n=plumbish)] if plumbish
                                           else [])], questions=[
        {"key": q.get("key"), "reword": bool(q.get("reword")),
         "question": q.get("question"), "header": q.get("header"),
         "options": _options(root, q), "multiSelect": False} for q in questions])


def _with_asks(core: Any, session: str, outcome: Outcome) -> Outcome:
    """A commanded check that comes out ``ready`` still hands over the judge's open questions:
    the ask gate (SR-361 EX-6) holds edits until the agent has asked them."""
    from plumb.api import open_core
    from plumb.understand import judge

    if outcome.state != "ready":
        return outcome
    questions = _open_questions(open_core(Path(core.root)), session)
    return _ask(core, session, outcome.digest, questions, []) if questions else outcome


def result_of(root: Path, session: str, job_id: str) -> JobResult | None:
    """The result the worker wrote for the job: a result with no ledger entry was not
    written by the worker and counts for nothing."""
    if not (files.ran_dir(root, session) / job_id).exists():
        return None
    raw = files.read_json(files.results_dir(root, session) / f"{job_id}.json")
    return files.result_from_json(raw) if isinstance(raw, Mapping) else None


def why_failed(result: JobResult) -> str:
    step = result.error.step if result.error else ""
    return WHY_BY_STEP.get(step, WHY_DEFAULT)


def _outcome_from_state(core: Any, session: str, digest: str) -> Outcome:
    root = Path(core.root)
    if gate.state(root, session).state == "open":
        return Outcome("ready", digest, [READY])
    reason = gate.state(root, session).reason
    if reason.startswith(gate.INTENT_CHANGE):   # SR-225: the check found a request that changes
        return Outcome("held", digest, [HELD.format(reason=reason)])   # a confirmed record
    return Outcome("waiting", digest, [WAITING])


def _couldnt(core: Any, session: str, digest: str, why: str) -> Outcome:
    if why == clarify.COULDNT_TIMEOUT:   # the check still runs: its result may yet hold
        return Outcome("couldnt_check", digest, [SHOW_STILL_CHECKING])
    clarify.write_couldnt_check(core, session, digest)   # SR-225 EX-9: a failure holds nothing
    return Outcome("couldnt_check", digest, [SHOW_COULDNT.format(why=why)])


def wait(core: Any, session: str | None = None, *, timeout: float | None = None,
         stream: Any = None, sleep: Callable[[float], None] = time.sleep,
         clock: Callable[[], float] = time.monotonic) -> Outcome:
    """Collect the clarify result of the owner's latest message (see the module doc)."""
    from plumb.progress import Reporter
    from plumb.stale import SESSION_ENV, current_session
    from plumb.understand import worker

    root = Path(core.root)
    # SR-169: this session's message, never the newest of whichever session logged last
    if session is None and any(os.environ.get(name) for name in SESSION_ENV):
        session = current_session(root)
    logged = latest_prompt(core, session)
    if logged is None:
        return Outcome("ready", "", [READY])
    session = str(logged.get("session") or session or "default")
    digest = str(logged["digest"])
    limit = float(timeout if timeout is not None else core.config.understand.clarify_wait_s)
    if clarify.commanded_words(str(logged.get("text") or "")) is None:
        # SR-171: no commanded check of this message; one still holding the gate keeps its digest
        held = gate.state(root, session)
        if not gate.is_closed(root, session) or not held.message_digest:
            return _judged(core, session, digest, _since(core, session, logged),
                           str(logged.get("at") or ""))
        digest = held.message_digest
        if held.reason.startswith(gate.INTENT_CHANGE):   # SR-378 EX-3: the prompt hook held it;
            return _outcome_from_state(core, session, digest)   # no check runs for it
    if gate.state(root, session).message_digest != digest and not gate.is_closed(root, session):
        gate.close(root, session, digest, clarify.GATE_REASON_CHECKING)   # no hook closed it
    if not gate.is_closed(root, session):
        return _with_asks(core, session, _outcome_from_state(core, session, digest))
    sent = clarify.sent_at(core, digest)   # each sending of the same words has its own check
    queued = [j for j in _jobs_of(root, session, "clarify", digest)
              if j.inputs["message"].get("at", "") == sent]
    ours = queued[-1] if queued else None
    started = clock()
    reporter = Reporter(root, None, "clarify", stream=stream)
    if ours is None:
        read = _jobs_of(root, session, "read", digest)
        ours = clarify.build(core, session, message={
            "digest": digest, "text": str(logged.get("text") or "")},
            after=read[-1].id if read else None)
        if ours is None:
            return _with_asks(core, session, Outcome("ready", digest, [READY]))
        reporter.update(owner_text.STEP_CHECKING)
        if result_of(root, session, ours.id) is None:
            worker.run_once(core, session, ours.id)
    else:
        worker.start_detached(root, session)
    shown_at = clock()
    while True:
        result = result_of(root, session, ours.id)
        if result is not None:
            if result.status == "ok":
                outcome = _outcome_from_state(core, session, digest)
                if outcome.state != "waiting":
                    reporter.done()
                    return _with_asks(core, session, outcome)
                # the result is in but not applied yet (the worker applies it next): poll on,
                # and once the limit passes say so instead of "waiting", which a re-run would
                # answer again for ever (the skill runs --wait again on waiting)
                if clock() - started >= limit:
                    reporter.failed(owner_text.STEP_CHECKING)
                    return _couldnt(core, session, digest, WHY_UNSETTLED)
                sleep(POLL_S)
                continue
            reporter.failed(owner_text.STEP_CHECKING)
            return _couldnt(core, session, digest, why_failed(result))
        if clock() - started >= limit:
            reporter.failed(owner_text.STEP_CHECKING)
            return _couldnt(core, session, digest, clarify.COULDNT_TIMEOUT)
        if clock() - shown_at >= 0.5:
            shown_at = clock()
            reporter.update(owner_text.STEP_CHECKING)
        sleep(POLL_S)


def run(command: str, argv: list[str]) -> int:
    if "--wait" not in argv:
        from plumb.capture import cli as capture_cli

        return int(capture_cli.run(command, argv) or 0)
    from plumb.cliutil import add_common, emit, resolve_root

    parser = argparse.ArgumentParser(
        prog="plumb clarify --wait",
        description="Collect the check of the owner's latest request: waits for it, or runs "
                    "it when none was queued.")
    add_common(parser)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout", type=float, default=None,
                        help="seconds to wait (default: understand.clarify_wait_s)")
    parser.add_argument("--session", default=None)
    args = parser.parse_args(argv)
    from plumb.api import open_core

    core = open_core(resolve_root(args.root))
    stream = sys.stderr
    outcome = wait(core, args.session, timeout=args.timeout, stream=stream)
    emit(outcome.as_json() if args.as_json else outcome.lines, args.as_json)
    return 0
