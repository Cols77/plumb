"""SR-336: questions waiting on a topic the owner's picture does not hold get one study proposed
ahead of them, and each offers 'Study it first'; chosen, it judges nothing again, the band's
study line names that study and the questions wait until the owner has read it. With no
question waiting, a step's study is proposed as DEC-207 has it."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from host.test_answer_rejudge import judge_jobs, world  # noqa: F401
from mod.helpers import DIGEST, KEY, run_mod
from study.helpers import drawn
from understand.test_judge_job import SESSION

from iaso import study
from iaso.api import open_core
from iaso.browser import launch
from iaso.hosts.claude_code import question_answer, snapshot
from iaso.present import owner_text
from iaso.study import cli
from iaso.understand import cmd_clarify, files, judge

pytestmark = pytest.mark.sr("SR-336")

FIRST = {"label": owner_text.STUDY_FIRST, "description": owner_text.STUDY_FIRST_NOTE}
ASKS = ("Does a merge of main into a branch count as the branch's own work?",
        "Should a held merge go to a side branch?",
        "May the merge check refuse a fast-forward?")


@pytest.fixture
def no_browser(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr(launch, "_start", lambda root, token: "http://127.0.0.1:50123")
    monkeypatch.setattr(launch, "_alive", lambda origin, token: False)
    monkeypatch.setattr(launch.webbrowser, "open", opened.append)
    return opened



def _study(repo: Path, *argv: str) -> int:
    return cli.run("study", [*argv, "--root", str(repo), "--session", SESSION])


def asking(repo: Path) -> list[str]:
    """Three open judge questions on the merge boundary, each its own principle; their keys."""
    hash_ = open_core(repo).index()["SR-001"].hash
    files.write_json_atomic(judge.questions_path(repo, SESSION), [
        {"key": judge.question_key(text), "job": "judge-0000000000000000",
         "records": [{"id": "SR-001", "hash": hash_}], "question": text,
         "header": "Merge boundary",
         "options": [{"label": "Yes (Recommended)", "description": "As now."},
                     {"label": "No", "description": "Not any more."}]} for text in ASKS])
    return [judge.question_key(text) for text in ASKS]


def proposed(repo: Path, keys: list[str]) -> str:
    assert _study(repo, "propose", "--title", "Where a merge ends", "--why", "three questions "
                  "hinge on it", "--depth", "diagrams", "--topic", "merge boundary",
                  "--for", *keys) == 0
    (idea,) = study.studies(repo)
    return idea["slug"]


def shown(repo: Path) -> Any:
    return cmd_clarify.wait(open_core(repo), SESSION, timeout=10)


def test_ex1_one_study_ahead_of_three_questions_each_offers_it(
        world: Path, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: F811
    """EX-1: three questions hinge on the merge boundary, which the picture lacks: candidates
    name them, one study is proposed for them (no loop open) and each question offers 'Study
    it first' within its four options; no other study while it waits, none on a known topic."""
    keys = asking(world)
    capsys.readouterr()
    assert _study(world, "candidates", "--json") == 0
    waiting = json.loads(capsys.readouterr().out)["waiting"]
    assert [(q["key"], q["topic"]) for q in waiting] == [(k, "Merge boundary") for k in keys]
    assert _study(world, "propose", "--title", "Something general", "--why", "x",
                  "--depth", "md") != 0        # questions wait: a general study waits too
    slug = proposed(world, keys)
    assert study.get(world, slug)["serves"] == keys and study.get(world, slug)["status"] == "idea"
    assert _study(world, "propose", "--title", "Another", "--why", "x", "--depth", "md",
                  "--for", keys[0]) != 0       # one idea waiting at a time
    outcome = shown(world)
    assert outcome.state == "ask" and len(outcome.questions) == 3
    assert all(q["options"][-1] == FIRST and len(q["options"]) <= 4 for q in outcome.questions)


def test_ex1_never_on_a_topic_the_owner_knows(world: Path) -> None:  # noqa: F811
    keys = asking(world)
    study.save_picture(world, "- knows: merge boundary\n")
    assert _study(world, "propose", "--title", "Where a merge ends", "--why", "x", "--depth",
                  "md", "--topic", "merge boundary", "--for", *keys) != 0
    assert study.studies(world) == []


def test_ex2_chosen_the_band_line_opens_the_study_and_the_questions_wait(
        world: Path, hook_input: Any, no_browser: list[str],  # noqa: F811
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        tmp_path: Path) -> None:
    """EX-2: 'Study it first' chosen: nothing goes to the judge, the band's study line names
    the study and its questions wait (still counted, not asked) until the owner opens it from
    the band; then they are asked again, without the option."""
    keys = asking(world)
    slug = proposed(world, keys)
    put = shown(world).questions[0]
    payload = hook_input("PostToolUse", tool_name="AskUserQuestion",
                         tool_input={"questions": [put]},
                         tool_response={"answers": {put["question"]: FIRST["label"]}},
                         session_id=SESSION)
    assert question_answer.main(stdin=io.StringIO(payload), stdout=io.StringIO(),
                                root=world) == 0
    assert judge_jobs(world) == []
    assert files.read_json(study.first_path(world, SESSION)) == {"study": slug}
    core = open_core(world)
    assert len(judge.open_questions(core, SESSION)) == 3 and snapshot.awaiting_count(core) == 3
    assert shown(world).state == "ready"            # they wait for the study
    study.choose(world, slug, "md")
    body = tmp_path / "body.md"
    body.write_text("A merge ends where main's own files end.\n", encoding="utf-8")
    assert _study(world, "add", slug, "--file", str(body), "--records", *drawn(world, slug)) == 0
    assert run_mod(monkeypatch, capsys, world, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, opened, _ = run_mod(monkeypatch, capsys, world, "room", "--study", slug,
                              stdin={"key": KEY})
    assert code == 0 and opened["status"] == "opened" and len(no_browser) == 1
    again = shown(world)
    assert again.state == "ask" and len(again.questions) == 3
    assert all(FIRST not in q["options"] for q in again.questions)
