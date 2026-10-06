"""The Pi adapter (sp4 4.2, SR-055)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hosts_helpers import approvals_written, approve_in_agent_shell, make_project, snapshot

from plumb.cli import main
from plumb.hosts.common import FALLBACK_PROMPT_LINE, NO_MARKER_LINE
from plumb.hosts.pi import install as pi

pytestmark = pytest.mark.sr("SR-055")

FOREIGN = "export default function (pi) {}\n"


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    make_project(repo, write_record, decision=False)
    (repo / "AGENTS.md").write_text("# Owner's notes\n", "utf-8")
    other = repo / ".pi" / "extensions" / "other" / "index.ts"
    other.parent.mkdir(parents=True)
    other.write_text(FOREIGN, "utf-8")
    return repo


def test_install_idempotent_preserves_foreign(project: Path) -> None:
    pi.install(project)
    first = snapshot(project)
    assert pi.install(project).changed == []
    assert snapshot(project) == first
    assert first[".pi/extensions/other/index.ts"].replace(b"\r\n", b"\n") == FOREIGN.encode()
    agents = first["AGENTS.md"].decode()
    assert agents.startswith("# Owner's notes") and agents.count("<!-- plumb:begin -->") == 1


def test_uninstall_removes_only_plumb(project: Path) -> None:
    before = snapshot(project)
    pi.install(project)
    pi.uninstall(project)
    assert snapshot(project) == before


def test_dry_run_writes_nothing(project: Path, monkeypatch, capsys) -> None:
    before = snapshot(project)
    monkeypatch.chdir(project)
    assert main(["hosts", "install", "pi", "--dry-run"]) == 0
    assert ".pi/extensions/plumb/index.ts" in capsys.readouterr().out
    assert snapshot(project) == before


def test_owner_only_refused_in_agent_shell(project: Path, monkeypatch) -> None:
    pi.install(project)
    source = (project / pi.EXTENSION).read_text("utf-8")
    assert 'process.env[MARKER] = "pi"' in source  # the environment the extension gives
    assert approve_in_agent_shell(project, monkeypatch, {"PLUMB_AGENT_SESSION": "pi"}) == 3
    assert approve_in_agent_shell(project, monkeypatch, {}) == 3  # extension not loaded
    assert approvals_written(project) == []


def test_status_names_missing_marker(project: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(project)
    assert main(["hosts", "status", "pi"]) == 0  # not installed: nothing sets the marker
    out = capsys.readouterr().out
    assert NO_MARKER_LINE in out and FALLBACK_PROMPT_LINE in out
    assert "self-recorded message: 0" in out
    pi.install(project)
    assert main(["hosts", "status", "pi"]) == 0
    out = capsys.readouterr().out
    assert NO_MARKER_LINE not in out and "before_agent_start" in out


def test_pi_extension_names_events_and_commands(project: Path) -> None:
    pi.install(project)
    source = (project / pi.EXTENSION).read_text("utf-8")
    for event in ("session_start", "before_agent_start", "tool_result", "agent_end"):
        assert f'pi.on("{event}"' in source
    assert 'pi.registerCommand("plumb"' in source and "ctx.ui.setStatus" in source
    assert '"--host", "pi", "--format", "json"' in source
    assert 'deliverAs: "followUp"' in source and "sendUserMessage" in source
    assert "__PLUMB_ARGV__" not in source


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

HARNESS = r'''
import { pathToFileURL } from "node:url";
const [ts, cwd] = process.argv.slice(2);
const mod = await import(pathToFileURL(ts).href);
const handlers = {}, sent = [], commands = {}, notes = [];
const pi = { on: (e, h) => (handlers[e] = h), sendMessage: (m, o) => sent.push({ m, o }),
  sendUserMessage: (t) => sent.push({ user: t }), registerCommand: (n, o) => (commands[n] = o) };
mod.default(pi);
const ctx = { cwd, hasUI: true, sessionManager: { getSessionId: () => "s1" },
  ui: { setStatus: (k, v) => notes.push(["status", v]),
        notify: (t) => notes.push(["notify", t]) } };
await handlers.session_start({ reason: "startup" }, ctx);
const injected = await handlers.before_agent_start({ prompt: "hello" }, ctx);
await handlers.agent_end({}, ctx);
await handlers.before_agent_start({ prompt: sent[0].m.content }, ctx);
await handlers.agent_end({}, ctx);
console.log(JSON.stringify({ injected, sent, notes, commands: Object.keys(commands),
  env: process.env.PLUMB_AGENT_SESSION }));
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_extension_runs_under_node(project: Path, tmp_path: Path) -> None:
    """HS2: the rendered extension runs under node's type stripping with a fake Pi; a block
    is sent once as a follow-up, never again while the agent continues (SR-055 EX-2)."""
    probe = subprocess.run(["node", "--experimental-strip-types", "-e", "1"],
                           capture_output=True)
    if probe.returncode != 0:
        pytest.skip("node cannot strip TypeScript types")
    fake = tmp_path / "fake_plumb.py"
    fake.write_text(FAKE_PLUMB, "utf-8")
    log = tmp_path / "calls.jsonl"
    source = pi.render([sys.executable, str(fake), str(log)])
    ts = tmp_path / "ext" / "index.ts"
    ts.parent.mkdir()
    ts.write_text(source, "utf-8")
    harness = tmp_path / "harness.mjs"
    harness.write_text(HARNESS, "utf-8")
    result = subprocess.run(["node", "--experimental-strip-types", "--no-warnings",
                             str(harness), str(ts), str(project)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["env"] == "pi" and data["commands"] == ["plumb"]
    assert data["injected"]["message"]["content"] == "ctx session-start\nctx prompt"
    assert data["injected"]["message"]["display"] is False
    assert len(data["sent"]) == 1 and data["sent"][0]["o"]["deliverAs"] == "followUp"
    assert ["status", "plumb | ok"] in data["notes"]
    calls = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
    assert [c["event"] for c in calls] == ["session-start", "prompt", "stop", "stop"]
    assert calls[1]["text"] == "hello"  # the follow-up was never logged as a prompt
    assert calls[3]["stop_active"] is True
