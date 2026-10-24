"""A study the owner asks for (SR-355): ``plumb study propose --asked``, any time, loop or not,
outside the limits on plumb's own proposals; the owner still picks the depth on the band."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand import test_intent_loop
from understand.test_intent_loop import SESSION

from plumb import study
from plumb.browser.service import BrowserService
from plumb.study import cli

pytestmark = pytest.mark.sr("SR-355")

intent = test_intent_loop.intent   # an open loop at its clarify step


def _propose(repo: Path, title: str, *extra: str) -> int:
    return cli.run("study", ["propose", "--title", title, "--why", "the owner asked",
                             "--depth", "diagrams", *extra, "--root", str(repo),
                             "--session", SESSION])


def test_ex1_asked_with_no_loop_open_is_offered_and_nothing_written(repo: Path) -> None:
    assert _propose(repo, "How merges are held") != 0      # plumb's own proposal needs a loop
    assert _propose(repo, "How merges are held", "--asked") == 0
    [held] = study.studies(repo)
    assert (held["status"], held["recommend"], held["body"]) == ("idea", "diagrams", "")
    assert BrowserService(repo).studies()["studies"] == []


def test_ex2_the_steps_limit_holds_only_plumbs_own_proposals(intent: Path) -> None:
    assert _propose(intent, "How plumb's background jobs run") == 0
    assert _propose(intent, "Another topic") != 0
    assert _propose(intent, "Another topic", "--asked") == 0
    assert [s["status"] for s in study.studies(intent)] == ["idea", "idea"]


def test_ex3_known_or_declined_topics_are_offered_when_asked(intent: Path) -> None:
    study.save_picture(intent, "- knows: merges\n")
    assert _propose(intent, "Merges", "--topic", "merges") != 0
    assert _propose(intent, "Merges", "--topic", "merges", "--asked") == 0
    slug = next(s["slug"] for s in study.studies(intent) if s["status"] == "idea")
    study.choose(intent, slug, None)
    assert _propose(intent, "Merges again", "--topic", "merges", "--asked") == 0


def test_ex4_picked_at_diagrams_it_is_written_and_the_room_shows_it(repo: Path,
                                                                   tmp_path: Path) -> None:
    assert _propose(repo, "How merges are held", "--asked") == 0
    slug = study.studies(repo)[0]["slug"]
    assert study.choose(repo, slug, "diagrams")["status"] == "accepted"
    body = tmp_path / "body.md"
    body.write_text("In plain words.\n\n```mermaid\nflowchart LR\n a --> b\n```\n",
                    encoding="utf-8")
    assert cli.run("study", ["add", slug, "--file", str(body), "--root", str(repo),
                             "--session", SESSION]) == 0
    [shown] = BrowserService(repo).studies()["studies"]
    assert (shown["slug"], shown["depth"]) == (slug, "diagrams")
