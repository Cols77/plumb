"""The Hermes adapter (sp4 4.3, SR-056)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from hosts_helpers import approvals_written, approve_in_agent_shell, make_project, snapshot

from plumb.cli import main
from plumb.hosts.common import FALLBACK_PROMPT_LINE, NO_MARKER_LINE
from plumb.hosts.hermes import install as hermes

pytestmark = pytest.mark.sr("SR-056")


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    monkeypatch.delenv(hermes.ENABLE_ENV, raising=False)
    make_project(repo, write_record)
    (repo / "AGENTS.md").write_text("# Owner's notes\n", "utf-8")
    other = repo / ".hermes" / "plugins" / "other" / "plugin.yaml"
    other.parent.mkdir(parents=True)
    other.write_text("name: other\n", "utf-8")
    return repo


@pytest.fixture(autouse=True)
def restore_marker(monkeypatch) -> None:
    """register(ctx) sets the marker in os.environ: give it back after each test."""
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "")
    monkeypatch.delenv("PLUMB_AGENT_SESSION")


class FakeCtx:
    """A Hermes plugin context: records registrations and injected messages."""

    def __init__(self, hooks: bool = True) -> None:
        self.hooks: dict[str, object] = {}
        self.commands: dict[str, object] = {}
        self.injected: list[str] = []
        if hooks:
            self.register_hook = lambda name, fn: self.hooks.__setitem__(name, fn)

    def register_command(self, name, handler, description: str = "", **_kw) -> None:
        self.commands[name] = handler

    def inject_message(self, content: str, role: str = "user") -> bool:
        self.injected.append(content)
        return True


def _load_plugin(directory: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, directory / "plugin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_idempotent_preserves_foreign(project: Path) -> None:
    hermes.install(project)
    first = snapshot(project)
    assert hermes.install(project).changed == []
    assert snapshot(project) == first
    assert ".hermes/plugins/plumb/plugin.py" in first
    assert first["AGENTS.md"].decode().startswith("# Owner's notes")
    assert b"name: other" in first[".hermes/plugins/other/plugin.yaml"]


def test_block_goes_to_hermes_md_when_present(project: Path) -> None:
    (project / ".hermes.md").write_text("# Hermes notes\n", "utf-8")
    hermes.install(project)
    assert "plumb:begin" in (project / ".hermes.md").read_text("utf-8")
    assert "plumb:begin" not in (project / "AGENTS.md").read_text("utf-8")


def test_uninstall_removes_only_plumb(project: Path) -> None:
    before = snapshot(project)
    hermes.install(project)
    hermes.uninstall(project)
    assert snapshot(project) == before


def test_uninstall_keeps_block_another_host_reads(project: Path) -> None:
    from plumb.hosts.pi import install as pi

    hermes.install(project)
    pi.install(project)
    report = hermes.uninstall(project)
    assert any("still used by pi" in line for line in report.lines)
    assert "plumb:begin" in (project / "AGENTS.md").read_text("utf-8")


def test_dry_run_writes_nothing(project: Path, monkeypatch) -> None:
    before = snapshot(project)
    monkeypatch.chdir(project)
    assert main(["hosts", "install", "hermes", "--dry-run"]) == 0
    assert snapshot(project) == before


def test_owner_only_refused_in_agent_shell(project: Path, monkeypatch) -> None:
    hermes.install(project)
    plugin = _load_plugin(project / hermes.PLUGIN_DIR, "plumb_hermes_guard")
    plugin.register(FakeCtx())
    env = {"PLUMB_AGENT_SESSION": os.environ["PLUMB_AGENT_SESSION"]}
    assert env == {"PLUMB_AGENT_SESSION": "hermes"}  # what the agent's terminal inherits
    assert approve_in_agent_shell(project, monkeypatch, env) == 3
    assert approve_in_agent_shell(project, monkeypatch, {}) == 3  # plugins not enabled
    assert approvals_written(project) == []


def test_status_names_missing_marker(project: Path, monkeypatch, capsys) -> None:
    hermes.install(project)
    monkeypatch.chdir(project)
    assert main(["hosts", "status", "hermes"]) == 0  # project plugins not enabled
    out = capsys.readouterr().out
    assert NO_MARKER_LINE in out and FALLBACK_PROMPT_LINE in out
    assert "needs HERMES_ENABLE_PROJECT_PLUGINS=1" in out
    monkeypatch.setenv(hermes.ENABLE_ENV, "1")
    assert main(["hosts", "status", "hermes"]) == 0
    out = capsys.readouterr().out
    assert NO_MARKER_LINE not in out and "pre_llm_call" in out


FAKE_PLUMB = r'''
import json, sys
event = sys.argv[sys.argv.index("hook") + 1]
data = json.loads(sys.stdin.read() or "{}")
with open(sys.argv[1], "a", encoding="utf-8") as log:
    log.write(json.dumps({"event": event, **data}) + "\n")
out = {"agent_context": [f"ctx {event}"], "owner_lines": [], "block": None,
       "status_line": "plumb | ok"}
if event == "stop" and not data.get("stop_active"):
    out["block"] = "plumb: run the covering tests"
print(json.dumps(out))
'''


def test_hermes_register_drives_callbacks(project: Path, tmp_path: Path, monkeypatch) -> None:
    fake = tmp_path / "fake_plumb.py"
    fake.write_text(FAKE_PLUMB, "utf-8")
    log = tmp_path / "calls.jsonl"
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text(
        hermes.render("plugin.py", [sys.executable, str(fake), str(log)]), "utf-8")
    plugin = _load_plugin(plugin_dir, "plumb_hermes_fake")
    ctx = FakeCtx()
    plugin.register(ctx)
    assert set(ctx.hooks) == {"on_session_start", "pre_llm_call", "post_tool_call",
                              "pre_verify", "post_llm_call"}
    monkeypatch.chdir(project)
    ctx.hooks["on_session_start"](session_id="h1", model="m", platform="cli")
    context = ctx.hooks["pre_llm_call"](session_id="h1", user_message="hello",
                                        is_first_turn=True)
    assert context == {"context": "ctx session-start\nctx prompt"}
    assert ctx.hooks["pre_verify"](session_id="h1", attempt=0) == {
        "decision": "block", "reason": "plumb: run the covering tests"}
    assert ctx.hooks["pre_verify"](session_id="h1", attempt=1) is None
    ctx.hooks["post_llm_call"](session_id="h1")  # pre_verify already ran: no third stop
    assert ctx.commands["plumb"]("explain the login thing").startswith("plumb: passed")
    # exactly the owner's words, logged as their prompt: plumb adds no word an agent could
    # relay as the owner's ok
    assert ctx.injected == ["/plumb explain the login thing"]
    calls = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
    assert [c["event"] for c in calls] == ["session-start", "prompt", "stop", "stop"]
    assert calls[1]["text"] == "hello" and calls[3]["stop_active"] is True


def test_register_without_hook_api_registers_only_the_command(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text(hermes.render("plugin.py", ["plumb"]), "utf-8")
    plugin = _load_plugin(plugin_dir, "plumb_hermes_nohooks")
    ctx = FakeCtx(hooks=False)
    plugin.register(ctx)
    assert list(ctx.commands) == ["plumb"] and ctx.hooks == {}


@pytest.mark.sr("SR-053")
def test_real_plumb_through_the_plugin(project: Path, monkeypatch) -> None:
    """The rendered plugin with a real plumb: the owner's prompt is logged via hook and the
    delta comes back as the turn's context."""
    plugin_dir = project / hermes.PLUGIN_DIR
    hermes.install(project)
    (plugin_dir / "plugin.py").write_text(
        hermes.render("plugin.py", [sys.executable, "-m", "plumb"]), "utf-8")
    plugin = _load_plugin(plugin_dir, "plumb_hermes_real")
    monkeypatch.chdir(project)
    result = plugin.pre_llm_call(session_id="r1", user_message="what does SR-001 do?")
    assert result and "SR-001" in result["context"]
    entry = json.loads((project / ".plumb" / "session" / "prompts.jsonl")
                       .read_text("utf-8").splitlines()[-1])
    assert entry["via"] == "hook"
