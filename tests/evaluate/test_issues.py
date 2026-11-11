"""SR-347, SR-348: the issues file collected, accumulated and opened as debug cases."""

from __future__ import annotations

import json

import pytest

from iaso import debug
from iaso.evaluate import issues

ISSUE = {"when": "t", "command": "iaso brief", "expected": "a brief", "got": "boom",
         "context": "starting"}


def scratch_with(tmp_path, rows):
    scratch = tmp_path / "scratch"
    (scratch / ".iaso").mkdir(parents=True)
    (scratch / issues.ISSUES_FILE).write_text(
        "".join(json.dumps(r) + "\n" for r in rows) + "not json\n", encoding="utf-8")
    return scratch


@pytest.mark.sr("SR-347")
def test_three_lines_are_collected_and_accumulated(tmp_path):
    root, run_dir = tmp_path / "root", tmp_path / "run"
    root.mkdir()
    rows = [{**ISSUE, "got": f"g{n}"} for n in range(3)]
    got = issues.collect(scratch_with(tmp_path, rows), run_dir, root, "r1", "simple", "haiku")
    assert got == rows
    assert len((run_dir / "issues.jsonl").read_text().splitlines()) == 3
    kept = [json.loads(x) for x in root.joinpath(*issues.ACCUMULATED).read_text().splitlines()]
    assert len(kept) == 3
    assert all((k["run"], k["task"], k["model"]) == ("r1", "simple", "haiku") for k in kept)


@pytest.mark.sr("SR-347")
def test_no_file_leaves_the_accumulated_file_alone(tmp_path):
    root = tmp_path / "root"
    target = root.joinpath(*issues.ACCUMULATED)
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"old": 1}\n')
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    assert issues.collect(scratch, tmp_path / "run", root, "r1", "simple", "haiku") == []
    assert (tmp_path / "run" / "issues.jsonl").read_text() == ""
    assert target.read_bytes() == b'{"old": 1}\n'


@pytest.mark.sr("SR-348")
def test_open_cases_writes_an_eval_issue_case(tmp_path):
    ids = issues.open_cases(tmp_path, [ISSUE])
    row = json.loads(debug._case_path(tmp_path, ids[0]).read_text("utf-8"))
    assert (row["kind"], row["target"]) == ("eval-issue", "iaso brief")
    assert row["detail"] == "expected: a brief; got: boom"
    assert row["log"] == "starting"


@pytest.mark.sr("SR-348")
def test_the_same_issue_twice_opens_one_case(tmp_path):
    assert len(issues.open_cases(tmp_path, [ISSUE, dict(ISSUE)])) == 1
    assert issues.open_cases(tmp_path, [ISSUE]) == []
