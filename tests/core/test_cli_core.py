"""K1 and K7: init, status and link through the CLI."""

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
---
Body.
"""

FEAT = """---
id: FEAT-001
title: Core
description: The core.
requirements: [SR-001]
---
"""


@pytest.mark.sr("SR-280")
def test_init_is_idempotent_and_writes_ignore_and_attributes(tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    assert cli.main(["init", "--root", str(root)]) == 0
    plumb = root / ".plumb"
    for name in ("intents", "requirements", "decisions", "features", "ncs", "log"):
        assert (plumb / name).is_dir()
    # one file per entry (SP6 6.5): init creates no JSONL log
    assert not (plumb / "log" / "events.jsonl").exists()
    assert not (plumb / "log" / "evidence.jsonl").exists()
    ignore = (plumb / ".gitignore").read_text(encoding="utf-8").split()
    assert {"cache/", "session/", "test_map.txt"} <= set(ignore)
    assert "merge=union" in (plumb / ".gitattributes").read_text(encoding="utf-8")
    assert (plumb / "config.yaml").exists()
    assert "require_trailer" in (plumb / "claims.yaml").read_text(encoding="utf-8")
    (plumb / "config.yaml").write_text("verify:\n  turn_budget_s: 7\n", encoding="utf-8")
    (plumb / "log" / "events.jsonl").write_text('{"x": 1}\n', encoding="utf-8")
    before = {p: p.read_bytes() for p in plumb.rglob("*") if p.is_file()}
    assert cli.main(["init", "--root", str(root)]) == 0
    after = {p: p.read_bytes() for p in plumb.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.sr("SR-278")
def test_status_json_counts(repo: Path, write_record, capsys: pytest.CaptureFixture[str]) -> None:
    write_record(repo, INT)
    write_record(repo, SR)
    write_record(repo, FEAT)
    assert cli.main(["link", "SR-001", "derives_from", "INT-001", "--root", str(repo)]) == 0
    capsys.readouterr()
    assert cli.main(["status", "--json", "--root", str(repo)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["records"] == {"intent": 1, "requirement": 1, "decision": 0, "feature": 1,
                               "nc": 0}
    assert data["requirements"] == {"total": 1, "confirmed": 0, "covered": 0, "failing": 0}
    assert data["confirmation"]["proposed"] == 3
    assert data["links"]["current"] == 1
    assert sorted(data["awaiting"]) == ["FEAT-001", "INT-001", "SR-001"]
    assert data["verification"] == "unavailable" or isinstance(data["verification"], dict)


@pytest.mark.sr("SR-231")
def test_link_cli_target_forms(repo: Path, write_record,
                               capsys: pytest.CaptureFixture[str]) -> None:
    write_record(repo, INT)
    write_record(repo, SR)
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_mod.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    root = ["--root", str(repo)]
    assert cli.main(["link", "SR-001", "derives_from", "INT-001", *root]) == 0
    assert cli.main(["link", "SR-001", "implemented_by", "src/mod.py", *root]) == 0
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_mod.py", "--example", "EX-1",
                     *root]) == 0
    # symbol and test-node ends (next-plan I3): a verified_by path::name is a test node
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_mod.py::test_x", *root]) == 0
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_mod.py::", *root]) == 2
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_mod.py::test_no", *root]) == 1
    assert cli.main(["link", "SR-001", "implemented_by", "../outside.py", *root]) == 2
    assert cli.main(["link", "SR-001", "implemented_by", "src/missing.py", *root]) == 1
    assert cli.main(["link", "SR-001", "derives_from", "SR-001", *root]) == 1  # kind matrix
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_mod.py", "--example", "EX-9",
                     *root]) == 1
    text = (repo / ".plumb" / "requirements" / "SR-001.md").read_text(encoding="utf-8")
    assert "src/mod.py" in text and "EX-1" in text and "Body." in text
