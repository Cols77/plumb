"""The backlog pass (JUDGE, SR-107, spec 8).

The records proposed before SP8 are judged in **one background pass**: a series of judge jobs,
each covering the records of one intent as a capture does, queued together and never metered per
turn. A job already done is not run again unless its record changed (a job is its records at
their versions, so the same records are the same job), and a pass a failure interrupted resumes
on the next turn from where it stopped: ``start`` queues only the records that have no judgment
at their current version.

What the pass finds takes the question route of every judged record: the judge model's
questions go to the question tool, a fragment of the owner's words included (no trial card).

While it runs the pass reports "judging the backlog" with the records judged and the total
(``progress.Reporter``); when it ends the last job writes the end line."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from plumb.present import owner_text
from plumb.understand import files, jobs

PASS = "backlog"
KINDS_JUDGED = ("intent", "requirement", "decision")


@dataclass
class Started:
    """What ``start`` queued: the job ids, the records they cover, the pass's total."""

    jobs: list[str] = field(default_factory=list)
    records: int = 0
    total: int = 0
    line: str = ""           # SR-245: the one line saying no judge can be reached


@dataclass
class After:
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- the records


def marker_path(root: Any, session: str) -> Any:
    return files.session_dir(root, session) / "backlog.json"


def proposed(core: Any) -> list[Any]:
    """The records waiting for the owner that the judge covers: proposed, or edited since the
    owner confirmed them, and not superseded."""
    index = core.index()
    statuses = core.status()
    return [index[i] for i in sorted(index)
            if index[i].kind in KINDS_JUDGED and statuses[i].confirmation != "confirmed"
            and statuses[i].superseded_by is None]


def latest_verdicts(core: Any) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for entry in core.events():
        if entry.kind == "verdict":
            out[str(entry.payload.get("id"))] = entry.payload
    return out


def judged_ids(core: Any, records: Sequence[Any]) -> set[str]:
    """The records with a judgment of their current version."""
    verdicts = latest_verdicts(core)
    return {r.id for r in records if verdicts.get(r.id, {}).get("hash") == r.hash}


def group_of(index: Mapping[str, Any], record: Any) -> str:
    """The intent a record belongs to (itself for an intent or a record deriving from none)."""
    if record.kind == "intent":
        return record.id
    for link in record.links:
        if link.kind == "derives_from" and link.target.record in index \
                and index[link.target.record].kind == "intent":
            return link.target.record
    return record.id


def queued_ids(core: Any, session: str) -> set[str]:
    """The records a judge job of the session still waiting to run covers at their current
    version (SR-298 EX-3): they are not queued twice."""
    index = core.index()
    return {str(r["id"]) for job in jobs.pending(core.root, session) if job.kind == "judge"
            for r in job.inputs.get("records") or () if isinstance(r, Mapping)
            and str(r.get("id")) in index and index[str(r["id"])].hash == r.get("hash")}


def other_loops(core: Any, session: str) -> set[str]:
    """The intents of the loops other sessions of this checkout still run (SR-301): their own
    gates judge their records; the backlog leaves them alone."""
    from plumb.understand.cmd_intent import _passed, loops

    return {str(d["intent"]) for p, d in loops(core.root) if d.get("intent")
            and p.parent.parent.name != session and not d.get("handed_to")
            and not _passed(d, "build")}


def waiting(core: Any, session: str) -> list[str]:
    """The records with no judgment of their current version and no job queued for it, not
    of another session's open loop."""
    records = proposed(core)
    index = core.index()
    busy = other_loops(core, session)
    skip = judged_ids(core, records) | queued_ids(core, session)
    return [r.id for r in records if r.id not in skip and group_of(index, r) not in busy]


def spawn(core: Any, session: str) -> bool:
    """At session start: when records wait, queue them in a detached process, so the hook only
    enqueues and returns (SR-298 EX-1). Never raises; nothing started for no records."""
    import os
    import subprocess
    import sys

    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("PLUMB_FAKE_DISPATCH"):
        return False
    try:
        if not waiting(core, session):
            return False
        from plumb.background import popen_options

        env = {k: v for k, v in os.environ.items() if k not in ("PLUMB_WORKER", "PLUMB_JOB")}
        subprocess.Popen([sys.executable, "-m", "plumb", "understand", "backlog", "--session",
                          session, "--root", str(core.root), "--queue-only"], env=env,
                         **popen_options(core.root))
    except Exception:  # noqa: BLE001 - a hook calls this
        return False
    return True


