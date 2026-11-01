"""Premises (JUDGE, SR-102): the owner's words a record rests on.

``premise_of(core, record)`` gives what the judge is shown: the owner's whole logged message
or messages the record derives from, the stored question when the answer was short, and the
parent intent, and the owner's question-tool answers about the record, at whichever version
they were asked (``answers``, SR-212). It reads the session prompt log first (the main
checkout's too, through git's common directory); the owner's messages are not copied into the
tracked log (DEC-116). A record is judged once, where the words are (the machine that captured
it); another checkout without that log never judges it again for want of them (SR-239 EX-10),
and nothing marks the words as missing. ``premise`` entries committed before DEC-116 still
serve as a fallback. A record whose
premise is only a fragment of the owner's words (older records) says so: ``fragment`` holds the
fragment and ``messages`` is empty.

``problems(core)`` is what ``plumb validate`` reports: a premise whose digest is not the
digest of its text."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PREFIX_MIN = 12


@dataclass(frozen=True)
class Premise:
    """What a record rests on. ``messages``: ``({"digest", "text"}, ...)`` (the owner's whole
    logged messages); ``question``: the stored question a short answer answered; ``parent``:
    the confirmed parent intent, if any; ``fragment``: the owner's words as the
    record quotes them when no whole message is on file; ``answers``: ``({"digest",
    "question", "options", "answer"}, ...)``, the owner's question-tool answers (``digest``:
    their log entry) that name the record."""

    messages: tuple[Mapping[str, str], ...] = ()
    question: str = ""
    parent: str | None = None
    fragment: str = ""
    answers: tuple[Mapping[str, Any], ...] = ()

    @property
    def on_file(self) -> bool:
        return bool(self.messages)

    @property
    def digest(self) -> str:
        return digest_of(self)

    def as_input(self) -> dict[str, Any]:
        """The ``premise`` object of a judge job's record entry."""
        messages = [dict(m) for m in self.messages]
        if not messages and self.fragment:
            messages = [{"digest": _sha(self.fragment), "text": self.fragment,
                         "partial": True}]
        given = {"messages": messages, "question": self.question, "parent": self.parent}
        if self.answers:                # absent when none: older inputs keep their digest
            given["answers"] = [dict(a) for a in self.answers]
        return given


def _sha(text: str) -> str:
    from plumb.normalize import sha256_text

    return sha256_text(text)


def input_digest(premise: Mapping[str, Any]) -> str:
    """The digest a verdict and an approval carry for a job's ``premise`` object: the
    message's own digest when there is one message, else the digest of the sorted message
    digests; nothing on file is ''. The owner's answers count only when there are some, so a
    premise without them keeps its digest."""
    from plumb.understand import files

    digests = sorted(str(m.get("digest")) for m in premise.get("messages") or ()
                     if isinstance(m, Mapping) and m.get("digest"))
    base = digests[0] if len(digests) == 1 else files.digest_of(digests) if digests else ""
    answers = premise.get("answers") or []
    return files.digest_of([base, answers]) if answers else base


def digest_of(premise: Premise) -> str:
    return input_digest(premise.as_input())


def digests_of(premise: Premise) -> list[str]:
    return sorted(m["digest"] for m in premise.messages)


# --------------------------------------------------------------------------- the logs


def _prefix(digest: Any) -> str:
    return str(digest or "").strip().lower().removeprefix("sha256:")


def committed(core: Any) -> dict[str, dict[str, Any]]:
    """Digest -> ``{"text", "session", "used_by"}`` of the ``premise`` entries of the committed
    log (``used_by`` merged over the entries of one digest)."""
    out: dict[str, dict[str, Any]] = {}
    for entry in core.events():
        if entry.kind != "premise":
            continue
        digest, text = entry.payload.get("digest"), entry.payload.get("text")
        if not isinstance(digest, str) or not isinstance(text, str):
            continue
        held = out.setdefault(digest, {"text": text, "session": entry.payload.get("session"),
                                       "used_by": []})
        for who in entry.payload.get("used_by") or ():
            if str(who) not in held["used_by"]:
                held["used_by"].append(str(who))
    return out


