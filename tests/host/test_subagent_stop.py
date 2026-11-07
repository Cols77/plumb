"""SR-166 EX-1: a workflow agent is held once on a stale link its work made, then let go
with a card."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from core.stale_asked import asked
from plumb import stale
from plumb.api import open_core
from plumb.contracts import Target
from plumb.hosts.claude_code import subagent_stop

pytestmark = pytest.mark.sr("SR-198")

SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return b + a\n", "utf-8")
    roots = repo / ".plumb" / "session" / "agent_roots.json"
    roots.parent.mkdir(parents=True, exist_ok=True)
    roots.write_text(json.dumps({"a1": {str(repo): ["SR-001#0"]}}), "utf-8")
    return repo


def _stop(repo: Path, hook_input, *, active: bool = False, agent: str = "a1") -> dict:
    out = io.StringIO()
    payload = hook_input("SubagentStop", agent_id=agent, stop_hook_active=active,
                         session_id="s1")
    assert subagent_stop.main(stdin=io.StringIO(payload), stdout=out, root=repo) == 0
    return json.loads(out.getvalue()) if out.getvalue().strip() else {}


def test_ex1_first_stop_blocks_naming_the_link(project: Path, hook_input) -> None:
    out = _stop(project, hook_input)
    assert out["decision"] == "block"
    assert "SR-001's link to src/calc.py is stale and unresolved (SR-001#0)" in out["reason"]
    assert "Held 1 of 1" in out["reason"]


def test_ex1_second_stop_lets_go_with_a_question(project: Path, hook_input) -> None:
    out = _stop(project, hook_input, active=True)
    assert out.get("decision") != "block"
    (card,) = asked(project, "s1")
    assert card["link"] == "SR-001#0"
    assert _stop(project, hook_input).get("decision") != "block"  # the card now holds it


def test_other_agents_roots_are_not_held(project: Path, hook_input, tmp_path: Path) -> None:
    (project / ".plumb" / "session" / "agent_roots.json").write_text(
        json.dumps({"a1": {str(tmp_path): ["SR-001#0"]}}), "utf-8")
    assert _stop(project, hook_input, agent="a1") == {}


def test_an_agent_that_edited_nothing_is_not_held(project: Path, hook_input) -> None:
    """a1 recorded the repository; a2 recorded nothing, so it inherits none of a1's work."""
    assert _stop(project, hook_input, agent="a1")["decision"] == "block"
    assert _stop(project, hook_input, agent="a2") == {}
    assert asked(project, "s1") == []
    assert _stop(project, hook_input, active=True, agent="a2") == {}
    assert asked(project, "s1") == []


def test_a_recorded_link_fixed_before_the_stop_is_not_held(project: Path, hook_input) -> None:
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    assert _stop(project, hook_input) == {}


def test_only_the_links_edit_check_recorded_are_checked(project: Path, hook_input) -> None:
    """Stale links the agent's notices did not name (older debt) are not its to resolve."""
    (project / ".plumb" / "session" / "agent_roots.json").write_text(
        json.dumps({"a1": {str(project): []}}), "utf-8")
    assert _stop(project, hook_input) == {}


def test_a_stale_link_of_the_same_record_not_recorded_is_not_held(project: Path,
                                                                  hook_input) -> None:
    """Only the recorded link ids are hashed, not every link of their records."""
    (project / "src" / "other.py").write_text("X = 1\n", "utf-8")
    open_core(project).add_link("SR-001", "implemented_by", Target(path="src/other.py"))
    (project / "src" / "other.py").write_text("X = 2\n", "utf-8")
    out = _stop(project, hook_input)
    assert "(SR-001#0)" in out["reason"] and "SR-001#1" not in out["reason"]
