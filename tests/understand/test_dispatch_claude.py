"""SR-104 EX-6: the Claude Code dispatcher runs one isolated, tool-less call per job."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from plumb.contracts import DispatchError, Job
from plumb.understand import agents
from plumb.understand.dispatch import claude_code
from understand.fakes import fake_claude

pytestmark = pytest.mark.sr("SR-273")

_REAL_ENV = dict(os.environ)   # before the isolation fixtures: the live test needs the login

SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
JOB = Job(id="read-0123456789abcdef", kind="read", session="s1", schema="read.v1")


def _answer(payload: object) -> str:
    return json.dumps({"type": "result", "is_error": False, "structured_output": payload,
                       "result": json.dumps(payload)})


def _dispatcher(fake, **options) -> claude_code.ClaudeCodeDispatcher:
    return claude_code.ClaudeCodeDispatcher(model="haiku", timeout_s=30, env=fake.env(),
                                            **options)


def _flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def test_ex6_command_selects_agent_and_isolates(tmp_path: Path, repo: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    fake = fake_claude(tmp_path / "bin", _answer({"n": 3}))
    monkeypatch.setattr(agents, "AGENTS_DIR", tmp_path / "agents")
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "read.md").write_text("You read the owner's answer.\n",
                                                 encoding="utf-8")
    listed: list[list[str]] = []
    real_rmtree = claude_code.shutil.rmtree

    def spy(path, *args, **kwargs):
        listed.append(os.listdir(path))
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(claude_code.shutil, "rmtree", spy)
    monkeypatch.chdir(repo)
    (repo / "CLAUDE.md").write_text("PROJECT RULES <!-- plumb:begin --> x <!-- plumb:end -->\n",
                                    encoding="utf-8")
    answer = _dispatcher(fake).run(JOB, system=agents.load("read"), user='{"message": "hi"}',
                                   schema=SCHEMA, on_step=lambda step: None)
    assert answer == {"n": 3}
    (call,) = fake.calls()
    argv = call["argv"]
    for flag in ("-p", "--no-session-persistence", "--strict-mcp-config",
                 "--disable-slash-commands"):
        assert flag in argv
    assert _flag(argv, "--agent") == "plumb-read"
    assert _flag(argv, "--model") == "haiku"
    assert _flag(argv, "--tools") == ""
    assert _flag(argv, "--setting-sources") == ""
    assert _flag(argv, "--output-format") == "json"
    assert json.loads(_flag(argv, "--json-schema")) == SCHEMA
    definition = json.loads(_flag(argv, "--agents"))
    assert set(definition) == {"plumb-read"}
    assert "You read the owner's answer." in definition["plumb-read"]["prompt"]
    assert "--bare" not in argv
    # a neutral, empty working directory that is not the repository
    assert Path(call["cwd"]).resolve() != repo.resolve()
    assert not Path(call["cwd"]).resolve().is_relative_to(repo.resolve())
    assert listed == [[]]
    # nothing of the project's own instructions reaches the model
    for text in (call["stdin"], json.dumps(definition)):
        assert "PROJECT RULES" not in text and "plumb:begin" not in text
    assert call["stdin"] == '{"message": "hi"}'


def test_env_has_plumb_job(tmp_path: Path) -> None:
    fake = fake_claude(tmp_path / "bin", _answer({"n": 1}))
    base = fake.env()
    base["PLUMB_WORKER"] = "ab" * 16
    claude_code.ClaudeCodeDispatcher(model="haiku", timeout_s=30, env=base).run(
        JOB, system="s", user="u", schema=SCHEMA, on_step=lambda step: None)
    (call,) = fake.calls()
    assert call["env"]["PLUMB_JOB"] == JOB.id
    assert "PLUMB_WORKER" not in call["env"]


def test_missing_binary_is_a_plain_error(tmp_path: Path) -> None:
    empty = tmp_path / "nothing"
    empty.mkdir()
    dispatcher = claude_code.ClaudeCodeDispatcher(
        model="haiku", timeout_s=5, env={"PATH": str(empty), "PATHEXT": ".EXE;.CMD"})
    reason = dispatcher.available()
    assert reason and "claude" in reason
    with pytest.raises(DispatchError) as caught:
        dispatcher.run(JOB, system="s", user="u", schema=SCHEMA, on_step=lambda step: None)
    assert caught.value.step == "start"


def test_bad_json_answer_fails_the_schema(tmp_path: Path) -> None:
    fake = fake_claude(tmp_path / "bin", _answer({"n": "three"}))
    with pytest.raises(DispatchError) as caught:
        _dispatcher(fake).run(JOB, system="s", user="u", schema=SCHEMA,
                              on_step=lambda step: None)
    assert caught.value.step == "schema"
    fake = fake_claude(tmp_path / "bin2", "this is not json")
    with pytest.raises(DispatchError) as caught:
        _dispatcher(fake).run(JOB, system="s", user="u", schema=SCHEMA,
                              on_step=lambda step: None)
    assert caught.value.step == "answer"


def test_an_error_result_of_the_cli_is_a_run_error(tmp_path: Path) -> None:
    fake = fake_claude(tmp_path / "bin", json.dumps(
        {"type": "result", "is_error": True, "result": "Not logged in"}))
    with pytest.raises(DispatchError) as caught:
        _dispatcher(fake).run(JOB, system="s", user="u", schema=SCHEMA,
                              on_step=lambda step: None)
    assert caught.value.step == "run" and "Not logged in" in caught.value.message


def test_timeout_is_a_timeout_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    fake = fake_claude(tmp_path / "bin", _answer({"n": 1}))

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("claude", 1)

    monkeypatch.setattr(claude_code.subprocess, "run", slow)
    with pytest.raises(DispatchError) as caught:
        _dispatcher(fake).run(JOB, system="s", user="u", schema=SCHEMA,
                              on_step=lambda step: None)
    assert caught.value.step == "timeout"


@pytest.mark.dispatch_live
def test_live_claude_answers_the_schema() -> None:
    import shutil

    if os.environ.get("DISPATCH_LIVE") != "1" or not shutil.which("claude"):
        pytest.skip("set DISPATCH_LIVE=1 with claude installed")
    answer = claude_code.ClaudeCodeDispatcher(model="haiku", timeout_s=90, env=_REAL_ENV).run(
        JOB, system="Answer with the schema only.", user="n is 3",
        schema=SCHEMA, on_step=lambda step: None)
    assert isinstance(answer["n"], int)
