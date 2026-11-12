"""SR-344, SR-345: one run against a claude double and an owner double."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from iaso.evaluate import run
from iaso.evaluate.tasks import Task


@pytest.fixture(autouse=True)
def no_scratch_left(tmp_path_factory, monkeypatch):
    """report-0ab44aff: a run leaves no iaso-eval-* folder in the temp folder."""
    import tempfile

    temp = tmp_path_factory.mktemp("systemp")
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    yield
    assert list(temp.glob("iaso-eval-*")) == []


class Claude:
    """Records (model, session_id, message); always answers 'ok'."""

    def __init__(self, capped_at=None):
        self.calls, self.capped_at = [], capped_at

    def __call__(self, binary, scratch, message, *, model, session_id, system, timeout_s, env,
                 max_turns=None, ask=None):
        self.calls.append((model, session_id, message))
        self.limits = (timeout_s, max_turns)
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


def go(tmp_path, claude, owner=None, model="haiku", limits=None):
    return run.run_task(tmp_path / "root", task(tmp_path), model=model, owner=owner or Owner(False),
                        runs_dir=tmp_path / "runs", claude=claude, binary="claude",
                        limits=limits or {"exchanges": 3})


@pytest.mark.sr("SR-344")
def test_the_run_leaves_a_run_folder_and_no_scratch_repository(tmp_path):
    claude = Claude()
    result = go(tmp_path, claude)
    assert not result.scratch.exists() and not result.scratch.parent.exists()
    assert [c[2] for c in claude.calls] == ["one", "two"]
    for name in ("transcript.jsonl", "score.json", "issues.jsonl", ".iaso"):
        assert (result.run_dir / name).exists()
    assert json.loads((result.run_dir / "score.json").read_text())["checks_total"] == 0


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
def test_claude_turn_lets_the_agent_run_python_and_iaso(tmp_path, monkeypatch):
    """The headless call allows the shell commands the task needs and puts the benchmark
    interpreter's iaso command on the agent's PATH (found in the first live run)."""
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
    assert "Bash(python:*)" in seen["argv"] and "Bash(iaso:*)" in seen["argv"]
    assert seen["env"]["PATH"].startswith(str(Path(sys.executable).parent))


@pytest.mark.sr("SR-344")
def test_claude_turn_is_never_an_attended_session(tmp_path, monkeypatch):
    """eval-52810e26: ``claude -p`` has no question tool, so the headless agent's hooks must not
    take it for the attended session that launched the benchmark: that session's
    CLAUDE_CODE_SESSION_ATTENDED=1 would make the stop and ask gate send the agent after a
    question tool it cannot find, turn after turn."""
    import subprocess

    seen = {}

    def fake_run(argv, **kw):
        seen.update(env=kw["env"])
        return subprocess.CompletedProcess(argv, 0, json.dumps(
            {"result": "ok", "session_id": "s9", "num_turns": 1}), "")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")
    run.claude_turn("claude", tmp_path, "hi", model="haiku", session_id=None, system="brief",
                    timeout_s=5)
    assert seen["env"].get("CLAUDE_CODE_SESSION_ATTENDED") != "1"
    run.claude_turn("claude", tmp_path, "hi", model="haiku", session_id=None, system="brief",
                    timeout_s=5, env={"PATH": "", "CLAUDE_CODE_SESSION_ATTENDED": "1"})
    assert seen["env"].get("CLAUDE_CODE_SESSION_ATTENDED") != "1"


@pytest.mark.sr("SR-344")
def test_two_runs_in_one_second_get_their_own_run_folders(tmp_path, monkeypatch):
    """Two runs of one task and model started in the same second never collide on the folder
    (the run folder name is stamped to the second)."""
    real = run.time.strftime
    monkeypatch.setattr(run.time, "strftime", lambda fmt, *a: "20261031T120000"
                        if fmt == "%Y%m%dT%H%M%S" else real(fmt, *a))
    first, second = go(tmp_path, Claude()), go(tmp_path, Claude())
    assert first.run_dir != second.run_dir
    assert (first.run_dir / "score.json").is_file() and (second.run_dir / "score.json").is_file()


@pytest.mark.sr("SR-345")
def test_without_limits_the_owner_answers_until_the_agent_stops_asking(tmp_path):
    """DEC-308: no limit by default; a named limit applies, and no turn or time cap is passed."""
    class Tires(Owner):
        def answer(self, brief, request, reply):
            self.calls += 1
            return {"asks": self.calls % 6 != 0, "answer": "ans"}
    claude = Claude()
    result = go(tmp_path, claude, Tires(True), limits=run.NO_LIMITS)
    assert result.unanswered == 0 and [c[2] for c in claude.calls].count("ans") == 10
    assert claude.limits == (None, None)
    named = Claude()
    go(tmp_path, named, Owner(False), limits={"turns": 7, "minutes": 2})
    assert named.limits[1] == 7 and 0 < named.limits[0] <= 120


@pytest.mark.sr("SR-344")
def test_claude_turn_gives_the_agent_the_stand_in_question_tool(tmp_path, monkeypatch):
    """DEC-407: with ``ask`` the headless call registers the stand-in MCP server, allows its
    tool, tells the agent to use it, and flags the hooks that a question tool is present; the
    owner's brief sits in a file outside the scratch repository."""
    import subprocess

    from iaso.hosts.claude_code import ask_gate

    seen = {}

    def fake_run(argv, **kw):
        config = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())
        seen.update(argv=argv, env=kw["env"], config=config, cwd=kw["cwd"])
        server = config["mcpServers"][ask_gate.STAND_IN_SERVER]
        seen["ask"] = json.loads(Path(server["env"]["IASO_ASK_CONFIG"]).read_text())
        return subprocess.CompletedProcess(argv, 0, json.dumps({"result": "ok"}), "")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")
    ask = {"brief": "hidden", "request": "one", "owner_model": "haiku"}
    run.claude_turn("claude", tmp_path, "hi", model="haiku", session_id=None, system="brief",
                    timeout_s=5, ask=ask)
    argv = seen["argv"]
    assert ask_gate.STAND_IN_TOOL in argv[argv.index("--allowedTools"):]
    assert argv[argv.index("--append-system-prompt") + 1].startswith("brief")
    assert ask_gate.STAND_IN_TOOL in argv[argv.index("--append-system-prompt") + 1]
    server = seen["config"]["mcpServers"][ask_gate.STAND_IN_SERVER]
    assert server["args"] == ["-m", "iaso.evaluate.ask_server"]
    assert seen["ask"] == ask and not str(tmp_path) in server["env"]["IASO_ASK_CONFIG"]
    assert seen["env"][ask_gate.STAND_IN_ENV] == "1"
    assert seen["env"].get("CLAUDE_CODE_SESSION_ATTENDED") != "1"


