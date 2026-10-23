"""A judge question the owner answered in a typed message, recorded by the agent's capture as a
decision quoting their words that supersedes the one asked about, is no longer open:
``clarify --wait`` never asks it again (case eval-2ecb0be7: the full-board and saving
questions were re-asked right after the owner answered them)."""

from __future__ import annotations

from pathlib import Path

import yaml

from plumb.api import open_core
from plumb.understand import judge
from understand.test_judge_cascade import world  # noqa: F401
from understand.test_judge_job import SESSION, log_prompt

SAID = "On a full board print draw and the score line, then start a fresh game"


def _decision(repo: Path, write_record, n: int, chosen: str, links: list[dict[str, str]],
              **extra: str) -> None:
    data = {"id": f"DEC-{n:03d}", "title": "Full board", "question": "What on a full board?",
            "chosen": chosen, "alternatives": ["Keep playing"], "matters": True, **extra,
            "links": links}
    write_record(repo, "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n")


def _ask_about(repo: Path, record_id: str) -> None:
    core = open_core(repo)
    judge.add_question(core, SESSION, {
        "key": judge.question_key("What should happen on a full board?"), "job": "judge-x",
        "records": [{"id": record_id, "hash": core.index()[record_id].hash}],
        "principle": "", "blocking": False, "diagram": False,
        "question": "What should happen on a full board?", "header": "Full board",
        "options": [{"label": "Print draw (Recommended)", "description": "Ends the game."},
                    {"label": "Keep playing", "description": "Nothing ends."}]})


def test_a_question_answered_in_the_owners_message_and_captured_is_not_open(
        world: Path, write_record) -> None:  # noqa: F811
    _decision(world, write_record, 1, "Keep playing", [{"kind": "decides", "to": "SR-001"}])
    _ask_about(world, "DEC-001")
    assert [q["key"] for q in judge.open_questions(open_core(world), SESSION)]

    log_prompt(world, SAID + ".", at="2999-01-01T00:00:00Z")
    _decision(world, write_record, 2, "Print draw and the score line, then a fresh game",
              [{"kind": "supersedes", "to": "DEC-001"}], quote=SAID)
    assert judge.open_questions(open_core(world), SESSION) == []


def test_a_question_about_a_superseded_decision_is_not_open(
        world: Path, write_record) -> None:  # noqa: F811
    """The decision asked about was replaced (``plumb decide --supersede``): the question asks
    about a choice no longer standing; its successor is judged on its own."""
    _decision(world, write_record, 1, "Keep playing", [{"kind": "decides", "to": "SR-001"}])
    _ask_about(world, "DEC-001")
    _decision(world, write_record, 2, "End the game", [{"kind": "supersedes", "to": "DEC-001"}])
    assert judge.open_questions(open_core(world), SESSION) == []
