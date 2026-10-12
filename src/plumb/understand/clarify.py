"""The clarify job kind (SHOW, spec 4.3): is the owner's request clear and complete?

``build`` queues one job per owner message (its ``needs`` is the message's read job, so a card
the owner has just answered is applied first); its inputs carry the conversation before the
message and the repository facts (SR-128), frozen when the prompt arrives; ``recompute``
rebuilds the inputs from the logs, the card store and that frozen context; ``apply`` turns
the model's answer into at most one card of three questions (the smaller gaps as labelled
assumptions on it), an offer of a short spec session when more than three questions change
what gets built, or nothing (no intent, no gap), and opens the gate when nothing is left to
ask. ``on_prompt`` is the prompt hook's side: it closes the gate and queues the job, and never
waits."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, CardState, ClarifyQuestion, Job
from plumb.present import owner_text
from plumb.understand import cardstore, files, gate
from plumb.understand.cards import choices_for
from plumb.understand.typed import PREFIX

kind = "clarify"
SCHEMA_ID = "clarify.v1"
HERE = Path(__file__).resolve().parent
MAX_QUESTIONS = 3
GO_TEXT = re.compile(r"^" + PREFIX + r"[ \t]+go$")   # SR-120: /plumb go or /plumb:plumb go

TOPIC_FALLBACK = "your request"
ISSUE_QUESTIONS = "{n} things would change what I build, and I need your answer before I start"
ISSUE_ESCALATION = ("{n} things would change what I build; a short spec session settles them "
                    "better than {n} questions")
SPEC_QUESTION = "Shall we go through them in a short spec session first?"
SPEC_YES = "Yes, a short spec session"
SPEC_NO = "No, build with my best guesses"
COULDNT_ISSUE = "I could not check whether your request is clear: {why}. Nothing was built."
COULDNT_TIMEOUT = "the check was still running"
COULDNT_QUESTION = "Build without the check?"
EVIDENCE_WILL = "  I will: {text}"
EVIDENCE_WONT = "  I will not: {text}"
EVIDENCE_ASSUMED = "  Assumed (not confirmed): {text}"
EVIDENCE_EXAMPLE = "  For example: {text}"
ESCALATION_MARK = "Escalation: short spec session"
GATE_REASON_CARD = "a question about your request is waiting for your answer"
GATE_REASON_ESCALATION = "a short spec session is offered before building"
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


def card_id(digest: str) -> str:
    return f"clarify:{short(digest)}"


def couldnt_card_id(digest: str) -> str:
    return f"couldnt_check:{short(digest)}"


# ---------------------------------------------------------------- inputs


def _message_of(context: Mapping[str, Any]) -> tuple[str, str]:
    raw = context.get("message")
    if isinstance(raw, Mapping):
        return str(raw.get("digest") or ""), str(raw.get("text") or "")
    return str(context.get("digest") or ""), str(context.get("text") or "")


def touched(core: Any, text: str) -> list[dict[str, str]]:
    """The confirmed (and settled) records the message seems to touch, with their text."""
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
        out.append({"id": rid, "status": "settled" if getattr(status, "settled", False)
                    else "confirmed", "text": record_text(record)})
    return out


def answered_for(root: Path, session: str, digest: str) -> list[dict[str, str]]:
    """The questions of clarify cards this message answered (what the reader just mapped), as
    ``{card, question, text, answer}``; a question answered "rejected" is not an answer."""
    out: list[dict[str, str]] = []
    for card in cardstore.own_cards(root, session):
        if card.kind != "clarify":
            continue
        texts = {q.id: q.text for q in card.questions}
        for answer in card.answers:
            if answer.message_digest == digest and answer.answer != "rejected":
                out.append({"card": card.id, "question": answer.question,
                            "text": texts.get(answer.question, ""), "answer": answer.answer})
    return out


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


def _inputs(core: Any, digest: str, text: str, answered: Sequence[Mapping[str, str]],
            frozen: Mapping[str, Any] | None = None) -> dict[str, Any]:
    out = {"message": {"digest": digest, "text": text}, "touched": touched(core, text),
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
    if not text.strip():
        return None
    after = context.get("after")
    frozen = frozen_context(Path(core.root), session, digest, context.get("transcript"), text)
    job = files.make_job(kind, session, SCHEMA_ID, _inputs(core, digest, text, (), frozen),
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
    return _inputs(core, digest, str(logged.get("text") or ""),
                   answered_for(Path(core.root), job.session, digest),
                   frozen_context(Path(core.root), job.session, digest))


# ---------------------------------------------------------------- apply


def _clean(items: Any) -> list[str]:
    if not isinstance(items, (list, tuple)):
        return []
    return [str(i).strip() for i in items if str(i).strip()]


def _gap_question(gap: Mapping[str, Any], n: int) -> ClarifyQuestion:
    suggestions = _clean(gap.get("suggestions"))
    try:
        first = int(gap.get("recommended") or 0)
    except (TypeError, ValueError):
        first = 0
    if 0 < first < len(suggestions):
        suggestions.insert(0, suggestions.pop(first))
    ident = re.sub(r"[^a-z0-9_-]+", "-", str(gap.get("id") or "").lower()).strip("-") or f"q{n}"
    return ClarifyQuestion(id=ident, text=str(gap.get("question") or "").strip(),
                           resolutions=tuple(suggestions),
                           choices=choices_for("clarify", suggestions))


def _already_answered(question: ClarifyQuestion, answered: Sequence[Mapping[str, Any]]) -> bool:
    for item in answered:
        if str(item.get("question")) == question.id:
            return True
        if question.text and str(item.get("text", "")).strip().lower() == question.text.lower():
            return True
    return False


def _evidence(readback: Mapping[str, Any]) -> str:
    lines = [EVIDENCE_WILL.format(text=t) for t in _clean(readback.get("will"))]
    lines += [EVIDENCE_WONT.format(text=t) for t in _clean(readback.get("wont"))]
    lines += [EVIDENCE_ASSUMED.format(text=t) for t in _clean(readback.get("assumptions"))]
    lines += [EVIDENCE_EXAMPLE.format(text=t) for t in _clean(readback.get("examples"))]
    return "\n".join(lines)


def assumptions(card: CardState) -> list[tuple[str, str]]:
    """The labelled assumptions of a clarify card as ``(text, status)``. They are always
    ``proposed``: answering the card confirms the answers to its questions and nothing else."""
    marker = EVIDENCE_ASSUMED.format(text="")
    return [(line[len(marker):].strip(), "proposed")
            for line in card.evidence.splitlines() if line.startswith(marker)]


def confirmed_answers(card: CardState) -> dict[str, str]:
    """The answers the reader mapped to the card's questions (the only thing it confirms)."""
    known = {q.id for q in card.questions}
    return {a.question: a.answer for a in card.answers
            if a.question in known and a.answer != "rejected"}


