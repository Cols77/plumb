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
    assert "MY_KEY" in out and SECRET not in out
    assert "/plumb jev status" in out
    assert "export " not in out and "$env:" not in out  # R14: no shell for the owner
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
        assert "reachable: yes (ok), resolved version jev-1.13 (jev-1.13.0)" in out
        assert "provider: typesafe" in out
        assert f"endpoint: {stub.url}/v1/systemone" in out
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


# -- OpenRouter: the provider preset, the user-level env file (SR-039)

OR_SECRET = "sk-or-secret-value-0123456789"


def _user_config(monkeypatch, tmp_path: Path) -> Path:
    from plumb.judgment import jev as jev_mod

    path = tmp_path / "userhome" / "jev.json"
    monkeypatch.setattr(jev_mod, "user_config_path", lambda: path)
    return path


def test_setup_openrouter_with_an_env_file(repo: Path, tmp_path: Path, monkeypatch,
                                           capsys) -> None:
    import json

    config_path = _user_config(monkeypatch, tmp_path)
    env_file = tmp_path / "elsewhere" / ".env"
    env_file.parent.mkdir()
    env_file.write_text(f"OPENROUTER_API_KEY={OR_SECRET}\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert run(repo, "jev", "setup", "--provider", "openrouter", "--env-var",
               "OPENROUTER_API_KEY", "--env-file", str(env_file)) == 0
    out = capsys.readouterr().out
    assert OR_SECRET not in out and "export " not in out and "$env:" not in out
    assert "found" in out
    jev = open_core(repo).config.judgment.jev
    assert (jev["provider"], jev["model"], jev["credential_env"]) == (
        "openrouter", "typesafe/jev-1.13", "OPENROUTER_API_KEY")
    assert jev["base_url"] == "https://openrouter.ai"
    raw = (repo / ".plumb" / "config.yaml").read_text(encoding="utf-8")
    assert "provider: openrouter" in raw and "base_url" not in raw
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "credential_env": "OPENROUTER_API_KEY", "env_file": str(env_file.resolve())}
    assert OR_SECRET.encode() not in all_bytes(repo)
    assert OR_SECRET not in config_path.read_text(encoding="utf-8")
    [event] = list(open_core(repo).log_read("events", ["jev-setup"]))
    assert event.payload["provider"] == "openrouter"
    from plumb.judgment.jev import key_source

    assert key_source(repo, name="OPENROUTER_API_KEY") == "env-file"


def test_setup_refuses_an_env_file_inside_the_repository(repo: Path, tmp_path: Path,
                                                          monkeypatch, capsys) -> None:
    config_path = _user_config(monkeypatch, tmp_path)
    (repo / ".env").write_text(f"OPENROUTER_API_KEY={OR_SECRET}\n", encoding="utf-8")
    assert run(repo, "jev", "setup", "--provider", "openrouter",
               "--env-file", str(repo / ".env")) == 2
    assert "inside the repository" in capsys.readouterr().err
    assert not config_path.exists()
    assert "openrouter" not in (repo / ".plumb" / "config.yaml").read_text(encoding="utf-8")


def test_setup_openrouter_defaults_the_variable_name(repo: Path, tmp_path: Path,
                                                     monkeypatch, capsys) -> None:
    config_path = _user_config(monkeypatch, tmp_path)
    assert run(repo, "jev", "setup", "--provider", "openrouter") == 0
    capsys.readouterr()
    assert open_core(repo).config.judgment.jev["credential_env"] == "OPENROUTER_API_KEY"
    assert not config_path.exists()  # no --env-file: the user-level file is not written


def test_status_shows_provider_endpoint_source_and_normalized_version(
        repo: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    import json

    stub = JevStub(model="typesafe/jev-1.13-20260917")
    try:
        config_path = _user_config(monkeypatch, tmp_path)
        env_file = tmp_path / "elsewhere" / ".env"
        env_file.parent.mkdir()
        env_file.write_text(f"OPENROUTER_API_KEY='{OR_SECRET}'\n", encoding="utf-8")
        config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps({"credential_env": "OPENROUTER_API_KEY",
                                           "env_file": str(env_file)}), encoding="utf-8")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        (repo / ".plumb" / "config.yaml").write_text(
            "judgment:\n  backend: jev\n"
            f"  jev: {{provider: openrouter, base_url: '{stub.url}'}}\n", encoding="utf-8")
        assert run(repo, "jev", "status", "--probe") == 0
        out = capsys.readouterr().out
        assert OR_SECRET not in out
        assert "provider: openrouter" in out
        assert f"endpoint: {stub.url}/api/alpha/decisions" in out
        assert "credential: present (variable OPENROUTER_API_KEY, from env-file;" in out
        assert ("reachable: yes (ok), resolved version jev-1.13 "
                "(typesafe/jev-1.13-20260917)") in out
        assert "version drift" not in out
        assert run(repo, "jev", "status", "--probe", "--json") == 0
        data = json.loads(capsys.readouterr().out)
        assert data["credential_source"] == "env-file"
        assert data["resolved_version"] == "jev-1.13"
        assert data["resolved_model"] == "typesafe/jev-1.13-20260917"
        assert data["version_drift"] is False
        stub.model = "typesafe/jev-1.14-20261001"
        assert run(repo, "jev", "status", "--probe") == 0
        assert "version drift: validated against typesafe/jev-1.13" in capsys.readouterr().out
    finally:
        stub.close()
