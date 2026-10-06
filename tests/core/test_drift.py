"""KS3: `plumb drift` prints only the drift signals (spec 5.10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import cli

INT = """---
id: INT-001
title: Grounded vibe coding
quote: "make vibe coding grounded on the projects artifacts"
readback: Ground the agent's work in the project's own records.
---
"""

SR = """---
id: SR-001
title: Links pin both ends
feature: FEAT-001
statement: Every link records the hash of both of its ends.
examples:
  - {id: EX-1, given: a current link, when: the target changes, then: the link is stale}
  - {id: EX-2, given: a current link, when: nothing changes, then: the link is current}
---
"""

FEAT = """---
id: FEAT-001
title: Core
description: The core.
requirements: [SR-001]
---
"""


def _setup(repo: Path, write_record) -> None:
    write_record(repo, INT)
    write_record(repo, SR)
    write_record(repo, FEAT)
    (repo / "src").mkdir()
    (repo / "src" / "links.py").write_text("def pin():\n    return 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_links.py").write_text("def test_pin():\n    assert True\n",
                                                   encoding="utf-8")
    root = ["--root", str(repo)]
    assert cli.main(["link", "SR-001", "derives_from", "INT-001", *root]) == 0
    assert cli.main(["link", "SR-001", "implemented_by", "src/links.py", *root]) == 0
    for example in ("EX-1", "EX-2"):
        assert cli.main(["link", "SR-001", "verified_by", "tests/test_links.py",
                         "--example", example, *root]) == 0


def _drift(repo: Path, capsys) -> tuple[int, dict]:
    capsys.readouterr()
    code = cli.main(["drift", "--json", "--root", str(repo)])
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.sr("SR-003")
def test_drift_clean_when_links_current_and_examples_covered(repo, write_record, capsys):
    _setup(repo, write_record)
    capsys.readouterr()
    assert cli.main(["drift", "--root", str(repo)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "drift: none"
    assert lines[1:] == ["advisory: fidelity never judged for 1 requirements (listed at the "
                         "merge boundary; plumb fidelity <SR>)"]


@pytest.mark.sr("SR-003")
def test_drift_reports_stale_link_with_moved_end(repo, write_record, capsys):
    _setup(repo, write_record)
    (repo / "src" / "links.py").write_text("def pin():\n    return 2\n", encoding="utf-8")
    code, data = _drift(repo, capsys)
    assert code == 1
    assert data["stale"] == [{"link": "SR-001#1", "moved": "target",
                              "target": "src/links.py"}]
    capsys.readouterr()
    cli.main(["drift", "--root", str(repo)])
    assert "SR-001#1 stale (target moved: src/links.py)" in capsys.readouterr().out


@pytest.mark.sr("SR-003")
def test_drift_reports_dangling_link(repo, write_record, capsys):
    _setup(repo, write_record)
    (repo / "src" / "links.py").unlink()
    code, data = _drift(repo, capsys)
    assert code == 1
    assert [d["link"] for d in data["dangling"]] == ["SR-001#1"]


@pytest.mark.sr("SR-003")
def test_drift_reports_uncovered_examples_of_any_requirement(repo, write_record, capsys):
    write_record(repo, INT)
    write_record(repo, SR)
    code, data = _drift(repo, capsys)
    assert code == 1
    assert data["uncovered_examples"] == {"SR-001": ["EX-1", "EX-2"]}


@pytest.mark.sr("SR-004")
def test_drift_reports_unconfirmed_edit(repo, write_record, capsys):
    _setup(repo, write_record)
    assert cli.main(["approve", "SR-001", "--root", str(repo)]) == 0
    sr = repo / ".plumb" / "requirements" / "SR-001.md"
    sr.write_text(sr.read_text(encoding="utf-8").replace(
        "hash of both of its ends", "hash of each of its two ends"), encoding="utf-8")
    code, data = _drift(repo, capsys)
    assert code == 1
    assert data["unconfirmed_edits"] == ["SR-001"]


@pytest.mark.sr("SR-022")
def test_drift_reports_fidelity_only_after_a_judgment(repo, write_record, capsys):
    """Never-judged fidelity is advisory (listed at the merge boundary, R4); a judgment that
    says drifts or unsure, or whose ends moved since, is a drift signal."""
    _setup(repo, write_record)
    code, data = _drift(repo, capsys)
    assert code == 0 and data["fidelity"] == []
    assert data["never_judged"] == ["SR-001"]
    assert cli.main(["judge", "SR-001", "--verdict", "fits", "--note", "ok",
                     "--root", str(repo)]) == 0
    code, data = _drift(repo, capsys)
    assert code == 0 and data["fidelity"] == [] and data["never_judged"] == []
    (repo / "src" / "links.py").write_text("def pin():\n    return 3\n", encoding="utf-8")
    assert cli.main(["repin", "SR-001#1", "--root", str(repo)]) == 0
    code, data = _drift(repo, capsys)
    assert code == 1
    assert data["fidelity"] == [{"requirement": "SR-001", "state": "unjudged"}]
