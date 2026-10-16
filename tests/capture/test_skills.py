"""CAPTURE C7: the plumb-records skill drives the capture helpers; plumb-clarify beside it
(sp2 9.1, SR-046, SR-043)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.hosts.claude_code.install import deny_rules, install, skill_names, uninstall


@pytest.fixture
def installed(repo: Path) -> Path:
    install(repo, launcher="path", commit_hook=False)
    return repo


@pytest.mark.sr("SR-046")
def test_plumb_records_skill_names_capture_helpers(installed: Path) -> None:
    skill = (installed / ".claude" / "skills" / "plumb-records" / "SKILL.md").read_text(
        encoding="utf-8")
    for words in ("plumb capture", "plumb decide", "plumb clarify", "plumb triage",
                  "plumb-clarify"):
        assert words in skill, words
    body = skill.split("---", 2)[2].strip().splitlines()
    assert len(body) <= 30  # about 25 lines of context, not procedure
    for owner_only in ("plumb approve", "triage --approve", "spec approve",
                       "config auto-approve"):
        assert owner_only in skill


@pytest.mark.sr("SR-043")
def test_clarify_skill_states_depths_and_discipline(installed: Path) -> None:
    assert skill_names() == ["plumb-clarify", "plumb-intent", "plumb-records"]
    path = installed / ".claude" / "skills" / "plumb-clarify" / "SKILL.md"
    skill = path.read_text(encoding="utf-8")
    assert skill.startswith("---\nname: plumb-clarify\n")
    assert "creates or changes intent" in skill.split("---", 2)[1]
    for words in ("trivial", "incremental", "escalated", "one at a time",
                  "I assume", "recommended", "--matters", "YAGNI",
                  "owner's terms", "\"go\" or \"ok\"", "labelled", "2-3 approaches",
                  "purpose", "plumb clarify", "spec show", "read-back"):
        assert words in skill, words
    assert "{plumb}" not in skill


@pytest.mark.sr("SR-157")
def test_skills_ask_with_the_question_tool_unless_a_card_fits(installed: Path) -> None:
    skills = {name: " ".join((installed / ".claude" / "skills" / name / "SKILL.md")
                             .read_text(encoding="utf-8").split())
              for name in ("plumb-clarify", "plumb-records")}
    for name, skill in skills.items():
        assert "question tool by default" in skill, name
        assert "context, consequences or a diagram" in skill, name
    assert "confirm, conflict, stale link, a decision that matters" in skills["plumb-clarify"]
    # intent questions still go through clarify
    assert "never ask in your own words about the owner's intent" in skills["plumb-clarify"]


@pytest.mark.sr("SR-046")
def test_skills_uninstalled_and_owner_commands_denied(installed: Path) -> None:
    from plumb.hosts.claude_code.install import Launcher

    rules = " ".join(deny_rules(Launcher("plumb", "plumb", "plumb")))
    for command in ("triage --approve", "spec approve", "config auto-approve", "config show"):
        assert f"Bash(plumb {command}:*)" in rules
    uninstall(installed)
    assert not (installed / ".claude" / "skills" / "plumb-clarify").exists()
    assert not (installed / ".claude" / "skills" / "plumb-records").exists()
