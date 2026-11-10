"""No approval command (task 8 of the judge-approval plan): ``approve``, ``confirm``,
``revoke``, ``relay``, ``triage --approve`` and ``spec approve`` are refused with exit 3 as no
longer existing, whoever runs them and whatever stdin holds, and write nothing. A typed
``/iaso approve`` is no command either: its words go to the reader as prose."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture.capture_helpers import agent_shell_setup, run
from understand.fakes import engine_standins  # noqa: F401 - the fixture
from understand.test_read_job import SESSION, ctx_for, log_prompt, make_core, record_text, state

from iaso import cli
from iaso.api import open_core
from iaso.understand import files, hooks

DEC = ("---\nid: DEC-017\ntitle: Pick a store\nquestion: which store?\noptions:\n- id: A\n"
       "  text: sqlite\nchosen: A\nstatus: proposed\n---\nbody\n")
STEPS = (("approve", "SR-040"), ("confirm", "SR-040"), ("revoke", "SR-040"),
         ("relay", "SR-040"))


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [DEC, record_text(40), record_text(41)])


def written(root: Path) -> list[str]:
    return [e.kind for e in open_core(root).events()]


def states(root: Path) -> dict[str, str]:
    return {i: s.confirmation for i, s in open_core(root).status().items()}


@pytest.mark.sr("SR-210")
def test_ex1_the_agent_runs_approve_confirm_or_revoke_and_each_is_refused(
        core, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """SR-210 EX-1: in the agent's session, iaso approve, confirm and revoke on a requirement
    are refused with exit 3 as no longer existing, and nothing is written."""
    monkeypatch.setenv("IASO_AGENT_SESSION", "claude-code")
    before = states(core.root)
    for verb in ("approve", "confirm", "revoke"):
        assert run(core.root, verb, "SR-040") == 3, verb
        assert f"iaso: {verb} no longer exists; nothing was recorded" in capsys.readouterr().err
    assert written(core.root) == [] and states(core.root) == before


@pytest.mark.sr("SR-210")
def test_ex2_no_marker_no_terminal_and_y_piped_in_still_refused(
        core, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """SR-210 EX-2: a host that cannot set the session marker, an agent shell with no
    terminal and "y" piped in: every approval-writing step is refused with exit 3, nothing
    written."""
    agent_shell_setup(monkeypatch)
    before = states(core.root)
    for step in STEPS:
        assert run(core.root, *step) == 3, step
        assert "no longer exists; nothing was recorded" in capsys.readouterr().err, step
    assert written(core.root) == [] and states(core.root) == before


@pytest.mark.sr("SR-210")
def test_ex5_relay_is_refused_as_gone_with_no_help_line(
        core, capsys: pytest.CaptureFixture[str]) -> None:
    """SR-210 EX-5: iaso relay is looked up and refused as no longer existing; no help
    line names it, nor approve, confirm or revoke."""
    assert run(core.root, "relay", "SR-040", "--quote", "ok") == 3
    assert "iaso: relay no longer exists" in capsys.readouterr().err
    verbs = {line.split()[0] for line in cli.help_text().splitlines()
             if line.startswith("  ") and line.strip()}
    assert not {"relay", "approve", "confirm", "revoke"} & verbs
    assert "--approve" not in cli.help_text()
    assert written(core.root) == []


@pytest.mark.sr("SR-209")
@pytest.mark.usefixtures("engine_standins")
def test_ex3_a_bare_ok_with_no_question_open_changes_nothing_and_asks_nothing(
        core) -> None:
    """SR-209 EX-3: no question is open; the owner writes a bare "ok": no record changes
    state and no question is asked."""
    before = states(core.root)
    digest = log_prompt(core, "ok")
    lines = hooks.on_prompt(ctx_for(core), core, {"digest": digest, "text": "ok"})
    assert states(core.root) == before
    assert [k for k in written(core.root) if k in ("approval", "revocation")] == []
    assert not (files.session_dir(core.root, SESSION) / "judge_questions.json").exists()
    assert not any("?" in line for line in lines)


@pytest.mark.sr("SR-209")
@pytest.mark.usefixtures("engine_standins")
def test_ex6_typed_iaso_approve_runs_no_approval_and_is_read_as_the_owners_words(
        core) -> None:
    """SR-209 EX-6: the owner types "/iaso approve DEC-017"; the prompt hook runs no
    approval, asks for no id, leaves every record's state unchanged and gives the words to
    the reader, to be read by meaning as the owner's answer."""
    state(core, ["DEC-017"])
    before = states(core.root)
    text = "/iaso approve DEC-017"
    digest = log_prompt(core, text)
    lines = hooks.on_prompt(ctx_for(core), core, {"digest": digest, "text": text})
    assert states(core.root) == before
    assert [k for k in written(core.root) if k in ("approval", "revocation")] == []
    assert not any("DEC-017" in line or "which records" in line for line in lines)
    jobs = [files.job_from_json(files.read_json(p))
            for p in files.jobs_dir(core.root, SESSION).glob("*.json")]
    [job] = [j for j in jobs if j.kind == "read"]
    assert job.inputs["message"]["digest"] == digest
    assert [i["id"] for i in job.inputs["shown"]] == ["DEC-017"]
