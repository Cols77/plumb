"""P6: every advertised verb is available and /plumb why stays fixed (sp5 6.4, SR-068)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from present_helpers import SR1, write_all

from plumb import cli

pytestmark = pytest.mark.sr("SR-068")

TEMPLATE = (Path(cli.__file__).parent / "hosts" / "claude_code" / "templates"
            / "plumb-command.md")


def _command_file_verbs() -> set[str]:
    text = TEMPLATE.read_text(encoding="utf-8")
    hint = next(line for line in text.splitlines() if line.startswith("argument-hint:"))
    verbs = {part.split()[0] for part in hint.split('"')[1].split("|")}
    verbs |= set(re.findall(r"Bash\(\{plumb\} ([a-z-]+):\*\)", text))
    verbs |= set(re.findall(r"`\{plumb\} ([a-z-]+)", text))
    return verbs


def _help_verbs() -> set[str]:
    verbs: set[str] = set()
    for line in cli.help_text().splitlines():
        verb = re.match(r"^  ([a-z][a-z-]*)\s{2,}", line)
        if verb:
            verbs.add(verb.group(1))
            continue
        listed = re.match(r"^([a-z][a-z ]*:)\s+(.*)$", line)
        if listed and listed.group(1) not in ("usage:",):
            verbs |= {item.split(" ")[0] for item in listed.group(2).split(", ")
                      if item and item.split(" ")[0] in cli.ROUTES}
    return verbs


def test_every_advertised_verb_is_routed_and_its_help_exits_zero(capsys) -> None:
    """EX-1: each verb of the installed /plumb command and of plumb --help is routed, and
    plumb <verb> --help exits 0."""
    advertised = _command_file_verbs() | _help_verbs()
    assert {"status", "explain", "why", "review", "confirm", "impact", "view", "resolve",
            "align"} <= advertised
    for verb in sorted(advertised):
        assert verb in cli.ROUTES, verb
        assert cli.main([verb, "--help"]) == 0, verb
    capsys.readouterr()


def test_why_prints_the_same_explanation_as_explain(repo: Path, write_record,
                                                    capsys) -> None:
    """EX-2: plumb why SR-001 prints what plumb explain SR-001 prints."""
    write_all(repo, write_record, SR1)
    assert cli.main(["explain", "--root", str(repo), "SR-001"]) == 0
    explained = capsys.readouterr().out
    assert cli.main(["why", "--root", str(repo), "SR-001"]) == 0
    assert capsys.readouterr().out == explained
    assert "not available in this build" not in explained


def test_help_lists_only_importable_verbs(monkeypatch) -> None:
    monkeypatch.setitem(cli.ROUTES, "ghost", "plumb.no_such_module_here")
    monkeypatch.setattr(cli, "_HELP", cli._HELP.replace(
        "records and integrity:\n",
        "records and integrity:\n  ghost        haunts the build\n                still\n")
        .replace("host:          hook,", "host:          ghost, hook,"))
    text = cli.help_text()
    assert "ghost" not in text and "haunts" not in text and "still" not in text
    assert "  init " in text and "host:          hook, hooks" in text
    assert cli.main(["ghost"]) == 2


@pytest.mark.sr("SR-039")
def test_plumb_command_routes_jev_setup_and_status() -> None:
    """R14: the owner reaches JEV setup and status through /plumb, never a shell."""
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "Bash({plumb} jev status:*)" in text and "Bash({plumb} jev setup:*)" in text
    assert "`jev status`" in text and "`jev setup" in text
    assert "{plumb} jev setup --provider openrouter" in text
    assert "{plumb} jev status --probe" in text


@pytest.mark.sr("SR-039")
def test_plumb_command_routes_jev_calibrate() -> None:
    """R14: the owner reaches calibration as /plumb jev calibrate; the agent runs the CLI."""
    text = TEMPLATE.read_text(encoding="utf-8")
    hint = next(line for line in text.splitlines() if line.startswith("argument-hint:"))
    assert "jev calibrate" in hint
    assert "Bash({plumb} jev calibrate:*)" in text and "`jev calibrate`" in text
    assert "run `{plumb} jev calibrate`" in text
