"""``plumb mcp install|uninstall`` registers the read-only server with a host (sp4 6.4,
SR-057, HS1)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from plumb.cli import main
from plumb.mcp import cli as mcp

pytestmark = pytest.mark.sr("SR-057")


@pytest.fixture
def project(repo: Path, tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    monkeypatch.chdir(repo)
    return repo


def test_claude_code_mcp_json_keeps_foreign(project: Path, capsys) -> None:
    (project / ".mcp.json").write_text(json.dumps(
        {"mcpServers": {"other": {"command": "x"}}}), "utf-8")
    assert main(["mcp", "install", "claude-code"]) == 0
    assert main(["mcp", "install", "claude-code"]) == 0
    assert capsys.readouterr().out.splitlines()[-1].endswith("changed nothing")
    servers = json.loads((project / ".mcp.json").read_text("utf-8"))["mcpServers"]
    assert servers["other"] == {"command": "x"}
    assert servers["plumb"]["args"][-2:] == ["mcp", "serve"]
    assert main(["mcp", "uninstall", "claude-code"]) == 0
    assert json.loads((project / ".mcp.json").read_text("utf-8")) == {
        "mcpServers": {"other": {"command": "x"}}}


def test_codex_table_appended_and_removed(project: Path) -> None:
    config = project / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text('model = "m"\n\n[mcp_servers.other]\ncommand = "o"\n', "utf-8")
    before = config.read_bytes()
    mcp.install(project, "codex")
    parsed = tomllib.loads(config.read_text("utf-8"))
    assert parsed["mcp_servers"]["plumb"]["args"][-2:] == ["mcp", "serve"]
    assert parsed["mcp_servers"]["other"]["command"] == "o" and parsed["model"] == "m"
    assert mcp.install(project, "codex")[0] == []  # idempotent
    mcp.install(project, "codex", remove=True)
    assert config.read_bytes() == before


def test_hermes_block_only_without_its_own_mcp_servers(project: Path) -> None:
    config = mcp.hermes_config()
    config.parent.mkdir(parents=True)
    config.write_text("model: m\n", "utf-8")
    mcp.install(project, "hermes")
    data = yaml.safe_load(config.read_text("utf-8"))
    assert data["model"] == "m" and data["mcp_servers"]["plumb"]["args"][-2:] == ["mcp",
                                                                                 "serve"]
    mcp.install(project, "hermes", remove=True)
    assert config.read_text("utf-8") == "model: m\n"
    config.write_text("mcp_servers:\n  other:\n    command: o\n", "utf-8")
    changed, lines = mcp.install(project, "hermes")
    assert changed == [] and "has its own mcp_servers" in lines[0]
    assert config.read_text("utf-8") == "mcp_servers:\n  other:\n    command: o\n"


def test_dry_run_writes_nothing(project: Path, capsys) -> None:
    assert main(["mcp", "install", "claude-code", "--dry-run"]) == 0
    assert "would change .mcp.json" in capsys.readouterr().out
    assert not (project / ".mcp.json").exists()
