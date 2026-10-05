"""H4: the session-start brief and the first status snapshot (spec 6.1)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fakes import FakeVerify

from plumb.api import open_core
from plumb.contracts import FullPending, NodeEvidence, Target
from plumb.hosts.claude_code import session_start

pytestmark = pytest.mark.sr("SR-009")


def _run(repo: Path, hook_input, **kwargs) -> str:
    out = io.StringIO()
    code = session_start.main(stdin=io.StringIO(hook_input("SessionStart", source="startup")),
                              stdout=out, root=repo, **kwargs)
    assert code == 0
    return out.getvalue()


def _many_records(repo: Path, write_record, count: int = 60) -> None:
    for i in range(1, count + 1):
        write_record(repo, f"---\nid: INT-{i:03d}\ntitle: Intent number {i}\nquote: q{i}\n---\n")
    for i in range(1, 6):
        write_record(repo, f"---\nid: NC-{i:04d}\ntitle: Open problem {i}\nstatus: open\n---\n")


def test_brief_about_30_lines_with_cap(repo: Path, write_record, hook_input) -> None:
    _many_records(repo, write_record)
    out = _run(repo, hook_input, verify=FakeVerify())
    lines = out.splitlines()
    assert lines[0].startswith("plumb brief")
    assert 25 <= len(lines) <= 40
    assert any("more (plumb brief --all)" in line for line in lines)


def test_brief_never_passes_hard_cap(repo: Path, write_record, hook_input) -> None:
    _many_records(repo, write_record)
    config = repo / ".plumb" / "config.yaml"
    config.write_text("hooks:\n  brief_lines: 200\n", encoding="utf-8")
    lines = _run(repo, hook_input, verify=None).splitlines()
    assert len(lines) <= 40
    assert any(line.startswith("tests: verification unavailable") for line in lines)


def test_brief_lists_awaiting_confirmation_and_drift(repo: Path, write_record,
                                                      hook_input) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: Links pin both ends\nstatement: s\n---\n")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/a.py"))
    (repo / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    verify = FakeVerify(tests={"SR-001": ("tests/test_a.py::test_x",)},
                        evidence_map={"tests/test_a.py::test_x": NodeEvidence(
                            "tests/test_a.py::test_x", "fresh-fail")},
                        pending=FullPending(True, ("uv.lock",)))
    out = _run(repo, hook_input, verify=verify)
    assert "awaiting your confirmation: 1 proposed (SR-001)" in out
    assert "drift: stale 1" in out
    assert ("tests: 1 failing (tests/test_a.py::test_x) | full verification pending (uv.lock)"
            in out)


def test_writes_status_snapshot(repo: Path, write_record, hook_input) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    _run(repo, hook_input, verify=FakeVerify(pending=FullPending(True, ("pyproject.toml",))))
    data = json.loads((repo / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert data["v"] == 1
    assert data["requirements_total"] == 1 and data["proposed"] == 1
    assert data["full_pending"] is True


def test_context_not_procedure(repo: Path, write_record, hook_input) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    out = _run(repo, hook_input, verify=FakeVerify())
    assert not json.dumps(out).startswith("{\"decision")
    assert "you must" not in out.lower() and "step 1" not in out.lower()
