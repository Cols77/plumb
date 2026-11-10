"""BRIDGE B4: claimed versus declared paths over a range (spec 5.9)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from iaso import cli
from iaso.claims import claims_check, glob_match, load_policy

pytestmark = pytest.mark.sr("SR-261")

SR_003 = """---
id: SR-003
title: Links pin both ends
statement: Links pin both ends.
links:
- kind: implemented_by
  path: src/links.py
- kind: verified_by
  path: tests/test_links.py
---
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True, encoding="utf-8").stdout


def _commit(root: Path, files: dict[str, str], message: str) -> str:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").strip()


@pytest.fixture
def ranged(repo: Path, write_record) -> tuple[Path, str]:
    write_record(repo, SR_003)
    _commit(repo, {}, "record")
    base = _git(repo, "rev-parse", "HEAD").strip()
    return repo, base


def test_claims_reports_undeclared_paths(ranged) -> None:
    repo, base = ranged
    sha = _commit(repo, {"src/links.py": "x = 1\n", "src/other.py": "y = 1\n"},
                  "links\n\nSR: SR-003")
    result = claims_check(repo, f"{base}..HEAD")
    assert result["commits"] == 1
    assert result["undeclared"] == [{"commit": sha, "path": "src/other.py",
                                     "claims": ["SR-003"]}]


@pytest.mark.sr("SR-233")
def test_a_deleted_test_is_declared_by_the_record_that_linked_it_before(ranged) -> None:
    repo, _ = ranged
    base = _commit(repo, {"tests/test_links.py": "def test(): pass\n"}, "test\n\nSR: SR-003")
    (repo / ".iaso" / "requirements" / "SR-003.md").write_text(
        SR_003.replace("- kind: verified_by\n  path: tests/test_links.py\n", ""), "utf-8")
    (repo / "tests" / "test_links.py").unlink()
    _commit(repo, {}, "retire the test\n\nSR: SR-003")
    assert claims_check(repo, f"{base}..HEAD")["undeclared"] == []
    # a file that still exists needs a current link: unlinking and changing it is undeclared
    (repo / ".iaso" / "requirements" / "SR-003.md").write_text(
        SR_003.replace("- kind: implemented_by\n  path: src/links.py\n", ""), "utf-8")
    sha = _commit(repo, {"src/links.py": "x = 2\n"}, "change\n\nSR: SR-003")
    assert claims_check(repo, f"{base}..HEAD")["undeclared"] == [
        {"commit": sha, "path": "src/links.py", "claims": ["SR-003"]}]


def test_claims_default_exempt_globs(ranged) -> None:
    repo, base = ranged
    _commit(repo, {"docs/notes.md": "n\n", ".iaso/requirements/x.md": "",
                   "uv.lock": "", "tests/test_links.py": "def test(): pass\n"},
            "docs\n\nSR: SR-003")
    result = claims_check(repo, f"{base}..HEAD")
    assert result["undeclared"] == []
    assert glob_match("docs/**", "docs/a/b.md")
    assert not glob_match("src/*.py", "src/a/b.py")


def test_claims_extra_exempt_from_policy(ranged) -> None:
    repo, base = ranged
    (repo / ".iaso" / "claims.yaml").write_text("exempt: ['scripts/**']\n", encoding="utf-8")
    _commit(repo, {"scripts/x.py": ""}, "script\n\nSR: SR-003")
    assert claims_check(repo, f"{base}..HEAD")["undeclared"] == []
    assert "docs/**" in load_policy(repo).exempt


def test_claims_baseline_entries(ranged) -> None:
    repo, base = ranged
    sha = _commit(repo, {"src/other.py": "y\n"}, "other\n\nSR: SR-003")
    (repo / ".iaso" / "claims.yaml").write_text(
        f"baseline:\n- {{commit: {sha[:10]}, path: src/other.py, nc: NC-0001}}\n"
        f"- {{commit: abc, path: x}}\n", encoding="utf-8")
    result = claims_check(repo, f"{base}..HEAD")
    assert result["undeclared"] == []
    assert result["baseline"] == [{"commit": sha, "path": "src/other.py"}]
    assert any("NC" in p for p in result["problems"])


def test_claims_lists_commits_without_trailer(ranged) -> None:
    repo, base = ranged
    sha = _commit(repo, {"src/other.py": "y\n"}, "no trailer")
    result = claims_check(repo, f"{base}..HEAD")
    assert result["unclaimed_commits"] == [sha]
    assert result["undeclared"] == []


def test_claims_cli_exit_codes(ranged, capsys) -> None:
    repo, base = ranged
    _commit(repo, {"src/links.py": "x\n"}, "ok\n\nSR: SR-003")
    assert cli.main(["claims", "check", "--range", f"{base}..HEAD", "--root", str(repo)]) == 0
    assert "no undeclared paths" in capsys.readouterr().out
    _commit(repo, {"src/other.py": "x\n"}, "bad\n\nSR: SR-003")
    assert cli.main(["claims", "check", "--range", f"{base}..HEAD", "--json",
                     "--root", str(repo)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["undeclared"][0]["path"] == "src/other.py"
