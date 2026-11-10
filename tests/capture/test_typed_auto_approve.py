"""SR-115, DEC-016: the owner's typed /iaso auto-approve on|off, seen by the prompt hook,
writes the owner's config event as their terminal does; the agent never switches it."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from capture_helpers import event_kinds, log_prompt, run
from jev_fixtures import calibrated

from iaso.api import open_core
from iaso.capture.autoapprove import auto_approve_state

pytestmark = pytest.mark.sr("SR-250")


def hook_reads(repo: Path, text: str) -> str:
    """The prompt hook reads ``text`` (the hook runs under the session marker)."""
    from iaso.understand import read

    digest = log_prompt(repo, text)
    core = open_core(repo)
    assert read.on_prompt(SimpleNamespace(session_id="test-session", root=repo), core,
                          {"digest": digest, "text": text}) is None
    return digest


def configs(repo: Path) -> list:
    return [e for e in open_core(repo).events() if e.kind == "config"]


@pytest.fixture
def jev(repo: Path, write_record, monkeypatch):
    stub = calibrated(repo, write_record, monkeypatch)
    monkeypatch.setenv("IASO_AGENT_SESSION", "session-1")
    yield repo
    stub.close()


def test_ex1_typed_on_logs_the_owners_config_event_and_turns_it_on(jev, capsys) -> None:
    repo = jev
    digest = hook_reads(repo, "/iaso auto-approve on")
    (entry,) = configs(repo)
    payload = entry.payload
    assert payload["by"] == "owner" and payload["via"] == "typed"
    assert payload["prompt_digest"] == digest and "quote" not in payload   # DEC-116
    from iaso import words
    from iaso.normalize import sha256_text

    assert payload["quote_digest"] == sha256_text("/iaso auto-approve on")
    assert words.joined(open_core(repo), entry)["quote"] == "/iaso auto-approve on"
    assert payload["auto_approve"]["enabled"] is True
    assert entry.marker == "session-1"           # the hook's own process: the quote is the proof
    state = auto_approve_state(open_core(repo))
    assert state.configured and state.effective
    assert state.source == "your typed /iaso auto-approve on"
    assert "enabled: true" in (repo / ".iaso" / "config.yaml").read_text(encoding="utf-8")
    from iaso.understand.read import confirmation_lines

    assert confirmation_lines(open_core(repo), digest) == ["Automatic confirmation is now on."]
    from iaso.validate import validate

    assert not [f for f in validate(open_core(repo)) if f.severity == "error"]
    assert run(repo, "status") == 0
    assert "auto-approve: on (set by your typed /iaso auto-approve on)" \
        in capsys.readouterr().out
    assert run(repo, "brief", "--all") == 0
    assert "auto-approve: on (set by your typed /iaso auto-approve on)" \
        in capsys.readouterr().out


def _without_the_words(repo: Path) -> None:
    """A checkout that never had the owner's words: no owner-words and no prompt entries."""
    for kind in ("owner-words", "prompt", "pre-intent"):
        for path in (repo / ".iaso" / "log" / kind).glob("*.json"):
            path.unlink()


def test_an_on_without_the_words_is_refused(jev) -> None:
    """Owner, 2026-11-01: "On" needs my words. A digest anyone can compute proves nothing."""
    repo = jev
    hook_reads(repo, "/iaso auto-approve on")
    _without_the_words(repo)
    assert not auto_approve_state(open_core(repo)).configured


def test_a_forged_on_with_no_words_is_refused(jev) -> None:
    from iaso.normalize import sha256_text

    repo = jev
    on = {"enabled": True, "backend": "jev", "min_probability": 0.9, "min_confidence": "high"}
    open_core(repo).log_append("events", "config", {
        "auto_approve": on, "by": "owner", "via": "typed", "prompt_digest": "sha256:p",
        "quote_digest": sha256_text("/iaso auto-approve on")})   # a digest the agent can compute
    assert not auto_approve_state(open_core(repo)).configured


def test_an_on_with_the_words_is_accepted(jev) -> None:
    repo = jev
    hook_reads(repo, "/iaso auto-approve on")
    state = auto_approve_state(open_core(repo))
    assert state.configured and state.source == "your typed /iaso auto-approve on"


def test_an_off_without_the_words_is_accepted_from_the_record(jev) -> None:
    """Owner, 2026-11-01: turning it off counts from the committed record alone."""
    repo = jev
    hook_reads(repo, "/iaso auto-approve on")
    hook_reads(repo, "/iaso auto-approve off")
    _without_the_words(repo)
    state = auto_approve_state(open_core(repo))
    assert not state.configured and state.source == "your typed /iaso auto-approve off"


