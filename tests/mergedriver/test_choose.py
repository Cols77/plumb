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
    log_prompt,
    parse,
    plumb,
    reads,
    record,
    shown,
    unreachable,
    write_record,
)
from plumb import cli
from plumb.api import open_core
from plumb.mergedriver import open_conflicts

pytestmark = pytest.mark.sr("SR-076")
SR = ".plumb/requirements/SR-005.md"


def _record(repo: Path) -> dict:
    return parse((repo / SR).read_text(encoding="utf-8"))[0]


def _relay(repo: Path, words: str, take: str, quote: str | None = None) -> int:
    digest = log_prompt(repo, words)
    return cli.main(["conflict", "relay", "IC-001", "--take", take, "--prompt", digest,
                     "--quote", quote or words, "--root", str(repo)])


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


def test_relay_needs_logged_prompt_and_card_in_stated_set(repo: Path, monkeypatch) -> None:
    conflicted(repo)
    reads(monkeypatch, repo, "change", "keep feat-x's version", "Keep feat-x's version")
    assert _relay(repo, "keep feat-x's version", "theirs") == 3  # the card was not shown
    assert _record(repo).get("conflict")
    shown(repo)
    assert cli.main(["conflict", "relay", "IC-001", "--take", "theirs", "--prompt",
                     "sha256:" + "0" * 64, "--quote", "keep feat-x's version",
                     "--root", str(repo)]) == 3  # not a logged prompt
    assert _relay(repo, "keep feat-x's version", "theirs") == 0
    (entry,) = events(repo, "conflict-resolution")
    assert entry["by"] == "agent-relayed" and entry["quote"] == "keep feat-x's version"
    assert entry["prompt"].startswith("sha256:")


def test_choose_with_prompt_is_the_relay(repo: Path, monkeypatch) -> None:
    conflicted(repo)
    shown(repo)
    reads(monkeypatch, repo, "change", "keep mine", "Keep main's version")
    digest = log_prompt(repo, "keep mine")
    assert cli.main(["conflict", "choose", "IC-001", "--take", "ours", "--prompt", digest,
                     "--quote", "keep mine", "--root", str(repo)]) == 0
    assert _record(repo)["statement"] == OURS_STATEMENT


def test_relay_takes_only_the_version_the_reading_found(repo: Path, monkeypatch) -> None:
    conflicted(repo)
    shown(repo)
    reads(monkeypatch, repo, "open", "whatever")
    assert _relay(repo, "keep main's or feat-x's, whatever", "theirs") == 3
    reads(monkeypatch, repo, "change", "keep main's", "Keep main's version")
    assert _relay(repo, "keep main's", "theirs") == 3  # the reading found the other side
    assert _record(repo).get("conflict")


def test_relay_without_take_applies_the_reading(repo: Path, monkeypatch) -> None:
    conflicted(repo)
    shown(repo)
    reads(monkeypatch, repo, "change", "keep feat-x's version", "Keep feat-x's version")
    digest = log_prompt(repo, "keep feat-x's version")
    assert cli.main(["conflict", "relay", "IC-001", "--prompt", digest,
                     "--quote", "keep feat-x's version", "--root", str(repo)]) == 0
    assert _record(repo)["statement"] == THEIRS_STATEMENT


def test_relay_with_a_change_asked_or_a_refusal_leaves_it_open(repo: Path,
                                                                monkeypatch) -> None:
    """SR-076 EX-4: the model reads a reservation or a refusal: exit 3, nothing changes."""
    conflicted(repo)
    shown(repo)
    before = (repo / SR).read_bytes()
    words = "keep feat-x's but change the title"
    reads(monkeypatch, repo, "change", words, "Keep feat-x's version, with its title changed")
    assert _relay(repo, words, "theirs") == 3
    reads(monkeypatch, repo, "rejected", "no, not feat-x's")
    assert _relay(repo, "no, not feat-x's", "theirs") == 3
    assert (repo / SR).read_bytes() == before
    assert events(repo, "conflict-resolution") == []


def test_relay_naming_a_side_is_not_enough_without_the_reading(repo: Path,
                                                               monkeypatch) -> None:
    """The agent's own match of the side's name settles nothing: the reading left it open."""
    conflicted(repo)
    shown(repo)
    reads(monkeypatch, repo, "open", "keep feat-x's version")
    assert _relay(repo, "keep feat-x's version", "theirs") == 3
    assert _record(repo).get("conflict")


def test_relay_with_the_model_unreachable_is_refused(repo: Path, monkeypatch,
                                                     capsys) -> None:
    conflicted(repo)
    shown(repo)
    before = (repo / SR).read_bytes()
    unreachable(monkeypatch, repo)
    assert _relay(repo, "keep feat-x's version", "theirs") == 3
    assert "the model could not be reached" in capsys.readouterr().err
    assert (repo / SR).read_bytes() == before
    assert events(repo, "conflict-resolution") == []


def test_relay_ignores_an_unrelated_request_in_the_same_message(repo: Path,
                                                               monkeypatch) -> None:
    """R16: only the quote counts; another request in the message neither blocks nor
    counts."""
    conflicted(repo)
    shown(repo)
    reads(monkeypatch, repo, "change", "Keep feat-x's version", "Keep feat-x's version")
    words = "Make the docs shorter. Keep feat-x's version"
    assert _relay(repo, words, "theirs", quote="Keep feat-x's version") == 0


def test_choosing_a_confirmed_side_reconfirms(repo: Path, monkeypatch) -> None:
    """SR-076 EX-3: feat-x's version was confirmed: choosing it confirms SR-005 again."""
    from plumb.approvals import approve

    theirs = record(statement=THEIRS_STATEMENT, examples=[ex(1)])
    write_record(repo, theirs)
    approve(open_core(repo), ["SR-005"])
    conflicted(repo, theirs=theirs)
    assert open_core(repo).status(["SR-005"])["SR-005"].confirmation != "confirmed"
    assert _choose(repo, "feat-x") == 0
    assert open_core(repo).status(["SR-005"])["SR-005"].confirmation == "confirmed"


def test_combined_stays_proposed(repo: Path, tmp_path: Path, monkeypatch) -> None:
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


@pytest.mark.sr("SR-076")
def test_command_and_skill_relay_only_the_owners_logged_words() -> None:
    """DEC-051 supersedes SR-150 EX-3: the command allows `conflict relay` and the skill
    says to relay only the owner's own logged words."""
    from plumb.hosts.claude_code import install

    root = Path(install.__file__).parent / "templates"
    command = (root / "plumb-command.md").read_text(encoding="utf-8")
    assert "Bash({plumb} conflict relay:*)" in command
    text = (root / "skills/plumb-records/references/conflicts.md").read_text(encoding="utf-8")
    assert "conflict relay" in text and "their own logged words" in text
