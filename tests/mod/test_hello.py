"""SP7 slice 4: ``plumb mod hello`` registers the panel's key digest for a session; the first
registration wins (sp7-owner-surface 5.1, DEC-025; SR-086 EX-3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mod.helpers import DIGEST, KEY, SESSION, kinds, mod_json, run_mod

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-086")


def test_first_registration_wins_and_a_second_is_refused(repo: Path, monkeypatch,
                                                         capsys) -> None:
    code, answer, _ = run_mod(monkeypatch, capsys, repo, "hello",
                              stdin={"key_digest": DIGEST})
    assert code == 0
    assert answer["active"] is True and answer["session"] == SESSION and answer["since"]
    held = json.loads(mod_json(repo).read_text(encoding="utf-8"))
    assert set(held) == {"active", "since", "key_digest", "heartbeat"}
    assert held["key_digest"] == DIGEST and held["active"] is True
    (hello,) = [e for e in open_core(repo).events() if e.kind == "mod-hello"]
    assert hello.payload == {"session": SESSION, "key_digest": DIGEST, "since": held["since"]}
    assert hello.marker == "none"
    before = mod_json(repo).read_bytes()

    code, answer, err = run_mod(monkeypatch, capsys, repo, "hello",
                                stdin={"key_digest": "c3" * 32})
    assert code == 3 and answer is None and "already" in err
    assert mod_json(repo).read_bytes() == before
    assert kinds(repo).count("mod-hello") == 1


def test_the_key_itself_is_never_written(repo: Path, monkeypatch, capsys) -> None:
    run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})
    written = mod_json(repo).read_text(encoding="utf-8")
    logged = "".join(p.read_text(encoding="utf-8")
                     for p in (repo / ".plumb" / "log").rglob("*.json"))
    assert KEY not in written and KEY not in logged


@pytest.mark.parametrize("stdin", [None, {}, {"key_digest": ""}, {"key_digest": "xyz"},
                                   {"key": KEY}])
def test_no_key_digest_is_refused_and_nothing_written(repo: Path, monkeypatch, capsys,
                                                      stdin) -> None:
    code, answer, _ = run_mod(monkeypatch, capsys, repo, "hello", stdin=stdin)
    assert code == 3 and answer is None
    assert not mod_json(repo).exists() and "mod-hello" not in kinds(repo)


def test_under_the_session_marker_hello_is_refused(repo: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    code, _, err = run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})
    assert code == 3 and "agent" in err
    assert not mod_json(repo).exists()
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    assert "mod-hello" not in kinds(repo)


def test_sessions_register_independently(repo: Path, monkeypatch, capsys) -> None:
    assert run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, _, _ = run_mod(monkeypatch, capsys, repo, "hello", "--session", "s2",
                         stdin={"key_digest": DIGEST})
    assert code == 0 and mod_json(repo, "s2").exists()
