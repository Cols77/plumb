"""SR-344, SR-345: one run against a claude double and an owner double."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from plumb.evaluate import run
from plumb.evaluate.tasks import Task


class Claude:
    """Records (model, session_id, message); always answers 'ok'."""

    def __init__(self, capped_at=None):
        self.calls, self.capped_at = [], capped_at

    def __call__(self, binary, scratch, message, *, model, session_id, system, timeout_s, env):
        self.calls.append((model, session_id, message))
        return {"text": "ok", "session_id": "s1", "error": "",
                "capped": self.capped_at == len(self.calls)}


class Owner:
    def __init__(self, asks):
        self.asks, self.calls = asks, 0

    def answer(self, brief, request, reply):
        self.calls += 1
        return {"asks": self.asks, "answer": "ans"}


def task(tmp_path: Path) -> Task:
    (tmp_path / "checks").mkdir(exist_ok=True)
    return Task("simple", "agent", "owner", ["one", "two"], tmp_path / "checks")


def go(tmp_path, claude, owner=None, model="haiku"):
    return run.run_task(tmp_path / "root", task(tmp_path), model=model, owner=owner or Owner(False),
                        runs_dir=tmp_path / "runs", claude=claude, binary="claude")


@pytest.mark.sr("SR-344")
def test_the_run_leaves_a_scratch_repository_and_a_run_folder(tmp_path):
    claude = Claude()
    result = go(tmp_path, claude)
    assert (result.scratch / ".plumb").is_dir()
    assert (result.scratch / ".claude" / "settings.json").is_file()
    assert [c[2] for c in claude.calls] == ["one", "two"]
    for name in ("transcript.jsonl", "score.json", "issues.jsonl", "plumb"):
        assert (result.run_dir / name).exists()
    assert json.loads((result.run_dir / "score.json").read_text())["checks_total"] == 0
    shutil.rmtree(result.scratch.parent, ignore_errors=True)


@pytest.mark.sr("SR-344")
def test_the_model_is_passed_and_named_in_the_folder(tmp_path):
    claude = Claude()
    result = go(tmp_path, claude, model="sonnet")
    assert {c[0] for c in claude.calls} == {"sonnet"}
    assert result.run_dir.name.endswith("-simple-sonnet")


@pytest.mark.sr("SR-344")
def test_no_claude_raises_before_any_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(run.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="claude command was not found"):
        run.run_task(tmp_path / "root", task(tmp_path), model="haiku", owner=Owner(False),
                     runs_dir=tmp_path / "runs", claude=Claude())
    assert not (tmp_path / "runs").exists()


@pytest.mark.sr("SR-344")
def test_a_capped_turn_is_marked_and_the_next_request_is_sent(tmp_path):
    claude = Claude(capped_at=1)
    result = go(tmp_path, claude)
    turns = [json.loads(x) for x in (result.run_dir / "transcript.jsonl").read_text().splitlines()]
    assert [t["source"] for t in turns if t["role"] == "agent"] == ["capped", ""]
    assert [c[2] for c in claude.calls] == ["one", "two"]


@pytest.mark.sr("SR-345")
def test_an_owner_who_always_asks_is_answered_three_times(tmp_path):
    claude, owner = Claude(), Owner(True)
    result = go(tmp_path, claude, owner)
    assert result.unanswered == 2   # both requests end on a reply that still asks
    assert [c[2] for c in claude.calls] == ["one", "ans", "ans", "ans", "two", "ans", "ans", "ans"]


@pytest.mark.sr("SR-345")
def test_an_owner_who_asks_nothing_is_called_once_per_request(tmp_path):
    claude, owner = Claude(), Owner(False)
    result = go(tmp_path, claude, owner)
    assert owner.calls == 2 and len(claude.calls) == 2 and result.unanswered == 0


@pytest.mark.sr("SR-344")
def test_claude_turn_lets_the_agent_run_python_and_plumb(tmp_path, monkeypatch):
    """The headless call allows the shell commands the task needs and puts the benchmark
    interpreter's plumb command on the agent's PATH (found in the first live run)."""
    import subprocess
    import sys

    seen = {}

    def fake_run(argv, **kw):
        seen.update(argv=argv, env=kw["env"])
        return subprocess.CompletedProcess(argv, 0, json.dumps(
            {"result": "ok", "session_id": "s9", "num_turns": 2}), "")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    got = run.claude_turn("claude", tmp_path, "hi", model="haiku", session_id=None,
                          system="brief", timeout_s=5)
    assert got["session_id"] == "s9" and not got["capped"]
    assert "Bash(python:*)" in seen["argv"] and "Bash(plumb:*)" in seen["argv"]
    assert seen["env"]["PATH"].startswith(str(Path(sys.executable).parent))
