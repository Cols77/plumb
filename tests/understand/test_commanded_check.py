"""SR-171: the request check runs only for a typed /plumb clarify <words>."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt
from understand.test_read_job import open_question

from plumb.api import open_core
from plumb.understand import files, gate, hooks

pytestmark = pytest.mark.sr("SR-222")

SESSION = "s1"
WORDS = "make the status line show the branch name"


def _say(repo: Path, text: str) -> None:
    core = open_core(repo)
    digest = log_prompt(repo, text, session=SESSION)
    hooks.on_prompt(SimpleNamespace(session_id=SESSION), core, {"digest": digest, "text": text})


def _jobs(repo: Path) -> list[str]:
    return sorted(p.stem for p in files.jobs_dir(repo, SESSION).glob("*.json"))


def test_ex1_an_ordinary_message_with_no_question_runs_nothing(repo: Path, engine_standins: Any) -> None:
    _say(repo, WORDS)
    assert _jobs(repo) == [] and not gate.is_closed(repo, SESSION)


def test_ex2_the_command_checks_the_words_and_holds_edits(repo: Path, engine_standins: Any) -> None:
    _say(repo, "/plumb clarify " + WORDS)
    assert [j for j in _jobs(repo) if j.startswith("clarify-")] and gate.is_closed(repo, SESSION)


def test_ex3_a_waiting_question_has_the_message_read_and_no_check(
        repo: Path, write_record: Any, engine_standins: Any) -> None:
    from understand.test_read_job import make_core, record_text

    open_question(make_core(repo, write_record, [record_text(1)]))
    _say(repo, "go with the first option")
    jobs = _jobs(repo)
    assert any(j.startswith("read-") for j in jobs)
    assert not any(j.startswith("clarify-") for j in jobs) and not gate.is_closed(repo, SESSION)


def test_ex4_the_prompt_tells_the_check_not_to_steer_and_to_use_the_last_message() -> None:
    from plumb.understand import clarify

    prompt = (Path(clarify.__file__).parent / "agents" / "clarify.md").read_text(encoding="utf-8")
    for words in ("how to carry out work already asked for", "raise no gap",
                  "most recent earlier message: read it", "never supply the options"):
        assert " ".join(prompt.split()).count(words), words


def test_ex5_shown_records_have_the_message_read_with_no_card(repo: Path, write_record: Any,
                                                              engine_standins: Any) -> None:
    from understand.test_read_job import make_core, record_text, state

    state(make_core(repo, write_record, [record_text(40)]), ["SR-040"], at="2026-10-05T09:00:00Z")                 # SR-101: the previous reply showed a record
    _say(repo, "SR-040 ok")
    jobs = _jobs(repo)
    assert any(j.startswith("read-") for j in jobs) and not any(j.startswith("clarify-") for j in jobs)
