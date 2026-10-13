"""SR-132 EX-2, EX-4: a merge withdraws the merged branch's open cards and says once which
records went in unconfirmed; the records stay proposed."""

from __future__ import annotations

from pathlib import Path

import pytest

from mergedriver.mdhelpers import commit_all, ex, make_repo, record, run_git, write_record
from plumb.api import open_core
from plumb.boundary.premerge import run_post_merge
from plumb.understand import cardstore
from plumb.contracts import CardState, ClarifyQuestion


@pytest.mark.sr("SR-132")
def test_merge_withdraws_branch_cards(tmp_path: Path, capsys) -> None:
    root = make_repo(tmp_path / "main")
    write_record(root, record(title="Relay checks", statement="s", examples=[ex(1)]))
    run_git(root, "checkout", "-q", "-b", "feat-x")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_all(root, "a")
    cards = [CardState(id=f"c{n}", branch="feat-x", questions=(ClarifyQuestion(
        id="q", record="SR-005"),)) for n in (1, 2)]
    cards.append(CardState(id="left", branch="feat-x", status="left_open"))
    cards.append(CardState(id="other", branch="feat-y"))
    cardstore.save(root, "s1", cards)
    run_git(root, "checkout", "-q", "main")
    run_git(root, "merge", "-q", "--no-ff", "--no-verify", "-m", "m", "feat-x")

    assert run_post_merge(root) == 0

    out = capsys.readouterr().out
    assert out.count("went in unconfirmed: Relay checks") == 1
    status = {c.id: c.status for c in cardstore.own_cards(root, "s1")}
    assert status == {"c1": "withdrawn", "c2": "withdrawn", "left": "withdrawn", "other": "open"}
    assert open_core(root).status(["SR-005"])["SR-005"].confirmation == "proposed"


@pytest.mark.sr("SR-132")
def test_syncing_main_into_a_feature_branch_withdraws_nothing(tmp_path: Path, capsys) -> None:
    root = make_repo(tmp_path / "main")
    run_git(root, "checkout", "-q", "-b", "feat-x")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_all(root, "a")
    run_git(root, "checkout", "-q", "main")
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    commit_all(root, "b")
    cardstore.save(root, "s1", [CardState(id="open-on-main", branch="main")])
    run_git(root, "checkout", "-q", "feat-x")
    run_git(root, "merge", "-q", "--no-ff", "--no-verify", "-m", "sync", "main")

    assert run_post_merge(root) == 0

    assert "unconfirmed" not in capsys.readouterr().out
    assert [c.status for c in cardstore.own_cards(root, "s1")] == ["open"]


@pytest.mark.sr("SR-132")
def test_an_older_post_merge_hook_is_refreshed_so_every_merge_reaches_the_withdrawal(
        tmp_path: Path) -> None:
    from plumb.boundary.premerge import POST_HOOK_MARKER, post_hook_path, refresh_post_hook

    root = make_repo(tmp_path / "main")
    path = post_hook_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"#!/bin/sh\n{POST_HOOK_MARKER} (older)\n[ \"$1\" = 1 ] && exit 0\n"
        "[ \"$(git config --bool plumb.mergeHold)\" = false ] && exit 0\n"
        "o=$(git rev-parse -q --verify ORIG_HEAD) || exit 0\n"
        "[ -n \"$(git rev-parse -q --verify HEAD^2)\" ] && exit 0\n"
        "exec python -m plumb merge-check --hook post-merge\n", encoding="utf-8")
    refresh_post_hook(root)
    text = path.read_text(encoding="utf-8")
    assert "HEAD^2" not in text and "mergeHold" not in text and "ORIG_HEAD" not in text
    assert "exec python -m plumb merge-check --hook post-merge" in text


@pytest.mark.sr("SR-132")
def test_merging_the_remote_copy_of_a_branch_withdraws_its_cards(tmp_path: Path, capsys) -> None:
    root = make_repo(tmp_path / "main")
    run_git(root, "checkout", "-q", "-b", "feat-x")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_all(root, "a")
    cardstore.save(root, "s1", [CardState(id="c1", branch="feat-x")])
    run_git(root, "update-ref", "refs/remotes/origin/feat-x", "feat-x")
    run_git(root, "checkout", "-q", "main")
    run_git(root, "merge", "-q", "--no-verify", "origin/feat-x")      # a fast-forward

    assert run_post_merge(root) == 0

    assert [c.status for c in cardstore.own_cards(root, "s1")] == ["withdrawn"]


@pytest.mark.sr("SR-132")
def test_a_branch_made_from_main_and_not_yet_merged_keeps_its_cards(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "main")
    run_git(root, "branch", "fresh")
    cardstore.save(root, "s1", [CardState(id="c1", branch="fresh")])
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    commit_all(root, "b")
    run_git(root, "merge", "-q", "--no-verify", "HEAD")                 # nothing to merge

    assert run_post_merge(root) == 0

    assert [c.status for c in cardstore.own_cards(root, "s1")] == ["open"]


@pytest.mark.sr("SR-132")
def test_a_card_on_the_checked_out_branch_of_a_repository_with_no_commit_is_not_gone(
        tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    root.mkdir()
    run_git(root, "init", "-q", "-b", "main")
    cardstore.save(root, "s1", [CardState(id="c1", branch="main"),
                                CardState(id="c2", branch="never-existed")])

    assert [c.id for c in cardstore.load(root, "s1")] == ["c1"]
