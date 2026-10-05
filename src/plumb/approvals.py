"""Approvals pinned to exact content, and the self-approval guard (spec 5.6).

Only two sources confirm a record:

1. the owner, with ``plumb approve`` in their own terminal (refused while the agent session
   marker ``PLUMB_AGENT_SESSION`` is set);
2. an agent-relayed approval, ``plumb relay``, which carries the owner's verbatim words: the
   cited prompt must be in the prompt log and hash to its digest, the quote must be a verbatim
   part of it and contain an affirmation that no negation before it in its sentence turns
   into an objection and that is not in a question, and every record must be in the stated
   set of the reply before that prompt or be named in the quote.

Silence, or a prompt that neither affirms nor objects, confirms nothing.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.confirm import affirmation_in, confirmation_of, remaining_approvals
from plumb.contracts import LogEntry
from plumb.normalize import normalize_text, sha256_bytes, sha256_text

if TYPE_CHECKING:
    from plumb.api import Core

MIN_PREFIX = 12


class Refused(PermissionError):
    """Refused by the guard (exit 3); nothing was written."""


class ApprovalError(ValueError):
    """An approval request naming unknown records or nothing to act on (exit 1)."""


def prompt_digest(text: str) -> str:
    """The digest the prompt hook records for a prompt: sha256 of its UTF-8 text."""
    return sha256_bytes(text.encode("utf-8"))


def marker() -> str | None:
    value = os.environ.get("PLUMB_AGENT_SESSION")
    return value or None


def refuse_under_marker(command: str) -> None:
    value = marker()
    if value:
        raise Refused(f"plumb {command} refused: the agent session marker is set "
                      f"(PLUMB_AGENT_SESSION={value}). Only the owner approves, in their own "
                      "terminal; relay the owner's words with plumb relay instead.")


def _records(core: Core, ids: Iterable[str]) -> list[dict[str, str]]:
    index = core.index()
    out: list[dict[str, str]] = []
    for record_id in ids:
        record = index.get(record_id)
        if record is None:
            raise ApprovalError(f"no record {record_id}")
        if all(r["id"] != record_id for r in out):
            out.append({"id": record_id, "hash": record.hash})
    if not out:
        raise ApprovalError("name at least one record")
    return out


def pending(core: Core) -> list[tuple[str, str, str]]:
    """``(id, hash, confirmation)`` of every proposed or unconfirmed-edit record."""
    index = core.index()
    approvals = remaining_approvals(core.events(), core.config.approve.affirmations)
    out = []
    for record_id in sorted(index):
        state, _ = confirmation_of(index[record_id], approvals.get(record_id, []))
        if state != "confirmed":
            out.append((record_id, index[record_id].hash, state))
    return out


def approve(core: Core, ids: Iterable[str], *, note: str = "") -> LogEntry:
    """Owner approval of records at their current hashes."""
    refuse_under_marker("approve")
    records = _records(core, ids)
    payload = {"records": records, "by": "owner", "prompt_digest": None, "quote": None,
               "quote_digest": None, "affirmation": None, "stated_set": None, "note": note}
    return core.log_append("events", "approval", payload)


def _revoked_records(core: Core, ids: Iterable[str]) -> list[dict[str, str]]:
    """Each record with the hash of the approval being revoked (its latest one)."""
    approvals = remaining_approvals(core.events(), core.config.approve.affirmations)
    out = []
    for item in _records(core, ids):
        remaining = approvals.get(item["id"], [])
        if not remaining:
            raise ApprovalError(f"{item['id']} has no approval to revoke")
        out.append({"id": item["id"], "hash": remaining[-1][0]})
    return out


def revoke(core: Core, ids: Iterable[str], *, note: str = "") -> LogEntry:
    refuse_under_marker("revoke")
    payload = {"records": _revoked_records(core, ids), "by": "owner", "prompt_digest": None,
               "quote": None, "quote_digest": None, "note": note}
    return core.log_append("events", "revocation", payload)


# --------------------------------------------------------------------------- relay


def _read_jsonl(path: Any) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, Mapping):
                    out.append(item)
    except FileNotFoundError:
        pass
    return out


def find_prompt(core: Core, given: str) -> Mapping[str, Any]:
    """The logged prompt a digest (full, or a unique prefix of 12+ hex digits) names."""
    wanted = given.strip().lower().removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]+", wanted or "x") or len(wanted) < MIN_PREFIX:
        raise Refused(f"prompt digest '{given}' must be at least {MIN_PREFIX} hex digits")
    matches: dict[str, Mapping[str, Any]] = {}
    for entry in _read_jsonl(core.paths.prompts):
        digest = str(entry.get("digest", ""))
        if digest.removeprefix("sha256:").startswith(wanted):
            matches.setdefault(digest, entry)
    if not matches:
        raise Refused(f"prompt {given} is not in the prompt log (.plumb/session/prompts.jsonl)")
    if len(matches) > 1:
        raise Refused(f"prompt digest prefix {given} is ambiguous; give more digits")
    digest, entry = next(iter(matches.items()))
    text = entry.get("text")
    if not isinstance(text, str) or digest not in (prompt_digest(text), sha256_text(text)):
        raise Refused(f"logged prompt {digest[:19]} does not hash to its digest")
    return {**entry, "digest": digest}


def _stated(core: Core, prompt_at: str) -> tuple[dict[str, str], list[str]]:
    """The stated set ``{id: hash}`` of the reply before the prompt, and its ids."""
    try:
        data = json.loads(core.paths.stated.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, []
    if not isinstance(data, Mapping):
        return {}, []
    stated_at = str(data.get("at") or "")
    if stated_at and prompt_at and stated_at > prompt_at:
        return {}, []  # written after the prompt: not the reply the owner answered
    records = {}
    for item in data.get("records") or []:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str):
            records[item["id"]] = str(item.get("hash") or "")
    return records, list(records)


def _named(record_id: str, quote: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9-]){re.escape(record_id)}(?![0-9])", quote) is not None


def _quote_pattern(quote: str) -> re.Pattern[str]:
    head = r"(?<!\w)" if re.match(r"\w", quote[0]) else ""
    tail = r"(?!\w)" if re.match(r"\w", quote[-1]) else ""
    return re.compile(head + re.escape(quote) + tail)


def quote_in_prompt(quote: str, text: str) -> bool:
    """Whether ``quote`` occurs verbatim in ``text`` on whole-word boundaries.

    A quote whose first (last) character is a word character must not be preceded (followed)
    by a word character in the prompt, so a fragment cut from inside a word ("ok" from
    "looks", "yes" from "yesterday") is not the owner's words.
    """
    if not quote:
        return False
    return _quote_pattern(quote).search(text) is not None


# A sentence ends at ., !, ? or ; followed by whitespace or the end, or at a line break, so
# "a.py" or "v1.2" do not split a sentence.
_SENTENCE_END = re.compile(r"[.!?;]+(?=\s|$)|\n")
# Words that turn an affirmation after them (in the same sentence) into a refusal or a delay.
_NEGATION = re.compile(
    r"(?<!\w)(?:no|not|never|nope|nah|nor|neither|wait|hold|stop|cannot|dont|cant|wont"
    r"|isnt|arent|shouldnt|wouldnt|doesnt|didnt|without)(?!\w)|\w+n['’]t(?!\w)",
    re.IGNORECASE)
# Idioms that contain a negation word but affirm.
_NOT_NEGATING = re.compile(
    r"(?<!\w)(?:no\s+(?:objections?|problems?|issues?|concerns?|complaints?)"
    r"|not\s+a\s+problem|no\s+worries)(?!\w)", re.IGNORECASE)


def _affirmation_offsets(quote: str, affirmations: Sequence[str]) -> list[int]:
    """Start offsets in ``quote`` of every configured affirmation term (whole words)."""
    offsets: list[int] = []
    for term in affirmations:
        words = [re.escape(w) for w in term.split()]
        if words:
            pattern = r"(?<![\w])" + r"\s+".join(words) + r"(?![\w])"
            offsets.extend(m.start() for m in re.finditer(pattern, quote, re.IGNORECASE))
    return sorted(set(offsets))


def affirmation_context_problem(quote: str, text: str,
                                affirmations: Sequence[str]) -> str | None:
    """Why the affirmation in ``quote`` does not affirm in its place in ``text``, or None.

    Each affirmation term of the quote, at each place the quote occurs in the prompt, is read
    in its sentence: a negation word before it in that sentence ("no, do not approve
    SR-001", "SR-001 is not ok") makes it an objection, and a sentence ending in ``?`` makes
    it a question. Either confirms nothing (R2). Words after the affirmation ("ok, but do
    not touch the docs") and other sentences of the prompt do not count.
    """
    offsets = _affirmation_offsets(quote, affirmations)
    for occurrence in _quote_pattern(quote).finditer(text):
        for offset in offsets:
            at = occurrence.start() + offset
            begin = 0
            for end in _SENTENCE_END.finditer(text, 0, at):
                begin = end.end()
            following = _SENTENCE_END.search(text, at)
            if following is not None and "?" in following.group():
                return ("the quote's affirmation sits in a question; a question confirms "
                        "nothing")
            before = _NOT_NEGATING.sub(" ", text[begin:at])
            word = _NEGATION.search(before)
            if word is not None:
                return (f"the quote's affirmation is negated by '{word.group()}' before it "
                        "in the prompt; an objection confirms nothing")
    return None


def relay(core: Core, ids: Sequence[str], *, prompt: str, quote: str, revoke: bool = False,
          note: str = "") -> LogEntry:
    """Record an approval (or revocation) the agent relays from the owner's own words."""
    entry = find_prompt(core, prompt)
    text = str(entry["text"])
    normalized_quote = normalize_text(quote)
    if not normalized_quote or not quote_in_prompt(normalized_quote, normalize_text(text)):
        raise Refused("the quote is not a verbatim part of that prompt (whole words)")
    affirmation = None
    if not revoke:
        affirmation = affirmation_in(normalized_quote, core.config.approve.affirmations)
        if affirmation is None:
            raise Refused("the quote does not affirm (no affirmation term such as ok, yes, "
                          "approve, lgtm, go ahead); a prompt that does not object is not a "
                          "confirmation")
        problem = affirmation_context_problem(normalized_quote, normalize_text(text),
                                              core.config.approve.affirmations)
        if problem is not None:
            raise Refused(problem)
    records = _revoked_records(core, ids) if revoke else _records(core, ids)
    stated, stated_ids = _stated(core, str(entry.get("at") or ""))
    index = core.index()
    for item in records:
        record_id = item["id"]
        in_set = record_id in stated and stated[record_id] in ("", index[record_id].hash)
        if not in_set and not _named(record_id, normalized_quote):
            raise Refused(f"{record_id} is not in the stated set of the reply before that "
                          "prompt and the quote does not name it")
    digest = str(entry["digest"])
    known = {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}
    if digest not in known:
        core.log_append("events", "prompt", {"digest": digest,
                                             "session": entry.get("session"),
                                             "at": entry.get("at")})
    payload: dict[str, Any] = {"records": records, "by": "agent-relayed",
                               "prompt_digest": digest, "quote": normalized_quote,
                               "quote_digest": sha256_text(normalized_quote)}
    if revoke:
        payload["note"] = note
        return core.log_append("events", "revocation", payload)
    payload.update({"affirmation": affirmation, "stated_set": stated_ids or None,
                    "note": note})
    return core.log_append("events", "approval", payload)
