"""D6: only the owner chooses a side (sp6 8.4, R2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mergedriver.mdhelpers import (
    BASE_STATEMENT,
    OURS_STATEMENT,
    THEIRS_STATEMENT,
    conflicted,
    events,
    ex,
    parse,
    plumb,
    record,
    write_record,
)
from plumb import cli
from plumb.api import open_core
from plumb.mergedriver import open_conflicts

pytestmark = pytest.mark.sr("SR-256")
SR = ".plumb/requirements/SR-005.md"


def _record(repo: Path) -> dict:
    return parse((repo / SR).read_text(encoding="utf-8"))[0]


def _choose(repo: Path, take: str) -> int:
    return cli.main(["conflict", "choose", "IC-001", "--take", take, "--root", str(repo)])


def test_owner_terminal_choice_writes_resolution(repo: Path) -> None:
    conflicted(repo)
    assert cli.main(["conflict", "choose", "IC-001", "--take", "feat-x",
                     "--root", str(repo)]) == 0
    data = _record(repo)
    assert data["statement"] == THEIRS_STATEMENT and "conflict" not in data
    assert any(x.get("path") == "tests/test_relay.py" for x in data["links"])
    (entry,) = events(repo, "conflict-resolution")
    assert (entry["ic"], entry["record"], entry["take"], entry["by"]) == (
        "IC-001", "SR-005", "theirs", "owner")


def test_choose_refused_without_terminal(repo: Path) -> None:
    """No marker, stdin a pipe holding "y": exit 3, nothing written."""
    conflicted(repo)
    before = (repo / SR).read_bytes()
    out = plumb(repo, "conflict", "choose", "IC-001", "--take", "theirs", stdin="y\n")
    assert out.returncode == 3
    assert "only the owner chooses a side" in out.stderr
    assert (repo / SR).read_bytes() == before
    assert events(repo, "conflict-resolution") == []


def test_choose_refused_under_marker_without_prompt(repo: Path) -> None:
    """SR-076 EX-4: the agent runs the choice in its shell: exit 3, nothing changes."""
    conflicted(repo)
    before = (repo / SR).read_bytes()
    out = plumb(repo, "conflict", "choose", "IC-001", "--take", "theirs", stdin="y\n",
                env={"PLUMB_AGENT_SESSION": "claude-code"})
    assert out.returncode == 3
    assert (repo / SR).read_bytes() == before
    assert events(repo, "conflict-resolution") == []


def test_choosing_a_confirmed_side_reconfirms(repo: Path) -> None:
    """SR-076 EX-3: feat-x's version was confirmed: choosing it confirms SR-005 again."""
    from plumb.approvals import approve

    theirs = record(statement=THEIRS_STATEMENT, examples=[ex(1)])
    write_record(repo, theirs)
    approve(open_core(repo), ["SR-005"])
    conflicted(repo, theirs=theirs)
    assert open_core(repo).status(["SR-005"])["SR-005"].confirmation != "confirmed"
    assert _choose(repo, "feat-x") == 0
    assert open_core(repo).status(["SR-005"])["SR-005"].confirmation == "confirmed"


def test_combined_stays_proposed(repo: Path, tmp_path: Path) -> None:
    conflicted(repo)
    combined = tmp_path / "combined.yaml"
    combined.write_text("statement: A relay pins the records the owner affirms, by name.\n",
                        encoding="utf-8")
    assert cli.main(["conflict", "propose", "IC-001", "--file", str(combined),
                     "--root", str(repo)]) == 0
    assert _choose(repo, "combined") == 0
    data = _record(repo)
    assert data["statement"] == "A relay pins the records the owner affirms, by name."
    assert open_core(repo).status(["SR-005"])["SR-005"].confirmation != "confirmed"


def test_propose_never_applies(repo: Path, tmp_path: Path) -> None:
    conflicted(repo)
    combined = tmp_path / "combined.yaml"
    combined.write_text("statement: both\n", encoding="utf-8")
    assert cli.main(["conflict", "propose", "SR-005", "--file", str(combined),
                     "--root", str(repo)]) == 0
    data = _record(repo)
    assert data["statement"] == OURS_STATEMENT
    assert data["conflict"]["proposed"]["fields"] == {"statement": "both"}
    assert events(repo, "conflict-resolution") == []
    (conflict,) = open_conflicts(open_core(repo))
    assert conflict.proposed is not None


def test_plain_words_name_the_conflict(repo: Path) -> None:
    conflicted(repo)
    assert cli.main(["conflict", "choose", "the", "relay", "checks", "--take", "main",
                     "--root", str(repo)]) == 0
    assert _record(repo)["statement"] == OURS_STATEMENT
    assert BASE_STATEMENT not in (repo / SR).read_text(encoding="utf-8")


def test_deny_rule_present_in_three_launcher_forms() -> None:
    from plumb.hosts.claude_code.install import Launcher, deny_rules, is_plumb_deny

    rules = deny_rules(Launcher("uv", "uv run --no-sync plumb", "uv run --no-sync plumb"))
    for prefix in ("plumb", "uv run plumb", "python -m plumb"):
        rule = f"Bash({prefix} conflict choose:*)"
        assert rule in rules and is_plumb_deny(rule)
    assert not any("conflict relay" in r for r in rules)


@pytest.mark.sr("SR-150")
def test_owners_own_choice_of_mains_version_is_unchanged(repo: Path) -> None:
    """SR-150 EX-2: main's version is chosen exactly as before."""
    conflicted(repo)
    assert cli.main(["conflict", "choose", "IC-001", "--take", "main",
                     "--root", str(repo)]) == 0
    assert _record(repo)["statement"] == OURS_STATEMENT
    (entry,) = events(repo, "conflict-resolution")
    assert (entry["take"], entry["by"]) == ("ours", "owner")


@pytest.mark.sr("SR-211")
def test_no_template_or_skill_names_the_relay() -> None:
    """SR-150 EX-3, back under DEC-057: no conflict relay or quoted choose is named in the
    skills and command."""
    from plumb.hosts.claude_code import install

    root = Path(install.__file__).parent / "templates"
    for path in (*root.rglob("*.md"), root / "plumb-command.md"):
        text = path.read_text(encoding="utf-8")
        assert "conflict relay" not in text, path
        assert not ("conflict choose" in text and "--quote" in text), path
