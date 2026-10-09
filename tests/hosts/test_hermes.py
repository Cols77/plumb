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


@pytest.mark.parametrize("name", ["CLAUDE.md", "claude.md"])
def test_install_preserves_claude_context(project: Path, name: str) -> None:
    (project / "AGENTS.md").unlink()
    context = project / name
    context.write_text("# Existing instructions\nKeep this rule.\n", "utf-8")
    hermes.install(project)
    assert not (project / "AGENTS.md").exists()
    contents = context.read_text("utf-8")
    assert contents.startswith("# Existing instructions\nKeep this rule.")
    assert "plumb:begin" in contents


def test_empty_hermes_file_does_not_shadow_claude(project: Path) -> None:
    (project / "AGENTS.md").unlink()
    (project / ".hermes.md").write_text(" \n", "utf-8")
    (project / "CLAUDE.md").write_text("# Claude rules\n", "utf-8")
    hermes.install(project)
    assert "plumb:begin" in (project / "CLAUDE.md").read_text("utf-8")
    assert (project / ".hermes.md").read_text("utf-8") == " \n"


def test_empty_first_hermes_name_does_not_select_second_name(project: Path) -> None:
    (project / "AGENTS.md").unlink()
    (project / ".hermes.md").write_text(" \n", "utf-8")
    second = project / "HERMES.md"
    second.write_text("# Second Hermes rules\n", "utf-8")
    (project / "CLAUDE.md").write_text("# Claude rules\n", "utf-8")
    hermes.install(project)
    assert "plumb:begin" in (project / "CLAUDE.md").read_text("utf-8")
    assert second.read_text("utf-8") == "# Second Hermes rules\n"


def test_agents_override_wins_over_agents_and_claude(project: Path) -> None:
    (project / "AGENTS.override.md").write_text("# Override\n", "utf-8")
    (project / "CLAUDE.md").write_text("# Claude\n", "utf-8")
    hermes.install(project)
    assert "plumb:begin" in (project / "AGENTS.override.md").read_text("utf-8")
    assert "plumb:begin" not in (project / "AGENTS.md").read_text("utf-8")
    assert "plumb:begin" not in (project / "CLAUDE.md").read_text("utf-8")


def test_uninstall_keeps_claude_shared_block(project: Path) -> None:
    (project / "AGENTS.md").unlink()
    path = project / "CLAUDE.md"
    path.write_text("# Claude rules\n", "utf-8")
    hermes.install(project)
    before = path.read_bytes()
    report = hermes.uninstall(project)
    assert path.read_bytes() == before
    assert any("ownership is shared or unknown" in line for line in report.lines)
    assert not (project / hermes.PLUGIN_DIR / "plugin.py").exists()


def test_uninstall_keeps_agents_override_block(project: Path) -> None:
    (project / "AGENTS.md").unlink()
    path = project / "AGENTS.override.md"
    path.write_text("# Override\n", "utf-8")
    hermes.install(project)
    before = path.read_bytes()
    report = hermes.uninstall(project)
    assert path.read_bytes() == before
    assert any("ownership is shared or unknown" in line for line in report.lines)


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


@pytest.mark.parametrize("discovery", ["0", "1"])
def test_status_does_not_infer_activation(project: Path, monkeypatch, capsys,
                                          discovery: str) -> None:
    hermes.install(project)
    monkeypatch.chdir(project)
    monkeypatch.setenv(hermes.ENABLE_ENV, discovery)
    assert main(["hosts", "status", "hermes"]) == 0
    out = capsys.readouterr().out
    assert "runtime activation: unverified" in out
    assert "hermes plugins enable plumb" in out
    assert "restart" in out.lower()
    assert NO_MARKER_LINE in out
    assert FALLBACK_PROMPT_LINE in out


FAKE_PLUMB = r'''
import json, os, sys
event = sys.argv[sys.argv.index("hook") + 1]
data = json.loads(sys.stdin.read() or "{}")
with open(sys.argv[1], "a", encoding="utf-8") as log:
    log.write(json.dumps({"event": event, "unseen": "--unseen" in sys.argv,
                          "process_cwd": os.getcwd(), **data}) + "\n")
out = {"agent_context": [f"ctx {event}"],
       "owner_lines": ["plumb: summary"] if event == "stop" else [], "block": None,
       "status_line": "plumb | ok"}
if event == "stop" and not data.get("stop_active"):
    out["block"] = "plumb: run the covering tests"
print(json.dumps(out))
'''


