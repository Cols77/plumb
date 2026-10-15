"""Real card factories retain decisions across redraw, refresh, and restart."""

import dataclasses

import pytest

from plumb import stale
from plumb.api import open_core
from plumb.browser import followup
from plumb.browser.demo import SESSION, seed
from plumb.browser.service import BrowserService
from plumb.contracts import Target
from plumb.mergedriver import conflicts
from plumb.understand import cards, cardstore, files, summary

pytestmark = [pytest.mark.sr("SR-176"), pytest.mark.sr("SR-178")]


@pytest.fixture
def root(tmp_path):
    return seed(tmp_path / "demo")


def shown(ui, card_id):
    return next(c for c in ui.draw(SESSION)["cards"] if c["id"] == card_id)


def payload(card, label, request_id="decision"):
    offer = card["offers"][0]
    button = next(b for b in offer["buttons"] if b["label"] == label)
    return {"offer": offer["offer_id"], "choice": button["index"], "request_id": request_id}


def stale_entry(root, by):
    path = root / "calc.py"
    path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    open_core(root).add_link("SR-001", "implemented_by", Target(path="calc.py", symbol="add"))
    path.write_text("def add(a, b):\n    return a * b\n", encoding="utf-8")
    entry = dict(link="SR-001#0", record="SR-001", path="calc.py", topic="Changed code",
                 issue="Code now multiplies", options=["Keep code", "Reword requirement"],
                 consequences=["Requirement stays unchecked", "Requirement changes"],
                 recommended=0, why="Preserve the current behavior", by=by)
    stale.add_card(root, SESSION, turn=1, **entry)
    return entry


@pytest.mark.parametrize("by", ["owner", "diagnosis"])
@pytest.mark.parametrize("label,status,state", [
    ("Keep code", "answered", "done"),
    ("Ask for a change", "change_requested", "waiting"),
    ("Leave open", "left_open", "left_open"),
])
def test_stale_decisions_survive_redraw_restart_and_identical_evaluation(
        root, by, label, status, state):
    entry = stale_entry(root, by)
    core = open_core(root)
    records = {r.id: r.hash for r in core.index().values()}
    links = core.link_states(["SR-001"])
    ui = BrowserService(root)
    action = payload(shown(ui, "stale:SR-001#0"), label)
    action["text"] = "Preserve my wording."
    result = ui.press(SESSION, action)
    assert result["status"] == ("closed" if label == "Keep code" else status)
    assert shown(ui, "stale:SR-001#0")["state"] == state
    stale.add_card(root, SESSION, turn=2, **entry)
    restarted = BrowserService(root)
    card = shown(restarted, "stale:SR-001#0")
    assert card["status"] == status and card["state"] == state
    assert bool(card["answers"]) == (label == "Keep code")
    if label == "Keep code":
        assert card["answers"][0]["answer"] == "change: Keep code"
    assert restarted.press(SESSION, action)["duplicate"] is True
    assert len(followup.history(root, SESSION)) == 1
    assert followup.read(root, SESSION, action["request_id"])["text"] == action["text"]
    fresh = open_core(root)
    assert {r.id: r.hash for r in fresh.index().values()} == records
    assert fresh.link_states(["SR-001"]) == links
    assert stale.open_card(root, SESSION, entry["link"])["status"] == "open"
    assert len([e for e in fresh.events() if e.kind == "card-press"
                and e.payload.get("card") == card["id"]]) == 1
    assert not any(c.kind == "stale_link" for c in cardstore.own_cards(root, SESSION))


@pytest.mark.parametrize("change", ["question", "target"])
def test_stale_changed_meaning_reopens_a_left_open_decision(root, change):
    entry = stale_entry(root, "diagnosis")
    ui = BrowserService(root)
    ui.press(SESSION, payload(shown(ui, "stale:SR-001#0"), "Leave open"))
    assert shown(ui, "stale:SR-001#0")["state"] == "left_open"
    if change == "question":
        entry["issue"] = "The new code divides instead"
    else:
        (root / "calc.py").write_text("def add(a, b):\n    return a / b\n", encoding="utf-8")
    stale.add_card(root, SESSION, turn=3, **entry)
    card = shown(BrowserService(root), "stale:SR-001#0")
    assert card["status"] == "open" and card["state"] == "waiting"
    assert card["answers"] == []


