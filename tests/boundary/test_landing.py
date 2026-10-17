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

    monkeypatch.setattr(backlog, "queue_waiting", lambda core, session: backlog.Started())
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
                        lambda core, session: queued.append(session) or backlog.Started())
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
    first = put(repo, "judgment", {"subject": "SR-001"})
    commit_all(repo, "records")
    run_git(repo, "checkout", "-q", "-b", "inflight")
    put(repo, "judgment", {"subject": "SR-001", "n": 2}, at="2026-10-02T10:00:00Z",
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
