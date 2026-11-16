"""SR-254 (owner, DEC-551): the landing's version bump in pyproject.toml (SR-377) changes no
test, so it is no shared test infrastructure change: it sets no full run pending and keeps the
after-main-moves covering run; any other pyproject.toml change still needs the full suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import PYPROJECT, commit_all, make_project, write

from iaso.api import open_core
from iaso.boundary import fullrun
from iaso.verify import open_verify
from iaso.verify.select import without_version

pytestmark = pytest.mark.sr("SR-254")

VERSIONED = '[project]\nname = "pkg"\nversion = "0.1.1"\n\n' + PYPROJECT


@pytest.fixture
def green(repo: Path) -> Path:
    make_project(repo)
    write(repo, "pyproject.toml", VERSIONED)
    commit_all(repo, "base")
    assert open_verify(open_core(repo)).run(full=True).ok
    return repo


def _bump(root: Path, extra: str = "") -> None:
    write(root, "pyproject.toml", VERSIONED.replace('"0.1.1"', '"0.1.2"') + extra)


def test_without_version_drops_only_the_project_version_line() -> None:
    text = '[project]\nname = "p"\nversion = "1"\n[tool.x]\nversion = "keep"\n'
    assert without_version(text) == '[project]\nname = "p"\n[tool.x]\nversion = "keep"\n'


def test_a_version_bump_sets_no_full_run_pending(green: Path) -> None:
    _bump(green)
    assert not open_verify(open_core(green)).full_pending().pending
    _bump(green, "# a pytest setting moved\n")
    pending = open_verify(open_core(green)).full_pending()
    assert pending.pending and pending.reasons == ("pyproject.toml changed",)


def test_after_a_landing_bumps_the_version_main_moving_keeps_the_covering_run(
        green: Path) -> None:
    _bump(green)
    write(green, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    commit_all(green, "merge main: a landing's version bump and a source change")
    core = open_core(green)
    verify = open_verify(core)
    plan = fullrun.delta_plan(core, verify, fullrun.current_identity(core, verify))
    assert plan is not None and plan[1] == ["src/pkg/mod.py"]


def test_any_other_pyproject_change_still_needs_a_full_run(green: Path) -> None:
    _bump(green, "# a pytest setting moved\n")
    write(green, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    commit_all(green, "merge main")
    core = open_core(green)
    verify = open_verify(core)
    assert fullrun.delta_plan(core, verify, fullrun.current_identity(core, verify)) is None


def test_a_full_run_that_hashed_pyproject_whole_still_counts_after_a_bump(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A run recorded before EX-24 hashed the whole file; a later bump alone keeps it counting."""
    from iaso.normalize import file_digest
    from iaso.verify import select

    make_project(repo)
    write(repo, "pyproject.toml", VERSIONED)
    commit_all(repo, "base")
    with monkeypatch.context() as m:
        m.setattr(select, "infra_digest", lambda rel, path: file_digest(path))
        assert open_verify(open_core(repo)).run(full=True).ok
    _bump(repo)
    commit_all(repo, "a landing's bump")
    assert not open_verify(open_core(repo)).full_pending().pending
    _bump(repo, "# a pytest setting moved\n")
    assert open_verify(open_core(repo)).full_pending().pending
