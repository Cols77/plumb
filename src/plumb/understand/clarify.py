"""The clarify job kind (SHOW, spec 4.3): is the owner's request clear and complete?

``build`` queues one job per owner message (its ``needs`` is the message's read job, so a card
the owner has just answered is applied first); its inputs carry the conversation before the
message and the repository facts (SR-128), frozen when the prompt arrives; ``recompute``
rebuilds the inputs from the logs, the card store and that frozen context; ``apply`` turns
the model's answer into the read-back card of the request (a proposal, the assumptions and the
one thing not done; the owner's one "yes" confirms the request's records), at most one choice
card for the one gap that blocks (or an offer of a short spec session when more than one
question changes what gets built), or nothing (no intent). Only the choice card keeps the gate
closed. ``on_prompt`` is the prompt hook's side: it closes the gate and queues the job, and never
waits."""

from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, CardState, Choice, ClarifyQuestion, Job
from plumb.present import owner_text
from plumb.understand import cardstore, files, gate
from plumb.understand.typed import PREFIX

kind = "clarify"
SCHEMA_ID = "clarify.v1"
HERE = Path(__file__).resolve().parent
MAX_QUESTIONS = 1
GO_TEXT = re.compile(r"^" + PREFIX + r"[ \t]+go$")   # SR-120: /plumb go or /plumb:plumb go

TOPIC_FALLBACK = "your request"
ISSUE_QUESTIONS = "{n} things would change what I build, and I need your answer before I start"
ISSUE_ESCALATION = ("{n} things would change what I build; going through them together in a "
                    "short spec session beats {n} separate questions")
EVIDENCE_GAPS = "The {n} things: {text}"
SPEC_YES_NOTE = "Nothing is built until we have been through them together"
SPEC_NO_NOTE = "Builds now on the guesses listed on your request; you can correct them there"
WAITS_ON = "Nothing is built until you answer the question below."
CHOICE_TOPIC = 'One question about your request of {date}: "{text}"'
SPEC_QUESTION = "Shall we go through them in a short spec session first?"
SPEC_YES = "Yes, a short spec session"
SPEC_NO = "No, build with my best guesses"
COULDNT_ISSUE = "I could not check whether your request is clear: {why}. Nothing was built."
COULDNT_TIMEOUT = "the check was still running"
COULDNT_QUESTION = "Build without the check?"
EVIDENCE_WONT = "Not doing: {text}"
EVIDENCE_ASSUMED = "Assumed: {text}"
EVIDENCE_CHANGES = "What changes: {text}"
TOPIC = 'Your request of {date}: "{text}"'
READBACK_ID = "ok"
READBACK_QUESTION = "Is this what you want?"
READBACK_YES = "Yes, that is what I meant"
READBACK_YES_NOTE = ("Confirms this request and everything recorded from it (the brief lists it); "
                     "it does not hold the work back")
READBACK_NO = "Not quite"
READBACK_NO_NOTE = "Say what to change; nothing is confirmed."
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


def choice_id(digest: str) -> str:
    return f"choice:{short(digest)}"


def couldnt_card_id(digest: str) -> str:
    return f"couldnt_check:{short(digest)}"


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


def answered_for(root: Path, session: str, digest: str) -> list[dict[str, str]]:
    """The questions of clarify cards this message answered (what the reader just mapped), as
    ``{card, question, text, answer}``; a question answered "rejected" is not an answer."""
    out: list[dict[str, str]] = []
    for card in cardstore.own_cards(root, session):
        if card.kind not in ("clarify", "choice"):
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


def _inputs(core: Any, session: str, digest: str, text: str,
            answered: Sequence[Mapping[str, str]], frozen: Mapping[str, Any] | None = None
            ) -> dict[str, Any]:
    out = {"message": {"digest": digest, "text": text}, "touched": touched(core, text),
           "answered": [dict(a) for a in answered]}
    open_cards = [{"id": c.id, "topic": c.topic, "question": c.issue}
                  for c in cardstore.own_cards(Path(core.root), session)
                  if c.kind in ("clarify", "choice") and c.status in cardstore.AWAITING
                  and short(digest) not in c.id]
    if open_cards:
        out["open_cards"] = open_cards
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
    return _inputs(core, job.session, digest, str(logged.get("text") or ""),
                   answered_for(Path(core.root), job.session, digest),
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
        choices=tuple(Choice(t, "change", t, c) for t, c in zip(suggestions, lines)))


