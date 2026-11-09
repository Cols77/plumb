"""The owner's words a record is judged against: the claim of a record, the logged prompts
its quotes must be verbatim in, and why a premise is not the owner's verified words (R8 A,
SR-040, SR-380: the triage command and view are gone; the judge, the auto-approval and the
quote recovery use these)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from iaso.capture.records import is_short_answer
from iaso.contracts import Record

if TYPE_CHECKING:
    from iaso.api import Core


def _flat(value: Any) -> str:
    return " ".join(str(value or "").split())


def _items(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    out = []
    for item in raw:
        text = item.get("text") if isinstance(item, Mapping) else item
        if _flat(text):
            out.append(_flat(text))
    return out


def _intent_premise(prompts: _Prompts | None, record: Record) -> str:
    """The owner's words an intent is judged against (SR-040): the whole logged prompt that
    holds the quote when the prompt log has it, else the quote; a short answer is kept with
    the question it answered (SR-097)."""
    quote = _flat(record.fields.get("quote"))
    if not quote:
        return ""
    premise = quote
    if prompts is not None:
        text = _verified_intent(prompts, record)
        if text is not None and text.strip():
            premise = text.strip()
    question = _flat(record.fields.get("question"))
    if question and is_short_answer(quote):
        premise = f"{question}\n{premise}"
    return premise


def _intent_premises(index: Mapping[str, Record], record: Record,
                     prompts: _Prompts | None) -> list[str]:
    out = []
    for link in record.links:
        if link.kind == "derives_from" and link.target.record in index:
            parent = index[link.target.record]
            if parent.kind == "intent":
                text = _intent_premise(prompts, parent)
                if text and text not in out:
                    out.append(text)
    return out


def claim(index: Mapping[str, Record], record: Record,
          prompts: _Prompts | None = None) -> tuple[str, str, str]:
    """``(claim kind, premise, hypothesis)`` of a record (sp2 8.1 step 2).

    An intent is judged on what its read-back asserts as the owner's: the read-back, will
    and won't lines. Its labelled assumptions are the agent's own, shown to the owner and
    never claimed as the owner's words, so they stay out. The premise is the owner's words in
    full (``_intent_premise``); a requirement's is its parent intents' premise."""
    fields = record.fields
    if record.kind == "intent":
        lines = [_flat(fields.get("readback") or record.title)]
        lines += [f"will: {w}" for w in _items(fields.get("will"))]
        lines += [f"won't: {w}" for w in _items(fields.get("wont"))]
        return "intent-readback", _intent_premise(prompts, record), "\n".join(lines)
    if record.kind == "requirement":
        premise = _intent_premises(index, record, prompts)
        held = "\n".join(premise)
        raw = fields.get("examples") or []
        premise += [q for q in (_flat(e.get("quote")) for e in raw
                                if isinstance(e, Mapping)) if q and q not in held]
        lines = [_flat(fields.get("statement") or record.title)]
        lines += [f"given {e.given}, when {e.when}, then {e.then}" for e in record.examples]
        return "example-restatement", "\n".join(premise), "\n".join(lines)
    if record.kind == "decision":
        premise = [_flat(fields.get("question"))] + [
            _flat(parent.fields.get("quote")) for parent in
            (index[link.target.record] for link in record.links
             if link.kind == "derives_from" and link.target.record in index)
            if parent.kind == "intent" and _flat(parent.fields.get("quote"))]
        return ("decision", "\n".join(p for p in premise if p),
                _flat(fields.get("chosen")))
    return record.kind, "", record.title


UNVERIFIED = "quote not verified"


class _Prompts:
    """The owner's logged prompts, read once per triage: ``text(prefix)`` is the text of the
    prompt iaso itself logged that a record's ``prompt`` digest prefix names, or None
    (unknown, not hashing to its digest, or recorded by the agent itself, SR-208)."""

    def __init__(self, core: Core) -> None:
        self.core = core
        self.cache: dict[str, str | None] = {}

    def text(self, prefix: Any) -> str | None:
        key = str(prefix or "").strip()
        if not key:
            return None
        if key not in self.cache:
            from iaso.approvals import Refused, find_prompt

            try:
                entry = find_prompt(self.core, key)
            except Refused:
                entry = None
            from iaso.boundary.glance import SELF_RECORDED_VIA

            ok = entry is not None and str(entry.get("via") or "") not in SELF_RECORDED_VIA
            self.cache[key] = str(entry["text"]) if ok and entry is not None else None
        return self.cache[key]


def _holds(text: str | None, quote: str) -> bool:
    from iaso.approvals import quote_in_prompt
    from iaso.normalize import normalize_text

    return text is not None and quote_in_prompt(normalize_text(quote), normalize_text(text))


def _verified_intent(prompts: _Prompts, record: Record) -> str | None:
    """The logged prompt text an intent's quote is verbatim in, or None."""
    text = prompts.text(record.fields.get("prompt"))
    quote = _flat(record.fields.get("quote"))
    return text if quote and _holds(text, quote) else None


def premise_problem(prompts: _Prompts, index: Mapping[str, Record],
                    record: Record) -> str | None:
    """Why the record's premise is not the owner's verified words, or None (R8 A: a record
    is rated against the owner's words only when they are the owner's). Every piece of the
    premise must be verbatim in a prompt the host's prompt hook logged: an intent's quote in
    the prompt its ``prompt`` digest names; a requirement's or a decision's intents the same
    way, and each example quote in one of those prompts or in its own ``prompt``."""
    if record.kind == "intent":
        return None if _verified_intent(prompts, record) else (
            f"{UNVERIFIED}: no prompt the hook logged holds it")
    texts: list[str] = []
    for link in record.links:
        parent = index.get(link.target.record or "")
        if (link.kind == "derives_from" and parent is not None and parent.kind == "intent"
                and _flat(parent.fields.get("quote"))):
            text = _verified_intent(prompts, parent)
            if text is None:
                return f"{UNVERIFIED}: {parent.id}'s quote is in no prompt the hook logged"
            texts.append(text)
    for raw in record.fields.get("examples") or []:
        if not isinstance(raw, Mapping) or not _flat(raw.get("quote")):
            continue
        own = prompts.text(raw.get("prompt"))
        if not any(_holds(t, _flat(raw.get("quote"))) for t in [*texts, own]):
            return (f"{UNVERIFIED}: the quote of {raw.get('id') or 'an example'} is in no "
                    "prompt the hook logged")
    return None


def approved_before(core: Core) -> set[str]:
    """Records with any valid approval in the log, by anyone (an edit of them is never
    low-risk, sp2 8.1)."""
    from iaso.confirm import checked

    out: set[str] = set()
    for entry, problem in checked(core):
        if problem is None and entry.kind == "approval":
            out.update(str(r.get("id")) for r in entry.payload.get("records") or []
                       if isinstance(r, Mapping))
    return out
