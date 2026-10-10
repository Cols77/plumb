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
    open_card,
    record_text,
    state,
)

from plumb.api import open_core
from plumb.present import owner_text
from plumb.understand import files, read, typed

pytestmark = pytest.mark.sr("SR-101")

DEC = ("---\nid: DEC-017\ntitle: Pick a store\nquestion: which store?\noptions:\n- id: A\n"
       "  text: sqlite\nchosen: A\nstatus: proposed\n---\nbody\n")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [DEC, record_text(40), record_text(41)])


def commands_of(core) -> list:
    return [e for e in core.events() if e.kind == "approval"
            and e.payload.get("by") == "agent-relayed"]


def test_ex6_typed_approve_unshown_dec017_confirmed_at_once_reader_not_called(
        core, engine_standins) -> None:
    from understand.test_read_job import clarify_card

    state(core, ["SR-040"])                        # DEC-017 was not shown
    open_card(core, clarify_card())                # a reader job would have had work to do
    text = "/plumb approve DEC-017"
    digest = log_prompt(core, text)
    job_id = read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text})
    assert job_id is None                          # the reader is not called
    assert list(files.jobs_dir(core.root, SESSION).glob("*.json")) == []
    assert engine_standins.dispatcher.jobs == []
    (entry,) = commands_of(core)
    assert entry.payload["via"] == "command" and entry.payload["prompt_digest"] == digest
    assert entry.payload["records"][0]["id"] == "DEC-017"
    after = open_core(core.root)
    assert after.status(["DEC-017"])["DEC-017"].confirmation == "confirmed"
    (line,) = read.confirmation_lines(after, digest)
    assert line == owner_text.TYPED_CONFIRMED.format(titles="Pick a store")


def test_a_typed_command_not_in_the_prompt_log_confirms_nothing(core) -> None:
    parsed = typed.parse("/plumb approve DEC-017")
    result = typed.confirm_now(core, parsed, "sha256:" + "1" * 64, SESSION)
    assert result.confirmed == () and commands_of(core) == []
    # logged by the agent itself (not by the prompt hook): refused too
    digest = log_prompt(core, "/plumb approve DEC-017", via="turn")
    assert typed.confirm_now(core, parsed, digest, SESSION).confirmed == ()
    # the logged words must be the command
    digest = log_prompt(core, "approve everything please")
    assert typed.confirm_now(core, parsed, digest, SESSION).confirmed == ()
    assert commands_of(core) == []


def test_unknown_ids_are_named_not_confirmed(core) -> None:
    digest = log_prompt(core, "/plumb confirm SR-040 SR-999")
    result = typed.confirm_now(core, typed.parse("/plumb confirm SR-040 SR-999"), digest,
                               SESSION)
    assert result.confirmed == ("SR-040",) and result.missing == ("SR-999",)


def test_ex10_typed_confirm_with_words_confirms_nothing(core, engine_standins) -> None:
    state(core, ["SR-040", "SR-041"])
    text = "/plumb confirm the reminder timing"
    parsed = typed.parse(text)
    assert parsed.command == "confirm" and parsed.ids == ()
    assert parsed.words == "the reminder timing"
    digest = log_prompt(core, text)
    assert typed.confirm_now(core, parsed, digest, SESSION).confirmed == ()
    job_id = read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text})
    assert job_id is not None                      # the words go to the reader as prose
    assert commands_of(core) == [] and approvals(open_core(core.root)) == {}
    job = files.job_from_json(files.read_json(files.jobs_dir(core.root, SESSION)
                                              / f"{job_id}.json"))
    assert [i["id"] for i in job.inputs["shown"]] == ["SR-040", "SR-041"]
    assert typed.reply_for(parsed) == owner_text.TYPED_NEEDS_IDS


@pytest.mark.parametrize("text,expected", [
    ("/plumb approve SR-001", ("approve", ("SR-001",), "", "", "")),
    ("  /plumb confirm SR-001, DEC-017 \n", ("confirm", ("SR-001", "DEC-017"), "", "", "")),
    ("/plumb confirm SR-001 and SR-002", ("confirm", (), "SR-001 and SR-002", "", "")),
    ("/plumb approve", ("approve", (), "", "", "")),
    ("/plumb undo SR-001", ("undo", ("SR-001",), "", "", "")),
    ("/plumb settle on intent", ("settle", (), "", "on", "intent")),
    ("/plumb settle off requirement", ("settle", (), "", "off", "requirement")),
    ("/plumb go", ("go", (), "", "", "")),
])
def test_grammar_is_exact(text: str, expected: tuple) -> None:
    parsed = typed.parse(text)
    assert (parsed.command, parsed.ids, parsed.words, parsed.state, parsed.kind) == expected


@pytest.mark.parametrize("text", [
    "plumb approve SR-001", "ok /plumb approve SR-001", "/plumb settle maybe intent",
    "/plumb settle on", "/plumb undo", "/plumb undo SR-001 SR-002", "/plumb go now",
    "/plumbs go", "/Plumb go", "please /plumb go", "/plumb", "/plumb frobnicate SR-001",
    "turn settling on", "", "yes"])
def test_grammar_rejects_everything_else(text: str) -> None:
    assert typed.parse(text) is None


def test_typed_owner_only_commands_do_not_reach_the_reader(core, engine_standins) -> None:
    state(core, ["SR-040"])
    for text in ("/plumb go", "/plumb undo SR-040", "/plumb settle on intent"):
        digest = log_prompt(core, text)
        assert read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text}) is None
    assert list(files.jobs_dir(core.root, SESSION).glob("*.json")) == []


def test_a_command_approval_must_be_the_typed_command_for_those_records(core) -> None:
    """The re-check of a ``via: command`` approval is the parse check, not affirmation words."""
    from plumb.confirm import checked
    from plumb.normalize import sha256_text

    def write(quote: str, record: str) -> None:
        digest = log_prompt(core, quote)
        core.log_append("events", "prompt", {"digest": digest, "session": SESSION, "at": "t"})
        core.log_append("events", "approval", {
            "records": [{"id": record, "hash": core.index()[record].hash}],
            "by": "agent-relayed", "via": "command", "prompt_digest": digest, "quote": quote,
            "quote_digest": sha256_text(quote), "affirmation": "approve", "stated_set": None})

    write("/plumb approve SR-040", "SR-040")                  # a typed command naming it
    write("no, do not approve SR-041", "SR-041")             # words with an affirmation term
    write("/plumb approve SR-040", "SR-041")                 # a typed command naming another
    problems = [p for _, p in checked(open_core(core.root)) if p]
    assert len(problems) == 2
    status = open_core(core.root).status(["SR-040", "SR-041"])
    assert (status["SR-040"].confirmation, status["SR-041"].confirmation) == (
        "confirmed", "proposed")
