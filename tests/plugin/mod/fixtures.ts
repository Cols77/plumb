// What `plumb mod draw|press` and the stop hook's present.json answer, for the panel's
// tests (SP7 5.10). tests/mod/test_handshake.py checks that each has the shape of a real run.
import type { PlumbCard, PlumbPresent } from '../../../plugin/types'

export const ROOT = '/work/shop'
export const SESSION = 'sess-1'
export const PYTHON = '/home/owner/.plumb/env/0.1.0/bin/python'

// BEGIN DRAW
export const DRAW = {
 "session": "sess-1",
 "cards": [
  {
   "id": "clarify:SR-001",
   "kind": "clarify",
   "topic": "CSV export",
   "issue": "The report exports as CSV with one row per invoice.",
   "evidence": "keep the CSV export",
   "resolutions": [
    "Yes, that's it",
    "No, drop it"
   ],
   "questions": [
    {
     "id": "confirm",
     "text": "Is \"CSV export\" what you meant?",
     "resolutions": [
      "Yes, that's it",
      "No, drop it"
     ],
     "record": "SR-001",
     "hash": "sha256:1111",
     "choices": [
      {
       "label": "Confirm",
       "answer": "accepted",
       "change": null,
       "consequence": ""
      },
      {
       "label": "No",
       "answer": "rejected",
       "change": null,
       "consequence": ""
      }
     ]
    }
   ],
   "status": "open",
   "answers": [],
   "branch": "",
   "diagram": "",
   "turn": 0,
   "repeats": true,
   "content": {
    "topic": "CSV export",
    "issue": "The report exports as CSV with one row per invoice.",
    "context": [
     "You asked for this on 11 Oct."
    ],
    "assumptions": [
     "Dates are written as YYYY-MM-DD."
    ],
    "wont": "No other export format.",
    "options": [
     {
      "n": 1,
      "text": "Confirm",
      "consequence": null,
      "recommended": true
     },
     {
      "n": 2,
      "text": "No",
      "consequence": null,
      "recommended": false
     }
    ],
    "diagram": ""
   },
   "offers": [
    {
     "offer_id": "sha256:aaaa",
     "question": "confirm",
     "record": "SR-001",
     "hash": "sha256:1111",
     "drawn_at": "2026-10-11T12:00:00Z",
     "buttons": [
      {
       "index": 0,
       "label": "Confirm",
       "answer": "accepted",
       "change": null,
       "consequence": ""
      },
      {
       "index": 1,
       "label": "No",
       "answer": "rejected",
       "change": null,
       "consequence": ""
      },
      {
       "index": 2,
       "label": "Ask for a change",
       "answer": "change",
       "change": null,
       "consequence": ""
      },
      {
       "index": 3,
       "label": "Leave open",
       "answer": "open",
       "change": null,
       "consequence": ""
      }
     ]
    }
   ]
  },
  {
   "id": "stale:SR-005#0",
   "kind": "stale_link",
   "topic": "Confirm button",
   "issue": "the confirm check now accepts the panel's Confirm button",
   "evidence": "",
   "resolutions": [
    "Keep the requirement and re-pin it",
    "Reword the requirement"
   ],
   "questions": [],
   "status": "open",
   "answers": [],
   "branch": "",
   "diagram": "",
   "turn": 3,
   "repeats": true,
   "content": {
    "topic": "Confirm button",
    "issue": "the confirm check now accepts the panel's Confirm button",
    "context": [
     "You said a click confirms because only you can click (4 Oct).",
     "The change adds a way you confirm without changing who confirms."
    ],
    "assumptions": [],
    "wont": null,
    "options": [
     {
      "n": 1,
      "text": "Keep the requirement and re-pin it",
      "consequence": "The requirement stays as it reads; the button is one more way you confirm.",
      "recommended": true
     },
     {
      "n": 2,
      "text": "Reword the requirement",
      "consequence": "The requirement names the button; it waits for you again.",
      "recommended": false
     }
    ],
    "diagram": ""
   },
   "offers": [
    {
     "offer_id": "sha256:bbbb",
     "question": "",
     "record": null,
     "hash": "",
     "drawn_at": "2026-10-11T12:00:00Z",
     "buttons": [
      {
       "index": 0,
       "label": "Keep the requirement and re-pin it",
       "answer": "accepted",
       "change": null,
       "consequence": ""
      },
      {
       "index": 1,
       "label": "Reword the requirement",
       "answer": "change",
       "change": "Reword the requirement",
       "consequence": ""
      },
      {
       "index": 2,
       "label": "Ask for a change",
       "answer": "change",
       "change": null,
       "consequence": ""
      },
      {
       "index": 3,
       "label": "Leave open",
       "answer": "open",
       "change": null,
       "consequence": ""
      }
     ]
    }
   ]
  },
  {
   "id": "clarify:SR-009",
   "kind": "clarify",
   "topic": "Late fees",
   "issue": "A late invoice gets a 5% fee.",
   "evidence": "",
   "resolutions": [
    "Yes, that's it",
    "No, drop it"
   ],
   "questions": [
    {
     "id": "confirm",
     "text": "Is \"Late fees\" what you meant?",
     "resolutions": [
      "Yes, that's it",
      "No, drop it"
     ],
     "record": "SR-009",
     "hash": "sha256:9999",
     "choices": []
    }
   ],
   "status": "left_open",
   "answers": [],
   "branch": "",
   "diagram": "",
   "turn": 0,
   "repeats": false,
   "content": {
    "topic": "Late fees",
    "issue": "A late invoice gets a 5% fee.",
    "context": [],
    "assumptions": [],
    "wont": null,
    "options": [],
    "diagram": ""
   },
   "offers": [
    {
     "offer_id": "sha256:cccc",
     "question": "confirm",
     "record": "SR-009",
     "hash": "sha256:9999",
     "drawn_at": "2026-10-11T11:00:00Z",
     "buttons": [
      {
       "index": 0,
       "label": "Confirm",
       "answer": "accepted",
       "change": null,
       "consequence": ""
      },
      {
       "index": 1,
       "label": "No",
       "answer": "rejected",
       "change": null,
       "consequence": ""
      },
      {
       "index": 2,
       "label": "Ask for a change",
       "answer": "change",
       "change": null,
       "consequence": ""
      },
      {
       "index": 3,
       "label": "Leave open",
       "answer": "open",
       "change": null,
       "consequence": ""
      }
     ]
    }
   ]
  }
 ]
}
// END DRAW

