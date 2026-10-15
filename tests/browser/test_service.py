"""Browser decisions retain the source session and exact shown record version."""

import dataclasses
import shutil

import pytest
from mod.helpers import DIGEST, SESSION, sample_card
from understand.test_read_job import make_core, open_card, record_text

from plumb.api import open_core
from plumb.mod import session
from plumb.understand import cardstore, recheck_button

pytestmark = pytest.mark.sr("SR-176")


def test_browser_readback_approves_exact_multiple_record_hashes(core):
    from plumb.understand import clarify

    digest = "sha256:" + "ab" * 32
    for n in (1, 2):
        (core.root / ".plumb/intents" / f"INT-{n:03d}.md").write_text(
            f"---\nid: INT-{n:03d}\ntitle: Export {n}\nquote: export it\nreadback: Export.\n"
            f"prompt: {digest[7:23]}\n---\n",
            encoding="utf-8",
        )
    fresh = open_core(core.root)
    card = clarify._readback_card(core.root, digest, "export it", {"proposal": "Export it."}, [])
    cardstore.save(core.root, SESSION, [card])
    ui = service(core.root)
    result = ui.press(SESSION, press_payload(ui.draw(SESSION)))
    assert result["confirmed"] == ["INT-001", "INT-002"]
    approvals = [e for e in open_core(core.root).events() if e.kind == "approval"]
    for approval in approvals:
        assert recheck_button.problem(approval, open_core(core.root)) is None
        for record in approval.payload["records"]:
            assert record["hash"] == fresh.index()[record["id"]].hash


@pytest.fixture
def core(repo, write_record):
    core = make_core(repo, write_record, [record_text(n) for n in (1, 2)])
    open_card(core, sample_card(core, "SR-001"))
    return core


def service(root):
    from plumb.browser.service import BrowserService

    return BrowserService(root)


def press_payload(snapshot, choice=0, request_id="request-1"):
    return {
        "offer": snapshot["cards"][0]["offers"][0]["offer_id"],
        "choice": choice,
        "request_id": request_id,
    }


def test_browser_approval_preserves_mod_and_rechecks_without_runtime(core):
    session.hello(core, SESSION, DIGEST)
    before = session.mod_path(core.root, SESSION).read_bytes()
    ui = service(core.root)
    snapshot = ui.draw(SESSION)
    shown = snapshot["cards"][0]["offers"][0]["hash"]
    result = ui.press(SESSION, press_payload(snapshot))
    assert result["confirmed"] == ["SR-001"]
    assert session.mod_path(core.root, SESSION).read_bytes() == before
    fresh = open_core(core.root)
    approval = next(e for e in fresh.events() if e.kind == "approval")
    assert approval.payload["surface"] == "browser"
    assert approval.payload["records"][0]["hash"] == shown
    assert recheck_button.problem(approval, fresh) is None
    shutil.rmtree(core.root / ".plumb" / "session")
    assert recheck_button.problem(approval, open_core(core.root)) is None


def test_stale_record_is_not_approved(core):
    ui = service(core.root)
    snapshot = ui.draw(SESSION)
    path = core.root / ".plumb/requirements/SR-001.md"
    path.write_text(path.read_text().replace("statement 1", "changed statement 1"))
    result = ui.press(SESSION, press_payload(snapshot))
    assert not result["confirmed"]
    assert result["left_out"]
    assert not [e for e in open_core(core.root).events() if e.kind == "approval"]


def test_duplicate_action_survives_restart_and_queues_once(core):
    ui = service(core.root)
    payload = press_payload(ui.draw(SESSION), choice=3)
    payload["text"] = "Keep the previous behavior."
    first = ui.press(SESSION, payload)
    again = service(core.root).press(SESSION, payload)
    assert again["duplicate"] is True
    assert first["followup"]["id"] == again["followup"]["id"]
    assert len(ui.draw(SESSION)["followups"]) == 1
    assert len([e for e in open_core(core.root).events() if e.kind == "card-press"]) == 1


