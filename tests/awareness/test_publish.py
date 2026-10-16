"""A2: each worktree publishes what it is changing into its own cache (SR-079)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from awareness.gitrepo import add_worktree, commit_all, make_repo, requirement
from plumb.api import open_core
from plumb.awareness import publish as pub

pytestmark = pytest.mark.sr("SR-258")


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    main = make_repo(tmp_path / "main")
    requirement(main, "SR-001", "relay checks")
    requirement(main, "SR-002", "status card")
    (main / "src").mkdir()
    (main / "src" / "relay.py").write_text("x = 1\n", encoding="utf-8")
    core = open_core(main)
    core.add_link("SR-002", "implemented_by", _target("src/relay.py"))
    commit_all(main, "records")
    other = add_worktree(main, tmp_path / "wt-x", "feat-x")
    return main, other


def _target(path: str):  # noqa: ANN202
    from plumb.contracts import Target

    return Target(path=path)


def test_publishes_edited_new_and_ends(tmp_path: Path) -> None:
    _main, other = _setup(tmp_path)
    requirement(other, "SR-001", "relay checks", "relay pins the stated group")
    commit_all(other, "edit SR-001")
    requirement(other, "SR-003", "new thing")
    commit_all(other, "new SR-003")
    (other / "src" / "relay.py").write_text("x = 2\n", encoding="utf-8")
    data = pub.publish(open_core(other), ["src/relay.py"])
    assert data is not None
    assert data["branch"] == "feat-x"
    assert data["records"]["SR-001"]["how"] == "edited"
    assert data["records"]["SR-003"]["how"] == "new"
    assert data["records"]["SR-002"]["how"] == "ends"
    assert data["records"]["SR-001"]["title"] == "relay checks"
    assert data["records"]["SR-001"]["hash"].startswith("sha256:")
    on_disk = json.loads(pub.changing_path(other).read_text(encoding="utf-8"))
    assert on_disk["records"] == data["records"]
    assert "src/relay.py" in on_disk["pending"]


def test_committed_part_recomputed_only_when_head_moved(tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch
                                                        ) -> None:
    _main, other = _setup(tmp_path)
    requirement(other, "SR-001", "relay checks", "changed")
    commit_all(other, "edit")
    calls: list[list[str]] = []
    real = subprocess.run

    def counting(args, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        calls.append(list(args))
        return real(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", counting)
    core = open_core(other)
    pub.publish(core, [])
    assert len([c for c in calls if c[0] == "git"]) == 2       # merge-base, diff
    calls.clear()
    pub.publish(core, ["src/relay.py"])
    pub.publish(core, [])
    assert [c for c in calls if c[0] == "git"] == []           # HEAD did not move
    monkeypatch.setattr(subprocess, "run", real)
    requirement(other, "SR-002", "status card", "changed too")
    commit_all(other, "edit 2")
    monkeypatch.setattr(subprocess, "run", counting)
    data = pub.publish(open_core(other), [])
    assert len([c for c in calls if c[0] == "git"]) == 2
    assert data is not None and set(data["records"]) >= {"SR-001", "SR-002"}


def test_default_branch_has_no_committed_part(tmp_path: Path) -> None:
    main, _other = _setup(tmp_path)
    data = pub.publish(open_core(main), [".plumb/requirements/SR-001.md"])
    assert data is not None and data["committed"] == []
    assert data["records"]["SR-001"]["how"] == "edited"


def test_note_edit_appends_path_without_index(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    _main, other = _setup(tmp_path)
    import plumb.api

    def no_index(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("note_edit opened the record index")

    monkeypatch.setattr(plumb.api, "open_core", no_index)
    monkeypatch.setattr(subprocess, "run", no_index)
    pub.note_edit(other, "src/relay.py")
    pub.note_edit(other, "src/relay.py")
    pub.note_edit(other, ".plumb/requirements/SR-001.md")
    data = pub.read_changing(pub.changing_path(other))
    assert data is not None
    assert data["pending"] == [".plumb/requirements/SR-001.md", "src/relay.py"]


def test_write_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _main, other = _setup(tmp_path)
    pub.publish(open_core(other), ["src/relay.py"])
    before = pub.changing_path(other).read_bytes()
    replaced: list[tuple[str, str]] = []
    real = os.replace

    def watch(src, dst):  # noqa: ANN001, ANN202
        replaced.append((Path(src).name, Path(dst).name))
        assert Path(dst).read_bytes() == before        # the old file stays whole until then
        return real(src, dst)

    monkeypatch.setattr(os, "replace", watch)
    pub.note_edit(other, "src/other.py")
    assert replaced and replaced[0][1] == "changing.json" and replaced[0][0].endswith(".tmp")
    assert not list(pub.changing_path(other).parent.glob("*.tmp"))
