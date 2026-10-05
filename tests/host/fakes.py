"""In-memory fakes of the lane protocols HOST consumes (spec 12.1, 12.4).

HOST's unit tests never import VERIFY or BRIDGE modules: they use these fakes. The
integration phase checks them against the same protocols.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from plumb.contracts import (
    EscalationRequest,
    FidelityPacket,
    FullPending,
    Judgment,
    LinkState,
    NodeEvidence,
    Record,
    Selection,
)
from plumb.text import CHANGE_WORDS


@dataclass
class FakeVerify:
    """A VerifyAPI whose answers are set by the test."""

    nodes: tuple[str, ...] = ()
    reasons: Mapping[str, str] = field(default_factory=dict)
    deferred: tuple[str, ...] = ()
    infra_changed: tuple[str, ...] = ()
    doc_only: bool | None = None
    evidence_map: dict[str, NodeEvidence] = field(default_factory=dict)
    pending: FullPending = field(default_factory=lambda: FullPending(False))
    tests: dict[str, tuple[str, ...]] = field(default_factory=dict)
    select_calls: list[tuple[str, ...]] = field(default_factory=list)

    def select(self, changed: Sequence[str], *, budget_s: float | None = None) -> Selection:
        changed = tuple(changed)
        self.select_calls.append(changed)
        doc_only = self.doc_only
        if doc_only is None:
            doc_only = bool(changed) and all(p.endswith(".md") and not p.startswith(".plumb/")
                                             for p in changed)
        nodes = () if doc_only else self.nodes
        return Selection(changed=changed, nodes=nodes,
                         reasons={n: self.reasons.get(n, "verified_by") for n in nodes},
                         deferred=() if doc_only else self.deferred,
                         infra_changed=self.infra_changed, doc_only=doc_only,
                         expected_s=float(len(nodes)))

    def evidence(self, nodes: Iterable[str]) -> Mapping[str, NodeEvidence]:
        return {n: self.evidence_map.get(n, NodeEvidence(n, "none")) for n in nodes}

    def full_pending(self) -> FullPending:
        return self.pending

    def tests_for(self, refs: Iterable[str]) -> Mapping[str, tuple[str, ...]]:
        return {r: self.tests.get(r, ()) for r in refs}


@dataclass
class FakeBackend:
    """A JudgmentBackend flagging a record when the prompt carries change words."""

    name: str = "fake"
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def intent_change(self, prompt: str, records: Sequence[Record]) -> Sequence[Judgment]:
        self.calls.append((prompt, tuple(r.id for r in records)))
        lowered = prompt.lower()
        changing = any(word in lowered for word in CHANGE_WORDS)
        return [Judgment(action="intent-change", subject=r.id,
                         verdict="change" if changing else "no-change",
                         confidence=0.7 if changing else 0.6, tier="escalate-llm",
                         backend=self.name, fingerprint="sha256:" + "0" * 64)
                for r in records]

    def drift_triage(self, states: Sequence[LinkState],
                     texts: Mapping[str, tuple[str, str]]) -> Sequence[Judgment]:
        return []

    def fidelity(self, packet: FidelityPacket) -> Judgment:
        return Judgment(action="fidelity", subject=packet.requirement, verdict="unsure",
                        confidence=0.0, tier="escalate-llm", backend=self.name,
                        fingerprint=packet.fingerprint)


@dataclass
class FakeCascade:
    """An LLMCascade that keeps the escalations it receives."""

    requests: list[EscalationRequest] = field(default_factory=list)

    def escalate(self, request: EscalationRequest) -> None:
        self.requests.append(request)
