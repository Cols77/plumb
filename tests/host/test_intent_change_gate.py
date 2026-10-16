"""SR-196: the edit gate closes on a request that changes a confirmed record while no intent
loop ran for it, names the record and its example, and the owner's typed /plumb go releases
it; a request that touches nothing confirmed runs no model and holds nothing."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from fakes import FakeBackend, FakeVerify

from plumb import approvals
from plumb.api import open_core
from plumb.hosts.claude_code import prompt
from plumb.understand import files, gate

pytestmark = pytest.mark.sr("SR-225")

SR1 = """---
id: SR-001
title: add adds
feature: FEAT-001
statement: add(a, b) returns the sum of a and b.
examples:
- id: EX-1
  given: the numbers 1 and 2
  when: add(1, 2) is called
  then: it returns 3
---
"""
SR9 = """---
id: SR-009
title: Status line shows counts
feature: FEAT-002
statement: The status line shows confirmed requirement counts.
---
"""
SESSION = "s1"


@pytest.fixture(autouse=True)
def _without_the_understanding_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    for text in (SR1, SR9):
        write_record(repo, text)
    approvals.approve(open_core(repo), ["SR-001"])
    return repo


def _run(repo: Path, hook_input, text: str, backend: FakeBackend | None = None) -> str:
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=text, session_id=SESSION)
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo, verify=FakeVerify(),
                       backend=backend or FakeBackend()) == 0
    return out.getvalue()


def test_ex1_gate_closes_naming_the_record_and_example_until_the_owner_releases(
        records: Path, hook_input) -> None:
    out = _run(records, hook_input, "make add subtract instead, SR-001")
    state = gate.state(records, SESSION)
    assert state.state == "closed" and state.reason == "intent change: SR-001 EX-1"
    assert "plumb: edits are held (intent change: SR-001 EX-1)" in out
    # the typed /plumb go releases it, as it releases a failed check
    assert gate.release(open_core(records), SESSION, "typed")
    assert gate.state(records, SESSION).state == "open"


def test_ex2_gate_stays_open_when_the_loop_ran_for_this_request(records: Path,
                                                                hook_input) -> None:
    text = "make add subtract instead, SR-001"
    short = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    loop = files.session_dir(records, SESSION) / "intent" / f"{short}.json"
    loop.parent.mkdir(parents=True)
    loop.write_text("{}", encoding="utf-8")
    out = _run(records, hook_input, text)
    assert "this may change SR-001" in out and "edits are held" not in out
    assert gate.state(records, SESSION).state == "open"


def test_ex3_nothing_confirmed_touched_keeps_the_gate_open_and_runs_no_model(
        records: Path, hook_input) -> None:
    backend = FakeBackend()
    out = _run(records, hook_input, "change the status line colour, SR-009", backend=backend)
    assert backend.calls == [] and "edits are held" not in out
    assert gate.state(records, SESSION).state == "open"
