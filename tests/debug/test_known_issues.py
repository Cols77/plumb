"""SR-356, SR-357: a debug case is fixed only once proven where it hurt, a recurrence reopens
the old case with its history, and the register of known issues reaches every session, gated
on the plugin build Claude Code runs (its MANIFEST against main's)."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from hosts.hosts_helpers import QuietVerify

from plumb import build, debug
from plumb.hosts.claude_code import session_start

REGISTER = Path(__file__).resolve().parents[2] / ".plumb" / "known-issues.json"
CASE = "field-answers-dropped-after-upgrade"


@pytest.fixture
def plugin(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """``plugin(same)``: Claude Code runs a plugin whose build is main's (or an older one)."""
    vendor = repo / "plugin" / "vendor"
    vendor.mkdir(parents=True)
    (vendor / "plumb.whl").write_bytes(b"wheel")
    (vendor / "MANIFEST.json").write_text(json.dumps({"wheel": "plumb.whl",
                                                       "source_digest": "main"}), "utf-8")
    for args in (("add", "-A"), ("commit", "-q", "-m", "main's build")):  # main's committed build
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    monkeypatch.setenv("PLUMB_SESSION_ID", "s2")
    for name in ("CLAUDE_PLUGIN_ROOT", "PLUMB_PLUGIN_ROOT"):
        monkeypatch.delenv(name, raising=False)

    def run(same: bool) -> None:
        loaded = tmp_path / "cache" / "plumb" / "vendor"
        loaded.mkdir(parents=True, exist_ok=True)
        (loaded / "MANIFEST.json").write_text(json.dumps(
            {"source_digest": "main" if same else "old"}), "utf-8")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(loaded.parent))
    return run


@pytest.fixture
def register(repo: Path) -> Path:
    shutil.copy(REGISTER, repo / ".plumb" / "known-issues.json")
    return repo


def _report(repo: Path, words: str, capsys) -> str:
    capsys.readouterr()
    assert debug.run("debug", ["--root", str(repo), "report", *words.split()]) == 0
    return capsys.readouterr().out


def test_the_build_is_outdated_only_when_the_loaded_plugin_differs_from_main(
        repo: Path, plugin) -> None:
    assert build.outdated(repo) == (False, "")      # no plugin runs this process
    plugin(True)
    assert build.outdated(repo) == (False, "")
    plugin(False)
    late, built = build.outdated(repo)
    assert late and built[:4].isdigit()


@pytest.mark.sr("SR-356")
def test_ex1_a_landed_fix_on_the_old_cached_plugin_reads_landed_not_proven(
        repo: Path, plugin, capsys) -> None:
    plugin(False)
    debug.open_case(repo, id=CASE, kind="report", target="flagged",
                    detail="answers dropped after the upgrade", session="s2")
    debug._update(repo, [CASE], branch="debug/x", state="resolved", landed="a15e6bbcd")
    assert debug.run("debug", ["--root", str(repo), "done", CASE]) == 1
    assert "stays landed, not proven" in capsys.readouterr().out
    (row,) = debug.all_cases(repo)
    assert debug.state(row) == debug.LANDED and "proven" not in row
    ((key, text),) = debug.lines(repo, "s2")
    assert key == f"reload:{CASE}" and "reload plugins" in text
    debug.run("debug", ["--root", str(repo)])
    assert f"{CASE}: landed, not proven" in capsys.readouterr().out
    plugin(True)   # reloaded: checked live in a session running main's build
    assert debug.run("debug", ["--root", str(repo), "done", CASE]) == 0
    assert debug.state(debug.all_cases(repo)[0]) == "resolved"


