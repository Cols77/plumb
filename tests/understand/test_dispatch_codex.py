"""SR-273: the codex dispatcher runs one isolated, read-only ``codex exec`` call per job for an
owner who works in Codex (report-6fb712c4). The command is a fake script."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from iaso.contracts import DispatchError, Job
from iaso.understand.dispatch import codex

pytestmark = pytest.mark.sr("SR-273")

JOB = Job(id="read-0123456789abcdef", kind="read", session="s1", schema="read.v1")
SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}, "note": {"type": "string"}},
          "required": ["n"]}


def _fake(bin_dir: Path, answer: str, code: int = 0, stderr: str = "") -> dict[str, str]:
    """A ``codex`` that records its argv, stdin and cwd and writes ``answer`` to the -o file."""
    bin_dir.mkdir()
    script = bin_dir / "codex"
    script.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "argv = sys.argv[1:]\n"
        f"open({str(bin_dir / 'call.json')!r}, 'w').write(json.dumps({{'argv': argv, "
        "'stdin': sys.stdin.read(), 'cwd': os.getcwd(), "
        "'schema': json.load(open(argv[argv.index('--output-schema') + 1]))}))\n"
        f"open(argv[argv.index('-o') + 1], 'w').write({answer!r})\n"
        f"sys.stderr.write({stderr!r})\nsys.exit({code})\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return {"PATH": str(bin_dir)}


def _run(env: dict[str, str], **options):
    return codex.CodexDispatcher(timeout_s=30, env=env, **options).run(
        JOB, system="SYSTEM", user="USER", schema=SCHEMA, on_step=lambda step: None)


def test_the_call_is_read_only_isolated_and_closes_the_schema(tmp_path: Path) -> None:
    env = _fake(tmp_path / "bin", json.dumps({"n": 3, "note": None}))
    assert _run(env, model="gpt-x") == {"n": 3}      # the optional note came back null: dropped
    call = json.loads((tmp_path / "bin" / "call.json").read_text("utf-8"))
    argv = call["argv"]
    assert argv[0] == "exec" and "--ephemeral" in argv and argv[argv.index("-s") + 1] == "read-only"
    assert argv[argv.index("-m") + 1] == "gpt-x"
    assert call["stdin"].startswith("SYSTEM") and "USER" in call["stdin"]
    assert call["cwd"] != str(Path.cwd()) and Path(call["cwd"]).name.startswith("iaso-job-")
    schema = call["schema"]                          # as Codex's strict output takes it
    assert schema["additionalProperties"] is False and schema["required"] == ["n", "note"]
    assert schema["properties"]["note"]["type"] == ["string", "null"]


def test_no_model_given_leaves_the_choice_to_codex(tmp_path: Path) -> None:
    env = _fake(tmp_path / "bin", json.dumps({"n": 1}))
    _run(env)
    assert "-m" not in json.loads((tmp_path / "bin" / "call.json").read_text("utf-8"))["argv"]


def test_a_failed_call_names_codex_and_its_cause(tmp_path: Path) -> None:
    env = _fake(tmp_path / "bin", "", code=1, stderr="You've hit your usage limit")
    with pytest.raises(DispatchError) as raised:
        _run(env)
    assert "codex" in str(raised.value) and "usage limit" in str(raised.value)


def test_an_answer_outside_the_schema_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DispatchError):
        _run(_fake(tmp_path / "bin", json.dumps({"n": "three"})))


def test_a_missing_command_is_unavailable(tmp_path: Path) -> None:
    assert "codex command was not found" in (
        codex.CodexDispatcher(env={"PATH": str(tmp_path)}).available() or "")


def test_the_configured_dispatcher_is_codex_when_set(repo: Path) -> None:
    from iaso.api import open_core
    from iaso.understand.dispatch import configured

    path = repo / ".iaso" / "config.yaml"
    path.write_text(path.read_text("utf-8") + "\nunderstand:\n  dispatch: codex\n", encoding="utf-8")
    dispatcher = configured(open_core(repo))
    assert dispatcher.name == "codex" and dispatcher.model == ""   # an unmapped level: Codex's own
    path.write_text(path.read_text("utf-8") + "  levels: {haiku: gpt-mini, sonnet: s, opus: o, fable: f}\n",
                    encoding="utf-8")
    assert configured(open_core(repo)).model == "gpt-mini"


def test_a_selfdebug_stage_runs_through_codex_in_the_work_copy(tmp_path: Path, repo: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    """report-6fb712c4: with dispatch codex, the fixer edits the work copy (workspace-write)
    and the diagnosis is read-only; a bare level names no model; the answer is the schema's."""
    from iaso import selfdebug

    path = repo / ".iaso" / "config.yaml"
    path.write_text(path.read_text("utf-8") + "\nunderstand:\n  dispatch: codex\n", encoding="utf-8")
    env = _fake(tmp_path / "bin", json.dumps({"test": "tests/x.py::t", "files": ["a.py"]}))
    monkeypatch.setenv("PATH", env["PATH"])
    fix = selfdebug.FixerDispatcher()(round=1, worktree=repo, model="sonnet", previous=[])
    assert fix == {"test": "tests/x.py::t", "files": ["a.py"]}
    call = json.loads((tmp_path / "bin" / "call.json").read_text("utf-8"))
    argv = call["argv"]
    assert argv[argv.index("-s") + 1] == "workspace-write" and "-m" not in argv
    assert argv[argv.index("-C") + 1] == str(repo) and call["cwd"] == str(repo)
    selfdebug.FixerDispatcher(agent="diagnoser", schema={"type": "object", "properties": {}},
                              mode="default", tools=selfdebug.READ_ONLY)(
        round=1, worktree=repo, model="gpt-x", previous=[])
    argv = json.loads((tmp_path / "bin" / "call.json").read_text("utf-8"))["argv"]
    assert argv[argv.index("-s") + 1] == "read-only" and argv[argv.index("-m") + 1] == "gpt-x"


