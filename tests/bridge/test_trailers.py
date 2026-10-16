"""BRIDGE B1: the ``SR:`` trailer check and its ``commit-msg`` hook (spec 5.9)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from plumb import cli
from plumb.claims import ForeignHookError, check_msg, install_commit_msg_hook

pytestmark = pytest.mark.sr("SR-261")

SR_001 = """---
id: SR-001
title: First requirement
feature: FEAT-001
statement: Something holds.
---
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True, encoding="utf-8").stdout


def _require(repo: Path, value: bool = True) -> None:
    (repo / ".plumb" / "claims.yaml").write_text(
        f"require_trailer: {'true' if value else 'false'}\nexempt: []\nbaseline: []\n",
        encoding="utf-8")


def test_check_msg_rejects_unknown_id(repo: Path, write_record) -> None:
    write_record(repo, SR_001)
    code, lines = check_msg(repo, "fix a thing\n\nSR: SR-999\n")
    assert code == 1
    assert any("SR-999" in line and "unknown" in line for line in lines)
    code, lines = check_msg(repo, "fix a thing\n\nSR: SR-001\n")
    assert code == 0, lines


def test_check_msg_rejects_malformed_id(repo: Path, write_record) -> None:
    write_record(repo, SR_001)
    code, lines = check_msg(repo, "x\n\nSR: SR-1, banana\n")
    assert code == 1
    assert any("malformed" in line and "banana" in line for line in lines)


def test_check_msg_requires_trailer_when_configured(repo: Path, write_record) -> None:
    write_record(repo, SR_001)
    assert check_msg(repo, "no trailer here\n")[0] == 0
    _require(repo)
    code, lines = check_msg(repo, "no trailer here\n")
    assert code == 1
    assert any("SR:" in line for line in lines)
    # a mention in prose or in a git comment line is no claim
    assert check_msg(repo, "relates to SR-001\n# SR: SR-001\n")[0] == 1
    assert check_msg(repo, "ok\n\nSR: SR-001\n")[0] == 0


def test_check_msg_passes_without_plumb_dir(tmp_path: Path) -> None:
    code, lines = check_msg(tmp_path, "anything\n\nSR: SR-999\n")
    assert code == 0
    assert lines == ["plumb: not initialized here, trailer not checked"]


def test_install_hook_writes_and_leaves_foreign_hook(repo: Path) -> None:
    path = install_commit_msg_hook(repo, sys.executable)
    assert path.name == "commit-msg"
    text = path.read_text(encoding="utf-8")
    assert "plumb trailers check-msg" in text
    assert text.startswith("#!/bin/sh\n")
    # idempotent: a plumb hook is rewritten in place
    assert install_commit_msg_hook(repo, sys.executable) == path
    path.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    with pytest.raises(ForeignHookError) as info:
        install_commit_msg_hook(repo, sys.executable)
    assert "left untouched" in str(info.value)
    assert path.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"


def test_install_hook_uses_installing_interpreter(repo: Path) -> None:
    path = install_commit_msg_hook(repo, "C:\\Py\\python.exe")
    text = path.read_text(encoding="utf-8")
    assert '"C:/Py/python.exe" -m plumb trailers check-msg "$1"' in text


def test_install_hook_serves_worktrees(repo: Path, tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(wt), "-b", "side")
    path = install_commit_msg_hook(wt, sys.executable)
    common = Path(_git(repo, "rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = repo / common
    assert path.resolve() == (common / "hooks" / "commit-msg").resolve()


def test_hook_rejects_commit_end_to_end(repo: Path, write_record) -> None:
    write_record(repo, SR_001)
    _require(repo)
    install_commit_msg_hook(repo, sys.executable)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "-A")
    bad = subprocess.run(["git", "commit", "-q", "-m", "x\n\nSR: SR-999"], cwd=repo,
                         capture_output=True, text=True)
    assert bad.returncode != 0
    assert "SR-999" in (bad.stdout + bad.stderr)
    _git(repo, "commit", "-q", "-m", "x\n\nSR: SR-001")


def test_trailers_cli(repo: Path, write_record, capsys) -> None:
    write_record(repo, SR_001)
    msg = repo / "MSG"
    msg.write_text("x\n\nSR: SR-999\n", encoding="utf-8")
    assert cli.main(["trailers", "check-msg", str(msg), "--root", str(repo)]) == 1
    msg.write_text("x\n\nSR: SR-001\n", encoding="utf-8")
    assert cli.main(["trailers", "check-msg", str(msg), "--root", str(repo)]) == 0
    capsys.readouterr()
    assert cli.main(["trailers", "install-hook", "--root", str(repo)]) == 0
    assert "commit-msg" in capsys.readouterr().out
    assert cli.main(["trailers", "--help"]) == 0
    assert cli.main(["trailers", "bogus"]) == 2


# -- MERGE MS3: git's own revert, merge and fixup messages over exempt paths only ---------


@pytest.mark.sr("SR-260")
@pytest.mark.parametrize("message", ['Revert "add docs"\n\nThis reverts commit abc.\n',
                                     "Merge branch 'feat'\n", "fixup! add docs\n",
                                     "squash! add docs\n"])
def test_generated_message_over_exempt_paths_passes(repo: Path, write_record,
                                                    message: str) -> None:
    write_record(repo, SR_001)
    _require(repo)
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text("g\n", encoding="utf-8")
    _git(repo, "add", "docs/guide.md")
    code, lines = check_msg(repo, message)
    assert code == 0, lines
    (repo / "src.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "src.py")
    assert check_msg(repo, message)[0] == 1  # a non-exempt path still needs a trailer


@pytest.mark.sr("SR-260")
def test_plain_message_over_exempt_paths_still_needs_trailer(repo: Path, write_record) -> None:
    write_record(repo, SR_001)
    _require(repo)
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text("g\n", encoding="utf-8")
    _git(repo, "add", "docs/guide.md")
    assert check_msg(repo, "update the guide\n")[0] == 1


# -- MERGE MS2: "does this diff serve its claimed SRs?" is a non-blocking warning -----------


class _FakeCaptureApi:
    calls: list = []

    @staticmethod
    def diff_serves(core, sr_ids, paths):
        _FakeCaptureApi.calls.append((list(sr_ids), list(paths)))
        return [f"plumb: warning: {sr_ids[0]} may not be served by {paths[0]}"]


@pytest.mark.sr("SR-200")
def test_diff_serves_warning_never_blocks(repo: Path, write_record, monkeypatch) -> None:
    import types

    write_record(repo, SR_001)
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    package = types.ModuleType("plumb.capture")
    monkeypatch.setitem(sys.modules, "plumb.capture", package)
    monkeypatch.setitem(sys.modules, "plumb.capture.api", _FakeCaptureApi)
    _FakeCaptureApi.calls = []
    code, lines = check_msg(repo, "x\n\nSR: SR-001\n")
    assert code == 0
    assert lines == ["plumb: warning: SR-001 may not be served by app.py"]
    assert _FakeCaptureApi.calls == [(["SR-001"], ["app.py"])]

    def boom(core, sr_ids, paths):
        raise RuntimeError("backend down")

    monkeypatch.setattr(_FakeCaptureApi, "diff_serves", staticmethod(boom))
    assert check_msg(repo, "x\n\nSR: SR-001\n") == (0, [])
    monkeypatch.setitem(sys.modules, "plumb.capture.api", None)  # not built: no warning
    assert check_msg(repo, "x\n\nSR: SR-001\n") == (0, [])
