"""SR-267 EX-5 (DEC-437): the pre-tool hook refuses an incomplete question-tool call."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso.hosts.claude_code import pretool

pytestmark = pytest.mark.sr("SR-267")


def ask(*options: dict[str, str]) -> dict[str, object]:
    return {"questions": [{"question": "Which?", "header": "h", "options": list(options)}]}


def run(tmp_path: Path, tool_input: dict[str, object]) -> dict[str, object]:
    return pretool.decide(tmp_path, "s", "AskUserQuestion", tool_input, {"session_id": "s"})


def reason(answer: dict[str, object]) -> str:
    return str(answer["hookSpecificOutput"]["permissionDecisionReason"])  # type: ignore[index]


def test_ex5_an_option_without_a_description_is_refused(tmp_path: Path) -> None:
    answer = run(tmp_path, ask({"label": "A (Recommended)", "description": "x, because y"},
                               {"label": "B", "description": ""}))
    assert 'option "B" has no description' in reason(answer)


def test_ex5_a_recommended_option_without_a_reason_is_refused(tmp_path: Path) -> None:
    answer = run(tmp_path, ask({"label": "A (Recommended)", "description": "does x"},
                               {"label": "B", "description": "does y"}))
    assert "gives no reason" in reason(answer)


def test_ex5_a_complete_question_goes_through(tmp_path: Path) -> None:
    assert run(tmp_path, ask({"label": "A (Recommended)", "description": "does x, because z"},
                             {"label": "B", "description": "does y"})) == {}
