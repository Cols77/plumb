"""PostToolUse on AskUserQuestion (or the headless run's stand-in, ``ask_gate.STAND_IN_TOOL``,
DEC-407): the owner's answers to the agent's questions (SR-156).

Logs one ``question-answer`` entry per answered question (session, question, the options shown
with their descriptions, the answer, ``via: question-tool``) as the owner's words, read from the
host's record of the tool call (SR-208 EX-5). An answer to one of the judge's questions
(``judge_questions.json``, matched by its key, or the session's one open question when the
answer is one of its option labels) names the records asked about at their version (``asked``),
and one bare judge job is queued for them: the worker rebuilds the premise with the answer and
judges again (SR-212). An answer to the agent's own wording (``iaso question reword``,
``judge.reworded``) answers every judge question it covers, ``asked.keys`` naming each
(SR-362). An answer to a pending proof question (``proof_questions.json``, filed by ``iaso proof SR-### --ask``
in any checkout of this machine, matched by its key) carries ``proof: {record, hash,
evidence_at}`` and the pending question is removed: the owner's yes is the only confirmation
of a proof (DEC-257, ``proof.owner_confirmed``). The proof is tagged only when the question
shown is the one that record's current passing evidence asks, with YES among its options
(``proof.confirmation``): ``.iaso/session`` is not guarded, so the pending entry only points.
The hook approves nothing. During a merge, rebase, cherry-pick or revert the entries are staged
(``conflicts.stage_choice``) so the commit that finishes it carries them (SR-260 EX-28). A
dismissed or unanswered question logs nothing. The answer
"Study it first" judges nothing either: its entry carries ``study`` (the study serving the
question), the band's study line names that study and the question waits until it is read
(``study.study_first``, SR-336).
"""

from __future__ import annotations

from iaso.paths import state_dir

import json
from pathlib import Path
from typing import Any, TextIO

from iaso.hosts.claude_code.hookio import HookContext, HookOutput, hook_budget, run_hook


def _answered(response: object) -> dict | None:
    """The ``{questions, answers}`` result of a question tool call. AskUserQuestion's response
    is that object; the stand-in is an MCP tool, so the host hands over its result: the same
    object as ``structuredContent``, or as JSON in a text block of ``content`` (DEC-407)."""
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            return None
    if isinstance(response, list):
        response = {"content": response}
    if not isinstance(response, dict):
        return None
    if isinstance(response.get("answers"), dict):
        return response
    if isinstance(response.get("structuredContent"), dict):
        return _answered(response["structuredContent"])
    for block in response.get("content") or ():
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            found = _answered(block["text"]) if block["text"].lstrip().startswith("{") else None
            if found is not None:
                return found
    return None


