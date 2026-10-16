"""VS4: ``plumb impact <ID|path>``: downstream records and covering tests with evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from verify_helpers import SR_TEXT, commit_all, make_project

from plumb import cli
from plumb.api import open_core
from plumb.contracts import Target
from plumb.verify import open_verify

INT_TEXT = """---
id: INT-001
title: Numbers add up
quote: "add numbers"
---
"""


@pytest.mark.sr("SR-255")
def test_impact_lists_records_and_tests(repo: Path, write_record,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    make_project(repo)
    write_record(repo, INT_TEXT)
    write_record(repo, SR_TEXT)
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/pkg/mod.py"))
    commit_all(repo)
    open_verify(open_core(repo)).run(nodes=["tests/test_mod.py"])
    root = ["--root", str(repo)]

    assert cli.main(["impact", "src/pkg/mod.py", "--json", *root]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["records"] == ["SR-001"]
    tests = {t["test"]: t["state"] for t in data["tests"]}
    assert tests["tests/test_mod.py"] == "fresh-pass"
    assert tests["tests/test_helper.py"] == "none"

    assert cli.main(["impact", "INT-001", "--json", *root]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["records"] == ["SR-001"]
    assert "tests/test_mod.py::test_add" in {t["test"] for t in data["tests"]}

    assert cli.main(["impact", "SR-001", *root]) == 0
    out = capsys.readouterr().out
    assert "src/pkg/mod.py" in out
    assert "tests/test_mod.py::test_add  fresh-pass" in out
