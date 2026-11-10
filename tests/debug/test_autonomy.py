"""SR-343 (DEC-316..DEC-319): iaso's own defects found at a landing go to the background
self-debug job; a committed, reviewed self-fix is named ready to land; the session that hit the
defect is told once the fix is in main; anyone flags a wrong result with one command. Git is
real; the landing's judge backlog is stubbed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from boundary.test_landing import debug_cases, docs, land_branch
from mergedriver.mdhelpers import commit_all, run_git
from iaso import debug
from iaso.boundary import landing
from iaso.understand import files

pytestmark = pytest.mark.sr("SR-343")


@pytest.fixture
def own(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """iaso's own repository shape, a session that detects, and no judge backlog."""
    from iaso.understand import backlog

    (repo / "pyproject.toml").write_text('[project]\nname = "iaso"\n', "utf-8")
    (repo / "src" / "iaso").mkdir(parents=True)
    (repo / "src" / "iaso" / "__init__.py").write_text("", "utf-8")
    commit_all(repo, "iaso-shaped")
    monkeypatch.setenv("IASO_SESSION_ID", "s1")
    monkeypatch.setattr(backlog, "queue_waiting", lambda core, session, **kw: backlog.Started())
    return repo


def _queued(root: Path, session: str) -> list[str]:
    return sorted(p.name for p in files.jobs_dir(root, session).glob("selfdebug*"))


def test_dec316_a_landings_own_defects_go_to_the_background_the_rest_stay(
        own: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: Any) -> Any:
        raise RuntimeError("tidy broke")

    monkeypatch.setattr(landing, "tidy", broken)
    monkeypatch.setattr(landing, "status_cases", lambda core, session, line: [
        {"id": "validate:E1:SR-001", "kind": "validate", "target": "SR-001", "detail": "bad"},
        {"id": "stale:SR-001#0", "kind": "stale-link", "target": "SR-001#0", "detail": "link"},
        {"id": "judge:SR-002", "kind": "judge-waiting", "target": "SR-002", "detail": "no key"}])
    sha, before = land_branch(own, lambda root: docs(root, "x.txt"))
    result = landing.land(own, sha, before)
    assert {r["kind"] for r in debug_cases(own, sha)} == {"stale-link", "judge-waiting"}
    rows = {r["kind"]: r for r in debug.open_cases(own)}
    assert set(rows) == {"landing-step", "validate"} and result["cases"] == 4
    assert "tidy broke" in rows["landing-step"]["detail"] and rows["validate"]["session"] == "s1"
    assert len(_queued(own, "s1")) == 2


def test_dec316_elsewhere_a_landings_cases_all_stay_with_the_agent(repo: Path) -> None:
    found = [{"id": "landing:tidy", "kind": "landing-step", "target": "tidy", "detail": "x"}]
    assert debug.from_landing(repo, found) == found and debug.open_cases(repo) == []


def _fixed_branch(root: Path, case: str = "hook-stop-1") -> str:
    """A self-fix as ``selfdebug.fix`` leaves it: a committed branch, the case resolved."""
    debug.open_case(root, id=case, kind="hook-error", target="stop", detail="ValueError: x")
    run_git(root, "checkout", "-q", "-b", "debug/hook-stop-1")
    docs(root, "src/iaso/fixed.py")
    commit_all(root, "fix")
    run_git(root, "checkout", "-q", "main")
    debug._update(root, [case], branch="debug/hook-stop-1")
    debug.resolve(root, [case])
    return "debug/hook-stop-1"


def test_dec317_a_committed_reviewed_self_fix_is_named_ready_to_land(own: Path) -> None:
    branch = _fixed_branch(own)
    ((key, text),) = debug.lines(own, "another session")
    assert key == "ready:hook-stop-1" and branch in text and "ready to land" in text
    assert "merge check" in text
    assert run_git(own, "rev-list", "--count", f"main..{branch}").stdout.strip() == "1"


def test_dec318_once_the_fix_is_in_main_the_detecting_session_is_told_what_to_retry(
        own: Path) -> None:
    branch = _fixed_branch(own)
    assert [k for k, _ in debug.lines(own, "s1")] == ["ready:hook-stop-1"]
    before = run_git(own, "rev-parse", "HEAD").stdout.strip()
    run_git(own, "merge", "-q", "--no-ff", "--no-verify", "-m", "land", branch)
    landing.land(own, run_git(own, "rev-parse", "HEAD").stdout.strip(), before)
    ((key, text),) = debug.lines(own, "s1")
    assert key == "fixed:hook-stop-1" and "fixed in main" in text
    assert "retry what ran the stop hook" in text
    assert debug.lines(own, "s2") == []


def test_dec319_anyone_flags_a_wrong_result_with_one_command(own: Path, capsys) -> None:
    words = ["iaso", "status", "counts", "a", "confirmed", "record", "as", "proposed"]
    assert debug.run("debug", ["--root", str(own), "report", *words]) == 0
    (row,) = debug.open_cases(own)
    assert row["kind"] == "report" and row["detail"] == " ".join(words)
    assert row["session"] == "s1" and row["id"] in capsys.readouterr().out
    assert len(_queued(own, "s1")) == 1
    assert debug.run("debug", ["--root", str(own), "report"]) == 2


def test_dec317_dec318_the_lines_reach_the_agent_at_its_next_prompt(repo: Path) -> None:
    from hosts.hosts_helpers import QuietVerify

    from iaso.contracts import TurnEvent
    from iaso.hosts.neutral import handle_event

    debug.open_case(repo, id="a", kind="report", target="flagged", detail="wrong count",
                    session="s1")
    debug.open_case(repo, id="b", kind="hook-error", target="stop", detail="boom", session="s1")
    debug._update(repo, ["a"], branch="debug/a", state="resolved")
    debug._update(repo, ["b"], branch="debug/b", state="resolved", landed="abc")

    def prompt() -> str:
        return "\n".join(handle_event(TurnEvent(kind="prompt", root=repo, session_id="s1",
                                                host="claude-code", text="hello"),
                                      verify=QuietVerify(), backend=None,
                                      unjudged=None).agent_context)

    first = prompt()
    assert "debug/a" in first and "ready to land" in first
    assert "fixed in main (hook-error: boom); retry what ran the stop hook" in first
    assert "debug/a" not in prompt()
