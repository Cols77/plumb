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
ApprovalBy = Literal["owner", "agent-relayed", "import", "auto-jev"]
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
    # R13 Q4: the standing approval rests on a message the agent recorded itself (an
    # agent-relayed approval citing a prompt logged by `plumb turn start`)
    self_recorded: bool = False


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


JudgmentAction = Literal["intent-change", "drift-triage", "fidelity", "faithfulness",
                         "contradiction", "ownership", "alignment", "dependency",
                         "ambiguity"]
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
    probability: float | None = None      # the answer's probability (JEV), when it has one
    confidence_label: Literal["low", "medium", "high"] | None = None


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
    # sp5 4.1 (the status card); the defaults keep older snapshots readable
    state: str = ""                       # aligned | awaits you | drift | failing | regression
    intent_summary: str = ""              # the session's intent in plain words (<= 40 chars)
    confirmed_by: Mapping[str, int] = field(default_factory=dict)  # owner, agent-relayed, ...
    auto_approve: str = "off"             # on | off | suspended
    # sp6 9.4 (SR-078): records also being changed on another worktree or branch, and the
    # branches named on the card; open intent conflicts awaiting the owner (sp6 8.3)
    overlaps: int = 0
    overlap_labels: tuple[str, ...] = ()
    conflicts: int = 0


@dataclass(frozen=True)
class Overlap:
    """A record this session works on that another worktree or branch is also changing
    (sp6 9.3, SR-078). ``how``: edited | new | ends | claimed (intent in flight, R17)."""

    record: str = ""
    title: str = ""
    branch: str = ""
    worktree: str = ""                    # "" for a branch without a worktree
    how: str = "edited"
    other_hash: str = ""                  # the other side's version: a new one repeats
    at: str = ""
    summary: str = ""                     # a claim's one-line intent, when claimed


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
    # sp2 11.2: typed judgments for capture, triage, ownership and hints (advisory, except
    # the gated entailment of auto-approval, sp2 8.2)
    version: str                          # resolved model version, "heuristic" otherwise
    def entailment(self, premise: str, hypothesis: str, *, subject: str,
                   claim_kind: str) -> Judgment: ...       # entailed | not-entailed | unsure
    def contradiction(self, prompt: str, record: Record) -> Judgment: ...
    # verdict contradicts | extends | benign
    def choose(self, question: str, options: Sequence[str], *, subject: str,
               context: str = "") -> Judgment: ...         # the chosen option or "none"
    def ask(self, question: str, context: str, *, subject: str,
            action: str) -> Judgment: ...                  # yes | no | unsure (Noul)


@runtime_checkable
class LLMCascade(Protocol):
    def escalate(self, request: EscalationRequest) -> None: ...


# --------------------------------------------------------------------------- sp2 CAPTURE
# Data shapes of ``plumb.capture.api`` (sp2 11.1). Every field has a default.


@dataclass(frozen=True)
class CaptureResult:
    written: tuple[str, ...] = ()          # IDs of new records, in write order
    updated: tuple[str, ...] = ()          # IDs of edited records
    needs_owner_again: tuple[str, ...] = ()  # updated records that were confirmed
    links: tuple[str, ...] = ()            # link ids added
    auto_approved: tuple[str, ...] = ()    # IDs approved by auto-jev (sp2 8.2)
    card: str = ""                         # the intent card text for the agent's reply
    lines: tuple[str, ...] = ()            # "INT-017 proposed", ...
    dry_run: bool = False


@dataclass(frozen=True)
class IntentFlag:
    record: str                            # the confirmed record the request may change
    kind: Literal["contradicts", "extends"] = "extends"
    confidence: float = 0.0
    example: str | None = None             # the example it is about (EX-n), when one
    reason: str = ""
    backend: str = "heuristic"


@dataclass(frozen=True)
class DiffStats:
    lines: int = 0                         # changed lines (added + removed)
    files: int = 0
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class EscalationSuggestion:
    trigger: Literal["size", "contradiction", "shared", "irreversible", "decisions",
                     "diff"] = "size"
    reason: str = ""
    intent: str | None = None
    line: str = ""                         # the one line a hook prints


@dataclass(frozen=True)
class TriageItem:
    id: str
    hash: Hash = ""
    title: str = ""
    kind: str = ""
    score: float | None = None             # faithfulness, 0..1; None without a judgment
    rating: Literal["faithful", "riskier", "unrated"] = "unrated"
    reason: str = ""
    excluded: str | None = None            # why it is always shown individually
    backend: str = ""


@dataclass(frozen=True)
class TriageView:
    backend: str = "none"
    available: bool = False                # False: "no judgments available"
    low_risk: tuple[TriageItem, ...] = ()
    individual: tuple[TriageItem, ...] = ()
    offer: str | None = None               # the one-line offer (R13 Q2), when low_risk


# --------------------------------------------------------------------------- sp5 PRESENT
# The output contract every host renders (sp5 9): cards and plain-language resolution.