def _already_answered(question: ClarifyQuestion, answered: Sequence[Mapping[str, Any]]) -> bool:
    for item in answered:
        if str(item.get("question")) == question.id:
            return True
        if question.text and str(item.get("text", "")).strip().lower() == question.text.lower():
            return True
    return False


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
    return card.kind == "choice" and ESCALATION_MARK in card.evidence


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


def _readback_card(root: Path, digest: str, text: str, readback: Mapping[str, Any],
                   lines: Sequence[str]) -> CardState:
    clipped = _clipped(text)
    will = _clean(readback.get("will"))
    wont = _clean(readback.get("wont"))[:1]
    proposal = str(readback.get("proposal") or "").strip() or (will[0] if will else clipped)
    evidence = [*lines, *(EVIDENCE_WONT.format(text=t) for t in wont)]
    resolutions = (READBACK_YES, READBACK_NO)
    return CardState(
        id=card_id(digest), kind="clarify", topic=TOPIC.format(date=_now()[:10], text=clipped),
        issue=proposal, evidence="\n".join(evidence), resolutions=resolutions,
        questions=(ClarifyQuestion(id=READBACK_ID, text=READBACK_QUESTION,
                                   resolutions=resolutions, choices=(
                                       Choice(READBACK_YES, "accepted",
                                              consequence=READBACK_YES_NOTE),
                                       Choice(READBACK_NO, "change",
                                              consequence=READBACK_NO_NOTE))),),
        status="open", turn=0, branch=repository(root)["branch"])


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    if core is None:
        return Applied(job=job.id)
    root = Path(core.root)
    message = job.inputs.get("message")
    digest = str(message.get("digest") if isinstance(message, Mapping) else "")
    text = str(message.get("text") if isinstance(message, Mapping) else "")
    session = job.session
    own = cardstore.own_cards(root, session)
    closed = tuple(c.id for c in own if c.id == couldnt_card_id(digest) and c.status == "open")
    # the reader marks the card left_open before this job applies (SR-131 EX-4)
    waiting = {c.id for c in own if c.kind == "choice"
               and c.status in (*cardstore.AWAITING, "left_open")}
    if any(e.kind == "read-entry" and e.payload.get("message_digest") == digest
           and e.payload.get("answer") == "open"
           and str(e.payload.get("id")).split("/", 1)[0] in waiting for e in core.events()):
        gate.refresh(root, session, digest, GATE_REASON_CARD)    # SR-131 EX-4: a vague answer
        return Applied(job=job.id, closed=closed)               # picks nothing; the card stays
    if str(answer.get("intent")) != "yes":
        gate.open(core, session, digest, "clarify", "your message carries no new request")
        return Applied(job=job.id, closed=closed)
    answered = [a for a in job.inputs.get("answered") or () if isinstance(a, Mapping)]
    gaps = [(g, _gap_question(g, n)) for n, g in enumerate(answer.get("gaps") or (), 1)
            if isinstance(g, Mapping)]
    gaps = [(g, q) for g, q in gaps if q.text and not _already_answered(q, answered)]
    raw = answer.get("readback")
    readback: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    # SR-131: only a gap with no better-supported answer is asked, and one at most; two or
    # more are a spec session offered; a gap that is not blocking is assumed
    open_gaps = [(g, q) for g, q in gaps if g.get("blocking")]
    escalate = len(open_gaps) > MAX_QUESTIONS
    blocking = [] if escalate else open_gaps[:1]
    # a gap not asked (not blocking, past the first, or all of them when a spec session is
    # offered) is a guess on the read-back, so the owner can still flip it
    asked = {id(g) for g, _ in blocking}
    lines = [EVIDENCE_ASSUMED.format(text=t) for t in _clean(readback.get("assumptions"))]
    lines += [EVIDENCE_ASSUMED.format(text=f"{q.text}: {q.resolutions[0]}")
              for g, q in gaps if id(g) not in asked and (escalate or not g.get("blocking"))
              and q.resolutions and not (escalate and g.get("blocking"))]
    if escalate or blocking:
        lines.insert(0, WAITS_ON)
    cards = [_readback_card(root, digest, text, readback, lines)]
    topic = CHOICE_TOPIC.format(date=_now()[:10], text=_clipped(text))
    if escalate:
        cards.append(CardState(
            id=choice_id(digest), kind="choice", topic=topic,
            issue=ISSUE_ESCALATION.format(n=len(open_gaps)),
            evidence="\n".join([ESCALATION_MARK, EVIDENCE_GAPS.format(
                n=len(open_gaps), text="; ".join(q.text for _, q in open_gaps)),
                *(EVIDENCE_ASSUMED.format(text=f"{q.text}: {q.resolutions[0]}")
                  for _, q in open_gaps if q.resolutions)]),
            resolutions=(SPEC_YES, SPEC_NO),
            questions=(ClarifyQuestion(id="spec", text=SPEC_QUESTION,
                                       resolutions=(SPEC_YES, SPEC_NO),
                                       choices=(Choice(SPEC_YES, "change", SPEC_YES, SPEC_YES_NOTE),
                                                Choice(SPEC_NO, "accepted", consequence=SPEC_NO_NOTE))),),
            status="open", turn=0, branch=cards[0].branch))
    elif blocking:
        gap, question = blocking[0]
        changes = "; ".join(c.consequence for c in question.choices if c.consequence)
        cards.append(CardState(
            id=choice_id(digest), kind="choice", topic=topic, issue=question.text,
            evidence=EVIDENCE_CHANGES.format(text=changes) if changes else "",
            resolutions=question.resolutions, questions=(question,), status="open", turn=0,
            branch=cards[0].branch,
            diagram=(f".plumb/session/{session}/diagrams/{short(digest)}.html"
                     if gap.get("diagram") else "")))
    mine = {c.id for c in cards}
    moot = [i for i in _clean(answer.get("replaces")) if i not in mine
            and any(c.id == i and c.status in cardstore.AWAITING for c in own)]
    if moot:
        cardstore.withdraw(root, session, moot)
    if len(cards) > 1:
        gate.refresh(root, session, digest,
                     GATE_REASON_ESCALATION if escalate else GATE_REASON_CARD)
    else:
        gate.open(core, session, digest, "clarify",
                  "the questions are answered" if answered else "nothing is unclear")
    return Applied(job=job.id, cards=tuple(cards), closed=closed)


