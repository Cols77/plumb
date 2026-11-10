"""SR-378 EX-3 (with SR-225): an ordinary request that reverses behaviour the owner confirmed
closes the edit gate in the prompt hook; it opens when the owner answers the question it raised
or types /iaso go, and ``clarify --wait`` answers ``held`` meanwhile without running a check."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fakes import FakeBackend, FakeVerify
from host.test_answer_rejudge import answer
from host.test_intent_change_gate import SESSION, records  # noqa: F401

from iaso.api import open_core
from iaso.hosts.claude_code import pretool, prompt
from iaso.understand import cmd_clarify, gate

pytestmark = pytest.mark.sr("SR-378")

REVERSE = "make add subtract instead, SR-001"


def _say(repo: Path, hook_input, text: str) -> str:
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=text, session_id=SESSION)
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo, verify=FakeVerify(),
                       backend=FakeBackend()) == 0
    return out.getvalue()


def _edit_denied(repo: Path) -> bool:
    answer_ = pretool.decide(repo, SESSION, "Edit", {"file_path": "src/add.py"})
    return answer_.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_ex3_a_reversing_request_holds_edits_until_the_owner_types_go(
        records: Path, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    understand = prompt.understand_lines
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])
    _say(records, hook_input, REVERSE)
    assert gate.closed_reason(records, SESSION).startswith(gate.INTENT_CHANGE)
    assert _edit_denied(records)
    assert cmd_clarify.wait(open_core(records), SESSION, timeout=5).state == "held"
    # only this patch goes: monkeypatch.undo() would also bring back the machine's IASO_JOB
    # (conftest strips it), and inside a iaso job every hook then does nothing
    monkeypatch.setattr(prompt, "understand_lines", understand)
    _say(records, hook_input, "/iaso go")
    assert gate.state(records, SESSION).state == "open" and not _edit_denied(records)


def test_ex3_the_owners_answer_opens_the_hold(records: Path, hook_input,  # noqa: F811
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])
    _say(records, hook_input, REVERSE)
    assert _edit_denied(records)
    answer(records, hook_input, "Should add subtract from now on?", "Yes, subtract")
    assert gate.state(records, SESSION).state == "open" and not _edit_denied(records)


def test_ex3_a_commanded_request_is_held_by_its_check_not_by_the_hook(
        records: Path, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])
    _say(records, hook_input, "/iaso clarify " + REVERSE)
    assert gate.state(records, SESSION).state != "closed" \
        or not gate.closed_reason(records, SESSION).startswith(gate.INTENT_CHANGE)
