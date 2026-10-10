"""CAPTURE SR-040 / SR-042 / SR-097: faithfulness is judged on what the read-back claims as
the owner's, against the owner's whole words, and triage tells apart faithful, contradicts
and goes beyond."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from capture_helpers import JevStub, log_prompt, record_text, run, use_jev

from plumb.api import open_core
from plumb.capture.triage import _Prompts, claim, triage, view_lines

LONG = ("I want multiply next to add. Keep it small, and do not touch the old exporter "
        "while you are there.")
QUOTE = "multiply next to add"


def short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def intent(write_record, repo: Path, record_id: str = "INT-001", **fields) -> None:
    base = {"quote": QUOTE, "readback": "add multiply next to add",
            "will": ["multiply"], "wont": ["touch the old exporter"],
            "assumptions": ["integers only"], "prompt": short(LONG)}
    base.update(fields)
    write_record(repo, record_text(record_id, "multiply", **base))


@pytest.fixture(autouse=True)
def logged(repo: Path) -> None:
    log_prompt(repo, LONG, at="2026-10-06T00:00:00Z")


def _claim(repo: Path, record_id: str, *, prompts: bool = True):
    core = open_core(repo)
    index = core.index()
    return claim(index, index[record_id], _Prompts(core) if prompts else None)


def test_hypothesis_is_what_the_owner_is_made_to_say(repo: Path, write_record) -> None:
    intent(write_record, repo)
    kind, _, hypothesis = _claim(repo, "INT-001")
    assert kind == "intent-readback"
    assert "add multiply next to add" in hypothesis
    assert "will: multiply" in hypothesis and "won't: touch the old exporter" in hypothesis
    assert "integers only" not in hypothesis and "assumed" not in hypothesis


def test_premise_is_the_whole_logged_prompt(repo: Path, write_record) -> None:
    intent(write_record, repo)
    assert _claim(repo, "INT-001")[1] == LONG
    assert _claim(repo, "INT-001", prompts=False)[1] == QUOTE  # no log: the quote


def test_premise_without_a_logged_prompt_is_the_quote(repo: Path, write_record) -> None:
    intent(write_record, repo, prompt="0000000000000000")
    assert _claim(repo, "INT-001")[1] == QUOTE


def test_short_answer_keeps_its_question_with_the_prompt(repo: Path, write_record) -> None:
    log_prompt(repo, "A", at="2026-10-06T00:00:01Z")
    intent(write_record, repo, quote="A", prompt=short("A"), question="Background or now?")
    assert _claim(repo, "INT-001")[1] == "Background or now?\nA"


def test_requirement_premise_is_its_intents_premise(repo: Path, write_record) -> None:
    intent(write_record, repo)
    write_record(repo, record_text(
        "SR-001", "multiply", statement="multiply returns the product",
        examples=[{"id": "EX-1", "given": "2 and 3", "when": "multiply runs",
                   "then": "it returns 6"}],
        links=[{"kind": "derives_from", "to": "INT-001"}]))
    kind, premise, hypothesis = _claim(repo, "SR-001")
    assert kind == "example-restatement" and premise == LONG
    assert "multiply returns the product" in hypothesis


def test_calibration_judges_the_same_claim(repo: Path, write_record) -> None:
    from plumb.approvals import approve
    from plumb.capture.calibrate import labelled_set

    intent(write_record, repo)
    approve(open_core(repo), ["INT-001"])
    [item] = [i for i in labelled_set(open_core(repo)) if i.label == "yes"]
    _, premise, hypothesis = _claim(repo, "INT-001")
    assert item.premise == premise == LONG and item.hypotheses == (hypothesis,)


@pytest.fixture
def stub():
    instance = JevStub(lambda state: 0.03 if "BEYOND" in state else 0.95)
    yield instance
    instance.close()


def test_the_judge_is_sent_the_claim_and_the_whole_words(repo: Path, write_record,
                                                         monkeypatch, stub) -> None:
    use_jev(repo, stub, monkeypatch)
    intent(write_record, repo)
    triage(open_core(repo))
    state = stub.requests[0]["state"]
    assert LONG in state and "will: multiply" in state and "integers only" not in state


def test_three_outcomes_are_told_apart(repo: Path, write_record, monkeypatch, stub,
                                       capsys) -> None:
    use_jev(repo, stub, monkeypatch)
    intent(write_record, repo, "INT-001")                                   # faithful
    intent(write_record, repo, "INT-002", readback="BEYOND add multiply")   # beyond
    intent(write_record, repo, "INT-003", will=["touch the old exporter"],
           wont=[])                                                          # contradicts
    view = triage(open_core(repo))
    assert [i.id for i in view.low_risk] == ["INT-001"]
    outcome = {i.id: i.outcome for i in view.individual}
    assert outcome == {"INT-002": "beyond", "INT-003": "contradicts"}
    assert view.low_risk[0].outcome == "faithful"
    text = "\n".join(view_lines(view))
    assert "goes beyond your words" in text and "contradicts your words" in text
    assert "riskier" not in text
    assert run(repo, "triage") == 0
    out = capsys.readouterr().out
    assert "riskier 0." not in out and "goes beyond your words" in out
