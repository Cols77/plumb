"""``plumb clarify --wait`` (SHOW S3): the agent's first action on an owner request.

It returns the clarify result for the owner's latest message: it waits up to the timeout
(``understand.clarify_wait_s``, 45 s) for the check the prompt hook queued, or runs the check
itself when none was queued (same inputs, same id, so it never runs twice). A late result
after a timeout is collected by the next ``--wait``; a timeout or a failed check puts the
"couldn't check" card in the card store and keeps the gate closed. Nothing here opens the
gate: only the check's own result, the owner's answers, or the owner's release do.

Without ``--wait`` the command is today's clarification-depth helper, unchanged."""

from __future__ import annotations

import argparse
import dataclasses
import os
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


@dataclasses.dataclass
class Outcome:
    state: str                                 # ready | card | escalation | couldnt_check | waiting
    digest: str = ""
    lines: list[str] = dataclasses.field(default_factory=list)
    card: str = ""

    def as_json(self) -> dict[str, Any]:
        return {"state": self.state, "message_digest": self.digest, "card": self.card,
                "lines": self.lines}


def latest_prompt(core: Any, session: str | None) -> Mapping[str, Any] | None:
    """The newest owner message of the session (any session when none is named)."""
    from plumb.approvals import is_owner_entry

    newest: Mapping[str, Any] | None = None
    try:
        text = Path(core.paths.prompts).read_text(encoding="utf-8")
    except OSError:
        return None
    import json

    for line in text.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, Mapping) and entry.get("digest") and is_owner_entry(entry) \
                and (session is None or entry.get("session") == session) \
                and not clarify.is_typed_go(str(entry.get("text") or "")):
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
         clock: Callable[[], float] = time.monotonic) -> Outcome:
    """Collect the clarify result of the owner's latest message (see the module doc)."""
    from plumb.progress import Reporter
    from plumb.understand import worker

    from plumb.stale import SESSION_ENV, current_session

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
    if gate.state(root, session).message_digest != digest and not gate.is_closed(root, session):
        gate.close(root, session, digest, clarify.GATE_REASON_CHECKING)   # no hook closed it
    if not gate.is_closed(root, session):
        return _outcome_from_state(core, session, digest)
    queued = _jobs_of(root, session, "clarify", digest)
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
    args = parser.parse_args(argv)
    from plumb.api import open_core

    core = open_core(resolve_root(args.root))
    stream = sys.stderr
    outcome = wait(core, args.session, timeout=args.timeout, stream=stream)
    emit(outcome.as_json() if args.as_json else outcome.lines, args.as_json)
    return 0