def is_escalation(card: CardState) -> bool:
    return card.kind == "clarify" and ESCALATION_MARK in card.evidence


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    if core is None:
        return Applied(job=job.id)
    message = job.inputs.get("message")
    digest = str(message.get("digest") if isinstance(message, Mapping) else "")
    session = job.session
    closed = tuple(c.id for c in cardstore.own_cards(Path(core.root), session)
                   if c.id == couldnt_card_id(digest) and c.status == "open")
    if str(answer.get("intent")) != "yes":
        gate.open(core, session, digest, "clarify", "your message carries no new request")
        return Applied(job=job.id, closed=closed)
    answered = [a for a in job.inputs.get("answered") or () if isinstance(a, Mapping)]
    questions = [_gap_question(g, n) for n, g in enumerate(answer.get("gaps") or (), 1)
                 if isinstance(g, Mapping)]
    questions = [q for q in questions if q.text and not _already_answered(q, answered)]
    raw = answer.get("readback")
    readback: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    topic = str(answer.get("topic") or "").strip() or TOPIC_FALLBACK
    if not questions:
        gate.open(core, session, digest, "clarify",
                  "the questions are answered" if answered else "nothing is unclear")
        return Applied(job=job.id, closed=closed)
    evidence = _evidence(readback)
    if len(questions) > MAX_QUESTIONS:
        card = CardState(
            id=card_id(digest), kind="clarify", topic=topic,
            issue=ISSUE_ESCALATION.format(n=len(questions)),
            evidence="\n".join(filter(None, [ESCALATION_MARK, evidence])),
            resolutions=(SPEC_YES, SPEC_NO),
            questions=(ClarifyQuestion(id="spec", text=SPEC_QUESTION,
                                       resolutions=(SPEC_YES, SPEC_NO),
                                       choices=choices_for("clarify", (SPEC_YES, SPEC_NO))),),
            status="open", turn=0)
        reason = GATE_REASON_ESCALATION
    else:
        card = CardState(
            id=card_id(digest), kind="clarify", topic=topic,
            issue=(questions[0].text if len(questions) == 1
                   else ISSUE_QUESTIONS.format(n=len(questions))),
            evidence=evidence, resolutions=questions[0].resolutions,
            questions=tuple(questions), status="open", turn=0)
        reason = GATE_REASON_CARD
    gate.refresh(Path(core.root), session, digest, reason)
    return Applied(job=job.id, cards=(card,), closed=closed)


def describe(job: Job) -> str:
    return owner_text.STEP_CHECKING


# ---------------------------------------------------------------- the failed check


