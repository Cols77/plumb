"""DEC-407, SR-345: the stand-in question tool of the headless benchmark agent. The scripted
owner answers each question from the hidden brief, and the result has AskUserQuestion's shape."""

from __future__ import annotations

import io
import json

import pytest

from iaso.evaluate import ask_server
from iaso.hosts.claude_code import ask_gate

QUESTIONS = [{"question": "Cache the pages or not?", "header": "Cache",
              "options": [{"label": "yes", "description": "faster"}, {"label": "no"}],
              "multiSelect": False}]
CONFIG = {"brief": "the owner wants caching", "request": "make pages faster",
          "owner_model": "haiku"}


class Owner:
    """Records what it is asked; answers 'yes'."""

    def __init__(self, answer="yes"):
        self.seen, self.reply = [], answer

    def answer(self, brief, request, reply):
        self.seen.append((brief, request, reply))
        return {"asks": True, "answer": self.reply}


def rpc(owner, *messages):
    out = io.StringIO()
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    assert ask_server.serve(ask_server.AskServer(CONFIG, owner), stdin, out) == 0
    return [json.loads(line) for line in out.getvalue().splitlines()]


def call(questions):
    return {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": ask_gate.STAND_IN_NAME, "arguments": {"questions": questions}}}


@pytest.mark.sr("SR-345")
def test_the_server_lists_one_tool_named_for_the_hooks():
    """The full name the hooks match is mcp__<server>__<tool> of the one tool listed."""
    init, listed = rpc(Owner(), {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                       {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert init["result"]["serverInfo"]["name"] == ask_gate.STAND_IN_SERVER
    (tool,) = listed["result"]["tools"]
    assert f"mcp__{ask_gate.STAND_IN_SERVER}__{tool['name']}" == ask_gate.STAND_IN_TOOL
    assert tool["inputSchema"]["required"] == ["questions"]


@pytest.mark.sr("SR-345")
def test_the_scripted_owner_answers_each_question_in_askuserquestions_shape():
    owner = Owner("yes")
    (got,) = rpc(owner, call(QUESTIONS))
    data = got["result"]["structuredContent"]
    assert data == {"questions": QUESTIONS, "answers": {"Cache the pages or not?": "yes"}}
    assert json.loads(got["result"]["content"][1]["text"]) == data
    assert 'User has answered your questions: "Cache the pages or not?"="yes"' in \
        got["result"]["content"][0]["text"]
    brief, request, shown = owner.seen[0]
    assert (brief, request) == (CONFIG["brief"], CONFIG["request"])
    assert shown == "Cache the pages or not?\n- yes: faster\n- no"


@pytest.mark.sr("SR-345")
def test_an_owner_with_nothing_to_say_still_answers():
    """A silent scripted owner (its model unavailable) never leaves the agent waiting."""
    (got,) = rpc(Owner(""), call(QUESTIONS))
    assert got["result"]["structuredContent"]["answers"] == {
        "Cache the pages or not?": ask_server.NO_ANSWER}


@pytest.mark.sr("SR-345")
def test_a_call_without_questions_is_refused():
    (got,) = rpc(Owner(), call("not a list"))
    assert got["error"]["code"] == ask_server.INVALID_PARAMS
