"""PostToolUse on AskUserQuestion: the owner's answers to the agent's questions (SR-156).

Logs one ``question-answer`` entry per answered question (session, question, the labels shown,
the answer) as the owner's words. It never confirms, rejects or changes a record: only a card
press or the owner's typed command does. A dismissed or unanswered question logs nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from plumb.hosts.claude_code.hookio import HookContext, HookOutput, hook_budget, run_hook


def handle(ctx: HookContext) -> HookOutput | None:
    asked = ctx.data.get("tool_input")
    response = ctx.data.get("tool_response")
    if not isinstance(asked, dict) or not isinstance(response, dict):
        return None
    answers = response.get("answers")
    questions = asked.get("questions")
    if not isinstance(answers, dict) or not isinstance(questions, list):
        return None
    entries = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        answer = answers.get(item.get("question"))
        if not isinstance(answer, str) or not answer:
            continue
        shown = [o.get("label") for o in item.get("options") or [] if isinstance(o, dict)]
        entries.append(("question-answer", {"session": ctx.session_id,
                                            "question": item["question"],
                                            "options": shown, "answer": answer}))
    if entries:
        from plumb.api import open_core

        open_core(ctx.root).log_append_many("events", entries)
    return None


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False,
         start: float | None = None) -> int:
    return run_hook("question-answer", handle, stdin=stdin, stdout=stdout, root=root,
                    budget_ms=hook_budget("post_edit"), json_output=True, watchdog=watchdog,
                    start=start)
