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


# --------------------------------------------------------------------------- kept one
# A merge stopped on an add/add of one record and someone resolved it by hand to one text:
# the incoming record is lost from the tree. Every entry point still reports the collision
# (they all read ``ids.collisions``), and merge-fix restores the incoming record renumbered.

SR_PATH = ".plumb/requirements/SR-002.md"


def _resolved_by_hand(tmp_path: Path, *, commit: bool = True) -> scenario.Scenario:
    s = scenario.build(tmp_path, approve=False, trailer_in_message=False)
    run_git(s.origin, "checkout", "--ours", "--", SR_PATH)
    run_git(s.origin, "add", "-A")
    if commit:
        run_git(s.origin, "commit", "-q", "--no-verify", "--no-edit")
    return s


def test_kept_one_merge_in_progress_is_a_collision(tmp_path: Path) -> None:
    s = _resolved_by_hand(tmp_path, commit=False)
    [found] = ids.collisions(open_core(s.origin))
    assert (found.id, found.how, found.paths) == ("SR-002", "kept-one", (SR_PATH,))
    assert found.sides == ("relay checks", "export csv")


@pytest.mark.parametrize("command", [["check", "--merge", "HEAD^1"],
                                     ["merge-check", "HEAD^1", "--no-run"]])
def test_kept_one_committed_merge_holds_the_report(tmp_path: Path, capsys, command) -> None:
    s = _resolved_by_hand(tmp_path)
    assert ids.collisions(open_core(s.origin), "HEAD^1")[0].how == "kept-one"
    code = main([*command, "--root", str(s.origin)])
    out = capsys.readouterr().out
    assert code == 1
    assert "ID collisions hold the merge" in out
    assert '"relay checks" and "export csv"' in out and "the merge kept only one" in out


def test_kept_one_committed_merge_holds_the_pre_push_hook(tmp_path: Path, capsys,
                                                          monkeypatch) -> None:
    import io
    import sys

    s = _resolved_by_hand(tmp_path)
    head = run_git(s.origin, "rev-parse", "HEAD").strip()
    first = run_git(s.origin, "rev-parse", "HEAD^1").strip()
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        f"refs/heads/main {head} refs/heads/main {first}\n"))
    code = main(["merge-check", "--hook", "pre-push", "--no-run", "--root", str(s.origin)])
    captured = capsys.readouterr()
    assert code == 1
    assert "ID collisions hold the merge" in captured.out
    assert "the push is refused" in captured.err


def test_kept_one_committed_merge_is_fixed_by_merge_fix(tmp_path: Path, capsys) -> None:
    s = _resolved_by_hand(tmp_path)
    assert main(["merge-fix", "--root", str(s.origin)]) == 0
    assert "now SR-003" in capsys.readouterr().out
    index = open_core(s.origin).index()
    assert index["SR-002"].title == "relay checks"
    assert index["SR-003"].title == "export csv"
    dec = index["DEC-001"]
    assert [lk.target.record for lk in dec.links if lk.kind == "decides"] == ["SR-003"]
    marker = (s.origin / "tests" / "test_export.py").read_text(encoding="utf-8")
    assert marker.count('mark.sr("SR-003")') == 2
    assert ids.collisions(open_core(s.origin), "HEAD^1") == ()
    assert main(["merge-fix", "--root", str(s.origin)]) == 0
    assert "nothing to fix" in capsys.readouterr().out


def test_kept_one_merge_in_progress_is_fixed_and_staged(tmp_path: Path) -> None:
    s = _resolved_by_hand(tmp_path, commit=False)
    result = ids.merge_fix(open_core(s.origin))
    assert [r["to"] for r in result.renumbered] == ["SR-003"] and result.remaining == ()
    assert ".plumb/requirements/SR-003.md" in result.staged
    assert ids.collisions(open_core(s.origin)) == ()
