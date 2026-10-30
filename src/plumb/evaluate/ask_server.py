"""DEC-407: the question tool of the headless benchmark agent. ``claude -p`` has no
AskUserQuestion, so this stdio MCP server stands in for it (``python -m plumb.evaluate.ask_server``,
registered by ``run.claude_turn``): it takes AskUserQuestion's input and answers each question
through the scripted owner (SR-345), from the task's hidden owner brief, before returning.
It returns AskUserQuestion's result, ``{questions, answers: {question: answer}}``, so plumb's
hooks log and judge the answers as the owner's words (``ask_gate.STAND_IN_TOOL``)."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.hosts.claude_code.ask_gate import STAND_IN_NAME, STAND_IN_SERVER
from plumb.mcp import server as mcp

CONFIG_ENV = "PLUMB_ASK_CONFIG"   # a JSON file {brief, request, owner_model} written per turn
NO_ANSWER = "No preference: use your best judgment and say what you chose."

_OPTION = {"type": "object", "required": ["label"], "properties": {
    "label": {"type": "string"}, "description": {"type": "string"}}}
_QUESTION = {"type": "object", "required": ["question", "options"], "properties": {
    "question": {"type": "string"}, "header": {"type": "string"},
    "options": {"type": "array", "items": _OPTION, "minItems": 2},
    "multiSelect": {"type": "boolean"}}}
TOOL: dict[str, Any] = {
    "name": STAND_IN_NAME,
    "description": "Ask the owner one to four questions and wait for their answers. Use this "
                   "for every question to the owner: never write a question in your reply "
                   "for the owner to answer.",
    "inputSchema": mcp._schema({"questions": {"type": "array", "items": _QUESTION,
                                              "minItems": 1, "maxItems": 4}}, ("questions",))}


def _shown(item: Mapping[str, Any]) -> str:
    """One question as the owner sees it: the words, then each option with its description."""
    lines = [str(item.get("question") or "")]
    for option in item.get("options") or ():
        if isinstance(option, Mapping):
            said = str(option.get("description") or "")
            lines.append(f"- {option.get('label', '')}: {said}" if said
                         else f"- {option.get('label', '')}")
    return "\n".join(lines)


def answer_questions(questions: list[Any], config: Mapping[str, Any], owner: Any) -> dict[str, str]:
    """``{question: answer}``, each answered by ``owner.answer(brief, request, shown)``; an owner
    with nothing to say gives ``NO_ANSWER``, so the agent is never left waiting."""
    answers = {}
    for item in questions:
        if not isinstance(item, Mapping) or not item.get("question"):
            continue
        got = owner.answer(str(config.get("brief") or ""), str(config.get("request") or ""),
                           _shown(item))
        answers[str(item["question"])] = got["answer"].strip() or NO_ANSWER
    return answers


class AskServer(mcp.Server):
    """The MCP session: ``mcp.Server`` with the one stand-in tool."""

    def __init__(self, config: Mapping[str, Any], owner: Any) -> None:
        super().__init__(Path.cwd())
        self.config, self.owner = config, owner
        self.handlers["tools/list"] = lambda _p: {"tools": [TOOL]}

    def _initialize(self, params: Mapping[str, Any]) -> dict[str, Any]:
        got = super()._initialize(params)
        got["serverInfo"]["name"] = STAND_IN_SERVER
        got["instructions"] = "The owner's question tool."
        return got

    def _call(self, params: Mapping[str, Any]) -> dict[str, Any]:
        arguments = params.get("arguments") or {}
        questions = arguments.get("questions") if isinstance(arguments, Mapping) else None
        if params.get("name") != STAND_IN_NAME or not isinstance(questions, list):
            raise mcp._RpcError(mcp.INVALID_PARAMS, f"{STAND_IN_NAME} takes a questions array")
        answers = answer_questions(questions, self.config, self.owner)
        said = ", ".join(f'"{q}"="{a}"' for q, a in answers.items())
        data = {"questions": questions, "answers": answers}
        return {"content": [
            {"type": "text", "text": f"User has answered your questions: {said}. You can now "
                                     "continue with the user's answers in mind."},
            {"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
            "structuredContent": data, "isError": False}


def main() -> int:
    from plumb.evaluate.owner import ScriptedOwner

    config = json.loads(Path(os.environ[CONFIG_ENV]).read_text(encoding="utf-8"))
    return mcp.serve(Path.cwd(), server=AskServer(config, ScriptedOwner(
        str(config.get("owner_model") or "haiku"))))


if __name__ == "__main__":
    sys.exit(main())
