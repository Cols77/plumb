"""The skills and the /plumb command the installer writes (SR-120, SR-122; DEC-036): the
grounding skill is plumb-records so /plumb is the command, the skills cover every answer of
``clarify --wait``, and the command answers every typed verb and allows exactly what it runs."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from plumb.guard import TABLE
from plumb.hosts.claude_code import install
from plumb.understand import cmd_clarify

TEMPLATES = Path(install.__file__).parent / "templates"
PATH = install.Launcher("path", "plumb", "plumb")


def _installed(repo: Path) -> Path:
    install.install(repo, launcher=PATH, hooks=(), commit_hook=False)
    return repo / ".claude"


def _command() -> str:
    return (TEMPLATES / "plumb-command.md").read_text(encoding="utf-8")


def _allowed(text: str) -> list[str]:
    line = next(x for x in text.splitlines() if x.startswith("allowed-tools:"))
    return re.findall(r"Bash\(([^)]*)\)", line)


def _body(text: str) -> str:
    return text.split("---", 2)[2]


@pytest.mark.sr("SR-202")
def test_grounding_skill_is_plumb_records_with_its_references(repo: Path) -> None:
    """EX-1: the skills listed are plumb-records, plumb-clarify, plumb-debug (SR-328) and
    plumb-intent; none is named plumb."""
    claude = _installed(repo)
    assert install.skill_names() == ["plumb-clarify", "plumb-debug", "plumb-intent",
                                     "plumb-records", "plumb-study-video"]
    assert not (claude / "skills" / "plumb").exists()
    for name in ("SKILL.md", "references/merge.md", "references/conflicts.md",
                 "references/capture-doc.md"):
        text = (claude / "skills" / "plumb-records" / name).read_text(encoding="utf-8")
        assert "{plumb}" not in text, name
    skill = (claude / "skills" / "plumb-records" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: plumb-records\n")
    for name in ("references/merge.md", "references/conflicts.md", "references/capture-doc.md"):
        assert name in skill, name


@pytest.mark.sr("SR-202")
def test_command_reads_the_references_where_this_install_put_them(repo: Path) -> None:
    """The plugin's command names its own root; the per-repository copy names .claude/."""
    assert "${CLAUDE_PLUGIN_ROOT}/skills/plumb-records/references/merge.md" in _command()
    text = (_installed(repo) / "commands" / "plumb.md").read_text(encoding="utf-8")
    assert "CLAUDE_PLUGIN_ROOT" not in text
    for name in ("merge.md", "conflicts.md"):
        rel = f".claude/skills/plumb-records/references/{name}"
        assert rel in text and (repo / rel).is_file(), name


@pytest.mark.sr("SR-202")
def test_install_removes_the_retired_plumb_skill_only_when_it_is_plumbs(repo: Path) -> None:
    old = repo / ".claude" / "skills" / "plumb"
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text(
        "---\nname: plumb\ndescription: Ground work in this repository's plumb records "
        "(owner intent).\n---\n# plumb\n", encoding="utf-8")
    report = install.install(repo, launcher=PATH, hooks=(), commit_hook=False, dry_run=True)
    assert old.exists() and ".claude/skills/plumb" in report.changed
    install.install(repo, launcher=PATH, hooks=(), commit_hook=False)
    assert not old.exists()
    assert (repo / ".claude" / "skills" / "plumb-records" / "SKILL.md").is_file()
    # a skill of the owner's own that happens to be named plumb is kept
    old.mkdir()
    (old / "SKILL.md").write_text("---\nname: plumb\ndescription: my plumbing notes\n---\n",
                                  encoding="utf-8")
    install.install(repo, launcher=PATH, hooks=(), commit_hook=False)
    install.uninstall(repo)
    assert (old / "SKILL.md").is_file()


@pytest.mark.sr("SR-202")
def test_uninstall_removes_the_skills_and_their_references(repo: Path) -> None:
    claude = _installed(repo)
    install.uninstall(repo)
    assert not (claude / "skills" / "plumb-records").exists()
    assert not (claude / "skills" / "plumb-clarify").exists()
    status = "\n".join(install.status(repo))
    assert "skill: not installed" in status


@pytest.mark.sr("SR-202")
def test_clarify_skill_covers_every_answer_of_clarify_wait(repo: Path) -> None:
    """EX-1: waiting means build nothing and run clarify --wait again; every state the
    command can answer is named."""
    states = re.search(r"state: str\s+# (.+)", Path(cmd_clarify.__file__).read_text(
        encoding="utf-8")).group(1).split(" | ")
    assert set(states) == {"ready", "ask", "card", "couldnt_check", "waiting",
                           "held"}
    folder = _installed(repo) / "skills" / "plumb-clarify"
    # SR-379: the state table lives in the skill's references; the skill points to it
    skill = (folder / "SKILL.md").read_text(encoding="utf-8")
    assert "references/clarify-states.md" in skill
    states_doc = (folder / "references" / "clarify-states.md").read_text(encoding="utf-8")
    for state in states:
        assert f"`{state}`" in states_doc, state
    waiting = states_doc[states_doc.index("- waiting"):].split("\n\n", 1)[0]
    assert "build nothing" in waiting and "plumb clarify --wait" in waiting
    head = skill.split("---", 2)[1]
    assert "creates or changes intent" in head  # SR-379 EX-2: not on every message


