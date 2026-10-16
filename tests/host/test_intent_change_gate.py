"""SR-225: the prompt hook flags a request that may change a confirmed record and holds
nothing itself (the clarify job holds once it finds a request: a question never holds); a
request that touches nothing confirmed runs no model."""

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


def test_ex1_the_hook_flags_the_record_and_holds_nothing_itself(records: Path,
                                                                hook_input) -> None:
    import json

    text = "make add subtract instead, SR-001"
    out = _run(records, hook_input, text)
    assert "this may change SR-001" in out and "edits are held" not in out
    assert gate.state(records, SESSION).state == "open"
    rows = [json.loads(line) for line in
            (records / ".plumb" / "session" / "intent_flags.jsonl").read_text("utf-8").splitlines()]
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert [(r["session"], r["prompt_digest"], r["subject"]) for r in rows] \
        == [(SESSION, digest, "SR-001")]
    # the clarify job turns the flag into the hold once it finds a request (SR-225 EX-1)
    core = open_core(records)
    from plumb.understand import clarify

    assert clarify.intent_change_hold(core, SESSION, digest) == "intent change: SR-001 EX-1"
    gate.close(records, SESSION, digest, "intent change: SR-001 EX-1")
    assert gate.release(core, SESSION, "typed")   # the typed /plumb go releases it
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
