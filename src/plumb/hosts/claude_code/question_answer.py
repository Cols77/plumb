"""PostToolUse on AskUserQuestion: the owner's answers to the agent's questions (SR-156).

Logs one ``question-answer`` entry per answered question (session, question, the options shown
with their descriptions, the answer, ``via: question-tool``) as the owner's words, read from the
host's record of the tool call (SR-208 EX-5). An answer to one of the judge's questions
(``judge_questions.json``, matched by its key, or the session's one open question when the
answer is one of its option labels) names the records asked about at their version (``asked``),
and one bare judge job is queued for them: the worker rebuilds the premise with the answer and
judges again (SR-212). The hook reads no record and approves nothing.
A dismissed or unanswered question logs nothing.
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
        shown = [{"label": o.get("label"), "description": o.get("description") or ""}
                 for o in item.get("options") or [] if isinstance(o, dict)]
        entries.append({"session": ctx.session_id, "question": item["question"],
                        "options": shown, "answer": answer, "via": "question-tool"})
    if not entries:
        return None
    from plumb.api import open_core
    from plumb.understand import files, judge, queue

    core = open_core(ctx.root)
    left = list(judge.unanswered(core, ctx.session_id))
    key_of = judge.question_key
    for entry in entries:
        key = key_of(entry["question"])
        found = next((q for q in left if q.get("key") == key), None)
        if found is None and len(left) == 1 and key_of(entry["answer"]) in {
                key_of(o.get("label")) for o in left[0].get("options") or ()
                if isinstance(o, dict)}:     # the one open question reworded: its option picked
            found = left[0]
        if found is not None:
            left.remove(found)
            entry["asked"] = {"job": found.get("job"), "key": found.get("key"),
                              "records": list(found.get("records") or ())}
    logged = core.log_append_many("events", [("question-answer", e) for e in entries])
    ids = [str(r.get("id")) for e in entries for r in (e.get("asked") or {}).get("records", ())
           if isinstance(r, dict)]
    if ids:      # the records are rebuilt from the logs by the worker (judge.recompute)
        queue.enqueue(core, files.make_job(judge.kind, ctx.session_id, judge.SCHEMA_ID, {
            "records": list(dict.fromkeys(ids)), "answered": [e.digest for e in logged]}))
    return None


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False,
         start: float | None = None) -> int:
    return run_hook("question-answer", handle, stdin=stdin, stdout=stdout, root=root,
                    budget_ms=hook_budget("post_edit"), json_output=True, watchdog=watchdog,
                    start=start)
