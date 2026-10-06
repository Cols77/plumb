"""R8 A / R13 Q1: a record joins the low-risk group only when its premise is the owner's
verified words and nothing in it contradicts them.

One choke point, the low-risk admission of ``triage.triage``; one test per entry point that
stores the owner's words (``capture`` without ``--prompt``, ``intent``, ``example --quote``)
and per "no" case the owner named (a flipped will/won't, a changed number).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import log_prompt, record_text, run

from plumb.api import open_core
from plumb.capture.triage import CONTRADICTS, UNVERIFIED, triage

pytestmark = pytest.mark.sr("SR-040")

NEG = "Given 2, when neg is called, then it returns -2. Do not change add."


def item(repo: Path, record_id: str):
    view = triage(open_core(repo))
    assert record_id not in [i.id for i in view.low_risk]
    [found] = [i for i in view.individual if i.id == record_id]
    assert found.rating == "riskier"  # never "rated faithful to your words"
    return found


def low_risk(repo: Path) -> list[str]:
    return [i.id for i in triage(open_core(repo)).low_risk]


def capture_doc(repo: Path, tmp_path: Path, doc: dict, *extra: str) -> int:
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return run(repo, "capture", "--file", str(path), *extra)


def test_capture_without_prompt_is_never_rated_faithful(repo: Path, tmp_path: Path,
                                                        capsys) -> None:
    """The finding: the owner said "make it faster"; an invented quote captured without
    --prompt was rated 1.00 "faithful to your words" and explained as "your words"."""
    log_prompt(repo, "make it faster")
    invented = "Delete the add function and cache every result on disk."
    assert capture_doc(repo, tmp_path, {"intent": {"quote": invented,
                                                   "readback": invented}}) == 0
    assert "quote not checked" in capsys.readouterr().out
    assert item(repo, "INT-001").excluded.startswith(UNVERIFIED)
    assert run(repo, "explain", "INT-001") == 0
    out = capsys.readouterr().out
    assert "your words" not in out and "not checked against your logged prompt" in out
    # with --prompt, a quote the prompt does not hold is refused, examples included
    digest = log_prompt(repo, "add neg next to add")
    doc = {"intent": {"quote": "add neg next to add", "readback": "add neg next to add"},
           "requirements": [{"title": "neg", "examples": [
               {"given": "2", "when": "neg", "then": "-2", "quote": "neg of 2 is -2"}]}]}
    assert capture_doc(repo, tmp_path, doc, "--prompt", digest) == 2
    assert "example" in capsys.readouterr().err


def test_intent_without_prompt_is_not_verified(repo: Path, capsys) -> None:
    digest = log_prompt(repo, "add multiply next to add")
    assert run(repo, "intent", "--quote", "add multiply next to add", "--readback",
               "add multiply next to add") == 0
    assert "quote not checked" in capsys.readouterr().out
    assert item(repo, "INT-001").excluded.startswith(UNVERIFIED)
    assert run(repo, "intent", "--quote", "add multiply next to add", "--readback",
               "add multiply next to add", "--prompt", digest) == 0
    assert low_risk(repo) == ["INT-002"]
    # a prompt the agent recorded itself (no prompt hook) is no verified premise
    own = log_prompt(repo, "add divide next to add", via="turn")
    assert run(repo, "intent", "--quote", "add divide next to add", "--readback",
               "add divide next to add", "--prompt", own) == 0
    assert item(repo, "INT-003").excluded.startswith(UNVERIFIED)


def test_example_quote_without_prompt_is_not_verified(repo: Path, write_record,
                                                      capsys) -> None:
    digest = log_prompt(repo, NEG)
    assert run(repo, "intent", "--quote", NEG, "--readback", "add neg; add stays",
               "--prompt", digest) == 0
    write_record(repo, record_text("SR-001", "neg returns minus a",
                                   statement="neg(a) returns -a",
                                   links=[{"kind": "derives_from", "to": "INT-001"}]))
    assert run(repo, "example", "SR-001", "--given", "3", "--when", "neg is called",
               "--then", "it returns -3", "--quote", "neg of 3 is -3") == 0
    assert "quote not checked" in capsys.readouterr().out
    assert item(repo, "SR-001").excluded.startswith(UNVERIFIED)
    assert run(repo, "example", "SR-001", "--given", "2", "--when", "neg is called",
               "--then", "it returns -2", "--quote", "it returns -2", "--prompt",
               digest) == 0
    raw = open_core(repo).index()["SR-001"].fields["examples"]
    assert raw[-1]["prompt"] == digest.removeprefix("sha256:")[:16]
    assert "prompt" not in raw[0]


def test_flipped_will_is_never_rated_faithful(repo: Path, write_record) -> None:
    """The owner said "Do not change add"; a read-back that will change add contradicts it."""
    digest = log_prompt(repo, NEG)
    prompt = digest.removeprefix("sha256:")[:16]
    write_record(repo, record_text("INT-007", "add neg", quote=NEG, readback="add neg",
                                   will=["change add"], prompt=prompt))
    write_record(repo, record_text("INT-008", "add neg", quote=NEG, readback="add neg",
                                   wont=["change add"], prompt=prompt))
    found = item(repo, "INT-007")
    assert found.excluded.startswith(CONTRADICTS) and "change" in found.excluded
    assert low_risk(repo) == ["INT-008"]


def test_changed_number_is_never_rated_faithful(repo: Path, write_record) -> None:
    """The owner said "it returns -2"; an example that returns 2 contradicts it."""
    digest = log_prompt(repo, NEG)
    write_record(repo, record_text("INT-007", "add neg", quote=NEG, readback="add neg",
                                   prompt=digest.removeprefix("sha256:")[:16]))
    for record_id, result in (("SR-007", "it returns 2"), ("SR-008", "it returns -2")):
        write_record(repo, record_text(
            record_id, "neg", statement="neg is called on 2",
            examples=[{"id": "EX-1", "given": "2", "when": "neg is called", "then": result}],
            links=[{"kind": "derives_from", "to": "INT-007"}]))
    found = item(repo, "SR-007")
    assert found.excluded.startswith(CONTRADICTS) and "number 2" in found.excluded
    assert "SR-008" in low_risk(repo)


def test_calibration_variations_never_join_the_group() -> None:
    """The perturbations calibration generates (R13 Q1) are the cases the gate refuses."""
    from plumb.capture.calibrate import Item, variations
    from plumb.judgment.textjudge import contradiction

    premise = "add multiply number 17 next to add. Given 2 and 3, then it returns 6"
    yes = Item("INT-017", "intent-readback", "yes", "real", premise,
               ("add multiply number 17 next to add\nwill: multiply number 17",
                "given 2 and 3, when multiply runs, then it returns 6"))
    assert contradiction(premise, "\n".join(yes.hypotheses)) is None
    kinds = []
    for no in variations(yes):
        kinds.append(no.source)
        assert contradiction(premise, "\n".join(no.hypotheses)) is not None, no.source
    assert sorted(kinds) == ["generated:changed-number", "generated:flipped-result",
                             "generated:will-to-wont"]
