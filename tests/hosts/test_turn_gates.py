"""Two turn guarantees, on every host entry point (decision 5, R3, R5):

- the intent-change card reaches the owner only when the agent, the cascade's LLM tier,
  concluded there is a change: a heuristic-only flag on an unrelated "add a X" request, or
  a flag the agent did not act on, never shows the owner an "Intent change" card;
- a turn that changed code always selects covering tests or falls back to R5's bounded
  sample with ``full verification pending`` ("coverage unknown"), and the regression check
  (trigger 3) runs, even on a repository whose test map is not built and cannot be built
  within the hook's budget (a fresh clone).

Entry points: the Claude Code hooks (``plumb hook prompt|stop``), the CLI-only fallback
(``plumb turn start|end``) and the Codex, Pi and Hermes adapters (``plumb hook <event>
--host X``), all through the same ``VerifyAPI`` and stop handler.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from hosts_helpers import git

from plumb.api import open_core
from plumb.cli import main

pytestmark = pytest.mark.sr("SR-053")

ENTRY_POINTS = ("claude-code", "cli", "codex", "pi", "hermes")

INT1 = """---
id: INT-001
title: Add sub(a, b) returning a - b
quote: add a sub function returning a minus b
readback: Add sub(a, b) returning a - b
---
"""
SR2 = """---
id: SR-002
title: sub returns a minus b
statement: sub(a, b) returns a - b
examples:
- id: EX-1
  given: 5 and 3
  when: sub is called
  then: it returns 2
links:
- kind: derives_from
  to: INT-001
- kind: implemented_by
  to: src/calc.py
---
"""


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    from plumb.approvals import approve

    write_record(repo, INT1)
    write_record(repo, SR2)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def sub(a, b):\n    return a - b\n", "utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text(
        "from calc import sub\n\n\ndef test_sub():\n    assert sub(5, 3) == 2\n", "utf-8")
    approve(open_core(repo), ["INT-001", "SR-002"])  # the owner's terminal (test)
    from plumb.links import repin

    for state in open_core(repo).link_states(["SR-002"]):
        if state.state == "stale":
            repin(open_core(repo), state.link.id)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "setup")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("PLUMB_NO_BACKGROUND_MAP", "1")
    return repo


def _call(monkeypatch, capsys, argv: list[str], stdin: str) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    assert main(argv) == 0
    return capsys.readouterr().out


def prompt(root: Path, entry: str, text: str, monkeypatch, capsys) -> str:
    if entry == "cli":
        return _call(monkeypatch, capsys, ["turn", "start", "--session", "s1", "--root",
                                           str(root)], text)
    if entry == "claude-code":
        return _call(monkeypatch, capsys, ["hook", "prompt", "--root", str(root)],
                     json.dumps({"session_id": "s1", "cwd": str(root), "prompt": text}))
    return _call(monkeypatch, capsys, ["hook", "prompt", "--host", entry, "--format", "json",
                                       "--root", str(root)],
                 json.dumps({"session_id": "s1", "text": text}))


def stop(root: Path, entry: str, monkeypatch, capsys, *, active: bool = False) -> str:
    if entry == "cli":
        return _call(monkeypatch, capsys, ["turn", "end", "--session", "s1", "--root",
                                           str(root)], "")
    if entry == "claude-code":
        return _call(monkeypatch, capsys, ["hook", "stop", "--root", str(root)],
                     json.dumps({"session_id": "s1", "cwd": str(root),
                                 "stop_hook_active": active}))
    return _call(monkeypatch, capsys, ["hook", "stop", "--host", entry, "--format", "json",
                                       "--root", str(root)],
                 json.dumps({"session_id": "s1", "stop_active": active}))


def edit(root: Path, rel: str, text: str) -> None:
    (root / rel).write_text(text, "utf-8")


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_heuristic_flag_alone_never_shows_an_intent_change_card(
        project: Path, entry: str, monkeypatch, capsys) -> None:
    # an unrelated new feature that only shares "add a ... function returning" with INT-001
    agent = prompt(project, entry, "add a negate function returning minus a", monkeypatch,
                   capsys)
    assert "this may change" not in agent
    edit(project, "src/calc.py", "def sub(a, b):\n    return a - b\n\n\n"
                                 "def neg(a):\n    return -a\n")
    outputs = [stop(project, entry, monkeypatch, capsys),
               stop(project, entry, monkeypatch, capsys, active=True)]
    assert not any("Intent change" in out for out in outputs)
    # a heuristic flag the agent did not act on (it changed only code): still no card
    agent = prompt(project, entry, "sub should return a float instead", monkeypatch, capsys)
    assert "this may change SR-002 (confirmed)" in agent  # the agent's instruction
    edit(project, "src/calc.py", "def sub(a, b):\n    return float(a - b)\n")
    outputs = [stop(project, entry, monkeypatch, capsys),
               stop(project, entry, monkeypatch, capsys, active=True)]
    assert not any("Intent change" in out for out in outputs)


@pytest.fixture
def no_map(project: Path, monkeypatch) -> list[Path]:
    """No test map, and one that cannot be built within a hook (as on a fresh clone of a
    real repository): every inline parse is over the hook's limit."""
    import plumb.verify.api as verify_api

    started: list[Path] = []
    monkeypatch.setattr(verify_api, "HOOK_PARSE_MAX", 0)
    monkeypatch.setattr(verify_api, "spawn_map_build", lambda root: started.append(root))
    for path in (project / ".plumb" / "cache" / "test_map.json",
                 project / ".plumb" / "test_map.txt"):
        path.unlink(missing_ok=True)
    return started


def record_regression(root: Path, node: str) -> None:
    """A run of this turn that failed ``node`` after an earlier recorded pass (R3)."""
    core = open_core(root)
    for run_id, outcome in (("r1", "passed"), ("r2", "failed")):
        core.log_append("evidence", "test-run", {
            "run_id": run_id, "full": False, "exit_status": 0 if outcome == "passed" else 1,
            "env": {"env_key": "k"},
            "nodes": [{"id": node, "outcome": outcome, "closure": "c",
                       "test_hash": "sha256:t", "duration_s": 0.1}]})


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_without_a_test_map_a_turn_samples_sets_pending_and_checks_regressions(
        project: Path, no_map: list[Path], entry: str, monkeypatch, capsys) -> None:
    prompt(project, entry, "make sub handle big numbers", monkeypatch, capsys)
    edit(project, "src/calc.py", "def sub(a, b):\n    return int(a) - int(b)\n")
    record_regression(project, "tests/test_calc.py::test_sub")
    first = stop(project, entry, monkeypatch, capsys)
    # the bounded sample asks the agent for the turn's covering tests
    assert "plumb tests run --paths src/calc.py" in first
    # trigger 3 ran without the map: the regression of this turn's run is asked
    assert "regression: tests/test_calc.py::test_sub" in first
    second = stop(project, entry, monkeypatch, capsys, active=True)
    assert "full verification pending (coverage unknown" in second
    assert "regressions not checked" not in first + second
    assert "check skipped" not in first + second
    assert no_map, "the map build was not started outside the hook"
    assert not (project / ".plumb" / "cache" / "test_map.json").exists()
