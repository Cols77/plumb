"""CAPTURE SR-040 / SR-042 / SR-097: faithfulness is judged on what the read-back claims as
the owner's, against the owner's whole words."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from capture_helpers import log_prompt, record_text

from iaso.api import open_core
from iaso.understand.claim import _Prompts, claim

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
    from iaso.approvals import approve
    from iaso.capture.calibrate import labelled_set

    intent(write_record, repo)
    approve(open_core(repo), ["INT-001"])
    [item] = [i for i in labelled_set(open_core(repo)) if i.label == "yes"]
    _, premise, hypothesis = _claim(repo, "INT-001")
    assert item.premise == premise == LONG and item.hypotheses == (hypothesis,)