def handle(ctx: HookContext) -> HookOutput | None:
    asked = ctx.data.get("tool_input")
    response = _answered(ctx.data.get("tool_response"))
    if not isinstance(asked, dict) or response is None:
        return None
    answers = response.get("answers")
    questions = asked.get("questions")
    if not isinstance(answers, dict) or not isinstance(questions, list):
        return None
    _note_asked(ctx)
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
    from iaso.api import open_core
    from iaso.present import owner_text
    from iaso.understand import judge

    core = open_core(ctx.root)
    own = list(judge.unanswered(core, ctx.session_id))
    # then any other session's: the owner's answer here settles a question the CLI or an
    # ended session filed (a merge held on it otherwise never clears)
    left = own + [q for q in judge.unanswered_anywhere(core)
                  if q.get("key") not in {o.get("key") for o in own}]
    key_of = judge.question_key
    worded = {w.get("key"): w for w in judge.reworded(core.root, ctx.session_id)}
    for entry in entries:
        key = key_of(entry["question"])
        covers = (worded.get(key) or {}).get("covers") or ()
        found = next((q for q in left if q.get("key") == key), None) or next(
            (q for q in left if q.get("key") in covers), None)  # SR-362: the agent's wording
        mine = [q for q in left if q in own]
        if found is None and len(mine) == 1 and key_of(entry["answer"]) in {
                key_of(o.get("label")) for o in mine[0].get("options") or ()
                if isinstance(o, dict)}:     # the one open question reworded: its option picked
            found = mine[0]
        if found is not None and entry["answer"] == owner_text.STUDY_FIRST:
            from iaso import study

            left.remove(found)       # SR-336 EX-2: no answer; the question waits for the study
            served = study.serving(ctx.root, str(found.get("key")))
            if served is not None:
                study.study_first(ctx.root, ctx.session_id, served["slug"])
                entry["study"] = served["slug"]
        elif found is not None:
            # SR-362 EX-1: an answer to the agent's wording answers every question it covers
            merged = [found, *(q for q in left if q is not found and q.get("key") in covers)]
            for q in merged:
                left.remove(q)
            # SR-361 EX-3: the answer to a principle reaches the records of all its questions
            group = [*merged, *(q for q in left if found.get("principle")
                                and q.get("principle") == found.get("principle"))]
            entry["asked"] = {"job": found.get("job"), "key": found.get("key"),
                              "principle": found.get("principle") or "",
                              "records": _carried(core, list({
                                  (r.get("id"), r.get("hash")): r for q in group
                                  for r in q.get("records") or () if isinstance(r, dict)
                              }.values()))}
            if covers:
                entry["asked"]["keys"] = [q.get("key") for q in merged]
            if _free_text(entry):
                entry["free_text"] = True   # SR-212: logged and reread, the question stays open
    elsewhere = _tag_proofs(core, ctx.session_id, entries, key_of)
    _tag_waivers(core, ctx.session_id, entries, key_of)
    logged = core.log_append_many("events", [("question-answer", e) for e in entries])
    _share_proofs(core, entries, elsewhere)
    from iaso.mergedriver.conflicts import stage_choice

    stage_choice(core)
    from iaso.understand import gate

    held = gate.state(Path(ctx.root), ctx.session_id)
    if held.reason.startswith(gate.INTENT_CHANGE) and not any(e.get("asked") for e in entries):
        # SR-225 EX-5, SR-378 EX-3: the owner answered the change put to them (not a judge
        # question): the hold on the confirmed record opens, no check is rerun
        gate.open(core, ctx.session_id, held.message_digest, "answer",
                  "the owner answered the question it raised")
    judge.rejudge(core, ctx.session_id, logged)
    return None