@pytest.mark.sr("SR-202")
def test_records_skill_runs_clarify_wait_first_and_names_the_guarded_commands(
        repo: Path) -> None:
    skill = (_installed(repo) / "skills" / "plumb-records" / "SKILL.md").read_text(
        encoding="utf-8")
    first = _body(skill).strip().split("\n- ")[1]
    assert first.startswith(
        "Every message, after `capture`: run `plumb clarify --wait --json` and act on its "
        "answer")
    assert "message_digest" in skill and "sha256" in skill
    assert "plumb tests map" in skill  # what to run when the test map is missing
    for row in TABLE:
        assert f"`{row.words[0]}" in skill or f"plumb {row.words[0]}" in skill, row.name


@pytest.mark.sr("SR-202")
def test_command_has_a_branch_for_each_typed_verb_and_a_fallback() -> None:
    """EX-2: /plumb init runs plumb init and reports it; EX-3: a typed approve approves
    nothing in the agent's session and the agent reports the status card."""
    body = _body(_command())
    assert "ignoring case" in body
    init = body[body.index("- `init`"):].split("\n- ", 1)[0]
    assert "run `{plumb} init`" in init and "report what it printed" in init
    typed = body[body.index("- `go`, `undo <ID>`"):].split("\n- ", 1)[0]
    assert "Run nothing to approve" in typed and "`{plumb} status --card`" in typed
    assert "install what plumb needs" in body
    assert "`{plumb} resolve <their words>`" in body
    drop = body[body.index("\"drop that work\""):].split("\n- ", 1)[0]
    assert "repeat it back" in drop
    assert body.count("message_digest") == 1


@pytest.mark.sr("SR-202")
def test_command_allows_exactly_what_it_runs_and_no_owner_command() -> None:
    text = _command()
    allowed = _allowed(text)
    # the body runs these itself or through the reference files it follows
    refs = TEMPLATES / "skills" / "plumb-records" / "references"
    runs = _body(text) + "".join((refs / n).read_text(encoding="utf-8")
                                 for n in ("merge.md", "conflicts.md"))
    run = set(re.findall(r"`\{plumb\} ([a-z-]+(?: --wait| migrate)?)", runs))
    run -= {"clarify", "relay"}  # clarify runs as --wait; a plain relay is named as refused
    for verb in run:
        assert any(rule.startswith(f"{{plumb}} {verb}") for rule in allowed), verb
    plumb_rules = {rule.split(":")[0].removeprefix("{plumb} ") for rule in allowed
                   if rule.startswith("{plumb} ")}
    for rule in plumb_rules:
        first = rule.split()[0]
        assert re.search(rf"\{{plumb\}} {re.escape(rule)}\b", runs) or (
            # SR-379: question reword runs as plumb-records says, which the command points to
            first in {"brief", "why", "show", "align", "question"}), rule
    for row in TABLE:
        if row.unless is None:
            assert not any(r.startswith(f"{{plumb}} {' '.join(row.words)}") for r in allowed)
    assert not any(r.startswith("{plumb} go") for r in allowed)  # the prompt hook does it
    git = [r for r in allowed if r.startswith("git ")]
    for rule in git:
        assert rule.split(":")[0] in runs, rule
    assert git and all(not r.startswith(("git push", "git reset --hard")) for r in git)
    assert "git add .plumb:*" in git and "git reset --keep ORIG_HEAD" in git


@pytest.mark.sr("SR-202")
def test_references_give_the_conflict_forms_and_a_capture_document_that_parses() -> None:
    refs = TEMPLATES / "skills" / "plumb-records" / "references"
    conflicts = (refs / "conflicts.md").read_text(encoding="utf-8")
    # the relay came back through the model (SR-076); the agent also proposes and suggests
    assert "conflict propose" in conflicts
    merge = (refs / "merge.md").read_text(encoding="utf-8")
    for step in ("git merge --no-ff", "git reset --keep ORIG_HEAD", "git rebase --continue",
                 "merge-check --hook pre-merge-commit", "git checkout --ours"):
        assert step in merge, step
    doc = (refs / "capture-doc.md").read_text(encoding="utf-8")
    blocks = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", doc, re.DOTALL)]
    assert set(blocks[0]) == {"intent", "requirements", "decisions"}
    assert all({"question", "options", "recommended"} <= set(q) for q in blocks[1])


def test_skill_files_wrap_at_95_columns() -> None:
    # vendor/ holds third-party skills kept as published (VENDORED.md)
    skills = [p for p in TEMPLATES.joinpath("skills").rglob("*.md") if "vendor" not in p.parts]
    for path in [*skills, TEMPLATES / "plumb-command.md"]:
        body = path.read_text(encoding="utf-8")
        if body.startswith("---"):
            body = body.split("---", 2)[2]
        assert max(len(line) for line in body.splitlines()) <= 95, path.name