class _Host:
    """A dispatcher that answers, or fails with ``error``; it counts its calls."""

    def __init__(self, name: str, answer: dict | None = None, error: DispatchError | None = None):
        self.name, self.answer, self.error, self.calls = name, answer, error, 0

    def available(self) -> str | None:
        return None

    def run(self, job, *, system, user, schema, on_step):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answer


def _fallback(*hosts: _Host):
    from iaso.understand.dispatch import FallbackDispatcher

    said: list[str] = []
    dispatcher = FallbackDispatcher(list(hosts))
    return dispatcher, said, lambda: dispatcher.run(JOB, system="s", user="u", schema=SCHEMA,
                                                    on_step=said.append)


@pytest.mark.parametrize("cause", ["You've hit your usage limit", "the claude command was not found "
                                   "on this machine", "HTTP 402 out of credit"])
def test_a_host_that_cannot_serve_hands_the_job_to_the_next_and_says_so(cause: str) -> None:
    first = _Host("claude-code", error=DispatchError("run", cause))
    second = _Host("codex", {"n": 1})
    dispatcher, said, run = _fallback(first, second)
    assert run() == {"n": 1} and (first.calls, second.calls) == (1, 1)
    assert dispatcher.name == "codex"
    assert said == [f"claude-code cannot serve ({cause[:80]}): trying codex"]


def test_a_timeout_or_a_bad_answer_is_not_retried_on_another_host() -> None:
    first = _Host("claude-code", error=DispatchError("timeout", "no answer within 120 seconds"))
    second = _Host("codex", {"n": 1})
    _, _, run = _fallback(first, second)
    with pytest.raises(DispatchError, match="claude-code: no answer within 120"):
        run()
    assert second.calls == 0


def test_when_every_host_fails_the_error_names_each_host_and_its_cause() -> None:
    _, _, run = _fallback(_Host("claude-code", error=DispatchError("run", "You've hit your limit")),
                          _Host("codex", error=DispatchError("run", "codex command was not found")))
    with pytest.raises(DispatchError) as raised:
        run()
    text = str(raised.value)
    assert "claude-code: You've hit your limit" in text and "codex: codex command was not found" in text


def test_several_hosts_in_the_config_make_a_fallback(repo: Path) -> None:
    from iaso.api import open_core
    from iaso.understand.dispatch import FallbackDispatcher, configured

    path = repo / ".iaso" / "config.yaml"
    path.write_text(path.read_text("utf-8") + "\nunderstand:\n  dispatch: claude-code, codex\n",
                    encoding="utf-8")
    dispatcher = configured(open_core(repo))
    assert isinstance(dispatcher, FallbackDispatcher)
    assert [h.name for h in dispatcher.hosts] == ["claude-code", "codex"]


def test_a_selfdebug_stage_moves_to_codex_when_claude_is_not_installed(
        tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso import selfdebug

    path = repo / ".iaso" / "config.yaml"
    path.write_text(path.read_text("utf-8") + "\nunderstand:\n  dispatch: claude-code,codex\n",
                    encoding="utf-8")
    env = _fake(tmp_path / "bin", json.dumps({"test": "t"}))     # a PATH with no claude
    monkeypatch.setenv("PATH", env["PATH"])
    assert selfdebug.FixerDispatcher()(round=1, worktree=repo, model="sonnet",
                                       previous=[]) == {"test": "t"}
