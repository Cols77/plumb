"""eval-52810e26: without the question tool the judge's questions are asked in plain words."""
from plumb.hosts.claude_code import stop


def test_ask_instructions_cover_missing_question_tool():
    assert "question tool" in stop.ASK_WAITING
    assert "no question" in stop.ASK_IN_TEXT and "plain words" in stop.ASK_IN_TEXT
