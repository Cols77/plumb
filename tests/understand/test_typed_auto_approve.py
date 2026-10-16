"""SR-115 EX-3: auto-approve named in a sentence switches nothing; the words go to the reader
as prose. The grammar of the typed /plumb auto-approve on|off."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.test_read_job import (
    SESSION,
    ctx_for,
    log_prompt,
    make_core,
    record_text,
    state,
)

from plumb.api import open_core
from plumb.capture.autoapprove import auto_approve_state
from plumb.understand import files, read, typed

pytestmark = pytest.mark.sr("SR-250")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(40)])


def test_ex3_a_sentence_mentioning_it_changes_nothing(core, engine_standins) -> None:
    state(core, ["SR-040"])                        # the reader has a record to read against
    text = "please turn auto-approve on, thanks"
    assert typed.parse(text) is None
    digest = log_prompt(core, text)
    job_id = read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text})
    assert job_id is not None                      # the reader reads it as prose
    assert (files.jobs_dir(core.root, SESSION) / f"{job_id}.json").exists()
    after = open_core(core.root)
    assert [e for e in after.events() if e.kind == "config"] == []
    assert not auto_approve_state(after).configured


def test_ex1_typed_command_does_not_reach_the_reader(core, engine_standins) -> None:
    text = "/plumb auto-approve on"
    digest = log_prompt(core, text)
    assert read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text}) is None
    assert list(files.jobs_dir(core.root, SESSION).glob("*.json")) == []
    (entry,) = [e for e in open_core(core.root).events() if e.kind == "config"]
    assert entry.payload["via"] == "typed" and entry.payload["by"] == "owner"


@pytest.mark.parametrize("text,state", [
    ("/plumb auto-approve on", "on"), ("  /plumb auto-approve off \n", "off"),
    ("/plumb auto-approve  on", "on")])
def test_grammar(text: str, state: str) -> None:
    parsed = typed.parse(text)
    assert (parsed.command, parsed.state) == ("auto-approve", state)


@pytest.mark.parametrize("text", [
    "/plumb auto-approve", "/plumb auto-approve maybe", "/plumb auto-approve on now",
    "please /plumb auto-approve on", "/plumb auto-approve ON", "plumb auto-approve on",
    "/plumb auto approve on"])
def test_grammar_rejects(text: str) -> None:
    assert typed.parse(text) is None
