// What `plumb mod draw|press|undo` and the stop hook's present.json answer, for the panel's
// tests (SP7 5.10). tests/mod/test_handshake.py checks that each has the shape of a real run.
import type { PlumbCard, PlumbPresent } from '../types'

export const ROOT = '/work/shop'
export const SESSION = 'sess-1'
export const PYTHON = '/home/owner/.plumb/env/0.1.0/bin/python'

// BEGIN DRAW
export const DRAW = {
  "session": "sess-1",
  "cards": [
    {
      "id": "show_first:SR-001", "kind": "show_first", "topic": "CSV export",
      "issue": "Before it counts as yours: \"CSV export\" reads: the report exports as CSV with one row per invoice.",
      "evidence": "keep the CSV export", "resolutions": ["Yes, that's it", "No, drop it"],
      "questions": [{"id": "confirm", "text": "Is \"CSV export\" what you meant?", "resolutions": ["Yes, that's it", "No, drop it"], "record": "SR-001", "hash": "sha256:1111", "choices": [{"label": "Confirm", "answer": "accepted", "change": null}, {"label": "No", "answer": "rejected", "change": null}]}],
      "status": "open", "answers": [], "owner_only": false, "turn": 0,
      "evidence_size": 19, "repeats": true, "content": null,
      "offers": [{"offer_id": "sha256:aaaa", "question": "confirm", "record": "SR-001", "hash": "sha256:1111", "drawn_at": "2026-10-11T12:00:00Z",
        "buttons": [{"index": 0, "label": "Confirm", "answer": "accepted", "change": null}, {"index": 1, "label": "No", "answer": "rejected", "change": null}, {"index": 2, "label": "Ask for a change", "answer": "change", "change": null}, {"index": 3, "label": "Leave open", "answer": "open", "change": null}]}]
    },
    {
      "id": "stale:SR-005#0", "kind": "stale_link", "topic": "Confirm button",
      "issue": "the confirm check now accepts the panel's Confirm button",
      "evidence": "src/plumb/confirm.py", "resolutions": ["Keep the requirement and re-pin it", "Reword the requirement"],
      "questions": [], "status": "open", "answers": [], "owner_only": false, "turn": 3,
      "evidence_size": 20, "repeats": true,
      "content": {
        "record_now": {"id": "SR-005", "kind": "requirement", "title": "Only the owner confirms", "wording": "A record is confirmed only by the owner.", "examples": ["EX-1: given an agent shell, when it approves, then it is refused"]},
        "change": {"path": "src/plumb/confirm.py", "diff": "--- a/src/plumb/confirm.py\n+++ b/src/plumb/confirm.py\n@@ -1,2 +1,3 @@\n def accepted(entry):\n-    return entry.by == 'owner'\n+    if entry.via == 'button':\n+        return recheck(entry)\n", "size": 160, "lines": 7, "added": 2, "removed": 1, "folded": false, "note": ""},
        "owner_words": {"items": [{"id": "INT-030", "title": "Buttons confirm", "quote": "a click confirms because only I can click", "prompt": null, "at": null}], "note": ""},
        "options": [{"n": 1, "text": "Keep the requirement and re-pin it", "consequence": "SR-005 stays as it reads; the button is one more way you confirm.", "recommended": true, "index": 0}, {"n": 2, "text": "Reword the requirement", "consequence": "SR-005 names the button; it waits for you again.", "recommended": false, "index": 1}],
        "why": "The change adds a way you confirm without changing who confirms.",
        "missing": [], "complete": true, "notes": []
      },
      "offers": [{"offer_id": "sha256:bbbb", "question": "", "record": null, "hash": "", "drawn_at": "2026-10-11T12:00:00Z",
        "buttons": [{"index": 0, "label": "Keep the requirement and re-pin it", "answer": "accepted", "change": null}, {"index": 1, "label": "Reword the requirement", "answer": "change", "change": "Reword the requirement"}, {"index": 2, "label": "Ask for a change", "answer": "change", "change": null}, {"index": 3, "label": "Leave open", "answer": "open", "change": null}]}]
    },
    {
      "id": "show_first:SR-009", "kind": "show_first", "topic": "Late fees",
      "issue": "Before it counts as yours: \"Late fees\" reads: a late invoice gets a 5% fee.",
      "evidence": "", "resolutions": ["Yes, that's it", "No, drop it"],
      "questions": [{"id": "confirm", "text": "Is \"Late fees\" what you meant?", "resolutions": ["Yes, that's it", "No, drop it"], "record": "SR-009", "hash": "sha256:9999", "choices": []}],
      "status": "left_open", "answers": [], "owner_only": false, "turn": 0,
      "evidence_size": 0, "repeats": false, "content": null,
      "offers": [{"offer_id": "sha256:cccc", "question": "confirm", "record": "SR-009", "hash": "sha256:9999", "drawn_at": "2026-10-11T11:00:00Z",
        "buttons": [{"index": 0, "label": "Confirm", "answer": "accepted", "change": null}, {"index": 1, "label": "No", "answer": "rejected", "change": null}, {"index": 2, "label": "Ask for a change", "answer": "change", "change": null}, {"index": 3, "label": "Leave open", "answer": "open", "change": null}]}]
    }
  ]
}
// END DRAW

