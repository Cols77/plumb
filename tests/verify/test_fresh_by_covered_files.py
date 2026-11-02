"""SR-374 EX-11, DEC-377: test evidence stays fresh while the files the test covers are
unchanged; a commit elsewhere does not stale it."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import commit_all, make_project, write

from plumb.api import open_core
from plumb.verify import open_verify


@pytest.mark.sr("SR-374")
def test_ex11_a_commit_to_another_file_leaves_the_evidence_fresh(repo: Path) -> None:
    make_project(repo)
    commit_all(repo)
    node = "tests/test_mod.py::test_add"
    assert open_verify(open_core(repo)).run(nodes=["tests/test_mod.py"]).ok
    write(repo, "src/pkg/lonely.py", "VALUE = 2\n")       # a file test_mod does not cover
    commit_all(repo, "one file changed")
    assert open_verify(open_core(repo)).evidence([node])[node].state == "fresh-pass"
    write(repo, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")   # one it covers
    commit_all(repo, "the covered file changed")
    assert open_verify(open_core(repo)).evidence([node])[node].state == "stale"
