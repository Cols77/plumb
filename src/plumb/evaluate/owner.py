"""The scripted owner (SR-345): answers the agent's questions from a hidden brief, one cheap
model call each, and sees only the request and the agent's reply, never the repository."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from plumb.contracts import DispatchError, Job
from plumb.understand import agents
from plumb.understand.dispatch.claude_code import ClaudeCodeDispatcher

OWNER_SCHEMA = {"type": "object", "required": ["asks", "answer"], "additionalProperties": False,
                "properties": {"asks": {"type": "boolean"}, "answer": {"type": "string"}}}
SILENT = {"asks": False, "answer": ""}


class ScriptedOwner:
    def __init__(self, model: str = "haiku", dispatcher: Any = None,
                 timeout_s: float = 120) -> None:
        self.model = model
        self.dispatcher = dispatcher or ClaudeCodeDispatcher(model=model, timeout_s=timeout_s)
        self.notes: list[str] = []  # dispatch failures, for the transcript

    def answer(self, brief: str, request: str, reply: str) -> dict:
        system = agents.load("owner") + "\n\n# The owner's picture\n" + brief
        user = json.dumps({"request": request, "reply": reply}, ensure_ascii=False)
        try:
            job = Job(id="owner-" + hashlib.sha256(user.encode()).hexdigest()[:16], kind="owner")
            got = self.dispatcher.run(job, system=system, user=user, schema=OWNER_SCHEMA,
                                      on_step=lambda _step: None)
        except DispatchError as exc:
            self.notes.append(f"scripted owner unavailable: {exc}")
            return dict(SILENT)
        return {"asks": bool(got.get("asks")), "answer": str(got.get("answer", ""))}
