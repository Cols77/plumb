"""Shared helpers of the PRESENT tests (sp5): records, hook drivers and lane fakes.

PRESENT's unit tests never import another lane's new modules (plan 3.5); these fakes stand in
for VERIFY, the judgment backend and CAPTURE's ``plumb.capture.api``.
"""

from __future__ import annotations

import io
import json
import sys
import types
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.contracts import FullPending, Judgment, NodeEvidence, Selection

SR1 = """---
id: SR-001
title: add returns the sum of two numbers
feature: FEAT-001
statement: app.calc.add(a, b) returns a + b for integers.
examples:
- id: EX-1
  given: a = 1 and b = 2
  when: add(a, b) is called
  then: it returns 3
---
"""
SR2 = """---
id: SR-002
title: divide returns the quotient
feature: FEAT-001
statement: app.calc.divide(a, b) returns a / b.
examples:
- id: EX-1
  given: 6 and 3
  when: divide runs
  then: it returns 2
- id: EX-2
  given: 1 and 0
  when: divide runs
  then: it returns 0
---
"""
SR3 = """---
id: SR-003
title: invoices export to csv
feature: FEAT-002
statement: An invoice exports to one csv file.
---
"""
INT1 = """---
id: INT-001
title: add multiply next to add
quote: "add multiply next to add"
readback: Add multiply(a, b) beside add.
will: [multiply(a, b) returns a * b]
wont: [floats]
assumptions: [integers only]
---
"""
FEAT1 = """---
id: FEAT-001
title: Calculator
requirements: [SR-001, SR-002]
---
"""
FEAT2 = """---
id: FEAT-002
title: Invoices
requirements: [SR-003]
---
"""


def write_all(repo: Path, write_record: Any, *texts: str) -> Path:
    for text in texts:
        write_record(repo, text)
    return repo


@dataclass
class FakeVerify:
    """A VerifyAPI whose answers the test sets."""

    nodes: tuple[str, ...] = ()
    deferred: tuple[str, ...] = ()
    evidence_map: dict[str, NodeEvidence] = field(default_factory=dict)
    pending: FullPending = field(default_factory=lambda: FullPending(False))
    tests: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def select(self, changed: Sequence[str], *, budget_s: float | None = None) -> Selection:
        changed = tuple(changed)
        doc_only = bool(changed) and all(p.endswith(".md") and not p.startswith(".plumb/")
                                         for p in changed)
        nodes = () if doc_only else self.nodes
        return Selection(changed=changed, nodes=nodes,
                         reasons={n: "verified_by" for n in nodes},
                         deferred=() if doc_only else self.deferred, doc_only=doc_only,
                         expected_s=float(len(nodes)))

    def evidence(self, nodes: Iterable[str]) -> Mapping[str, NodeEvidence]:
        return {n: self.evidence_map.get(n, NodeEvidence(n, "none")) for n in nodes}

    def full_pending(self) -> FullPending:
        return self.pending

    def tests_for(self, refs: Iterable[str]) -> Mapping[str, tuple[str, ...]]:
        return {r: self.tests.get(r, ()) for r in refs}


@dataclass
class FakeBackend:
    """A JudgmentBackend that flags a record when the prompt says "instead"."""

    name: str = "fake"
    answers: dict[str, str] = field(default_factory=dict)   # subject -> yes | no | unsure
    version: str = "fake-1"

    def intent_change(self, prompt: str, records: Sequence[Any]) -> Sequence[Judgment]:
        change = "instead" in prompt.lower()
        return [Judgment(action="intent-change", subject=r.id,
                         verdict="change" if change else "no-change", confidence=0.7,
                         tier="escalate-llm", backend=self.name,
                         fingerprint="sha256:" + "0" * 64) for r in records]

    def drift_triage(self, states: Any, texts: Any) -> Sequence[Judgment]:
        return []

    def fidelity(self, packet: Any) -> Judgment:
        return Judgment(action="fidelity", subject=packet.requirement, verdict="unsure",
                        confidence=0.0, tier="escalate-llm", backend=self.name,
                        fingerprint=packet.fingerprint)

    def ask(self, question: str, context: str, *, subject: str, action: str) -> Any:
        """Noul: yes | no | unsure, with the answer's probability (sp2 11.2)."""
        verdict = self.answers.get(subject, "yes")
        return types.SimpleNamespace(
            action="alignment", subject=subject, verdict=verdict,
            confidence=0.9 if verdict != "unsure" else 0.0, backend=self.name,
            probability=0.95 if verdict != "unsure" else None)


def run_prompt(repo: Path, hook_input: Any, text: str, session: str = "s1", **kwargs: Any
               ) -> str:
    from plumb.hosts.claude_code import prompt

    kwargs.setdefault("verify", FakeVerify())
    kwargs.setdefault("backend", FakeBackend())
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=text, session_id=session)
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo, **kwargs) == 0
    return out.getvalue()


def run_stop(repo: Path, hook_input: Any, session: str = "s1", **kwargs: Any) -> dict:
    """The stop hook's answer as JSON (``{}`` when it printed nothing)."""
    from plumb.hosts.claude_code import stop

    kwargs.setdefault("verify", FakeVerify())
    kwargs.setdefault("unjudged", lambda core, ids: ())
    out = io.StringIO()
    payload = hook_input("Stop", session_id=session, stop_hook_active=False)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=repo, **kwargs) == 0
    text = out.getvalue().strip()
    return json.loads(text) if text else {}


def touch(repo: Path, rel: str, session: str = "s1") -> None:
    """Record ``rel`` as edited this turn (what the post-edit hook does)."""
    directory = repo / ".plumb" / "session" / session
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "touched.txt").open("a", encoding="utf-8") as handle:
        handle.write(rel + "\n")


def fake_capture(monkeypatch: Any, **functions: Any) -> types.ModuleType:
    """Install a fake ``plumb.capture.api`` exposing ``functions`` (CAPTURE is another lane).
    Only the api module is replaced: the rest of the real package (``spec``, ``triage``...)
    stays importable."""
    import plumb.capture as package

    api = types.ModuleType("plumb.capture.api")
    for name, function in functions.items():
        setattr(api, name, function)
    monkeypatch.setattr(package, "api", api, raising=False)
    monkeypatch.setitem(sys.modules, "plumb.capture.api", api)
    return api