def message_for(core: Any, prefix: Any, known: Mapping[str, Mapping[str, Any]] | None = None
                ) -> Mapping[str, str] | None:
    """The whole message a digest (or a prefix of it, 12+ hex digits) names: the
    session's prompt log first, then the ``premise`` entries committed before DEC-116. None when
    neither has it."""
    wanted = _prefix(prefix)
    if len(wanted) < PREFIX_MIN:
        return None
    from plumb.approvals import Refused, find_prompt

    try:
        found = find_prompt(core, wanted)
        return {"digest": str(found["digest"]), "text": str(found["text"])}
    except Refused:
        pass
    held = committed(core) if known is None else known
    for digest, item in held.items():
        if _prefix(digest).startswith(wanted):
            return {"digest": digest, "text": str(item["text"])}
    return None


def _prompt_prefixes(record: Any) -> list[str]:
    out: list[str] = []
    if record.fields.get("prompt"):
        out.append(str(record.fields["prompt"]))
    for example in record.fields.get("examples") or ():
        if isinstance(example, Mapping) and example.get("prompt"):
            out.append(str(example["prompt"]))
    return out


def _parents(index: Mapping[str, Any], record: Any) -> list[Any]:
    return [index[link.target.record] for link in record.links
            if link.kind == "derives_from" and link.target.record in index
            and index[link.target.record].kind == "intent"]


def _quote(record: Any) -> str:
    quote = record.fields.get("quote")
    if isinstance(quote, (list, tuple)):
        return " ".join(" ".join(str(q).split()) for q in quote)
    return " ".join(str(quote or "").split())


ANSWER_VIA = {"question-answer": "question-tool", "pre-intent": "read"}


def answer_entries(core: Any, record: Any) -> list[Any]:
    """The owner's answers whose ``asked`` names ``record`` at its current version or at an
    earlier one never confirmed (SR-212 EX-6, SR-209 EX-4: the agent rewords the record to
    agree with the answer, and the reworded record goes back to the judge with that answer;
    SR-248 EX-9: an edit of a record confirmed on that answer is asked about again):
    question-tool answers, and the worker's ``pre-intent`` of a message answering what the
    last reply showed (``via: read``, SR-209 EX-2). Entries without that ``via`` or ``asked``
    (older ones) never count."""
    out: list[Any] = []
    events = core.events()
    confirmed = {str(r.get("hash")) for e in events if e.kind == "approval"   # the record's
                 for r in e.payload.get("records") or ()               # approved hashes
                 if isinstance(r, Mapping) and r.get("id") == record.id}
    bound = {str(e.payload.get("answer")): e.payload.get("asked") for e in events
             if e.kind == "answer-bound"}   # SR-362: an answer asked before its rewording
    for entry in events:
        p = entry.payload
        asked = p.get("asked") or bound.get(entry.digest)
        if entry.kind not in ANSWER_VIA or ANSWER_VIA[entry.kind] != p.get("via") \
                or not isinstance(asked, Mapping):
            continue
        if any(isinstance(r, Mapping) and r.get("id") == record.id
               and carries(str(r.get("hash")), record.hash, confirmed)
               for r in asked.get("records") or ()):
            out.append(entry)
    return out


def carries(asked: str, current: str, confirmed: Collection[str]) -> bool:
    """Whether an answer asked about a record at hash ``asked`` counts for it at ``current``:
    the same version, or an earlier one never confirmed (the answer is still the open
    conversation about the record)."""
    return asked == current or asked not in confirmed


