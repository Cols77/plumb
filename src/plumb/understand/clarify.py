"""The clarify job kind (SHOW, spec 4.3): is the owner's request clear and complete?

``build`` queues one job per owner message (its ``needs`` is the message's read job, so an answer
the owner has just given is applied first); its inputs carry the conversation before the
message and the repository facts (SR-128), frozen when the prompt arrives; ``recompute``
rebuilds the inputs from the logs and that frozen context; ``apply`` stores every gap that blocks, all of them (SR-223 EX-15), for ``clarify --wait``
to hand to the agent, who asks them at once with the question tool; no card is drawn and no spec
session is offered for the count. Only the intent loop's own gate holds edits. ``on_prompt`` is the prompt hook's side: it closes the gate and queues the job, and never
waits."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, Choice, ClarifyQuestion, Job
from plumb.present import owner_text
from plumb.understand import files, gate
from plumb.understand.typed import PREFIX

kind = "clarify"
SCHEMA_ID = "clarify.v1"
HERE = Path(__file__).resolve().parent
GAP_FILE = "clarify_gaps.json"   # SR-223 EX-15: the gaps to ask, written by ``apply``
GO_TEXT = re.compile(r"^" + PREFIX + r"[ \t]+go$")   # SR-120: /plumb go or /plumb:plumb go

COULDNT_TIMEOUT = "the check was still running"
GATE_REASON_CHECKING = "your request is being checked"
GATE_REASON_COULDNT = "the check of your request did not finish"
GATE_RELEASED = "You said to build without the check; edits are allowed again."


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "clarify.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**data, "id": SCHEMA_ID}


schema: Mapping[str, Any] = _load_schema()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def short(digest: str) -> str:
    return digest.removeprefix("sha256:")[:12]


# ---------------------------------------------------------------- inputs


def _message_of(context: Mapping[str, Any]) -> tuple[str, str]:
    raw = context.get("message")
    if isinstance(raw, Mapping):
        return str(raw.get("digest") or ""), str(raw.get("text") or "")
    return str(context.get("digest") or ""), str(context.get("text") or "")


def touched(core: Any, text: str) -> list[dict[str, str]]:
    """The confirmed records the message seems to touch, with their text."""
    from plumb.query import record_text

    found = [rid for rid, _ in core.relevant(text, 8)]
    if not found:
        return []
    index = core.index()
    statuses = core.status(found)
    out: list[dict[str, str]] = []
    for rid in found:
        status = statuses.get(rid)
        record = index.get(rid)
        if record is None or status is None or status.confirmation != "confirmed":
            continue
        out.append({"id": rid, "status": "confirmed", "text": record_text(record)})
    return out


def answered_for(core: Any, session: str, digest: str) -> list[dict[str, str]]:
    """The questions this message answered, as ``{question, text, answer}`` (the clarify check
    logged each as a ``question-answer`` entry)."""
    return [{"question": str(e.payload.get("question") or ""),
             "text": str(e.payload.get("question") or ""),
             "answer": str(e.payload.get("answer") or "")}
            for e in core.events() if e.kind == "question-answer"
            and e.payload.get("session") == session and e.payload.get("message_digest") == digest]


# SR-128: the conversation the message belongs to. The reader resolves "the findings above" or
# "this issue" only from the agent's last reply and the owner's previous messages, read from
# the host's transcript and cut to a budget; a transcript that cannot be read leaves the
# message alone, as before. After a /compact the host's summary of what came before is given
# too (``summary``), and the owner's other recent sessions of the same project
# (``other_sessions``: "the issue we found in that chat" points into one of them), each its last
# reply and the owner's last messages, from the transcripts beside this one.
REPLY_BUDGET = 4000          # the agent's last reply, kept from its end
EARLIER_COUNT = 3            # the owner's previous messages
EARLIER_BUDGET = 500         # each, kept from its start
SUMMARY_BUDGET = 3000        # the compaction summary, kept from its start
TAIL_READS = (256 * 1024, 1024 * 1024, 4 * 1024 * 1024)   # the transcript is read from its end
OTHER_COUNT = 2              # the owner's other sessions of the project, most recent first
OTHER_WINDOW_S = 7 * 24 * 3600   # ... written to in the last week
OTHER_REPLY_BUDGET = 1500    # each one's last reply, kept from its end
OTHER_EARLIER_BUDGET = 300   # each of its owner's last messages, kept from its start
CUT = "…"
# what the host writes in the owner's place: slash-command envelopes, local command output,
# background-task notices, reminders. Anything else, a message starting with "<" too (pasted
# HTML), is the owner's own words.
HOST_NOTICE = re.compile(r"^<(?:command-|local-command-|task-notification|system-reminder|"
                         r"bash-|user-prompt-submit-hook)")


def _cut_end(text: str, budget: int) -> str:
    """The last ``budget`` characters of ``text`` (a reply ends with what it concludes)."""
    text = text.strip()
    return text if len(text) <= budget else CUT + text[-(budget - len(CUT)):].lstrip()


def _cut_start(text: str, budget: int) -> str:
    text = text.strip()
    return text if len(text) <= budget else text[:budget - len(CUT)].rstrip() + CUT


def _entry_text(entry: Any, role: str) -> str | None:
    """The plain text of a transcript entry spoken by ``role``: the owner's own words or the
    agent's reply text. Tool calls and results, injected (meta) entries, subagent turns, the
    compaction summary (``_summary_text``) and host notices (``<task-notification>``,
    ``<command-name>``..., ``HOST_NOTICE``) are not the conversation."""
    if not isinstance(entry, Mapping) or entry.get("isMeta") or entry.get("isSidechain") \
            or entry.get("isCompactSummary"):
        return None
    message = entry.get("message")
    if not isinstance(message, Mapping) or message.get("role") != role:
        return None
    content = message.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        blocks = [b for b in content if isinstance(b, Mapping)]
        if role == "user" and any(b.get("type") == "tool_result" for b in blocks):
            return None
        text = "\n".join(str(b.get("text") or "") for b in blocks if b.get("type") == "text")
    else:
        return None
    text = text.strip()
    if not text or (role == "user" and HOST_NOTICE.match(text)):
        return None
    return text


def _summary_text(entry: Any) -> str | None:
    """The host's summary of the conversation before a /compact (a user entry marked
    ``isCompactSummary``), or None."""
    if not isinstance(entry, Mapping) or not entry.get("isCompactSummary"):
        return None
    message = entry.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    if isinstance(content, list):
        content = "\n".join(str(b.get("text") or "") for b in content
                            if isinstance(b, Mapping) and b.get("type") == "text")
    return content.strip() or None if isinstance(content, str) else None


def _turns(lines: Sequence[str]) -> list[tuple[str, str]]:
    """``(who, text)`` in order, ``who`` being ``owner``, ``agent`` or ``summary`` (the
    compaction summary, which stands for every turn before it)."""
    out: list[tuple[str, str]] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        summary = _summary_text(entry)
        if summary is not None:
            out.append(("summary", summary))
            continue
        for role, who in (("user", "owner"), ("assistant", "agent")):
            text = _entry_text(entry, role)
            if text is not None:
                out.append((who, text))
    return out


def _tail_turns(path: Path, reads: Sequence[int] = TAIL_READS) -> list[tuple[str, str]]:
    """The transcript's turns, read from its end: enough of it to hold the owner's last few
    messages (or reach the compaction summary that stands for them), never more than the
    largest read (a long session stays cheap on the prompt path)."""
    size = path.stat().st_size
    turns: list[tuple[str, str]] = []
    for limit in reads:
        start = max(0, size - limit)
        with open(path, "rb") as handle:
            handle.seek(start)
            raw = handle.read()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if start:
            lines = lines[1:]                     # the first line read is a partial one
        turns = _turns(lines)
        if not start or sum(1 for who, _ in turns if who == "owner") > EARLIER_COUNT \
                or any(who == "summary" for who, _ in turns):
            break
    return turns


def _talk(turns: Sequence[tuple[str, str]], reply_budget: int, earlier_budget: int
          ) -> dict[str, Any]:
    """The last reply (every reply text since the owner's last message in ``turns``), the
    owner's last ``EARLIER_COUNT`` messages and the latest compaction summary of ``turns``."""
    summaries = [n for n, (who, _) in enumerate(turns) if who == "summary"]
    summary = turns[summaries[-1]][1] if summaries else ""
    if summaries:
        after = turns[summaries[-1] + 1:]
        # a session that ended right after its compaction: its last turns are the ones the
        # summary stands for, still read where the tail holds them
        before = [t for t in turns[:summaries[-1]] if t[0] != "summary"]
        turns = after if any(who != "summary" for who, _ in after) else before
    owner = [n for n, (who, _) in enumerate(turns) if who == "owner"]
    since = owner[-1] + 1 if owner else 0
    reply = "\n\n".join(text for who, text in turns[since:] if who == "agent")
    talk: dict[str, Any] = {
        "last_reply": _cut_end(reply, reply_budget),
        "earlier_messages": [_cut_start(turns[n][1], earlier_budget)
                             for n in owner[-EARLIER_COUNT:]]}
    if summary:
        talk["summary"] = _cut_start(summary, SUMMARY_BUDGET)
    return talk


def other_sessions(transcript: Path, now: float | None = None) -> list[dict[str, Any]]:
    """The owner's other recent sessions of the same project: the transcripts beside
    ``transcript`` (the host keeps one folder per project), the ``OTHER_COUNT`` written to most
    recently within ``OTHER_WINDOW_S``, each read from its end once (``TAIL_READS[0]``) for its
    last reply, the owner's last messages and its compaction summary. Unreadable ones are left
    out."""
    import time

    now = time.time() if now is None else now
    try:
        found = []
        for path in transcript.parent.glob("*.jsonl"):
            if path.name == transcript.name:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if now - mtime <= OTHER_WINDOW_S:
                found.append((mtime, path))
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for mtime, path in sorted(found, reverse=True):
        if len(out) >= OTHER_COUNT:
            break
        try:
            turns = _tail_turns(path, TAIL_READS[:1])
        except OSError:
            continue
        talk = _talk(turns, OTHER_REPLY_BUDGET, OTHER_EARLIER_BUDGET)
        if not talk["last_reply"] and not talk["earlier_messages"] and "summary" not in talk:
            continue
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime))
        out.append({"last_active": stamp, **talk})
    return out


