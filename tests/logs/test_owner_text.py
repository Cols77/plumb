"""SP6 11.1: the legacy-log warning names no shell command (SR-074)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from logutil import legacy_entry, write_legacy

from plumb import cli
from plumb.api import open_core
from plumb.present.owner_text import LEGACY_LOG, bare_cli_verbs

pytestmark = pytest.mark.sr("SR-232")


def _legacy(root: Path) -> None:
    first = legacy_entry("repin", {"i": 0}, None)
    write_legacy(root, "events", [first, legacy_entry("repin", {"i": 1}, first["digest"])])


def test_validate_warning(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _legacy(repo)
    assert cli.main(["validate", "--root", str(repo)]) == 0  # a warning, never a hold
    out = capsys.readouterr().out
    line = next(x for x in out.splitlines() if "legacy-log" in x)
    assert LEGACY_LOG.format(n=2) in line
    assert "migrate the logs" in line
    assert bare_cli_verbs(line) == []


def test_merge_report_warning(repo: Path) -> None:
    from plumb.boundary import merge_report, render

    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True,
                         capture_output=True).stdout.strip()
    _legacy(repo)
    report = merge_report(open_core(repo), sha, run_full=False)
    assert report.legacy_log_lines == 2
    text = "\n".join(render(report))
    assert LEGACY_LOG.format(n=2) in text
    warning = next(x for x in text.splitlines() if "old format" in x)
    assert bare_cli_verbs(warning) == []
    (repo / ".plumb" / "log" / "events.jsonl").write_bytes(b"")
    again = merge_report(open_core(repo), sha, run_full=False)
    assert again.legacy_log_lines == 0
    assert again.exit == report.exit  # the warning never changes the exit code
    assert "old format" not in "\n".join(render(again))


def test_bare_cli_verbs_for_this_lane() -> None:
    assert bare_cli_verbs("uv run plumb log migrate") == ["plumb log"]
    assert bare_cli_verbs("/plumb migrate the logs") == []
    assert bare_cli_verbs("plumb log: no legacy log line remains") == []
    assert bare_cli_verbs(LEGACY_LOG.format(n=3)) == []
