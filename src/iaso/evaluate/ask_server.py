"""DEC-407: the question tool of the headless benchmark agent. ``claude -p`` has no
AskUserQuestion, so this stdio MCP server stands in for it (``python -m iaso.evaluate.ask_server``,
registered by ``run.claude_turn``): it takes AskUserQuestion's input and answers each question
through the scripted owner (SR-345), from the task's hidden owner brief, before returning.
It returns AskUserQuestion's result, ``{questions, answers: {question: answer}}``, so iaso's
hooks log and judge the answers as the owner's words (``ask_gate.STAND_IN_TOOL``)."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from iaso.hosts.claude_code.ask_gate import STAND_IN_NAME, STAND_IN_SERVER

CONFIG_ENV = "IASO_ASK_CONFIG"   # a JSON file {brief, request, owner_model} written per turn
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
    "inputSchema": {"type": "object", "required": ["questions"], "additionalProperties": False,
                    "properties": {"questions": {"type": "array", "items": _QUESTION,
                                                 "minItems": 1, "maxItems": 4}}}}
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
INVALID_PARAMS, METHOD_NOT_FOUND = -32602, -32601


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


class AskServer:
    """The MCP session, newline-delimited JSON-RPC 2.0 over stdio, with the one stand-in tool
    (iaso's own MCP server is gone: only what a question tool needs is here)."""

    def __init__(self, config: Mapping[str, Any], owner: Any) -> None:
        self.config, self.owner = config, owner

    def handle(self, message: Any) -> dict[str, Any] | None:
        """The response to one message, or None for a notification."""
        if not isinstance(message, Mapping) or "id" not in message:
            return None
        method, params = message.get("method"), message.get("params") or {}
        if method == "initialize":
            asked = params.get("protocolVersion")
            result: Any = {"protocolVersion": asked if asked in PROTOCOL_VERSIONS
                           else PROTOCOL_VERSIONS[0], "capabilities": {"tools": {}},
                           "serverInfo": {"name": STAND_IN_SERVER, "version": "1"},
                           "instructions": "The owner's question tool."}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [TOOL]}
        elif method == "tools/call":
            arguments = params.get("arguments") or {}
            questions = arguments.get("questions") if isinstance(arguments, Mapping) else None
            if params.get("name") != STAND_IN_NAME or not isinstance(questions, list):
                return _error(message["id"], INVALID_PARAMS,
                              f"{STAND_IN_NAME} takes a questions array")
            result = self._call(questions)
        else:
            return _error(message["id"], METHOD_NOT_FOUND, f"method not found: {method}")
        return {"jsonrpc": "2.0", "id": message["id"], "result": result}

    def _call(self, questions: list[Any]) -> dict[str, Any]:
        answers = answer_questions(questions, self.config, self.owner)
        said = ", ".join(f'"{q}"="{a}"' for q, a in answers.items())
        data = {"questions": questions, "answers": answers}
        return {"content": [
            {"type": "text", "text": f"User has answered your questions: {said}. You can now "
                                     "continue with the user's answers in mind."},
            {"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
            "structuredContent": data, "isError": False}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(server: AskServer, stdin: Any = None, stdout: Any = None) -> int:
    """Answer requests until stdin closes."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        try:
            response = server.handle(json.loads(line)) if line.strip() else None
        except ValueError:
            response = _error(None, -32700, "parse error")
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0


def main() -> int:
    from iaso.evaluate.owner import ScriptedOwner

    config = json.loads(Path(os.environ[CONFIG_ENV]).read_text(encoding="utf-8"))
    return serve(AskServer(config, ScriptedOwner(str(config.get("owner_model") or "haiku"))))


if __name__ == "__main__":
    sys.exit(main())
