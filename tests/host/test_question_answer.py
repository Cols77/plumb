"""SR-156: the owner's answers to the question tool are logged, and change no record."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.hosts.claude_code import question_answer

pytestmark = pytest.mark.sr("SR-212")

ASKED = {"questions": [{"question": "Run the slow tests now or later?", "header": "Tests",
                        "options": [{"label": "now", "description": ""},
                                    {"label": "later", "description": ""}],
                        "multiSelect": False}]}


def _answers(repo: Path) -> list:
    return [e for e in open_core(repo).log_read("events", ["question-answer"])]


def _run(repo: Path, hook_input, response: object) -> str:
    out = io.StringIO()
    payload = hook_input("PostToolUse", tool_name="AskUserQuestion", tool_input=ASKED,
                         tool_response=response)
    assert question_answer.main(stdin=io.StringIO(payload), stdout=out, root=repo) == 0
    return out.getvalue()


def test_logs_question_options_and_answer(repo: Path, hook_input) -> None:  # EX-1
    out = _run(repo, hook_input, {"questions": ASKED["questions"],
                                  "answers": {"Run the slow tests now or later?": "later"}})
    assert out == ""
    (entry,) = _answers(repo)
    assert entry.payload == {"session": "test-session",
                             "question": "Run the slow tests now or later?",
                             "options": [{"label": "now", "description": ""},
                                         {"label": "later", "description": ""}],
                             "answer": "later", "via": "question-tool"}


def test_an_answer_that_says_confirm_confirms_nothing(repo: Path, hook_input) -> None:  # EX-2
    _run(repo, hook_input, {"answers": {"Run the slow tests now or later?":
                                        "yes, confirm SR-005"}})
    assert [e.kind for e in open_core(repo).log_read("events")] == ["question-answer"]


@pytest.mark.parametrize("response", [{"answers": {}}, {}, "dismissed", None])
def test_a_dismissed_question_logs_nothing(repo: Path, hook_input,
                                           response: object) -> None:  # EX-3
    assert _run(repo, hook_input, response) == ""
    assert _answers(repo) == []


def test_a_stand_in_call_is_logged_like_an_askuserquestion_call(repo: Path, hook_input) -> None:
    """DEC-407: the stand-in's MCP result (structuredContent, or JSON in a text block) is read
    as AskUserQuestion's response."""
    from plumb.hosts.claude_code import ask_gate

    data = {"questions": ASKED["questions"],
            "answers": {"Run the slow tests now or later?": "now"}}
    for response in ({"structuredContent": data, "content": []},
                     [{"type": "text", "text": "User has answered your questions"},
                      {"type": "text", "text": json.dumps(data)}]):
        payload = hook_input("PostToolUse", tool_name=ask_gate.STAND_IN_TOOL, tool_input=ASKED,
                             tool_response=response)
        assert question_answer.main(stdin=io.StringIO(payload), stdout=io.StringIO(),
                                    root=repo) == 0
    first, second = _answers(repo)
    assert first.payload == second.payload
    assert first.payload["answer"] == "now" and first.payload["via"] == "question-tool"
