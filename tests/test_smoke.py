"""Smoke tests: the package imports and the CLI entry point answers."""

import re
import subprocess
import sys

import plumb
from plumb.cli import main


def test_package_exposes_version() -> None:
    # SR-377: 0.1.<git commit count>
    assert re.fullmatch(r"0\.1\.\d+", plumb.__version__)


def test_cli_version_flag(capsys) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"plumb {plumb.__version__}"


def test_cli_without_arguments_prints_help(capsys) -> None:
    assert main([]) == 0
    assert "usage: plumb" in capsys.readouterr().out


def test_module_is_runnable() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "plumb", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == f"plumb {plumb.__version__}"
