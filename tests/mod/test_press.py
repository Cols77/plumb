"""SP7 slice 4: the Python side of the press (sp7-realign-sp8 C4-C6, slice 4 row): offers are
recorded when cards are drawn, ``plumb mod press --offer --choice`` with the key on stdin answers
through the one answer path, every button is logged, and only a press on a drawn offer at the
shown version confirms (SR-086, SR-112 EX-7, DEC-032, DEC-034)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mod.helpers import DIGEST, KEY, OTHER_KEY, SESSION, kinds, run_mod, sample_card
from understand.test_read_job import make_core, open_card, record_text

from plumb import confirm
from plumb.api import open_core
from plumb.understand import cards, cardstore, read

pytestmark = pytest.mark.sr("SR-086")

CONFIRM, NO, FIX_IT, ASK_CHANGE, LEAVE_OPEN = 0, 1, 2, 3, 4     # a trial card's buttons, in order


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(n) for n in range(1, 3)])


@pytest.fixture
def drawn(core, monkeypatch, capsys):
    """The panel registered, a trial card for SR-001 open, the cards drawn."""
    open_card(core, sample_card(core, "SR-001"))
    assert run_mod(monkeypatch, capsys, core.root, "hello",
                   stdin={"key_digest": DIGEST})[0] == 0
    code, answer, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert code == 0
    return answer


def _offer(answer, card_id: str = "card:SR-001") -> dict:
    (card,) = [c for c in answer["cards"] if c["id"] == card_id]
    return card["offers"][0]


def _press(monkeypatch, capsys, root: Path, offer: str, choice: int, stdin=None):
    return run_mod(monkeypatch, capsys, root, "press", "--offer", offer, "--choice",
                   str(choice), stdin={"key": KEY} if stdin is None else stdin)


def _edit(root: Path, n: int = 1) -> None:
    path = root / ".plumb" / "requirements" / f"SR-{n:03d}.md"
    path.write_text(path.read_text(encoding="utf-8").replace(f"statement {n}",
                                                             f"statement {n}, reworded"),
                    encoding="utf-8")


def _confirmation(root: Path, rid: str = "SR-001") -> str:
    return open_core(root).status([rid])[rid].confirmation


def _status(root: Path, card_id: str = "card:SR-001") -> str:
    (card,) = [c for c in cardstore.own_cards(root, SESSION) if c.id == card_id]
    return card.status


# ---------------------------------------------------------------- drawing records the offers


def test_drawing_records_one_offer_per_question_with_the_buttons(core, drawn) -> None:
    offer = _offer(drawn)
    record = core.index()["SR-001"]
    assert offer["record"] == "SR-001" and offer["hash"] == record.hash
    assert offer["offer_id"].startswith("sha256:") and offer["drawn_at"]
    assert [(b["index"], b["answer"]) for b in offer["buttons"]] == [
        (0, "accepted"), (1, "rejected"), (2, "change"), (3, "change"), (4, "open")]
    assert [b["label"] for b in offer["buttons"]] == [
        "Yes", "No", "Fix it", "Ask for a change", "Leave open"]
    (card,) = drawn["cards"]
    card_evidence = cardstore.own_cards(core.root, SESSION)[0].evidence
    assert card["repeats"] is True
    logged = [e for e in open_core(core.root).events() if e.kind == "offer"]
    assert [e.payload["offer"] for e in logged] == [offer["offer_id"]]
    assert logged[0].payload["hash"] == record.hash and logged[0].payload["key_digest"] == DIGEST


def test_drawing_again_keeps_the_first_offer(core, drawn, monkeypatch, capsys) -> None:
    code, again, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert code == 0 and _offer(again) == _offer(drawn)
    assert kinds(core.root).count("offer") == 1


# ---------------------------------------------------------------- refused: nothing written


@pytest.mark.parametrize("stdin", [{"key": OTHER_KEY}, {}, {"key": ""}, {"key": "zz"}])
def test_wrong_key_or_no_key_is_refused_and_nothing_written(core, drawn, monkeypatch, capsys,
                                                            stdin) -> None:
    before = (kinds(core.root), cardstore.own_cards(core.root, SESSION))
    code, answer, _ = _press(monkeypatch, capsys, core.root, _offer(drawn)["offer_id"],
                             CONFIRM, stdin=stdin)
    assert code == 3 and answer is None
    assert (kinds(core.root), cardstore.own_cards(core.root, SESSION)) == before
    assert _confirmation(core.root) == "proposed"


def test_under_the_session_marker_the_press_is_refused(core, drawn, monkeypatch,
                                                       capsys) -> None:
    before = kinds(core.root)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    code, _, err = _press(monkeypatch, capsys, core.root, _offer(drawn)["offer_id"], CONFIRM)
    assert code == 3 and "agent" in err
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    assert kinds(core.root) == before and _confirmation(core.root) == "proposed"


def test_no_panel_registered_refuses_drawing_and_pressing(core, monkeypatch, capsys) -> None:
    open_card(core, sample_card(core, "SR-001"))
    assert run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})[0] == 3
    assert _press(monkeypatch, capsys, core.root, "sha256:" + "0" * 64, CONFIRM)[0] == 3
    assert not (core.root / ".plumb" / "session" / SESSION / "offers").exists()
    assert {"offer", "card-press", "approval"}.isdisjoint(kinds(core.root))


def test_an_offer_never_drawn_is_refused(core, drawn, monkeypatch, capsys) -> None:
    before = kinds(core.root)
    code, _, _ = _press(monkeypatch, capsys, core.root, "sha256:" + "0" * 64, CONFIRM)
    assert code == 3 and kinds(core.root) == before


def test_a_button_the_offer_does_not_have_is_a_usage_error(core, drawn, monkeypatch,
                                                           capsys) -> None:
    before = kinds(core.root)
    assert _press(monkeypatch, capsys, core.root, _offer(drawn)["offer_id"], 9)[0] == 2
    assert kinds(core.root) == before


# ---------------------------------------------------------------- the buttons


def test_confirm_writes_by_owner_via_button_at_the_shown_hash(core, drawn, monkeypatch,
                                                              capsys) -> None:
    offer = _offer(drawn)
    code, answer, _ = _press(monkeypatch, capsys, core.root, offer["offer_id"], CONFIRM)
    assert code == 0
    assert answer["confirmed"] == ["SR-001"] and answer["left_out"] == []
    assert answer["answer"] == "accepted" and answer["prefill"] is None
    assert "Requirement 1" in answer["line"] and "SR-001" in answer["model_note"]
    events = [e for e in open_core(core.root).events() if e.kind in ("card-press", "approval")]
    assert [e.kind for e in events][-2:] == ["card-press", "approval"]
    press, approval = events[-2:]
    assert press.payload["answer"] == "accepted" and press.payload["choice"] == CONFIRM
    payload = approval.payload
    assert (payload["by"], payload["via"], payload["offer"], payload["card"]) == (
        "owner", "button", offer["offer_id"], "card:SR-001")
    assert payload["key_digest"] == DIGEST and approval.marker == "none"
    assert [(r["id"], r["hash"]) for r in payload["records"]] == [("SR-001", offer["hash"])]
    assert confirm.entry_problem(approval, set(), (), open_core(core.root)) is None
    assert _confirmation(core.root) == "confirmed"
    assert open_core(core.root).status(["SR-001"])["SR-001"].approved_by == "owner"


def test_sr135_ex2_a_reworded_button_still_applies_its_stored_answer(
        core, drawn, monkeypatch, capsys) -> None:
    from plumb.mod.offers import offer_path
    from plumb.understand import files

    offer = _offer(drawn)
    path = offer_path(core.root, SESSION, offer["offer_id"])
    data = files.read_json(path)
    data["buttons"][CONFIRM]["label"] = "Sure, carry on"        # reworded; the answer is stored
    files.write_json_atomic(path, data)
    code, answer, _ = _press(monkeypatch, capsys, core.root, offer["offer_id"], CONFIRM)
    assert code == 0 and answer["confirmed"] == ["SR-001"]
    assert _confirmation(core.root) == "confirmed"


def test_sr130_ex1_a_readback_press_confirms_its_requests_records(
        core, monkeypatch, capsys) -> None:
    """The read-back's offer names the request's records; one Yes confirms them all, and the
    button approval passes its re-check because the offer listed them."""
    from plumb.understand import clarify

    digest = "sha256:" + "ab" * 32
    (core.root / ".plumb" / "intents" / "INT-001.md").write_text(
        "---\nid: INT-001\ntitle: Export\nquote: export it\nreadback: Export.\n"
        f"prompt: {digest.removeprefix('sha256:')[:16]}\n---\n", encoding="utf-8")
    core = open_core(core.root)
    card = clarify._readback_card(core.root, digest, "export it", {"proposal": "Export it."}, [])
    open_card(core, card)
    run_mod(monkeypatch, capsys, core.root, "hello", stdin={"key_digest": DIGEST})
    _, drawn, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    offer = _offer(drawn, card.id)
    code, answer, _ = _press(monkeypatch, capsys, core.root, offer["offer_id"], 0)
    assert code == 0 and answer["confirmed"] == ["INT-001"]
    approval = [e for e in open_core(core.root).events() if e.kind == "approval"][-1]
    assert confirm.entry_problem(approval, set(), (), open_core(core.root)) is None


def test_sr130_a_readback_drawn_before_its_records_exist_confirms_only_what_it_showed(
        core, monkeypatch, capsys) -> None:
    from plumb.understand import clarify

    digest = "sha256:" + "ab" * 32
    card = clarify._readback_card(core.root, digest, "export it", {"proposal": "Export it."}, [])
    open_card(core, card)
    run_mod(monkeypatch, capsys, core.root, "hello", stdin={"key_digest": DIGEST})
    _, first, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    (core.root / ".plumb" / "intents" / "INT-001.md").write_text(
        "---\nid: INT-001\ntitle: Export\nquote: export it\nreadback: Export.\n"
        f"prompt: {digest.removeprefix('sha256:')[:16]}\n---\n", encoding="utf-8")
    _, second, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    old, new = _offer(first, card.id), _offer(second, card.id)
    assert old["offer_id"] != new["offer_id"]                  # the records changed: drawn again
    assert _confirmation(core.root, "INT-001") == "proposed"
    _, answer, _ = _press(monkeypatch, capsys, core.root, new["offer_id"], 0)
    assert answer["confirmed"] == ["INT-001"]


def test_a_changed_record_is_left_out_and_re_carded(core, monkeypatch, capsys) -> None:
    record = core.index()["SR-001"]
    beyond = cards.beyond_card(core.index(), record, ["says more"],
                               {"messages": [{"text": "keep it short"}]})
    open_card(core, beyond)
    run_mod(monkeypatch, capsys, core.root, "hello", stdin={"key_digest": DIGEST})
    _, drawn, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    offer = _offer(drawn, beyond.id)
    _edit(core.root)
    code, answer, _ = _press(monkeypatch, capsys, core.root, offer["offer_id"], 0)
    assert code == 0
    assert answer["confirmed"] == [] and answer["status"] == "closed"
    assert answer["left_out"] == [{"id": "SR-001", "title": "Requirement 1",
                                   "reason": "changed since it was shown"}]
    assert "changed since it was shown" in answer["line"]
    (fresh_id,) = answer["fresh_cards"]
    assert fresh_id.startswith("choice:SR-001:")        # which version do you mean
    assert "approval" not in kinds(core.root) and "card-press" in kinds(core.root)
    assert _confirmation(core.root) == "proposed"
    now = open_core(core.root).index()["SR-001"].hash
    held = {c.id: c for c in cardstore.own_cards(core.root, SESSION)}
    assert held[beyond.id].status == "closed"
    assert held[fresh_id].questions[0].hash == now != offer["hash"]
    # the fresh card is drawn as a new offer at the version it has now
    _, again, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert _offer(again, fresh_id)["hash"] == now


def test_leave_open_writes_no_approval_and_stops_the_card_repeating(core, drawn, monkeypatch,
                                                                    capsys) -> None:
    code, answer, _ = _press(monkeypatch, capsys, core.root, _offer(drawn)["offer_id"],
                             LEAVE_OPEN)
    assert code == 0 and answer["status"] == "left_open" and answer["confirmed"] == []
    assert answer["prefill"] is None and "Left open" in answer["line"]
    assert [k for k in kinds(core.root) if k in ("card-press", "approval", "rejection")] \
        == ["card-press"]
    assert _status(core.root) == "left_open" and _confirmation(core.root) == "proposed"
    # DEC-034: not at the end of a turn, still listed under what awaits
    assert cardstore.load(core.root, SESSION) == []
    _, listed, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    (card,) = listed["cards"]
    assert card["status"] == "left_open" and card["repeats"] is False
    # ... until its record changes
    _edit(core.root)
    _, listed, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert listed["cards"][0]["status"] == "open" and listed["cards"][0]["repeats"] is True
    assert [c.id for c in cardstore.load(core.root, SESSION)] == ["card:SR-001"]


def test_ask_for_a_change_writes_no_approval_and_returns_the_prefill(core, drawn, monkeypatch,
                                                                     capsys) -> None:
    code, answer, _ = _press(monkeypatch, capsys, core.root, _offer(drawn)["offer_id"],
                             ASK_CHANGE)
    assert code == 0 and answer["status"] == "change_requested"
    assert answer["prefill"] == "Change to 'Requirement 1': "
    assert answer["confirmed"] == [] and "approval" not in kinds(core.root)
    (press,) = [e for e in open_core(core.root).events() if e.kind == "card-press"]
    assert press.payload["answer"] == "change"
    # the owner's next message is read against it (SR-086 EX-7)
    assert [c.id for c in cardstore.load(core.root, SESSION)] == ["card:SR-001"]
    assert [i["card"] for i in read.card_items(open_core(core.root), SESSION)] \
        == ["card:SR-001"]


def test_every_button_is_logged_once(core, drawn, monkeypatch, capsys) -> None:
    offer = _offer(drawn)["offer_id"]
    _press(monkeypatch, capsys, core.root, offer, LEAVE_OPEN)
    _press(monkeypatch, capsys, core.root, offer, ASK_CHANGE)
    _press(monkeypatch, capsys, core.root, offer, NO)
    presses = [e.payload for e in open_core(core.root).events() if e.kind == "card-press"]
    assert [(p["choice"], p["answer"]) for p in presses] == [
        (LEAVE_OPEN, "open"), (ASK_CHANGE, "change"), (NO, "rejected")]
    assert all(p["session"] == SESSION and p["offer"] == offer and p["key_digest"] == DIGEST
               for p in presses)
    assert "approval" not in kinds(core.root)


# ---------------------------------------------------------------- the re-check


def _forged(core, **payload):
    record = core.index()["SR-001"]
    body = {"by": "owner", "via": "button", "session": SESSION, "offer": "sha256:" + "1" * 64,
            "key_digest": DIGEST, "card": "card:SR-001", "question": "confirm",
            "records": [{"id": "SR-001", "hash": record.hash}], **payload}
    return core.log_append("events", "approval", body)


def test_a_hand_written_button_approval_is_rejected(core, drawn) -> None:
    from plumb.validate import validate

    entry = _forged(core)
    assert "offer was not drawn" in confirm.entry_problem(entry, set(), (), core)
    assert _confirmation(core.root) == "proposed"
    findings = [f for f in validate(open_core(core.root)) if f.code == "approval"]
    assert any("button approval" in f.message for f in findings)


def test_a_button_approval_copying_a_drawn_offer_for_another_version_is_rejected(
        core, drawn) -> None:
    offer = _offer(drawn)
    other = _forged(core, offer=offer["offer_id"],
                    records=[{"id": "SR-002", "hash": core.index()["SR-002"].hash}])
    assert "did not show SR-002" in confirm.entry_problem(other, set(), (), core)
    wrong_key = _forged(core, offer=offer["offer_id"], key_digest="f" * 64)
    assert "key" in confirm.entry_problem(wrong_key, set(), (), core)
    assert _confirmation(core.root, "SR-002") == "proposed"
    assert _confirmation(core.root) == "proposed"


def test_a_button_approval_written_before_its_offer_was_drawn_is_rejected(
        core, monkeypatch, capsys) -> None:
    open_card(core, sample_card(core, "SR-001"))
    run_mod(monkeypatch, capsys, core.root, "hello", stdin={"key_digest": DIGEST})
    from plumb.understand import files

    offer = files.digest_of(["card:SR-001", "confirm", core.index()["SR-001"].hash])
    early = _forged(core, offer=offer)                 # names the offer before it is drawn
    run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    fresh = open_core(core.root)
    assert "not drawn in that session before it" in confirm.entry_problem(early, set(), (),
                                                                          fresh)
    assert _confirmation(core.root) == "proposed"