@pytest.mark.sr("SR-356")
def test_ex1_done_from_a_plain_bash_reads_the_plugin_the_session_started_with(
        repo: Path, plugin, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """The agent's Bash has no plugin variable: the session's host.json names the plugin."""
    plugin(False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT")
    host = repo / ".plumb" / "session" / "s2" / "host.json"
    host.parent.mkdir(parents=True, exist_ok=True)
    host.write_text(json.dumps({"plugin": str(tmp_path / "cache" / "plumb")}), "utf-8")
    debug.open_case(repo, id=CASE, kind="report", target="flagged",
                    detail="answers dropped after the upgrade", session="s2")
    debug._update(repo, [CASE], branch="debug/x", state="resolved", landed="a15e6bbcd")
    assert debug.run("debug", ["--root", str(repo), "done", CASE]) == 1
    assert "stays landed, not proven" in capsys.readouterr().out


@pytest.mark.sr("SR-356")
def test_ex2_a_proven_case_seen_again_reopens_with_its_history(repo: Path, plugin) -> None:
    plugin(True)
    debug.hook_error(repo, "stop", 'File "a.py", in answer\nKeyError: \'answer\'')
    (first,) = debug.open_cases(repo)
    debug._update(repo, [first["id"]], state="resolved", branch="debug/x", landed="abc",
                  proven="2026-10-20")
    # a later session, another traceback with the same symptom: matched by symptom, not name
    debug.hook_error(repo, "stop", 'File "b.py", in record\nKeyError: \'answer\'')
    (row,) = debug.open_cases(repo)
    assert row["id"] == first["id"] and row["came_back"] == "s2"
    assert row["history"] == [{"state": "resolved", "landed": "abc", "proven": "2026-10-20",
                               "session": first["session"], "detail": "KeyError: 'answer'"}]
    ((key, text),) = debug.lines(repo, "s2")
    assert key.startswith("back:") and "came back" in text and "history" in text


@pytest.mark.sr("SR-357")
def test_ex1_a_fresh_session_is_told_the_open_known_issue(register: Path, hook_input,
                                                         monkeypatch) -> None:
    monkeypatch.setattr(session_start, "hook_budget", lambda name: (lambda root: 4000.0))
    out = io.StringIO()
    assert session_start.main(stdin=io.StringIO(hook_input("SessionStart", source="startup")),
                              stdout=out, root=register, verify=QuietVerify()) == 0
    said = [line for line in out.getvalue().splitlines() if "known issues" in line]
    assert said[0].startswith("plumb: known issues open: KI-4 judge line shown while the "
                              "judge answered") and len(said) <= 2


@pytest.mark.sr("SR-357")
def test_ex2_on_an_older_plugin_a_fixed_issue_says_reload_and_reopens_nothing(
        register: Path, plugin, capsys) -> None:
    plugin(False)
    out = _report(register, "plumb re-asks the answered questions", capsys)
    assert "fixed in main, reload plugins" in out
    assert debug.open_cases(register) == []


@pytest.mark.sr("SR-357")
def test_ex3_on_mains_build_a_fixed_issue_seen_again_reopens_it(register: Path, plugin,
                                                                 capsys) -> None:
    plugin(True)
    out = _report(register, "plumb re-asks the answered questions", capsys)
    (row,) = debug.open_cases(register)
    assert row["id"] == "KI-5" and row["history"] == [{"state": "fixed",
                                                       "landed": "3a1d16d2f"}]
    assert "KI-5 came back" in out
    assert "KI-5" in debug.known_lines(register)[0]   # open again at the next session start


@pytest.mark.sr("SR-367")
def test_ex4_the_session_owning_a_case_is_told_when_it_is_proven(repo: Path, plugin) -> None:
    plugin(True)
    debug.open_case(repo, id=CASE, kind="report", target="flagged",
                    detail="answers dropped after the upgrade", session="s1")
    debug._update(repo, [CASE], branch="debug/x", state="resolved", landed="abc",
                  proven="2026-10-25")
    ((key, text),) = debug.lines(repo, "s1")
    assert key == f"proven:{CASE}" and "proven fixed" in text
    assert debug.lines(repo, "s3") == []


@pytest.mark.sr("SR-367")
def test_ex4_the_owning_session_is_told_its_problem_came_back_elsewhere(
        repo: Path, plugin, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin(True)
    monkeypatch.setenv("PLUMB_SESSION_ID", "s1")
    debug.hook_error(repo, "stop", 'File "a.py", in answer\nKeyError: \'answer\'')
    (first,) = debug.open_cases(repo)
    debug._update(repo, [first["id"]], state="resolved", branch="debug/x", landed="abc",
                  proven="2026-10-20")
    assert first["session"] == "s1"
    monkeypatch.setenv("PLUMB_SESSION_ID", "s2")
    debug.hook_error(repo, "stop", 'File "b.py", in record\nKeyError: \'answer\'')
    ((key, text),) = debug.lines(repo, "s1")
    assert key.startswith("back:") and "came back in another session" in text
    assert debug.lines(repo, "s3") == []