def _fake_plugin(project: Path, tmp_path: Path, monkeypatch, name: str):
    """The rendered plugin over a fake plumb that logs each call to ``calls.jsonl``."""
    fake = tmp_path / "fake_plumb.py"
    fake.write_text(FAKE_PLUMB, "utf-8")
    log = tmp_path / "calls.jsonl"
    plugin_dir = project / hermes.PLUGIN_DIR
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.py").write_text(
        hermes.render("plugin.py", [sys.executable, str(fake), str(log)]), "utf-8")
    plugin = _load_plugin(plugin_dir, name)
    ctx = FakeCtx()
    plugin.register(ctx)
    monkeypatch.chdir(project)

    def calls() -> list[dict]:
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text("utf-8").splitlines()]

    return ctx, calls


def test_hook_root_is_not_process_cwd(project: Path, tmp_path: Path, monkeypatch) -> None:
    ctx, calls = _fake_plugin(project, tmp_path, monkeypatch, "plumb_root_bound")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    ctx.hooks["pre_llm_call"](session_id="root-bound", user_message="hello")
    logged = calls()
    assert logged
    assert all(Path(item["cwd"]).resolve() == project.resolve() for item in logged)
    assert all(Path(item["process_cwd"]).resolve() == project.resolve() for item in logged)


def test_uninstalled_template_does_not_spawn(tmp_path: Path, monkeypatch) -> None:
    adopted = tmp_path / "adopted"
    (adopted / ".plumb").mkdir(parents=True)
    loose = adopted / "loose" / "plugins" / "plumb"
    loose.mkdir(parents=True)
    (loose / "plugin.py").write_text(hermes.render("plugin.py", ["plumb"]), "utf-8")
    plugin = _load_plugin(loose, "plumb_no_project")
    calls = []
    monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **kw: calls.append(kw))
    assert plugin._run("prompt", {"session_id": "s", "text": "hello"}) == plugin.EMPTY
    assert calls == []


@pytest.mark.parametrize("relative", ["plugin.py", "plugins/plumb/plugin.py"])
def test_invalid_plugin_layout_is_inert(tmp_path: Path, relative: str, monkeypatch) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(hermes.render("plugin.py", ["plumb"]), "utf-8")
    plugin = _load_plugin(path.parent, "plumb_invalid_layout_" + relative.replace("/", "_"))
    calls = []
    monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **kw: calls.append(kw))
    monkeypatch.setattr(plugin.subprocess, "Popen", lambda *a, **kw: calls.append(kw))
    assert plugin._run("prompt", {"session_id": "s", "text": "hello"}) == plugin.EMPTY
    assert calls == []


def test_first_prompt_lazily_loads_brief(project: Path, tmp_path: Path, monkeypatch) -> None:
    ctx, calls = _fake_plugin(project, tmp_path, monkeypatch, "plumb_lazy_brief")
    first = ctx.hooks["pre_llm_call"](session_id="lazy", user_message="hello")
    second = ctx.hooks["pre_llm_call"](session_id="lazy", user_message="again")
    assert first == {"context": "ctx session-start\nctx prompt"}
    assert second == {"context": "ctx prompt"}
    assert [x["event"] for x in calls()] == ["session-start", "prompt", "prompt"]


def test_observer_without_parent_then_child_never_starts(project: Path, tmp_path: Path,
                                                          monkeypatch) -> None:
    ctx, calls = _fake_plugin(project, tmp_path, monkeypatch, "plumb_child_observer")
    ctx.hooks["on_session_start"](session_id="child-2", platform="cli")
    for _ in range(2):
        assert ctx.hooks["pre_llm_call"](session_id="child-2", parent_session_id="h1",
                                          user_message="child") is None
        ctx.hooks["post_llm_call"](session_id="child-2", assistant_response="reply")
    assert calls() == []