def conversation(transcript: Any, message: str) -> dict[str, Any] | None:
    """The conversation before ``message``: the agent's last reply (every reply text since the
    owner's previous message, cut to its last ``REPLY_BUDGET`` characters) and the owner's
    previous ``EARLIER_COUNT`` messages (oldest first, each cut to ``EARLIER_BUDGET``). The
    message itself is left out when the host already wrote it. None when there is no
    transcript, it cannot be read, or it holds no earlier turn."""
    if not isinstance(transcript, str) or not transcript:
        return None
    try:
        turns = _tail_turns(Path(transcript))
    except OSError:
        return None
    owner = [n for n, (who, _) in enumerate(turns) if who == "owner"]
    if owner and turns[owner[-1]][1] == message.strip():
        turns = turns[:owner[-1]]
    talk = _talk(turns, REPLY_BUDGET, EARLIER_BUDGET)
    if not talk["last_reply"] and not talk["earlier_messages"] and "summary" not in talk:
        return None
    return talk


def repository(root: Path) -> dict[str, Any]:
    """What the reader may say about the repository: its root, whether it is a git repository
    (the root or a folder above it holds ``.git``) and the branch checked out. Read from git's
    files, no git process on the prompt path."""
    from plumb.awareness import gitfiles

    root = Path(root)
    for folder in (root, *root.parents):
        if (folder / ".git").exists():
            found = gitfiles.current(folder)
            if found is not None:
                return {"root": str(root), "git": True, "branch": found.branch or ""}
    return {"root": str(root), "git": False, "branch": ""}


