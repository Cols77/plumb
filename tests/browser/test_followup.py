import pytest

from plumb.browser import followup
from plumb.hosts.claude_code.hookio import Deadline, HookContext

pytestmark = pytest.mark.sr("SR-178")


def test_harness_notification_does_not_consume_user_turn_handoff(tmp_path):
    from plumb.hosts.claude_code.prompt import handle

    followup.write(
        tmp_path,
        "source",
        {
            "id": "one",
            "card": "card",
            "status": "queued",
            "created": "now",
            "model_note": "Owner correction",
        },
    )
    ctx = HookContext(
        "prompt",
        {"prompt": "<task-notification>worker done</task-notification>"},
        tmp_path,
        "source",
        Deadline(100),
    )
    assert handle(ctx, backend=None).text == ""
    assert followup.history(tmp_path, "source")[0]["status"] == "queued"
    owner = HookContext(
        "prompt", {"prompt": "Continue the work"}, tmp_path, "source", Deadline(100)
    )
    try:
        handle(owner, backend=None)
    except Exception:
        pass
    assert "Owner correction" in "\n".join(owner.kept.snapshot())
    assert followup.history(tmp_path, "source")[0]["status"] == "delivered"


def test_delivery_only_to_matching_session_and_preserved_before_ack(tmp_path):
    from plumb.hosts.claude_code.prompt import handle

    followup.write(
        tmp_path,
        "source",
        {
            "id": "one",
            "card": "card",
            "status": "queued",
            "created": "now",
            "model_note": "Owner chose Ask for a change.",
            "text": "Preserve the existing format.",
        },
    )
    other = HookContext("prompt", {}, tmp_path, "other", Deadline(1))
    assert not followup.preserve(other)
    source = HookContext("prompt", {}, tmp_path, "source", Deadline(1))
    # Unadopted fixture makes later core work fail; kept output must survive it.
    try:
        handle(source, backend=None)
    except Exception:
        pass
    assert "Preserve the existing format." in "\n".join(source.kept.snapshot())
    assert followup.history(tmp_path, "source")[0]["status"] == "delivered"
    again = HookContext("prompt", {}, tmp_path, "source", Deadline(100))
    assert not followup.preserve(again)


def test_pending_intent_is_recovered_as_uncertain_handoff(tmp_path):
    followup.write(
        tmp_path,
        "source",
        {
            "id": "one",
            "card": "card",
            "status": "pending",
            "created": "now",
            "offer": "sha256:abc",
            "choice": 0,
            "text": "Correction survives restart.",
        },
    )
    followup.recover(tmp_path, "source")
    entry = followup.read(tmp_path, "source", "one")
    assert entry["status"] == "queued"
    assert "interrupted" in entry["model_note"].lower()
    assert "do not assume" in entry["model_note"].lower()


def test_later_keep_cannot_drop_acknowledged_browser_note(tmp_path):
    followup.write(
        tmp_path,
        "source",
        {
            "id": "one",
            "status": "queued",
            "model_note": "Owner correction",
            "created": "now",
            "card": "card",
        },
    )
    ctx = HookContext("prompt", {}, tmp_path, "source", Deadline(1))
    followup.preserve(ctx)
    ctx.keep(["Later intent translation"])
    assert "Owner correction" in "\n".join(ctx.kept.snapshot())


def test_followups_keep_action_sequence_after_restart(tmp_path):
    for ident, sequence, note in (("a", 2, "Second correction"), ("b", 1, "First answer")):
        followup.write(
            tmp_path,
            "source",
            {
                "id": ident,
                "status": "queued",
                "sequence": sequence,
                "model_note": note,
                "created": "same-second",
                "card": "card",
            },
        )
    notes = [line.text for _, line in followup.pending(tmp_path, "source")]
    assert "First answer" in notes[0] and "Second correction" in notes[1]
