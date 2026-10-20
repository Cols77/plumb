"""Studies and the understanding picture (SR-292, SR-293, SR-294; DEC-207): ``plumb study
propose|add|list|candidates|mark``, at most one study idea per loop step, none on a topic the
owner knows, written only once the owner accepts it at a depth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from capture.capture_helpers import log_prompt
from mergedriver.mdhelpers import conflicted
from mod.helpers import DIGEST, KEY, run_mod
from understand import test_intent_loop
from understand.test_intent_loop import SESSION, _findings

from plumb import study
from plumb.api import open_core
from plumb.mergedriver import conflicts
from plumb.study import cli
from plumb.understand import cmd_intent
from study.helpers import written

pytestmark = pytest.mark.sr("SR-292")

intent = test_intent_loop.intent   # INT-001, SR-040 deriving from it, and an open loop


def _study(repo: Path, *argv: str) -> int:
    return cli.run("study", [*argv, "--root", str(repo), "--session", SESSION])


DIAGRAM = "How it works, in plain words.\n\n```mermaid\nflowchart LR\n a --> b\n```\n"


def _body(tmp_path: Path, text: str = DIAGRAM) -> Path:
    body = tmp_path / "body.md"
    body.write_text(text, encoding="utf-8")
    return body


def _add(repo: Path, tmp_path: Path, title: str, topic: str | None = None) -> int:
    """Proposed, accepted with diagrams, written."""
    return written(repo, SESSION, title, "you choose here next", _body(tmp_path), topic)


def _propose(repo: Path, title: str, topic: str | None = None, depth: str = "diagrams") -> int:
    return _study(repo, "propose", "--title", title, "--why", "the plan adds a job",
                  "--depth", depth, *(["--topic", topic] if topic else []))


def _idea(repo: Path) -> str:
    return next(s["slug"] for s in study.studies(repo) if s["status"] == "idea")


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


@pytest.mark.sr("SR-293")
def test_sr293_ex6_a_passed_gate_tells_the_agent_to_pick_the_steps_study(
        intent: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """SR-293 EX-6: a gate that passes ends by telling the agent to pick the new step's study
    (candidates, then one idea or none); nothing once the step has its idea."""
    low = _findings(tmp_path, "low")
    capsys.readouterr()
    assert test_intent_loop._run(intent, "gate", "clarify", "--intent", "INT-001",
                                 "--findings", low) == 0
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("plumb: pick the plan step's study") and "study candidates" in last
    assert "study propose" in last and "nothing" in last
    assert _propose(intent, "How plumb's background jobs run") == 0
    capsys.readouterr()
    assert test_intent_loop._run(intent, "gate", "clarify", "--intent", "INT-001",
                                 "--findings", low) == 0
    assert "study" not in capsys.readouterr().out      # the plan step already has its idea
    assert test_intent_loop._run(intent, "gate", "plan", "--intent", "INT-001",
                                 "--findings", low) == 0
    assert "pick the build step's study" in capsys.readouterr().out


@pytest.mark.sr("SR-336")
def test_sr336_ex3_no_question_waits_the_step_study_as_before(
        intent: Path, capsys: pytest.CaptureFixture) -> None:
    """SR-336 EX-3: no question waits: nothing to study ahead of, and the step's study of
    general interest is proposed as DEC-207 has it, one per step."""
    assert _candidates(intent, capsys)["waiting"] == []
    assert _propose(intent, "How plumb's background jobs run") == 0
    [held] = study.studies(intent)
    assert (held["step"], held["status"], "serves" in held) == ("clarify", "idea", False)
    assert _propose(intent, "Another study", "other") != 0


@pytest.mark.sr("SR-293")
def test_sr293_ex6_a_proposed_study_is_only_an_idea(intent: Path) -> None:
    """SR-293 EX-6: proposing writes the idea (title, why, recommended depth), no page."""
    assert _propose(intent, "How plumb's background jobs run", "background jobs") == 0
    [held] = study.studies(intent)
    assert {k: held[k] for k in ("title", "why", "recommend", "status", "body")} == {
        "title": "How plumb's background jobs run", "why": "the plan adds a job",
        "recommend": "diagrams", "status": "idea", "body": ""}
    # it holds the step (EX-5) and cannot be written before the owner accepts it
    assert _propose(intent, "Another study", "other") != 0
    with pytest.raises(ValueError, match="not accepted"):
        study.add(intent, held["slug"], DIAGRAM)


@pytest.mark.sr("SR-293")
def test_sr293_ex7_accepted_with_diagrams_the_study_has_its_diagram(intent: Path,
                                                                    tmp_path: Path) -> None:
    """SR-293 EX-7: accepted at 'diagrams', the study is written in plain words with them."""
    assert _propose(intent, "How plumb's background jobs run") == 0
    slug = _idea(intent)
    assert study.choose(intent, slug, "diagrams")["status"] == "accepted"
    assert _study(intent, "add", slug, "--file", str(_body(tmp_path))) == 0
    held = study.get(intent, slug)
    assert (held["status"], held["depth"]) == ("new", "diagrams")
    assert "```mermaid" in held["body"]


@pytest.mark.sr("SR-293")
def test_sr293_ex8_markdown_only_has_no_diagram(intent: Path, tmp_path: Path) -> None:
    """SR-293 EX-8: 'Markdown only' chosen where diagrams were recommended: no diagram."""
    assert _propose(intent, "How plumb's background jobs run", depth="diagrams") == 0
    slug = _idea(intent)
    study.choose(intent, slug, "md")
    assert _study(intent, "add", slug, "--file", str(_body(tmp_path))) != 0   # has a diagram
    assert study.get(intent, slug)["status"] == "accepted"
    plain = _body(tmp_path, "How it works, in plain words, with a table.\n")
    assert _study(intent, "add", slug, "--file", str(plain)) == 0
    assert "```mermaid" not in study.get(intent, slug)["body"]


@pytest.mark.sr("SR-293")
def test_sr293_ex9_a_declined_idea_is_never_proposed_again(intent: Path, tmp_path: Path,
                                                          capsys: pytest.CaptureFixture) -> None:
    """SR-293 EX-9: 'not now': nothing written, and the idea is not proposed again."""
    assert _propose(intent, "How plumb's background jobs run", "background jobs") == 0
    slug = _idea(intent)
    assert study.choose(intent, slug, None)["status"] == "declined"
    assert study.get(intent, slug)["body"] == ""
    _next_step(intent, tmp_path, "clarify")
    assert _candidates(intent, capsys)["declined"] == ["background jobs"]
    assert _propose(intent, "Background jobs, again", "Background  Jobs") != 0
    assert _propose(intent, "How plumb's background jobs run", "the dispatcher") != 0
    assert [s["status"] for s in study.studies(intent)] == ["declined"]


@pytest.mark.sr("SR-294")
def test_sr294_ex8_the_next_turn_tells_the_agent_the_accepted_depth(
        intent: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    """SR-294 EX-8: the owner chose 'with diagrams' in the band (``plumb mod study``, the key
    on stdin); the agent's next turn is told the idea was accepted at that depth."""
    from types import SimpleNamespace

    from plumb.understand.hooks import on_prompt

    assert _propose(intent, "How plumb's background jobs run") == 0
    slug = _idea(intent)
    assert run_mod(monkeypatch, capsys, intent, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, answer, _ = run_mod(monkeypatch, capsys, intent, "study", "--study", slug,
                              "--depth", "diagrams", stdin={"key": KEY})
    assert code == 0 and answer == {"slug": slug, "status": "accepted", "depth": "diagrams"}
    lines = on_prompt(SimpleNamespace(root=intent, session_id=SESSION), None, {})
    assert lines[0] == ("plumb: the owner accepted the study idea 'How plumb's background jobs "
                        f"run' at depth diagrams: write it now with plumb study add {slug} "
                        "--file <body.md>")
    assert _candidates(intent, capsys)["accepted"] == [
        {"slug": slug, "title": "How plumb's background jobs run", "depth": "diagrams"}]


@pytest.mark.sr("SR-294")
@pytest.mark.parametrize("how", ["no key", "the agent's marker", "video", "twice"])
def test_sr294_ex7_only_the_owners_press_chooses_and_video_waits(
        intent: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        how: str) -> None:
    """SR-294 EX-7: the choice is the panel's key-checked press; video is not offered yet."""
    assert _propose(intent, "How plumb's background jobs run") == 0
    slug = _idea(intent)
    assert run_mod(monkeypatch, capsys, intent, "hello", stdin={"key_digest": DIGEST})[0] == 0
    if how == "the agent's marker":
        monkeypatch.setenv("PLUMB_AGENT_SESSION", SESSION)
    if how == "twice":
        study.choose(intent, slug, None)
    code = run_mod(monkeypatch, capsys, intent, "study", "--study", slug, "--depth",
                   "video" if how == "video" else "md",
                   stdin={} if how == "no key" else {"key": KEY})[0]
    assert code == (3 if how in ("no key", "the agent's marker") else 2)
    assert study.get(intent, slug)["status"] == ("declined" if how == "twice" else "idea")


@pytest.mark.sr("SR-294")
def test_sr294_ex9_not_now_writes_nothing_and_the_room_lists_no_idea(intent: Path) -> None:
    """SR-294 EX-9: 'not now' leaves no page; an idea is never a study of the room's."""
    from plumb.browser.service import BrowserService

    assert _propose(intent, "How plumb's background jobs run") == 0
    slug = _idea(intent)
    assert BrowserService(intent).studies()["studies"] == []
    with pytest.raises(LookupError):
        study.mark(intent, slug, "opened")
    study.choose(intent, slug, None)
    assert BrowserService(intent).studies()["studies"] == []
    assert study.get(intent, slug)["body"] == ""
