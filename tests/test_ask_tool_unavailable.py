"""DEC-407: a session with no question tool is never told to ask the judge's questions in plain
words (SR-267 EX-8: questions go only through a question tool); the headless benchmark agent is
given a stand-in tool instead (tests/evaluate/test_ask_server.py)."""
import pytest

from iaso.hosts.claude_code import stop


@pytest.mark.sr("SR-267")
def test_the_only_ask_instruction_names_the_question_tool():
    assert "question tool" in stop.ASK_WAITING
    assert not hasattr(stop, "ASK_IN_TEXT")
