"""Studies and the understanding picture (SR-292, SR-293): ``plumb study add|list|candidates|
mark``, at most one study per loop step, none on a topic the owner knows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from capture.capture_helpers import log_prompt
from mergedriver.mdhelpers import conflicted
from understand import test_intent_loop
from understand.test_intent_loop import SESSION, _findings

from plumb import study
from plumb.api import open_core
from plumb.mergedriver import conflicts
from plumb.study import cli
from plumb.understand import cmd_intent

pytestmark = pytest.mark.sr("SR-292")

intent = test_intent_loop.intent   # INT-001, SR-040 deriving from it, and an open loop


def _study(repo: Path, *argv: str) -> int:
    return cli.run("study", [*argv, "--root", str(repo), "--session", SESSION])


def _add(repo: Path, tmp_path: Path, title: str, topic: str | None = None) -> int:
    body = tmp_path / "body.md"
    body.write_text("How it works, in plain words.\n\n```mermaid\nflowchart LR\n a --> b\n```\n",
                    encoding="utf-8")
    return _study(repo, "add", "--title", title, "--why", "you choose here next",
                  "--file", str(body), *(["--topic", topic] if topic else []))


def _candidates(repo: Path, capsys: pytest.CaptureFixture) -> dict[str, Any]:
    capsys.readouterr()
    assert _study(repo, "candidates", "--json") == 0
    return json.loads(capsys.readouterr().out)


def _next_step(repo: Path, tmp_path: Path, stage: str) -> None:
    assert cmd_intent.run("intent", ["gate", stage, "--intent", "INT-001", "--findings",
                                     _findings(tmp_path), "--root", str(repo),
                                     "--session", SESSION]) == 0


def test_a_study_is_written_new_for_the_loop_step(intent: Path, tmp_path: Path) -> None:
    assert _add(intent, tmp_path, "How plumb's background jobs run", "background jobs") == 0
    [held] = study.studies(intent)
    assert {k: held[k] for k in ("title", "topic", "step", "status")} == {
        "title": "How plumb's background jobs run", "topic": "background jobs",
        "step": "clarify", "status": "new"}
    assert "```mermaid" in held["body"]


def test_sr292_ex1_i_know_this_stops_studies_on_the_topic(intent: Path, tmp_path: Path,
                                                         capsys: pytest.CaptureFixture) -> None:
    """SR-292 EX-1: after 'I know this' on a judge cascade study, nothing more on it."""
    assert _add(intent, tmp_path, "How the judge cascade decides", "judge cascade") == 0
    slug = study.studies(intent)[0]["slug"]
    assert _study(intent, "mark", slug, "known") == 0
    assert study.picture(intent)["knows"] == ["judge cascade"]
    _next_step(intent, tmp_path, "clarify")
    found = _candidates(intent, capsys)
    assert "judge cascade" in found["known"]
    assert [r["id"] for r in found["records"]] == ["INT-001", "SR-040"]   # the loop's records
    assert _add(intent, tmp_path, "The judge cascade, again", "Judge  Cascade") != 0
    assert len(study.studies(intent)) == 1


def test_sr292_ex2_go_deeper_makes_a_deeper_study_a_candidate(
        intent: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """SR-292 EX-2: after 'Go deeper' on record links, a deeper study is a candidate."""
    assert _add(intent, tmp_path, "How records link", "record links") == 0
    assert _study(intent, "mark", study.studies(intent)[0]["slug"], "deeper") == 0
    assert study.studies(intent)[0]["status"] == "deeper"
    _next_step(intent, tmp_path, "clarify")
    assert _candidates(intent, capsys)["deeper"] == ["record links (deeper)"]
    assert _add(intent, tmp_path, "Record links in depth", "record links") == 0


def test_sr292_ex3_a_removed_line_makes_the_topic_a_candidate_again(intent: Path,
                                                                   tmp_path: Path) -> None:
    """SR-292 EX-3: the owner removes 'knows: hooks'; hooks studies are candidates again."""
    study.save_picture(intent, "- knows: hooks\n- knows: the judge\n")
    assert _add(intent, tmp_path, "How plumb's hooks run", "hooks") != 0
    study.save_picture(intent, "- knows: the judge\n")
    assert study.picture(intent) == {"knows": ["the judge"], "needs": []}
    assert _add(intent, tmp_path, "How plumb's hooks run", "hooks") == 0


def test_sr292_ex4_a_fresh_project_starts_from_the_prompts(intent: Path,
                                                          capsys: pytest.CaptureFixture) -> None:
    """SR-292 EX-4: no picture yet: the owner's prompts so far, nothing assumed known."""
    log_prompt(intent, "/plumb intent add multiply next to add", session=SESSION)
    assert not study.picture_path(intent).exists()
    found = _candidates(intent, capsys)
    assert found["picture"] == {"knows": [], "needs": []} and found["known"] == []
    assert found["prompts"] == ["/plumb intent add multiply next to add"]
    assert found["loop"]["step"] == "clarify" and not found["loop"]["has_study"]


@pytest.mark.sr("SR-293")
def test_sr293_ex3_none_for_a_step_whose_topic_is_known(intent: Path, tmp_path: Path) -> None:
    """SR-293 EX-3: the picture says the owner knows the step's topic: no study for it."""
    study.save_picture(intent, "- knows: background jobs\n")
    assert _add(intent, tmp_path, "How plumb's background jobs run", "background jobs") != 0
    assert study.studies(intent) == []


@pytest.mark.sr("SR-293")
def test_sr293_ex5_three_steps_at_most_three_studies(intent: Path, tmp_path: Path) -> None:
    """SR-293 EX-5: a loop with three steps proposes at most three studies."""
    for n, stage in enumerate(("clarify", "plan", None)):
        assert _add(intent, tmp_path, f"Study {n} of the step", f"topic {n}") == 0
        assert _add(intent, tmp_path, f"Another study {n}", f"other {n}") != 0
        if stage:
            _next_step(intent, tmp_path, stage)
    assert [s["step"] for s in study.studies(intent)] == ["clarify", "plan", "build"]


@pytest.mark.sr("SR-293")
def test_a_conflict_study_lays_out_both_sides_and_chooses_nothing(
        intent: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """DEC-154: an open conflict is a candidate; its study read and marked settles nothing."""
    ic = conflicted(intent)
    [listed] = _candidates(intent, capsys)["conflicts"]
    assert (listed["ic"], listed["sides"]) == (ic, ["main", "feat-x"])
    assert _add(intent, tmp_path, "Two ways to pin a relay", "relay pins") == 0
    for how in ("opened", "known"):
        assert _study(intent, "mark", study.studies(intent)[0]["slug"], how) == 0
    assert [c.ic for c in conflicts.open_conflicts(open_core(intent))] == [ic]


def test_no_open_loop_no_study(repo: Path, tmp_path: Path) -> None:
    assert _add(repo, tmp_path, "A study outside a loop") == 1
