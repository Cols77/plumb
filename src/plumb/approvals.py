"""Approvals pinned to exact content, and the self-approval guard (spec 5.6).

Only two sources confirm a record:

1. the owner, with ``plumb approve`` in their own terminal: refused while the agent session
   marker ``PLUMB_AGENT_SESSION`` is set, and, on every host, written only after a y/N
   answered in an interactive terminal (``require_owner``, the one choke point of every
   owner-only write), so an agent shell the adapter could not mark is refused too;
2. an agent-relayed approval, ``plumb relay``, which carries the owner's verbatim words: the
   cited prompt must be in the prompt log and hash to its digest, the quote must be a verbatim
   part of it and contain an affirmation that no negation before it in its sentence turns
   into an objection and that is not in a question, and every record must be in the stated
   set of the reply before that prompt, shown there in full, or be named in the quote.

Silence, or a prompt that neither affirms nor objects, confirms nothing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.confirm import affirmation_in, remaining_approvals
from plumb.contracts import LogEntry
from plumb.normalize import normalize_text, sha256_bytes, sha256_text
from plumb.trace import owning_ends

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


class Declined(Exception):
    """The owner answered no (or nothing) at the terminal question; nothing was written."""


def _interactive() -> bool:
    """Whether stdin and stdout are both interactive terminals."""
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def owner_terminal_answer(question: str) -> str | None:
    """The answer typed at ``question`` in an interactive terminal, or None when stdin and
    stdout are not both terminals (an agent's shell tool, a pipe, a script, CI).

    Tests replace this function (``tests/conftest.py``) so the test process stands in for the
    owner's terminal; the guard's own tests restore it."""
    if not _interactive():
        return None
    try:
        return input(question)
    except EOFError:
        return ""


def require_owner(command: str, question: str) -> None:
    """The one choke point of every owner-only write (concept 4.6, guard check 4).

    Guarantee: an entry attributed to the owner (``by: owner`` approval or revocation, owner
    waiver, set or triage approval, the auto-approve ``config`` event) is written only from
    the owner's own interactive terminal, on every host. Refused (exit 3) under the session
    marker, and refused when stdin and stdout are not both terminals, which is how an agent's
    shell runs on a host whose adapter cannot set the marker; a piped "y" proves nothing.
    Otherwise the owner answers ``question`` with y/N; any other answer raises ``Declined``.
    """
    refuse_under_marker(command)
    answer = owner_terminal_answer(f"{question} [y/N] ")
    if answer is None:
        raise Refused(f"plumb {command} refused: not an interactive terminal. Owner-only "
                      "commands write only after a y/N answered in the owner's own terminal "
                      "(stdin and stdout both terminals; in mintty, prefix winpty). An agent "
                      "relays the owner's words with plumb relay instead.")
    if answer.strip().lower() not in ("y", "yes"):
        raise Declined(f"plumb {command}: nothing written")


def _names(items: Sequence[Mapping[str, Any]], extra: Mapping[str, Any]) -> str:
    names = [str(item["id"]) for item in items]
    shown = ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
    if extra.get("exempt"):
        shown = (shown + "; " if shown else "") + "trace.exempt " + " ".join(extra["exempt"])
    return shown


def _verified_pins(core: Core, record: Any) -> dict[str, str]:
    """``{verified_by end: content hash}`` of a requirement's existing acceptance tests."""
    from plumb.confirm import verified_end

    out: dict[str, str] = {}
    for link in record.links:
        end = verified_end(link)
        if end is None:
            continue
        digest = core.hash_target(link.target)
        if digest is not None:
            out[end] = digest
    return out


def _records(core: Core, ids: Iterable[str]) -> list[dict[str, Any]]:
    index = core.index()
    out: list[dict[str, Any]] = []
    for record_id in ids:
        record = index.get(record_id)
        if record is None:
            raise ApprovalError(f"no record {record_id}")
        if all(r["id"] != record_id for r in out):
            item: dict[str, Any] = {"id": record_id, "hash": record.hash}
            ends = owning_ends(record)
            if ends:  # what the requirement owns as approved: the merge boundary asks
                item["ends"] = ends  # again for an end added later (a widened requirement)
            verified = _verified_pins(core, record)
            if verified:  # the content of each acceptance test the owner confirmed: an
                item["verified"] = verified  # edit to it is an unconfirmed edit (confirm.py)
            out.append(item)
    if not out:
        raise ApprovalError("name at least one record")
    return out


def pending(core: Core) -> list[tuple[str, str, str]]:
    """``(id, hash, confirmation)`` of every proposed or unconfirmed-edit record (a
    requirement whose confirmed acceptance test changed is an unconfirmed edit too)."""
    index = core.index()
    statuses = core.status()
    out = []
    for record_id in sorted(index):
        state = statuses[record_id].confirmation
        if state != "confirmed":
            out.append((record_id, index[record_id].hash, state))
    return out


def current_exempt(core: Core) -> list[str]:
    """The ``trace.exempt`` globs of the current config, sorted."""
    return sorted({str(g) for g in core.config.trace.exempt})


def approved_exempt(core: Core) -> set[str]:
    """Every ``trace.exempt`` glob a valid approval entry confirmed (spec 7.5)."""
    from plumb.confirm import checked_entries

    out: set[str] = set()
    for entry, problem in checked_entries(core.events(), core.config.approve.affirmations):
        if problem is None and entry.kind == "approval":
            out.update(str(g) for g in entry.payload.get("exempt") or [])
    return out


def _exempt_payload(core: Core, exempt: bool) -> dict[str, Any]:
    if not exempt:
        return {}
    globs = current_exempt(core)
    if not globs:
        raise ApprovalError("trace.exempt in .plumb/config.yaml lists no globs to confirm")
    return {"exempt": globs}


def approve(core: Core, ids: Iterable[str], *, note: str = "",
            exempt: bool = False) -> LogEntry:
    """Owner approval of records at their current hashes; with ``exempt``, also of the
    current ``trace.exempt`` globs (paths the owner says need no requirement)."""
    refuse_under_marker("approve")
    ids = list(ids)
    extra = _exempt_payload(core, exempt)
    records = _records(core, ids) if ids or not extra else []
    require_owner("approve", f"approve {_names(records, extra)} at their current content, "
                  "as yourself (by: owner)?")
    payload = {"records": records, "by": "owner", "prompt_digest": None, "quote": None,
               "quote_digest": None, "affirmation": None, "stated_set": None, "note": note,
               **extra}
    return core.log_append("events", "approval", payload)


def _revoked_records(core: Core, ids: Iterable[str]) -> list[dict[str, Any]]:
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
    records = _revoked_records(core, ids)
    require_owner("revoke", f"revoke your approval of {_names(records, {})} (by: owner)?")
    payload = {"records": records, "by": "owner", "prompt_digest": None,
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


def _stated(core: Core, prompt_at: str) -> tuple[dict[str, tuple[str, bool]], list[str]]:
    """The stated set ``{id: (hash, shown)}`` of the reply before the prompt, and its ids.

    ``shown`` is false for a record the reply did not display in full (cut by the summary
    cap, too long, or a blocked stop); a stated set written before ``shown`` existed counts
    every record as shown.
    """
    try:
        data = json.loads(core.paths.stated.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, []
    if not isinstance(data, Mapping):
        return {}, []
    stated_at = str(data.get("at") or "")
    if stated_at and prompt_at and stated_at > prompt_at:
        return {}, []  # written after the prompt: not the reply the owner answered
    records: dict[str, tuple[str, bool]] = {}
    for item in data.get("records") or []:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str):
            records[item["id"]] = (str(item.get("hash") or ""), item.get("shown") is not False)
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
          note: str = "", exempt: bool = False) -> LogEntry:
    """Record an approval (or revocation) the agent relays from the owner's own words.

    With ``exempt``, the approval also confirms the current ``trace.exempt`` globs; the quote
    must then name the exemption (the word "exempt" or one of the globs)."""
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
    extra = _exempt_payload(core, exempt and not revoke)
    if extra and not (re.search(r"(?<!\w)exempt", normalized_quote, re.IGNORECASE)
                      or any(g in normalized_quote for g in extra["exempt"])):
        raise Refused("the quote does not name the exemption (the word exempt or a glob); "
                      "an ok about something else confirms no trace.exempt change")
    records: list[dict[str, Any]] = []
    if ids or not extra:
        records = _revoked_records(core, ids) if revoke else _records(core, ids)
    stated, stated_ids = _stated(core, str(entry.get("at") or ""))
    index = core.index()
    for item in records:
        record_id = item["id"]
        if _named(record_id, normalized_quote):
            continue
        stated_hash, shown = stated.get(record_id, (None, False))
        if stated_hash is None or stated_hash not in ("", index[record_id].hash):
            raise Refused(f"{record_id} is not in the stated set of the reply before that "
                          "prompt and the quote does not name it")
        if not shown:
            raise Refused(f"{record_id} was not shown in full in the reply before that "
                          "prompt (plumb show prints it); the quote must name it")
    digest = str(entry["digest"])
    known = {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}
    if digest not in known:
        core.log_append("events", "prompt", {"digest": digest,
                                             "session": entry.get("session"),
                                             "at": entry.get("at")})
    payload: dict[str, Any] = {"records": records, "by": "agent-relayed",
                               "prompt_digest": digest, "quote": normalized_quote,
                               "quote_digest": sha256_text(normalized_quote),
                               # R13 Q4: the cited prompt reached the log through the
                               # agent's own `plumb turn start`, not the host's prompt hook
                               "self_recorded": entry.get("via") == "turn"}
    if revoke:
        payload["note"] = note
        return core.log_append("events", "revocation", payload)
    payload.update({"affirmation": affirmation, "stated_set": stated_ids or None,
                    "note": note, **extra})
    return core.log_append("events", "approval", payload)
