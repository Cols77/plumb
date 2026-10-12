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
from plumb.understand import clarify, files, gate, hooks, read, recheck_settled, settle, typed
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
from understand.test_recheck_settled import problem, settled_world, undo_entry

pytestmark = pytest.mark.sr("SR-120")

NEGATIVES = ["/plumbing go", "/plumb:other go", "/plumb:plumbing go", "/plumb:plumb:plumb go",
             "/plumb:go", "/plumb:plumbgo", "plumb:plumb go", "/Plumb:plumb go"]


@pytest.fixture(autouse=True)
def in_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)


# ---- the grammar ----------------------------------------------------------------------------


@pytest.mark.parametrize("words", ["approve SR-034", "confirm SR-034, DEC-017", "go",
                                   "auto-approve on", "auto-approve off",
                                   "settle on intent", "settle off requirement", "undo SR-001"])
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
    assert settle.TYPED.match("/plumb:plumb settle off intent").group(1, 2) == ("off", "intent")
    assert recheck_settled.UNDO.match("/plumb:plumb undo Operation 1").group(1) == "Operation 1"
    for check, words in ((ownerconfig.TYPED, "auto-approve on"),
                         (settle.TYPED, "settle on intent"), (recheck_settled.UNDO, "undo X")):
        for head in ("/plumbing", "/plumb:other", "/plumb:plumbing"):
            assert check.match(f"{head} {words}") is None, (head, words)


@pytest.mark.parametrize("text,expected", [
    ("/plumb:plumb settle on intent", "/plumb settle on intent"),
    ("  /plumb:plumb undo Operation 1", "/plumb undo Operation 1"),
    ("/plumb settle on intent", "/plumb settle on intent"),
    ("/plumb:other settle on intent", "/plumb:other settle on intent"),
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


def test_namespaced_settle_in_an_entry_counts(repo: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.approvals import prompt_digest

    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    for quote, on in (("/plumb:other settle on requirement", False),
                      ("/plumb:plumb settle on requirement", True)):
        open_core(repo).log_append("events", "settle-config", {
            "kind": "requirement", "on": True, "via": "typed", "calibration": "",
            "quote": quote, "prompt_digest": prompt_digest(quote)})
        assert settle.state(open_core(repo), "requirement").on is on, quote


def test_namespaced_undo_in_an_entry_counts(repo: Path, write_record,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.approvals import prompt_digest

    settled_world(repo, write_record)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    lookalike = "/plumb:other undo Operation 1"
    assert problem(repo, undo_entry(repo, quote=lookalike,
                                    prompt_digest=prompt_digest(lookalike))) is not None
    typed_undo = "/plumb:plumb undo Operation 1"
    proven = undo_entry(repo, quote=typed_undo, prompt_digest=prompt_digest(typed_undo))
    assert problem(repo, proven) is None
    assert open_core(repo).status(["SR-001"])["SR-001"].confirmation == "proposed"


# ---- the command the agent runs for a typed settle or undo --------------------------------


def test_namespaced_settle_through_the_command_switches_and_keeps_the_quote(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent runs ``plumb settle on intent --prompt <digest>`` for the owner's
    ``/plumb:plumb settle on intent``: it is the owner's command, and the entry quotes it."""
    from plumb.understand import cmd_settle
    from understand.test_judge_job import log_prompt as log_hook
    from understand.test_settle_switch import configs

    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    digest = log_hook(repo, "/plumb:plumb settle on intent")
    assert cmd_settle.run("settle", ["on", "intent", "--prompt", digest,
                                     "--root", str(repo)]) == 0
    assert settle.state(open_core(repo), "intent").on is True
    entry = configs(repo, "intent")[-1]
    assert entry.payload["quote"] == "/plumb:plumb settle on intent"
    assert recheck_settled.problem(entry, open_core(repo)) is None


@pytest.mark.parametrize("text", ["/plumb:other settle on intent", "/plumbing settle on intent"])
def test_lookalike_settle_through_the_command_is_refused(
        repo: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    from plumb.understand import cmd_settle
    from understand.test_judge_job import log_prompt as log_hook

    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    digest = log_hook(repo, text)
    assert cmd_settle.run("settle", ["on", "intent", "--prompt", digest,
                                     "--root", str(repo)]) == 3
    assert settle.state(open_core(repo), "intent").on is False


def test_namespaced_undo_through_the_command_takes_the_record_back(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import cmd_settle
    from understand.test_judge_job import log_prompt as log_hook

    settled_world(repo, write_record)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    digest = log_hook(repo, "/plumb:plumb undo SR-001")
    assert cmd_settle.run("undo", ["SR-001", "--prompt", digest, "--root", str(repo)]) == 0
    assert len([e for e in open_core(repo).events() if e.kind == "revocation"]) == 1


# ---- one case rule for every parser: lower case, as typed.parse ----------------------------

@pytest.mark.parametrize("text", ["/PLUMB settle on intent", "/Plumb:plumb settle on intent",
                                  "/PLUMB:plumb settle on intent", "/plumb SETTLE on intent"])
def test_settle_in_another_case_is_not_the_typed_command(
        repo: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """``/plumb Approve SR-034`` is not a typed command (typed.parse), so neither is
    ``/PLUMB settle on``: the entry check, the undo check and the command agree."""
    from plumb.understand import cmd_settle
    from understand.test_judge_job import log_prompt as log_hook

    assert typed.parse(text) is None
    assert settle.TYPED.match(text) is None
    assert recheck_settled.UNDO.match(text.replace("settle on intent", "undo SR-001")) is None
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    digest = log_hook(repo, text)
    assert cmd_settle.run("settle", ["on", "intent", "--prompt", digest,
                                     "--root", str(repo)]) == 3
    assert settle.state(open_core(repo), "intent").on is False


def test_undo_title_words_keep_any_case() -> None:
    """Only the head is exact: the owner's words for the record may be in any case."""
    from plumb.understand import cmd_settle

    assert cmd_settle._same_command("/plumb undo Operation 1", "/plumb undo operation 1")
    assert cmd_settle._same_command("/plumb:plumb  undo SR-001", "/plumb undo SR-001")
    assert not cmd_settle._same_command("/PLUMB undo SR-001", "/plumb undo SR-001")
    assert not cmd_settle._same_command("/plumb Undo SR-001", "/plumb undo SR-001")