def _carried(core: Any, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """SR-216 EX-9: a record superseded while its question was open takes the answer through
    its replacement (at the replacement's current hash), so the old question is closed by it
    and never asked again; any other record keeps the version asked."""
    index = core.index()
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        rid, seen = str(r.get("id")), set()
        item = r
        while rid in index and rid not in seen:
            seen.add(rid)
            later = core.status([rid])[rid].superseded_by
            if not later or later not in index:
                break
            rid, item = later, {**r, "id": later, "hash": index[later].hash}
        out.setdefault(rid, item)
    return list(out.values())


def _free_text(entry: dict[str, Any]) -> bool:
    """Options were shown and the answer is none of their labels (a multi-select answer joins
    labels): the owner's own words, which do not by themselves close the question."""
    labels = [str(o.get("label")) for o in entry.get("options") or () if o.get("label")]
    if not labels:
        return False
    rest = str(entry["answer"])
    for label in sorted(labels, key=len, reverse=True):
        rest = rest.replace(label, "")
    return rest.strip(" ,;\n") != ""


def _note_asked(ctx: HookContext) -> None:
    """SR-361 EX-6: the question tool ran, so the ask gate opens even in a session whose
    pre-tool hook predates the question tool's matcher (hooks.json is read at session start)."""
    from iaso.understand import judge

    if not judge.questions_path(ctx.root, ctx.session_id).exists():
        return
    try:
        from iaso.api import open_core

        judge.note_asked(open_core(ctx.root), ctx.session_id)
    except Exception:  # noqa: BLE001 - logging the owner's answers comes first
        pass


def _share_proofs(core, entries: list[dict], elsewhere: list[tuple[Any, dict]]) -> None:
    """DEC-116, DEC-257: the owner's yes to a proof is an outcome, committed so it follows the
    record through a merge and a renumber; the answer entry itself (their words) stays local.
    A yes to a question filed in another checkout also goes in that checkout's log, where the
    branch delivering the record carries it."""
    from iaso.capture import proof
    from iaso.mergedriver.conflicts import stage_choice

    def share(where, entry: dict) -> None:
        tag = entry.get("proof")
        if isinstance(tag, dict) and entry.get("answer") == proof.YES:
            where.log_append("events", "proof-confirmed", {
                "record": tag.get("record"), "hash": tag.get("hash"),
                "evidence_at": tag.get("evidence_at"), "answer": proof.YES})

    other = {id(entry) for _, entry in elsewhere}
    for entry in entries:
        if id(entry) not in other:       # recorded once, in the checkout that filed the question
            share(core, entry)
    for where, entry in elsewhere:
        try:
            share(where, entry)
            stage_choice(where)
        except Exception:  # noqa: BLE001 - the answer is logged; another checkout never fails it
            pass


def _proof_files(core, session: str, name: str = "") -> list[tuple[Path, Path]]:
    """``(root, file)`` of every pending proof question file (or pending file ``name``): the
    session's own first, then the other session folders of this checkout (the CLI's), then
    those of every other checkout of the repository on this machine, where ``iaso proof --ask``
    in a worktree files them."""
    from iaso import log
    from iaso.capture import proof
    from iaso.understand import files

    name = name or proof.QUESTIONS_FILE
    own = files.session_dir(Path(core.root), session) / name
    found = [(Path(core.root), own)] if own.exists() else []
    for root in (Path(core.root), *log.sibling_roots(core.paths)):
        found += [(root, path) for path in sorted((state_dir(root) / "session").glob(
            f"*/{name}")) if path != own]
    return found


def _tag_waivers(core, session: str, entries: list[dict], key_of) -> None:
    """SR-254 EX-11: an answer to a pending run-or-waive question (``iaso tests ask-waiver``)
    leaves its file; a WAIVE answer is the owner's ``waiver`` of the digest it was asked on,
    logged in the checkout that filed it, where that merge is checked."""
    from iaso.api import open_core
    from iaso.understand import files
    from iaso.verify.policy import WAIVE, WAIVER_QUESTIONS_FILE

    for root, path in _proof_files(core, session, WAIVER_QUESTIONS_FILE):
        asked = files.read_json(path)
        asked = [q for q in asked if isinstance(q, dict)] if isinstance(asked, list) else []
        hits = [(e, q) for e in entries if "waiver" not in e for q in asked
                if q.get("key") == key_of(e["question"])]
        if not hits:
            continue
        try:
            where = core if root == Path(core.root) else open_core(root)
        except Exception:  # noqa: BLE001 - a broken checkout never loses the owner's answer
            continue
        for entry, found in hits:
            if found in asked:
                asked.remove(found)
            if entry["answer"] == WAIVE and WAIVE in [o["label"] for o in entry["options"]]:
                entry["waiver"] = found.get("diff_digest")
                where.log_append("events", "waiver", {
                    "diff_digest": found.get("diff_digest"), "by": "owner",
                    "via": "question-tool", "reason": "the owner waived it through the "
                    "question tool"})
        files.write_json_atomic(path, asked)


def _tag_proofs(core, session: str, entries: list[dict], key_of) -> list[tuple[Any, dict]]:
    """DEC-257: each entry answering a pending proof question gets ``proof`` (when
    ``proof.confirmation`` rebuilds that very question from the record, in the checkout that
    filed it) and that question leaves its ``proof_questions.json``. Returns ``(core, entry)``
    for the entries tagged from another checkout."""
    from iaso.api import open_core
    from iaso.capture import proof
    from iaso.understand import files

    elsewhere: list[tuple[Any, dict]] = []
    for root, path in _proof_files(core, session):
        asked = proof.pending(root, path.parent.name)
        hits = [(e, q) for e in entries if "proof" not in e for q in asked
                if q.get("key") == key_of(e["question"])]
        if not hits:
            continue
        try:
            where = core if root == Path(core.root) else open_core(root)
        except Exception:  # noqa: BLE001 - a broken checkout never loses the owner's answer
            continue
        for entry, found in hits:
            if "proof" in entry:
                continue
            asked.remove(found)
            tag = proof.confirmation(where, found.get("record"), entry["question"],
                                     [o["label"] for o in entry["options"]])
            if tag is not None:
                entry["proof"] = tag
                if where is not core:
                    elsewhere.append((where, entry))
        files.write_json_atomic(path, asked)
    return elsewhere


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False,
         start: float | None = None) -> int:
    return run_hook("question-answer", handle, stdin=stdin, stdout=stdout, root=root,
                    budget_ms=hook_budget("post_edit"), json_output=True, watchdog=watchdog,
                    start=start)
