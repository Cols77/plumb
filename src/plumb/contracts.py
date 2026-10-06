"""Frozen data shapes and protocols shared by every lane (spec 12.1). No I/O here."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

SCHEMA_VERSION = 1
Hash = str  # "sha256:" + 64 lowercase hex digits

RecordKind = Literal["intent", "requirement", "decision", "feature", "nc"]
KIND_PREFIX: Mapping[str, str] = {"intent": "INT", "requirement": "SR", "decision": "DEC",
                                  "feature": "FEAT", "nc": "NC"}
KIND_DIR: Mapping[str, str] = {"intent": "intents", "requirement": "requirements",
                               "decision": "decisions", "feature": "features", "nc": "ncs"}
ID_RE = r"^(?:(?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})$"
LinkKind = Literal["derives_from", "decides", "upstream", "relates_to", "implemented_by",
                   "verified_by", "corrects", "supersedes"]
Confirmation = Literal["proposed", "confirmed", "unconfirmed-edit"]
ApprovalBy = Literal["owner", "agent-relayed", "import"]
LogStream = Literal["events", "evidence"]


@dataclass(frozen=True)
class Pin:
    source: Hash          # YAML key "from"
    target: Hash          # YAML key "to"


@dataclass(frozen=True)
class Target:
    record: str | None = None   # "SR-004"            (YAML key "to")
    path: str | None = None     # repo-relative POSIX path
    symbol: str | None = None   # "plumb.links:link_states"
    test: str | None = None     # "tests/core/test_links.py::test_pin_drift"


@dataclass(frozen=True)
class Link:
    source: str                 # source record ID
    index: int                  # position in the source's links list
    kind: LinkKind
    target: Target
    example: str | None = None  # "EX-1" / "AC-1"
    pin: Pin | None = None

    @property
    def id(self) -> str:
        return f"{self.source}#{self.index}"


@dataclass(frozen=True)
class Example:
    id: str
    given: str = ""
    when: str = ""
    then: str = ""
    criterion: str = ""         # imported acceptance text


@dataclass(frozen=True)
class Record:
    id: str
    kind: RecordKind
    title: str
    path: str                   # repo-relative POSIX path of the .md file
    fields: Mapping[str, Any]   # frontmatter without id, title, links
    body: str
    links: tuple[Link, ...]
    examples: tuple[Example, ...] = ()
    hash: Hash = ""


@dataclass(frozen=True)
class LinkState:
    link: Link
    state: Literal["current", "stale", "dangling", "unpinned"]
    moved: Literal["source", "target", "both"] | None = None
    current: Pin | None = None  # current hashes, when both ends exist


@dataclass(frozen=True)
class RecordStatus:
    id: str
    confirmation: Confirmation
    approved_by: ApprovalBy | None
    covered: bool                         # requirements only; False otherwise
    uncovered_examples: tuple[str, ...]
    links: tuple[LinkState, ...]
    superseded_by: str | None = None
    # requirements: verified_by ends whose content changed since the owner's approval pinned
    # it (the record is then an unconfirmed edit: its acceptance test changed meaning)
    changed_tests: tuple[str, ...] = ()


@dataclass(frozen=True)
class LogEntry:
    stream: LogStream
    kind: str
    at: str                               # UTC, "YYYY-MM-DDTHH:MM:SSZ"
    marker: str                           # PLUMB_AGENT_SESSION value or "none"
    payload: Mapping[str, Any]
    prev: Hash | None
    digest: Hash
    offset: int = -1                      # byte offset of the line, when read


SelectionReason = Literal["verified_by", "literal", "import", "naming", "sample"]
EvidenceState = Literal["fresh-pass", "flaky-pass", "fresh-fail", "stale", "none"]


@dataclass(frozen=True)
class Selection:
    changed: tuple[str, ...]
    nodes: tuple[str, ...]                # priority order, within budget
    reasons: Mapping[str, SelectionReason]
    deferred: tuple[str, ...] = ()
    sampled: tuple[str, ...] = ()
    unknown_coverage: tuple[str, ...] = ()
    infra_changed: tuple[str, ...] = ()
    doc_only: bool = False
    expected_s: float = 0.0


@dataclass(frozen=True)
class NodeEvidence:
    node_id: str
    state: EvidenceState
    regression: bool = False              # failing now, passed or flaky earlier (7.5)
    test_changed_since_pass: bool = False # regression note only; never clears `regression`
    last_run: str | None = None           # run_id
    reuse_miss: Literal["closure", "test", "env", "identity"] | None = None
    last_failed: bool = False             # its last recorded run failed, whatever changed since


@dataclass(frozen=True)
class FullPending:
    pending: bool
    reasons: tuple[str, ...] = ()


JudgmentAction = Literal["intent-change", "drift-triage", "fidelity"]
Tier = Literal["accept", "escalate-llm", "escalate-human"]


@dataclass(frozen=True)
class Judgment:
    action: JudgmentAction
    subject: str                          # record ID or link ID
    verdict: str                          # change|no-change, cosmetic|material, fits|drifts|unsure
    confidence: float
    tier: Tier
    backend: str                          # heuristic | jev:<version> | host-agent | disabled | fake
    fingerprint: Hash
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FidelityPacket:
    requirement: str
    requirement_hash: Hash
    statement: str
    examples: tuple[Example, ...]
    # ends: {link, kind, path, symbol|test, hash, content, truncated}
    ends: tuple[Mapping[str, Any], ...]
    evidence: tuple[Mapping[str, Any], ...]  # {node_id, state}
    fingerprint: Hash


@dataclass(frozen=True)
class EscalationRequest:
    judgment: Judgment
    instruction: str                      # one line for the host agent
    packet: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StatusSnapshot:
    at: str
    requirements_total: int
    requirements_confirmed: int
    proposed: int                         # all kinds, proposed or unconfirmed edit
    stale_links: int
    dangling_links: int
    tests: Literal["ok", "failing", "regression", "not-run", "unknown"]
    failing: tuple[str, ...] = ()
    regressions: tuple[str, ...] = ()
    deferred: int = 0
    full_pending: bool = False
    full_pending_reasons: tuple[str, ...] = ()
    fidelity_unjudged: tuple[str, ...] = ()
    ask: int = 0
    skipped: str | None = None            # "budget" | "error" | None


@runtime_checkable
class CoreAPI(Protocol):
    root: Path
    def index(self) -> Mapping[str, Record]: ...
    def status(self, ids: Iterable[str] | None = None) -> Mapping[str, RecordStatus]: ...
    def link_states(self, ids: Iterable[str] | None = None) -> Sequence[LinkState]: ...
    def records_for_paths(self, paths: Iterable[str]) -> Mapping[str, tuple[str, ...]]: ...
    # maps each given repo-relative path to the IDs of the records it is a link end of
    # (or whose record file it is)
    def relevant(self, text: str, limit: int = 5) -> Sequence[tuple[str, float]]: ...
    def brief_lines(self, max_lines: int = 30) -> list[str]: ...
    def hash_target(self, target: Target) -> Hash | None: ...
    def write_record(self, kind: RecordKind, fields: Mapping[str, Any], body: str = "",
                     *, record_id: str | None = None) -> Record: ...
    def add_link(self, source: str, kind: LinkKind, target: Target,
                 example: str | None = None) -> Link: ...
    def log_append(self, stream: LogStream, kind: str,
                   payload: Mapping[str, Any]) -> LogEntry: ...
    def log_read(self, stream: LogStream, kinds: Iterable[str] | None = None,
                 since_offset: int = 0) -> Iterator[LogEntry]: ...


@runtime_checkable
class VerifyAPI(Protocol):
    def select(self, changed: Sequence[str], *,
               budget_s: float | None = None) -> Selection: ...
    def evidence(self, nodes: Iterable[str]) -> Mapping[str, NodeEvidence]: ...
    def full_pending(self) -> FullPending: ...
    def tests_for(self, refs: Iterable[str]) -> Mapping[str, tuple[str, ...]]: ...  # ID or path


@runtime_checkable
class JudgmentBackend(Protocol):
    name: str
    def intent_change(self, prompt: str, records: Sequence[Record]) -> Sequence[Judgment]: ...
    def drift_triage(self, states: Sequence[LinkState],
                     texts: Mapping[str, tuple[str, str]]) -> Sequence[Judgment]: ...
    def fidelity(self, packet: FidelityPacket) -> Judgment: ...


@runtime_checkable
class LLMCascade(Protocol):
    def escalate(self, request: EscalationRequest) -> None: ...
