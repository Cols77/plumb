"""R2 / decision 2: an "ok" beside a correction the agent cannot place confirms nothing
(audit round 3).

The owner corrects an example through numbers or synonyms ("ok, except 3 minus 5 should
return 0") as often as by naming the record. When a prompt holds an objection or change
clause (an objection word, or a clause opening with but, though, except, ...) and none of its
objections names a record by ID or resolves in plain words to a record the owner was asked
about, it objects to every one of them (``approvals.owner_scope``, the one choke point). One
test per entry point with the four reproduced prompts: ``plumb relay`` by IDs, ``--group``,
``--set``, the prompt hook's relay line and ``plumb turn start``. When the prompt objects to
something else, the stored quote must be the owner's whole statement, not a bare "ok", and
the merge-boundary glance flags the message and prints it.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from capture_helpers import event_kinds, log_prompt, record_text, run, write_stated

from plumb.api import open_core
from plumb.hosts.claude_code import prompt as prompt_hook

pytestmark = pytest.mark.sr("SR-005")

PROMPTS = [
    ("ok, except 3 minus 5 should return 0, we clamp at zero", "ok"),
    ("ok but 5 to the 0 should give 0 for us", "ok"),
    ("sounds good, but b can be negative", "sounds good"),
    ("yes, though negative exponents must be supported too", "yes"),
]
IDS = ["INT-003", "SR-003", "SR-002"]
POW_WRONG = "No, the pow example is wrong, it should return 9. Ok, carry on with the tests"


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    write_record(repo, record_text("INT-003", "sub subtracts and pow raises",
                                   quote="add sub and pow", readback="Add sub and pow",
                                   mode="escalated", members=["SR-003", "SR-002"]))
    write_record(repo, record_text(
        "SR-003", "sub subtracts", statement="sub(a, b) returns a - b",
        examples=[{"id": "EX-1", "given": "a = 5 and b = 3", "when": "sub is called",
                   "then": "it returns 2"},
                  {"id": "EX-2", "given": "a = 3 and b = 5", "when": "sub is called",
                   "then": "it returns -2"}],
        links=[{"kind": "derives_from", "to": "INT-003"}]))
    write_record(repo, record_text(
        "SR-002", "pow raises a to a power", statement="pow(a, b) returns a ** b",
        assumptions=["b is a natural number"],
        examples=[{"id": "EX-1", "given": "a = 5 and b = 0", "when": "pow is called",
                   "then": "it returns 1"}],
        links=[{"kind": "derives_from", "to": "INT-003"}]))
    return repo


def stated(repo: Path, *, at: str = "2026-10-06T09:59:00Z", group: bool = False) -> None:
    index = open_core(repo).index()
    groups = ([{"group": "low-risk", "records": [{"id": i, "hash": index[i].hash}
                                                 for i in IDS]}] if group else None)
    write_stated(repo, [(i, index[i].hash) for i in IDS], at=at, groups=groups)


def nothing_confirmed(repo: Path) -> bool:
    statuses = open_core(repo).status(IDS)
    return ("approval" not in event_kinds(repo)
            and all(statuses[i].confirmation == "proposed" for i in IDS))


@pytest.mark.parametrize("words, affirmation", PROMPTS)
def test_relay_ids_confirms_nothing_beside_an_unplaced_correction(
        project: Path, capsys, words: str, affirmation: str) -> None:
    stated(project)
    digest = log_prompt(project, words)
    for ids in (IDS, ["SR-003"], ["SR-002"]):
        for quote in (affirmation, words):
            assert run(project, "relay", *ids, "--prompt", digest, "--quote", quote) == 3
    assert "object" in capsys.readouterr().err
    assert nothing_confirmed(project)


@pytest.mark.parametrize("words, affirmation", PROMPTS)
def test_relay_group_confirms_nothing_beside_an_unplaced_correction(
        project: Path, capsys, words: str, affirmation: str) -> None:
    stated(project, group=True)
    digest = log_prompt(project, words)
    assert run(project, "relay", "--group", "low-risk", "--prompt", digest, "--quote",
               affirmation) == 3
    assert "object" in capsys.readouterr().err
    assert nothing_confirmed(project)


@pytest.mark.parametrize("words, affirmation", PROMPTS)
def test_relay_set_confirms_nothing_beside_an_unplaced_correction(
        project: Path, capsys, words: str, affirmation: str) -> None:
    stated(project)
    digest = log_prompt(project, words)
    assert run(project, "relay", "--set", "INT-003", "--prompt", digest, "--quote",
               affirmation) == 3
    assert "object" in capsys.readouterr().err
    assert nothing_confirmed(project)


def _relay_command(out: str) -> list[str]:
    [line] = [line for line in out.splitlines() if line.startswith("plumb: awaiting")]
    if "run plumb relay " not in line:
        return []
    return line.split("run plumb relay ", 1)[1].split(" --prompt", 1)[0].split()


@pytest.mark.parametrize("words, affirmation", PROMPTS)
def test_prompt_hook_relay_line_suggests_nothing_beside_an_unplaced_correction(
        project: Path, hook_input, words: str, affirmation: str) -> None:
    stated(project, at="2000-01-01T00:00:00Z")
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=words, session_id="s1")
    assert prompt_hook.main(stdin=io.StringIO(payload), stdout=out, root=project,
                            verify=None, backend=None) == 0
    text = out.getvalue()
    assert _relay_command(text) == []
    assert "objects to or asks to change INT-003, SR-003, SR-002" in text


@pytest.mark.parametrize("words, affirmation", PROMPTS)
def test_turn_start_relay_line_suggests_nothing_beside_an_unplaced_correction(
        project: Path, monkeypatch, capsys, words: str, affirmation: str) -> None:
    from plumb.cli import main

    monkeypatch.delenv("PLUMB_AGENT_SESSION")  # the CLI-only fallback: no prompt hook
    stated(project, at="2000-01-01T00:00:00Z")
    monkeypatch.setattr("sys.stdin", io.StringIO(words))
    assert main(["turn", "start", "--session", "s1", "--root", str(project)]) == 0
    out = capsys.readouterr().out
    assert _relay_command(out) == []
    assert "objects to or asks to change INT-003, SR-003, SR-002" in out


def test_quote_beside_a_placed_correction_is_the_owners_whole_statement(project: Path,
                                                                        capsys) -> None:
    """The correction names the pow records, so sub may still be confirmed, but only with
    the owner's whole statement as the quote; the glance flags the message and prints it."""
    from plumb.boundary.glance import glance_line, glance_rows

    stated(project)
    digest = log_prompt(project, POW_WRONG)
    assert run(project, "relay", "SR-003", "--prompt", digest, "--quote", "Ok") == 3
    assert "whole clause" in capsys.readouterr().err
    assert run(project, "relay", "SR-003", "--prompt", digest, "--quote",
               "Ok, carry on with the tests") == 0
    assert open_core(project).status(["SR-003"])["SR-003"].confirmation == "confirmed"
    [entry] = open_core(project).log_read("events", ["approval"])
    assert entry.payload["prompt_objects"] is True
    [row] = glance_rows(open_core(project), [])
    line = glance_line(row)
    assert "the same message also objects or asks for a change" in line
    assert f'message "{POW_WRONG}"' in line
