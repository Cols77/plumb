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
READY = "Nothing in your request needs asking. You can start building."
SHOW_CARD = ("Show this to the owner in your reply and do not build until they have "
             "answered.")
SHOW_COULDNT = ("Show this to the owner in your reply. Nothing was built, and nothing is built "
                "until they say to build anyway.")
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
        if isinstance(entry, Mapping) and entry.get("digest") \
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
    current = gate.state(root, session)
    if current.state == "open":
        return Outcome("ready", digest, [READY])
    for card in cardstore.own_cards(root, session):
        if card.id == clarify.card_id(digest) and card.status == "open":
            state = "escalation" if clarify.is_escalation(card) else "card"
            return Outcome(state, digest, [*clarify.render(card), SHOW_CARD], card.id)
    return Outcome("waiting", digest, [WAITING])


def _couldnt(core: Any, session: str, digest: str, why: str) -> Outcome:
    card = clarify.write_couldnt_check(Path(core.root), session, digest, why)
    return Outcome("couldnt_check", digest, [*clarify.render(card), SHOW_COULDNT], card.id)


def wait(core: Any, session: str | None = None, *, timeout: float | None = None,
         stream: Any = None, sleep: Callable[[float], None] = time.sleep,
         clock: Callable[[], float] = time.monotonic) -> Outcome:
    """Collect the clarify result of the owner's latest message (see the module doc)."""
    from plumb.progress import Reporter
    from plumb.understand import worker

    root = Path(core.root)
    logged = latest_prompt(core, session)
    if logged is None:
        return Outcome("ready", "", [READY])
    session = str(logged.get("session") or session or "default")
    digest = str(logged["digest"])
    limit = float(timeout if timeout is not None else core.config.understand.clarify_wait_s)
    if gate.state(root, session).message_digest != digest and not gate.is_closed(root, session):
        gate.close(root, session, digest, clarify.GATE_REASON_CHECKING)   # no hook closed it
    if not gate.is_closed(root, session):
        return Outcome("ready", digest, [READY])
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
    while True:
        result = result_of(root, session, ours.id)
        if result is not None:
            if result.status == "ok":
                reporter.done()
                return _outcome_from_state(core, session, digest)
            reporter.failed(owner_text.STEP_CHECKING)
            return _couldnt(core, session, digest, why_failed(result))
        if clock() - started >= limit:
            reporter.failed(owner_text.STEP_CHECKING)
            return _couldnt(core, session, digest, clarify.COULDNT_TIMEOUT)
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
