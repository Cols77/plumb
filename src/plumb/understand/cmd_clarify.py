"""``plumb clarify --wait`` (SHOW S3): the agent's first action on an owner request.

It returns the clarify result for the owner's latest message: it waits up to the timeout
(``understand.clarify_wait_s``, 45 s) for the check the prompt hook queued, or runs the check
itself when none was queued (same inputs, same id, so it never runs twice). A late result
after a timeout is collected by the next ``--wait``; a timeout or a failed check puts the
"couldn't check" card in the card store and keeps the gate closed. Nothing here opens the
gate: only the check's own result, the owner's answers, or the owner's release do.

An ordinary message is not checked: ``--wait`` collects the judge jobs queued since the owner
last spoke and answers ``ask`` with the judge's open questions for the question tool (SR-248),
or ``ready`` with what the judge approved on the owner's behalf. The questions never close the
gate.

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
from plumb.understand import cardstore, clarify, files, gate

POLL_S = 0.05
WHY_BY_STEP = {
    "dispatch": "no model is available to check it",
    "timeout": "the model took too long",
    "schema": "the model's answer could not be used",
    "needs": "reading your last answer failed first",
    "run": "the model could not be reached",
}
WHY_DEFAULT = "the check failed"
# the check finished, yet the gate stays closed with no card: nothing will change by waiting
WHY_UNSETTLED = "the check finished without a question or a go-ahead"
READY = "Nothing in your request needs asking. You can start building."
ASK = ("The owner has this one question on a card. Say in one line that it waits there; do "
       "not restate it or its options; build nothing until they answer; plumb reads their "
       "answer from their next message.")
DRAW = ("Draw the answer space with the diagram:architecture-diagram skill into {path}. "
        "The question: {question} The options: {options}. (For the drawing only; do not "
        "repeat them in your reply.)")
BUILD_ON = "Build on this; tell the owner in one line what you assumed:"
SHOW_COULDNT = ("The check could not be made and the owner has a card offering to build anyway or "
                "wait. Say so in one line; nothing was built, and nothing is built until they "
                "say to build anyway.")
WAITING = "The check of your request is not finished. Do not build yet."
ASK_QUESTIONS = ("Ask these {n} questions with the question tool, one at a time, as given: each "
                 "question, header and option label and description verbatim.")
UNMATCHED = "Ask these questions as given; the last answer matched none of them."
JUDGING = ("plumb's judge is still reading the records; go on with the work and run clarify "
           "--wait again before the turn ends.")
APPROVED = "approved on your behalf: {title} (judge-approved, {by}, {score})"
ASKED_PER_TURN = 3      # SR-334
ROOM_TEXT_MAX = 600     # SR-333: a question longer than this has more to see than the tool holds
HELD = ("plumb: edits are held ({reason}): this request changes a confirmed record and no "
        "intent loop ran for it. /plumb intent opens the loop; the owner's /plumb go releases.")


@dataclasses.dataclass
class Outcome:
    state: str           # ready | ask | card | escalation | couldnt_check | waiting | held
    digest: str = ""
    lines: list[str] = dataclasses.field(default_factory=list)
    card: str = ""
    questions: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        shown = {"questions": self.questions} if self.state == "ask" else {}
        return {"state": self.state, "message_digest": self.digest, "card": self.card,
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

    return [j for j in jobs.queued(root, session) if j.kind == "judge" and j.created >= at]


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


def _by_principle(questions: list[Mapping[str, Any]], room: int) -> list[Mapping[str, Any]]:
    """SR-334: every blocking question (even several on one principle), then one question per
    other principle while ``room`` (the blocking ones count) lasts, the biggest first."""
    def principle(q: Mapping[str, Any]) -> str:
        return str(q.get("principle") or q.get("key"))

    blocking = [q for q in questions if q.get("blocking")]
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for q in questions:
        if not q.get("blocking") and principle(q) not in map(principle, blocking):
            groups.setdefault(principle(q), []).append(q)
    ordered = sorted(groups.values(), key=lambda g: -len(g))
    return [*blocking, *(g[0] for g in ordered[:max(room - len(blocking), 0)])]


def _options(root: Path, question: Mapping[str, Any]) -> list[Any]:
    """SR-333 EX-1, EX-2: a question with more to see (a diagram, or a text over
    ``ROOM_TEXT_MAX``) offers to study it in the room, last and within the tool's four options
    (the room shows every option). SR-336 EX-1: a question a study serves offers to study it
    first instead (one study option at most)."""
    from plumb import study

    options = list(question.get("options") or ())
    if study.serving(root, str(question.get("key"))):
        extra = {"label": owner_text.STUDY_FIRST, "description": owner_text.STUDY_FIRST_NOTE}
    elif question.get("diagram") or len(str(question.get("question") or "")) > ROOM_TEXT_MAX:
        extra = {"label": owner_text.ROOM_STUDY, "description": owner_text.ROOM_STUDY_NOTE}
    else:
        return options
    return [*options[:3], extra]


def _judged(core: Any, session: str, digest: str, at: str, limit: float,
            sleep: Callable[[float], None], clock: Callable[[], float], turn: str = "",
            mid_task: bool = False) -> Outcome:
    """SR-248: the judge jobs queued since the owner last spoke, collected: ``waiting`` while
    one runs past the limit, ``ask`` while its questions are open, else ``ready`` with what the
    judge approved. The questions never close the gate (P6). SR-334: one question per
    principle, at most ``ASKED_PER_TURN`` answered since the owner's message (``turn``) but
    the blocking ones; ``mid_task``, the blocking ones only."""
    from plumb import study
    from plumb.api import open_core
    from plumb.understand import judge, worker

    root = Path(core.root)
    started, ran = clock(), False
    while pending := [j for j in _judge_jobs_since(root, session, at)
                      if result_of(root, session, j.id) is None]:
        if not ran:
            for job in pending:
                worker.run_once(core, session, job.id)
            ran = True
            continue
        if clock() - started >= limit:
            return Outcome("waiting", digest, [JUDGING])
        sleep(POLL_S)
    core = open_core(root)          # a detached worker may have written meanwhile
    said = [e for e in core.events() if e.kind == "question-answer"
            and e.payload.get("session") == session and e.at >= (turn or at)]
    room = 0 if mid_task else ASKED_PER_TURN - sum(1 for e in said if e.payload.get("asked"))
    later = study.first_keys(root, session)       # SR-336 EX-2: they wait for the study
    questions = _by_principle([q for q in judge.open_questions(core, session)
                               if q.get("key") not in later], room)
    if questions:
        answers = [e.payload for e in said if e.at >= at]
        # SR-212: the agent reworded the question, or asked one of its own
        missed = bool(answers) and answers[-1].get("via") == "question-tool" \
            and not any(answers[-1].get(k) for k in ("asked", "room", "study"))
        line = UNMATCHED if missed else ASK_QUESTIONS.format(n=len(questions))
        return Outcome("ask", digest, [line], questions=[
            {"question": q.get("question"), "header": q.get("header"),
             "options": _options(root, q), "multiSelect": False} for q in questions])
    return Outcome("ready", digest, [READY, *_approved(core, at)])


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
    cards = {c.id: c for c in cardstore.own_cards(root, session) if c.status == "open"}
    if gate.state(root, session).state == "open":
        readback = cards.get(clarify.card_id(digest))
        assumed = readback.evidence.splitlines() if readback else []
        return Outcome("ready", digest, [READY, BUILD_ON, *assumed] if assumed else [READY])
    reason = gate.state(root, session).reason
    if reason.startswith(gate.INTENT_CHANGE):   # SR-225: the check found a request that changes
        return Outcome("held", digest, [HELD.format(reason=reason)])   # a confirmed record
    choice = cards.get(clarify.choice_id(digest))
    if choice is None:   # SR-131 EX-4: an earlier blocking card still holds the gate
        choice = next((c for c in cardstore.own_cards(root, session) if c.kind == "choice"
                       and c.status in clarify.HOLDING), None)
    if choice is None:
        return Outcome("waiting", digest, [WAITING])
    drawn = [DRAW.format(path=choice.diagram, question=choice.issue,
                         options="; ".join(choice.resolutions))] if choice.diagram else []
    return Outcome("escalation" if clarify.is_escalation(choice) else "card", digest,
                   [*drawn, ASK], choice.id)


def _couldnt(core: Any, session: str, digest: str, why: str) -> Outcome:
    from plumb.approvals import Refused, find_prompt

    try:
        text = str(find_prompt(core, digest).get("text") or "")
    except Refused:
        text = ""
    card = clarify.write_couldnt_check(Path(core.root), session, digest, why, text)
    return Outcome("couldnt_check", digest, [SHOW_COULDNT], card.id)


def wait(core: Any, session: str | None = None, *, timeout: float | None = None,
         stream: Any = None, sleep: Callable[[float], None] = time.sleep,
         clock: Callable[[], float] = time.monotonic, mid_task: bool = False) -> Outcome:
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
            return _judged(core, session, digest, _since(core, session, logged), limit, sleep,
                           clock, str(logged.get("at") or ""), mid_task)
        digest = held.message_digest
    if gate.state(root, session).message_digest != digest and not gate.is_closed(root, session):
        gate.close(root, session, digest, clarify.GATE_REASON_CHECKING)   # no hook closed it
    if not gate.is_closed(root, session):
        return _outcome_from_state(core, session, digest)
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
            return Outcome("ready", digest, [READY])
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
                    return outcome
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
    parser.add_argument("--mid-task", action="store_true",
                        help="the agent is mid-task: ask only the questions that block it")
    args = parser.parse_args(argv)
    from plumb.api import open_core

    core = open_core(resolve_root(args.root))
    stream = sys.stderr
    outcome = wait(core, args.session, timeout=args.timeout, stream=stream,
                   mid_task=args.mid_task)
    emit(outcome.as_json() if args.as_json else outcome.lines, args.as_json)
    return 0