def queue_waiting(core: Any, session: str, *, mark: bool = True) -> Started:
    """Queue the waiting records (session start's process, the landing job). With no judge
    reachable, SR-245 holds: one line says which and why, and nothing else changes. Without
    ``mark`` no pass is marked: each turn end would otherwise run ``resume`` (hook latency)."""
    from plumb.understand import verdict

    ids = waiting(core, session)
    if not ids:
        return Started()
    model = str(core.config.understand.judge_model)
    gap = verdict.model_gap(core, model)
    if gap and verdict.open_jev(core) is None:
        from plumb.judgment import waiting_line

        return Started(line=waiting_line(core.root, "the backlog", f"{model}: {gap}") or "")
    return start(core, session, {r.id for r in proposed(core)} - set(ids), mark=mark)


# --------------------------------------------------------------------------- the pass


def start(core: Any, session: str, skip: set[str] = frozenset(), *,
          mark: bool = True) -> Started:
    """Queue the judge jobs of the pass: one per intent, covering the records that have no
    judgment of their current version (and not in ``skip``). Idempotent: a job is its records, so jobs already
    queued or done are the same jobs. Marks the pass as started so ``resume`` continues it."""
    from plumb.understand import judge, queue

    records = proposed(core)
    done = judged_ids(core, records) | skip
    index = core.index()
    groups: dict[str, list[str]] = {}
    for record in records:
        if record.id not in done:
            groups.setdefault(group_of(index, record), []).append(record.id)
    out = Started(records=sum(len(v) for v in groups.values()), total=len(records))
    for key in sorted(groups):
        job = judge.build(core, session, records=groups[key], **{"pass": PASS,
                                                                  "total": len(records)})
        if job is not None:
            queue.enqueue(core, job)
            out.jobs.append(job.id)
    if mark:
        files.write_json_atomic(marker_path(core.root, session), {
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "total": len(records)})
    return out


def resume(core: Any, session: str) -> Started:
    """Continue a pass that was started (a failed job is queued again by the queue); nothing
    when no pass was started or nothing is left."""
    if not marker_path(core.root, session).exists():
        return Started()
    return start(core, session)


def holding(core: Any, session: str) -> set[str]:
    """The records a started pass that is not finished keeps back from the trial: their
    cards come when the pass ends."""
    if not marker_path(core.root, session).exists():
        return set()
    records = proposed(core)
    if len(judged_ids(core, records)) >= len(records):
        return set()
    return {r.id for r in records}


# --------------------------------------------------------------------------- cards


def after_job(core: Any, job: Any, *, verdicts: Sequence[Mapping[str, Any]]) -> After:
    """Called by ``judge.apply`` for a job of the pass: report the progress; when this job
    finishes the pass, write the end line. The records take the question route as any judged
    record does (no trial card); ``verdicts`` are this job's, not in the log yet."""
    from plumb.progress import Reporter
    from plumb.understand import judge

    records = proposed(core)
    judged = judged_ids(core, records) | {str(v["id"]) for v in verdicts}
    waiting_for = [r for r in records if r.id not in judged]
    total = max(int(job.inputs.get("total") or 0), len(records))
    done = total - len(waiting_for)
    reporter = Reporter(core.root, job.session, "judge")
    queued = [j for j in jobs.pending(core.root, job.session)
              if j.id != job.id and j.inputs.get("pass") == PASS]
    if waiting_for and queued:    # with none queued the pass ends, or its line runs forever
        reporter.update(owner_text.STEP_JUDGING_BACKLOG, done, total)
        return After()
    reporter.done(final=owner_text.BACKLOG_DONE.format(
        judged=done, questions=len(judge.open_questions(core, job.session))))
    return After()


def run(command: str, argv: list[str]) -> int:
    """``plumb understand backlog``: start (or continue) the pass from a shell."""
    import argparse

    from plumb.api import open_core
    from plumb.cliutil import add_common, resolve_root

    parser = argparse.ArgumentParser(prog="plumb understand backlog")
    add_common(parser)
    parser.add_argument("--session", default=files.CLI_SESSION)
    parser.add_argument("--queue-only", action="store_true")   # session start: no pass marked
    args = parser.parse_args(argv)
    core = open_core(resolve_root(args.root))
    started = queue_waiting(core, args.session, mark=not args.queue_only)
    print(started.line or (owner_text.BACKLOG_STARTED.format(
        records=started.records, jobs=len(started.jobs)) if started.jobs
        else owner_text.BACKLOG_NOTHING))
    return 0