def answers_of(core: Any, record: Any) -> tuple[dict[str, Any], ...]:
    """The owner's question-tool answers about ``record`` at its current hash
    (``answer_entries``), as the judge is shown them."""
    return tuple({"digest": e.digest, "question": str(e.payload.get("question") or ""),
                  "options": list(e.payload.get("options") or ()),
                  "answer": str(e.payload.get("answer") or e.payload.get("text") or "")}
                 for e in answer_entries(core, record))


def owner_words(core: Any) -> list[tuple[str, str]]:
    """SR-335: ``(text, at)`` of the owner's own logged words: their question-tool answers
    and the prompts they typed."""
    from plumb.understand import read

    said = [(str(e.payload.get("answer") or ""), e.at) for e in core.events()
            if e.kind == "question-answer" and e.payload.get("via") == "question-tool"]
    return said + [(str(p.get("text") or ""), str(p.get("at") or ""))
                   for p in read._prompt_entries(core)]


def owner_quoted(record: Any, said: Sequence[tuple[str, str]]) -> bool:
    """SR-335 EX-1, EX-3: a decision the owner's words settle before it is approved: its
    ``quote`` (else what it chose) is verbatim in words of theirs (``owner_words``). One only
    the agent wrote, or one that misquotes them, is not."""
    from plumb.understand import recover

    quoted = recover.quote_parts(record) or [str(record.fields.get("chosen") or "")]
    return record.kind == "decision" and all(
        any(recover.holds(text, q) for text, _ in said) for q in quoted)


def premise_of(core: Any, record: Any, *, statuses: Mapping[str, Any] | None = None,
               known: Mapping[str, Mapping[str, Any]] | None = None) -> Premise:
    """The premise of ``record`` (see the module docstring)."""
    index = core.index()
    sources = [record] if record.kind == "intent" else _parents(index, record)
    prefixes: list[str] = []
    for source in sources:
        prefixes += _prompt_prefixes(source)
    if record.kind != "intent":
        prefixes += _prompt_prefixes(record)
    held = committed(core) if known is None else known
    messages: list[Mapping[str, str]] = []
    for prefix in prefixes:
        message = message_for(core, prefix, held)
        if message is not None and all(message["digest"] != m["digest"] for m in messages):
            messages.append(message)
    question = " ".join(" ".join(str(s.fields.get("question") or "").split())
                        for s in sources).strip()
    parent = None
    if record.kind != "intent":
        states = statuses if statuses is not None else core.status(
            [p.id for p in sources])
        for source in sources:
            state = states.get(source.id)
            if state is not None and state.confirmation == "confirmed":
                parent = source.id
                break
    fragment = ""
    if not messages:
        fragment = " ".join(q for q in (_quote(s) for s in sources) if q)
    return Premise(messages=tuple(messages), question=question, parent=parent,
                   fragment=fragment, answers=answers_of(core, record))


def _digest_matches(digest: str, text: str) -> bool:
    from plumb.approvals import prompt_digest

    return digest in (prompt_digest(text), _sha(text))


def problems(core: Any) -> list[str]:
    """What ``plumb validate`` reports about the ``premise`` entries committed before DEC-116:
    a digest that is not the digest of its text. None are written any more."""
    if core is None:
        return []
    out: list[str] = []
    held: dict[str, str] = {}
    for entry in core.events():
        if entry.kind != "premise":
            continue
        digest, text = entry.payload.get("digest"), entry.payload.get("text")
        if not isinstance(digest, str) or not isinstance(text, str):
            out.append(f"premise entry {entry.name or entry.digest[:19]} lacks its digest "
                       "or its text")
            continue
        if not _digest_matches(digest, text):
            out.append(f"premise {digest[:19]}: the digest is not the digest of its text")
            continue
        held[digest] = text
    return out


def used_by(core: Any, digest: str) -> Sequence[str]:
    item = committed(core).get(digest)
    return tuple(item["used_by"]) if item else ()


def digests(items: Iterable[Mapping[str, str]]) -> list[str]:
    return sorted(m["digest"] for m in items)
