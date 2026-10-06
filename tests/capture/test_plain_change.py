"""R2 / decision 2: an "ok" beside a correction in plain words confirms nothing it corrects
(audit round 4).

Round 3 refused an ok beside an objection word or a clause opening with but, though or
except. A correction the owner writes in plain words, with no such cue, still confirmed every
record shown: "ok, please also accept floats" confirmed DEC "Floats too?" (chosen: integers
only) and the intent whose won't list says "no floats yet"; "ok. Actually multiply by 0 gives
1 for us" confirmed the requirement whose example says multiply by 0 returns 0; "ok, and make
cube accept floats too" confirmed the cube records. The one choke point,
``approvals.owner_scope`` through ``approvals.change_clauses``, now reads as a change clause
any clause that holds a directive (make, accept, also, too, actually, ...) beside a
distinctive word, or says anything in plain words about a record the owner was asked about
(its title, statement, examples, assumptions, won't list or a decision's alternatives). One
test per entry point: ``plumb relay`` by IDs, ``--group``, ``--set``, the prompt hook's relay
line and ``plumb turn start``; the merge-boundary glance flags the message.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from capture_helpers import log_prompt, record_text, run, write_stated

from plumb.api import open_core
from plumb.hosts.claude_code import prompt as prompt_hook

pytestmark = pytest.mark.sr("SR-005")

IDS = ["INT-001", "SR-001", "SR-002", "DEC-001"]
# (owner's message, the affirming words an agent would quote, records it must never confirm)
PROMPTS = [
    ("ok, please also accept floats", "ok", ["INT-001", "DEC-001"]),
    ("ok. Actually multiply by 0 gives 1 for us", "ok", ["INT-001", "SR-001", "DEC-001"]),
    ("ok, and make cube accept floats too", "ok", ["INT-001", "SR-002", "DEC-001"]),
    # naming no shown record, a number still states behaviour nobody can place: all held
    ("ok, 3 minus 5 is 0 for us", "ok", IDS),
]
PRAISE = ["ok", "ok, thanks", "Ok, carry on with the tests", "ok, the multiply looks good"]


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    write_record(repo, record_text("INT-001", "multiply and cube", quote="add multiply and cube",
                                   readback="Add multiply and cube", wont=["no floats yet"],
                                   mode="escalated", members=["SR-001", "SR-002"]))
    write_record(repo, record_text(
        "SR-001", "multiply works", statement="multiply(a, b) returns a * b",
        examples=[{"id": "EX-1", "given": "a = 2 and b = 3", "when": "multiply is called",
                   "then": "it returns 6"},
                  {"id": "EX-2", "given": "a = 4 and b = 0", "when": "multiply is called",
                   "then": "it returns 0"}],
        links=[{"kind": "derives_from", "to": "INT-001"}]))
    write_record(repo, record_text(
        "SR-002", "cube works", statement="cube(n) returns n ** 3",
        examples=[{"id": "EX-1", "given": "n = 2", "when": "cube is called",
                   "then": "it returns 8"}],
        links=[{"kind": "derives_from", "to": "INT-001"}]))
    write_record(repo, record_text("DEC-001", "Floats too?",
                                   question="Should multiply and cube accept floats?",
                                   chosen="integers only", alternatives=["floats too"],
                                   matters=True, links=[{"kind": "decides", "to": "SR-002"}]))
    return repo


def stated(repo: Path, *, at: str = "2026-10-06T09:59:00Z", group: bool = False) -> None:
    index = open_core(repo).index()
    groups = ([{"group": "low-risk", "records": [{"id": i, "hash": index[i].hash}
                                                 for i in IDS]}] if group else None)
    write_stated(repo, [(i, index[i].hash) for i in IDS], at=at, groups=groups)


def confirmed(repo: Path) -> set[str]:
    statuses = open_core(repo).status(IDS)
    return {i for i in IDS if statuses[i].confirmation == "confirmed"}


@pytest.mark.parametrize("words, affirmation, corrected", PROMPTS)
def test_relay_ids_never_confirms_a_record_the_plain_correction_names(
        project: Path, capsys, words: str, affirmation: str, corrected: list[str]) -> None:
    stated(project)
    digest = log_prompt(project, words)
    assert run(project, "relay", *IDS, "--prompt", digest, "--quote", affirmation) == 3
    assert "object" in capsys.readouterr().err
    for record_id in corrected:
        for quote in (affirmation, words):
            assert run(project, "relay", record_id, "--prompt", digest, "--quote",
                       quote) == 3
    for record_id in sorted(set(IDS) - set(corrected)):
        code = run(project, "relay", record_id, "--prompt", digest, "--quote", affirmation)
        if words.startswith(affirmation + "."):
            # "ok." is a whole statement of its own: it may confirm what the correction does
            # not name, and the approval flags the message for the merge-boundary glance
            assert code == 0
        else:  # a bare ok cut from the clause holding the change
            assert code == 3
            assert "whole clause" in capsys.readouterr().err
    assert not confirmed(project) & set(corrected)
    for entry in open_core(project).log_read("events", ["approval"]):
        assert entry.payload["prompt_objects"] is True


def test_relay_ids_refuses_a_partial_quote_naming_records_beside_a_change(
        project: Path, capsys) -> None:
    words = "ok INT-001 and SR-002, and make multiply return floats"
    stated(project)
    digest = log_prompt(project, words)
    assert run(project, "relay", "INT-001", "SR-002", "--prompt", digest, "--quote",
               "ok INT-001 and SR-002") == 3
    assert "INT-001" in capsys.readouterr().err
    assert run(project, "relay", "SR-002", "--prompt", digest, "--quote",
               "ok INT-001 and SR-002") == 3
    assert "whole clause" in capsys.readouterr().err
    assert confirmed(project) == set()


@pytest.mark.parametrize("words, affirmation, corrected", PROMPTS)
def test_relay_group_confirms_nothing_beside_a_plain_correction(
        project: Path, capsys, words: str, affirmation: str, corrected: list[str]) -> None:
    stated(project, group=True)
    digest = log_prompt(project, words)
    assert run(project, "relay", "--group", "low-risk", "--prompt", digest, "--quote",
               affirmation) == 3
    assert "object" in capsys.readouterr().err
    assert confirmed(project) == set()


@pytest.mark.parametrize("words, affirmation, corrected", PROMPTS)
def test_relay_set_confirms_nothing_beside_a_plain_correction(
        project: Path, capsys, words: str, affirmation: str, corrected: list[str]) -> None:
    stated(project)
    digest = log_prompt(project, words)
    for quote in (affirmation, words):
        assert run(project, "relay", "--set", "INT-001", "--prompt", digest, "--quote",
                   quote) == 3
    assert "object" in capsys.readouterr().err
    assert confirmed(project) == set()


def _relay_line(out: str) -> tuple[list[str], str]:
    [line] = [line for line in out.splitlines() if line.startswith("plumb: awaiting")]
    if "run plumb relay " not in line:
        return [], line
    return line.split("run plumb relay ", 1)[1].split(" --prompt", 1)[0].split(), line


@pytest.mark.parametrize("words, affirmation, corrected", PROMPTS)
def test_prompt_hook_relay_line_holds_back_what_the_plain_correction_names(
        project: Path, hook_input, words: str, affirmation: str, corrected: list[str]) -> None:
    stated(project, at="2000-01-01T00:00:00Z")
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=words, session_id="s1")
    assert prompt_hook.main(stdin=io.StringIO(payload), stdout=out, root=project,
                            verify=None, backend=None) == 0
    suggested, line = _relay_line(out.getvalue())
    assert not set(suggested) & set(corrected)
    assert f"objects to or asks to change {', '.join(i for i in IDS if i in corrected)}" \
        in line
    if suggested:
        assert "<owner's whole sentence>" in line


@pytest.mark.parametrize("words, affirmation, corrected", PROMPTS)
def test_turn_start_relay_line_holds_back_what_the_plain_correction_names(
        project: Path, monkeypatch, capsys, words: str, affirmation: str,
        corrected: list[str]) -> None:
    from plumb.cli import main

    monkeypatch.delenv("PLUMB_AGENT_SESSION")  # the CLI-only fallback: no prompt hook
    stated(project, at="2000-01-01T00:00:00Z")
    monkeypatch.setattr("sys.stdin", io.StringIO(words))
    assert main(["turn", "start", "--session", "s1", "--root", str(project)]) == 0
    suggested, line = _relay_line(capsys.readouterr().out)
    assert not set(suggested) & set(corrected)
    assert f"objects to or asks to change {', '.join(i for i in IDS if i in corrected)}" \
        in line


@pytest.mark.parametrize("words", PRAISE)
def test_an_ok_that_asks_for_nothing_still_confirms(project: Path, words: str) -> None:
    stated(project)
    digest = log_prompt(project, words)
    quote = words.split(",")[0]
    assert run(project, "relay", *IDS, "--prompt", digest, "--quote", quote) == 0
    assert confirmed(project) == set(IDS)


def test_glance_flags_a_plain_correction_beside_a_whole_quote(project: Path) -> None:
    """The record the correction does not name may be confirmed, only with the owner's whole
    statement as the quote; the approval and the merge-boundary glance flag the message."""
    from plumb.boundary.glance import glance_line, glance_rows

    words = "ok, please also accept floats"
    stated(project)
    digest = log_prompt(project, words)
    assert run(project, "relay", "SR-001", "--prompt", digest, "--quote", words) == 0
    [entry] = open_core(project).log_read("events", ["approval"])
    assert entry.payload["prompt_objects"] is True
    [row] = glance_rows(open_core(project), [])
    assert "the same message also objects or asks for a change" in glance_line(row)