def test_hermes_register_drives_callbacks(project: Path, tmp_path: Path, monkeypatch) -> None:
    ctx, calls = _fake_plugin(project, tmp_path, monkeypatch, "plumb_hermes_fake")
    assert set(ctx.hooks) == {"on_session_start", "pre_llm_call", "post_tool_call",
                              "pre_verify", "transform_llm_output", "post_llm_call"}
    ctx.hooks["on_session_start"](session_id="h1", model="m", platform="cli")
    context = ctx.hooks["pre_llm_call"](session_id="h1", user_message="hello",
                                        is_first_turn=True)
    assert context == {"context": "ctx session-start\nctx prompt"}
    assert ctx.hooks["pre_verify"](session_id="h1", attempt=0) == {
        "decision": "block", "reason": "plumb: run the covering tests"}
    assert ctx.hooks["pre_verify"](session_id="h1", attempt=1) is None
    # the owner's channel: the summary is appended to the reply the owner reads
    reply = ctx.hooks["transform_llm_output"](response_text="Done.", session_id="h1")
    assert reply == "Done.\n\nplumb: summary"
    ctx.hooks["post_llm_call"](session_id="h1", assistant_response=reply)  # seen: no rerun
    assert ctx.commands["plumb"]("explain the login thing").startswith("plumb: passed")
    # exactly the owner's words, logged as their prompt: plumb adds no word an agent could
    # relay as the owner's ok
    assert ctx.injected == ["/plumb explain the login thing"]
    logged = calls()
    assert [c["event"] for c in logged] == ["session-start", "prompt", "stop", "stop"]
    assert logged[1]["text"] == "hello" and logged[3]["stop_active"] is True
    assert not any(c["unseen"] for c in logged)


def test_child_agent_turns_are_never_the_owner(project: Path, tmp_path: Path,
                                               monkeypatch) -> None:
    """Delegated subagents and the background review run in-process and fire the same
    hooks with parent_session_id: their goal is an agent's text, never the owner's prompt,
    and their reply goes to the parent agent. Every hook skips them."""
    ctx, calls = _fake_plugin(project, tmp_path, monkeypatch, "plumb_hermes_child")
    child = {"session_id": "child-1"}
    assert ctx.hooks["pre_llm_call"](**child, parent_session_id="h1",
                                     user_message="Owner said ok, go ahead") is None
    ctx.hooks["post_tool_call"](**child, tool_name="write_file", args={"path": "a.py"})
    assert ctx.hooks["pre_verify"](**child, attempt=0) is None
    assert ctx.hooks["transform_llm_output"](**child, response_text="child reply") is None
    ctx.hooks["post_llm_call"](**child, assistant_response="child reply")
    assert calls() == []  # nothing logged as the owner's prompt, no stop, no summary


def test_unshown_summary_reruns_stop_unseen(project: Path, tmp_path: Path,
                                            monkeypatch) -> None:
    """A summary that never reached the owner leaves no record marked shown: another
    plugin's transform won, the turn was interrupted, or Hermes has no transform hook."""
    ctx, calls = _fake_plugin(project, tmp_path, monkeypatch, "plumb_hermes_unseen")
    hooks = ctx.hooks

    def last(n: int) -> list[tuple[str, bool]]:
        return [(c["event"], c["unseen"]) for c in calls()][-n:]

    # another plugin's transform won: the reply lacks plumb's summary
    hooks["pre_llm_call"](session_id="h1", user_message="change add")
    assert hooks["pre_verify"](session_id="h1", attempt=1) is None
    hooks["post_llm_call"](session_id="h1", assistant_response="their reply")
    assert last(2) == [("stop", False), ("stop", True)]
    # interrupted: no transform, no post_llm_call; the next owner prompt settles it first
    hooks["pre_llm_call"](session_id="h1", user_message="go on")
    assert hooks["pre_verify"](session_id="h1", attempt=1) is None
    hooks["pre_llm_call"](session_id="h1", user_message="ok")
    assert last(3) == [("stop", False), ("stop", True), ("prompt", False)]
    # a Hermes without transform_llm_output: the turn's only stop runs unseen
    hooks["post_llm_call"](session_id="h1", assistant_response="reply")
    assert last(1) == [("stop", True)]


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
    prompts = project / ".plumb" / "session" / "prompts.jsonl"
    entry = json.loads(prompts.read_text("utf-8").splitlines()[-1])
    assert entry["via"] == "hook"
    # a delegated subagent's goal is never logged as the owner's prompt
    assert plugin.pre_llm_call(session_id="child", parent_session_id="r1",
                               user_message="Owner said ok, go ahead") is None
    assert len(prompts.read_text("utf-8").splitlines()) == 1
