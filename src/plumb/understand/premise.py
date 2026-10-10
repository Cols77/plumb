"""Premises (JUDGE, SR-102): the owner's words a record rests on.

``premise_of(core, record)`` gives what the judge is shown: the owner's whole logged message
or messages the record derives from, the stored question when the answer was short, and the
parent intent. It reads the committed log first (``premise`` entries: text and digest,
written by ``commit`` when a record first takes a message as its premise), then the session's
prompt log, so a record keeps its premise after the session log is gone. A record whose
premise is only a fragment of the owner's words (older records) says so: ``fragment`` holds the
fragment and ``messages`` is empty.

``problems(core)`` is what ``plumb validate`` reports: a premise whose digest is not the
digest of its text, and a settled record whose premise is not on file."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PREFIX_MIN = 12


@dataclass(frozen=True)
class Premise:
    """What a record rests on. ``messages``: ``({"digest", "text"}, ...)`` (the owner's whole
    logged messages); ``question``: the stored question a short answer answered; ``parent``:
    the confirmed or settled parent intent, if any; ``fragment``: the owner's words as the
    record quotes them when no whole message is on file."""

    messages: tuple[Mapping[str, str], ...] = ()
    question: str = ""
    parent: str | None = None
    fragment: str = ""

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
        return {"messages": messages, "question": self.question, "parent": self.parent}


def _sha(text: str) -> str:
    from plumb.normalize import sha256_text

    return sha256_text(text)


def input_digest(premise: Mapping[str, Any]) -> str:
    """The digest a verdict and a settled approval carry for a job's ``premise`` object: the
    message's own digest when there is one message, else the digest of the sorted message
    digests; nothing on file is ''."""
    digests = sorted(str(m.get("digest")) for m in premise.get("messages") or ()
                     if isinstance(m, Mapping) and m.get("digest"))
    if len(digests) == 1:
        return digests[0]
    if digests:
        from plumb.understand import files

        return files.digest_of(digests)
    return ""


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
    """The whole message a digest (or a prefix of it, 12+ hex digits) names: the committed
    log first, then the session's prompt log. None when neither has it."""
    wanted = _prefix(prefix)
    if len(wanted) < PREFIX_MIN:
        return None
    held = committed(core) if known is None else known
    for digest, item in held.items():
        if _prefix(digest).startswith(wanted):
            return {"digest": digest, "text": str(item["text"])}
    from plumb.approvals import Refused, find_prompt

    try:
        found = find_prompt(core, wanted)
    except Refused:
        return None
    return {"digest": str(found["digest"]), "text": str(found["text"])}


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
                   fragment=fragment)


# --------------------------------------------------------------------------- committing


def commit(core: Any, doc: Any, result: Any, *, prompt_digest: str | None = None) -> None:
    """Write the message ``prompt_digest`` names to the committed log (text and digest) when
    the records ``result`` wrote or changed first take it as their premise; one entry per
    capture, naming them in ``used_by``. Nothing is written when there is no message, or when
    the committed log already holds it for all of them."""
    if core is None or result is None or not prompt_digest:
        return None
    ids = [str(i) for i in (*getattr(result, "written", ()), *getattr(result, "updated", ()))]
    if not ids:
        return None
    from plumb.approvals import Refused, find_prompt

    try:
        found = find_prompt(core, prompt_digest)
    except Refused:
        return None
    digest, text = str(found["digest"]), str(found["text"])
    held = committed(core).get(digest)
    fresh = [i for i in ids if held is None or i not in held["used_by"]]
    if not fresh:
        return None
    core.log_append("events", "premise", {"digest": digest, "text": text,
                                          "session": found.get("session"),
                                          "used_by": fresh})
    return None


def _digest_matches(digest: str, text: str) -> bool:
    from plumb.approvals import prompt_digest

    return digest in (prompt_digest(text), _sha(text))


def problems(core: Any) -> list[str]:
    """What ``plumb validate`` reports about premises: a digest that is not the digest of its
    text, and a settled record whose premise is not in the committed log."""
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
    for entry in core.events():
        if entry.kind != "approval" or entry.payload.get("by") != "settled":
            continue
        wanted = entry.payload.get("premise_digests") or [entry.payload.get("premise_digest")]
        for digest in wanted:
            if digest and digest not in held:
                ids = ", ".join(str(r.get("id")) for r in entry.payload.get("records") or ()
                                if isinstance(r, Mapping))
                out.append(f"{ids} rests on a premise ({str(digest)[:19]}) that is not in "
                           "the committed log")
    return out


def used_by(core: Any, digest: str) -> Sequence[str]:
    item = committed(core).get(digest)
    return tuple(item["used_by"]) if item else ()


def digests(items: Iterable[Mapping[str, str]]) -> list[str]:
    return sorted(m["digest"] for m in items)