def test_restart_requires_redraw_before_pressing_old_key_offer(core):
    first = service(core.root)
    snapshot = first.draw(SESSION)
    payload = press_payload(snapshot)
    before = cardstore.own_cards(core.root, SESSION)
    second = service(core.root)
    with pytest.raises(PermissionError, match="redraw"):
        second.press(SESSION, payload)
    fresh = open_core(core.root)
    assert not [e for e in fresh.events() if e.kind in ("card-press", "approval")]
    assert cardstore.own_cards(core.root, SESSION) == before
    current = second.draw(SESSION)
    result = second.press(SESSION, press_payload(current, request_id="after-redraw"))
    assert result["confirmed"] == ["SR-001"]
    fresh = open_core(core.root)
    approval = next(e for e in fresh.events() if e.kind == "approval")
    assert recheck_button.problem(approval, fresh) is None


def test_request_id_cannot_be_reused_for_another_answer(core):
    ui = service(core.root)
    payload = press_payload(ui.draw(SESSION), choice=4)
    ui.press(SESSION, payload)
    with pytest.raises(ValueError, match="request_id"):
        ui.press(SESSION, {**payload, "choice": 0})


def test_duplicate_alias_reserves_request_id_without_second_handoff(core):
    ui = service(core.root)
    payload = press_payload(ui.draw(SESSION), choice=4, request_id="original")
    ui.press(SESSION, payload)
    alias = {**payload, "request_id": "alias"}
    assert ui.press(SESSION, alias)["duplicate"] is True
    conflicting = press_payload(ui.draw(SESSION), choice=3, request_id="alias")
    with pytest.raises(ValueError, match="request_id"):
        ui.press(SESSION, conflicting)
    assert len(ui.draw(SESSION)["followups"]) == 1
    current = press_payload(ui.draw(SESSION), choice=3, request_id="later-change")
    ui.press(SESSION, current)
    retry = service(core.root).press(SESSION, alias)
    assert retry["duplicate"] is True and retry["status"] == "left_open"
    assert retry["followup"]["id"] == "original"
    assert cardstore.own_cards(core.root, SESSION)[0].status == "change_requested"


def test_multiple_questions_remain_independent(core):
    first = sample_card(core, "SR-001")
    second = sample_card(core, "SR-002").questions[0]
    cardstore.save(
        core.root,
        SESSION,
        [
            dataclasses.replace(
                first, questions=(first.questions[0], dataclasses.replace(second, id="second"))
            )
        ],
    )
    ui = service(core.root)
    drawn = ui.draw(SESSION)
    ui.press(SESSION, press_payload(drawn))
    ui.press(
        SESSION,
        {
            "offer": drawn["cards"][0]["offers"][1]["offer_id"],
            "choice": 0,
            "request_id": "request-2",
        },
    )
    assert all(
        open_core(core.root).status([rid])[rid].confirmation == "confirmed"
        for rid in ("SR-001", "SR-002")
    )


def test_startup_refuses_agent_marker(core, monkeypatch):
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "source-agent")
    with pytest.raises(PermissionError):
        service(core.root)


def test_restart_recovers_handoff_after_answer_before_receipt(core, monkeypatch):
    import plumb.browser.service as module
    from plumb.browser import followup

    ui = service(core.root)
    payload = press_payload(ui.draw(SESSION))
    original = module.press

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated receipt interruption")

    monkeypatch.setattr(module, "press", interrupted)
    with pytest.raises(RuntimeError):
        ui.press(SESSION, payload)
    assert len([e for e in open_core(core.root).events() if e.kind == "approval"]) == 1
    service(core.root)
    assert followup.history(core.root, SESSION)[0]["status"] == "queued"


def test_changed_options_without_record_change_are_refused(core):
    ui = service(core.root)
    snapshot = ui.draw(SESSION)
    card = cardstore.own_cards(core.root, SESSION)[0]
    question = card.questions[0]
    changed = dataclasses.replace(question, text="A materially different question")
    cardstore.save(core.root, SESSION, [dataclasses.replace(card, questions=(changed,))])
    with pytest.raises(PermissionError, match="changed"):
        ui.press(SESSION, press_payload(snapshot))
    assert not [e for e in open_core(core.root).events() if e.kind == "approval"]


