"""D7: the merge boundary holds intent conflicts; the quick merge check at git's
pre-merge-commit (sp6 10, R17)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from mergedriver.mdhelpers import (
    THEIRS_STATEMENT,
    commit_all,
    conflicted,
    events,
    ex,
    install_driver,
    make_repo,
    plumb,
    record,
    run_git,
    write_record,
)
from plumb import cli
from plumb.api import open_core
from plumb.boundary.premerge import HOOK_MARKER, check, install_hook, uninstall_hook

FOREIGN = "#!/bin/sh\necho foreign\n"


def _hook(root: Path) -> Path:
    return root / ".git" / "hooks" / "pre-merge-commit"


def _diverged(tmp_path: Path, *, theirs_statement: str = THEIRS_STATEMENT,
              approve_theirs: bool = False) -> tuple[Path, Path]:
    """main and feat-x both changed SR-005's statement; the driver and the hook installed."""
    root = make_repo(tmp_path / "main")
    install_driver(root)
    install_hook(root, sys.executable)
    write_record(root, record(statement="A relay pins every stated record.", examples=[ex(1)]))
    commit_all(root, "SR-005")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    write_record(root, record(statement="A relay pins only what the owner affirms.",
                              examples=[ex(1)]))
    commit_all(root, "ours")
    write_record(other, record(statement=theirs_statement, examples=[ex(1)]))
    if approve_theirs:
        from plumb.approvals import approve

        approve(open_core(other), ["SR-005"])
    commit_all(other, "theirs\n\nSR: SR-005")
    return root, other


@pytest.mark.sr("SR-077")
@pytest.mark.parametrize("argv", [["check", "--merge", "main"],
                                  ["merge-check", "main", "--no-run"]])
def test_merge_check_exits_4_with_card(repo: Path, argv: list[str]) -> None:
    """SR-077 EX-1: a merge result with IC-001 open: exit 4 and the card."""
    conflicted(repo, theirs=record(statement=THEIRS_STATEMENT, examples=[ex(1)]))
    out = plumb(repo, *argv)
    assert out.returncode == 4, out.stdout + out.stderr
    assert "intent conflicts wait for your choice (/plumb conflicts):" in out.stdout
    assert "Conflict  IC-001 on SR-005" in out.stdout
    data = json.loads(plumb(repo, *argv, "--json").stdout)
    data = data.get("merge", data)  # check --merge --json: {validate, merge}
    assert data["intent_conflicts"][0]["ic"] == "IC-001"


@pytest.mark.sr("SR-077")
def test_hook_refuses_merge_commit_on_ic(tmp_path: Path) -> None:
    """SR-077 EX-2: git does not record the merge commit; the output names /plumb conflicts."""
    root, _ = _diverged(tmp_path)
    head = run_git(root, "rev-parse", "HEAD").stdout
    merged = run_git(root, "merge", "--no-edit", "feat-x", check=False)
    output = merged.stdout + merged.stderr
    assert merged.returncode != 0
    assert run_git(root, "rev-parse", "HEAD").stdout == head
    assert run_git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").stdout.strip()
    assert "/plumb conflicts" in output and "finish the merge" in output
    assert "no test run" in output


@pytest.mark.sr("SR-077")
def test_commit_completes_after_choice(tmp_path: Path) -> None:
    """SR-077 EX-6: the owner's choice settles the held merge; it can be finished."""
    root, _ = _diverged(tmp_path, approve_theirs=True)
    run_git(root, "merge", "--no-edit", "feat-x", check=False)
    assert cli.main(["conflict", "choose", "IC-001", "--take", "feat-x",
                     "--root", str(root)]) == 0
    run_git(root, "add", "-A")
    report = check(open_core(root))
    assert report.exit == 0, report.lines
    run_git(root, "commit", "-q", "-m", "Merge branch feat-x")
    assert not run_git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD",
                       check=False).stdout.strip()