def couldnt_check_card(digest: str, why: str = "") -> CardState:
    """The card shown when the check could not be made: it says nothing was built and asks
    "Build without the check?" with Build anyway and Wait."""
    resolutions = (owner_text.GATE_BUILD_ANYWAY, owner_text.GATE_WAIT)
    return CardState(
        id=couldnt_card_id(digest), kind="couldnt_check", topic=TOPIC_FALLBACK,
        issue=COULDNT_ISSUE.format(why=why or COULDNT_TIMEOUT), resolutions=resolutions,
        questions=(ClarifyQuestion(id="release", text=COULDNT_QUESTION,
                                   resolutions=resolutions,
                                   choices=choices_for("couldnt_check", resolutions)),),
        status="open")


def write_couldnt_check(root: Path, session: str, digest: str, why: str = "") -> CardState:
    """Put the "couldn't check" card of the message in the card store (once) and keep the
    gate closed for it."""
    card = couldnt_check_card(digest, why)
    cards = [c for c in cardstore.own_cards(root, session) if c.id != card.id]
    cardstore.save(root, session, [*cards, card])
    gate.refresh(root, session, digest, GATE_REASON_COULDNT)
    return card


def render(card: CardState) -> list[str]:
    """The card as the owner reads it (the agent shows it in its reply)."""
    head = owner_text.CARD_COULDNT_CHECK if card.kind == "couldnt_check" \
        else owner_text.CARD_CLARIFY
    lines = [head.format(topic=card.topic, issue=card.issue)]
    if card.evidence and card.kind == "clarify":
        lines.extend(line for line in card.evidence.splitlines() if line != ESCALATION_MARK)
    for question in card.questions:
        lines.append(question.text)
        lines.extend(owner_text.CARD_RESOLUTION.format(n=n, text=text)
                     for n, text in enumerate(question.resolutions, 1))
    return lines


# ---------------------------------------------------------------- the card effects


def _clarify_pending(root: Path, session: str, digest: str) -> bool:
    """A clarify job for this message with no result yet: it opens the gate itself."""
    for path in files.jobs_dir(root, session).glob("clarify-*.json"):
        raw = files.read_json(path)
        message = (raw.get("inputs") or {}).get("message") if isinstance(raw, Mapping) else None
        if isinstance(message, Mapping) and message.get("digest") == digest \
                and not (files.results_dir(root, session) / path.name).exists():
            return True
    return False


def _clarify_effect(*, core: Any, card: CardState, job: Any = None, digest: str = "",
                    **_: Any) -> Applied | None:
    """A clarify card answered: when every question is mapped the gate opens, unless this
    message's own clarify job is still to run (it opens the gate, or asks what is new)."""
    done = bool(card.questions) and all(
        any(a.question == q.id and a.answer != "rejected" for a in card.answers)
        for q in card.questions)
    session = str(getattr(job, "session", "") or "")
    if done and session and not _clarify_pending(Path(core.root), session, digest):
        gate.open(core, session, digest, "clarify", "every question of the card is answered")
    return None


def _couldnt_check_effect(*, core: Any, card: CardState, job: Any = None, digest: str = "",
                          accepted: bool = False, **_: Any) -> Applied | None:
    """The "Build without the check?" card: only an accepted answer at or above the reader's
    threshold (``accepted``) opens the gate; "wait" keeps it closed."""
    session = str(getattr(job, "session", "") or "")
    if accepted and session:
        gate.release(core, session, "owner-words", digest=digest)
    return None


def _register() -> None:
    from plumb.understand import effects

    effects.register("clarify", _clarify_effect)
    effects.register("couldnt_check", _couldnt_check_effect)


_register()


# ---------------------------------------------------------------- the prompt hook's side


def is_typed_go(text: str) -> bool:
    return bool(GO_TEXT.match(text.strip()))


def on_prompt(ctx: Any, core: Any, entry: Any, *, after: str | None = None) -> list[str]:
    """Close the gate for this message and queue its clarify job (idempotent, no wait). The
    typed ``/plumb go`` releases a failed check instead and carries no request of its own.
    Returns the agent-facing lines."""
    session = str(getattr(ctx, "session_id", "") or "")
    digest = str(entry.get("digest") if isinstance(entry, Mapping) else "")
    text = str(entry.get("text") if isinstance(entry, Mapping) else "")
    if not session or not digest:
        return []
    if is_typed_go(text):
        if gate.release(core, session, "typed", digest=digest):
            return [GATE_RELEASED]
        return []
    gate.close(Path(core.root), session, digest, GATE_REASON_CHECKING)
    data = getattr(ctx, "data", None)
    transcript = data.get("transcript_path") if isinstance(data, Mapping) else None
    build(core, session, message={"digest": digest, "text": text}, after=after,
          transcript=transcript)
    return [owner_text.GATE_CLOSED.format(reason=GATE_REASON_CHECKING)]
