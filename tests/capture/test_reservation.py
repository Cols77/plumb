"""R1 / R2 / decision 2: a relay pins only the records, and only the examples, that the
owner's words affirm without reservation (audit round 5).

Rounds 3 and 4 read a correction through closed word lists (objection, contrastive and
directive words). Exclusions, scopes and deferrals passed them: "yes, apart from the zero
example, that one is off", "lgtm, minus the zero example", "go ahead, skip the zero example",
"ok for the intent; I'll look at the examples later", "ok for the examples only", "ok, will
check the examples tomorrow" and "would that be ok if I sleep on it" each confirmed the
requirement whose example the owner excluded or deferred, and no approval carried
``prompt_objects``. Beside an affirmation, the one choke point (``approvals.owner_scope``
through ``approvals.change_clauses``) now reads any clause holding a word beyond the closed
vocabulary of assent as a reservation; an ok scoped to a kind of record ("ok for the
intent") keeps only that kind. One test per entry point: ``plumb relay`` by IDs,
``--group``, ``--set``, the prompt hook's relay line, ``plumb turn start`` and the
merge-boundary glance.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from capture_helpers import event_kinds, log_prompt, record_text, run, write_stated

from plumb.api import open_core
from plumb.hosts.claude_code import prompt as prompt_hook

pytestmark = pytest.mark.sr("SR-005")

IDS = ["INT-009", "SR-009"]
# (owner's message, the affirming words an agent would quote)
RESERVED = [
    ("yes, apart from the zero example, that one is off", "yes"),
    ("yes, aside from the zero example", "yes"),
    ("ok, other than the zero example", "ok"),
    ("lgtm, minus the zero example", "lgtm"),
    ("ok, zero example is off", "ok"),
    ("go ahead, skip the zero example", "go ahead"),
    ("ok for the intent; I'll look at the examples later", "ok"),
    ("ok for the examples only", "ok"),
    ("ok, will check the examples tomorrow", "ok"),
    ("would that be ok if I sleep on it", "ok"),
]
SCOPED = "ok for the intent; I'll look at the examples later"


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    write_record(repo, record_text("INT-009", "add cube", quote="add a cube function",
                                   readback="Add cube next to add", mode="escalated",
                                   members=["SR-009"]))
    write_record(repo, record_text(
        "SR-009", "cube works", statement="cube(a) returns a ** 3",
        examples=[{"id": "EX-1", "given": "a = 2", "when": "cube is called",
                   "then": "it returns 8"},
                  {"id": "EX-2", "given": "a = 0", "when": "cube is called",
                   "then": "it returns 0"}],
        links=[{"kind": "derives_from", "to": "INT-009"}]))
    return repo


def stated(repo: Path, *, at: str = "2026-10-06T09:59:00Z", group: bool = False) -> None:
    index = open_core(repo).index()
    groups = ([{"group": "low-risk", "records": [{"id": i, "hash": index[i].hash}
                                                 for i in IDS]}] if group else None)
    write_stated(repo, [(i, index[i].hash) for i in IDS], at=at, groups=groups)


def confirmed(repo: Path) -> set[str]:
    statuses = open_core(repo).status(IDS)
    return {i for i in IDS if statuses[i].confirmation == "confirmed"}


@pytest.mark.parametrize("words, affirmation", RESERVED)
def test_relay_ids_never_confirms_what_the_owner_holds_back(
        project: Path, capsys, words: str, affirmation: str) -> None:
    stated(project)
    digest = log_prompt(project, words)
    for ids in (IDS, ["SR-009"]):
        for quote in (affirmation, words):
            assert run(project, "relay", *ids, "--prompt", digest, "--quote", quote) == 3
    assert "object" in capsys.readouterr().err
    assert "SR-009" not in confirmed(project)
    for entry in open_core(project).log_read("events", ["approval"]):
        assert entry.payload["prompt_objects"] is True


def test_relay_ids_scoped_ok_confirms_only_the_kind_it_names(project: Path, capsys) -> None:
    """"ok for the intent; I'll look at the examples later" may confirm the intent, only
    with the owner's whole statement as the quote, and the approval flags the message."""
    stated(project)
    digest = log_prompt(project, SCOPED)
    assert run(project, "relay", "INT-009", "--prompt", digest, "--quote", "ok") == 3
    assert "whole clause" in capsys.readouterr().err
    assert run(project, "relay", "INT-009", "--prompt", digest, "--quote",
               "ok for the intent") == 0
    assert confirmed(project) == {"INT-009"}
    [entry] = open_core(project).log_read("events", ["approval"])
    assert entry.payload["prompt_objects"] is True


