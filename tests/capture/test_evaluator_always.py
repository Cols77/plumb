"""SR-434, DEC-464: the owner's standing choice that the evaluator checks every proof."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import log_prompt

from iaso.api import open_core
from iaso.capture import evaluatorpref, proof
from iaso.capture.records import CaptureError
from iaso.contracts import Target
from iaso.understand import typed

pytestmark = pytest.mark.sr("SR-434")

INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\nreadback: Ground the work.\n---\n"
SR = "---\nid: SR-001\ntitle: Thing\nstatement: The thing works.\n---\n"


@pytest.fixture
def repo_core(repo: Path, write_record):
    write_record(repo, INT)
    write_record(repo, SR)
    c = open_core(repo)
    c.add_link("SR-001", "derives_from", Target(record="INT-001"))
    proof.set_plan(c, "SR-001", "run the thing", "command")
    return open_core(repo)


def _type(repo: Path, text: str) -> None:
    core = open_core(repo)
    digest = log_prompt(repo, text)
    typed.switch_now(core, typed.parse(text), digest)


def _picked(repo: Path) -> bool:
    core = open_core(repo)
    return proof.evaluator_picked(core.index()["SR-001"], core)


def test_ex3_off_by_default_the_pick_is_refused(repo_core) -> None:
    assert not _picked(Path(repo_core.root))
    with pytest.raises(CaptureError):
        proof.require_pick(repo_core)


def test_ex1_ex2_ex4_typed_always_is_the_pick_for_every_proof(repo_core) -> None:
    repo = Path(repo_core.root)
    _type(repo, "/iaso evaluator always")
    assert _picked(repo)
    proof.require_pick(open_core(repo))      # no refusal, no answer of the loop needed


def test_ex6_typed_ask_switches_it_back(repo_core) -> None:
    repo = Path(repo_core.root)
    _type(repo, "/iaso evaluator always")
    _type(repo, "/iaso evaluator ask")
    assert not _picked(repo)


def test_ex5_an_event_without_the_owners_typed_words_switches_nothing(repo_core) -> None:
    repo = Path(repo_core.root)
    text = "/iaso evaluator ask"                # the digest and quote say ask, the event says always
    digest = log_prompt(repo, text)
    repo_core.log_append("events", "config", {
        evaluatorpref.KEY: "always", "by": "owner", "via": "typed",
        "prompt_digest": digest, "quote": text})
    assert not _picked(repo)
    repo_core.log_append("events", "config", {evaluatorpref.KEY: "always", "by": "agent"})
    assert not _picked(repo)


def test_ex5_the_terminal_command_writes_nothing_in_an_agents_shell(
        repo_core, monkeypatch) -> None:
    from capture_helpers import agent_shell_setup, run

    repo = Path(repo_core.root)
    agent_shell_setup(monkeypatch)
    assert run(repo, "config", "evaluator", "always") != 0
    assert not _picked(repo)
