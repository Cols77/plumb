"""SR-170 (DEC-057): a conflict answered in chat is read by plumb, never relayed."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.fakes import as_worker

from mergedriver.mdhelpers import (
    OURS_STATEMENT,
    THEIRS_STATEMENT,
    conflicted,
    events,
    ex,
    log_prompt,
    parse,
    record,
    shown,
)
from plumb import cli
from plumb.api import open_core
from plumb.understand import read

pytestmark = pytest.mark.sr("SR-170")
SR = ".plumb/requirements/SR-005.md"
SESSION = "test-session"     # mdhelpers.log_prompt's


def _statement(repo: Path) -> str:
    return parse((repo / SR).read_text(encoding="utf-8"))[0]["statement"]


def _reply(repo: Path, words: str, said: str, change: str | None) -> None:
    """The owner's ``words`` read by a stubbed model as ``said`` (with ``change``), applied."""
    core = open_core(repo)
    digest = log_prompt(repo, words)
    job = read.build(core, SESSION, message={"digest": digest, "text": words})
    assert job is not None
    (item,) = [i for i in job.inputs["cards"] if i["kind"] == "conflict"]
    entry = {"id": item["id"], "hash": "", "answer": said, "change": change,
             "evidence": words, "confidence": 0.95}
    with as_worker(repo, SESSION):
        read.apply(core, job, {"entries": [entry]})


def test_ex1_a_clear_pick_in_chat_is_applied_by_plumb(repo: Path) -> None:
    conflicted(repo)
    shown(repo)
    _reply(repo, "keep feat-x's version", "change", "Keep feat-x's version")
    assert _statement(repo) == THEIRS_STATEMENT
    (entry,) = events(repo, "conflict-resolution")
    assert (entry["take"], entry["by"], entry["quote"]) == (
        "theirs", "owner-words", "keep feat-x's version")
    assert entry["prompt"].startswith("sha256:")


def test_ex3_a_change_asked_or_a_refusal_leaves_it_open(repo: Path) -> None:
    conflicted(repo)
    shown(repo)
    before = (repo / SR).read_bytes()
    _reply(repo, "keep feat-x's version but change the title", "change",
           "Keep feat-x's version, with its title changed")
    _reply(repo, "no, not feat-x's", "rejected", None)
    _reply(repo, "keep feat-x's or main's, whatever", "open", None)
    assert (repo / SR).read_bytes() == before
    assert events(repo, "conflict-resolution") == []


def test_a_card_the_owner_was_not_shown_is_not_read(repo: Path) -> None:
    """Only a card the reply before the message showed can be answered in words."""
    conflicted(repo)
    log = log_prompt(repo, "keep feat-x's version")
    assert read.build(open_core(repo), SESSION, message={
        "digest": log, "text": "keep feat-x's version"}) is None
    assert _statement(repo) != THEIRS_STATEMENT


def test_a_changed_card_is_not_answered_by_an_old_reply(repo: Path) -> None:
    conflicted(repo)
    shown(repo)
    # the sides change after the card was shown
    conflicted(repo, ours=record(statement=OURS_STATEMENT + " More.", examples=[ex(1)]))
    digest = log_prompt(repo, "keep feat-x's version")
    assert read.build(open_core(repo), SESSION, message={
        "digest": digest, "text": "keep feat-x's version"}) is None


def test_ex2_the_agent_cannot_relay_the_answer(repo: Path, capsys) -> None:
    conflicted(repo)
    shown(repo)
    before = (repo / SR).read_bytes()
    digest = log_prompt(repo, "keep feat-x's version")
    for argv in (["conflict", "relay", "IC-001", "--take", "theirs", "--prompt", digest,
                  "--quote", "keep feat-x's version"],
                 ["conflict", "relay", "IC-001"],
                 ["conflict", "choose", "IC-001", "--take", "theirs", "--prompt", digest,
                  "--quote", "keep feat-x's version"]):
        assert cli.main([*argv, "--root", str(repo)]) == 3
        assert "nothing was chosen" in capsys.readouterr().err
    assert (repo / SR).read_bytes() == before
    assert events(repo, "conflict-resolution") == []