@pytest.mark.sr("SR-344")
def test_claude_turn_without_ask_adds_no_question_tool(tmp_path, monkeypatch):
    """Without ``ask`` there is no stand-in: no MCP config, no allowed tool, no hook flag."""
    import subprocess

    from iaso.hosts.claude_code import ask_gate

    seen = {}

    def fake_run(argv, **kw):
        seen.update(argv=argv, env=kw["env"])
        return subprocess.CompletedProcess(argv, 0, json.dumps({"result": "ok"}), "")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.delenv(ask_gate.STAND_IN_ENV, raising=False)
    run.claude_turn("claude", tmp_path, "hi", model="haiku", session_id=None, system="brief",
                    timeout_s=5)
    assert "--mcp-config" not in seen["argv"] and ask_gate.STAND_IN_TOOL not in seen["argv"]
    assert ask_gate.STAND_IN_ENV not in seen["env"]


@pytest.mark.sr("SR-344")
def test_the_scratch_repository_hears_the_stand_in_tool(tmp_path):
    """DEC-407: the scratch settings log the stand-in's answers with the question-answer hook."""
    from iaso.hosts.claude_code import ask_gate

    scratch = run.scratch_repo(tmp_path)
    groups = json.loads((scratch / ".claude" / "settings.json").read_text())["hooks"]["PostToolUse"]
    (heard,) = [g for g in groups if g["matcher"] == ask_gate.STAND_IN_TOOL]
    assert heard["hooks"][0]["command"].endswith("hook question-answer")


@pytest.mark.sr("SR-344")
def test_the_scratch_repository_has_a_judge_by_default(tmp_path):
    """eval-8ba65c4a: with no judge named, the agent's capture is never checked, and the agent
    may not change the config to fix that."""
    from iaso.config import load_config

    scratch = run.scratch_repo(tmp_path)
    assert load_config(scratch).judgment.backend == "jev"


@pytest.mark.sr("SR-344")
def test_the_run_judges_with_the_judge_of_the_repository_it_runs_from(tmp_path):
    """The credential's provider is the host's: the preset default would look for another key."""
    from iaso.config import load_config

    root = tmp_path / "root"
    (root / ".iaso").mkdir(parents=True)
    (root / ".iaso" / "config.yaml").write_text(
        "judgment:\n  backend: jev\n  jev:\n    provider: openrouter\n", encoding="utf-8")
    kept = tmp_path / "kept"
    shutil.copytree(go(tmp_path, Claude()).run_dir / ".iaso", kept / ".iaso")
    judgment = load_config(kept).judgment
    assert judgment.backend == "jev"
    assert judgment.jev["credential_env"] == "OPENROUTER_API_KEY"
