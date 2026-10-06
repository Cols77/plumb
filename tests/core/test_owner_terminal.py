"""Owner-only writes need the owner's own interactive terminal, on every host (SR-005 EX-6).

Guarantee: an entry attributed to the owner (``by: owner``) is written only after a y/N
answered in an interactive terminal (``approvals.require_owner``). These tests run with NO
session marker, as on a host whose adapter cannot set it, and with stdin a pipe holding "y"
(an agent's shell piping ``yes``): every owner-only entry point must refuse with exit 3 and
write nothing. One test per entry point.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest

from plumb import approvals, cli
from plumb.api import open_core
from plumb.approvals import owner_terminal_answer as REAL_TERMINAL_CHECK

DIGEST = "sha256:" + "cd" * 32

SR = """---
id: SR-001
title: add numbers
statement: add returns the sum
examples:
- id: EX-1
  given: two numbers
  when: add runs
  then: it returns their sum
---
"""


@pytest.fixture
def agent_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """No session marker, the real terminal check, and a piped "y" on stdin."""
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    monkeypatch.setattr(approvals, "owner_terminal_answer", REAL_TERMINAL_CHECK)
    monkeypatch.setattr("sys.stdin", io.StringIO("y\ny\ny\n"))


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR)
    return repo


def _events(root: Path, kind: str) -> list:
    return list(open_core(root).log_read("events", [kind]))


def _refused(code: int, capsys: pytest.CaptureFixture[str]) -> None:
    assert code == 3
    assert "not an interactive terminal" in capsys.readouterr().err


@pytest.mark.sr("SR-005")
def test_approve_library_refused_without_terminal(project: Path, agent_shell: None) -> None:
    with pytest.raises(approvals.Refused, match="not an interactive terminal"):
        approvals.approve(open_core(project), ["SR-001"])
    assert _events(project, "approval") == []


@pytest.mark.sr("SR-005")
def test_approve_ids_refused_without_terminal(project: Path, agent_shell: None,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    _refused(cli.main(["approve", "SR-001", "--root", str(project)]), capsys)
    assert _events(project, "approval") == []


@pytest.mark.sr("SR-005")
def test_approve_proposed_refused_without_terminal(project: Path, agent_shell: None,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    _refused(cli.main(["approve", "--proposed", "--root", str(project)]), capsys)
    assert _events(project, "approval") == []


@pytest.mark.sr("SR-005")
def test_approve_exempt_refused_without_terminal(project: Path, agent_shell: None,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    config = project / ".plumb" / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8")
                      + "\ntrace:\n  exempt: ['src/gen/*']\n", encoding="utf-8")
    _refused(cli.main(["approve", "--exempt", "--root", str(project)]), capsys)
    assert _events(project, "approval") == []


@pytest.mark.sr("SR-005")
def test_revoke_refused_without_terminal(project: Path, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    approvals.approve(open_core(project), ["SR-001"])  # the owner, in the test stand-in
    monkeypatch.setattr(approvals, "owner_terminal_answer", REAL_TERMINAL_CHECK)
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
    _refused(cli.main(["revoke", "SR-001", "--root", str(project)]), capsys)
    assert _events(project, "revocation") == []
    assert open_core(project).status(["SR-001"])["SR-001"].confirmation == "confirmed"


@pytest.mark.sr("SR-005")
def test_waive_digest_refused_without_terminal(repo: Path, agent_shell: None,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    _refused(cli.main(["tests", "waive", "--diff-digest", DIGEST, "--reason", "flaky",
                       "--root", str(repo)]), capsys)
    assert _events(repo, "waiver") == []


@pytest.mark.sr("SR-005")
def test_waive_current_diff_refused_without_terminal(
        repo: Path, agent_shell: None, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    _refused(cli.main(["tests", "waive", "--reason", "flaky", "--root", str(repo)]), capsys)
    assert _events(repo, "waiver") == []


@pytest.mark.sr("SR-005")
def test_waive_merge_refused_without_terminal(repo: Path, agent_shell: None,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    subprocess.run(["git", "checkout", "-q", "-b", "feat"], cwd=repo, check=True)
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "change"], cwd=repo, check=True)
    _refused(cli.main(["tests", "waive", "--merge", "main", "--reason", "flaky",
                       "--root", str(repo)]), capsys)
    assert _events(repo, "waiver") == []


@pytest.mark.sr("SR-005")
def test_owner_terminal_yes_writes_and_no_declines(project: Path,
                                                   monkeypatch: pytest.MonkeyPatch,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(approvals, "owner_terminal_answer", REAL_TERMINAL_CHECK)
    monkeypatch.setattr(approvals, "_interactive", lambda: True)
    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
    assert cli.main(["approve", "SR-001", "--root", str(project)]) == 0
    assert "nothing written" in capsys.readouterr().out
    assert _events(project, "approval") == []
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
    assert cli.main(["approve", "SR-001", "--root", str(project)]) == 0
    entries = _events(project, "approval")
    assert len(entries) == 1 and entries[0].payload["by"] == "owner"
