"""SR-432: the records folder is .iaso."""

from pathlib import Path

import pytest

from iaso.paths import find_root, state_dir


@pytest.mark.sr("SR-432")
def test_state_dir_new_repo_is_dot_iaso(tmp_path: Path) -> None:
    assert state_dir(tmp_path) == tmp_path / ".iaso"


@pytest.mark.sr("SR-432")
def test_find_root_finds_dot_iaso(tmp_path: Path) -> None:
    (tmp_path / ".iaso").mkdir()
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert find_root(sub) == tmp_path.resolve()


@pytest.mark.sr("SR-432")
def test_a_new_repo_keeps_everything_under_dot_iaso(tmp_path: Path) -> None:
    """The link map, the debug cases, the log and the merge check of a new repository read
    and write under .iaso: nothing creates an old-name folder, which would hide its records."""
    import subprocess

    from iaso import debug, log, stale
    from iaso.boundary.premerge import unstaged_iaso
    from iaso.commands import init_repo

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    init_repo(tmp_path)
    (tmp_path / ".iaso" / "requirements" / "SR-001.md").write_text("---\nid: SR-001\n---\n",
                                                                    encoding="utf-8")
    new = tmp_path / ".iaso"
    assert stale.cache_path(tmp_path).is_relative_to(new)
    assert debug._case_path(tmp_path, "c1").is_relative_to(new)
    assert ".iaso/requirements/SR-001.md" in unstaged_iaso(tmp_path)
    assert log.tracked_names(tmp_path) == set()
    assert not (tmp_path / ("." + "plum" + "b")).exists()
