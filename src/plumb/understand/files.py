"""File formats of the understanding layer (plan 3.2 item 2): paths, atomic JSON writes, the
job id. One writer per file is named in the plan; this module only knows the shapes."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import (
    ClarifyAnswer,
    ClarifyQuestion,
    GateState,
    Job,
    JobError,
    JobResult,
    Progress,
)

_SAFE = re.compile(r"[^A-Za-z0-9_-]+")
CLI_SESSION = "cli"


def session_dir(root: Path, session: str) -> Path:
    return Path(root) / ".plumb" / "session" / (_SAFE.sub("-", session).strip("-") or "default")


def jobs_dir(root: Path, session: str) -> Path:
    return session_dir(root, session) / "jobs"


def results_dir(root: Path, session: str) -> Path:
    return session_dir(root, session) / "results"


def ran_dir(root: Path, session: str) -> Path:
    return session_dir(root, session) / "ran"


def cards_path(root: Path, session: str) -> Path:
    return session_dir(root, session) / "cards.json"


def stale_cards_path(root: Path, session: str) -> Path:
    return session_dir(root, session) / "stale_cards.json"


def gate_path(root: Path, session: str) -> Path:
    return session_dir(root, session) / "gate"


def failures_path(root: Path, session: str) -> Path:
    return session_dir(root, session) / "failures.json"


def progress_path(root: Path, session: str | None) -> Path:
    return session_dir(root, session or CLI_SESSION) / "progress"


def lock_path(root: Path, session: str) -> Path:
    return session_dir(root, session) / "worker.lock"


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def canonical(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_of(data: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()


def job_id(kind: str, schema: str, inputs: Mapping[str, Any], needs: str | None) -> str:
    """``<kind>-`` plus 16 hex of the sha256 of the canonical JSON of (kind, schema, inputs,
    needs): the same inputs give the same id, so a retried hook never queues twice."""
    raw = canonical([kind, schema, inputs, needs])
    return f"{kind}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def make_job(kind: str, session: str, schema: str, inputs: Mapping[str, Any], *,
             needs: str | None = None, created: str = "") -> Job:
    return Job(id=job_id(kind, schema, inputs, needs), kind=kind, session=session,
               created=created, schema=schema, needs=needs, inputs=dict(inputs),
               inputs_digest=digest_of(inputs))


def job_to_json(job: Job) -> dict[str, Any]:
    return {"v": job.v, "id": job.id, "kind": job.kind, "session": job.session,
            "created": job.created, "schema": job.schema, "needs": job.needs,
            "inputs": dict(job.inputs), "inputs_digest": job.inputs_digest}


def job_from_json(data: Mapping[str, Any]) -> Job:
    needs = data.get("needs")
    return Job(id=str(data.get("id", "")), kind=str(data.get("kind", "")),
               session=str(data.get("session", "")), created=str(data.get("created", "")),
               schema=str(data.get("schema", "")), needs=str(needs) if needs else None,
               inputs=dict(data.get("inputs") or {}),
               inputs_digest=str(data.get("inputs_digest", "")), v=int(data.get("v", 1)))


def result_to_json(result: JobResult) -> dict[str, Any]:
    error = None if result.error is None else {"step": result.error.step,
                                               "message": result.error.message}
    return {"v": result.v, "job": result.job, "status": result.status,
            "answer": None if result.answer is None else dict(result.answer), "error": error,
            "model": result.model, "dispatcher": result.dispatcher, "started": result.started,
            "finished": result.finished, "run_s": result.run_s}


def result_from_json(data: Mapping[str, Any]) -> JobResult:
    error = data.get("error")
    answer = data.get("answer")
    return JobResult(
        job=str(data.get("job", "")), status="error" if data.get("status") == "error" else "ok",
        answer=dict(answer) if isinstance(answer, Mapping) else None,
        error=JobError(str(error.get("step", "")), str(error.get("message", "")))
        if isinstance(error, Mapping) else None,
        model=str(data.get("model", "")), dispatcher=str(data.get("dispatcher", "")),
        started=str(data.get("started", "")), finished=str(data.get("finished", "")),
        run_s=float(data.get("run_s") or 0), v=int(data.get("v", 1)))


def gate_to_json(gate: GateState) -> dict[str, Any]:
    return {"state": gate.state, "message_digest": gate.message_digest, "reason": gate.reason,
            "since": gate.since}


def gate_from_json(data: Any) -> GateState:
    if not isinstance(data, Mapping):
        return GateState()
    return GateState(state="closed" if data.get("state") == "closed" else "open",
                     message_digest=str(data.get("message_digest", "")),
                     reason=str(data.get("reason", "")), since=str(data.get("since", "")))


def progress_to_json(progress: Progress) -> dict[str, Any]:
    return {"step": progress.step, "done": progress.done, "total": progress.total,
            "started": progress.started, "updated": progress.updated,
            "state": progress.state, "kind": progress.kind}


def progress_from_json(data: Any) -> Progress | None:
    if not isinstance(data, Mapping):
        return None
    state = data.get("state")
    return Progress(step=str(data.get("step", "")), done=int(data.get("done") or 0),
                    total=int(data.get("total") or 0), started=str(data.get("started", "")),
                    updated=str(data.get("updated", "")),
                    state=state if state in ("running", "failed", "done") else "running",
                    kind=str(data.get("kind", "")))


def question_to_json(q: ClarifyQuestion) -> dict[str, Any]:
    return {"id": q.id, "text": q.text, "resolutions": list(q.resolutions), "record": q.record}


def answer_to_json(a: ClarifyAnswer) -> dict[str, Any]:
    return {"question": a.question, "answer": a.answer, "message_digest": a.message_digest}
