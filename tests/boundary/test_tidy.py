"""SR-286: at a landing the tidy deletes, in one commit, the documents the landed decision
names; a folder outside the repository goes without a commit; a cited document stays."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boundary.test_landing import debug_cases, decision, docs, head, land_branch
from mergedriver.mdhelpers import commit_all, record, run_git, write_record
from iaso.boundary import landing

pytestmark = pytest.mark.sr("SR-286")

SPECS = ["docs/specs/sp1-records.md", "docs/plans/sp1-records.md", "followups.md"]


def feature(cites: str) -> str:
    return record("FEAT-001", "Sub-project 1: records" if cites else "Records",
                  description=f"what {cites} specifies" if cites else "the records")


def test_ex1_the_named_files_go_in_one_tidy_commit_and_the_rest_stay(repo: Path) -> None:
    docs(repo, *SPECS, "docs/sp9-intent-loop.md", "docs/concept.md")
    write_record(repo, feature(SPECS[0]))
    commit_all(repo, "v1")

    def build(root: Path) -> None:
        decision(*SPECS)(root)
        write_record(root, feature(""))          # the landing rewords what cited the spec

    sha, before = land_branch(repo, build)
    result = landing.land(repo, sha, before)
    assert result["removed"] == SPECS
    gone = run_git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert sorted(gone) == sorted(SPECS)
    assert (repo / "docs" / "sp9-intent-loop.md").exists()
    assert (repo / "docs" / "concept.md").exists()
    texts = [p.read_text(encoding="utf-8") for p in (repo / ".iaso").rglob("FEAT-*.md")]
    assert not any(s in t for s in SPECS for t in texts)
    assert all(s in landing.lines(repo)[0][1] for s in SPECS)


def test_ex2_a_folder_outside_the_repository_goes_without_a_commit(repo: Path,
                                                                   tmp_path: Path) -> None:
    outside = tmp_path / "pruned-worktrees"
    (outside / "old").mkdir(parents=True)
    (outside / "old" / "f.txt").write_text("x", encoding="utf-8")
    sha, before = land_branch(repo, decision(str(outside)))
    result = landing.land(repo, sha, before)
    assert not outside.exists() and result["outside"] == [str(outside)]
    assert head(repo) == sha                   # nothing in the repository: no commit
    assert str(outside) in landing.lines(repo)[0][1]


def test_ex3_a_document_a_current_record_cites_stays_and_goes_to_debugging(
        repo: Path) -> None:
    docs(repo, "docs/spec.md")
    write_record(repo, record("SR-001", "rule", statement="as docs/spec.md says"))
    commit_all(repo, "cited")
    sha, before = land_branch(repo, decision("docs/spec.md"))
    result = landing.land(repo, sha, before)
    assert (repo / "docs" / "spec.md").exists() and result["removed"] == []
    rows = [r for r in debug_cases(repo, sha) if r["kind"] == "tidy-cited"]
    assert rows and "SR-001" in rows[0]["detail"]


def test_ex4_tidying_again_changes_nothing(repo: Path) -> None:
    from iaso.api import open_core

    docs(repo, "docs/a.md")
    commit_all(repo, "doc")
    sha, before = land_branch(repo, decision("docs/a.md"))
    landing.land(repo, sha, before)
    after = head(repo)
    assert landing.tidy(open_core(repo), before, sha) == ([], [], [])
    assert landing.land(repo, sha, before)["line"] == "" and head(repo) == after


def test_ex5_an_owner_file_no_landing_named_is_untouched(repo: Path) -> None:
    docs(repo, "docs/a.md", "docs/mine.md")
    commit_all(repo, "docs")
    sha, before = land_branch(repo, decision("docs/a.md"))
    landing.land(repo, sha, before)
    assert (repo / "docs" / "mine.md").read_text(encoding="utf-8") == "docs/mine.md\n"
    assert json.loads(landing.marker(repo, sha).read_text(encoding="utf-8"))["removed"] == \
        ["docs/a.md"]
