"""SR-098: a mixed answer list confirms its yes items (R2, decision 2).

One owner message answers several records: some "yes", some with a correction. A correction
is placed on the record an ID labels at the start of its line or answer item ("INT-016: We
don't want ..."), even when the ID ends one line and the correction begins the next, so the
relay confirms the yes records and holds back only the records the corrections name. A
correction or reservation that names nothing still holds back every record, and a malformed
ID (INT-24) is neither an objection nor a plain-words reference.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import approvals
from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-098")

IDS = ["INT-006", "INT-013", "INT-016"]
ANSWER = ("INT-006: yes. INT-013: no. I don't know what to do with pi-agent-factory just yet. "
          "INT-016: We don't want token budget.")


def _record(record_id: str, title: str, quote: str) -> str:
    return f"---\nid: {record_id}\ntitle: {title}\nquote: {quote}\n---\n"


@pytest.fixture
def project(repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    write_record(repo, _record("INT-006", "Intent cards come first", "cards first"))
    write_record(repo, _record("INT-013", "Agents are registered", "register agents"))
    write_record(repo, _record("INT-016", "Spend is capped", "cap the spend"))
    write_record(repo, ("---\nid: SR-097\ntitle: Cards are listed\nstatement: lists cards\n---\n"))
    write_record(repo, ("---\nid: SR-098\ntitle: Mixed answers\nstatement: mixed answers\n---\n"))
    return repo


def _state(root: Path, ids: list[str]) -> None:
    index = open_core(root).index()
    stated = root / ".plumb" / "session" / "stated.json"
    stated.parent.mkdir(parents=True, exist_ok=True)
    stated.write_text(json.dumps({"at": "2026-10-06T02:59:00Z", "session": "s1",
                                  "reply_after_prompt": None,
                                  "records": [{"id": i, "hash": index[i].hash} for i in ids]}),
                      encoding="utf-8")


def _log(root: Path, text: str) -> str:
    digest = approvals.prompt_digest(text)
    prompts = root / ".plumb" / "session" / "prompts.jsonl"
    prompts.parent.mkdir(parents=True, exist_ok=True)
    with prompts.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"digest": digest, "session": "s1",
                                 "at": "2026-10-06T03:00:00Z", "text": text,
                                 "via": "hook"}) + "\n")
    return digest


def _confirmation(root: Path, record_id: str) -> str:
    return open_core(root).status([record_id])[record_id].confirmation


def _relay(root: Path, ids: list[str], words: str, quote: str) -> None:
    approvals.relay(open_core(root), ids, prompt=_log(root, words), quote=quote)


def test_ex1_yes_item_is_confirmed_beside_placed_corrections(project: Path) -> None:
    _state(project, IDS)
    _relay(project, ["INT-006"], ANSWER, "INT-006: yes")
    assert _confirmation(project, "INT-006") == "confirmed"
    assert _confirmation(project, "INT-016") == "proposed"


def test_ex2_corrected_item_is_refused(project: Path) -> None:
    _state(project, IDS)
    with pytest.raises(approvals.Refused, match="INT-016"):
        _relay(project, ["INT-016"], ANSWER, "INT-006: yes")
    assert _confirmation(project, "INT-016") == "proposed"


def test_ex1_owner_scope_holds_back_only_named_records(project: Path) -> None:
    index = open_core(project).index()
    named, objected = approvals.owner_scope(ANSWER, "INT-006: yes", ["yes"], index, IDS)
    assert named == {"INT-006"}
    assert objected == {"INT-013", "INT-016"}


def test_ex3_reservation_naming_nothing_holds_back_every_record(project: Path) -> None:
    _state(project, IDS)
    words = "INT-006: yes. Actually I'd rather sleep on all of this."
    with pytest.raises(approvals.Refused, match="INT-006"):
        _relay(project, ["INT-006"], words, "INT-006: yes")
    assert _confirmation(project, "INT-006") == "proposed"


def test_ex4_correction_is_placed_across_the_line_break(project: Path) -> None:
    _state(project, IDS)
    words = "INT-006: yes\nINT-016:\nWe don't want token budget"
    index = open_core(project).index()
    _, objected = approvals.owner_scope(words, "INT-006: yes", ["yes"], index, IDS)
    assert objected == {"INT-016"}
    _relay(project, ["INT-006"], words, "INT-006: yes")
    assert _confirmation(project, "INT-006") == "confirmed"
    with pytest.raises(approvals.Refused, match="INT-016"):
        _relay(project, ["INT-016"], words, "INT-006: yes")


def test_ex4_unlabelled_correction_after_a_label_line_still_holds_all(project: Path) -> None:
    """A correction under no ID label (a free line) is not placed on a label above it."""
    index = open_core(project).index()
    words = "INT-006: yes\nWe don't want token budget"
    _, objected = approvals.owner_scope(words, "INT-006: yes", ["yes"], index, IDS)
    assert "INT-006" in objected or objected >= {"INT-016"}


def test_ex5_mistyped_id_is_not_an_objection(project: Path) -> None:
    _state(project, ["SR-097", "SR-098"])
    words = "Confirm SR-097, SR-098, INT-24"
    index = open_core(project).index()
    named, objected = approvals.owner_scope(words, "Confirm SR-097, SR-098, INT-24",
                                            ["confirm"], index, ["SR-097", "SR-098"])
    assert objected == set()
    assert {"SR-097", "SR-098"} <= named
    _relay(project, ["SR-098"], words, "Confirm SR-097, SR-098, INT-24")
    assert _confirmation(project, "SR-098") == "confirmed"


def test_ex1_words_of_a_labelled_correction_do_not_hold_back_another_record(
        project: Path, write_record) -> None:
    """INT-006's own text shares words with INT-016's correction: the correction is placed
    by its label, so it holds back INT-016 alone."""
    write_record(project, _record("INT-006", "Token budget shown first",
                                  "token budget pi agent factory"))
    _state(project, IDS)
    index = open_core(project).index()
    named, objected = approvals.owner_scope(ANSWER, "INT-006: yes", ["yes"], index, IDS)
    assert named == {"INT-006"}
    assert objected == {"INT-013", "INT-016"}
    _relay(project, ["INT-006"], ANSWER, "INT-006: yes")
    assert _confirmation(project, "INT-006") == "confirmed"


def test_ex4_line_break_label_with_shared_words(project: Path, write_record) -> None:
    write_record(project, _record("INT-006", "Token budget shown first", "token budget"))
    _state(project, IDS)
    words = "INT-006: yes\nINT-016:\nWe don't want token budget"
    index = open_core(project).index()
    _, objected = approvals.owner_scope(words, "INT-006: yes", ["yes"], index, IDS)
    assert objected == {"INT-016"}


def test_ex3_reservation_after_two_yes_items_holds_back_both(project: Path) -> None:
    _state(project, IDS)
    words = "INT-006: yes. INT-013: yes. Actually I'd rather sleep on all of this."
    with pytest.raises(approvals.Refused, match="INT-006"):
        _relay(project, ["INT-006"], words, "INT-006: yes")
    assert _confirmation(project, "INT-006") == "proposed"


def test_ex3_reservation_after_a_correction_holds_back_every_record(project: Path) -> None:
    _state(project, IDS)
    words = (
        "INT-006: yes. INT-016: We don't want token budget. "
        "Actually I'd rather sleep on all of this."
    )
    with pytest.raises(approvals.Refused, match="INT-006"):
        _relay(project, ["INT-006"], words, "INT-006: yes")
    assert _confirmation(project, "INT-006") == "proposed"
