"""SR-361, INT-119: a session is told to ask only the judge's questions about records its own
branch changes compared with main; the rest wait in /iaso status, and a session in main's
checkout is told to ask none (DEC-420, DEC-421)."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import git
from understand.test_judge_job import SESSION, requirement_text

from iaso.api import open_core
from iaso.present import insights
from iaso.understand import files, judge

pytestmark = [pytest.mark.sr("SR-361"), pytest.mark.work_scope]

ASK_1 = "Should totals round up or to the nearest cent?"
ASK_2 = "Should the receipt show the tax line?"


def _asks(root: Path) -> None:
    """The judge's open questions in one session folder, one on SR-001 and one on SR-002."""
    index = open_core(root).index()
    files.write_json_atomic(judge.questions_path(root, SESSION), [
        {"key": judge.question_key(text), "job": "judge-0000000000000000",
         "records": [{"id": rid, "hash": index[rid].hash}], "question": text, "header": "Totals",
         "options": [{"label": "Up", "description": ""}, {"label": "Nearest", "description": ""}]}
        for text, rid in ((ASK_1, "SR-001"), (ASK_2, "SR-002"))])


@pytest.fixture
def two_records(repo: Path, write_record) -> Path:
    write_record(repo, requirement_text(1, "Totals are rounded", "Totals round to the cent"))
    write_record(repo, requirement_text(2, "Receipts list items", "A receipt lists each item"))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "records")
    return repo


def _branch_changing_sr001(repo: Path, tmp_path: Path) -> Path:
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "work", str(wt))
    record = next((wt / ".iaso" / "requirements").glob("SR-001*.md"))
    record.write_text(record.read_text(encoding="utf-8").replace(
        "round to the cent", "round up to the next cent"), encoding="utf-8")
    git(wt, "commit", "-qam", "round up")
    return wt


def test_a_session_is_told_to_ask_only_about_records_its_branch_changes(
        two_records: Path, tmp_path: Path) -> None:
    wt = _branch_changing_sr001(two_records, tmp_path)
    _asks(wt)
    assert judge.work_ids(open_core(wt)) == {"SR-001"}
    assert [q["question"] for q in judge.to_ask(open_core(wt), SESSION)] == [ASK_1]
    # the other question still waits for the owner, only no session is pushed to ask it
    assert {q["question"] for q in judge.open_questions(open_core(wt), SESSION)} == {ASK_1, ASK_2}


def test_a_session_in_mains_checkout_is_told_to_ask_none(two_records: Path) -> None:
    write = two_records / ".iaso" / "requirements"
    record = next(write.glob("SR-001*.md"))
    record.write_text(record.read_text(encoding="utf-8") + "\n", encoding="utf-8")  # uncommitted
    _asks(two_records)
    assert judge.work_ids(open_core(two_records)) == set()
    assert judge.to_ask(open_core(two_records), SESSION) == []


def test_session_start_names_only_a_question_on_the_branchs_work(two_records: Path,
                                                                  tmp_path: Path) -> None:
    wt = _branch_changing_sr001(two_records, tmp_path)
    _asks(wt)
    line = insights._questions_line(open_core(wt))
    assert line is not None and ASK_1 in line.text and ASK_2 not in line.text
    _asks(two_records)
    assert insights._questions_line(open_core(two_records)) is None