// BEGIN DRAW_TRIAL
export const DRAW_TRIAL = {
 "session": "sess-1",
 "cards": [
  {
   "id": "trial:SR-001",
   "kind": "trial",
   "topic": "CSV export",
   "issue": "From your words of 4 Oct: keep the CSV export. Is that what you meant?",
   "evidence": "",
   "resolutions": [
    "Yes",
    "No"
   ],
   "questions": [
    {
     "id": "trial:SR-001#1",
     "text": "CSV export",
     "resolutions": [
      "Yes, that is what I meant",
      "No, that is not what I meant"
     ],
     "record": "SR-001",
     "hash": "sha256:1111",
     "choices": [
      {
       "label": "Yes",
       "answer": "accepted",
       "change": null,
       "consequence": ""
      },
      {
       "label": "No",
       "answer": "rejected",
       "change": null,
       "consequence": ""
      }
     ]
    }
   ],
   "status": "open",
   "answers": [],
   "branch": "",
   "diagram": "",
   "turn": 0,
   "repeats": true,
   "content": {
    "topic": "CSV export",
    "issue": "From your words of 4 Oct: keep the CSV export. Is that what you meant?",
    "context": [
     "Your words of 4 Oct: \"keep the CSV export\""
    ],
    "assumptions": [],
    "wont": null,
    "options": [
     {
      "n": 1,
      "text": "Yes",
      "consequence": null,
      "recommended": true
     },
     {
      "n": 2,
      "text": "No",
      "consequence": null,
      "recommended": false
     },
     {
      "n": 3,
      "text": "Fix it",
      "consequence": null,
      "recommended": false
     }
    ],
    "diagram": ""
   },
   "offers": [
    {
     "offer_id": "sha256:t001",
     "question": "trial:SR-001#1",
     "record": "SR-001",
     "hash": "sha256:1111",
     "drawn_at": "2026-10-11T12:00:00Z",
     "buttons": [
      {
       "index": 0,
       "label": "Yes",
       "answer": "accepted",
       "change": null,
       "consequence": ""
      },
      {
       "index": 1,
       "label": "No",
       "answer": "rejected",
       "change": null,
       "consequence": ""
      },
      {
       "index": 2,
       "label": "Fix it",
       "answer": "change",
       "change": null,
       "consequence": ""
      },
      {
       "index": 3,
       "label": "Leave open",
       "answer": "open",
       "change": null,
       "consequence": ""
      }
     ]
    }
   ]
  }
 ]
}
// END DRAW_TRIAL