CardMode = Literal["full", "compact", "off"]


@dataclass(frozen=True)
class IntentCardData:
    """The data of one intent card (sp2 11.1; the same shape CAPTURE provides)."""

    id: str
    title: str = ""
    state: str = "proposed"                # confirmation state
    confirmed_by: str | None = None        # "you" | "you (relayed)" | "JEV" | "import"
    label: str = ""                        # plain label, "self-recorded message" included
    quote: str = ""
    will: tuple[str, ...] = ()
    wont: tuple[str, ...] = ()
    assumed: tuple[str, ...] = ()
    examples: tuple[tuple[str, str, str], ...] = ()   # (SR, EX-n, text)
    tests: tuple[tuple[str, str], ...] = ()           # (test end, state)
    decisions: tuple[str, ...] = ()        # DEC ids deciding it
    # sp5 4.2: a card shows its record in full (the stated-set "shown" form), so PRESENT
    # also carries the record's kind, an SR's statement or an INT's read-back, and a DEC's
    # alternatives; CAPTURE's data leaves them empty
    kind: str = ""
    statement: str = ""
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class Resolved:
    """One thing the owner's words may mean: a record, a repository path or a test node."""

    ref: str                               # "SR-004", "src/app/calc.py", "tests/x.py::t"
    kind: Literal["record", "path", "test"] = "record"
    title: str = ""                        # the owner's terms: a record title, else the ref
    score: float = 0.0                     # 0..1
    reason: str = ""                       # "matched the title of SR-004"


@dataclass(frozen=True)
class Resolution:
    """``plumb resolve``: the owner's words mapped to records, paths and tests (sp5 5)."""

    query: str
    how: Literal["id", "path", "test", "words", "none"] = "none"
    items: tuple[Resolved, ...] = ()       # ranked, best first
    ambiguous: bool = False                # the best match is not clearly ahead: ask

    @property
    def ids(self) -> tuple[str, ...]:
        """The record IDs, when the resolution is clear; () when it is ambiguous."""
        if self.ambiguous:
            return ()
        return tuple(i.ref for i in self.items if i.kind == "record")

    @property
    def best(self) -> str | None:
        """The one thing the words clearly name (a record ID, a path or a test node); None
        when they are ambiguous or match nothing (the consumer then asks, never guesses)."""
        if self.ambiguous or not self.items:
            return None
        return self.items[0].ref


@dataclass(frozen=True)
class AutoApproveState:
    configured: bool = False               # the owner's latest config event says on
    effective: bool = False
    reason: str = "off"                    # why it is not effective, or "on"
    backend: str | None = None
    min_probability: float = 0.9
    min_confidence: str = "high"
    calibrated_version: str | None = None
    model_version: str | None = None       # last resolved JEV version seen
    suspended: bool = False                # model changed since calibration
    mirror_mismatch: bool = False          # config.yaml says on without the owner's event


@dataclass(frozen=True)
class Proposal:
    path: str
    proposed: str | None = None            # the proposed owner (record ID or test node)
    candidates: tuple[str, ...] = ()
    confidence: float = 0.0
    backend: str = "heuristic"
    reason: str = ""
    line: str = ""


@dataclass(frozen=True)
class ClarifyView:
    depth: Literal["trivial", "incremental", "escalated"] = "incremental"
    reason: str = ""
    answered: tuple[str, ...] = ()         # "SR-004 (confirmed): ..." lines
    questions: tuple[Mapping[str, Any], ...] = ()   # kept, ranked; ask the first
    dropped: tuple[Mapping[str, Any], ...] = ()     # each with "dropped_because"
    escalation: tuple[EscalationSuggestion, ...] = ()
    backend: str = "heuristic"
    # R17 (SR-081): the early intent-conflict cards and warnings against other branches'
    # intent in flight, shown first: ask a card before any implementation
    inflight: tuple[str, ...] = ()


# --------------------------------------------------------------------------- sp4 HOSTS
# The host-neutral turn API (sp4 3.1): every adapter turns its host's event into a
# ``TurnEvent`` and renders the ``TurnOutput`` of ``plumb.hosts.neutral.handle_event``.

TurnKind = Literal["session-start", "prompt", "edit", "stop"]


@dataclass(frozen=True)
class TurnEvent:
    kind: TurnKind
    root: Path
    session_id: str
    host: str                         # "claude-code" | "codex" | "pi" | "hermes" | "cli"
    text: str | None = None           # prompt text (prompt)
    path: str | None = None           # edited path (edit)
    source: str | None = None         # session start source: startup | resume | clear | compact
    stop_active: bool = False         # the host is already continuing after a block


@dataclass(frozen=True)
class TurnOutput:
    agent_context: tuple[str, ...] = ()   # lines added to the agent's context
    owner_lines: tuple[str, ...] = ()     # status card, summary, intent card (owner-facing)
    block: str | None = None              # one instruction that keeps the agent working
    status_line: str = ""                 # the one-line status card
