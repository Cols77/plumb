"""R2 / R9: an objection is not an approval, however the owner names the record.

The owner names records in plain words ("the pow example is wrong"), not only by ID. A relayed
"ok" from the same prompt never confirms a record the prompt objects to or asks to change,
on every entry point of the one check (``approvals.owner_scope``): ``plumb relay`` with IDs,
``--group low-risk`` and ``--set INT``, the Claude Code prompt hook's relay line and
``plumb turn start``.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from capture_helpers import event_kinds, log_prompt, record_text, run, write_stated

from plumb.api import open_core
from plumb.hosts.claude_code import prompt as prompt_hook

pytestmark = pytest.mark.sr("SR-005")

POW_WRONG = "No, the pow example is wrong, it should return 9. Ok, carry on with the tests"
EXCEPT_POW = ("Looks good except the pow example: it should be 2 and 4 giving 16. "
              "ok go ahead")
DIV_FLOAT = "ok but div should return a float"


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
    write_record(repo, record_text(
        "SR-006", "div returns a over b", statement="div(a, b) returns a / b",
        examples=[{"id": "EX-1", "given": "6 and 3", "when": "div is called",
                   "then": "it returns 2"}]))
    return repo


def stated(repo: Path, ids: list[str], **kwargs) -> None:
    index = open_core(repo).index()
    write_stated(repo, [(i, index[i].hash) for i in ids], **kwargs)


def confirmation(repo: Path, record_id: str) -> str:
    return open_core(repo).status([record_id])[record_id].confirmation


@pytest.mark.parametrize("words, ids, quote", [
    (POW_WRONG, ["INT-005", "SR-005"], "Ok, carry on with the tests"),
    (EXCEPT_POW, ["SR-005"], "ok go ahead"),
    (DIV_FLOAT, ["SR-006"], "ok"),
])
def test_relay_ids_refuses_a_record_objected_to_in_plain_words(
        project: Path, capsys, words: str, ids: list[str], quote: str) -> None:
    stated(project, ["INT-005", "SR-005", "SR-006"])
    digest = log_prompt(project, words)
    assert run(project, "relay", *ids, "--prompt", digest, "--quote", quote) == 3
    assert "object" in capsys.readouterr().err
    assert "approval" not in event_kinds(project)
    assert all(confirmation(project, i) == "proposed" for i in ids)


def test_relay_ids_still_confirms_what_the_objection_leaves_alone(project: Path) -> None:
    stated(project, ["INT-005", "SR-005", "SR-006"])
    digest = log_prompt(project, POW_WRONG)
    assert run(project, "relay", "SR-006", "--prompt", digest, "--quote",
               "Ok, carry on with the tests") == 0
    assert confirmation(project, "SR-006") == "confirmed"
    assert confirmation(project, "SR-005") == "proposed"


def test_relay_group_refused_when_plain_words_object_to_a_member(project: Path,
                                                                 capsys) -> None:
    index = open_core(project).index()
    group = {"group": "low-risk", "records": [{"id": i, "hash": index[i].hash}
                                              for i in ("INT-005", "SR-005", "SR-006")]}
    write_stated(project, [], groups=[group])
    digest = log_prompt(project, EXCEPT_POW)
    assert run(project, "relay", "--group", "low-risk", "--prompt", digest, "--quote",
               "ok go ahead") == 3
    assert "SR-005" in capsys.readouterr().err
    assert "approval" not in event_kinds(project)


def test_relay_set_refused_when_plain_words_object_to_a_member(project: Path,
                                                               capsys) -> None:
    stated(project, ["INT-005", "SR-005"])
    digest = log_prompt(project, POW_WRONG)
    assert run(project, "relay", "--set", "INT-005", "--prompt", digest, "--quote",
               "Ok, carry on with the tests") == 3
    assert "object" in capsys.readouterr().err
    assert "approval" not in event_kinds(project)


def _relay_command(out: str) -> list[str]:
    [line] = [line for line in out.splitlines() if line.startswith("plumb: awaiting")]
    if "run plumb relay " not in line:
        return []
    return line.split("run plumb relay ", 1)[1].split(" --prompt", 1)[0].split()


def test_prompt_hook_relay_line_leaves_out_records_objected_to_in_plain_words(
        project: Path, hook_input) -> None:
    stated(project, ["INT-005", "SR-005", "SR-006"], at="2000-01-01T00:00:00Z")
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=POW_WRONG, session_id="s1")
    assert prompt_hook.main(stdin=io.StringIO(payload), stdout=out, root=project,
                            verify=None, backend=None) == 0
    text = out.getvalue()
    assert _relay_command(text) == ["SR-006"]
    assert "objects to or asks to change INT-005, SR-005" in text


def test_turn_start_relay_line_leaves_out_records_objected_to_in_plain_words(
        project: Path, monkeypatch, capsys) -> None:
    from plumb.cli import main

    stated(project, ["INT-005", "SR-005", "SR-006"], at="2000-01-01T00:00:00Z")
    monkeypatch.setattr("sys.stdin", io.StringIO(DIV_FLOAT))
    assert main(["turn", "start", "--session", "s1", "--root", str(project)]) == 0
    out = capsys.readouterr().out
    assert _relay_command(out) == ["INT-005", "SR-005"]
    assert "objects to or asks to change SR-006" in out
