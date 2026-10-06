"""CAPTURE CS2: plumb jev status and setup; the secret is never read into, printed by or
written by plumb (R8 commands; sp2 7.3, SR-039)."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import KEY, JevStub, run, use_jev

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-039")

SECRET = "ts-secret-value-0123456789"


def all_bytes(repo: Path) -> bytes:
    return b"".join(p.read_bytes() for p in repo.rglob("*")
                    if p.is_file() and ".git" not in p.parts)


def test_setup_records_only_the_name(repo: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MY_KEY", SECRET)
    assert run(repo, "jev", "setup", "--env-var", "MY_KEY") == 0
    out = capsys.readouterr().out
    assert "export MY_KEY=<your key>" in out and SECRET not in out
    core = open_core(repo)
    assert core.config.judgment.backend == "jev"
    assert core.config.judgment.jev["credential_env"] == "MY_KEY"
    [event] = list(core.log_read("events", ["jev-setup"]))
    assert event.payload["credential_env"] == "MY_KEY"
    assert SECRET.encode() not in all_bytes(repo)
    # the commented template stays
    assert "# plumb configuration." in (repo / ".plumb" / "config.yaml").read_text("utf-8")
    assert run(repo, "jev", "setup", "--env-var", "not a name") == 2


def test_status_never_prints_the_secret(repo: Path, monkeypatch, capsys) -> None:
    stub = JevStub()
    try:
        use_jev(repo, stub, monkeypatch)
        assert run(repo, "jev", "status", "--probe") == 0
        out = capsys.readouterr().out
        assert "configured: yes" in out and "credential: present" in out
        assert "reachable: yes (ok), resolved version jev-1.13.0" in out
        assert KEY not in out
        monkeypatch.delenv("TYPESAFE_API_KEY")
        assert run(repo, "jev", "status") == 0
        assert "credential: absent (variable TYPESAFE_API_KEY" in capsys.readouterr().out
    finally:
        stub.close()


def test_status_without_jev(repo: Path, capsys) -> None:
    assert run(repo, "jev", "status", "--json") == 0
    import json

    data = json.loads(capsys.readouterr().out)
    assert data["configured"] is False and data["auto_approve"] == "off"
