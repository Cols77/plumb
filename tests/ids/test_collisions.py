"""IDS I4: ID collisions and the merge report's ``id_collisions`` section (sp6 5.1, 10;
SR-072)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ids import scenario
from ids.gitrepo import commit_all, make_repo, record_text, run_git, write
from plumb import ids
from plumb.api import open_core
from plumb.cli import main

pytestmark = pytest.mark.sr("SR-072")


def test_unmerged_add_add_is_a_collision(tmp_path: Path) -> None:
    s = scenario.build(tmp_path)
    [found] = ids.collisions(open_core(s.origin))
    assert (found.id, found.how) == ("SR-002", "add/add")
    assert found.paths == (".plumb/requirements/SR-002.md",)
    assert found.sides == ("relay checks", "export csv")


def test_same_content_add_add_is_not(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    run_git(root, "checkout", "-q", "-b", "side")
    write(root, "SR-009", "imported on both sides")
    commit_all(root, "side")
    run_git(root, "checkout", "-q", "main")
    write(root, "SR-009", "imported on both sides")
    commit_all(root, "main")
    run_git(root, "merge", "--no-edit", "side")
    assert ids.collisions(open_core(root)) == ()


def test_duplicate_ids_at_two_paths(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    write(root, "SR-005", "first")
    commit_all(root, "first")
    (root / ".plumb" / "requirements" / "SR-005-copy.md").write_text(
        record_text("SR-005", "second"), encoding="utf-8")
    [found] = ids.collisions(open_core(root))
    assert found.how == "duplicate"
    assert found.paths == (".plumb/requirements/SR-005.md",
                           ".plumb/requirements/SR-005-copy.md")
    assert found.sides == ("first", "second")


def test_from_ref_preview_writes_nothing(tmp_path: Path) -> None:
    s = scenario.build(tmp_path, merge=False)
    run_git(s.origin, "fetch", "-q", str(s.clone), "main:incoming")
    ref = run_git(s.origin, "rev-parse", ids.REF).strip()
    head = run_git(s.origin, "rev-parse", "HEAD").strip()
    assert main(["merge-fix", "--from", "incoming", "--root", str(s.origin)]) == 1
    assert run_git(s.origin, "status", "--porcelain") == ""
    assert run_git(s.origin, "rev-parse", ids.REF).strip() == ref
    assert run_git(s.origin, "rev-parse", "HEAD").strip() == head


@pytest.mark.parametrize("command", [["check", "--merge", "HEAD"],
                                     ["merge-check", "HEAD", "--no-run"]])
def test_merge_report_exits_1_with_fix_line(tmp_path: Path, capsys, command) -> None:
    s = scenario.build(tmp_path)
    code = main([*command, "--root", str(s.origin)])
    out = capsys.readouterr().out
    assert code == 1
    assert "ID collisions hold the merge" in out
    assert '"relay checks" and "export csv"' in out
    assert ".plumb/requirements/SR-002.md" in out and "/plumb merge-fix fixes it" in out


def test_duplicate_named_with_both_files(tmp_path: Path, capsys) -> None:
    root = make_repo(tmp_path / "r")
    write(root, "SR-070", "relay checks")
    (root / ".plumb" / "requirements" / "SR-070-b.md").write_text(
        record_text("SR-070", "export csv"), encoding="utf-8")
    assert main(["check", "--merge", "main", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    [line] = [x for x in out.splitlines() if "/plumb merge-fix fixes it" in x]
    assert ".plumb/requirements/SR-070.md" in line and ".plumb/requirements/SR-070-b.md" in line


@pytest.mark.parametrize("command", [["check", "--merge", "HEAD"],
                                     ["merge-check", "HEAD", "--no-run"]])
def test_no_collision_after_fix(tmp_path: Path, capsys, command) -> None:
    s = scenario.build(tmp_path)
    assert main(["merge-fix", "--root", str(s.origin)]) == 0
    capsys.readouterr()
    main([*command, "--json", "--root", str(s.origin)])
    out = capsys.readouterr().out
    assert '"id_collisions": []' in out