def context_path(root: Path, session: str, digest: str) -> Path:
    return files.session_dir(root, session) / "clarify_context" / f"{short(digest)}.json"


def frozen_context(root: Path, session: str, digest: str, transcript: Any = None,
                   message: str = "") -> dict[str, Any]:
    """The conversation and repository facts of the message, written once when the prompt
    arrives and read back after, so the job's inputs recompute the same (the transcript keeps
    growing; the reader must see the conversation as it was when the owner spoke)."""
    path = context_path(root, session, digest)
    known = files.read_json(path)
    if isinstance(known, Mapping) and isinstance(known.get("repository"), Mapping):
        return dict(known)
    frozen: dict[str, Any] = {"repository": repository(root)}
    talk = conversation(transcript, message) if transcript else None
    if talk is not None:
        frozen["context"] = talk
    if isinstance(transcript, str) and transcript:
        others = other_sessions(Path(transcript))
        if others:
            frozen["other_sessions"] = others
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        files.write_json_atomic(path, frozen)
    except OSError:
        pass
    return frozen


def sent_at(core: Any, digest: str) -> str:
    """When the owner last sent the message: the same words sent again are checked again."""
    from plumb.approvals import Refused, find_prompt

    try:
        return str(find_prompt(core, digest).get("at") or "")
    except Refused:
        return ""


