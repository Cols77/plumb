"""INT-131 acceptance tests: the product is called IASO (SR-430); records folder (SR-432)."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
OLD = "plum" + "b"


def _run(module: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    return subprocess.run([sys.executable, "-m", module, *args], cwd=cwd, env=env,
                          capture_output=True, text=True, check=False)


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


@pytest.mark.sr("SR-430")
def test_ex2_iaso_package_help_says_iaso(tmp_path: Path) -> None:
    result = _run("iaso", ["--help"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "usage: iaso" in result.stdout
    assert OLD not in result.stdout.lower()


@pytest.mark.sr("SR-430")
def test_ex2_cli_script_is_iaso_only() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^name = "iaso"', text, re.M)
    assert re.search(r'^iaso = "iaso\.cli:main"', text, re.M)
    assert not re.search(rf"^{OLD} = ", text, re.M)


@pytest.mark.sr("SR-430")
def test_ex1_plugin_and_marketplace_names() -> None:
    plugin = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text("utf-8"))
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text("utf-8"))
    assert plugin["name"] == "iaso"
    assert market["name"] == "iaso"
    assert [p["name"] for p in market["plugins"]] == ["iaso"]


@pytest.mark.sr("SR-430")
def test_ex1_slash_command_is_iaso() -> None:
    commands = ROOT / "plugin/commands"
    assert (commands / "iaso.md").is_file()
    assert not (commands / f"{OLD}.md").exists()


@pytest.mark.sr("SR-430")
def test_ex1_status_lines_name_iaso_not_old(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert _run("iaso", ["init"], repo).returncode == 0
    out = _run("iaso", ["status"], repo)
    assert out.returncode == 0, out.stderr
    assert "iaso" in out.stdout.lower()
    assert OLD not in out.stdout.lower()


@pytest.mark.sr("SR-430")
def test_readme_calls_product_iaso() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "IASO" in text
    assert OLD not in text.lower()


@pytest.mark.sr("SR-432")
def test_ex1_init_in_empty_repo_creates_dot_iaso(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _run("iaso", ["init"], repo)
    assert result.returncode == 0, result.stderr
    assert (repo / ".iaso").is_dir()
    assert not (repo / f".{OLD}").exists()