// BEGIN DRAW_TRIAL
export const DRAW_TRIAL = {
  "session": "sess-1",
  "cards": [
    {
      "id": "trial:5d1c0a9e7b21", "kind": "trial", "topic": "CSV export, Late fees",
      "issue": "plumb would settle these from your words; is that right?",
      "evidence": "CSV export: keep the CSV export | Late fees: charge 5% on late invoices", "resolutions": ["Yes, that is what I meant", "No, that is not what I meant"],
      "questions": [
        {"id": "trial:5d1c0a9e7b21#1", "text": "CSV export", "resolutions": ["Yes, that is what I meant", "No, that is not what I meant"], "record": "SR-001", "hash": "sha256:1111", "choices": [{"label": "Yes, that is what I meant", "answer": "accepted", "change": null}, {"label": "No, that is not what I meant", "answer": "rejected", "change": null}]},
        {"id": "trial:5d1c0a9e7b21#2", "text": "Late fees", "resolutions": ["Yes, that is what I meant", "No, that is not what I meant"], "record": "SR-009", "hash": "sha256:9999", "choices": [{"label": "Yes, that is what I meant", "answer": "accepted", "change": null}, {"label": "No, that is not what I meant", "answer": "rejected", "change": null}]}
      ],
      "status": "open", "answers": [], "owner_only": false, "turn": 0,
      "evidence_size": 71, "repeats": true, "content": null,
      "offers": [
        {"offer_id": "sha256:t001", "question": "trial:5d1c0a9e7b21#1", "record": "SR-001", "hash": "sha256:1111", "drawn_at": "2026-10-11T12:00:00Z",
          "buttons": [{"index": 0, "label": "Yes, that is what I meant", "answer": "accepted", "change": null}, {"index": 1, "label": "No, that is not what I meant", "answer": "rejected", "change": null}, {"index": 2, "label": "Ask for a change", "answer": "change", "change": null}, {"index": 3, "label": "Leave open", "answer": "open", "change": null}]},
        {"offer_id": "sha256:t009", "question": "trial:5d1c0a9e7b21#2", "record": "SR-009", "hash": "sha256:9999", "drawn_at": "2026-10-11T12:00:00Z",
          "buttons": [{"index": 0, "label": "Yes, that is what I meant", "answer": "accepted", "change": null}, {"index": 1, "label": "No, that is not what I meant", "answer": "rejected", "change": null}, {"index": 2, "label": "Ask for a change", "answer": "change", "change": null}, {"index": 3, "label": "Leave open", "answer": "open", "change": null}]}
      ]
    }
  ]
}
// END DRAW_TRIAL

// BEGIN PRESS_TRIAL_NO
export const PRESS_TRIAL_NO = {
  "ok": true, "offer": "sha256:t009", "card": "trial:5d1c0a9e7b21", "question": "trial:5d1c0a9e7b21#2", "choice": 1,
  "label": "No, that is not what I meant", "answer": "rejected", "status": "open", "confirmed": [], "rejected": ["SR-009"],
  "left_out": [], "fresh_cards": [], "prefill": null,
  "line": "You pressed No, that is not what I meant: dropped: \"Late fees\".",
  "model_note": "The owner pressed No, that is not what I meant; dropped: SR-009 'Late fees'.",
  "notes": []
}
// END PRESS_TRIAL_NO

// BEGIN PRESENT
export const PRESENT = {
  "turn": 1760184000, "turn_id": "t-1", "session": "sess-1", "written_at": "2026-10-11T12:00:01Z",
  "confirmations": [], "settled": ["Settled from your words: Deadline reminders (Undo)."],
  "settled_records": [{"id": "SR-007", "title": "Deadline reminders"}],
  "cards": []
}
// END PRESENT

// BEGIN PRESS_CONFIRM
export const PRESS_CONFIRM = {
  "ok": true, "offer": "sha256:aaaa", "card": "show_first:SR-001", "question": "confirm", "choice": 0,
  "label": "Confirm", "answer": "accepted", "status": "closed", "confirmed": ["SR-001"], "rejected": [],
  "left_out": [], "fresh_cards": [], "prefill": null,
  "line": "You pressed Confirm: now confirmed: \"CSV export\".",
  "model_note": "The owner pressed Confirm; now confirmed: SR-001 'CSV export'. Do not ask again.",
  "notes": []
}
// END PRESS_CONFIRM

// BEGIN PRESS_LEAVE_OPEN
export const PRESS_LEAVE_OPEN = {
  "ok": true, "offer": "sha256:aaaa", "card": "show_first:SR-001", "question": "confirm", "choice": 3,
  "label": "Leave open", "answer": "open", "status": "left_open", "confirmed": [], "rejected": [],
  "left_out": [], "fresh_cards": [], "prefill": null,
  "line": "Left open: \"CSV export\". It stops coming back at the end of each turn until it changes; it stays listed under what awaits you.",
  "model_note": "The owner pressed Leave open on \"CSV export\". Do not ask about it again until it changes.",
  "notes": []
}
// END PRESS_LEAVE_OPEN

// BEGIN PRESS_CHANGE
export const PRESS_CHANGE = {
  "ok": true, "offer": "sha256:aaaa", "card": "show_first:SR-001", "question": "confirm", "choice": 2,
  "label": "Ask for a change", "answer": "change", "status": "change_requested", "confirmed": [], "rejected": [],
  "left_out": [], "fresh_cards": [], "prefill": "Change to 'CSV export': ",
  "line": "Say what to change about \"CSV export\"; your next message is read against it.",
  "model_note": "The owner pressed Ask for a change on \"CSV export\"; their next message says what to change.",
  "notes": []
}
// END PRESS_CHANGE

// BEGIN UNDO
export const UNDO = {
  "ok": true, "undone": ["SR-007"], "line": "Deadline reminders is proposed again and waits for you.",
  "model_note": "The owner pressed Undo on the settled line; SR-007 'Deadline reminders' is proposed again. Do not treat it as confirmed."
}
// END UNDO

export const CARDS = DRAW.cards as unknown as PlumbCard[]
export const PRESENT_DATA = PRESENT as unknown as PlumbPresent