def test_stale_target_change_in_same_turn_has_a_fresh_answerable_offer(root):
    entry = stale_entry(root, "diagnosis")
    ui = BrowserService(root)
    old = payload(shown(ui, "stale:SR-001#0"), "Keep code", "first")
    ui.press(SESSION, old)
    (root / "calc.py").write_text("def add(a, b):\n    return a / b\n", encoding="utf-8")
    stale.add_card(root, SESSION, turn=1, **entry)
    current = payload(shown(ui, "stale:SR-001#0"), "Keep code", "second")
    assert current["offer"] != old["offer"]
    with pytest.raises(PermissionError, match="changed"):
        ui.press(SESSION, {**old, "request_id": "obsolete"})
    assert ui.press(SESSION, old)["duplicate"] is True
    result = ui.press(SESSION, current)
    assert not result["duplicate"]
    assert ui.press(SESSION, current)["duplicate"] is True
    assert shown(ui, "stale:SR-001#0")["state"] == "done"
    assert len(followup.pending(root, SESSION)) == 2
    assert len([e for e in open_core(root).events() if e.kind == "card-press"
                and e.payload.get("card") == "stale:SR-001#0"]) == 2


def test_invalid_button_never_recovers_a_handoff(root):
    ui = BrowserService(root)
    card = shown(ui, "demo-card-1")
    before = cardstore.own_cards(root, SESSION)
    events = open_core(root).events()
    with pytest.raises(LookupError, match="button 999"):
        ui.press(SESSION, {"offer": card["offers"][0]["offer_id"], "choice": 999,
                           "request_id": "bad", "text": "Never send this to the agent"})
    BrowserService(root)
    assert not followup.pending(root, SESSION)
    assert not followup.history(root, SESSION)
    assert cardstore.own_cards(root, SESSION) == before
    assert open_core(root).events() == events


def test_disappeared_card_unknown_failure_never_recovers_a_handoff(root):
    ui = BrowserService(root)
    card = shown(ui, "demo-card-1")
    action = payload(card, card["offers"][0]["buttons"][0]["label"])
    cardstore.save(root, SESSION, [c for c in cardstore.own_cards(root, SESSION)
                                 if c.id != card["id"]])
    events = open_core(root).events()
    with pytest.raises(LookupError, match="no longer exists"):
        ui.press(SESSION, action)
    BrowserService(root)
    assert followup.read(root, SESSION, action["request_id"])["status"] == "failed"
    assert not followup.pending(root, SESSION)
    assert open_core(root).events() == events


def save_turn(root, card):
    core = open_core(root)
    files.write_json_atomic(files.session_dir(root, SESSION) / summary.DRAWN,
                            [summary._drawn_entry(core, SESSION, card, "open", turn_built=True)])


@pytest.mark.parametrize("stop_redraw", [False, True])
def test_turn_card_leave_then_change_is_waiting_after_restart(root, stop_redraw):
    card = cards.regression_card(open_core(root).index(), "tests/test_export.py::test_export")
    save_turn(root, card)
    ui = BrowserService(root)
    ui.press(SESSION, payload(shown(ui, card.id), "Leave open"))
    assert shown(ui, card.id)["state"] == "left_open"
    if stop_redraw:
        files.write_json_atomic(files.session_dir(root, SESSION) / summary.DRAWN, [
            summary._drawn_entry(open_core(root), SESSION, card, "left_open", turn_built=True)])
    result = ui.press(SESSION, payload(shown(ui, card.id), "Ask for a change", "change"))
    assert result["status"] == "change_requested"
    after = shown(BrowserService(root), card.id)
    assert after["state"] == "waiting" and after["repeats"] and after["offers"]
    assert card.id not in summary.turn_left(root, SESSION)


def test_turn_card_semantic_change_still_refuses_old_offer(root):
    card = cards.regression_card(open_core(root).index(), "tests/test_export.py::test_export")
    save_turn(root, card)
    ui = BrowserService(root)
    action = payload(shown(ui, card.id), "Ask for a change")
    save_turn(root, dataclasses.replace(card, issue="A different failure needs investigation"))
    with pytest.raises(PermissionError, match="changed"):
        ui.press(SESSION, action)


@pytest.mark.parametrize("proposed", [False, True])
def test_conflict_both_only_completes_when_combined_version_applies(root, proposed):
    core = open_core(root)
    if proposed:
        conflicts.propose(core, "IC-001", {"statement": "name, email, address, phone"})
        core = open_core(root)
        save_turn(root, cards.conflict_card(core.index(), conflicts.find(core, "IC-001")))
    path = root / ".plumb/requirements/SR-006.md"
    before = path.read_bytes()
    ui = BrowserService(root)
    card = next(c for c in ui.draw(SESSION)["cards"] if c["kind"] == "conflict")
    result = ui.press(SESSION, payload(card, cards.BOTH))
    after = shown(BrowserService(root), card["id"])
    resolutions = [e for e in open_core(root).events() if e.kind == "conflict-resolution"]
    if proposed:
        assert result["status"] == "closed" and after["state"] == "done"
        assert not after["offers"] and path.read_bytes() != before
        assert not conflicts.open_conflicts(open_core(root))
        assert len(resolutions) == 1
    else:
        assert result["status"] == "change_requested"
        assert after["state"] == "waiting" and after["offers"]
        assert path.read_bytes() == before
        assert conflicts.find(open_core(root), "IC-001")
        assert result["followup"]["status"] == "queued"
        assert not resolutions
