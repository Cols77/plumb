"""SR-296, SR-301: the landing job runs once per landing, in the background, its steps in
order, a failing step a debug case; it writes only main's tree and log."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.test_log_compaction import put
from mergedriver.mdhelpers import commit_all, ex, record, run_git, write_record
from plumb.api import open_core
from plumb.boundary import landing
from plumb.contracts import Target
from plumb.validate import validate
from understand.fakes import engine_standins  # noqa: F401
from understand.test_backlog import bulk
from understand.test_judge_job import SESSION


def head(root: Path) -> str:
    return run_git(root, "rev-parse", "HEAD").stdout.strip()


def land_branch(root: Path, build: Any, *, ff: bool = False) -> tuple[str, str]:
    """``build(root)`` on a branch ``feat``, merged into main; ``(head, before)``."""
    before = head(root)
    run_git(root, "checkout", "-q", "-b", "feat")
    build(root)
    commit_all(root, "feat")
    run_git(root, "checkout", "-q", "main")
    run_git(root, "merge", "-q", "--ff-only" if ff else "--no-ff", "--no-verify",
            *([] if ff else ["-m", "m"]), "feat")
    return head(root), before


def docs(root: Path, *names: str) -> None:
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(f"{name}\n", encoding="utf-8")


def decision(*tidy: str) -> Any:
    return lambda root: write_record(root, record("DEC-001", "clean up", question="q",
                                                  chosen="c", tidy=list(tidy)))


def debug_cases(root: Path, sha: str) -> list[dict[str, Any]]:
    path = root / ".plumb" / "cache" / "debug" / f"{sha}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@pytest.mark.sr("SR-296")
def test_ex1_the_landing_tidies_compacts_and_names_both(repo: Path) -> None:
    write_record(repo, record("SR-001", "old rule", statement="s", examples=[ex(1)]))
    put(repo, "judgment", {"subject": "SR-001"})
    docs(repo, "docs/a.md", "docs/b.md")
    commit_all(repo, "before")

    def build(root: Path) -> None:
        decision("docs/a.md", "docs/b.md")(root)
        write_record(root, record("SR-002", "new rule", statement="s", examples=[ex(1)],
                                  links=[{"kind": "supersedes", "to": "SR-001"}]))

    sha, before = land_branch(repo, build)
    result = landing.land(repo, sha, before)
    assert result["removed"] == ["docs/a.md", "docs/b.md"] and result["archived"] == 1
    changed = run_git(repo, "show", "--no-renames", "--name-status", "--format=", "HEAD").stdout.split("\n")
    assert "D\tdocs/a.md" in changed and "D\tdocs/b.md" in changed
    assert "A\t.plumb/log/judgment/archive.jsonl" in changed
    line = landing.lines(repo)[0][1]
    assert "docs/a.md" in line and "docs/b.md" in line and "compacted 1" in line


@pytest.mark.sr("SR-296")
def test_a_tracked_local_kind_entry_compacts_into_a_committed_deletion(repo: Path) -> None:
    put(repo, "job-note", {"kind": "k", "job": "j", "detail": "d"})
    run_git(repo, "add", "-f", ".plumb/log/job-note")
    commit_all(repo, "a job-note tracked before it became local")
    sha, before = land_branch(repo, lambda root: docs(root, "x.md"))
    result = landing.land(repo, sha, before)
    assert result["archived"] == 1 and not debug_cases(repo, sha)
    assert run_git(repo, "ls-files", "--deleted", "--", ".plumb/log").stdout == ""
    assert run_git(repo, "log", "-1", "--format=%B").stdout.rstrip().endswith("SR: SR-296")


@pytest.mark.sr("SR-287")
def test_ex15_the_landing_commit_names_no_log_path_the_log_code_picks(repo: Path) -> None:
    """SR-287 EX-15 / DEC-195: the landing job never names the log folder or its local kinds;
    the log code drops a local kind's untracked segment and keeps a tracked one's removal."""
    import inspect

    from plumb import log

    source = inspect.getsource(landing._commit)
    assert ".plumb/log" not in source and "LOCAL_KINDS" not in source
    put(repo, "job-note", {"kind": "k", "job": "j", "detail": "d"})
    run_git(repo, "add", "-f", ".plumb/log/job-note")
    commit_all(repo, "a tracked job-note")
    tracked = ".plumb/log/" + sorted(log.tracked_names(repo))[0]
    assert log.committable(repo, ["docs/a.md", tracked, ".plumb/log/job-note/archive.jsonl",
                                  ".plumb/log/judgment/archive.jsonl"]) == [
        "docs/a.md", tracked, ".plumb/log/judgment/archive.jsonl"]


@pytest.mark.sr("SR-296")
def test_ex2_every_waiting_record_is_queued_by_the_landing(repo: Path, write_record,
                                                            engine_standins) -> None:
    from plumb.understand import backlog, files

    bulk(repo, write_record, {"alpha": 39})
    sha, before = land_branch(repo, lambda root: None)
    assert len(backlog.waiting(open_core(repo), SESSION)) == 40
    result = landing.land(repo, sha, before, session=SESSION)
    assert result["queued"] == 40
    assert backlog.waiting(open_core(repo), SESSION) == []
    assert list(files.jobs_dir(repo, SESSION).glob("*.json"))
    assert "queued 40 records" in result["line"]


@pytest.mark.sr("SR-296")
def test_ex3_three_stale_links_become_three_cases(repo: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import backlog

    monkeypatch.setattr(backlog, "queue_waiting", lambda core, session, **kw: backlog.Started())
    write_record(repo, record("SR-001", "rule", statement="s", examples=[ex(1)]))
    docs(repo, "src/a.py", "src/b.py", "src/c.py")
    core = open_core(repo)
    for name in ("a", "b", "c"):
        core.add_link("SR-001", "implemented_by", Target(path=f"src/{name}.py"))
    commit_all(repo, "linked")
    sha, before = land_branch(repo, lambda root: docs(root, "src/a.py", "src/b.py",
                                                      "src/c.py") or [
        (root / f"src/{n}.py").write_text("changed\n", encoding="utf-8") for n in "abc"])
    result = landing.land(repo, sha, before)
    rows = debug_cases(repo, sha)
    assert [r["kind"] for r in rows] == ["stale-link"] * 3 and result["cases"] == 3
    assert "3 cases went to debugging" in landing.lines(repo)[0][1]


@pytest.mark.sr("SR-296")
def test_ex4_running_again_changes_nothing(repo: Path) -> None:
    docs(repo, "docs/a.md")
    commit_all(repo, "doc")
    sha, before = land_branch(repo, decision("docs/a.md"))
    landing.land(repo, sha, before)
    after = head(repo)
    mark = landing.marker(repo, sha).read_bytes()
    assert landing.land(repo, sha, before) == {"line": "", "again": True}
    assert head(repo) == after and landing.marker(repo, sha).read_bytes() == mark


@pytest.mark.sr("SR-296")
def test_ex5_a_fast_forward_starts_the_landing(repo: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.boundary.premerge import run_post_merge

    started: list[tuple[str, str]] = []
    monkeypatch.setattr(landing, "spawn", lambda root, h, b: started.append((h, b)))
    run_git(repo, "config", "plumb.mergeHold", "false")
    sha, before = land_branch(repo, lambda root: docs(root, "x.txt"), ff=True)
    assert run_post_merge(repo) == 0
    assert started == [(sha, before)]


@pytest.mark.sr("SR-296")
def test_ex6_a_failing_step_is_a_case_and_the_rest_still_run(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import backlog

    def broken(*args: Any) -> Any:
        raise RuntimeError("tidy broke")

    queued: list[str] = []
    monkeypatch.setattr(landing, "tidy", broken)
    monkeypatch.setattr(backlog, "queue_waiting",
                        lambda core, session, **kw: queued.append(session) or backlog.Started())
    sha, before = land_branch(repo, lambda root: docs(root, "x.txt"))
    result = landing.land(repo, sha, before)
    assert queued and landing.marker(repo, sha).exists()
    rows = debug_cases(repo, sha)
    assert rows[0]["id"] == "landing:tidy" and "tidy broke" in rows[0]["detail"]
    assert result["cases"] == len(rows)


@pytest.mark.sr("SR-301")
def test_ex1_another_worktrees_loop_gate_and_cards_are_unchanged(repo: Path,
                                                                  tmp_path: Path) -> None:
    from plumb.contracts import CardState
    from plumb.understand import cardstore

    other = tmp_path / "other"
    run_git(repo, "worktree", "add", "-q", "-b", "other", str(other))
    session = other / ".plumb" / "session" / "s2"
    session.mkdir(parents=True)
    (session / "gate.json").write_text('{"state": "closed"}', encoding="utf-8")
    (session / "intent.json").write_text('{"stage": "build"}', encoding="utf-8")
    cardstore.save(other, "s2", [CardState(id="c1", branch="other"),
                                 CardState(id="c2", branch="other")])
    seen = {p: p.read_bytes() for p in session.rglob("*") if p.is_file()}
    docs(repo, "docs/a.md")
    commit_all(repo, "doc")
    sha, before = land_branch(repo, decision("docs/a.md"))
    landing.land(repo, sha, before)
    assert {p: p.read_bytes() for p in session.rglob("*") if p.is_file()} == seen


@pytest.mark.sr("SR-301")
def test_ex2_a_document_an_inflight_branch_changed_stays(repo: Path) -> None:
    docs(repo, "docs/a.md", "docs/b.md")
    commit_all(repo, "docs")
    run_git(repo, "checkout", "-q", "-b", "inflight")
    (repo / "docs" / "a.md").write_text("still working on it\n", encoding="utf-8")
    commit_all(repo, "inflight")
    run_git(repo, "checkout", "-q", "main")
    sha, before = land_branch(repo, decision("docs/a.md", "docs/b.md"))
    result = landing.land(repo, sha, before)
    assert result["removed"] == ["docs/b.md"] and (repo / "docs" / "a.md").exists()


@pytest.mark.sr("SR-301")
def test_ex3_an_inflight_branch_merges_the_compacted_main_cleanly(repo: Path) -> None:
    write_record(repo, record("SR-001", "old rule", statement="s", examples=[ex(1)]))
    first = put(repo, "waiver", {"subject": "SR-001"})
    commit_all(repo, "records")
    run_git(repo, "checkout", "-q", "-b", "inflight")
    put(repo, "waiver", {"subject": "SR-001", "n": 2}, at="2026-10-02T10:00:00Z",
        prev=first["digest"])
    commit_all(repo, "inflight work")
    run_git(repo, "checkout", "-q", "main")
    sha, before = land_branch(repo, lambda root: write_record(root, record(
        "SR-002", "new rule", statement="s", examples=[ex(1)],
        links=[{"kind": "supersedes", "to": "SR-001"}])))
    assert landing.land(repo, sha, before)["archived"] == 1
    run_git(repo, "checkout", "-q", "inflight")
    merged = run_git(repo, "merge", "-q", "--no-ff", "--no-verify", "-m", "sync", "main",
                     check=False)
    assert merged.returncode == 0, merged.stdout + merged.stderr
    assert [f.line() for f in validate(open_core(repo)) if f.severity == "error"] == []


@pytest.mark.sr("SR-301")
def test_ex1_a_worktree_named_for_the_tidy_is_never_removed(repo: Path, tmp_path: Path) -> None:
    """SR-301 EX-1: a landing's tidy list names another worktree's folder (or one holding it):
    the folder stays and the landing writes a case instead."""
    holder = tmp_path / "trees"
    other = holder / "other"
    run_git(repo, "worktree", "add", "-q", "-b", "other", str(other))
    sha, before = land_branch(repo, decision(str(holder), str(other)))
    result = landing.land(repo, sha, before)
    assert other.exists() and result["outside"] == []
    assert {r["kind"] for r in debug_cases(repo, sha)} >= {"tidy-worktree"}


@pytest.mark.sr("SR-301")
def test_ex2_a_document_changed_uncommitted_in_another_worktree_stays(
        repo: Path, tmp_path: Path) -> None:
    """SR-301 EX-2: the in-flight change is not committed yet, only edited in its worktree."""
    docs(repo, "docs/a.md", "docs/b.md")
    commit_all(repo, "docs")
    other = tmp_path / "other"
    run_git(repo, "worktree", "add", "-q", "-b", "other", str(other))
    (other / "docs" / "a.md").write_text("still working on it\n", encoding="utf-8")
    sha, before = land_branch(repo, decision("docs/a.md", "docs/b.md"))
    result = landing.land(repo, sha, before)
    assert result["removed"] == ["docs/b.md"] and (repo / "docs" / "a.md").exists()


@pytest.mark.sr("SR-301")
def test_ex1_entries_about_an_inflight_branchs_record_stay_live(repo: Path,
                                                                 tmp_path: Path) -> None:
    """SR-301 EX-1: a card entry on main names SR-050, a record only an in-flight worktree
    has: the compaction does not take it for retired; one naming no record anywhere moves."""
    put(repo, "escalation-declined", {"record": "SR-050", "reason": "asked"})
    put(repo, "escalation-declined", {"record": "SR-060", "reason": "retired: replaced"})
    commit_all(repo, "cards")
    other = tmp_path / "other"
    run_git(repo, "worktree", "add", "-q", "-b", "other", str(other))
    write_record(other, record("SR-050", "branch rule", statement="s", examples=[ex(1)]))
    sha, before = land_branch(repo, lambda root: docs(root, "docs/x.md"))
    landing.land(repo, sha, before)
    live = [json.loads(p.read_text(encoding="utf-8"))["payload"]["record"]
            for p in (repo / ".plumb" / "log" / "escalation-declined").glob("*.json")]
    assert live == ["SR-050"]


def land_worktree(repo: Path, tmp_path: Path, *, dirty: str = "", loop: bool = False,
                  merge: bool = True) -> tuple[Path, dict[str, Any]]:
    """A worktree on branch ``feat`` with one commit, merged into main (unless ``merge`` is
    false); then the landing. ``dirty`` is an untracked file written in the worktree."""
    tree = tmp_path / "wt-feat"
    before = head(repo)
    run_git(repo, "worktree", "add", "-q", "-b", "feat", str(tree))
    docs(tree, "work.md")
    commit_all(tree, "work")
    if dirty:
        docs(tree, dirty)
    if loop:
        path = repo / ".plumb" / "session" / "s9" / "intent" / "abc.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"digest": "sha256:abc", "intent": "INT-001", "note": "feat",
                                    "stages": {"clarify": {"state": "open"}}}), "utf-8")
    if merge:
        run_git(repo, "merge", "-q", "--no-ff", "--no-verify", "-m", "m", "feat")
    return tree, landing.land(repo, head(repo), before)


@pytest.mark.sr("SR-320")
def test_ex7_a_merged_clean_worktree_is_removed_and_its_branch_kept(repo: Path,
                                                                    tmp_path: Path) -> None:
    tree, result = land_worktree(repo, tmp_path, dirty=".plumb/log/x/y.json")
    assert not tree.exists() and result["worktrees"] == ["wt-feat"] and result["kept"] == []
    assert run_git(repo, "branch", "--list", "feat").stdout.strip() != ""
    assert "removed finished worktrees wt-feat" in landing.lines(repo)[0][1]


@pytest.mark.sr("SR-320")
def test_ex8_a_worktree_with_uncommitted_changes_is_kept_and_named(repo: Path,
                                                                    tmp_path: Path) -> None:
    tree, result = land_worktree(repo, tmp_path, dirty="notes.md")
    assert tree.exists() and result["worktrees"] == []
    assert "worktree wt-feat finished but kept: uncommitted changes" in landing.lines(repo)[0][1]


@pytest.mark.sr("SR-320")
def test_ex9_a_worktree_named_by_an_open_loop_is_kept_and_named(repo: Path,
                                                                 tmp_path: Path) -> None:
    tree, result = land_worktree(repo, tmp_path, loop=True)
    assert tree.exists() and result["worktrees"] == []
    assert "worktree wt-feat finished but kept: an open intent loop" in landing.lines(repo)[0][1]


@pytest.mark.sr("SR-320")
def test_ex10_an_unmerged_worktree_is_untouched_and_not_named(repo: Path,
                                                               tmp_path: Path) -> None:
    tree, result = land_worktree(repo, tmp_path, merge=False)
    assert tree.exists() and result["worktrees"] == [] and result["kept"] == []
    assert "wt-feat" not in landing.lines(repo)[0][1]
    assert run_git(repo, "branch", "--list", "feat").stdout.strip() != ""


@pytest.mark.sr("SR-320")
def test_ex12_a_worktree_kept_at_one_landing_is_removed_at_the_next(repo: Path,
                                                                    tmp_path: Path) -> None:
    tree, first = land_worktree(repo, tmp_path, dirty="notes.md")
    assert tree.exists() and first["worktrees"] == []
    (tree / "notes.md").unlink()
    run_git(repo, "commit", "-q", "--allow-empty", "--no-verify", "-m", "next")
    second = landing.land(repo, head(repo), run_git(repo, "rev-parse", "HEAD~1").stdout.strip())
    assert not tree.exists() and second["worktrees"] == ["wt-feat"]


@pytest.mark.sr("SR-320")
def test_ex13_a_fresh_worktree_with_no_commits_is_never_removed(repo: Path,
                                                                tmp_path: Path) -> None:
    tree = tmp_path / "wt-fresh"
    run_git(repo, "worktree", "add", "-q", "-b", "fresh", str(tree))
    sha, before = land_branch(repo, lambda root: docs(root, "docs/x.md"))
    result = landing.land(repo, sha, before)
    assert tree.exists() and result["worktrees"] == [] and result["kept"] == []


@pytest.mark.sr("SR-320")
def test_ex14_a_fast_forward_merged_branch_with_its_own_commit_is_removed(
        repo: Path, tmp_path: Path) -> None:
    tree = tmp_path / "wt-ff"
    before = head(repo)
    run_git(repo, "worktree", "add", "-q", "-b", "ff", str(tree))
    docs(tree, "work.md")
    commit_all(tree, "work")
    run_git(repo, "merge", "-q", "--ff-only", "--no-verify", "ff")
    result = landing.land(repo, head(repo), before)
    assert not tree.exists() and result["worktrees"] == ["wt-ff"]


@pytest.mark.sr("SR-320")
def test_ex15_a_reset_only_branch_is_kept_like_a_fresh_fork(repo: Path,
                                                            tmp_path: Path) -> None:
    tree = tmp_path / "wt-reset"
    run_git(repo, "worktree", "add", "-q", "-b", "reset", str(tree))
    sha, before = land_branch(repo, lambda root: docs(root, "docs/x.md"))
    run_git(tree, "reset", "-q", "--hard", sha)  # a reflog entry that is no commit
    result = landing.land(repo, sha, before)
    assert tree.exists() and result["worktrees"] == [] and result["kept"] == []


@pytest.mark.sr("SR-296")
def test_ex11_a_second_landing_run_queues_no_judge_job_twice(repo: Path, write_record,
                                                              engine_standins) -> None:
    from plumb.understand import backlog, files

    bulk(repo, write_record, {"alpha": 3})
    sha, before = land_branch(repo, lambda root: None)
    landing.land(repo, sha, before, session=SESSION)
    jobs = sorted(files.jobs_dir(repo, SESSION).glob("*.json"))
    landing.marker(repo, sha).unlink()  # the marker lost: the run happens again
    result = landing.land(repo, sha, before, session=SESSION)
    assert result["queued"] == 0 and backlog.waiting(open_core(repo), SESSION) == []
    assert sorted(files.jobs_dir(repo, SESSION).glob("*.json")) == jobs


@pytest.mark.sr("SR-296")
def test_a_helper_or_tsx_file_linked_as_a_test_is_no_unrun_case(repo: Path) -> None:
    from mergedriver.mdhelpers import link

    write_record(repo, record("SR-001", "rule", statement="s", examples=[ex(1)], links=[
        link("verified_by", path="tests/helper.py"),
        link("verified_by", path="tests/plugin/a.test.tsx"),
        link("verified_by", path="tests/test_real.py")]))
    for name in ("helper.py", "plugin/a.test.tsx", "test_real.py"):
        docs(repo, f"tests/{name}")
    commit_all(repo, "linked")
    cases = landing.status_cases(open_core(repo), "", "")
    assert {c["target"] for c in cases if c["kind"] == "unrun-test"} <= {"tests/test_real.py"}


@pytest.mark.sr("SR-338")
def test_ex2_ended_session_folders_go_unmarked_ones_stay(repo: Path) -> None:
    sessions = repo / ".plumb" / "session"
    for name in ("ended", "live"):
        (sessions / name).mkdir(parents=True)
        (sessions / name / "gate").write_text("{}", encoding="utf-8")
    (sessions / "ended" / "ended.json").write_text("{}", encoding="utf-8")
    sha, before = land_branch(repo, lambda root: docs(root, "x.txt"))
    result = landing.land(repo, sha, before)
    assert result["sessions"] == ["ended"]
    assert not (sessions / "ended").exists() and (sessions / "live" / "gate").exists()
    assert "removed 1 ended session folders" in result["line"]


@pytest.mark.sr("SR-338")
def test_ex3_the_landings_own_session_folder_stays(repo: Path) -> None:
    own = repo / ".plumb" / "session" / "s-own"
    own.mkdir(parents=True)
    (own / "ended.json").write_text("{}", encoding="utf-8")
    assert landing.ended_sessions(repo, "s-own") == [] and own.is_dir()


@pytest.mark.sr("SR-340")
def test_ex3_an_ended_session_folder_holding_a_waiting_question_stays(repo: Path) -> None:
    sessions = repo / ".plumb" / "session"
    for name in ("asked", "done"):
        (sessions / name).mkdir(parents=True)
        (sessions / name / "ended.json").write_text("{}", encoding="utf-8")
    (sessions / "asked" / "cards.json").write_text(json.dumps({"cards": [
        {"id": "choice:abc", "kind": "choice", "topic": "t", "issue": "which?",
         "status": "open"}]}), encoding="utf-8")
    assert landing.ended_sessions(repo, "s-own") == ["done"]
    assert (sessions / "asked" / "cards.json").exists() and not (sessions / "done").exists()
