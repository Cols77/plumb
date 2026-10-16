"""Calibration labels from the owner's answers (task 7 of the judge-approval plan, SR-252).
When a re-judge after a question round says the owner's answer corrected the judge's reading,
one ``capture-error`` rejection pins the record at the asked hash with the premise, the parts
and JEV's score logged at judgment time: calibration counts it as a real 'no' with no new model
call. An approval citing the owner's answers with no correction counts as 'yes'. ``jev status``
shows, per kind, the owner's answers, the real and generated 'no' examples and the threshold.
JEV and the model are stubs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from capture_helpers import JevStub, run, use_jev
from jev_fixtures import default_noul, owner_decisions
from understand import test_judge_cascade
from understand.fakes import FakeDispatcher
from understand.test_cascade_fast_track import judged, write
from understand.test_judge_cascade import StubJev, configure
from understand.test_round_approval import ASK, model_says, owner_answers

from plumb.api import open_core
from plumb.capture.calibrate import calibrate, labelled_set

world = test_judge_cascade.world   # INT-001 and SR-001 from the owner's logged MESSAGE


def corrected_by(record_id: str) -> FakeDispatcher:
    """The judge model after the round: the owner's answer shows the record misread them."""
    return FakeDispatcher({"judge": {"verdicts": [
        {"id": record_id, "verdict": "contradicts", "confidence": 0.2, "beyond": [],
         "contradicts": ["the owner meant every page"], "clear": False,
         "answer_corrects": True}]}})


@pytest.mark.sr("SR-252")
def test_ex4_a_correction_in_the_question_tool_is_a_real_no_with_the_logged_score(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-252 EX-4: given the owner corrects the judge model's interpretation in the question
    tool, when calibration next runs, then the correction counts as a real 'no' paired with
    JEV's score logged at judgment time, with no new model call."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    configure(world)
    asked_hash = open_core(world).index()["SR-001"].hash
    answer = owner_answers(world, ["SR-001"], answer="Every page")
    _, _, applied = judged(open_core(world), ["SR-001"], StubJev(0.4), corrected_by("SR-001"))
    [rejection] = [e["payload"] for e in applied.entries if e["kind"] == "rejection"]
    assert (rejection["by"], rejection["reason"]) == ("owner-answer", "capture-error")
    assert rejection["answers"] == [answer]
    [pinned] = rejection["records"]
    assert (pinned["id"], pinned["hash"], pinned["kind"]) == (
        "SR-001", asked_hash, "example-restatement")
    assert pinned["jev_score"] == 0.4
    assert ASK in pinned["premise"] and "Answer: Every page" in pinned["premise"]
    assert pinned["hypotheses"]
    write(world, applied)

    core = open_core(world)
    [item] = [i for i in labelled_set(core) if i.record == "SR-001"]
    assert (item.label, item.source, item.hash, item.score) == ("no", "answer", asked_hash, 0.4)
    jev = StubJev(0.99)
    entry, results = calibrate(core, backend=jev)
    assert jev.calls == []                                     # no new model call
    assert entry.payload["source"] == "logged"
    result = results["example-restatement"]
    assert (result.real_negatives, result.answers) == (1, 1)
    assert result.threshold == pytest.approx(0.401)            # above the pinned 0.4


@pytest.mark.sr("SR-252")
def test_an_approval_on_the_owners_answers_with_no_correction_is_a_yes(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An approval citing the owner's answers, with no correction, counts as 'yes' (source
    ``answer``), scored by JEV's score logged at that judgment."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    configure(world)
    owner_answers(world, ["SR-001"])
    _, _, applied = judged(open_core(world), ["SR-001"], StubJev(0.85),
                           model_says(("SR-001", 0.8, True)))
    assert [e for e in applied.entries if e["kind"] == "rejection"] == []
    write(world, applied)
    core = open_core(world)
    [item] = [i for i in labelled_set(core) if i.record == "SR-001"
              and not i.source.startswith("gen")]
    assert (item.label, item.source) == ("yes", "answer")
    _, results = calibrate(core, backend=StubJev(0.1))
    result = results["example-restatement"]
    assert (result.positives, result.answers, result.recall) == (1, 1, 0.0)


@pytest.mark.sr("SR-252")
def test_too_few_real_no_examples_show_not_passing_with_the_four_counts(
        repo: Path, write_record, monkeypatch, capsys) -> None:
    """A fixture with too few real 'no' examples: ``jev status`` shows the kind not passing,
    with the owner's answers, the real 'no' examples, the generated ones and the threshold."""
    stub = JevStub(default_noul)
    try:
        use_jev(repo, stub, monkeypatch)
        owner_decisions(repo, write_record, intents=20, revoked=1)
        assert run(repo, "jev", "calibrate") == 1
        capsys.readouterr()
        assert run(repo, "jev", "status") == 0
        out = capsys.readouterr().out
    finally:
        stub.close()
    line = next(x for x in out.splitlines() if x.strip().startswith("intent-readback:"))
    assert re.search(r"intent-readback: not passing; 21 of your decisions \(0 from your "
                     r"answers\), 'no' examples 1 real \+ 1 generated counted \(of \d+\); "
                     r"threshold 0\.\d{3}$", line.strip()), line
