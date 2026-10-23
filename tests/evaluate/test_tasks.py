"""SR-349: the two benchmark tasks load, and their hidden checks pass a reference program."""

import re
import subprocess
import sys

import pytest

from plumb.evaluate import tasks

RULE = ("Whenever plumb behaves wrongly (a refusal you cannot explain, an error, a command or "
        "hook line that contradicts plumb's skills or its own words, a question you cannot "
        "answer), append one JSON line to `.plumb/eval-issues.jsonl`: "
        '`{"when": ISO time, "command": the plumb command or hook, "expected": what you '
        'expected, "got": what plumb said, "context": what you were doing}`. '
        "Then go on with the work.")


def flat(text: str) -> str:
    return " ".join(re.sub(r"^> ?", "", text, flags=re.MULTILINE).split())


def checks_of(task: tasks.Task) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in task.checks.glob("test_*.py"))


def run_checks(task, scratch, program: str, source: str):
    (scratch / program).write_text(source, encoding="utf-8")
    copy = scratch / "eval_checks"
    copy.mkdir()
    for p in task.checks.glob("test_*.py"):
        (copy / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return subprocess.run([sys.executable, "-m", "pytest", "eval_checks", "-q",
                           "-p", "no:cacheprovider"], cwd=scratch, capture_output=True,
                          text=True, timeout=300)


@pytest.mark.sr("SR-349")
def test_simple_requests():
    task = tasks.load("simple")
    assert len(task.requests) == 3
    assert "tic-tac-toe" in task.requests[0] and "keyboard" in task.requests[0]


@pytest.mark.sr("SR-349")
def test_complex_fourth_request_names_cents():
    task = tasks.load("complex")
    assert len(task.requests) == 5 and "whole cents" in task.requests[3]


@pytest.mark.sr("SR-349")
def test_unknown_task_refused():
    with pytest.raises(ValueError):
        tasks.load("nope")


@pytest.mark.sr("SR-349")
@pytest.mark.parametrize("name", tasks.NAMES)
def test_every_request_checked_and_brief_hides_checks(name):
    task = tasks.load(name)
    marked = {int(n) for n in re.findall(r"# request: (\d+)", checks_of(task))}
    assert marked == set(range(1, len(task.requests) + 1))
    assert "test_" not in task.agent_brief and "eval_checks" not in task.agent_brief
    assert task.owner_brief and task.checks.is_dir()


@pytest.mark.sr("SR-347")
@pytest.mark.parametrize("name", tasks.NAMES)
def test_issues_rule_in_brief(name):
    assert RULE in flat(tasks.load(name).agent_brief)


@pytest.mark.sr("SR-349")
def test_simple_checks_pass_reference(tmp_path, reference_game):
    done = run_checks(tasks.load("simple"), tmp_path, "game.py", reference_game)
    assert "6 passed" in done.stdout, done.stdout


@pytest.mark.sr("SR-349")
def test_simple_checks_fail_without_draw(tmp_path, reference_game):
    source = reference_game.replace('print("draw")', 'print("nothing")')
    done = run_checks(tasks.load("simple"), tmp_path, "game.py", source)
    assert "1 failed" in done.stdout and "test_draw" in done.stdout


@pytest.mark.sr("SR-349")
def test_complex_checks_pass_reference(tmp_path, reference_expenses):
    done = run_checks(tasks.load("complex"), tmp_path, "expenses.py", reference_expenses)
    assert "7 passed" in done.stdout, done.stdout