@pytest.mark.parametrize("words, affirmation", RESERVED)
def test_relay_group_confirms_nothing_beside_a_reservation(
        project: Path, capsys, words: str, affirmation: str) -> None:
    stated(project, group=True)
    digest = log_prompt(project, words)
    assert run(project, "relay", "--group", "low-risk", "--prompt", digest, "--quote",
               affirmation) == 3
    assert "object" in capsys.readouterr().err
    assert "approval" not in event_kinds(project)


@pytest.mark.parametrize("words, affirmation", RESERVED)
def test_relay_set_confirms_nothing_beside_a_reservation(
        project: Path, capsys, words: str, affirmation: str) -> None:
    stated(project)
    digest = log_prompt(project, words)
    for quote in (affirmation, words):
        assert run(project, "relay", "--set", "INT-009", "--prompt", digest, "--quote",
                   quote) == 3
    assert "object" in capsys.readouterr().err
    assert confirmed(project) == set()


def _relay_line(out: str) -> tuple[list[str], str]:
    [line] = [line for line in out.splitlines() if line.startswith("plumb: awaiting")]
    if "run plumb relay " not in line:
        return [], line
    return line.split("run plumb relay ", 1)[1].split(" --prompt", 1)[0].split(), line


@pytest.mark.parametrize("words, affirmation", RESERVED)
def test_prompt_hook_relay_line_holds_back_what_the_owner_reserves(
        project: Path, hook_input, words: str, affirmation: str) -> None:
    stated(project, at="2000-01-01T00:00:00Z")
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=words, session_id="s1")
    assert prompt_hook.main(stdin=io.StringIO(payload), stdout=out, root=project,
                            verify=None, backend=None) == 0
    suggested, line = _relay_line(out.getvalue())
    assert "SR-009" not in suggested
    assert "objects to or asks to change" in line and "SR-009" in line.split("|")[-1]
    if suggested:
        assert "<owner's whole sentence>" in line


@pytest.mark.parametrize("words, affirmation", RESERVED)
def test_turn_start_relay_line_holds_back_what_the_owner_reserves(
        project: Path, monkeypatch, capsys, words: str, affirmation: str) -> None:
    from plumb.cli import main

    monkeypatch.delenv("PLUMB_AGENT_SESSION")  # the CLI-only fallback: no prompt hook
    stated(project, at="2000-01-01T00:00:00Z")
    monkeypatch.setattr("sys.stdin", io.StringIO(words))
    assert main(["turn", "start", "--session", "s1", "--root", str(project)]) == 0
    suggested, line = _relay_line(capsys.readouterr().out)
    assert "SR-009" not in suggested
    assert "objects to or asks to change" in line


@pytest.mark.parametrize("words, affirmation", RESERVED)
def test_glance_flags_a_reservation_beside_the_quote(project: Path, words: str,
                                                     affirmation: str) -> None:
    """The glance re-reads the logged message through the same reader, so even an approval
    written without ``prompt_objects`` (an older one) is flagged beside a reservation."""
    from plumb.boundary.glance import _message

    digest = log_prompt(project, words)
    payload = {"records": [{"id": "INT-009"}], "prompt_digest": digest,
               "quote": affirmation, "stated_set": IDS}
    shown = _message(payload, {digest: {"text": words}}, open_core(project))
    assert shown["prompt_objects"] is True
    assert shown["prompt_text"] == words


def test_glance_line_flags_the_scoped_ok(project: Path) -> None:
    from plumb.boundary.glance import glance_line, glance_rows

    stated(project)
    digest = log_prompt(project, SCOPED)
    assert run(project, "relay", "INT-009", "--prompt", digest, "--quote",
               "ok for the intent") == 0
    [row] = glance_rows(open_core(project), [])
    assert "the same message also objects or asks for a change" in glance_line(row)


@pytest.mark.parametrize("words", ["ok", "ok, thanks", "Ok, carry on with the tests",
                                   "Looks right to me, ok go on with the links.",
                                   "No objections, approve them", "ok, go ahead with it"])
def test_an_ok_holding_nothing_back_still_confirms(project: Path, words: str) -> None:
    stated(project)
    digest = log_prompt(project, words)
    quote = "approve" if "approve" in words else words.split(",")[0].split(" ok")[0]
    quote = "ok" if quote.startswith("Looks") else quote
    assert run(project, "relay", *IDS, "--prompt", digest, "--quote", quote) == 0
    assert confirmed(project) == set(IDS)
    [entry] = open_core(project).log_read("events", ["approval"])
    assert "prompt_objects" not in entry.payload