@pytest.mark.sr("SR-077")
def test_quick_check_holds_unconfirmed_and_undeclared(tmp_path: Path) -> None:
    """R17: no intent conflict, but the incoming change touches an unconfirmed requirement
    and a file no requirement declares: held, without a test run."""
    root = make_repo(tmp_path / "main")
    install_hook(root, sys.executable)
    write_record(root, record(statement="s", examples=[ex(1)]))
    commit_all(root, "SR-005")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    (root / "notes.txt").write_text("main\n", encoding="utf-8")
    commit_all(root, "main side")
    (other / "src").mkdir()
    (other / "src" / "relay.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(other, "relay\n\nSR: SR-005")
    merged = run_git(root, "merge", "--no-edit", "feat-x", check=False)
    output = merged.stdout + merged.stderr
    assert merged.returncode != 0
    assert 'SR-005 "relay checks" is not confirmed yet' in output
    assert "src/relay.py changed without a requirement that declares it" in output


@pytest.mark.sr("SR-077")
def test_quick_check_runs_no_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-077 EX-4 (R17): the merge-time check never starts the test suite (that runs once,
    at push)."""
    import plumb.boundary.fullrun as fullrun
    import plumb.verify as verify

    def boom(*_a, **_k):
        raise AssertionError("the quick merge check started a test run")

    monkeypatch.setattr(fullrun, "full_run", boom)
    monkeypatch.setattr(verify, "open_verify", boom)
    root, _ = _diverged(tmp_path)
    run_git(root, "merge", "--no-edit", "--no-verify", "--no-commit", "feat-x", check=False)
    report = check(open_core(root))
    assert report.exit == 4 and report.intent_conflicts


@pytest.mark.sr("SR-077")
def test_foreign_hook_untouched(repo: Path, capsys) -> None:
    """SR-077 EX-3: the foreign hook is untouched; the output says how to call plumb."""
    _hook(repo).parent.mkdir(parents=True, exist_ok=True)
    _hook(repo).write_text(FOREIGN, encoding="utf-8")
    assert cli.main(["merge-check", "--install-pre-merge-commit", "--root", str(repo)]) == 1
    assert "call plumb from my merge hook" in capsys.readouterr().out
    assert cli.main(["merge-check", "--install-pre-merge-commit", "--json",
                     "--root", str(repo)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["foreign"] is True
    assert data["hook_line"].endswith("-m plumb merge-check --hook pre-merge-commit || exit $?")
    assert _hook(repo).read_text(encoding="utf-8") == FOREIGN
    assert cli.main(["hooks", "install", "--root", str(repo), "--launcher", "uv"]) == 0
    assert _hook(repo).read_text(encoding="utf-8") == FOREIGN


@pytest.mark.sr("SR-077")
def test_uninstall_removes_only_plumb_hook(repo: Path) -> None:
    _hook(repo).parent.mkdir(parents=True, exist_ok=True)
    _hook(repo).write_text(FOREIGN, encoding="utf-8")
    assert uninstall_hook(repo) is False
    assert _hook(repo).read_text(encoding="utf-8") == FOREIGN
    _hook(repo).unlink()
    assert cli.main(["merge-check", "--install-pre-merge-commit", "--root", str(repo)]) == 0
    assert HOOK_MARKER in _hook(repo).read_text(encoding="utf-8")
    assert cli.main(["merge-check", "--uninstall-pre-merge-commit", "--root", str(repo)]) == 0
    assert not _hook(repo).exists()


@pytest.mark.sr("SR-077")
def test_hooks_install_and_init_install_the_quick_check(repo: Path, tmp_path: Path) -> None:
    """SR-077 EX-5 (R17): /plumb init and hooks install set up the quick merge check AND the
    pre-push hook (the one full run) by default: the merge runs no tests because push does."""
    from plumb.boundary.prepush import HOOK_MARKER as PUSH_MARKER

    push = repo / ".git" / "hooks" / "pre-push"
    assert cli.main(["hooks", "install", "--root", str(repo), "--launcher", "uv"]) == 0
    text = _hook(repo).read_text(encoding="utf-8")
    assert HOOK_MARKER in text and "merge-check --hook pre-merge-commit" in text
    pushed = push.read_text(encoding="utf-8")
    assert PUSH_MARKER in pushed and "merge-check --hook pre-push" in pushed
    other = tmp_path / "fresh"
    other.mkdir()
    run_git(other, "init", "-q", "-b", "main")
    assert cli.main(["init", "--root", str(other)]) == 0
    assert HOOK_MARKER in _hook(other).read_text(encoding="utf-8")
    assert PUSH_MARKER in (other / ".git" / "hooks" / "pre-push").read_text(encoding="utf-8")
    assert cli.main(["hooks", "uninstall", "--root", str(repo)]) == 0
    assert not _hook(repo).exists() and not push.exists()


@pytest.mark.sr("SR-077")
@pytest.mark.parametrize("argv", [["hooks", "install"], ["init"]])
def test_adoption_keeps_a_foreign_pre_push_hook(repo: Path, argv: list[str],
                                                capsys: pytest.CaptureFixture) -> None:
    """A pre-push hook plumb did not write is left byte-identical and named in plain words;
    the quick merge check is still installed."""
    push = repo / ".git" / "hooks" / "pre-push"
    push.parent.mkdir(parents=True, exist_ok=True)
    push.write_text(FOREIGN, encoding="utf-8")
    assert cli.main([*argv, "--root", str(repo)]) == 0
    assert push.read_text(encoding="utf-8") == FOREIGN
    assert HOOK_MARKER in _hook(repo).read_text(encoding="utf-8")
    assert "your own pre-push hook was kept" in capsys.readouterr().out


class _CountingJev:
    """A configured non-heuristic backend that counts its calls."""

    name = "jev"
    version = "jev-test-1"

    def __init__(self) -> None:
        self.calls = 0

    def contradiction(self, prompt: str, rec: object):
        from plumb.contracts import Judgment

        self.calls += 1
        return Judgment(action="intent_change", subject="SR-005", verdict="benign",
                        confidence=0.8, tier="accept", backend="jev:test", fingerprint="f",
                        reasons=("both can hold",), probability=0.82)


def _jev_configured(monkeypatch: pytest.MonkeyPatch) -> _CountingJev:
    import plumb.judgment as judgment

    backend = _CountingJev()
    monkeypatch.setattr(judgment, "get_backend", lambda core, hook: backend)
    return backend


@pytest.mark.sr("SR-077")
def test_quick_check_never_calls_a_judgment_backend(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R17 CHEAP: with JEV configured, the pre-merge-commit check shows the card without a
    backend call and writes nothing to the log."""
    import plumb.boundary.premerge as premerge

    backend = _jev_configured(monkeypatch)
    conflicted(repo)
    head = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    monkeypatch.setattr(premerge, "incoming_heads", lambda root: [(head, "feat-x")])
    report = check(open_core(repo))
    assert report.exit == 4 and report.intent_conflicts
    assert backend.calls == 0
    assert "  Compatible? no judgment available" in report.intent_conflicts[0]["card"]
    assert [p for p in events(repo, "judgment") if p.get("subject") == "IC-001"] == []


@pytest.mark.sr("SR-077")
def test_pre_push_hook_never_calls_a_judgment_backend(
        repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    """The pre-push hook's report shows conflict cards from logged judgments only; the
    owner's /plumb merge-check still judges live."""
    import io

    from plumb.boundary import merge_report
    from plumb.boundary.cli import _hook_pre_push

    backend = _jev_configured(monkeypatch)
    conflicted(repo)
    head = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        f"refs/heads/main {head} refs/heads/main {'0' * 40}\n"))
    assert _hook_pre_push(open_core(repo), False) != 0
    out = capsys.readouterr().out
    assert "Conflict  IC-001 on SR-005" in out and "Compatible? no judgment available" in out
    assert backend.calls == 0
    assert [p for p in events(repo, "judgment") if p.get("subject") == "IC-001"] == []
    merge_report(open_core(repo), head, run_full=False)  # interactive: live
    assert backend.calls == 1
