"""SR-394: an idle intent loop opens in a new session and window, on the owner's press or the
owner's words to an agent; never otherwise. No test opens a window: the opener runs with a
fake program finder and a fake spawn."""

from __future__ import annotations

import functools
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from mod.helpers import DIGEST, KEY, run_mod
from present.present_helpers import run_prompt

from plumb import cli
from plumb.api import open_core
from plumb.approvals import prompt_origin
from plumb.awareness import inflight
from plumb.hosts.common import MARKER_NAME
from plumb.understand import cmd_intent, files, gate, loops, recover

from awareness.gitrepo import commit_all
from capture.capture_helpers import log_prompt
from conftest import git
from understand.test_judge_job import intent_text, requirement_text
from understand.test_loops import _loop, _passed, _worktree

pytestmark = pytest.mark.sr("SR-394")

REAL_LAUNCH = loops.launch          # the conftest replaces the module's; this is the real one
ID = "aaaaaaaaaaaa"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
ASKER = "sender"


class Windows:
    """The machine's windows, faked: ``calls`` holds each (argv, spawn keywords)."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def spawn(self, argv: list[str], **kwargs: Any) -> None:
        self.calls.append((argv, kwargs))

    def command(self, n: int = -1) -> list[str]:
        argv = self.calls[n][0]
        return argv[argv.index("--") + 1:]


@pytest.fixture
def window(monkeypatch: pytest.MonkeyPatch) -> Windows:
    windows = Windows()
    monkeypatch.setattr(loops, "launch", functools.partial(
        REAL_LAUNCH, which=lambda p: "/usr/bin/gnome-terminal" if p == "gnome-terminal" else None,
        spawn=windows.spawn, env={"DISPLAY": ":0", "PATH": "/usr/bin"}, platform="linux"))
    return windows


def _commit_records(repo: Path, write_record: Any) -> None:
    write_record(repo, intent_text(1, "q", "Builds the card-store."))
    write_record(repo, requirement_text(1, "Colours show", "Colours show.", intent=1))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "records")


def _idle_build(root: Path, **fields: Any) -> Path:
    return _loop(root, "gone", DIGEST_A, intent="INT-001", stages=_passed("clarify", "plan"),
                 tasks={"label": "building", "done": 3, "total": 4,
                        "left": ["the colours slice"]}, **fields)


def _ask(repo: Path, words: str, at: str = "2026-10-06T10:00:00Z", session: str = ASKER) -> None:
    log_prompt(repo, words, at=at, session=session)


def _reopen(root: Path, *argv: str, session: str = ASKER) -> int:
    return cli.main(["loops", "reopen", *argv, "--session", session, "--root", str(root)])


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.as_posix(): p.read_bytes() for p in (root / ".plumb" / "session").rglob("*.json")}


def test_ex1_reopen_starts_a_named_session_on_the_branch_with_the_brief(
        repo: Path, tmp_path: Path, write_record: Any, window: Windows) -> None:
    _commit_records(repo, write_record)
    wt = _worktree(repo, tmp_path)
    plan = tmp_path / "plan.md"
    plan.write_text("the plan\n", encoding="utf-8")
    _idle_build(wt, files=[str(plan), str(tmp_path / "gone.md")])
    assert loops.reopen(repo, loop=ID)["opened"] is True
    (argv, kwargs), = window.calls
    command = window.command()
    assert kwargs["cwd"] == str(wt) and kwargs["start_new_session"] is True
    assert Path(command[0]).name == "claude" and command[1] == "--session-id" and command[3] == "-n"
    assert command[4] == "plumb: Builds the card-store."
    brief = command[-1]
    assert brief.startswith("<plumb-loop-brief>")
    assert f"plumb intent adopt --from-session gone --digest {ID} --session {command[2]}" in brief
    for part in ("Builds the card-store.", "build · 3/4", "the colours slice", "INT-001",
                 "Colours show", str(plan), "Branch: intent/wt"):
        assert part in brief
    assert "gone.md" not in brief


def test_ex2_after_the_new_session_adopts_the_loop_is_live_there_and_the_old_copy_handed_over(
        repo: Path, tmp_path: Path, write_record: Any, window: Windows) -> None:
    _commit_records(repo, write_record)
    wt = _worktree(repo, tmp_path)
    old = _idle_build(wt)
    loops.reopen(repo, loop=ID)
    new = window.command()[2]
    assert cmd_intent.run("intent", ["adopt", "--root", str(wt), "--from-session", "gone",
                                     "--digest", ID, "--session", new]) == 0
    rows = loops.listing(repo, agents={new: {"status": "busy"}})["rows"]
    assert [(r["session"], r["live"]) for r in rows] == [(new, True)]
    assert files.read_json(old)["handed_to"]["session"] == new


def test_ex3_listing_seven_idle_loops_opens_nothing(
        repo: Path, tmp_path: Path, window: Windows) -> None:
    for n in range(7):
        _loop(repo, f"gone{n}", "sha256:" + f"{n}" * 64)
    assert len(loops.listing(repo, agents={})["rows"]) == 7
    assert cli.main(["loops", "--root", str(repo)]) == 0
    assert window.calls == []


def test_ex4_a_live_loop_is_not_offered_and_reopen_is_refused(
        repo: Path, monkeypatch: pytest.MonkeyPatch, window: Windows,
        capsys: pytest.CaptureFixture) -> None:
    _loop(repo, "busy", DIGEST_A)
    live = {"busy": {"status": "busy", "cwd": ""}}
    monkeypatch.setattr(loops, "claude_sessions", lambda: live)
    assert loops.listing(repo)["rows"][0]["reopen"] is False
    _ask(repo, f"reopen loop {ID}")
    assert _reopen(repo, "--loop", ID) == 1
    assert "a session works on this loop" in capsys.readouterr().err
    assert window.calls == []


def test_ex5_a_main_checkout_loop_gets_a_new_worktree(
        repo: Path, write_record: Any, window: Windows) -> None:
    _commit_records(repo, write_record)
    _idle_build(repo)
    loops.reopen(repo, loop=ID)
    path = repo / ".plumb" / "wt" / "intent-int-001"
    assert path.is_dir() and window.calls[0][1]["cwd"] == str(path)
    assert git(path, "branch", "--show-current").strip() == "intent/int-001"
    assert git(repo, "branch", "--show-current").strip() == "main"


def test_ex6_the_agents_command_opens_the_same_session_as_the_pane(
        repo: Path, tmp_path: Path, write_record: Any, window: Windows,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    _commit_records(repo, write_record)
    wt = _worktree(repo, tmp_path, "card-store")
    _idle_build(wt)
    _ask(repo, "reopen the card-store loop")           # logged in main; the agent runs in wt
    assert _reopen(wt, "card-store") == 0
    (wt / ".plumb" / "session" / "gone" / loops.PENDING).unlink()      # the first window's adopt
    assert run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, answer, _ = run_mod(monkeypatch, capsys, repo, "reopen", "--loop", ID,
                              stdin={"key": KEY})
    assert code == 0 and answer["opened"] is True
    (first, _), (second, _) = window.calls

    def same(argv: list[str]) -> list[str]:        # without the new session's id and its brief
        command = argv[argv.index("--") + 1:]
        return [*command[:2], *command[3:-1]]

    assert same(first) == same(second) and first[:first.index("--")] == second[:second.index("--")]
    assert window.command(0)[2] != window.command(1)[2]


def test_ex7_no_window_gives_the_command_and_changes_nothing(
        repo: Path, write_record: Any, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    _commit_records(repo, write_record)
    path = _idle_build(repo)
    monkeypatch.setattr(loops, "launch", functools.partial(
        REAL_LAUNCH, which=lambda p: "/usr/bin/xterm", spawn=None, env={"PATH": "/usr/bin"},
        platform="linux"))
    before = (path.read_bytes(), _snapshot(repo))
    _ask(repo, f"reopen loop {ID}")
    assert _reopen(repo, "--loop", ID) == 1
    out = capsys.readouterr().out
    assert "no terminal window could be opened here" in out
    assert "claude --session-id" in out and "-n 'plumb: Builds the card-store.'" in out
    assert "git worktree add" in out
    assert not (repo / ".plumb" / "wt").exists()
    assert (path.read_bytes(), _snapshot(repo)) == before


def test_an_agent_reopen_the_owner_did_not_ask_is_refused_and_opens_nothing(
        repo: Path, write_record: Any, window: Windows) -> None:
    _commit_records(repo, write_record)
    path = _idle_build(repo)
    before = path.read_bytes()
    assert _reopen(repo, "--loop", ID) == 2                              # no owner message at all
    _ask(repo, f"reopen loop {ID}", at="2026-10-06T10:00:00Z")
    _ask(repo, "thanks, that is all", at="2026-10-06T11:00:00Z")
    assert _reopen(repo, "--loop", ID) == 2                              # only an older message
    assert cli.main(["loops", "reopen", "--loop", ID, "--root", str(repo)]) == 2   # no session
    assert window.calls == [] and not (repo / ".plumb" / "wt").exists()
    assert path.read_bytes() == before


def test_an_ambiguous_reopen_is_settled_by_the_owners_pick(
        repo: Path, tmp_path: Path, window: Windows, capsys: pytest.CaptureFixture) -> None:
    ids = {}
    for name, digest in (("a", DIGEST_A), ("b", DIGEST_B)):
        said = log_prompt(repo, f"/plumb intent the card-store {name}", session=f"g{name}",
                          at="2026-10-01T10:00:00Z")
        _loop(_worktree(repo, tmp_path, f"card-{name}"), f"g{name}", said)
        ids[name] = said.removeprefix("sha256:")[:12]
    _ask(repo, "reopen the card-store loop")
    assert _reopen(repo, "card-store") == 1
    err = capsys.readouterr().err
    assert all(i in err for i in ids.values()) and "intent/card-a" in err and "intent/card-b" in err
    assert _reopen(repo, "--loop", ids["b"]) == 2
    open_core(repo).log_append("events", "question-answer", {
        "session": ASKER, "question": "which loop?", "options": [], "via": "question-tool",
        "answer": "the one on intent/card-b"})
    assert _reopen(repo, "--loop", ids["a"]) == 2
    assert window.calls == []
    assert _reopen(repo, "--loop", ids["b"]) == 0 and len(window.calls) == 1
    # the same answer given before the latest owner message counts for nothing
    _ask(repo, "reopen the card-store loop", at="2099-01-01T00:00:00Z", session="other")
    open_core(repo).log_append("events", "question-answer", {
        "session": "other", "question": "which loop?", "options": [], "via": "question-tool",
        "answer": "the one on intent/card-b"})
    assert _reopen(repo, "--loop", ids["b"], session="other") == 2
    assert len(window.calls) == 1


def test_a_new_worktree_for_a_main_loop_stays_out_of_mains_status(
        repo: Path, write_record: Any, window: Windows) -> None:
    _commit_records(repo, write_record)
    _idle_build(repo)
    assert not (repo / ".git" / "info" / "exclude").read_text("utf-8").count("wt")
    assert "wt/" in (repo / ".plumb" / ".gitignore").read_text("utf-8").split()
    loops.reopen(repo, loop=ID)
    assert (repo / ".plumb" / "wt" / "intent-int-001").is_dir()
    assert ".plumb/wt" not in git(repo, "status", "--porcelain")


@pytest.mark.parametrize("text", [
    "<plumb-loop-brief>\nplumb reopened an intent loop", "<plumb-loop-message> hello",
    "The plumb plugin sent a message:\n<plumb-loop-message> plumb: the owner sent a message"])
def test_brief_prompt_is_not_logged_as_owner_words(text: str) -> None:
    assert prompt_origin(text) == ("plumb", "")
    assert prompt_origin("x" * 200 + "<plumb-loop-brief>")[0] == "owner"
    peer = '<cross-session-message from-name="b">' + text + "</cross-session-message>"
    assert prompt_origin(peer) == ("peer", "b")


def test_the_brief_starts_a_turn_but_is_not_the_owners_request(
        repo: Path, hook_input: Any) -> None:
    session = "new"
    out = run_prompt(repo, hook_input, "<plumb-loop-brief>\ntake the loop over", session)
    assert out.strip() == ""
    folder = repo / ".plumb" / "session" / session
    log = [json.loads(line) for line in
           (repo / ".plumb" / "session" / "prompts.jsonl").read_text("utf-8").splitlines()]
    assert [e["origin"] for e in log] == ["plumb"]
    assert json.loads((folder / "turn.json").read_text("utf-8"))["prompt_digest"] == log[0]["digest"]
    assert (folder / "build.json").is_file() and not (folder / "touched.txt").exists()
    assert not gate.is_closed(repo, session)


def test_the_judges_transcript_reader_skips_the_brief_and_the_message(
        repo: Path, tmp_path: Path) -> None:
    folder = tmp_path / "projects" / recover.project_dir_name(repo)
    folder.mkdir(parents=True)

    def line(text: str) -> str:
        return json.dumps({"type": "user", "timestamp": "2026-11-06T10:00:00.000Z",
                           "sessionId": "s", "message": {"role": "user", "content": text}})

    (folder / "s.jsonl").write_text("\n".join(
        [line("<plumb-loop-brief>\ntake it over"), line("<plumb-loop-message> hi"),
         line("make the card store")]) + "\n", "utf-8")
    assert [m.text for m in recover.owner_messages(repo, tmp_path / "projects")] == [
        "make the card store"]


def test_a_main_loop_whose_intent_another_branch_carries_reopens_on_that_branch(
        repo: Path, tmp_path: Path, write_record: Any, window: Windows) -> None:
    _commit_records(repo, write_record)
    _idle_build(repo)
    other = _worktree(repo, tmp_path, "other")
    (other / "work.txt").write_text("own work\n", encoding="utf-8")
    commit_all(other, "own work")
    inflight.record_claim(open_core(other), records={}, summary="", intent="INT-001")
    loops.reopen(repo, loop=ID)
    assert window.calls[-1][1]["cwd"] == str(other)
    git(repo, "worktree", "remove", "--force", str(other))          # the branch stays, no checkout
    (repo / ".plumb" / "session" / "gone" / loops.PENDING).unlink()
    loops.reopen(repo, loop=ID)
    path = repo / ".plumb" / "wt" / "intent-int-001"
    assert window.calls[-1][1]["cwd"] == str(path)
    assert git(path, "branch", "--show-current").strip() == "intent/other"
    assert "intent/int-001" not in git(repo, "branch", "--list", "intent/int-001")


def test_launch_hands_the_new_window_no_session_identity() -> None:
    seen: list[dict[str, Any]] = []
    have = {"CLAUDECODE": "1", "CLAUDE_CODE_CHILD_SESSION": "1", "CLAUDE_CODE_SESSION_ID": "x",
            "CLAUDE_PID": "7", MARKER_NAME: "claude-code", "DISPLAY": ":0", "PATH": "/bin",
            "HOME": "/home/x"}
    assert REAL_LAUNCH(["claude"], Path("/w"), which=lambda p: p == "kitty" or None,
                       spawn=lambda argv, **kw: seen.append({"argv": argv, **kw}), env=have,
                       platform="linux") is True
    (call,) = seen
    assert call["argv"] == ["kitty", "-d", "/w", "claude"] and call["cwd"] == "/w"
    assert call["env"] == {"DISPLAY": ":0", "PATH": "/bin", "HOME": "/home/x"}


def test_launch_table_per_platform() -> None:
    seen: list[list[str]] = []
    spawn = lambda argv, **kw: seen.append(argv)  # noqa: E731
    assert REAL_LAUNCH(["claude", "a b"], Path("/w d"), spawn=spawn, env={}, platform="win32")
    assert REAL_LAUNCH(["claude", 'say "hi"'], Path("/w d"), spawn=spawn, env={}, platform="darwin")
    assert seen[0] == ["wt", "-d", "/w d", "claude", "a b"]
    assert seen[1][:2] == ["osascript", "-e"]
    assert """cd '/w d' && claude 'say \\"hi\\"'""" in seen[1][2]
    assert REAL_LAUNCH(["c"], Path("/w"), which=lambda p: None, env={"DISPLAY": ":0"},
                       platform="linux") is False


def test_debug_and_evaluate_rows_cannot_be_reopened(
        repo: Path, window: Windows, monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"kind": "debug", "id": "KI-9", "intent": "", "goal": "the stop hook is slow",
           "goal_full": "the stop hook is slow", "branch": "", "live": False, "last": ""}
    monkeypatch.setattr(loops, "listing", lambda root, agents=None: {"rows": [row]})
    with pytest.raises(ValueError, match="only an intent loop"):
        loops.reopen(repo, words="stop hook")
    assert window.calls == []


def test_spawn_error_falls_back(repo: Path, write_record: Any, monkeypatch: pytest.MonkeyPatch,
                                capsys: pytest.CaptureFixture) -> None:
    _commit_records(repo, write_record)
    _idle_build(repo)

    def broken(argv: list[str], **kwargs: Any) -> None:
        raise OSError("no such program")

    monkeypatch.setattr(loops, "launch", functools.partial(
        REAL_LAUNCH, which=lambda p: "/usr/bin/xterm", spawn=broken, env={"DISPLAY": ":0"},
        platform="linux"))
    _ask(repo, f"reopen loop {ID}")
    assert _reopen(repo, "--loop", ID) == 1
    assert "open the session by hand" in capsys.readouterr().out
    assert not (repo / ".plumb" / "wt" / "intent-int-001").exists()       # undone
    assert "intent/int-001" not in git(repo, "branch", "--list", "intent/int-001")


def test_mod_reopen_refuses_without_the_key(repo: Path, window: Windows,
                                            monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture) -> None:
    _idle_build(repo)
    assert run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, _, err = run_mod(monkeypatch, capsys, repo, "reopen", "--loop", ID, stdin={})
    assert code == 3 and "no key" in err
    code, _, err = run_mod(monkeypatch, capsys, repo, "reopen", "--loop", ID,
                           stdin={"key": "b2" * 32})
    assert code == 3 and window.calls == []


def test_a_mention_of_a_loop_is_not_a_request_to_reopen_it(
        repo: Path, write_record: Any, window: Windows) -> None:
    _commit_records(repo, write_record)
    _idle_build(repo)
    for said in ("how is INT-001 going?", f"what is {ID} waiting for?"):
        _ask(repo, said)
        assert _reopen(repo, "INT-001") == 2 and _reopen(repo, "--loop", ID) == 2
    assert window.calls == []
    _ask(repo, "please re-open INT-001", at="2026-10-06T11:00:00Z")
    assert _reopen(repo, "INT-001") == 0 and len(window.calls) == 1


def test_the_owners_pick_between_loops_of_main_is_honoured_from_any_checkout(
        repo: Path, tmp_path: Path, window: Windows) -> None:
    ids = {}
    for name, digest in (("a", DIGEST_A), ("b", DIGEST_B)):
        said = log_prompt(repo, f"/plumb intent retire the card store {name}", session=f"g{name}",
                          at="2026-10-01T10:00:00Z")
        _loop(repo, f"g{name}", said)
        ids[name] = said.removeprefix("sha256:")[:12]
    _ask(repo, "reopen the card store loop")
    assert _reopen(repo, "card store") == 1                      # two: the agent asks
    open_core(repo).log_append("events", "question-answer", {
        "session": ASKER, "question": "which loop?", "options": [], "via": "question-tool",
        "answer": "retire the card store b (main)"})
    wt = _worktree(repo, tmp_path, "elsewhere")                # the answer is in main's log
    assert _reopen(wt, "--loop", ids["a"]) == 2
    assert _reopen(wt, "--loop", ids["b"]) == 0 and len(window.calls) == 1


def test_the_listing_loads_the_records_once_per_checkout_and_only_for_kept_rows(
        repo: Path, write_record: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import plumb.api

    _commit_records(repo, write_record)
    for session in ("s1", "s2", "s3"):          # one loop seen from three sessions
        _loop(repo, session, DIGEST_A, intent="INT-001", stages=_passed("clarify", "plan"))
    calls: list[Path] = []
    real = plumb.api.open_core
    monkeypatch.setattr(plumb.api, "open_core", lambda r, *a, **k: calls.append(r) or real(r, *a, **k))
    assert len(loops.listing(repo, agents={})["rows"]) == 1
    assert len(calls) <= 1


def test_a_second_press_opens_no_second_session(
        repo: Path, write_record: Any, window: Windows) -> None:
    _commit_records(repo, write_record)
    _idle_build(repo)
    loops.reopen(repo, loop=ID)
    (row,) = loops.listing(repo, agents={})["rows"]
    assert row["reopen"] is False and row["send"] is False and row["waits"]
    with pytest.raises(ValueError, match="being opened"):
        loops.reopen(repo, loop=ID)
    assert len(window.calls) == 1


def test_a_main_loop_worktree_is_ignored_in_a_repository_adopted_before_the_ignore_line(
        repo: Path, write_record: Any, window: Windows) -> None:
    _commit_records(repo, write_record)
    _idle_build(repo)
    ignore = repo / ".plumb" / ".gitignore"
    ignore.write_text("\n".join(x for x in ignore.read_text("utf-8").split() if x != "wt/") + "\n",
                      encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "an older plumb's ignore file")
    loops.reopen(repo, loop=ID)
    assert (repo / ".plumb" / "wt" / "intent-int-001").is_dir()
    assert ".plumb/wt" not in git(repo, "status", "--porcelain")


def test_windows_terminal_keeps_a_semicolon_of_the_brief_and_the_hand_command_is_quoted_for_it() -> None:
    seen: list[list[str]] = []
    assert REAL_LAUNCH(["claude", "INT-001 x; SR-001 y"], Path("/w"), env={}, platform="win32",
                       spawn=lambda argv, **kw: seen.append(argv))
    assert seen[0] == ["wt", "-d", "/w", "claude", "INT-001 x\\; SR-001 y"]
    assert loops._quote(["claude", 'a "b" c'], "win32") == 'claude "a \\"b\\" c"'
    assert loops._quote(["claude", "a b"], "linux") == "claude 'a b'"
