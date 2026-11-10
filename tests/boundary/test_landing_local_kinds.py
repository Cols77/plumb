"""report-003e0dc7: the landing's tidy commit never adds a local-kind or owner-words entry's
content, whatever the ignore rules say or git already tracks at the time."""

from __future__ import annotations

from pathlib import Path

import pytest

from boundary.test_landing import docs, land_branch
from core.test_log_compaction import put
from mergedriver.mdhelpers import commit_all, run_git
from iaso import log
from iaso.boundary import landing
from iaso.normalize import canonical_json

KINDS = ("prompt", "verdict", "repin", "gate", "card-withdrawn")

pytestmark = pytest.mark.sr("SR-321")


def test_the_tidy_never_commits_a_tracked_local_segment(repo: Path) -> None:
    """A segment main still tracks: the entry's removal is committed, the owner's words the
    compaction appended to the segment are not."""
    folder = repo / ".iaso" / "log" / "prompt"
    earlier = put(repo, "prompt", {"text": "committed long ago"})
    segment = folder / "archive.jsonl"
    segment.write_bytes(canonical_json(earlier) + b"\n")
    next(iter(folder.glob("*.json"))).unlink()
    put(repo, "prompt", {"text": "the owner's own words"}, prev=earlier["digest"])
    (entry,) = folder.glob("*.json")
    run_git(repo, "add", "-f", ".iaso/log/prompt")
    commit_all(repo, "a prompt entry and segment tracked before the kind became local")
    sha, before = land_branch(repo, lambda root: docs(root, "x.md"))

    assert landing.land(repo, sha, before)["archived"] == 1

    assert b"the owner's own words" in segment.read_bytes(), "the compaction moved it: the premise"
    shown = run_git(repo, "show", "--no-renames", "--name-status", "--format=", "HEAD").stdout
    assert f"D\t{entry.relative_to(repo).as_posix()}" in shown
    committed = run_git(repo, "show", "HEAD:.iaso/log/prompt/archive.jsonl").stdout
    assert "the owner's own words" not in committed


def test_a_tracked_local_segment_leaves_git_but_its_content_never_enters(repo: Path) -> None:
    """Only a tracked local segment's new content is held back: its removal is committed, so a
    segment main still tracks can leave the tree."""
    put(repo, "job-note", {"kind": "k", "job": "j", "detail": "d"})
    segment = repo / ".iaso" / "log" / "job-note" / "archive.jsonl"
    segment.write_bytes(b"{}\n")
    run_git(repo, "add", "-f", ".iaso/log/job-note")
    commit_all(repo, "a job-note segment tracked before the kind became local")
    name = segment.relative_to(repo).as_posix()

    assert log.committable(repo, [name]) == []
    segment.unlink()
    assert log.committable(repo, [name]) == [name]


def test_the_tracked_judgment_segment_still_gets_each_landings_entries(repo: Path) -> None:
    """Judgment is not a local kind: SR-321 moves its entries into its tracked segment at each
    landing, and that segment's new content is committed."""
    folder = repo / ".iaso" / "log" / "judgment"
    earlier = put(repo, "judgment", {"subject": "SR-001"})
    (folder / "archive.jsonl").write_bytes(canonical_json(earlier) + b"\n")
    next(iter(folder.glob("*.json"))).unlink()
    run_git(repo, "add", "-f", ".iaso/log/judgment/archive.jsonl")
    commit_all(repo, "the judgment segment")
    put(repo, "judgment", {"subject": "SR-002"}, prev=earlier["digest"])
    sha, before = land_branch(repo, lambda root: docs(root, "x.md"))

    assert landing.land(repo, sha, before)["archived"] == 1

    assert "SR-002" in run_git(repo, "show", "HEAD:.iaso/log/judgment/archive.jsonl").stdout


def test_no_untracked_local_entry_is_committed_without_ignore_rules(repo: Path) -> None:
    """Main's ignore rules lack the local kinds (a landing before they arrive). The entries are
    written after the merge, as a hook writes them: the tidy is what could first track them."""
    sha, before = land_branch(repo, lambda root: (root / ".iaso" / ".gitignore").write_text(
        "", encoding="utf-8") and None)
    put(repo, "approval", {"subject": "SR-001"})   # a shared entry, so a tidy commit happens
    for kind in KINDS:
        put(repo, kind, {"subject": "SR-001", "text": "t"})

    landing.land(repo, sha, before)

    shown = run_git(repo, "show", "--name-status", "--format=", "HEAD").stdout
    tracked = run_git(repo, "ls-files", "--", ".iaso/log").stdout
    assert ".iaso/log/approval/" in shown
    for kind in KINDS:
        assert f".iaso/log/{kind}/" not in shown
        assert f".iaso/log/{kind}/" not in tracked