def test_a_checkout_without_the_words_still_needs_the_structure(jev) -> None:
    from iaso.normalize import sha256_text

    repo = jev
    on = {"enabled": True, "backend": "jev", "min_probability": 0.9, "min_confidence": "high"}
    core = open_core(repo)
    core.log_append("events", "config", {
        "auto_approve": on, "by": "owner", "via": "typed", "prompt_digest": "sha256:p",
        "quote_digest": sha256_text("anything the owner never typed as a command")})
    assert not auto_approve_state(open_core(repo)).configured
    core.log_append("events", "config", {
        "auto_approve": on, "by": "owner", "via": "typed", "prompt_digest": "sha256:p",
        "quote_digest": sha256_text("/iaso auto-approve off")})   # says the other state
    assert not auto_approve_state(open_core(repo)).configured


def test_ex1_typed_off_turns_it_off(jev) -> None:
    repo = jev
    hook_reads(repo, "/iaso auto-approve on")
    hook_reads(repo, "/iaso auto-approve off")
    state = auto_approve_state(open_core(repo))
    assert not state.configured and state.source == "your typed /iaso auto-approve off"
    assert "enabled: false" in (repo / ".iaso" / "config.yaml").read_text(encoding="utf-8")


def test_ex1_typed_on_without_jev_is_logged_and_says_why_not_in_effect(repo: Path) -> None:
    digest = hook_reads(repo, "/iaso auto-approve on")
    state = auto_approve_state(open_core(repo))
    assert state.configured and not state.effective
    from iaso.understand.read import confirmation_lines

    (line,) = confirmation_lines(open_core(repo), digest)
    assert line.startswith("Automatic confirmation is switched on, but not in effect yet: ")


def test_ex2_agent_running_config_auto_approve_is_refused_and_logs_nothing(
        jev, capsys) -> None:
    repo = jev                                     # IASO_AGENT_SESSION is set
    assert run(repo, "config", "auto-approve", "on") == 3
    assert run(repo, "config", "auto-approve", "off") == 3
    assert "agent session marker is set" in capsys.readouterr().err
    assert "config" not in event_kinds(repo)
    assert not auto_approve_state(open_core(repo)).configured


def test_a_typed_switch_the_hook_did_not_log_changes_nothing(jev) -> None:
    from iaso.understand import typed

    repo = jev
    parsed = typed.parse("/iaso auto-approve on")
    core = open_core(repo)
    assert typed.switch_now(core, parsed, "sha256:" + "1" * 64).lines == ()
    digest = log_prompt(repo, "/iaso auto-approve on", via="turn")  # the agent's own
    assert typed.switch_now(core, parsed, digest).lines == ()
    digest = log_prompt(repo, "turn auto-approve on please")
    assert typed.switch_now(core, parsed, digest).lines == ()
    assert configs(repo) == []


def test_a_config_event_under_the_marker_without_the_typed_proof_switches_nothing(
        jev) -> None:
    from iaso.approvals import prompt_digest

    repo = jev
    core = open_core(repo)
    on = {"enabled": True, "backend": "jev", "min_probability": 0.9, "min_confidence": "high"}
    core.log_append("events", "config", {"auto_approve": on, "by": "owner"})
    off_quote = "/iaso auto-approve off"         # a quote that says the other state
    core.log_append("events", "prompt", {"digest": prompt_digest(off_quote)})
    core.log_append("events", "config", {"auto_approve": on, "by": "owner", "via": "typed",
                                         "prompt_digest": prompt_digest(off_quote),
                                         "quote": off_quote})
    on_quote = "/iaso auto-approve on"           # no prompt event logged before it
    core.log_append("events", "config", {"auto_approve": on, "by": "owner", "via": "typed",
                                         "prompt_digest": prompt_digest(on_quote),
                                         "quote": on_quote})
    assert not auto_approve_state(open_core(repo)).configured


def test_yaml_on_without_the_event_is_off_and_status_says_so(repo: Path, capsys) -> None:
    config = repo / ".iaso" / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8") + "auto_approve: {enabled: true}\n",
                      encoding="utf-8")
    state = auto_approve_state(open_core(repo))
    assert not state.configured and state.mirror_mismatch and state.source is None
    assert run(repo, "status") == 0
    assert "auto-approve: off (config.yaml says on, but you never switched it on" \
        in capsys.readouterr().out


def test_status_names_the_terminal_as_the_source(repo: Path, write_record, monkeypatch,
                                                 capsys) -> None:
    stub = calibrated(repo, write_record, monkeypatch)
    try:
        assert run(repo, "config", "auto-approve", "on") == 0  # the owner's terminal (test)
        assert run(repo, "status") == 0
        assert "auto-approve: on (set by your terminal)" in capsys.readouterr().out
    finally:
        stub.close()


def test_status_says_never_switched_on(repo: Path, capsys) -> None:
    assert run(repo, "status") == 0
    assert "auto-approve: off (never switched on)" in capsys.readouterr().out
