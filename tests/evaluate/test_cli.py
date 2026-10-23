"""SR-344 EX-3 end to end: the evaluate command's argument check and the missing claude."""

import pytest

from plumb import cli


@pytest.mark.sr("SR-344")
def test_unknown_task_exits_2_with_usage(capsys):
    assert cli.main(["evaluate", "nope"]) == 2
    assert "usage: plumb evaluate" in capsys.readouterr().err


@pytest.mark.sr("SR-344")
def test_missing_claude_prints_one_line_and_exits_1(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("plumb.evaluate.cli.shutil.which", lambda name: None)
    assert cli.main(["evaluate", "simple", "--no-limits", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and "claude command" in out[0]
    assert not (tmp_path / ".plumb").exists()


@pytest.mark.sr("SR-344")
def test_unnamed_limits_are_asked_not_assumed(monkeypatch, capsys, tmp_path):
    """The owner's answer of 23 Oct: with no limit named and no --no-limits, nothing runs and
    the agent is told to ask the owner with the question tool."""
    monkeypatch.setattr("plumb.evaluate.cli.shutil.which", lambda name: "claude")
    assert cli.main(["evaluate", "simple", "--root", str(tmp_path)]) == 2
    assert "question tool" in capsys.readouterr().out and not (tmp_path / ".plumb").exists()
