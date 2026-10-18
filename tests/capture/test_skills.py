"""CAPTURE C7: the plumb-records skill drives the capture helpers; plumb-clarify beside it
(sp2 9.1, SR-046, SR-043)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.hosts.claude_code.install import deny_rules, install, skill_names, uninstall

# the four rules every skill and the /plumb command give the agent (plan task 9)
RULES = (
    ("After `capture`, run `plumb clarify --wait --json`. On `ask`, pass each `question`, "
     "`header` and option `label` and `description` to AskUserQuestion verbatim, one call per "
     "question, in order. Never restate a question in prose."),
    ("Never answer, infer or default a question for the owner, never pick the recommended "
     "option for them, and never write or read `judge_questions.json` or any approval."),
    ("If the question tool is unavailable (a subagent or headless run) or the owner dismisses "
     "a question, stop asking, tell the owner in one plain line that the work waits for their "
     "answer, and do not rerun `ask` in a loop."),
    ("Any other question to the owner also goes through the question tool, with options and "
     "their consequences."),
)
NAMES = ("plumb-clarify", "plumb-debug", "plumb-intent", "plumb-records")


@pytest.fixture
def installed(repo: Path) -> Path:
    install(repo, launcher="path", commit_hook=False)
    return repo


def _texts(repo: Path) -> dict[str, str]:
    """Each installed skill and the /plumb command, whitespace collapsed."""
    claude = repo / ".claude"
    paths = {name: claude / "skills" / name / "SKILL.md" for name in NAMES}
    paths["command"] = claude / "commands" / "plumb.md"
    return {name: " ".join(path.read_text(encoding="utf-8").split())
            for name, path in paths.items()}


@pytest.mark.sr("SR-208")
def test_plumb_records_skill_names_capture_helpers(installed: Path) -> None:
    skill = (installed / ".claude" / "skills" / "plumb-records" / "SKILL.md").read_text(
        encoding="utf-8")
    for words in ("plumb capture", "plumb decide", "plumb clarify", "plumb triage",
                  "plumb-clarify"):
        assert words in skill, words
    body = skill.split("---", 2)[2].strip().splitlines()
    assert len(body) <= 40  # about 25 lines of context, not procedure, and the question rules
    for owner_only in ("plumb approve", "triage --approve", "spec approve",
                       "config auto-approve"):
        assert owner_only in skill


@pytest.mark.sr("SR-223")
def test_clarify_skill_states_depths_and_discipline(installed: Path) -> None:
    assert skill_names() == ["plumb-clarify", "plumb-debug", "plumb-intent", "plumb-records"]
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


@pytest.mark.sr("SR-223")
def test_skills_ask_with_the_question_tool(installed: Path) -> None:
    skills = _texts(installed)
    for name in ("plumb-clarify", "plumb-records"):
        assert ("Any other question to the owner also goes through the question tool, with "
                "options and their consequences") in skills[name], name
    assert "Claude Code's question tool (rule 4 below)" in skills["plumb-clarify"]
    # intent questions still go through clarify
    assert "never ask in your own words about the owner's intent" in skills["plumb-clarify"]


@pytest.mark.sr("SR-208")
def test_skills_uninstalled_and_owner_commands_denied(installed: Path) -> None:
    from plumb.hosts.claude_code.install import Launcher

    rules = " ".join(deny_rules(Launcher("plumb", "plumb", "plumb")))
    for command in ("triage --approve", "spec approve", "config auto-approve", "config show"):
        assert f"Bash(plumb {command}:*)" in rules
    uninstall(installed)
    assert not (installed / ".claude" / "skills" / "plumb-clarify").exists()
    assert not (installed / ".claude" / "skills" / "plumb-records").exists()


@pytest.mark.sr("SR-208")
def test_skills_say_the_agent_never_decides_the_owner_approved(installed: Path) -> None:
    """EX-10: the installed skills say the agent may never decide on its own that the owner
    approved, and name no relay."""
    refs = installed / ".claude" / "skills" / "plumb-records" / "references"
    for name, text in _texts(installed).items():
        assert "you never decide on your own that the owner approved" in text, name
        assert "no approval command exists" in text, name
        assert "relay" not in text.lower(), name
        assert "/plumb approve" not in text and "approve <IDs>" not in text, name
    for path in refs.glob("*.md"):
        assert "relay" not in path.read_text(encoding="utf-8").lower(), path.name


@pytest.mark.sr("SR-267")
def test_skills_ask_waiting_questions_through_the_tool_never_in_prose(installed: Path) -> None:
    """EX-8: with questions waiting, the agent asks them through the question tool, one at a
    time, verbatim, and never restates them as a list to answer in prose."""
    for name, text in _texts(installed).items():
        assert RULES[0] in text, name
    clarify = _texts(installed)["plumb-clarify"]
    assert "- ask (plumb's judge has questions about what the owner meant)" in clarify


@pytest.mark.sr("SR-248")
def test_the_four_question_rules_are_in_each_skill(installed: Path) -> None:
    """EX-3 (the agent side): the judge model's questions reach the owner through the
    question tool; each skill and the /plumb command carry the four rules, in order."""
    for name, text in _texts(installed).items():
        at = [text.find(rule) for rule in RULES]
        assert -1 not in at and at == sorted(at), name
        for gone in ("the read-back's ok confirms", "the owner confirms on the cards",
                     "owner's ok confirms",
                     # rule 1 runs on every message: no text may say it never asks there
                     "only gives the message digest", "answers ready at once",
                     "Only after the owner types"):
            assert gone not in text, (name, gone)
