"""SP8 lane STALE, HA2 (SR-111): the synchronous edit check names the links an edit made
stale, in one line each, as additional context for the agent."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest

from iaso import stale
from iaso.api import open_core
from iaso.contracts import Target
from iaso.hosts.claude_code import edit_check, install

pytestmark = pytest.mark.sr("SR-198")


@pytest.fixture(autouse=True)
def _stale_notices_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests are about the stale notices; the requirement lines an edit adds (SR-374
    EX-3) are tested in tests/present/test_insights.py."""
    monkeypatch.setattr(edit_check, "_serves", lambda *args: [])

SR5 = """---
id: SR-005
title: Relay checks the quote
statement: relay checks the quote.
examples:
- id: EX-1
  given: a quote
  when: relay runs
  then: it checks it
---
"""
CODE = "def f(a, b):\n    return a + b\n\n\ndef g(x):\n    return x\n"
NOTICE = ("iaso: SR-005's link to src/x.py is stale: the file changed; rerun its tests and "
          "repin, reword SR-005, or ask the owner with the question tool")


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR5)
    (repo / "src").mkdir()
    (repo / "src" / "x.py").write_text(CODE, encoding="utf-8")
    open_core(repo).add_link("SR-005", "implemented_by", Target(path="src/x.py", symbol="f"))
    stale.ensure_linkmap(open_core(repo))
    return repo


def _run(repo: Path, hook_input, rel: str = "src/x.py", session: str = "test-session") -> str:
    out = io.StringIO()
    payload = hook_input("PostToolUse", tool_name="Edit", session_id=session,
                         tool_input={"file_path": str(repo / rel)})
    assert edit_check.main(stdin=io.StringIO(payload), stdout=out, root=repo) == 0
    return out.getvalue()


def _edit(repo: Path) -> None:
    (repo / "src" / "x.py").write_text(CODE.replace("a + b", "a - b"), encoding="utf-8")


def test_ex1_notice_in_one_line(project: Path, hook_input) -> None:
    _edit(project)
    out = json.loads(_run(project, hook_input))
    assert out == {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                          "additionalContext": NOTICE}}


def test_silent_when_nothing_stale(project: Path, hook_input) -> None:
    assert _run(project, hook_input) == ""
    (project / "src" / "x.py").write_text(CODE.replace("return x", "return x  "),
                                          encoding="utf-8")
    assert _run(project, hook_input) == ""
    assert _run(project, hook_input, rel="README.md") == ""


def test_silent_without_a_link_map(project: Path, hook_input) -> None:
    stale.cache_path(project).unlink()
    _edit(project)
    assert _run(project, hook_input) == ""


def test_said_once_per_state(project: Path, hook_input) -> None:
    _edit(project)
    assert _run(project, hook_input) != ""
    assert _run(project, hook_input) == ""           # the same state is not repeated
    (project / "src" / "x.py").write_text(CODE.replace("a + b", "a * b"), encoding="utf-8")
    assert _run(project, hook_input) != ""           # a further change is


def test_at_most_five_then_more(project: Path, hook_input, write_record) -> None:
    for n in range(10, 17):
        write_record(project, SR5.replace("SR-005", f"SR-0{n}"))
        open_core(project).add_link(f"SR-0{n}", "implemented_by",
                                   Target(path="src/x.py", symbol="f"))
    stale.ensure_linkmap(open_core(project))
    _edit(project)
    text = json.loads(_run(project, hook_input))["hookSpecificOutput"]["additionalContext"]
    lines = text.splitlines()
    assert len(lines) == 6 and lines[-1] == "iaso: +3 more"


def test_link_added_after_the_map_is_still_seen(project: Path, hook_input, write_record) -> None:
    (project / "src" / "y.py").write_text("v = 1\n", encoding="utf-8")
    time.sleep(0.05)
    open_core(project).add_link("SR-005", "implemented_by", Target(path="src/y.py"))
    (project / "src" / "y.py").write_text("v = 2\n", encoding="utf-8")
    out = json.loads(_run(project, hook_input, rel="src/y.py"))
    assert "link to src/y.py is stale" in out["hookSpecificOutput"]["additionalContext"]


def test_direct_record_edit_names_derived_records(repo: Path, hook_input, write_record) -> None:
    write_record(repo, "---\nid: INT-016\ntitle: Add multiply\nquote: add multiply\n"
                       "readback: Add multiply beside add\nwill:\n- a product\n---\n")
    write_record(repo, SR5.replace("SR-005", "SR-032"))
    open_core(repo).add_link("SR-032", "derives_from", Target(record="INT-016"))
    stale.ensure_linkmap(open_core(repo))
    time.sleep(0.05)
    write_record(repo, "---\nid: INT-016\ntitle: Add multiply\nquote: add multiply\n"
                       "readback: Add multiply and divide\nwill:\n- a product\n---\n")
    out = json.loads(_run(repo, hook_input, rel=".iaso/intents/INT-016.md"))
    assert out["hookSpecificOutput"]["additionalContext"] == (
        "SR-032 derives from INT-016, which was reworded: check that it still agrees")