def test_browser_approval_cannot_claim_mod_or_unknown_surface(core):
    ui = service(core.root)
    ui.press(SESSION, press_payload(ui.draw(SESSION)))
    fresh = open_core(core.root)
    approval = next(e for e in fresh.events() if e.kind == "approval")
    for surface in ("mod", "unknown"):
        forged = dataclasses.replace(approval, payload={**approval.payload, "surface": surface})
        assert recheck_button.problem(forged, fresh)


def test_invalid_session_aliases_and_unknown_offers_are_refused(core):
    ui = service(core.root)
    with pytest.raises(LookupError):
        ui.draw("s1/../s1")
    with pytest.raises(PermissionError):
        ui.press(SESSION, {"offer": "sha256:" + "0" * 64, "choice": 0, "request_id": "x"})


def test_duplicate_question_with_new_request_id_does_not_repeat_approval(core):
    card = sample_card(core, "SR-001")
    second = dataclasses.replace(sample_card(core, "SR-002").questions[0], id="second")
    cardstore.save(
        core.root, SESSION, [dataclasses.replace(card, questions=(*card.questions, second))]
    )
    ui = service(core.root)
    payload = press_payload(ui.draw(SESSION))
    ui.press(SESSION, payload)
    result = ui.press(SESSION, {**payload, "request_id": "another-click"})
    assert result["duplicate"] is True
    assert len([e for e in open_core(core.root).events() if e.kind == "approval"]) == 1
    with pytest.raises(PermissionError, match="already answered"):
        ui.press(SESSION, {**payload, "request_id": "different-answer", "choice": 1})


def test_snapshot_exposes_evidence_and_actual_conflict_sides(core):
    path = core.root / ".plumb/requirements/SR-001.md"
    text = path.read_text()
    text = text.replace(
        "statement: statement 1",
        "statement: statement 1\nconflict:\n"
        "  id: IC-001\n  fields:\n    statement:\n      base: original\n      ours: this branch\n"
        "      theirs: other branch\n  ours:\n    label: main\n  theirs:\n    label: feature",
    )
    path.write_text(text)
    fresh = open_core(core.root)
    cardstore.save(core.root, SESSION, [sample_card(fresh, "SR-001")])
    card = service(core.root).draw(SESSION)["cards"][0]
    assert card["records"][0]["status"]["confirmation"] == "proposed"
    assert card["diff"]["fields"]["statement"] == {
        "base": "original",
        "ours": "this branch",
        "theirs": "other branch",
    }


def test_turn_built_display_matches_fresh_hashed_content(tmp_path):
    from plumb.browser.demo import SESSION as demo_session
    from plumb.browser.demo import seed
    from plumb.mod import offers
    from plumb.understand import files, summary

    root = seed(tmp_path / "demo")
    path = files.session_dir(root, demo_session) / summary.DRAWN
    cached = files.read_json(path)
    cached[0]["content"] = {"context": "OUTDATED CONTEXT"}
    files.write_json_atomic(path, cached)
    snapshot = service(root).draw(demo_session)
    current = next(c for c in snapshot["cards"] if c["kind"] == "conflict")
    assert current["content"] == offers.content_for(
        open_core(root), demo_session, cardstore.card_from_json(cached[0]["card"])
    )


@pytest.mark.parametrize("other_question", [False, True])
def test_repeated_leave_change_cycle_applies_current_answer(core, other_question):
    if other_question:
        card = cardstore.own_cards(core.root, SESSION)[0]
        second = dataclasses.replace(card.questions[0], id="second")
        cardstore.save(
            core.root, SESSION, [dataclasses.replace(card, questions=(*card.questions, second))]
        )
    ui = service(core.root)
    result = None
    for n, choice in enumerate((4, 3, 4, 3)):
        payload = press_payload(ui.draw(SESSION), choice=choice, request_id=f"cycle-{n}")
        if other_question and n == 2:
            payload["offer"] = ui.draw(SESSION)["cards"][0]["offers"][1]["offer_id"]
        payload["text"] = "fix it" if choice == 3 else ""
        result = ui.press(SESSION, payload)
    current = cardstore.own_cards(core.root, SESSION)[0]
    assert current.status == result["status"] == "change_requested"
    assert result["duplicate"] is False