def _inputs(core: Any, session: str, digest: str, text: str,
            answered: Sequence[Mapping[str, str]], frozen: Mapping[str, Any] | None = None
            ) -> dict[str, Any]:
    out = {"message": {"digest": digest, "text": text, "at": sent_at(core, digest)},
           "touched": touched(core, text),
           "answered": [dict(a) for a in answered]}
    out.update(frozen or {})
    return out


def build(core: Any, session: str, **context: Any) -> Job | None:
    """Queue the clarify job of the owner message in ``context['message']``
    (``{digest, text}``); ``context['after']`` is the id of the message's read job, which
    becomes ``Job.needs``; ``context['transcript']`` is the host's transcript, read for the
    conversation before the message. The same message gives the same job id."""
    from plumb.understand import queue

    digest, text = _message_of(context)
    text = commanded_words(text) or text      # SR-171: the check reads the words, not the command
    if not text.strip():
        return None
    after = context.get("after")
    frozen = frozen_context(Path(core.root), session, digest, context.get("transcript"), text)
    job = files.make_job(kind, session, SCHEMA_ID, _inputs(core, session, digest, text, (), frozen),
                         needs=str(after) if after else None, created=_now())
    queue.enqueue(core, job)
    return job


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    """The job's inputs from the logs: the message from the prompt log, the confirmed records
    it touches now, and the clarify questions the reader mapped from it (after the read job
    was applied). None when the message is not in the prompt log."""
    from plumb.approvals import Refused, find_prompt

    message = job.inputs.get("message")
    digest = str(message.get("digest") if isinstance(message, Mapping) else "")
    try:
        logged = find_prompt(core, digest)
    except Refused:
        return None
    digest = str(logged["digest"])
    return _inputs(core, job.session, digest,
                   commanded_words(str(logged.get("text") or "")) or str(logged.get("text") or ""),
                   answered_for(core, job.session, digest),
                   frozen_context(Path(core.root), job.session, digest))


# ---------------------------------------------------------------- apply


def _clean(items: Any) -> list[str]:
    if not isinstance(items, (list, tuple)):
        return []
    return [str(i).strip() for i in items if str(i).strip()]


def _gap_question(gap: Mapping[str, Any], n: int) -> ClarifyQuestion:
    """The gap as one question: the recommended suggestion first, each with its consequence."""
    suggestions = _clean(gap.get("suggestions"))
    lines = [*_clean(gap.get("consequences")), *[""] * len(suggestions)][:len(suggestions)]
    try:
        first = int(gap.get("recommended") or 0)
    except (TypeError, ValueError):
        first = 0
    if 0 < first < len(suggestions):
        suggestions.insert(0, suggestions.pop(first))
        lines.insert(0, lines.pop(first))
    ident = re.sub(r"[^a-z0-9_-]+", "-", str(gap.get("id") or "").lower()).strip("-") or f"q{n}"
    return ClarifyQuestion(
        id=ident, text=str(gap.get("question") or "").strip(), resolutions=tuple(suggestions),
        choices=tuple(Choice(t, "change", t, c) for t, c in zip(suggestions, lines, strict=False)))


