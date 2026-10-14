"""SR-101 EX-9 and INT-028/INT-029: there is no agent-run prose relay command, the prompt hook
no longer tells the agent to confirm on its own reading, and no word rule that decides
whether the owner approved is left in `approvals`."""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path

import pytest
from capture.capture_helpers import log_prompt

from plumb import approvals
from plumb.api import open_core
from plumb.cli import main
from plumb.hosts.claude_code import prompt

pytestmark = pytest.mark.sr("SR-101")

SR1 = """---
id: SR-001
title: Add multiply
feature: FEAT-001
statement: Multiply two numbers.
examples:
- id: EX-1
  given: 2 and 3
  when: multiply runs
  then: 6
---
"""

WORD_RULES = ("affirmation_in", "affirmation_context_problem", "change_clauses", "owner_scope",
              "objection_clauses", "quote_covers_clauses", "_NEGATION", "_OBJECTION",
              "_CLAUSE_PUNCT", "_CLAUSE_WORD", "_clauses", "_KIND_RE", "_NARROW", "_POSITIVE",
              "_check_scope", "_asks_change", "_plain_named", "awaiting_line")


@pytest.fixture
def project(repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    write_record(repo, SR1)
    return repo


def approvals_of(repo: Path) -> list:
    return [e for e in open_core(repo).events() if e.kind == "approval"]


def test_ex9_there_is_no_relay_command_so_a_prompt_reading_no_confirms_nothing(
        project: Path, capsys) -> None:
    digest = log_prompt(project, "no, do not approve SR-001")
    assert main(["relay", "SR-001", "--prompt", digest, "--quote", "approve SR-001",
                 "--root", str(project)]) == 3
    assert "no longer exists" in capsys.readouterr().err
    assert not hasattr(approvals, "relay")
    assert approvals_of(project) == []


def test_the_typed_exact_command_still_parses_for_the_hook(project: Path) -> None:
    from plumb.understand import typed

    parsed = typed.parse("/plumb approve SR-001")
    assert parsed is not None and parsed.command == "approve"
    assert list(parsed.ids) == ["SR-001"]


def test_the_prompt_hook_no_longer_tells_the_agent_to_relay(
        project: Path, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])
    index = open_core(project).index()
    stated = project / ".plumb" / "session" / "stated.json"
    stated.parent.mkdir(parents=True, exist_ok=True)
    stated.write_text(json.dumps({"at": "2026-10-06T00:00:00Z", "records": [
        {"id": "SR-001", "hash": index["SR-001"].hash, "shown": True}]}), "utf-8")
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt="ok", session_id="s1")
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=project) == 0
    assert "plumb relay" not in out.getvalue()
    assert "awaiting confirmation" not in out.getvalue()
    assert not hasattr(prompt, "awaiting_line")


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("approvals"):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id == "approvals":
            names.add(node.attr)
    return names


def test_no_word_rule_of_approvals_is_left_or_imported_anywhere() -> None:
    import plumb

    assert [name for name in WORD_RULES if hasattr(approvals, name)] == []
    root = Path(plumb.__file__).parent
    offenders = {str(path.relative_to(root)): sorted(_imports(path) & set(WORD_RULES))
                 for path in root.rglob("*.py")}
    assert {k: v for k, v in offenders.items() if v} == {}
