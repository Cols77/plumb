"""sp6 11.1: every MERGEDRIVER surface the owner sees names a /plumb command or plain words,
never a shell command (R14). One test per surface, each rendering it for real."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mergedriver.mdhelpers import (
    Counter,
    commit_all,
    conflicted,
    ex,
    install_driver,
    make_repo,
    plumb,
    reads_keep,
    record,
    run_git,
    write_record,
)
from plumb import cli
from plumb.api import open_core
from plumb.boundary.premerge import install_hook
from plumb.mergedriver import conflict_card, merge_texts, open_conflicts, status
from plumb.present import owner_text
from plumb.present.owner_text import bare_cli_verbs

LABELS = ("main", "feat-x")


def _clean(text: str) -> None:
    assert text.strip()
    assert bare_cli_verbs(text) == [], text


@pytest.mark.sr("SR-256")
def test_driver_stderr() -> None:
    """Merged field by field, the add/add collision and the text fallback."""
    merged = merge_texts(record(statement="a"), record(statement="b"),
                         record(statement="a", domain="d"), labels=LABELS,
                         reserve_ic=Counter())
    add_add = merge_texts("", record("SR-070", "one"), record("SR-070", "two"),
                          labels=LABELS, reserve_ic=Counter())
    text = merge_texts(record(statement="a"), record(statement="b"),
                       "---\nid: SR-005\ntitle: [x\n---\n", labels=LABELS,
                       reserve_ic=Counter())
    conflict = merge_texts(record(statement="a"), record(statement="b"),
                           record(statement="c"), labels=LABELS, reserve_ic=Counter())
    held = merge_texts(record(statement="a"), conflict.text, record(statement="d"),
                       labels=LABELS, reserve_ic=Counter())
    assert held.exit == 1
    for result in (merged, add_add, text, conflict, held):
        _clean("\n".join(result.notes))


@pytest.mark.sr("SR-256")
def test_driver_status(tmp_path: Path, capsys) -> None:
    root = make_repo(tmp_path / "r")
    _clean(status(root))
    install_driver(root)
    _clean(status(root))
    assert cli.main(["hooks", "status", "--root", str(root)]) == 0
    out = [line for line in capsys.readouterr().out.splitlines()
           if "merge driver" in line or "pre-merge-commit" in line or "pre-push" in line
           or "prepare-commit-msg" in line]
    _clean("\n".join(out))
    from plumb.present import owner_text

    _clean(owner_text.PREPUSH_INSTALLED)
    _clean(owner_text.FOREIGN_PREPUSH_HOOK)


@pytest.mark.sr("SR-260")
def test_unmerged_section(tmp_path: Path) -> None:
    """modify/delete, an unparsable side and no driver, through the merge report."""
    from plumb.mergedriver.unmerged import unmerged_lines, unmerged_rows

    root = make_repo(tmp_path / "r")
    write_record(root, record(statement="a"))
    write_record(root, record("SR-006", "other", statement="a"))
    commit_all(root, "records")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    write_record(root, record(statement="main's"))
    (root / ".plumb" / "requirements" / "SR-006.md").write_text(
        "---\nid: SR-006\ntitle: [broken\n---\n", encoding="utf-8")
    commit_all(root, "main")
    (other / ".plumb" / "requirements" / "SR-005.md").unlink()
    write_record(other, record("SR-006", "other", statement="feat's"))
    commit_all(other, "feat")
    run_git(root, "merge", "--no-edit", "feat-x", check=False)  # no driver configured
    rows = unmerged_rows(open_core(root))
    assert {r["how"] for r in rows} == {"modify/delete", "no-driver"}
    _clean("\n".join(unmerged_lines(rows)))
    report = plumb(root, "merge-check", "main", "--no-run")
    assert report.returncode == 1
    assert 'say "keep the changed one" or "keep it removed"' in report.stdout
    assert "/plumb init installs the record merge" in report.stdout
    run_git(root, "merge", "--abort")
    install_driver(root)
    run_git(root, "merge", "--no-edit", "feat-x", check=False)
    rows = unmerged_rows(open_core(root))
    assert {r["how"] for r in rows} == {"modify/delete", "text"}
    _clean("\n".join(unmerged_lines(rows)))


@pytest.mark.sr("SR-256")
def test_conflict_card(repo: Path) -> None:
    base = record(statement="s", examples=[ex(1), ex(2)])
    ours = record(statement="s1", examples=[ex(1), ex(2, then="ours")])
    theirs = record(statement="s2", examples=[ex(1), ex(2, then="theirs")])
    conflicted(repo, base=base, ours=ours, theirs=theirs)
    core = open_core(repo)
    _clean("\n".join(conflict_card(core, open_conflicts(core)[0])))
    _clean(plumb(repo, "conflicts").stdout)
    _clean(plumb(repo, "show", "IC-001").stdout)


@pytest.mark.sr("SR-256")
def test_choose_messages(repo: Path, capsys: pytest.CaptureFixture) -> None:
    """The refusal (the agent's shell, a pipe) and the applied choice."""
    conflicted(repo)
    refused = plumb(repo, "conflict", "choose", "IC-001", "--take", "theirs", stdin="y\n",
                    env={"PLUMB_AGENT_SESSION": "claude-code"})
    assert refused.returncode == 3
    _clean(refused.stderr)
    assert cli.main(["conflict", "choose", "IC-001", "--take", "theirs",
                     "--root", str(repo)]) == 0
    applied = capsys.readouterr().out
    _clean(applied)
    assert owner_text.CHOSEN.split("{")[0] in applied


@pytest.mark.sr("SR-260")
def test_premerge_hook_output(tmp_path: Path) -> None:
    """The refusal with MERGE_HELD, and the foreign-hook install text."""
    root = make_repo(tmp_path / "r")
    install_driver(root)
    install_hook(root, sys.executable)
    write_record(root, record(statement="a"))
    commit_all(root, "SR-005")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    write_record(root, record(statement="b"))
    commit_all(root, "main")
    write_record(other, record(statement="c"))
    commit_all(other, "feat")
    held = run_git(root, "merge", "--no-edit", "feat-x", check=False)
    assert held.returncode != 0
    hook_lines = [line for line in (held.stdout + held.stderr).splitlines()
                  if not line.startswith(("Auto-merging", "Not committing", "Automatic"))]
    _clean("\n".join(hook_lines))
    assert owner_text.MERGE_HELD in held.stdout + held.stderr
    run_git(root, "merge", "--abort")
    hook = root / ".git" / "hooks" / "pre-merge-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    foreign = plumb(root, "merge-check", "--install-pre-merge-commit")
    assert foreign.returncode == 1
    _clean(foreign.stdout + foreign.stderr)


@pytest.mark.sr("SR-260")
@pytest.mark.parametrize("operation", ["merge", "rebase", "cherry-pick"])
def test_commit_hold_output(operation: str) -> None:
    """The quick check's lines for a step held on what git will not record, a record it
    cannot read and an open conflict, for a merge and for a rebase or cherry-pick step;
    and the commit hook's install texts."""
    from plumb.boundary.premerge import PremergeReport, render

    report = PremergeReport(
        merging="feat-x", into="main", operation=operation, exit=1,
        unstaged=(".plumb/requirements/SR-005.md",),
        unreadable=({"path": ".plumb/requirements/SR-006.md",
                     "line": "  " + owner_text.UNPARSABLE.format(record="SR-006",
                                                                 title="totals")},))
    lines = render(report)
    _clean("\n".join(lines))
    finish = "finish the merge" if operation == "merge" else f"continue the {operation}"
    assert any(finish in line for line in lines)
    _clean(render(PremergeReport(into="main", operation=operation))[-1])
    _clean(owner_text.COMMIT_HOLD_INSTALLED)
    _clean(owner_text.FOREIGN_COMMIT_HOOK)