def _already_answered(question: ClarifyQuestion, answered: Sequence[Mapping[str, Any]]) -> bool:
    for item in answered:
        if str(item.get("question")) == question.id:
            return True
        if question.text and str(item.get("text", "")).strip().lower() == question.text.lower():
            return True
    return False


def request_records(core: Any, digest: str) -> list[Any]:
    """The records of the request ``digest``: the intents whose ``prompt`` field is its digest
    (a 12+ hex prefix either way), and what derives from or decides them, however deep."""
    want = digest.removeprefix("sha256:")
    index = core.index()
    found = set()
    for r in index.values():
        said = str(r.fields.get("prompt") or "")
        if r.kind == "intent" and len(said) >= 12 and (want.startswith(said)
                                                       or said.startswith(want)):
            found.add(r.id)
    while True:
        more = {r.id for r in index.values() if r.id not in found and any(
            link.kind in ("derives_from", "decides") and link.target.record in found
            for link in r.links)}
        if not more:
            return [index[i] for i in sorted(found)]
        found |= more


def _clipped(text: str) -> str:
    clipped = " ".join(text.split())
    return clipped if len(clipped) <= 80 else clipped[:79].rstrip() + "..."


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    if core is None:
        return Applied(job=job.id)
    root = Path(core.root)
    message = job.inputs.get("message")
    digest = str(message.get("digest") if isinstance(message, Mapping) else "")
    text = str(message.get("text") if isinstance(message, Mapping) else "")
    session = job.session
    from plumb.understand import read

    early: Applied | None = None
    said = answer.get("answers")     # SR-163: a clear answer to a question just put to the owner
    if isinstance(said, Mapping) and read.evidence_in(str(said.get("evidence") or ""), text):
        question = str(said.get("question") or "").strip()
        gate.open(core, session, digest, "clarify", "your message answers a question")
        entries = ({"kind": "question-answer", "payload": {
            "session": session, "question": question, "options": [],
            "answer": str(said["evidence"]), "message_digest": digest}},) if question else ()
        early = Applied(job=job.id, entries=entries)
        if not (str(said.get("also") or "").strip() and str(answer.get("intent")) == "yes"):
            return early      # SR-187: the whole message was the answer
    if str(answer.get("intent")) != "yes":
        gate.open(core, session, digest, "clarify", "your message carries no new request")
        return Applied(job=job.id)
    answered = [a for a in job.inputs.get("answered") or () if isinstance(a, Mapping)]
    gaps = [(g, _gap_question(g, n)) for n, g in enumerate(answer.get("gaps") or (), 1)
            if isinstance(g, Mapping)]
    gaps = [(g, q) for g, q in gaps if q.text and not _already_answered(q, answered)]
    # SR-223 EX-15: every gap with no better-supported answer is asked, all at once, with the
    # question tool; a count alone offers no spec session; a gap that is not blocking is
    # assumed. The questions are stored for ``clarify --wait`` to hand to the agent
    open_gaps = [(g, q) for g, q in gaps if g.get("blocking")]
    store_gap_questions(root, session, digest, [q for _, q in open_gaps])
    if hold := intent_change_hold(core, session, digest):
        gate.refresh(root, session, digest, hold)   # SR-225: only a request holds
    else:
        gate.open(core, session, digest, "clarify",
                  "the questions are answered" if answered else "nothing is unclear")
    return early if early is not None else Applied(job=job.id)


def store_gap_questions(root: Path, session: str, digest: str,
                        questions: Sequence[ClarifyQuestion]) -> None:
    """SR-223 EX-15: the message's blocking gaps, all of them, as the question tool takes
    them (``key``, ``question``, ``header``, ``options``); the newest message replaces the
    older ones. Nothing is drawn on a card."""
    rows = [{"key": " ".join(q.text.lower().split()), "reword": False, "question": q.text,
             "header": "Decision", "blocking": True, "digest": digest,
             "options": [{"label": c.label, "description": c.consequence}
                         for c in q.choices][:4]} for q in questions if len(q.choices) >= 2]
    files.write_json_atomic(files.session_dir(root, session) / GAP_FILE, rows)