// BEGIN PRESS_TRIAL_NO
export const PRESS_TRIAL_NO = {
 "ok": true,
 "offer": "sha256:t001",
 "card": "trial:SR-001",
 "question": "trial:SR-001#1",
 "choice": 1,
 "label": "No",
 "answer": "rejected",
 "status": "closed",
 "confirmed": [],
 "rejected": [
  "SR-001"
 ],
 "left_out": [],
 "fresh_cards": [],
 "prefill": null,
 "line": "You pressed No: plumb's reading of \"CSV export\" is marked wrong; the record stays as it is.",
 "model_note": "The owner pressed No; plumb's reading of SR-001 'CSV export' is marked wrong. The record stays: do not remove or rewrite it.",
 "notes": []
}
// END PRESS_TRIAL_NO

// BEGIN PRESENT
export const PRESENT = {
 "turn": 1760184000,
 "turn_id": "t-1",
 "session": "sess-1",
 "written_at": "2026-10-11T12:00:01Z",
 "confirmations": [],
 "cards": []
}
// END PRESENT

// BEGIN PRESS_CONFIRM
export const PRESS_CONFIRM = {
  "ok": true, "offer": "sha256:aaaa", "card": "clarify:SR-001", "question": "confirm", "choice": 0,
  "label": "Confirm", "answer": "accepted", "status": "closed", "confirmed": ["SR-001"], "rejected": [],
  "left_out": [], "fresh_cards": [], "prefill": null,
  "line": "You pressed Confirm: now confirmed: \"CSV export\".",
  "model_note": "The owner pressed Confirm; now confirmed: SR-001 'CSV export'. Do not ask again.",
  "notes": []
}
// END PRESS_CONFIRM

// BEGIN PRESS_LEAVE_OPEN
export const PRESS_LEAVE_OPEN = {
  "ok": true, "offer": "sha256:aaaa", "card": "clarify:SR-001", "question": "confirm", "choice": 3,
  "label": "Leave open", "answer": "open", "status": "left_open", "confirmed": [], "rejected": [],
  "left_out": [], "fresh_cards": [], "prefill": null,
  "line": "Left open: \"CSV export\". It stops coming back at the end of each turn until it changes; it stays listed under what awaits you.",
  "model_note": "The owner pressed Leave open on \"CSV export\". Do not ask about it again until it changes.",
  "notes": []
}
// END PRESS_LEAVE_OPEN

// BEGIN PRESS_CHANGE
export const PRESS_CHANGE = {
  "ok": true, "offer": "sha256:aaaa", "card": "clarify:SR-001", "question": "confirm", "choice": 2,
  "label": "Ask for a change", "answer": "change", "status": "change_requested", "confirmed": [], "rejected": [],
  "left_out": [], "fresh_cards": [], "prefill": "Change to 'CSV export': ",
  "line": "Say what to change about \"CSV export\"; your next message is read against it.",
  "model_note": "The owner pressed Ask for a change on \"CSV export\"; their next message says what to change.",
  "notes": []
}
// END PRESS_CHANGE

export const CARDS = DRAW.cards as unknown as PlumbCard[]
export const PRESENT_DATA = PRESENT as unknown as PlumbPresent
