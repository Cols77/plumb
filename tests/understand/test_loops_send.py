"""SR-395: the owner's words reach the session working on a loop, once, labelled as sent through
the loop list; an agent passes only words the owner typed. No test messages a real session: the
running sessions come from a fake map and delivery is the target's own hooks, called here."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mod.helpers import DIGEST, KEY, run_mod
from present.present_helpers import run_prompt

from plumb import cli
from plumb.hosts.claude_code import pretool
from plumb.understand import gate, loops

from capture.capture_helpers import log_prompt
from understand.test_loops import _loop, _passed, _worktree

pytestmark = pytest.mark.sr("SR-395")

ID = "aaaaaaaaaaaa"
DIGEST_A = "sha256:" + "a" * 64
TARGET = "target"
SENDER = "sender"


@pytest.fixture(autouse=True)
def busy(monkeypatch: pytest.MonkeyPatch) -> None:
    """The target session is working (the fake map of ``claude agents``)."""
    monkeypatch.setattr(loops, "claude_sessions",
                        lambda: {TARGET: {"status": "busy", "cwd": ""}})


def _building(root: Path, session: str = TARGET) -> Path:
    return _loop(root, session, DIGEST_A, stages=_passed("clarify", "plan"),
                 tasks={"label": "building", "done": 1, "total": 2, "left": ["the colours"]})


def _pane_send(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
               text: str) -> tuple[int, Any, str]:
    assert run_mod(monkeypatch, capsys, root, "hello", stdin={"key_digest": DIGEST})[0] == 0
    return run_mod(monkeypatch, capsys, root, "send", "--loop", ID,
                   stdin={"key": KEY, "text": text})


def _send(root: Path, *words: str, text: str, session: str = SENDER) -> int:
    return cli.main(["loops", "send", *words, "--text", text, "--session", session,
                     "--root", str(root)])


def _message(root: Path) -> Any:
    return loops.listing(root)["rows"][0]["message"]


def _inbox(root: Path, session: str = TARGET) -> Path:
    return root / ".plumb" / "session" / session / "inbox.jsonl"


def test_ex1_typed_on_the_row_reaches_the_working_session_before_its_next_step_and_reads_delivered(
        repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    _building(repo)
    code, answer, _ = _pane_send(repo, monkeypatch, capsys, "skip the colours slice")
    assert code == 0 and answer["sent"] is True
    assert _message(repo)["state"] == "sent"
    held = pretool.decide(repo, TARGET, "Read", {"file_path": "a.py"}, {"session_id": TARGET})
    reason = held["hookSpecificOutput"]["permissionDecisionReason"]
    assert held["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "message through plumb's loop list" in reason and "skip the colours slice" in reason
    assert pretool.decide(repo, TARGET, "Read", {"file_path": "a.py"}, {}) == {}
    assert _message(repo)["state"] == "delivered"


def test_ex2_an_agent_passes_the_owners_words_unchanged(repo: Path, tmp_path: Path) -> None:
    wt = _worktree(repo, tmp_path, "card-store")
    _building(wt)
    log_prompt(repo, "tell the card-store loop to rebase on main", session=SENDER)
    assert _send(wt, "card-store", text="rebase on main") == 0
    (entry,) = [json.loads(line) for line in _inbox(wt).read_text("utf-8").splitlines()]
    assert entry["text"] == "rebase on main" and entry["via"] == "agent"


def test_ex3_words_the_owner_did_not_type_are_refused_and_nothing_sent(
        repo: Path, capsys: pytest.CaptureFixture) -> None:
    _building(repo)
    log_prompt(repo, "tell the card-store loop to rebase on main", session=SENDER)
    assert _send(repo, ID, text="delete the branch") == 2
    assert _send(repo, ID, text="rebase on main", session="other") == 2
    assert not _inbox(repo).exists() and "did not type" in capsys.readouterr().err


def test_ex4_a_waiting_session_with_no_band_reads_sent_until_its_next_turn_then_delivered_once(
        repo: Path, hook_input: Any, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    _building(repo)
    _pane_send(repo, monkeypatch, capsys, "rebase on main")
    assert _message(repo)["state"] == "sent"       # no panel of the target runs: nothing wakes it
    first = run_prompt(repo, hook_input, "go on", TARGET)
    assert first.count("rebase on main") == 1
    assert "rebase on main" not in run_prompt(repo, hook_input, "and now", TARGET)
    assert _message(repo)["state"] == "delivered"


def test_ex5_a_loop_nobody_works_on_is_refused_and_named_reopenable(
        repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    _building(repo, "gone")
    log_prompt(repo, "tell it to rebase", session=SENDER)
    assert _send(repo, ID, text="rebase") == 1
    err = capsys.readouterr().err
    assert "no session works on this loop" in err and f"plumb loops reopen {ID}" in err
    assert not _inbox(repo, "gone").exists()


def test_a_loop_held_in_a_worktree_reaches_the_session_whose_hooks_run_in_main(
        repo: Path, tmp_path: Path) -> None:
    wt = _worktree(repo, tmp_path)
    _building(wt)
    host = repo / ".plumb" / "session" / TARGET / "host.json"
    host.parent.mkdir(parents=True, exist_ok=True)
    host.write_text("{}", "utf-8")
    log_prompt(repo, "tell the loop to rebase on main", session=SENDER)
    assert _send(wt, ID, text="rebase on main") == 0
    assert _inbox(repo).is_file() and not _inbox(wt).exists()
    assert "rebase on main" in str(pretool.decide(repo, TARGET, "Read", {}, {}))
    assert _message(repo)["state"] == _message(wt)["state"] == "delivered"


def test_take_inbox_keeps_a_message_appended_during_the_take(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loops.append_inbox(repo, TARGET, {"id": "1", "loop": ID, "text": "one", "sent_at": "a"})
    real = loops._lines
    calls: list[int] = []

    def racing(path: Path) -> list[dict[str, Any]]:
        if not calls:
            calls.append(1)
            loops.append_inbox(repo, TARGET, {"id": "2", "loop": ID, "text": "two",
                                              "sent_at": "b"})
        return real(path)

    monkeypatch.setattr(loops, "_lines", racing)
    assert [m["text"] for m in loops.take_inbox(repo, TARGET)] == ["one"]
    monkeypatch.setattr(loops, "_lines", real)
    assert [m["text"] for m in loops.take_inbox(repo, TARGET)] == ["two"]


@pytest.mark.parametrize("prompt", ["<plumb-loop-message> plumb: the owner sent this session a "
                                    "message.",
                                    "The plumb plugin sent a message: <plumb-loop-message> "
                                    "plumb: the owner sent this session a message."])
def test_a_message_prompt_starts_a_turn_and_delivers(
        repo: Path, hook_input: Any, prompt: str) -> None:
    loops.append_inbox(repo, TARGET, {"id": "1", "loop": ID, "text": "rebase on main",
                                      "sent_at": "a"})
    out = run_prompt(repo, hook_input, prompt, TARGET)
    assert out.count("rebase on main") == 1 and "relevant records" not in out
    folder = repo / ".plumb" / "session"
    log = [json.loads(line) for line in (folder / "prompts.jsonl").read_text("utf-8").splitlines()]
    assert log[-1]["origin"] == "plumb"
    turn = json.loads((folder / TARGET / "turn.json").read_text("utf-8"))
    assert turn["prompt_digest"] == log[-1]["digest"] and not gate.is_closed(repo, TARGET)


def test_a_subagents_step_leaves_the_message_for_the_main_agent(
        repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    _building(repo)
    _pane_send(repo, monkeypatch, capsys, "rebase on main")
    before = _inbox(repo).read_text("utf-8")
    assert pretool.decide(repo, TARGET, "Read", {}, {"agent_id": "a1"}) == {}
    assert _inbox(repo).read_text("utf-8") == before and _message(repo)["state"] == "sent"
    assert "rebase on main" in str(pretool.decide(repo, TARGET, "Read", {}, {}))