def gap_questions(core: Any, session: str) -> list[dict[str, Any]]:
    """SR-223 EX-15: the stored gap questions the owner has not answered yet."""
    raw = files.read_json(files.session_dir(Path(core.root), session) / GAP_FILE)
    said = {" ".join(str(e.payload.get("question") or "").lower().replace(
        "(recommended)", "").split()) for e in core.events() if e.kind == "question-answer"
        and e.payload.get("session") == session}
    return [dict(r) for r in raw if isinstance(r, Mapping) and r.get("key") not in said] \
        if isinstance(raw, list) else []


def describe(job: Job) -> str:
    return owner_text.STEP_CHECKING


# ---------------------------------------------------------------- the failed check


def write_couldnt_check(core: Any, session: str, digest: str) -> None:
    """The check of the message could not be made: the gate it closed opens, and the agent
    works on (SR-225 EX-9, SR-378 EX-4); no card is filed."""
    gate.open(core, session, digest, "couldnt-check", GATE_REASON_COULDNT)


def intent_change_hold(core: Any, session: str, digest: str) -> str:
    """SR-225: the gate reason for a request the prompt hook flagged as changing a confirmed
    record (``intent_flags.jsonl``) while no intent loop ran for it (``plumb intent open``
    writes ``intent/<digest12>.json``); "" otherwise. The reader has already found a request
    in the message: a question or a notice never reaches this."""
    root = Path(core.root)
    short = digest.removeprefix("sha256:")[:12]
    if (files.session_dir(root, session) / "intent" / f"{short}.json").is_file():
        return ""
    try:
        rows = [json.loads(line) for line in (files.session_dir(root, session).parent
                                              / "intent_flags.jsonl")
                .read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return ""
    index = core.index()
    for row in rows:
        if not isinstance(row, Mapping) or row.get("session") != session \
                or row.get("prompt_digest") != digest:
            continue
        record = index.get(str(row.get("subject")))
        if record is not None:
            return " ".join([gate.INTENT_CHANGE, record.id, *(e.id for e in record.examples)])
    return ""


# ---------------------------------------------------------------- the prompt hook's side


def is_typed_go(text: str) -> bool:
    return bool(GO_TEXT.match(text.strip()))


def commanded_words(text: str) -> str | None:
    """The words of a typed ``/plumb clarify <words>`` (SR-171) or ``/plumb intent <words>``
    (SR-193), else None."""
    from plumb.understand import typed

    parsed = typed.parse(text)
    return parsed.words if parsed is not None and parsed.command in ("clarify", "intent") else None


def _typed_settle(text: str) -> bool:
    from plumb.understand import typed

    parsed = typed.parse(text)
    return parsed is not None and parsed.command == "settle"


def on_prompt(ctx: Any, core: Any, entry: Any, *, after: str | None = None) -> list[str]:
    """Close the gate for this message and queue its clarify job (idempotent, no wait). The
    typed ``/plumb go`` releases a failed check instead and carries no request of its own.
    Returns the agent-facing lines."""
    session = str(getattr(ctx, "session_id", "") or "")
    digest = str(entry.get("digest") if isinstance(entry, Mapping) else "")
    text = str(entry.get("text") if isinstance(entry, Mapping) else "")
    if not session or not digest:
        return []
    if text.strip() and _typed_settle(text):
        return []                         # SR-134 EX-2: typed.on_prompt tells the owner it is gone
    if is_typed_go(text):
        if gate.release(core, session, "typed", digest=digest):
            return [GATE_RELEASED]
        return []
    data = getattr(ctx, "data", None)
    transcript = data.get("transcript_path") if isinstance(data, Mapping) else None
    words = commanded_words(text)
    if words is None:                     # SR-171 EX-1: an ordinary message is not checked;
        frozen_context(Path(core.root), session, digest, transcript, text)   # SR-208 EX-4:
        return []                         # the judge's pre-intent keeps the reply it answered
    gate.close(Path(core.root), session, digest, GATE_REASON_CHECKING)
    build(core, session, message={"digest": digest, "text": text}, after=after,
          transcript=transcript)
    return [owner_text.GATE_CLOSED.format(reason=GATE_REASON_CHECKING)]
