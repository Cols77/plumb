"""SR-368: a study asked in plain words is offered by plumb's prompt hook itself, so the agent
never has to find out how plumb makes studies."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fakes import FakeBackend, FakeVerify

from plumb import study
from plumb.hosts.claude_code import prompt

pytestmark = pytest.mark.sr("SR-368")


@pytest.fixture(autouse=True)
def _without_the_understanding_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])


def _run(repo: Path, hook_input, text: str) -> str:
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=text, session_id="s1")
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo,
                       verify=FakeVerify(), backend=FakeBackend()) == 0
    return out.getvalue()


def test_ex1_a_study_asked_in_plain_words_is_offered_on_the_band(repo: Path,
                                                                 hook_input) -> None:
    out = _run(repo, hook_input, "I'd like a study of how merges are held.")
    [idea] = study.studies(repo)
    assert (idea["title"], idea["status"], idea["recommend"]) == (
        "how merges are held", "idea", "diagrams")
    assert "the study idea 'how merges are held' is on the band" in out
    assert "write nothing until the owner accepts it" in out


@pytest.mark.parametrize("text", ["make me a study about the judge",
                                  "study room on the judge", "/plumb study the judge"])
def test_ex1_other_plain_words_offer_it_too(repo: Path, hook_input, text: str) -> None:
    _run(repo, hook_input, text)
    assert [s["title"] for s in study.studies(repo)] == ["the judge"]


def test_ex2_study_as_a_verb_offers_nothing(repo: Path, hook_input) -> None:
    out = _run(repo, hook_input, "study the failing test and fix it")
    assert study.studies(repo) == []
    assert "study idea" not in out


def test_an_idea_already_waiting_is_said_and_nothing_more_is_offered(repo: Path,
                                                                     hook_input) -> None:
    _run(repo, hook_input, "a study on merges")
    out = _run(repo, hook_input, "a study on the judge")
    assert [s["title"] for s in study.studies(repo)] == ["merges"]
    assert "'merges' already waits on the band" in out
