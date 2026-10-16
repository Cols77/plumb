"""SR-120: under the Claude Code plugin the command is namespaced, so the owner may type
/plumb:plumb where they would type /plumb. Every parser of the owner's typed command takes both
(EX-2), and nothing else that merely starts like it (EX-3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.capture import ownerconfig
from plumb.capture.autoapprove import auto_approve_state
from plumb.understand import clarify, files, gate, hooks, read, typed
from understand.test_clarify_release import SESSION as GO_SESSION
from understand.test_clarify_release import _ctx, _entries, _failed_check
from understand.test_read_job import (
    SESSION,
    ctx_for,
    log_prompt,
    make_core,
    record_text,
    state,
)

pytestmark = pytest.mark.sr("SR-202")

NEGATIVES = ["/plumbing go", "/plumb:other go", "/plumb:plumbing go", "/plumb:plumb:plumb go",
             "/plumb:go", "/plumb:plumbgo", "plumb:plumb go", "/Plumb:plumb go"]


@pytest.fixture(autouse=True)
def in_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)


# ---- the grammar ----------------------------------------------------------------------------


@pytest.mark.parametrize("words", ["approve SR-034", "confirm SR-034, DEC-017", "go",
                                   "auto-approve on", "auto-approve off",
                                   "undo SR-001"])
def test_both_spellings_parse_the_same(words: str) -> None:
    plain = typed.parse(f"/plumb {words}")
    assert plain is not None
    assert typed.parse(f"/plumb:plumb {words}") == plain
    assert typed.parse(f"  /plumb:plumb\t{words}\n") == plain


@pytest.mark.parametrize("text", NEGATIVES + ["/plumbing approve SR-034",
                                              "/plumb:other approve SR-034",
                                              "/plumb:plumb", "/plumb:plumbapprove SR-034"])
def test_other_slash_words_are_not_the_command(text: str) -> None:
    assert typed.parse(text) is None


@pytest.mark.parametrize("text", NEGATIVES)
def test_go_needs_one_of_the_two_spellings(text: str) -> None:
    assert clarify.is_typed_go("/plumb go") and clarify.is_typed_go("/plumb:plumb go")
    assert not clarify.is_typed_go(text)


def test_each_owner_check_takes_the_namespaced_spelling() -> None:
    assert ownerconfig.TYPED.match("/plumb:plumb auto-approve on").group(1) == "on"
    for head in ("/plumbing", "/plumb:other", "/plumb:plumbing"):
        assert ownerconfig.TYPED.match(f"{head} auto-approve on") is None, head


@pytest.mark.parametrize("text,expected", [
    ("/plumb:plumb undo SR-001", "/plumb undo SR-001"),
    ("  /plumb:plumb undo SR-001", "/plumb undo SR-001"),
    ("/plumb:other undo SR-001", "/plumb:other undo SR-001"),
    ("/plumb:plumbing go", "/plumb:plumbing go"),
    ("", "")])
def test_canonical_spells_the_namespaced_prefix_plain(text: str, expected: str) -> None:
    assert typed.canonical(text) == expected


# ---- what each typed command does -----------------------------------------------------------


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(34)])


def test_ex2_namespaced_approve_confirms_at_once(core, engine_standins) -> None:
    state(core, ["SR-034"])
    text = "/plumb:plumb approve SR-034"
    digest = log_prompt(core, text)
    assert read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text}) is None
    assert list(files.jobs_dir(core.root, SESSION).glob("*.json")) == []   # reader not called
    after = open_core(core.root)
    assert after.status(["SR-034"])["SR-034"].confirmation == "confirmed"
    (entry,) = [e for e in after.events() if e.kind == "approval"]
    assert entry.payload["quote"] == text and entry.payload["via"] == "command"
    from plumb.confirm import entry_problem

    # the re-check of the written approval reads the namespaced quote as the typed command
    prompts = {e.payload.get("digest") for e in after.events() if e.kind == "prompt"}
    assert entry_problem(entry, prompts, ()) is None


def test_ex3_plumbing_approve_confirms_nothing(core, engine_standins) -> None:
    state(core, ["SR-034"])
    for text in ("/plumbing approve SR-034", "/plumb:other approve SR-034"):
        digest = log_prompt(core, text)
        read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text})
    after = open_core(core.root)
    assert after.status(["SR-034"])["SR-034"].confirmation != "confirmed"
    assert [e for e in after.events() if e.kind == "approval"] == []


def test_namespaced_auto_approve_switches_and_counts_as_the_owners(core,
                                                                  engine_standins) -> None:
    text = "/plumb:plumb auto-approve on"
    digest = log_prompt(core, text)
    assert read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text}) is None
    after = open_core(core.root)
    (entry,) = [e for e in after.events() if e.kind == "config"]
    assert entry.payload["via"] == "typed" and ownerconfig.typed_proof(entry)
    assert ownerconfig.latest(list(after.events())) == entry
    assert auto_approve_state(after).configured


def test_ex3_namespaced_lookalike_switches_nothing(core, engine_standins) -> None:
    text = "/plumb:other auto-approve on"
    digest = log_prompt(core, text)
    read.on_prompt(ctx_for(core), core, {"digest": digest, "text": text})
    assert [e for e in open_core(core.root).events() if e.kind == "config"] == []


def test_namespaced_go_releases_a_failed_check(repo: Path, engine_standins: Any) -> None:
    from capture.capture_helpers import log_prompt as hook_prompt

    _failed_check(repo, engine_standins)
    text = "/plumb:plumb go"
    go = hook_prompt(repo, text, session=GO_SESSION)
    hooks.on_prompt(_ctx(), open_core(repo), {"digest": go, "text": text})
    assert not gate.is_closed(repo, GO_SESSION)
    assert [e["by"] for e in _entries(repo)] == ["release:typed"]


def test_ex3_plumbing_go_releases_nothing(repo: Path, engine_standins: Any) -> None:
    from capture.capture_helpers import log_prompt as hook_prompt

    _failed_check(repo, engine_standins)
    for text in ("/plumbing go", "/plumb:other go"):
        go = hook_prompt(repo, text, session=GO_SESSION)
        hooks.on_prompt(_ctx(), open_core(repo), {"digest": go, "text": text})
    assert gate.is_closed(repo, GO_SESSION)
    assert [e["by"] for e in _entries(repo)] == []


def test_a_namespaced_undo_entry_counts_only_as_the_typed_undo(repo: Path) -> None:
    """The undo re-check takes both spellings and no look-alike (the whole message, lower case)."""
    from plumb.approvals import prompt_digest
    from plumb.contracts import LogEntry

    def problem(quote: str) -> str | None:
        entry = LogEntry(stream="events", kind="revocation", at="", marker="agent-1",
                         digest="", prev="", payload={
                             "by": "undone", "via": "typed", "quote": quote,
                             "prompt_digest": prompt_digest(quote),
                             "records": [{"id": "SR-001", "hash": "sha256:x"}]})
        return typed.problem(entry, open_core(repo))

    assert problem("/plumb:plumb undo SR-001") is None
    assert problem("/plumb undo SR-001") is None
    for lookalike in ("/plumb:other undo SR-001", "/PLUMB undo SR-001", "/plumb Undo SR-001"):
        assert problem(lookalike) is not None, lookalike


def test_an_undo_entry_must_cite_a_logged_prompt(repo: Path) -> None:
    """Like the owner's words, an undo written under the agent marker rests on a prompt event."""
    from plumb import confirm
    from plumb.approvals import prompt_digest
    from plumb.contracts import LogEntry
    from plumb.log import entry_digest

    quote = "/plumb undo SR-001"
    payload = {"by": "undone", "via": "typed", "quote": quote, "prompt_digest": prompt_digest(quote),
               "records": [{"id": "SR-001", "hash": "sha256:x"}]}
    raw = {"v": 1, "kind": "revocation", "at": "t", "marker": "agent-1", "payload": payload,
           "prev": None}
    entry = LogEntry("events", "revocation", "t", "agent-1", payload, None, entry_digest(raw))
    core = open_core(repo)
    assert "cites no earlier prompt" in (confirm.entry_problem(entry, set(), (), core) or "")
    assert confirm.entry_problem(entry, {prompt_digest(quote)}, (), core) is None
