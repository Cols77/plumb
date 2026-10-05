"""Typed judgment questions, answers and sealed records (spec 8.2).

Extracted and simplified from pi-agent-factory's ``substrate/judgment/model.py``. A record
carries a request fingerprint (state hash, question-set hash, resolved version) and a digest
over every other field, so mutating any field fails ``verify_record``. plumb does not write
record files: a JEV judgment becomes a ``judgment`` event in ``events.jsonl`` carrying the
fingerprint.

Vendor facts pinned by pi-agent-factory T-075 (``2026-09-28-jev-vendor-verification.md``): a
noul answer carries one probability and no confidence, so the adapter derives both and marks
them ``derived`` (V5); a choice takes at most 255 options and a score 2 to 10 ordered levels
(V6, V7).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from plumb.normalize import canonical_json, sha256_bytes

QuestionKind = Literal["choice", "score", "noul"]
Outcome = Literal["ok", "unavailable", "invalid"]
ConfidenceSource = Literal["vendor", "derived"]

DEFAULT_MODEL_ALIAS = "jev-latest"
MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10


@dataclass(frozen=True)
class JudgmentQuestion:
    """One typed question in the vendor's wire shape; build it with the constructors."""

    kind: QuestionKind
    instructions: str
    criteria: tuple[Any, ...]

    @classmethod
    def choice(cls, instructions: str, options: Mapping[str, str | None]) -> JudgmentQuestion:
        if not 1 <= len(options) <= MAX_CHOICE_OPTIONS:
            raise ValueError(f"a choice takes 1 to {MAX_CHOICE_OPTIONS} options")
        return cls("choice", instructions, tuple(options.items()))

    @classmethod
    def score(cls, instructions: str, levels: Sequence[str]) -> JudgmentQuestion:
        if not MIN_SCORE_LEVELS <= len(levels) <= MAX_SCORE_LEVELS:
            raise ValueError(f"a score takes {MIN_SCORE_LEVELS} to {MAX_SCORE_LEVELS} levels")
        return cls("score", instructions, tuple(levels))

    @classmethod
    def noul(cls, instructions: str, true: str, false: str) -> JudgmentQuestion:
        return cls("noul", instructions, (("true", true), ("false", false)))

    def to_wire(self) -> dict[str, Any]:
        """The question in the ``/v1/systemone`` request shape."""
        criteria: Any = list(self.criteria) if self.kind == "score" else dict(self.criteria)
        return {"type": self.kind, "instructions": self.instructions, "criteria": criteria}

    def prompt_text(self) -> str:
        return json.dumps(self.to_wire(), ensure_ascii=False)


@dataclass(frozen=True)
class TruncationReport:
    """How state assembly fitted the state into the vendor budget."""

    truncated: bool
    chars_per_token: int
    budget_tokens: int
    estimated_tokens: int
    original_chars: int
    kept_chars: int


@dataclass(frozen=True)
class JudgmentRequest:
    """State text plus an ordered question map, addressed to a model alias."""

    state: str
    questions: tuple[tuple[str, JudgmentQuestion], ...]
    model: str = DEFAULT_MODEL_ALIAS
    truncation: TruncationReport | None = None


def _check_probability(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"probability {value!r} is outside [0, 1]")


@dataclass(frozen=True)
class JudgmentAnswer:
    """One typed answer; ``confidence_source`` says who computed the confidence."""

    kind: QuestionKind
    value: str | float
    probabilities: dict[str, float]
    confidence: float
    confidence_source: ConfidenceSource

    @classmethod
    def from_noul(cls, p: float) -> JudgmentAnswer:
        """``{true: p, false: 1 - p}`` and confidence ``max(p, 1 - p)``, marked derived."""
        _check_probability(p)
        return cls("noul", p, {"true": p, "false": 1 - p}, max(p, 1 - p), "derived")

    @classmethod
    def from_vendor(cls, kind: Literal["choice", "score"], value: str | float,
                    probabilities: Mapping[str, float], confidence: float) -> JudgmentAnswer:
        for probability in probabilities.values():
            _check_probability(float(probability))
        _check_probability(float(confidence))
        probs = {str(label): float(p) for label, p in probabilities.items()}
        return cls(kind, value, probs, float(confidence), "vendor")


@dataclass(frozen=True)
class JudgmentRecord:
    """The evidence form of one judgment."""

    requested_alias: str
    resolved_version: str | None
    state_hash: str
    question_set_hash: str
    request_fingerprint: str
    answers: dict[str, JudgmentAnswer]
    truncation: TruncationReport | None
    timestamp: str
    outcome: Outcome
    tiers: dict[str, str] = field(default_factory=dict)
    version_drift: bool = False
    usage: dict[str, int] | None = None
    digest: str = ""


def state_hash(state: str) -> str:
    return sha256_bytes(state.encode("utf-8"))


def question_set_hash(questions: Sequence[tuple[str, JudgmentQuestion]]) -> str:
    """Hash of an ordered question map; order is part of the hash."""
    return sha256_bytes(canonical_json([[name, q.to_wire()] for name, q in questions]))


def request_fingerprint(state_digest: str, questions_digest: str, resolved_version: str) -> str:
    return sha256_bytes(canonical_json([state_digest, questions_digest, resolved_version]))


def make_record(request: JudgmentRequest, *, outcome: Outcome, timestamp: str,
                resolved_version: str | None = None,
                answers: Mapping[str, JudgmentAnswer] | None = None,
                usage: Mapping[str, int] | None = None) -> JudgmentRecord:
    """A sealed, unrouted record for ``request``."""
    s_hash = state_hash(request.state)
    q_hash = question_set_hash(request.questions)
    record = JudgmentRecord(
        requested_alias=request.model, resolved_version=resolved_version, state_hash=s_hash,
        question_set_hash=q_hash,
        request_fingerprint=request_fingerprint(s_hash, q_hash, resolved_version or ""),
        answers=dict(answers or {}), truncation=request.truncation, timestamp=timestamp,
        outcome=outcome, usage=dict(usage) if usage is not None else None)
    return seal(record)


def record_to_dict(record: JudgmentRecord) -> dict[str, Any]:
    return dataclasses.asdict(record)


def record_digest(record: JudgmentRecord) -> str:
    data = record_to_dict(record)
    data.pop("digest")
    return sha256_bytes(canonical_json(data))


def seal(record: JudgmentRecord) -> JudgmentRecord:
    return dataclasses.replace(record, digest=record_digest(record))


def verify_record(record: JudgmentRecord) -> bool:
    """True when no field changed since sealing and the fingerprint follows from the inputs."""
    consistent = record.request_fingerprint == request_fingerprint(
        record.state_hash, record.question_set_hash, record.resolved_version or "")
    return bool(record.digest) and consistent and record.digest == record_digest(record)