def describe(job: Job) -> str:
    return owner_text.STEP_CHECKING


# ---------------------------------------------------------------- the failed check


def couldnt_check_card(digest: str, why: str = "", topic: str = "") -> CardState:
    """The card shown when the check could not be made: it says nothing was built and asks
    "Build without the check?" with Build anyway and Wait."""
    resolutions = (owner_text.GATE_WAIT, owner_text.GATE_BUILD_ANYWAY)   # waiting is the safe one
    return CardState(
        id=couldnt_card_id(digest), kind="couldnt_check", topic=topic or TOPIC_FALLBACK,
        issue=COULDNT_ISSUE.format(why=why or COULDNT_TIMEOUT), resolutions=resolutions,
        questions=(ClarifyQuestion(id="release", text=COULDNT_QUESTION,
                                   resolutions=resolutions,
                                   choices=(
                                       Choice(owner_text.GATE_WAIT, "rejected",
                                              consequence=owner_text.GATE_WAIT_NOTE),
                                       Choice(owner_text.GATE_BUILD_ANYWAY, "accepted",
                                              consequence=owner_text.GATE_BUILD_NOTE))),),
        status="open")


def write_couldnt_check(root: Path, session: str, digest: str, why: str = "",
                        text: str = "") -> CardState:
    """Put the "couldn't check" card of the message in the card store (once) and keep the
    gate closed for it."""
    card = couldnt_check_card(digest, why, TOPIC.format(date=_now()[:10], text=_clipped(text))
                              if text.strip() else "")
    cards = [c for c in cardstore.own_cards(root, session) if c.id != card.id]
    cardstore.save(root, session, [*cards, card])
    gate.refresh(root, session, digest, GATE_REASON_COULDNT)
    return card


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


