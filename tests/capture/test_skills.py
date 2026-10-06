"""CAPTURE C7: the plumb skill drives the capture helpers; plumb-clarify beside it
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
def test_plumb_skill_names_capture_helpers(installed: Path) -> None:
    skill = (installed / ".claude" / "skills" / "plumb" / "SKILL.md").read_text(
        encoding="utf-8")
    for words in ("plumb capture", "plumb decide", "plumb clarify", "plumb triage",
                  "plumb relay", "--group low-risk", "--set INT-###", "plumb-clarify"):
        assert words in skill, words
    body = skill.split("---", 2)[2].strip().splitlines()
    assert len(body) <= 30  # about 25 lines of context, not procedure
    for owner_only in ("plumb approve", "triage --approve", "spec approve",
                       "config auto-approve"):
        assert owner_only in skill


@pytest.mark.sr("SR-043")
def test_clarify_skill_states_depths_and_discipline(installed: Path) -> None:
    assert skill_names() == ["plumb", "plumb-clarify"]
    path = installed / ".claude" / "skills" / "plumb-clarify" / "SKILL.md"
    skill = path.read_text(encoding="utf-8")
    assert skill.startswith("---\nname: plumb-clarify\n")
    assert "creates or changes intent" in skill.split("---", 2)[1]
    for words in ("trivial", "incremental", "escalated", "ONE per message",
                  "multiple choice", "recommended", "--matters", "YAGNI",
                  "owner's terms", "\"go\" or \"ok\"", "labelled", "2-3 approaches",
                  "purpose", "plumb clarify", "spec show", "intent card"):
        assert words in skill, words
    assert "{plumb}" not in skill


@pytest.mark.sr("SR-046")
def test_skills_uninstalled_and_owner_commands_denied(installed: Path) -> None:
    from plumb.hosts.claude_code.install import Launcher

    rules = " ".join(deny_rules(Launcher("plumb", "plumb", "plumb")))
    for command in ("triage --approve", "spec approve", "config auto-approve", "config show"):
        assert f"Bash(plumb {command}:*)" in rules
    uninstall(installed)
    assert not (installed / ".claude" / "skills" / "plumb-clarify").exists()
    assert not (installed / ".claude" / "skills" / "plumb").exists()
