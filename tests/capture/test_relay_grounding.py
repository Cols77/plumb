"""R2 / R13 Q4: on a host whose prompt hook is installed, only a hook-logged prompt grounds an
owner decision the agent presents (audit round 3). The prose relay of approvals is gone
(SR-101 EX-9); what still takes a prompt are ``escalate decline`` and the auto-approval check.

The CLI-only fallback lets the agent record the owner's message itself (``iaso turn start``,
``via: turn``) on hosts WITHOUT a prompt hook, labelled "self-recorded message". Where the
hook exists (the ``claude-code`` marker; Codex once its hook has logged a prompt), that path
would let the agent write "ok SR-001" itself and present it. One choke point refuses it
(``approvals.owner_prompt``); one test per entry point: ``iaso escalate decline --prompt``
and the auto-approval eligibility check. The Claude Code deny rules also cover ``iaso turn start``
and ``iaso hook prompt`` (defence in depth).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import event_kinds, log_prompt, record_text, run, write_stated

from iaso.api import open_core

pytestmark = pytest.mark.sr("SR-208")

OK = "ok, go ahead"
REFUSED = "not logged by the prompt hook"


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    monkeypatch.setenv("IASO_AGENT_SESSION", "claude-code")
    write_record(repo, record_text("INT-005", "Add pow(a, b) returning a to the power b",
                                   quote="add a pow function", readback="Add pow(a, b)",
                                   mode="escalated", members=["SR-005"]))
    write_record(repo, record_text(
        "SR-005", "pow returns a to the power b", statement="pow(a, b) returns a ** b",
        examples=[{"id": "EX-1", "given": "2 and 3", "when": "pow is called",
                   "then": "it returns 8"}],
        links=[{"kind": "derives_from", "to": "INT-005"}]))
    index = open_core(repo).index()
    group = {"group": "low-risk", "records": [{"id": i, "hash": index[i].hash}
                                              for i in ("INT-005", "SR-005")]}
    write_stated(repo, [(i, index[i].hash) for i in ("INT-005", "SR-005")], groups=[group])
    return repo


def _refused(repo: Path, capsys, *argv: str) -> None:
    assert run(repo, *argv) == 3
    assert REFUSED in capsys.readouterr().err
    assert "approval" not in event_kinds(repo)
    assert "escalation-declined" not in event_kinds(repo)


def test_escalate_decline_refuses_a_self_recorded_prompt_under_a_prompt_hook(
        project: Path, capsys) -> None:
    words = "no spec needed, just do it"
    digest = log_prompt(project, words, via="turn")
    _refused(project, capsys, "escalate", "decline", "--prompt", digest, "--quote", words)


def _codex_hook_prompt(repo: Path) -> None:
    path = repo / ".iaso" / "session" / "prompts.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"digest": "sha256:" + "c" * 64, "session": "x", "at": "t",
                                 "text": "hello", "via": "hook", "host": "codex"}) + "\n")


def test_auto_approval_never_rests_on_a_self_recorded_prompt_under_a_prompt_hook(
        repo: Path, write_record, monkeypatch) -> None:
    from jev_fixtures import calibrated

    stub = calibrated(repo, write_record, monkeypatch, requirements=True)
    try:
        assert run(repo, "config", "auto-approve", "on") == 0  # the owner's terminal (test)
        monkeypatch.setenv("IASO_AGENT_SESSION", "claude-code")
        words = "add multiply next to add"
        before = set(open_core(repo).index())
        digest = log_prompt(repo, words, via="turn")
        doc = repo / "doc.json"
        doc.write_text(json.dumps({"intent": {"quote": words, "readback": words,
                                              "will": ["multiply next to add"]}}),
                       encoding="utf-8")
        assert run(repo, "capture", "--file", str(doc), "--prompt", digest) == 0
        [intent] = sorted(set(open_core(repo).index()) - before)
        assert open_core(repo).status([intent])[intent].confirmation == "proposed"
        assert not [e for e in open_core(repo).log_read("events", ["approval"])
                    if e.payload.get("by") == "auto-jev"]
    finally:
        stub.close()


def test_claude_code_deny_rules_cover_turn_start_and_hook_prompt() -> None:
    from iaso.hosts.claude_code.install import choose_launcher, deny_rules, is_iaso_deny

    rules = deny_rules(choose_launcher(Path("."), "path"))
    for command in ("turn start", "hook prompt"):
        assert f"Bash(iaso {command}:*)" in rules
        assert f"Bash(python -m iaso {command}:*)" in rules
    assert all(is_iaso_deny(rule) for rule in rules)
