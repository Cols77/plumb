"""H3: the status snapshot and the status line (spec 6.6, 12.5)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fakes import FakeVerify

from plumb.api import open_core
from plumb.contracts import FullPending, NodeEvidence, StatusSnapshot
from plumb.hosts.claude_code import snapshot, statusline

pytestmark = pytest.mark.sr("SR-013")

SR1 = "---\nid: SR-001\ntitle: One\nstatement: s1\n---\n"
SR2 = "---\nid: SR-002\ntitle: Two\nstatement: s2\n---\n"


def _snap(**fields) -> StatusSnapshot:
    base = dict(at="2026-10-06T04:00:00Z", requirements_total=14, requirements_confirmed=12,
                proposed=2, stale_links=1, dangling_links=0, tests="ok")
    base.update(fields)
    return StatusSnapshot(**base)


def _line(repo: Path, snap: StatusSnapshot | None) -> str:
    if snap is not None:
        snapshot.write_snapshot(repo, snap)
    out = io.StringIO()
    assert statusline.main(root=repo, stdin=io.StringIO(""), stdout=out) == 0
    return out.getvalue().strip()


def test_renders_line_from_snapshot(repo: Path) -> None:
    """The status line is the status card (sp5 4.1, SR-061)."""
    assert _line(repo, _snap()) == "plumb ● awaits you · SR 12/14 ok · 2 awaits you · 1 stale"
    assert _line(repo, _snap(tests="regression", regressions=("t::a",), ask=1)) == (
        "plumb ✗ regression · SR 12/14 ok · 2 awaits you · 1 stale · 1 question")
    assert "✗ failing" in _line(repo, _snap(tests="failing", failing=("a", "b")))
    assert "2 failing" in _line(repo, _snap(tests="failing", failing=("a", "b")))


def test_full_pending_shown_only_when_pending(repo: Path) -> None:
    assert "full pending" not in _line(repo, _snap(full_pending=False))
    assert _line(repo, _snap(full_pending=True, full_pending_reasons=("uv.lock",))) == (
        "plumb ● awaits you · SR 12/14 ok · 2 awaits you · 1 stale · full pending")


def test_missing_snapshot(repo: Path) -> None:
    assert _line(repo, None) == "plumb | no status yet"
    (repo / ".plumb" / "session").mkdir(parents=True, exist_ok=True)
    (repo / ".plumb" / "session" / "status.json").write_text("{broken", encoding="utf-8")
    assert _line(repo, None) == "plumb | no status yet"


def test_root_from_status_line_input(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    snapshot.write_snapshot(repo, _snap())
    out = io.StringIO()
    stdin = io.StringIO(json.dumps({"workspace": {"project_dir": str(repo)}}))
    statusline.main(stdin=stdin, stdout=out)
    assert out.getvalue().startswith("plumb ● awaits you · SR 12/14 ok")


def test_snapshot_written_with_version(repo: Path) -> None:
    snapshot.write_snapshot(repo, _snap(failing=("x",)))
    data = json.loads((repo / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert data["v"] == 1 and data["failing"] == ["x"] and data["requirements_total"] == 14


def test_build_snapshot_from_core_and_verify(repo: Path, write_record) -> None:
    write_record(repo, SR1)
    write_record(repo, SR2)
    core = open_core(repo)
    verify = FakeVerify(pending=FullPending(True, ("uv.lock",)))
    snap = snapshot.build_snapshot(
        core, verify=verify,
        evidence={"t::a": NodeEvidence("t::a", "fresh-pass"),
                  "t::b": NodeEvidence("t::b", "fresh-fail", regression=True)},
        ask=1)
    assert snap.requirements_total == 2 and snap.requirements_confirmed == 0
    assert snap.proposed == 2
    assert snap.tests == "regression" and snap.regressions == ("t::b",)
    assert snap.full_pending and snap.full_pending_reasons == ("uv.lock",)
    assert snap.ask == 1


def test_snapshot_tests_states() -> None:
    def tests_of(*states: tuple[str, bool]) -> str:
        evidence = {f"n{i}": NodeEvidence(f"n{i}", s, regression=r)
                    for i, (s, r) in enumerate(states)}
        return snapshot.tests_state(evidence)[0]

    assert tests_of(("fresh-pass", False), ("flaky-pass", False)) == "ok"
    assert tests_of(("fresh-pass", False), ("fresh-fail", False)) == "failing"
    assert tests_of(("fresh-pass", False), ("none", False)) == "not-run"
    assert tests_of(("stale", False)) == "not-run"
    assert tests_of(("fresh-fail", True), ("fresh-fail", False)) == "regression"
    assert snapshot.tests_state(None)[0] == "unknown"
    assert snapshot.tests_state({})[0] == "unknown"
