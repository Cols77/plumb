"""R4: cards answered in prose (SR-101 EX-11, SR-103 EX-9 and EX-10, SR-105)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from understand.fakes import as_worker
from understand.test_read_apply import (
    approvals,
    entries_of,
    write_applied,
)
from understand.test_read_job import (
    SESSION,
    log_prompt,
    make_core,
    open_card,
    record_text,
)

from plumb.api import open_core
from plumb.contracts import CardState, ClarifyQuestion
from plumb.understand import effects, read

pytestmark = pytest.mark.sr("SR-101")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(n) for n in (2, 3, 40, 41)]
                     + [record_text(300 + n) for n in range(18)])


@pytest.fixture
def handled(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Fake effect handlers for the card kinds of the other lanes; what each was given."""
    calls: list[dict] = []
    effects.handler_for("beyond")      # load the kind modules first, or they replace the fakes
    for card_kind in ("beyond", "contradicts", "clarify", "couldnt_check", "trial"):
        monkeypatch.setitem(effects.HANDLERS, card_kind,
                            lambda *, _k=card_kind, **kw: calls.append({"kind": _k, **kw}))
    return calls


def card(card_id: str, card_kind: str, questions: list[ClarifyQuestion], *,
         resolutions: tuple[str, ...] = ()) -> CardState:
    return CardState(id=card_id, kind=card_kind, topic=f"topic {card_id}", issue="an issue",
                     resolutions=resolutions, questions=tuple(questions))


def pinned(core, each: CardState) -> CardState:
    """The card as plumb makes it: each question holds the version of its record it showed."""
    index = core.index()
    return dataclasses.replace(each, questions=tuple(
        dataclasses.replace(q, hash=q.hash or (index[q.record].hash if q.record in index else ""))
        for q in each.questions))


def answer(core, cards: list[CardState], message: str, entries: list[dict]):
    """Open the cards, log the message, build and apply the reader's scripted entries."""
    for each in cards:
        open_card(core, pinned(core, each))
    digest = log_prompt(core, message)
    job = read.build(core, SESSION, message={"digest": digest, "text": message})
    assert job is not None
    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": entries})
    write_applied(core, applied)
    return open_core(core.root), applied, job


def e(item: str, said: str, evidence: str, confidence: float = 0.95, **extra) -> dict:
    return {"id": item, "hash": "", "answer": said, "evidence": evidence,
            "confidence": confidence, **extra}


def one_question(card_id: str, card_kind: str, resolutions: tuple[str, ...]) -> CardState:
    return card(card_id, card_kind, [ClarifyQuestion(id="q", text="keep it?",
                                                     resolutions=resolutions)],
                resolutions=resolutions)


def test_ex11_keep_drop_reword_and_two_versions_map(core, handled) -> None:
    keep = ("keep it", "drop it", "reword")
    versions = ("the first version", "the second version")
    cases = [("keep it", "accepted", None, "beyond", keep),
             ("drop it", "rejected", None, "beyond", keep),
             ("reword to say weekly", "change", "weekly", "beyond", keep),
             ("the second, plus the first's date", "change",
              "the second version with the first's date", "contradicts", versions)]
    for n, (message, said, change, card_kind, resolutions) in enumerate(cases):
        handled.clear()
        after, applied, _ = answer(
            core, [one_question(f"c{n}", card_kind, resolutions)], message,
            [e(f"c{n}/q", said, message, change=change)])
        (call,) = handled
        assert call["kind"] == card_kind and call["card"].id == f"c{n}"
        assert call["entry"]["answer"] == said and call["entry"]["change"] == change
        assert call["accepted"] is (said == "accepted")
        (state,) = [c for c in applied.cards if c.id == f"c{n}"]
        assert state.status == "answered" and state.answers[0].question == "q"
        assert state.answers[0].answer.startswith(said if said != "change" else "change:")
        assert f"c{n}" in applied.closed


def trial_card(card_id: str, ids: list[str], card_kind: str = "trial") -> CardState:
    return card(card_id, card_kind, [
        ClarifyQuestion(id=f"q{n}", text=f"settle {i}?", resolutions=("yes", "no"), record=i)
        for n, i in enumerate(ids)])


def test_sr105_ex5_yes_yes_no_third_rejected_as_misreading(core, handled) -> None:
    message = "yes to the first two, no to the third"
    after, applied, _ = answer(core, [trial_card("t1", ["SR-002", "SR-003", "SR-040"])],
                               message, [
        e("t1/q0", "accepted", "yes to the first two"),
        e("t1/q1", "accepted", "yes to the first two"),
        e("t1/q2", "rejected", "no to the third", rejection="misread")])
    assert set(approvals(after)) == {"SR-002", "SR-003"}
    assert all(p["label"] == "yes" for p in approvals(after).values())
    (rejection,) = entries_of(after, "rejection")
    assert rejection.payload["reason"] == "capture-error"
    assert rejection.payload["records"][0]["id"] == "SR-040"
    assert [h["card"].id for h in handled] == ["t1", "t1", "t1"]


def test_sr103_ex9_all_three_questions_mapped_in_one_message(core, handled) -> None:
    clarify = card("k1", "clarify", [
        ClarifyQuestion(id=f"q{n}", text=f"question {n}", resolutions=("a", "b"))
        for n in range(3)])
    message = "CSV, everything, and weekly"
    _, applied, _ = answer(core, [clarify], message, [
        e("k1/q0", "change", "CSV", change="CSV"),
        e("k1/q1", "change", "everything", change="everything"),
        e("k1/q2", "change", "weekly", change="weekly")])
    (state,) = applied.cards
    assert [a.answer for a in state.answers] == ["change: CSV", "change: everything",
                                                  "change: weekly"]
    assert state.status == "answered" and "k1" in applied.closed
    assert [h["entry"]["change"] for h in handled] == ["CSV", "everything", "weekly"]


def test_sr103_ex10_no_wait_maps_to_rejected(core, handled) -> None:
    couldnt = one_question("w1", "couldnt_check", ("Build anyway", "Wait"))
    _, applied, _ = answer(core, [couldnt], "no, wait", [e("w1/q", "rejected", "no, wait")])
    (call,) = handled
    assert call["entry"]["answer"] == "rejected" and call["accepted"] is False


def test_build_anyway_below_the_threshold_is_not_accepted(core, handled) -> None:
    couldnt = one_question("w1", "couldnt_check", ("Build anyway", "Wait"))
    _, applied, _ = answer(core, [couldnt], "i guess", [
        e("w1/q", "accepted", "i guess", confidence=0.6)])
    assert handled == [] and applied.cards == ()


def test_read_registers_stale_link() -> None:
    assert effects.handler_for("stale_link") is not None


def test_a_record_on_a_card_is_confirmed_only_by_the_cards_answer(core, handled) -> None:
    from understand.test_read_job import state

    state(core, ["SR-002"])                      # the record is also in the stated set
    _, applied, _ = answer(core, [trial_card("t1", ["SR-002"])], "ok",
                               [e("SR-002", "accepted", "ok")])
    (call,) = handled
    assert call["card"].id == "t1" and call["accepted"] is True
    assert "t1" in applied.closed
