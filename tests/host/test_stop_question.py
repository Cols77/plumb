"""SR-091 EX-6: a decision asked as plain text is in the stated set of that reply."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from plumb.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-091")

DEC = """---
id: DEC-026
title: Reminder channel
question: Email or SMS?
chosen: email
alternatives:
- sms
matters: true
---
"""
QUESTION = ("### Question (DEC-026): how should reminders go out?\n"
            "A. email\nB. SMS\nC. both\n")


def _stop(repo: Path, hook_input, reply: str, session: str = "s1") -> dict:
    (repo / ".plumb" / "session" / session).mkdir(parents=True, exist_ok=True)
    payload = hook_input("Stop", session_id=session, stop_hook_active=False,
                         last_assistant_message=reply)
    assert stop.main(stdin=io.StringIO(payload), stdout=io.StringIO(), root=repo,
                     verify=None, unjudged=None) == 0
    path = repo / ".plumb" / "session" / "stated.json"
    return json.loads(path.read_text("utf-8"))


def test_plain_text_question_states_the_decision(repo: Path, write_record, hook_input) -> None:
    write_record(repo, DEC)
    stated = _stop(repo, hook_input, QUESTION)
    assert [r["id"] for r in stated["records"]] == ["DEC-026"]
    assert stated["records"][0]["shown"] is True


def test_decision_named_in_passing_is_not_stated(repo: Path, write_record, hook_input) -> None:
    write_record(repo, DEC)
    stated = _stop(repo, hook_input, "Done. See DEC-026 for the channel.\n")
    assert stated["records"] == []


def test_question_about_unknown_decision_is_not_stated(repo: Path, hook_input) -> None:
    stated = _stop(repo, hook_input, QUESTION)
    assert stated["records"] == []


def test_question_read_from_transcript(repo: Path, write_record, hook_input,
                                       tmp_path: Path) -> None:
    write_record(repo, DEC)
    transcript = tmp_path / "t.jsonl"
    entry = {"message": {"role": "assistant", "content": [{"type": "text", "text": QUESTION}]}}
    transcript.write_text(json.dumps(entry) + "\n", "utf-8")
    (repo / ".plumb" / "session" / "s2").mkdir(parents=True, exist_ok=True)
    payload = hook_input("Stop", session_id="s2", stop_hook_active=False,
                         transcript_path=str(transcript))
    stop.main(stdin=io.StringIO(payload), stdout=io.StringIO(), root=repo, verify=None,
              unjudged=None)
    stated = json.loads((repo / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    assert [r["id"] for r in stated["records"]] == ["DEC-026"]
