"""IDS I7: the ``plumb merge-fix`` command (sp6 5.6; SR-071)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ids import scenario
from plumb.cli import main

pytestmark = pytest.mark.sr("SR-071")


def test_output_names_titles_not_paths(tmp_path: Path, capsys) -> None:
    s = scenario.build(tmp_path)
    assert main(["merge-fix", "--root", str(s.origin)]) == 0
    out = capsys.readouterr().out
    assert 'SR-002 "export csv" from the merged branch is now SR-003' in out
    assert "the owner's approval carried" in out and "3 commits' trailers mapped" in out
    assert ".plumb/" not in out and ".md" not in out


def test_json_shape(tmp_path: Path, capsys) -> None:
    s = scenario.build(tmp_path)
    assert main(["merge-fix", "--json", "--root", str(s.origin)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {"renumbered", "remaining", "blocked", "staged", "dry_run", "lines"}
    [row] = data["renumbered"]
    assert set(row) == {"from", "to", "title", "kind", "references", "files", "approvals",
                        "commits"}
    assert (row["from"], row["to"], row["kind"]) == ("SR-002", "SR-003", "requirement")
    assert data["remaining"] == [] and data["dry_run"] is False


def test_exit_codes(tmp_path: Path, capsys) -> None:
    s = scenario.build(tmp_path)
    assert main(["merge-fix", "--dry-run", "--root", str(s.origin)]) == 0
    assert main(["merge-fix", "--root", str(s.origin)]) == 0
    assert main(["merge-fix", "--root", str(s.origin)]) == 0  # nothing left
    assert main(["merge-fix", "--bogus", "--root", str(s.origin)]) == 2


def test_exit_1_when_a_side_is_not_a_record(tmp_path: Path, capsys) -> None:
    from ids.gitrepo import commit_all, make_repo, run_git, write

    root = make_repo(tmp_path / "r")
    run_git(root, "checkout", "-q", "-b", "side")
    path = root / ".plumb" / "requirements" / "SR-005.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\nid: SR-005\ntitle: [unclosed\n---\n", encoding="utf-8")
    commit_all(root, "side")
    run_git(root, "checkout", "-q", "main")
    write(root, "SR-005", "relay checks")
    commit_all(root, "main")
    run_git(root, "merge", "--no-edit", "side", check=False)
    assert main(["merge-fix", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "SR-005 still has two records" in out and "/plumb merge-fix" in out
