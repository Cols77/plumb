"""A3: overlaps across real worktrees, read-only (SR-078, SR-079)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from awareness.gitrepo import add_worktree, commit_all, listing, make_repo, requirement
from plumb import awareness
from plumb.api import open_core
from plumb.awareness import publish as pub
from plumb.present.delta import Emitter


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    main = make_repo(tmp_path / "main")
    requirement(main, "SR-005", "relay checks", "A relay pins every stated record.")
    requirement(main, "SR-006", "status card")
    commit_all(main, "records")
    other = add_worktree(main, tmp_path / "wt-x", "feat-x")
    return main, other


def _edit(root: Path, statement: str, record: str = "SR-005", title: str = "relay checks"
          ) -> None:
    requirement(root, record, title, statement)
    pub.publish(open_core(root), [f".plumb/requirements/{record}.md"])


@pytest.mark.sr("SR-258")
def test_brief_names_record_and_branch(tmp_path: Path) -> None:
    """SR-078 EX-1: feat-x edited SR-005; a session starts in main's worktree, which works
    on SR-005 too: the brief names it and the branch."""
    main, other = _pair(tmp_path)
    _edit(other, "A relay pins the stated group, named by its title.")
    _edit(main, "A relay pins only the records the owner's words affirm.")
    lines = awareness.brief_lines(open_core(main))
    assert lines == ['plumb: SR-005 "relay checks" is also being changed on branch feat-x']


@pytest.mark.sr("SR-258")
def test_delta_line_once_then_again_after_other_side_changes(tmp_path: Path) -> None:
    """SR-078 EX-2: once per session; again only when the other side's version changed."""
    main, other = _pair(tmp_path)
    _edit(other, "first version on feat-x")
    seen = tmp_path / "session" / "seen.json"

    def prompt() -> list[str]:
        emitter = Emitter(seen, "prompt", None)
        out = emitter.add(awareness.delta_lines(open_core(main), ["SR-005"]))
        emitter.close()
        return out

    first = prompt()
    assert first == ['plumb: SR-005 "relay checks" is also being changed on branch feat-x']
    assert prompt() == []
    time.sleep(0.02)
    _edit(other, "second version on feat-x")
    assert prompt() == first


@pytest.mark.sr("SR-258")
def test_no_overlap_no_line_and_no_status_field(tmp_path: Path) -> None:
    """SR-078 EX-4: nothing shared, nothing shown."""
    main, other = _pair(tmp_path)
    _edit(other, "feat-x changes SR-006 only", record="SR-006", title="status card")
    _edit(main, "main changes SR-005 only")
    core = open_core(main)
    assert awareness.brief_lines(core) == []
    assert awareness.delta_lines(core, ["SR-005"]) == []
    assert awareness.snapshot_fields(core, ["SR-005"]) == {}


@pytest.mark.sr("SR-258")
def test_other_worktree_untouched(tmp_path: Path) -> None:
    """SR-079 EX-3: reading another worktree creates or modifies nothing there."""
    main, other = _pair(tmp_path)
    _edit(other, "feat-x version")
    _edit(main, "main version")
    before = listing(other)
    core = open_core(main)
    awareness.brief_lines(core)
    awareness.delta_lines(core, ["SR-005"])
    awareness.snapshot_fields(core, ["SR-005"])
    awareness.status_section(core)
    assert listing(other) == before


@pytest.mark.sr("SR-258")
def test_stale_changing_json_ignored(tmp_path: Path) -> None:
    main, other = _pair(tmp_path)
    _edit(other, "feat-x version, long ago")
    old = time.time() - 8 * 86400
    path = pub.changing_path(other)
    os.utime(path, (old, old))
    record_file = other / ".plumb" / "requirements" / "SR-005.md"
    os.utime(record_file, (old, old))
    assert awareness.overlaps(open_core(main), ["SR-005"]) == ()


@pytest.mark.sr("SR-258")
def test_reader_maps_paths_with_own_index(tmp_path: Path) -> None:
    """A stale ``records`` map does not hide a changed end: the reader maps the paths."""
    main, other = _pair(tmp_path)
    from plumb.contracts import Target

    (main / "src").mkdir()
    (main / "src" / "relay.py").write_text("x = 1\n", encoding="utf-8")
    open_core(main).add_link("SR-005", "implemented_by", Target(path="src/relay.py"))
    commit_all(main, "link")
    pub.note_edit(other, "src/relay.py")          # the post-edit hook: a path, no records
    data = json.loads(pub.changing_path(other).read_text(encoding="utf-8"))
    assert data["records"] == {}
    found = awareness.overlaps(open_core(main), ["SR-005"])
    assert [(o.record, o.branch, o.how) for o in found] == [("SR-005", "feat-x", "ends")]
