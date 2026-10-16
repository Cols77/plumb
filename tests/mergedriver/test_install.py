"""D3, D4: the driver's installation and ``plumb hooks install`` (sp6 7.1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mergedriver.mdhelpers import launcher_for, make_repo, run_git
from plumb import cli
from plumb.mergedriver import install, status, uninstall
from plumb.mergedriver.gitconfig import ATTR_LINES, driver_command

pytestmark = pytest.mark.sr("SR-256")


def _attrs(root: Path) -> list[str]:
    return (root / ".plumb" / ".gitattributes").read_text(encoding="utf-8").splitlines()


def test_install_writes_attributes_and_config_once(tmp_path: Path) -> None:
    """SR-075 EX-4: installed twice, declared once, other attributes kept."""
    root = make_repo(tmp_path / "r")
    assert cli.main(["hooks", "install", "--root", str(root), "--launcher", "uv"]) == 0
    assert cli.main(["hooks", "install", "--root", str(root), "--launcher", "uv"]) == 0
    lines = _attrs(root)
    for line in ATTR_LINES:
        assert lines.count(line) == 1
    assert "log/*.jsonl merge=union" in lines
    config = run_git(root, "config", "--get-all", "merge.plumb-record.driver").stdout
    assert config.strip().count("\n") == 0
    assert config.strip() == driver_command(launcher_for(sys.executable))
    assert install(root, launcher_for(sys.executable)) == ["plumb: record merge driver "
                                                           "unchanged"]


def test_foreign_attributes_kept(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    path = root / ".plumb" / ".gitattributes"
    path.write_text("*.bin binary\n", encoding="utf-8")
    install(root, launcher_for(sys.executable))
    assert _attrs(root)[0] == "*.bin binary"
    uninstall(root)
    assert _attrs(root) == ["*.bin binary"]


def test_uninstall_removes_exactly_plumb_lines(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    run_git(root, "config", "merge.other.driver", "true")
    install(root, launcher_for(sys.executable))
    assert cli.main(["hooks", "uninstall", "--root", str(root)]) == 0
    assert not any("plumb-record" in line for line in _attrs(root))
    assert run_git(root, "config", "--get", "merge.plumb-record.driver",
                   check=False).returncode != 0
    assert run_git(root, "config", "--get", "merge.other.driver").stdout.strip() == "true"


def test_status_reports_attribute_without_driver(tmp_path: Path, capsys) -> None:
    root = make_repo(tmp_path / "r")
    assert status(root) == "merge driver: not installed (/plumb init installs it)"
    install(root, launcher_for(sys.executable))
    assert status(root) == "merge driver: installed"
    run_git(root, "config", "--unset", "merge.plumb-record.driver")
    assert status(root) == "merge driver: attribute without driver (/plumb init installs it)"
    assert cli.main(["hooks", "status", "--root", str(root)]) == 0
    assert "merge driver: attribute without driver" in capsys.readouterr().out


def test_launcher_matches_commit_msg_hook(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    assert cli.main(["hooks", "install", "--root", str(root), "--launcher", "uv"]) == 0
    hook = (root / ".git" / "hooks" / "commit-msg").read_text(encoding="utf-8")
    exe = hook.split('exec "', 1)[1].split('"', 1)[0]
    driver = run_git(root, "config", "--get", "merge.plumb-record.driver").stdout.strip()
    assert driver.startswith(f'"{exe}" -m plumb merge-driver ')


def test_init_installs_the_driver(tmp_path: Path, capsys) -> None:
    """R15, R17: /plumb init (``plumb init``) adopts a repository with the record merge."""
    root = tmp_path / "r"
    root.mkdir()
    run_git(root, "init", "-q", "-b", "main")
    assert cli.main(["init", "--root", str(root)]) == 0
    assert status(root) == "merge driver: installed"
    capsys.readouterr()
    assert cli.main(["init", "--root", str(root)]) == 0
    assert capsys.readouterr().out.strip() == "plumb: already initialized"
