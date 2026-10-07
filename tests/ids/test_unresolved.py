"""IDS: ``merge-fix`` renumbers nothing while a file naming the colliding ID cannot be read
(sp6 5.3, 5.6; SR-071).

Rewriting around such a file would leave the incoming side's reference on the first
parent's record once the owner resolves it. ``merge_fix`` has one gate before any
reservation or write (``mergefix._unresolved``): a record, test or claims file whose
incoming version names the old ID and that is still unmerged or does not read. One test
per kind of file, the dry run, and the committed merge."""

from __future__ import annotations

from pathlib import Path

import pytest

from ids import scenario
from ids.gitrepo import commit_all, run_git
from plumb import ids
from plumb.api import open_core
from plumb.cli import main

pytestmark = pytest.mark.sr("SR-071")

FEAT = ".plumb/features/FEAT-001.md"
SR_PATH = ".plumb/requirements/SR-002.md"


def _feature(root: Path, description: str, requirements: list[str]) -> None:
    (root / FEAT).write_text(
        "---\nid: FEAT-001\ntitle: io\ndescription: " + description + "\nrequirements:\n"
        + "".join(f"- {r}\n" for r in requirements) + "---\n", encoding="utf-8")


def _merge(s: scenario.Scenario) -> None:
    run_git(s.origin, "fetch", "-q", str(s.clone), "main:incoming")
    out = run_git(s.origin, "merge", "--no-edit", "incoming", check=False)
    assert "CONFLICT" in out, out


def _feature_conflict(tmp_path: Path) -> scenario.Scenario:
    """Both sides edit FEAT-001 on adjacent lines; the incoming side lists its SR-002."""
    s = scenario.build(tmp_path, merge=False)
    _feature(s.clone, "d, with csv", ["SR-001", "SR-002"])
    commit_all(s.clone, "feature lists export\n\nSR: SR-002")
    _feature(s.origin, "d, with relays", ["SR-001"])
    commit_all(s.origin, "feature reworded\n\nSR: SR-001")
    _merge(s)
    return s


def _untouched(s: scenario.Scenario, before_ref: str) -> None:
    assert not (s.origin / ".plumb" / "requirements" / "SR-003.md").exists()
    assert run_git(s.origin, "rev-parse", ids.REF).strip() == before_ref
    assert not [e for e in open_core(s.origin).events() if e.kind == "renumber"]


def test_unmerged_record_naming_the_id_blocks(tmp_path: Path, capsys) -> None:
    s = _feature_conflict(tmp_path)
    before = run_git(s.origin, "rev-parse", ids.REF).strip()
    result = ids.merge_fix(open_core(s.origin))
    assert result.renumbered == () and result.blocked == (FEAT,)
    assert [c.id for c in result.remaining] == ["SR-002"]
    assert "is not renumbered yet" in result.lines[0] and FEAT not in result.lines[0]
    assert main(["merge-fix", "--root", str(s.origin)]) == 1
    _untouched(s, before)
    # the owner resolves the feature keeping both sides; now the incoming entry follows
    _feature(s.origin, "d, with relays and csv", ["SR-001", "SR-002"])
    run_git(s.origin, "add", FEAT)
    capsys.readouterr()
    assert main(["merge-fix", "--root", str(s.origin)]) == 0
    assert "now SR-003" in capsys.readouterr().out
    assert open_core(s.origin).index()["FEAT-001"].fields["requirements"] == \
        ["SR-001", "SR-003"]


def test_dry_run_blocks_too(tmp_path: Path) -> None:
    s = _feature_conflict(tmp_path)
    before = run_git(s.origin, "rev-parse", ids.REF).strip()
    result = ids.merge_fix(open_core(s.origin), dry_run=True)
    assert result.blocked == (FEAT,) and result.renumbered == () and result.remaining
    assert main(["merge-fix", "--dry-run", "--root", str(s.origin)]) == 1
    _untouched(s, before)


def test_unmerged_test_file_naming_the_id_blocks(tmp_path: Path) -> None:
    s = scenario.build(tmp_path, merge=False)
    (s.clone / "tests" / "test_shared.py").write_text(
        'import pytest\n\n\n@pytest.mark.sr("SR-002")\ndef test_shared():\n    pass\n',
        encoding="utf-8")
    commit_all(s.clone, "shared test\n\nSR: SR-002")
    (s.origin / "tests" / "test_shared.py").write_text(
        "def test_shared():\n    assert 1\n", encoding="utf-8")
    commit_all(s.origin, "shared test\n\nSR: SR-002")
    _merge(s)
    before = run_git(s.origin, "rev-parse", ids.REF).strip()
    result = ids.merge_fix(open_core(s.origin))
    assert result.blocked == ("tests/test_shared.py",) and result.renumbered == ()
    _untouched(s, before)


def test_committed_conflict_markers_block(tmp_path: Path) -> None:
    s = _feature_conflict(tmp_path)
    run_git(s.origin, "checkout", "--ours", "--", SR_PATH)  # kept one, by hand
    run_git(s.origin, "add", "-A")  # FEAT-001 still holds its conflict markers
    run_git(s.origin, "commit", "-q", "--no-verify", "--no-edit")
    assert "<<<<<<<" in (s.origin / FEAT).read_text(encoding="utf-8")
    before = run_git(s.origin, "rev-parse", ids.REF).strip()
    result = ids.merge_fix(open_core(s.origin))
    assert result.blocked == (FEAT,) and result.renumbered == ()
    assert [c.how for c in result.remaining] == ["kept-one"]
    _untouched(s, before)


def test_unrelated_unmerged_file_does_not_block(tmp_path: Path) -> None:
    s = scenario.build(tmp_path, merge=False)
    (s.clone / "tests" / "test_shared.py").write_text("X = 1\n", encoding="utf-8")
    commit_all(s.clone, "shared\n\nSR: SR-002")
    (s.origin / "tests" / "test_shared.py").write_text("X = 2\n", encoding="utf-8")
    commit_all(s.origin, "shared\n\nSR: SR-002")
    _merge(s)
    result = ids.merge_fix(open_core(s.origin))
    assert result.blocked == () and [r["to"] for r in result.renumbered] == ["SR-003"]
