"""CAPTURE C7: the plumb-records skill drives the capture helpers; plumb-clarify beside it
(sp2 9.1, SR-046, SR-043)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.hosts.claude_code.install import deny_rules, install, skill_names, uninstall

# the question rules the agent follows; written once, in plumb-records (SR-379)
RULES = (
    ("After `capture`, run `plumb clarify --wait --json`. On `ask`, pass each `question`, "
     "`header` and option `label` and `description` to the question tool, every question at "
     "once, as soon as it is raised; never restate one in prose. Put each in the owner's terms "
     "with `plumb question reword`, merging those that hinge on one principle; never drop, "
     "answer or default one."),
    ("Never answer, infer or default a question for the owner, never pick the recommended "
     "option for them, and never write or read `judge_questions.json` or any approval."),
    ("If the question tool is unavailable (a subagent or headless run) or the owner dismisses "
     "a question, stop asking, tell the owner in one plain line that the work waits for their "
     "answer, and do not rerun `ask` in a loop."),
    ("Any other question to the owner also goes through the question tool, with options and "
     "their consequences."),
)
POINTER = "Questions to the owner: follow plumb-records"
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
    for words in ("plumb capture", "plumb decide", "plumb clarify",
                  "plumb-clarify"):
        assert words in skill, words
    body = skill.split("---", 2)[2].strip().splitlines()
    # context, not procedure, and the question rules written once (SR-379)
    assert len(body) <= 55
    for owner_only in ("plumb approve",
                       "config auto-approve"):
        assert owner_only in skill


@pytest.mark.sr("SR-223")
def test_clarify_skill_states_depths_and_discipline(installed: Path) -> None:
    assert skill_names() == ["plumb-clarify", "plumb-debug", "plumb-intent", "plumb-records",
                             "plumb-study-video"]
    path = installed / ".claude" / "skills" / "plumb-clarify" / "SKILL.md"
    skill = path.read_text(encoding="utf-8")
    assert skill.startswith("---\nname: plumb-clarify\n")
    assert "creates or changes intent" in skill.split("---", 2)[1]
    for words in ("trivial", "incremental", "escalated", "all at once",
                  "I assume", "recommended", "--matters", "YAGNI",
                  "owner's terms", "\"go\" or \"ok\"", "labelled", "2-3 approaches",
                  "purpose", "plumb clarify", "spec show", "read-back"):
        assert words in skill, words
    assert "{plumb}" not in skill


@pytest.mark.sr("SR-223")
def test_skills_ask_with_the_question_tool(installed: Path) -> None:
    skills = _texts(installed)
    assert ("Any other question to the owner also goes through the question tool, with "
            "options and their consequences") in skills["plumb-records"]
    # intent questions still go through clarify
    assert "never ask in your own words about the owner's intent" in skills["plumb-clarify"]


@pytest.mark.sr("SR-208")
def test_skills_uninstalled_and_owner_commands_denied(installed: Path) -> None:
    from plumb.hosts.claude_code.install import Launcher

    rules = " ".join(deny_rules(Launcher("plumb", "plumb", "plumb")))
    for command in ("config auto-approve", "config show"):
        assert f"Bash(plumb {command}:*)" in rules
    uninstall(installed)
    assert not (installed / ".claude" / "skills" / "plumb-clarify").exists()
    assert not (installed / ".claude" / "skills" / "plumb-records").exists()


@pytest.mark.sr("SR-208")
def test_skills_say_the_agent_never_decides_the_owner_approved(installed: Path) -> None:
    """EX-10: the installed rulebook says the agent may never decide on its own that the owner
    approved, and no skill or reference names a relay."""
    refs = installed / ".claude" / "skills" / "plumb-records" / "references"
    texts = _texts(installed)
    assert "you never decide on your own that the owner approved" in texts["plumb-records"]
    assert "no approval command exists" in texts["plumb-records"]
    for name, text in texts.items():
        assert "relay" not in text.lower(), name
        assert "/plumb approve" not in text and "approve <IDs>" not in text, name
    for path in refs.glob("*.md"):
        assert "relay" not in path.read_text(encoding="utf-8").lower(), path.name


@pytest.mark.sr("SR-267")
def test_skills_ask_waiting_questions_through_the_tool_never_in_prose(installed: Path) -> None:
    """EX-8: with questions waiting, the agent asks them through the question tool, verbatim,
    and never restates them as a list to answer in prose."""
    assert RULES[0] in _texts(installed)["plumb-records"]
    states = (installed / ".claude" / "skills" / "plumb-clarify" / "references"
              / "clarify-states.md")
    assert "- ask (plumb's judge has questions about what the owner meant)" in " ".join(
        states.read_text(encoding="utf-8").split())


@pytest.mark.sr("SR-379")
def test_question_rules_live_in_plumb_records_and_others_point_to_it(installed: Path) -> None:
    """EX-1: the question rules (and the pacing sentence) appear in plumb-records only; the
    other skills and the /plumb command say where they are."""
    texts = _texts(installed)
    at = [texts["plumb-records"].find(rule) for rule in RULES]
    assert -1 not in at and at == sorted(at)
    assert texts["plumb-records"].count("every judge question is asked at the next chance") == 1
    for name, text in texts.items():
        if name == "plumb-records":
            continue
        assert POINTER in text, name
        assert "every judge question is asked at the next chance" not in text, name
        for rule in RULES:
            assert rule not in text, name
        for gone in ("question pushback", "Never answer, infer or default"):
            assert gone not in text, (name, gone)


@pytest.mark.sr("SR-379")
def test_clarify_triggers_on_intent_change_only(installed: Path) -> None:
    """EX-2: plumb-clarify's description names intent changes and the spec session, not every
    request, so an ordinary tidy-up does not match it."""
    skill = (installed / ".claude" / "skills" / "plumb-clarify" / "SKILL.md").read_text(
        encoding="utf-8")
    description = " ".join(skill.split("---", 2)[1].split())
    assert "creates or changes intent" in description and "spec session" in description
    assert "Not for tidy-ups" in description
    assert "every owner request" not in description


@pytest.mark.sr("SR-379")
def test_glossary_defines_every_plumb_term_used(installed: Path) -> None:
    """EX-3: each term the skills use is defined by one line of the glossary (ten lines at
    most)."""
    skills = installed / ".claude" / "skills"
    glossary = (skills / "plumb-records" / "references" / "glossary.md").read_text(
        encoding="utf-8").splitlines()
    terms = ("band", "room", "loop pane", "stale link", "repin", "relink", "reword",
             "intent conflict")
    defined = [line[2:].split(":")[0] for line in glossary if line.startswith("- ")]
    assert defined == list(terms) and len(glossary) <= 12
    used = " ".join(p.read_text(encoding="utf-8") for p in skills.glob("plumb-*/**/*.md"))
    assert "repin" in used and "stale link" in used
    assert "glossary.md" in _texts(installed)["plumb-records"]


@pytest.mark.sr("SR-379")
def test_no_record_ids_in_skills(installed: Path) -> None:
    import re

    ids = re.compile(r"\b(?:INT|SR|DEC|FEAT|NC)-\d")
    for path in (installed / ".claude" / "skills").glob("plumb-*/**/*.md"):
        assert not ids.search(path.read_text(encoding="utf-8")), path.name
    for name, text in _texts(installed).items():
        assert not ids.search(text), name


@pytest.mark.sr("SR-379")
def test_command_grants_no_destructive_git(installed: Path) -> None:
    """EX-4: git rm, git commit, git merge and git checkout --ours/--theirs are not
    pre-approved by the /plumb command."""
    text = (installed / ".claude" / "commands" / "plumb.md").read_text(encoding="utf-8")
    allowed = next(line for line in text.splitlines() if line.startswith("allowed-tools:"))
    for git in ("git rm", "git commit", "git merge", "git checkout"):
        assert git not in allowed, git
    assert len(text.split("---", 2)[1].strip().splitlines()) == 3   # one-line description


@pytest.mark.sr("SR-379")
def test_stage_a_runs_in_the_main_session(installed: Path) -> None:
    """EX-5: a blocking question of stage A is asked from the main session with the question
    tool, never from a workflow agent; stages B and C may be workflow phases."""
    text = _texts(installed)["plumb-intent"]
    assert "Stage A runs in this session" in text and "never from a workflow agent" in text
    assert "stages B and C run as its phases" in text


@pytest.mark.sr("SR-396")
def test_sr396_ex1_the_proof_question_offers_the_evaluator_first(installed: Path) -> None:
    """EX-1: the loop's proof question suggests the independent evaluator as its first option,
    in every loop; stage C then runs it instead of showing the proof."""
    text = _texts(installed)["plumb-intent"]
    stage_a = text[text.find("Stage A,"):text.find("Stage B,")]
    from plumb.capture.proof import EVALUATOR_OPTION   # the label plumb looks for

    assert f'first option, marked as the suggestion, is "{EVALUATOR_OPTION}"' in stage_a
    assert "never take it as picked from an earlier one" in stage_a and "--evaluator" in stage_a
    stage_c = text[text.find("Stage C,"):text.find("Studies:")]
    for words in ("plumb evaluate proof", "ask nothing", "plumb proof SR-### --overrule",
                  "Never record a verdict by hand"):
        assert words in stage_c, words


@pytest.mark.sr("SR-396")
def test_sr396_ex5_a_fix_run_offers_the_evaluator_once_at_launch(installed: Path) -> None:
    """EX-5: plumb's own fix runs offer the evaluator once, at launch, and ask nothing after."""
    text = _texts(installed)["plumb-debug"]
    assert "offer the independent proof evaluator once with the question tool" in text
    assert "--proof-evaluator" in text and "Ask nothing during the run" in text


@pytest.mark.sr("SR-293")
def test_each_intent_stage_picks_its_study_before_its_gate(installed: Path) -> None:
    """SR-293 EX-6: each stage of the loop proposes its step's study idea (or none) as its
    last step before its gate, so the agent proposes without a prompt mentioning studies."""
    text = _texts(installed)["plumb-intent"]
    stages = [text.find(f"Stage {s},") for s in "ABC"] + [text.find("Studies:")]
    assert -1 not in stages and stages == sorted(stages)
    gates = ("intent gate clarify --findings", "intent gate plan --findings", "intent done`.")
    for (start, end), gate in zip(zip(stages, stages[1:]), gates):
        stage = text[start:end]
        assert "plumb study propose" in stage and "study candidates" in stage
        assert stage.rfind("study propose") < stage.rfind(gate), gate
