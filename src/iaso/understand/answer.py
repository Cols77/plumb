"""One answer path for the owner's words: the state of one application of the reader's answers.

``Answering`` queues the rejections and reversals one application of the owner's
words produces (``by: owner-words``); nothing here writes, the caller writes the result."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from iaso.contracts import Applied, Job


def _rejection(core: Any, job: Job, digest: str, record: Any, evidence: str, confidence: float,
               rejection: Any) -> dict[str, Any]:
    from iaso.capture.calibrate import snapshot
    from iaso.normalize import sha256_text

    item = {"id": record.id, "hash": record.hash, **snapshot(core.index(), record, core)}
    return {"kind": "rejection", "payload": {
        "by": "owner-words", "session": job.session, "job": job.id, "records": [item],
        "reason": "capture-error" if rejection == "misread" else "intent-change",
        "prompt_digest": digest, "quote": evidence, "quote_digest": sha256_text(evidence),
        "confidence": confidence}}


def _reversal(job: Job, digest: str, message: str, record: Any, evidence: str,
              confidence: float) -> dict[str, Any]:
    """SR-372 EX-6: the owner said in conversation that a record iaso approved from their
    words or a judge's verdict is wrong; it is proposed again, their words the reason."""
    return {"kind": "revocation", "payload": {
        "by": "owner-words", "session": job.session, "job": job.id,
        "records": [{"id": record.id, "hash": record.hash}], "prompt_digest": digest,
        "message": message, "evidence": evidence, "confidence": confidence,
        "reason": evidence}}


class Answering:
    """The state of one application of answers (in memory; the caller writes the result).
    ``job``, ``digest`` and ``message`` are the reader's."""

    def __init__(self, core: Any, session: str, *, job: Job | None = None, digest: str = "",
                 message: str = "") -> None:
        self.core, self.session = core, session
        self.job, self.digest, self.message = job, digest, message
        self.index = core.index()
        self.statuses = core.status(list(self.index))
        self.entries: list[Mapping[str, Any]] = []
        self.notes: list[str] = []

    def reject(self, record: Any, evidence: str, confidence: float, rejection: Any) -> None:
        state = self.statuses[record.id]
        if state.confirmation == "confirmed":
            if self.job is not None and state.approved_by in (
                    "auto-jev", "auto-model", "owner-words"):   # SR-372 EX-6: said wrong
                self.entries.append(_reversal(self.job, self.digest, self.message, record,
                                              evidence, confidence))
            return
        assert self.job is not None
        self.entries.append(_rejection(self.core, self.job, self.digest, record, evidence,
                                       confidence, rejection))

    def applied(self) -> Applied:
        return Applied(job=self.job.id if self.job is not None else "",
                       entries=tuple(self.entries), notes=tuple(self.notes))
