"""IDS: two files holding one record are not an ID collision (sp6 5.1; concept 4.4; SR-072).

"The same record" is ``collision.same_record``: equal record hashes, which leave ``links``
and their pins out. A side that only linked or repinned an imported record, or a merge
driver resolution equal after parsing, is one record. One test per check that compares:
the unmerged add/add, two files in the working tree, the add/add a merge kept one of, and
the ``--from`` preview; and ``merge-fix`` renumbers none of them."""

from __future__ import annotations

from pathlib import Path

import pytest

from ids.gitrepo import commit_all, make_repo, record_text, run_git, write
from plumb import ids
from plumb.api import open_core
from plumb.cli import main

pytestmark = pytest.mark.sr("SR-257")

LINKS = [{"kind": "implemented_by", "path": "a.py"}]
TITLE = "imported on both sides"


def _both_sides_add(tmp_path: Path, *, merge: bool = True) -> Path:
    """``side`` adds SR-009 and links it; ``main`` adds the same SR-009 unlinked."""
    root = make_repo(tmp_path / "r")
    run_git(root, "checkout", "-q", "-b", "side")
    write(root, "SR-009", TITLE, links=LINKS)
    commit_all(root, "side")
    run_git(root, "checkout", "-q", "main")
    write(root, "SR-009", TITLE)
    commit_all(root, "main")
    if merge:
        run_git(root, "merge", "--no-edit", "side", check=False)
    return root


def test_unmerged_add_add_differing_only_in_links_is_not(tmp_path: Path) -> None:
    root = _both_sides_add(tmp_path)
    assert "SR-009.md" in run_git(root, "ls-files", "-u")  # git did stop on it
    assert ids.collisions(open_core(root)) == ()
    result = ids.merge_fix(open_core(root))
    assert result.renumbered == () and result.remaining == ()
    assert sorted(p.name for p in (root / ".plumb" / "requirements").glob("*.md")) == \
        ["SR-009.md"]


def test_duplicate_files_differing_only_in_links_are_not(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    write(root, "SR-009", TITLE)
    (root / ".plumb" / "requirements" / "SR-009-copy.md").write_text(
        record_text("SR-009", TITLE, links=LINKS), encoding="utf-8")
    assert ids.collisions(open_core(root)) == ()


def test_kept_one_resolved_to_the_linked_record_is_not(tmp_path: Path) -> None:
    root = _both_sides_add(tmp_path)
    write(root, "SR-009", TITLE, links=LINKS)  # the resolution a merge driver writes
    run_git(root, "add", "-A")
    run_git(root, "commit", "-q", "--no-verify", "--no-edit")
    assert ids.collisions(open_core(root), "HEAD^1") == ()


def test_from_preview_of_the_same_record_is_not(tmp_path: Path, capsys) -> None:
    root = _both_sides_add(tmp_path, merge=False)
    assert ids.merge_fix(open_core(root), from_ref="side").remaining == ()
    assert main(["merge-fix", "--from", "side", "--root", str(root)]) == 0
    assert "nothing to fix" in capsys.readouterr().out


def test_a_different_title_is_still_a_collision(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    run_git(root, "checkout", "-q", "-b", "side")
    write(root, "SR-009", "export csv", links=LINKS)
    commit_all(root, "side")
    run_git(root, "checkout", "-q", "main")
    write(root, "SR-009", "relay checks")
    commit_all(root, "main")
    run_git(root, "merge", "--no-edit", "side", check=False)
    [found] = ids.collisions(open_core(root))
    assert found.sides == ("relay checks", "export csv")