def test_budget_300_min_of_5(project: Path, hook_input) -> None:
    runs = []
    for _ in range(5):
        _edit(project)
        stale_told = project / ".iaso" / "session" / "test-session" / "stale_told.json"
        stale_told.unlink(missing_ok=True)
        start = time.monotonic()
        _run(project, hook_input)
        runs.append((time.monotonic() - start) * 1000)
    assert min(runs) < 300 * 0.9, runs


def test_install_adds_sync_entry_after_async_one(repo: Path) -> None:
    uv = install.Launcher("uv", "uv run --no-sync iaso", "uv run --no-sync iaso")
    install.install(repo, launcher=uv, hooks=("post-edit", "edit-check", "stop"))
    settings = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    groups = settings["hooks"]["PostToolUse"]
    commands = [g["hooks"][0]["command"] for g in groups]
    assert commands == ["uv run --no-sync iaso hook post-edit",
                        "uv run --no-sync iaso hook edit-check"]
    assert groups[0]["hooks"][0]["async"] is True
    assert "async" not in groups[1]["hooks"][0]
    assert groups[1]["matcher"] == "Edit|Write|MultiEdit|NotebookEdit"
    assert "edit-check" in install.available_hooks()


def test_own_records_inside_budget(hook_input) -> None:
    """On iaso's own records and a warm link map the check stays inside the budget."""
    root = Path(__file__).resolve().parents[2]
    if not (root / ".iaso" / "requirements").is_dir():
        pytest.skip("no records")
    from iaso.hosts.claude_code import hookio  # noqa: F401

    core = open_core(root)
    stale.ensure_linkmap(core)
    runs = []
    for _ in range(5):
        out = io.StringIO()
        payload = hook_input("PostToolUse", tool_name="Edit", session_id="perf-own",
                             tool_input={"file_path": str(root / "src/iaso/links.py")})
        start = time.monotonic()
        edit_check.main(stdin=io.StringIO(payload), stdout=out, root=root)
        runs.append((time.monotonic() - start) * 1000)
    assert min(runs) < 300 * 0.9, runs


def test_sr166_edit_outside_the_root_uses_the_files_own_root(project: Path, hook_input,
                                                             tmp_path: Path, write_record) -> None:
    other = tmp_path / "wt"
    (other / ".iaso").mkdir(parents=True)
    (other / "src").mkdir()
    (other / "src" / "x.py").write_text(CODE, encoding="utf-8")
    write_record(other, SR5)
    open_core(other).add_link("SR-005", "implemented_by", Target(path="src/x.py", symbol="f"))
    stale.ensure_linkmap(open_core(other))
    (other / "src" / "x.py").write_text(CODE.replace("a + b", "a - b"), encoding="utf-8")
    out = io.StringIO()
    payload = hook_input("PostToolUse", tool_name="Edit", agent_id="a1",
                         tool_input={"file_path": str(other / "src" / "x.py")})
    assert edit_check.main(stdin=io.StringIO(payload), stdout=out, root=project) == 0
    assert NOTICE in out.getvalue()
    roots = json.loads((project / ".iaso" / "session" / "agent_roots.json").read_text("utf-8"))
    assert roots == {"a1": {str(other.resolve()): ["SR-005#0"]}}  # what subagent-stop rechecks


@pytest.mark.sr("SR-198")
def test_sr166_a_worktree_no_session_prompted_in_gets_its_map_built(project: Path, hook_input,
                                                                    tmp_path: Path,
                                                                    write_record) -> None:
    other = tmp_path / "wt"
    (other / ".iaso").mkdir(parents=True)
    (other / "src").mkdir()
    (other / "src" / "x.py").write_text(CODE, encoding="utf-8")
    write_record(other, SR5)
    open_core(other).add_link("SR-005", "implemented_by", Target(path="src/x.py", symbol="f"))
    assert stale.load_linkmap(other) is None  # no prompt hook ever ran there
    (other / "src" / "x.py").write_text(CODE.replace("a + b", "a - b"), encoding="utf-8")
    out = io.StringIO()
    payload = hook_input("PostToolUse", tool_name="Edit", agent_id="a1",
                         tool_input={"file_path": str(other / "src" / "x.py")})
    assert edit_check.main(stdin=io.StringIO(payload), stdout=out, root=project) == 0
    assert NOTICE in out.getvalue()
    assert stale.load_linkmap(other) is not None


@pytest.mark.sr("SR-198")
def test_sr166_an_edit_that_makes_nothing_stale_records_no_link(project: Path,
                                                                hook_input) -> None:
    (project / "src" / "x.py").write_text(CODE.replace("return x", "return -x"), "utf-8")
    assert _run(project, hook_input) == ""
    roots = json.loads((project / ".iaso" / "session" / "agent_roots.json").read_text("utf-8"))
    assert roots == {"main": {str(project): []}}
