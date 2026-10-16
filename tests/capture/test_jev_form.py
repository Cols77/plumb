"""SR-183: JEV's question form is a setting (judgment.jev.output: yes_no by default, choice
allowed). The choice form asks one choice over supported, beyond and contradicts and reads the
probability of supported; a calibration records the form it measured and is never served to
auto-approval for the other form."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import JevStub, run, use_jev
from jev_fixtures import calibrated

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-244")


def set_form(repo: Path, stub: JevStub, form: str | None) -> None:
    out = f", output: {form}" if form else ""
    (repo / ".plumb" / "config.yaml").write_text(
        "judgment:\n  backend: jev\n  hook_timeout_ms: 2000\n"
        f"  jev: {{base_url: '{stub.url}'{out}}}\n", encoding="utf-8")


def ask(repo: Path):
    from plumb.judgment import get_backend

    core = open_core(repo)
    return core, get_backend(core, hook=False).entailment(
        "build feature alpha", "build feature alpha", subject="INT-100",
        claim_kind="intent-readback")


def test_ex1_unset_form_asks_yes_no_as_today(repo: Path, monkeypatch) -> None:
    stub = JevStub()
    use_jev(repo, stub, monkeypatch)
    assert open_core(repo).config.judgment.jev.get("output", "yes_no") == "yes_no"
    _, judgment = ask(repo)
    assert [q["type"] for q in stub.requests[-1]["questions"].values()] == ["noul"]
    assert judgment.verdict == "entailed" and judgment.probability == 0.95
    stub.close()


def test_ex2_choice_form_asks_the_three_way_choice_and_reads_supported(
        repo: Path, monkeypatch) -> None:
    stub = JevStub()
    use_jev(repo, stub, monkeypatch)
    set_form(repo, stub, "choice")
    core, judgment = ask(repo)
    question = next(iter(stub.requests[-1]["questions"].values()))
    assert question["type"] == "choice"
    assert list(question["criteria"]) == ["supported", "beyond", "contradicts"]
    assert judgment.verdict == "entailed" and judgment.probability == 0.9   # P(supported)
    logged = [e.payload for e in core.events() if e.kind == "judgment"][-1]
    assert logged["form"] == "choice"                                      # the log names it
    stub.close()


def test_ex3_a_yes_no_calibration_does_not_serve_the_choice_form(
        repo: Path, write_record, monkeypatch) -> None:
    from plumb.capture.autoapprove import auto_approve_state
    from plumb.capture.jevcmd import jev_status, status_lines

    stub = calibrated(repo, write_record, monkeypatch)
    assert run(repo, "config", "auto-approve", "on") == 0      # the owner's terminal (test)
    assert auto_approve_state(open_core(repo)).effective
    calibration = [e for e in open_core(repo).events() if e.kind == "calibration"][-1]
    assert calibration.payload["form"] == "yes_no"
    set_form(repo, stub, "choice")
    state = auto_approve_state(open_core(repo))
    assert not state.effective and "choice form" in state.reason
    assert "calibration" in state.reason
    text = "\n".join(status_lines(jev_status(open_core(repo))))
    assert "calibration for the choice form is needed" in text
    stub.close()


def test_the_verdict_cascade_does_not_use_a_calibration_of_the_other_form(
        repo: Path, write_record, monkeypatch) -> None:
    from plumb.understand import verdict

    stub = calibrated(repo, write_record, monkeypatch)
    set_form(repo, stub, "choice")
    core = open_core(repo)
    cleared, why = verdict._ask_jev(core, [{"id": "INT-100", "kind": "intent"}],
                                    object())
    assert cleared == {} and "choice form" in why
    stub.close()
