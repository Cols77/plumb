"""R2 / R13 Q4: on a host whose prompt hook is installed, only a hook-logged prompt grounds a
relayed owner decision (audit round 3).

The CLI-only fallback lets the agent record the owner's message itself (``plumb turn start``,
``via: turn``) on hosts WITHOUT a prompt hook, labelled "self-recorded message". Where the
hook exists (the ``claude-code`` marker; Codex once its hook has logged a prompt), that path
would let the agent write "ok SR-001" itself and relay it. One choke point refuses it
(``approvals.owner_prompt``); one test per entry point: ``plumb relay`` with IDs,
``--group low-risk``, ``--set INT``, ``plumb escalate decline --prompt``, and the
auto-approval eligibility check. The Claude Code deny rules also cover ``plumb turn start``
and ``plumb hook prompt`` (defence in depth).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from capture_helpers import event_kinds, log_prompt, record_text, run, write_stated

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-069")

OK = "ok, go ahead"
REFUSED = "not logged by the prompt hook"


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
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


def test_relay_ids_refuses_a_self_recorded_prompt_under_a_prompt_hook(project: Path,
                                                                      capsys) -> None:
    digest = log_prompt(project, OK, via="turn")
    _refused(project, capsys, "relay", "INT-005", "SR-005", "--prompt", digest,
             "--quote", OK)
    # the same words as the prompt hook logged them confirm (the owner's own prompt)
    digest = log_prompt(project, "ok, go ahead with it", via="hook")
    assert run(project, "relay", "INT-005", "SR-005", "--prompt", digest, "--quote",
               "ok, go ahead with it") == 0


def test_relay_group_refuses_a_self_recorded_prompt_under_a_prompt_hook(project: Path,
                                                                        capsys) -> None:
    digest = log_prompt(project, OK, via="turn")
    _refused(project, capsys, "relay", "--group", "low-risk", "--prompt", digest,
             "--quote", OK)


def test_relay_set_refuses_a_self_recorded_prompt_under_a_prompt_hook(project: Path,
                                                                      capsys) -> None:
    digest = log_prompt(project, OK, via="turn")
    _refused(project, capsys, "relay", "--set", "INT-005", "--prompt", digest,
             "--quote", OK)


def test_escalate_decline_refuses_a_self_recorded_prompt_under_a_prompt_hook(
        project: Path, capsys) -> None:
    words = "no spec needed, just do it"
    digest = log_prompt(project, words, via="turn")
    _refused(project, capsys, "escalate", "decline", "--prompt", digest, "--quote", words)


def test_turn_start_message_never_grounds_a_relay_under_the_claude_code_marker(
        project: Path, monkeypatch, capsys) -> None:
    """The reproduced path: the agent pipes its own "ok" into plumb turn start, then relays
    the digest it got."""
    from plumb.approvals import prompt_digest
    from plumb.cli import main

    monkeypatch.chdir(project)
    monkeypatch.setattr("sys.stdin", io.StringIO("ok INT-005 SR-005"))
    assert main(["turn", "start", "--session", "s9"]) == 0
    capsys.readouterr()
    digest = prompt_digest("ok INT-005 SR-005")
    _refused(project, capsys, "relay", "INT-005", "SR-005", "--prompt", digest,
             "--quote", "ok INT-005 SR-005")


def _codex_hook_prompt(repo: Path) -> None:
    path = repo / ".plumb" / "session" / "prompts.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"digest": "sha256:" + "c" * 64, "session": "x", "at": "t",
                                 "text": "hello", "via": "hook", "host": "codex"}) + "\n")


def test_codex_refuses_once_its_prompt_hook_has_logged_a_prompt(project: Path, monkeypatch,
                                                               capsys) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "codex")
    digest = log_prompt(project, OK, via="turn")
    # hooks not trusted yet (no prompt they logged): the fallback confirms, labelled (Q4)
    assert run(project, "relay", "SR-005", "--prompt", digest, "--quote", OK) == 0
    [entry] = open_core(project).log_read("events", ["approval"])
    assert entry.payload["self_recorded"] is True
    _codex_hook_prompt(project)
    digest = log_prompt(project, "ok then", via="turn")
    assert run(project, "relay", "INT-005", "--prompt", digest, "--quote", "ok then") == 3
    assert REFUSED in capsys.readouterr().err


def test_auto_approval_never_rests_on_a_self_recorded_prompt_under_a_prompt_hook(
        repo: Path, write_record, monkeypatch) -> None:
    from jev_fixtures import calibrated

    stub = calibrated(repo, write_record, monkeypatch, requirements=True)
    try:
        assert run(repo, "config", "auto-approve", "on") == 0  # the owner's terminal (test)
        monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
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
    from plumb.hosts.claude_code.install import choose_launcher, deny_rules, is_plumb_deny

    rules = deny_rules(choose_launcher(Path("."), "path"))
    for command in ("turn start", "hook prompt"):
        assert f"Bash(plumb {command}:*)" in rules
        assert f"Bash(python -m plumb {command}:*)" in rules
    assert all(is_plumb_deny(rule) for rule in rules)
