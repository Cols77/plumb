"""Case report-818ae7ac: a path an old session touched whose file is gone (renamed away) is no
changed path; a run records none of it."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import commit_all, make_project

from iaso.api import open_core
from iaso.verify import open_verify

pytestmark = pytest.mark.sr("SR-255")


def test_a_touched_path_whose_file_is_gone_is_not_changed(repo: Path) -> None:
    make_project(repo)
    commit_all(repo)
    old = repo / ".iaso" / "session" / "ended-long-ago"
    old.mkdir(parents=True)
    (old / "touched.txt").write_text("src/oldname/text.py\nsrc/pkg/helper.py\n", encoding="utf-8")
    assert open_verify(open_core(repo)).changed_paths() == ["src/pkg/helper.py"]
