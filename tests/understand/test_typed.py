"""R5: typed commands are an exact grammar, not reading (SR-101 EX-6 and EX-10)."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.test_read_apply import approvals
from understand.test_read_job import (
    SESSION,
    ctx_for,
    log_prompt,
    make_core,
    record_text,
    state,
)

from iaso.api import open_core
from iaso.understand import files, read, typed

pytestmark = pytest.mark.sr("SR-214")

DEC = ("---\nid: DEC-017\ntitle: Pick a store\nquestion: which store?\noptions:\n- id: A\n"
       "  text: sqlite\nchosen: A\nstatus: proposed\n---\nbody\n")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [DEC, record_text(40), record_text(41)])


def commands_of(core) -> list:
    return [e for e in core.events() if e.kind == "approval"
            and e.payload.get("by") == "agent-relayed"]


def test_ex10_typed_confirm_with_words_confirms_nothing(core, engine_standins) -> None:
    state(core, ["SR-040", "SR-041"])
    text = "/iaso confirm the reminder timing"
    assert typed.parse(text) is None               # SR-209 EX-6: no approve or confirm verb
    digest = log_prompt(core, text)
    job_id = read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text})
    assert job_id is not None                      # the words go to the reader as prose
    assert commands_of(core) == [] and approvals(open_core(core.root)) == {}
    job = files.job_from_json(files.read_json(files.jobs_dir(core.root, SESSION)
                                              / f"{job_id}.json"))
    assert [i["id"] for i in job.inputs["shown"]] == ["SR-040", "SR-041"]


@pytest.mark.parametrize("text,expected", [
    ("/iaso undo SR-001", ("undo", ("SR-001",), "", "")),
    ("/iaso go", ("go", (), "", "")),
])
def test_grammar_is_exact(text: str, expected: tuple) -> None:
    parsed = typed.parse(text)
    assert (parsed.command, parsed.ids, parsed.words, parsed.state) == expected


@pytest.mark.parametrize("text", [
    "iaso approve SR-001", "ok /iaso approve SR-001", "/iaso undo",
    "/iaso approve SR-001", "/iaso confirm SR-001, DEC-017", "/iaso approve",
    "/iaso undo SR-001 SR-002", "/iaso go now",
    "/iasos go", "/Iaso go", "please /iaso go", "/iaso", "/iaso frobnicate SR-001",
    "turn settling on", "", "yes"])
def test_grammar_rejects_everything_else(text: str) -> None:
    assert typed.parse(text) is None


def test_typed_owner_only_commands_do_not_reach_the_reader(core, engine_standins) -> None:
    state(core, ["SR-040"])
    for text in ("/iaso go", "/iaso undo SR-040"):
        digest = log_prompt(core, text)
        assert read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text}) is None
    assert list(files.jobs_dir(core.root, SESSION).glob("*.json")) == []


def test_a_command_approval_must_be_the_typed_command_for_those_records(core) -> None:
    """The re-check of a past ``via: command`` approval is the parse check, not affirmation
    words (the command is gone; its entries are still re-checked)."""
    from iaso.confirm import checked
    from iaso.normalize import sha256_text

    def write(quote: str, record: str) -> None:
        digest = log_prompt(core, quote)
        core.log_append("events", "prompt", {"digest": digest, "session": SESSION, "at": "t"})
        core.log_append("events", "approval", {
            "records": [{"id": record, "hash": core.index()[record].hash}],
            "by": "agent-relayed", "via": "command", "prompt_digest": digest, "quote": quote,
            "quote_digest": sha256_text(quote), "affirmation": "approve", "stated_set": None})

    write("/iaso approve SR-040", "SR-040")                  # a typed command naming it
    write("no, do not approve SR-041", "SR-041")             # words with an affirmation term
    write("/iaso approve SR-040", "SR-041")                 # a typed command naming another
    problems = [p for _, p in checked(open_core(core.root)) if p]
    assert len(problems) == 2
    status = open_core(core.root).status(["SR-040", "SR-041"])
    assert (status["SR-040"].confirmation, status["SR-041"].confirmation) == (
        "confirmed", "proposed")
