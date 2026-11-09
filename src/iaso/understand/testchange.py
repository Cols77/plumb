"""The testchange job kind (SR-207, report-fba0ba92): a model reads the edit that made a
regressed acceptance test of an approved example pass again, and says whether it was a real,
needed change or made only so the test passes. ``apply`` logs the verdict (``test-change-
verdict``, keyed by the test's changed body); ``verdict`` reads it back. No verdict, a failed
job or a doubtful one keeps the hidden-regression flag. It approves nothing."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from iaso.contracts import Applied, Job, Target
from iaso.understand import files

kind = "testchange"
SCHEMA_ID = "testchange.v1"
VERDICT_KIND = "test-change-verdict"
CONFIDENT = 0.8
DIFF_LIMIT = 12000
HERE = Path(__file__).resolve().parent


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "testchange.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**data, "id": SCHEMA_ID}


schema: Mapping[str, Any] = _load_schema()


def _git_text(root: Path, *args: str) -> str:
    import subprocess

    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def key_of(core: Any, node: str, failed_in: Any, head: Any, deleted: bool) -> list[str]:
    """What a verdict is about: the test, the failing run, the passing run's commit and the
    test file's current body (a new edit is a new question)."""
    test_file = node.split("::", 1)[0]
    current = "deleted" if deleted else core.hash_target(Target(path=test_file))
    return [node, str(failed_in or ""), str(head or ""), str(current or "")]


def context_of(core: Any, item: Mapping[str, Any], head: str | None) -> str:
    """What the judge reads: each requirement the test verifies with its examples, the runs,
    and the diff of the test file from the body that passed to the current one."""
    from iaso.judgment.common import record_text

    node = str(item["node"])
    test_file = node.split("::", 1)[0]
    index = core.index()
    parts = [f"Acceptance test: {node}",
             f"It passed in run {item.get('passed_in')}, failed in run "
             f"{item.get('failed_in')} (a regression), then the test file was changed "
             f"and it passed in run {item.get('masked_by')}."]
    for record_id, examples in sorted(dict(item.get("requirements") or {}).items()):
        record = index.get(record_id)
        if record is None:
            continue
        parts.append(f"\nRequirement {record_id}: {record_text(record)}")
        for example in record.examples:
            mark = " (verified by this test)" if example.id in examples else ""
            text = example.criterion or (f"given {example.given}, when {example.when}, "
                                         f"then {example.then}")
            parts.append(f"  {example.id}{mark}: {text}")
    base = head or "HEAD"
    root = Path(core.root)
    diff = _git_text(root, "diff", base, "--", test_file)
    if not diff.strip():
        old = _git_text(root, "show", f"{base}:{test_file}")
        diff = f"(no diff from {base}; the earlier body)\n{old}" if old else \
            "(the earlier body is not available)"
    since = f"commit {head}" if head else "its commit is not recorded; diff from HEAD"
    parts.append(f"\nChange to {test_file} since the passing run ({since}):"
                 f"\n{diff[:DIFF_LIMIT]}")
    return "\n".join(parts)


def verdict(core: Any, key: list[str]) -> dict[str, Any] | None:
    """The logged verdict for ``key`` (the latest), ``{real, verdict, probability, reason}``;
    ``real`` only for a confident "real". None when no job has answered."""
    found = None
    for entry in core.log_read("events", [VERDICT_KIND]):
        if list(entry.payload.get("key") or []) == key:
            found = entry.payload
    if found is None:
        return None
    probability = float(found.get("probability") or 0.0)
    return {"real": found.get("verdict") == "real" and probability >= CONFIDENT,
            "verdict": found.get("verdict"), "probability": probability,
            "reason": str(found.get("reason") or "")}


def failure(core: Any, key: list[str], item: Mapping[str, Any], head: str | None,
            deleted: bool) -> dict[str, str] | None:
    """``{judge, reason}`` when the queued job for ``key`` ended in an error (no judge could
    be reached, or it failed); None while it is queued or running."""
    from iaso.stale import current_session
    from iaso.understand import jobs

    session = current_session(core.root)
    job = build(core, session, item=item, head=head, deleted=deleted)
    outcome = jobs.result(Path(core.root), session, job.id) if job is not None else None
    if outcome is None or outcome.status != "error":
        return None
    return {"judge": outcome.dispatcher or "the judge",
            "reason": outcome.error.message if outcome.error else "it failed"}


def build(core: Any, session: str, **context: Any) -> Job | None:
    item = context.get("item")
    if core is None or not item:
        return None
    head, deleted = context.get("head"), bool(context.get("deleted"))
    return files.make_job(kind, session, SCHEMA_ID, {
        "item": dict(item), "head": head, "deleted": deleted,
        "key": key_of(core, str(item["node"]), item.get("failed_in"), head, deleted),
        "context": context_of(core, item, head)})


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    """Nothing left to read once the test file changed again (a new job asks about that)."""
    inputs = job.inputs
    item, head = inputs.get("item") or {}, inputs.get("head")
    now = key_of(core, str(item.get("node")), item.get("failed_in"), head,
                 bool(inputs.get("deleted")))
    if now != list(inputs.get("key") or []):
        return None
    return {**inputs, "context": context_of(core, item, head)}


def describe(job: Job) -> str:
    return "reading a change to a test"


def enqueue(core: Any, item: Mapping[str, Any], head: str | None, deleted: bool) -> None:
    """Queue the reading; it never waits for the model (SR-273). No session, no job."""
    from iaso.stale import current_session
    from iaso.understand import queue

    job = build(core, current_session(core.root), item=item, head=head, deleted=deleted)
    if job is not None:
        queue.enqueue(core, job)


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    return Applied(job=job.id, entries=({"kind": VERDICT_KIND, "payload": {
        "key": list(job.inputs["key"]), "subject": str(job.inputs["item"]["node"]),
        "verdict": str(answer.get("verdict")),
        "probability": float(answer.get("probability") or 0.0),
        "reason": str(answer.get("reason") or "")}},))