def _shown_records(core: Any, session: str, card: str, source: Any) -> dict[tuple[str, str], str] | None:
    """The ``(id, hash)`` pairs the read-back was drawn with, each with the proposal shown: those
    of the offer pressed, or of the card's latest drawing; None when typed words answer a card
    never drawn in the panel."""
    from plumb.mod.offers import load_offer, offers_dir

    offer = getattr(source, "offer_id", "")
    if offer:
        held = [load_offer(core.root, session, offer)]
    else:
        held = [files.read_json(p) for p in offers_dir(Path(core.root), session).glob("*.json")]
        held = sorted((h for h in held if isinstance(h, Mapping) and h.get("card") == card),
                      key=lambda h: str(h.get("drawn_at")))[-1:]
    if not any(held):
        return None if not offer else {}
    return {(str(r.get("id")), str(r.get("hash"))): str(r.get("proposal") or "")
            for h in held if h for r in h.get("records") or () if isinstance(r, Mapping)}


def _clarify_effect(*, core: Any, card: CardState, accepted: bool = False,
                    confirm: Any = None, entry: Mapping[str, Any] | None = None,
                    session: str = "", source: Any = None, **_: Any) -> Applied | None:
    """The read-back answered yes: that one answer confirms the records it was drawn with, at
    the versions drawn (SR-130); a record changed or added since is left unconfirmed and
    asked again on a choice showing what was answered next to how it reads now."""
    from plumb.understand import cards, trial

    digest = card.id.removeprefix("clarify:")
    if not (accepted and confirm is not None and card.id != digest and digest):
        return None
    said = entry or {}
    shown = _shown_records(core, session, card.id, source)
    again: list[CardState] = []
    for record in request_records(core, digest):
        if shown is None or (record.id, record.hash) in shown:
            confirm(record.id, record.hash, str(said.get("evidence") or ""),
                    float(said.get("confidence") or 1.0))
        else:
            old = next((p for (i, _h), p in shown.items() if i == record.id), "")
            again.append(cards.which_version(record, old or record.title,
                                             trial._proposal(record), card.branch,
                                             card.topic))
    return Applied(job="", cards=tuple(again)) if again else None


def _choice_effect(*, core: Any, card: CardState, job: Any = None, digest: str = "",
                   **_: Any) -> Applied | None:
    """The choice answered: the gate opens, unless this message's own clarify job is still to
    run (it opens the gate, or asks what is new)."""
    # the spec session offer opens the gate only on "build with my best guesses"
    opens = (lambda a: a == "accepted") if is_escalation(card) else (lambda a: a != "rejected")
    guessed = bool(card.answers) and is_escalation(card) and opens(card.answers[-1].answer)
    done = bool(card.questions) and all(
        any(a.question == q.id and opens(a.answer) for a in card.answers)
        for q in card.questions)
    session = str(getattr(job, "session", "") or "")
    if done and session and not _clarify_pending(Path(core.root), session, digest):
        gate.open(core, session, digest, "clarify", "every question of the card is answered")
    if not (guessed and session):
        return None
    # "build with my best guesses": the request lists them, as the answer promised
    guesses = [l for l in card.evidence.splitlines() if l.startswith(EVIDENCE_ASSUMED.format(text=""))]
    want = card_id(digest or card.id.removeprefix("choice:"))
    return Applied(job="", cards=tuple(
        replace(c, evidence="\n".join([*c.evidence.splitlines(), *guesses]))
        for c in cardstore.own_cards(Path(core.root), session) if c.id == want))


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
    effects.register("choice", _choice_effect)
    effects.register("couldnt_check", _couldnt_check_effect)


_register()


# ---------------------------------------------------------------- the prompt hook's side


def is_typed_go(text: str) -> bool:
    return bool(GO_TEXT.match(text.strip()))


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
    gate.close(Path(core.root), session, digest, GATE_REASON_CHECKING)
    data = getattr(ctx, "data", None)
    transcript = data.get("transcript_path") if isinstance(data, Mapping) else None
    build(core, session, message={"digest": digest, "text": text}, after=after,
          transcript=transcript)
    return [owner_text.GATE_CLOSED.format(reason=GATE_REASON_CHECKING)]
