"""PostToolUse on AskUserQuestion: the owner's answers to the agent's questions (SR-156).

Logs one ``question-answer`` entry per answered question (session, question, the options shown
with their descriptions, the answer, ``via: question-tool``) as the owner's words, read from the
host's record of the tool call (SR-208 EX-5). An answer to one of the judge's questions
(``judge_questions.json``, matched by its key, or the session's one open question when the
answer is one of its option labels) names the records asked about at their version (``asked``),
and one bare judge job is queued for them: the worker rebuilds the premise with the answer and
judges again (SR-212). An answer to a pending proof question (``proof_questions.json``,
filed by ``plumb proof SR-### --ask``, matched by its key) carries ``proof: {record, hash,
evidence_at}`` and the pending question is removed: the owner's yes is the only confirmation
of a proof (DEC-257, ``proof.owner_confirmed``). The proof is tagged only when the question
shown is the one that record's current passing evidence asks, with YES among its options
(``proof.confirmation``): ``.plumb/session`` is not guarded, so the pending entry only points.
The hook approves nothing. During a merge, rebase, cherry-pick or revert the entries are staged
(``conflicts.stage_choice``) so the commit that finishes it carries them (SR-260 EX-28). A
dismissed or unanswered question logs nothing. The answer "Build anyway" to a failed check's
"Build without the check?" releases the gate (``gate.release`` ... ``button``).
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
            # SR-334 EX-2: the answer to a principle reaches the records of all its questions
            group = [found, *(q for q in left if found.get("principle")
                              and q.get("principle") == found.get("principle"))]
            entry["asked"] = {"job": found.get("job"), "key": found.get("key"),
                              "records": list({(r.get("id"), r.get("hash")): r for q in group
                                               for r in q.get("records") or ()
                                               if isinstance(r, dict)}.values())}
    _tag_proofs(core, ctx.session_id, entries, key_of)
    logged = core.log_append_many("events", [("question-answer", e) for e in entries])
    from plumb.mergedriver.conflicts import stage_choice

    stage_choice(core)
    from plumb.present import owner_text
    from plumb.understand import clarify, gate

    if any(e["question"] == clarify.COULDNT_QUESTION and e["answer"] == owner_text.GATE_BUILD_ANYWAY
           for e in entries):      # the owner's own button on a failed check (gate.release)
        gate.release(core, ctx.session_id, "button")
    ids = [str(r.get("id")) for e in entries for r in (e.get("asked") or {}).get("records", ())
           if isinstance(r, dict)]
    if ids:      # the records are rebuilt from the logs by the worker (judge.recompute)
        queue.enqueue(core, files.make_job(judge.kind, ctx.session_id, judge.SCHEMA_ID, {
            "records": list(dict.fromkeys(ids)), "answered": [e.digest for e in logged]}))
    return None


def _tag_proofs(core, session: str, entries: list[dict], key_of) -> None:
    """DEC-257: each entry answering a pending proof question gets ``proof`` (when
    ``proof.confirmation`` rebuilds that very question from the record) and that question
    leaves the session's ``proof_questions.json``."""
    from plumb.capture import proof
    from plumb.understand import files

    asked = proof.pending(core.root, session)
    if not asked:
        return
    for entry in entries:
        key = key_of(entry["question"])
        found = next((q for q in asked if q.get("key") == key), None)
        if found is not None:
            asked.remove(found)
            tag = proof.confirmation(core, found.get("record"), entry["question"],
                                     [o["label"] for o in entry["options"]])
            if tag is not None:
                entry["proof"] = tag
    files.write_json_atomic(proof.questions_path(core.root, session), asked)


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False,
         start: float | None = None) -> int:
    return run_hook("question-answer", handle, stdin=stdin, stdout=stdout, root=root,
                    budget_ms=hook_budget("post_edit"), json_output=True, watchdog=watchdog,
                    start=start)
