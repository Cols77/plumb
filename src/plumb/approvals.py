"""Approvals pinned to exact content, and the self-approval guard (spec 5.6).

Only two sources confirm a record:

1. the owner, with ``plumb approve`` in their own terminal: refused while the agent session
   marker ``PLUMB_AGENT_SESSION`` is set, and, on every host, written only after a y/N
   answered in an interactive terminal (``require_owner``, the one choke point of every
   owner-only write), so an agent shell the adapter could not mark is refused too;
2. an agent-relayed approval, ``plumb relay``, which carries the owner's verbatim words: the
   cited prompt must be in the prompt log and hash to its digest, the quote must be a verbatim
   part of it and contain an affirmation that no negation before it in its sentence turns
   into an objection and that is not in a question, no record may be named in the prompt
   next to objection words, an ok whose clause names records confirms only those
   (``owner_scope``), and every record must be in the stated set of the reply before that
   prompt, shown there in full, or be named in the quote.

Silence, or a prompt that neither affirms nor objects, confirms nothing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.confirm import affirmation_in, escalated_of, remaining_approvals
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


def approval_items(core: Core, ids: Iterable[str]) -> list[dict[str, Any]]:
    """The ``records`` of an approval of ``ids`` at their current hashes, with the owned
    ends and the acceptance-test pins (what the merge boundary and ``changed_tests`` check)."""
    return _records(core, ids)


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
    from plumb.confirm import checked

    out: set[str] = set()
    for entry, problem in checked(core):
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
    approvals = remaining_approvals(core.events(), core.config.approve.affirmations,
                                    escalated_of(core))
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
    """The logged prompt a digest (full, or a unique prefix of 12+ hex digits) names.

    The same words sent twice ("ok" in one session, "ok" again later) share a digest; the
    entry is the LATEST one logged, the prompt the owner just sent, so its time is the one
    the stated set of the reply before it is checked against (``_stated``,
    ``_stated_group``). The prompt log is append-only, so the last line is the latest."""
    wanted = given.strip().lower().removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]+", wanted or "x") or len(wanted) < MIN_PREFIX:
        raise Refused(f"prompt digest '{given}' must be at least {MIN_PREFIX} hex digits")
    matches: dict[str, Mapping[str, Any]] = {}
    for entry in _read_jsonl(core.paths.prompts):
        digest = str(entry.get("digest", ""))
        if digest.removeprefix("sha256:").startswith(wanted):
            matches[digest] = entry  # the latest entry of each digest wins
    if not matches:
        raise Refused(f"prompt {given} is not in the prompt log (.plumb/session/prompts.jsonl)")
    if len(matches) > 1:
        raise Refused(f"prompt digest prefix {given} is ambiguous; give more digits")
    digest, entry = next(iter(matches.items()))
    text = entry.get("text")
    if not isinstance(text, str) or digest not in (prompt_digest(text), sha256_text(text)):
        raise Refused(f"logged prompt {digest[:19]} does not hash to its digest")
    return {**entry, "digest": digest}


# Hosts whose prompt hook logs every owner prompt once plumb is installed there: the install
# writes the hooks and the session marker together (``plumb install claude-code``).
PROMPT_HOOK_HOSTS = ("claude-code",)


def host_logs_prompts(core: Core, host: str | None) -> bool:
    """Whether the host named by the session marker has a working prompt hook.

    Claude Code always does (the marker and the hooks are installed together). Another
    host's hooks run only once the owner trusts them (Codex keeps a hash per hook), so
    there a prompt the hook already logged for that host is the proof. Without a marker
    (the owner's own terminal, or a host that cannot set one) nothing says so."""
    if not host or host == "cli":
        return False
    if host in PROMPT_HOOK_HOSTS:
        return True
    return any(item.get("via") == "hook" and item.get("host") == host
               for item in _read_jsonl(core.paths.prompts))


def owner_prompt(core: Core, given: str) -> Mapping[str, Any]:
    """The logged prompt that grounds an owner decision the agent relays (``plumb relay``
    with IDs, ``--group``, ``--set``, ``plumb escalate decline --prompt``): the one choke
    point of R2's "the owner's explicit words".

    Guarantee: on a host whose prompt hook is installed, only a prompt that hook logged
    (``via: hook``) grounds a relay. A message the agent recorded itself (``plumb turn
    start``, ``via: turn``) is the CLI-only fallback's path for hosts WITHOUT a prompt hook
    (R13 Q4, labelled "self-recorded message"); where the hook exists, it would let the
    agent write the owner's words itself, so it is refused (exit 3)."""
    entry = find_prompt(core, given)
    host = marker()
    if entry.get("via") != "hook" and host_logs_prompts(core, host):
        raise Refused(f"prompt {str(entry['digest'])[:19]} was not logged by the prompt hook "
                      f"(via: {entry.get('via') or '?'}); on this host "
                      f"(PLUMB_AGENT_SESSION={host}) only the owner's own prompts, as the "
                      "hook logged them, confirm anything. A message the agent recorded "
                      "itself (plumb turn start) is for hosts without a prompt hook")
    return entry


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


# ----------------------------------------------------- whose records the owner's words affirm

# A record ID as the owner writes it (the shape plumb.query reads from prompts).
_RECORD_ID = re.compile(r"(?<![A-Za-z0-9-])((?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})(?![0-9])")
# Clause boundaries: punctuation ends a clause after it; a contrastive word starts the next
# clause ("SR-001 is ok | but DEC-001 is wrong", "ok | except SR-034").
_CLAUSE_PUNCT = re.compile(r"[.!?;,:]+(?=\s|$)|\n")
_CLAUSE_WORD = re.compile(r"(?<!\w)(?:but|however|though|although|whereas|while|yet|except"
                          r"|instead)(?!\w)", re.IGNORECASE)
# Words that, in the clause naming a record, object to it or ask to change it (R2: "an
# objection is not an approval"): a record named next to them is never confirmed.
_OBJECTION = re.compile(
    r"(?<!\w)(?:no|not|never|nope|nah|nor|wrong|incorrect|instead|change|changed|changes"
    r"|rewrite|redo|fix|reject|rejected|revert|remove|drop|disagree|except|wait|hold|stop"
    r"|bad|broken|cannot|dont|cant|wont|isnt|arent|shouldnt|wouldnt|doesnt|didnt"
    r"|should|must|rather|prefer|replace|rename|mistake|typo)(?!\w)"
    r"|\w+n['’]t(?!\w)", re.IGNORECASE)
# Words that point at "a record" in general without naming one ("the example is wrong"):
# an objection clause that holds one of them and names no record objects to every
# candidate record.
_REFERENCE = ("example", "examples", "test", "tests", "requirement", "requirements",
              "record", "records", "intent", "decision", "decisions", "assumption",
              "assumptions", "readback", "spec", "card", "statement", "behaviour", "behavior",
              "result", "results")
# Words too common in records to name one by themselves (plain-language naming, R9).
_GENERIC = (*_REFERENCE, "function", "functions", "method", "class", "code", "file", "files",
            "value", "values", "number", "numbers", "return", "returns", "returning", "call",
            "called", "calls", "given", "case", "cases", "thing", "things", "work", "please",
            "carry", "look", "looks", "good", "fine", "right", "need", "want", "like", "keep",
            "add", "adds", "make", "run", "runs", "time", "way", "okay", "yes", "sure",
            "think", "seem", "seems", "go", "ahead")
# What may sit between IDs in a list ("SR-001, SR-002 and DEC-001").
_ID_LIST_FILLER = re.compile(r"(?:[\s,&+/:;]|(?<!\w)(?:and|or)(?!\w))*", re.IGNORECASE)


def _clauses(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of each clause of ``text``; a clause holding only record IDs (a
    list whose predicate follows, "SR-001, DEC-001 are wrong") joins the next clause, or
    the previous one when it ends the text."""
    cuts = {0, len(text)}
    cuts.update(m.end() for m in _CLAUSE_PUNCT.finditer(text))
    cuts.update(m.start() for m in _CLAUSE_WORD.finditer(text))
    points = sorted(cuts)
    spans = [(a, b) for a, b in zip(points, points[1:], strict=False) if text[a:b].strip()]
    merged: list[tuple[int, int]] = []
    pending: int | None = None
    for start, end in spans:
        if pending is not None:
            start, pending = pending, None
        body = _RECORD_ID.sub("", text[start:end])
        if _RECORD_ID.search(text[start:end]) and _ID_LIST_FILLER.fullmatch(body):
            pending = start  # an ID-only clause: its predicate is in the next clause
            continue
        merged.append((start, end))
    if pending is not None:
        if merged:
            merged[-1] = (merged[-1][0], len(text))
        else:
            merged.append((pending, len(text)))
    return merged


def _naming_stems(record: Any) -> frozenset[str]:
    """The words the owner may name ``record`` by (R9: plain language, not IDs): its title,
    statement, read-back, quote, and every example's given/when/then and quote."""
    from plumb.present.resolve import stems

    fields = getattr(record, "fields", {}) or {}
    parts = [str(getattr(record, "title", "") or "")]
    for key in ("statement", "readback", "quote", "question", "chosen"):
        value = fields.get(key)
        parts.extend(map(str, value) if isinstance(value, list) else [str(value or "")])
    for example in getattr(record, "examples", ()) or ():
        parts.extend((example.given, example.when, example.then, example.criterion))
    for raw in fields.get("examples") or []:
        if isinstance(raw, Mapping) and raw.get("quote"):
            parts.append(str(raw["quote"]))
    return stems(" ".join(parts))


def _plain_named(clause: str, records: Mapping[str, Any]) -> set[str]:
    """The ``records`` that ``clause`` names in plain words: one of its distinctive words
    (neither an objection word nor a generic one) is a word of the record."""
    from plumb.present.resolve import stems

    words = stems(_OBJECTION.sub(" ", clause)) - stems(" ".join(_GENERIC))
    if not words:
        return set()
    return {record_id for record_id, record in records.items()
            if words & _naming_stems(record)}


def _refers_generally(clause: str) -> bool:
    from plumb.present.resolve import stems

    return bool(stems(clause) & stems(" ".join(_REFERENCE)))


# A clause that opens with a contrastive word asks for something other than what was shown
# ("sounds good, but b can be negative", "yes, though negative exponents must work too"):
# a change clause even without an objection word.
_CHANGE_OPENING = re.compile(r"^\W*(?:but|however|though|although|whereas|yet|except"
                             r"|instead)(?!\w)", re.IGNORECASE)


def _objects(clause: str) -> bool:
    """Whether ``clause`` objects to something or asks to change it."""
    body = _NOT_NEGATING.sub(" ", _RECORD_ID.sub(" ", clause))
    return bool(_OBJECTION.search(body) or _CHANGE_OPENING.match(clause))


def objection_clauses(text: str) -> list[str]:
    """The clauses of ``text`` that object to something or ask to change it."""
    return [text[a:b].strip() for a, b in _clauses(text) if _objects(text[a:b])]


def owner_scope(text: str, quote: str | None, affirmations: Sequence[str],
                records: Mapping[str, Any] | None = None,
                scope: Iterable[str] | None = None) -> tuple[set[str], set[str]]:
    """``(named, objected)``: the record IDs the owner's affirming words name, and every
    record the prompt names in a clause that objects to it or asks to change it.

    The one place that reads which records a prompt confirms (R2), for ``plumb relay``
    (IDs, ``--group``, ``--set``) and the relay line the prompt hook suggests. The
    affirming words are the clauses ``quote`` occurs in (without a quote: the clauses
    holding an affirmation term). When they name records, an ok confirms only those
    ("SR-001 is ok but DEC-001 is wrong" confirms SR-001 alone). A record named next to
    objection or change words ("wrong", "not", "instead", "should", "except", ...)
    anywhere in the prompt is never confirmed, however the owner names it (R9): by its ID,
    or, among ``records`` (the record index), by a word of its title, statement, examples
    or quote ("the pow example is wrong" objects to the records about pow). An objection
    clause that names no record but refers to one in general ("the example is wrong")
    objects to every record. Both sets are empty for a bare "ok".

    ``scope`` is the records the owner was asked about (the stated set of the reply before
    the prompt and the records relayed). A prompt holding an objection or change clause
    (an objection word, or a clause opening with but, though, except, ...) none of whose
    objections names a record by ID or resolves in plain words to a record of ``scope``
    objects to every record of ``scope``: the
    owner corrected something the agent cannot place ("ok, except 3 minus 5 should return
    0"), so the ok confirms nothing rather than the record the correction is about."""
    clauses = _clauses(text)
    objected: set[str] = set()
    wanted = set(scope or ())
    objecting = False
    placed = False
    for start, end in clauses:
        clause = text[start:end]
        ids = set(_RECORD_ID.findall(clause))
        if not _objects(clause):
            continue
        objecting = True
        named_here = set(ids)
        if records:
            plain = _plain_named(_RECORD_ID.sub(" ", clause), records)
            named_here |= plain
            if not ids and not plain and _refers_generally(clause):
                plain = set(records)
            objected |= plain
        objected |= ids
        if ids or named_here & wanted:  # an ID the owner wrote places the objection
            placed = True
    if objecting and wanted and not placed:
        objected |= wanted
    if quote:
        spans = [(m.start(), m.end()) for m in _quote_pattern(quote).finditer(text)]
    else:
        spans = [(m, m + 1) for m in _affirmation_offsets(text, affirmations)]
    affirming = [(a, b) for a, b in clauses if any(s < b and e > a for s, e in spans)]
    named = {i for a, b in affirming for i in _RECORD_ID.findall(text[a:b])}
    if quote:
        named |= set(_RECORD_ID.findall(quote))
    return named, objected


def _trimmed(text: str, spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """``spans`` without surrounding blanks and closing punctuation."""
    out: list[tuple[int, int]] = []
    for a, b in spans:
        segment = text[a:b]
        body = segment.rstrip().rstrip(".!?;,:").rstrip()
        lead = len(segment) - len(segment.lstrip())
        if body.strip():
            out.append((a + lead, a + len(body)))
    return out


def _statements(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of each statement of ``text``: its sentences, each cut again where a
    contrastive word (but, except, though, ...) starts the next part ("SR-001 is ok | but
    INT-001 is wrong, use floats")."""
    cuts = {0, len(text)}
    cuts.update(m.end() for m in _SENTENCE_END.finditer(text))
    cuts.update(m.start() for m in _CLAUSE_WORD.finditer(text))
    points = sorted(cuts)
    return [(a, b) for a, b in zip(points, points[1:], strict=False) if text[a:b].strip()]


def quote_covers_clauses(quote: str, text: str) -> bool:
    """Whether ``quote`` occurs in ``text`` as whole statements (``_statements``): it starts
    where one starts and ends where one ends (it may span several), never a bare "ok" cut
    from "Ok, carry on with the tests"."""
    spans = _trimmed(text, _statements(text))
    starts = {a for a, _ in spans}
    for occurrence in _quote_pattern(quote).finditer(text):
        begin, end = occurrence.start(), occurrence.end()
        if begin not in starts:
            continue
        last = next((b for a, b in spans if a <= end - 1 < b), None)
        if last is None or end >= last:
            return True
    return False


def _check_scope(text: str, quote: str, affirmations: Sequence[str], ids: Sequence[str],
                 *, group: str | None = None, set_anchor: str | None = None,
                 records: Mapping[str, Any] | None = None,
                 scope: Iterable[str] = ()) -> None:
    """Refused unless the owner's words affirm every record of the relay (``owner_scope``).

    The IDs path: no record the prompt objects to, and, when the affirming words name
    records, only those. ``--group``: the owner's ok to the offer names no record and objects
    to none of the group (otherwise the named IDs are relayed one by one). ``--set``: no set
    id is objected to, and named records include the anchor. When the prompt holds an
    objection or change clause at all, the quote must be the whole clause (or clauses) the
    owner's affirmation sits in, never a bare "ok" cut from beside a correction, so the
    stored quote, which the merge-boundary glance shows, carries what the owner said."""
    named, objected = owner_scope(text, quote, affirmations, records,
                                  scope=[*ids, *scope])
    against = sorted(i for i in ids if i in objected)
    if against:
        allowed = sorted(i for i in (named or set(ids)) if i not in objected and i in ids)
        hint = (f"; relay only {' '.join(allowed)}" if allowed and not (group or set_anchor)
                else "")
        raise Refused(f"the owner's words object to or ask to change {', '.join(against)}; "
                      f"an objection is not an approval{hint}")
    if named and group:
        raise Refused(f"the owner's words name {', '.join(sorted(named))}; an ok naming "
                      f"records confirms those records, not group {group}: relay the named "
                      "IDs instead")
    if named and set_anchor and set_anchor not in named:
        raise Refused(f"the owner's words name {', '.join(sorted(named))}, not the set "
                      f"{set_anchor}; relay the named IDs instead")
    outside = sorted(i for i in ids if i not in named) if named and not set_anchor else []
    if outside:
        allowed = sorted(i for i in ids if i in named)
        hint = f"; relay only {' '.join(allowed)}" if allowed else ""
        raise Refused(f"the owner's words name {', '.join(sorted(named))}, not "
                      f"{', '.join(outside)}; an ok naming records confirms only those{hint}")
    if objection_clauses(text) and not quote_covers_clauses(quote, text):
        raise Refused("the owner's message also objects to or asks to change something; "
                      "quote the whole clause the owner's affirmation sits in, not only "
                      "the affirming words")


def _stated_group(core: Core, group: str, prompt_at: str) -> list[dict[str, Any]]:
    """The records ``{id, hash}`` of the group the reply before the prompt offered (the
    stop hook writes it into the stated set, sp2 8.1)."""
    try:
        data = json.loads(core.paths.stated.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, Mapping):
        raise Refused(f"no group {group} in the stated set of the reply before that prompt")
    stated_at = str(data.get("at") or "")
    if stated_at and prompt_at and stated_at > prompt_at:
        raise Refused("the stated set was written after that prompt; it is not the reply "
                      "the owner answered")
    for item in data.get("groups") or []:
        if isinstance(item, Mapping) and item.get("group") == group:
            records = [r for r in item.get("records") or [] if isinstance(r, Mapping)
                       and isinstance(r.get("id"), str) and isinstance(r.get("hash"), str)]
            if records:
                return [{"id": r["id"], "hash": r["hash"]} for r in records]
    raise Refused(f"no group {group} in the stated set of the reply before that prompt; "
                  "the owner's ok confirms only a group the reply offered")


def _check_shown(record_id: str, current: str, quote: str,
                 stated: Mapping[str, tuple[str, bool]]) -> None:
    """Refused unless the quote names ``record_id``, or the reply before the prompt showed
    it in full at its ``current`` hash (R2: a relayed ok confirms only what it showed)."""
    if _named(record_id, quote):
        return
    stated_hash, shown = stated.get(record_id, (None, False))
    if stated_hash is None or stated_hash not in ("", current):
        raise Refused(f"{record_id} is not in the stated set of the reply before that "
                      "prompt at its current content and the quote does not name it")
    if not shown:
        raise Refused(f"{record_id} was not shown in full in the reply before that "
                      "prompt (plumb show prints it); the quote must name it")


def _check_set_shown(anchor: str, records: Sequence[Mapping[str, Any]], quote: str,
                     stated: Mapping[str, tuple[str, bool]]) -> None:
    """The set path's R2 check, over every set id (the anchor and each member), each at the
    hash the set approval pins (sp2 6.2).

    Through the stated set (the quote does not name the anchor), every set id must have been
    shown in full at that hash. When the quote names the anchor, the owner refers to the set
    by name; a set id the reply showed at another hash was still edited after the owner saw
    it, and is refused unless the quote names it too."""
    anchor_named = _named(anchor, quote)
    for item in records:
        record_id, current = str(item["id"]), str(item["hash"])
        if anchor_named and not _named(record_id, quote):
            stated_hash = stated.get(record_id, (None, False))[0]
            if stated_hash not in (None, "", current):
                raise Refused(f"{record_id} of the set {anchor} changed after the reply "
                              "before that prompt showed it; show the set again (plumb spec "
                              "show) and relay the owner's new words")
            continue
        _check_shown(record_id, current, quote, stated)


def relay(core: Core, ids: Sequence[str], *, prompt: str, quote: str, revoke: bool = False,
          note: str = "", exempt: bool = False, group: str | None = None,
          set_anchor: str | None = None) -> LogEntry:
    """Record an approval (or revocation) the agent relays from the owner's own words.

    With ``exempt``, the approval also confirms the current ``trace.exempt`` globs; the quote
    must then name the exemption (the word "exempt" or one of the globs). With ``group``
    (sp2 8.1), it approves exactly the records and hashes of that group in the stated set of
    the reply before the prompt (a record changed since is left out and named). With
    ``set_anchor`` (sp2 6.2), it is the one set-hash approval of an escalated spec: every set
    id (the anchor and each member) must be in that stated set, shown, at the hash the
    approval pins, unless the quote names the anchor; then only a set id shown at another
    hash (edited after the owner saw it) is refused (``_check_set_shown``).

    A confirmation resting on a prompt the prompt hook did not record (a host without one,
    where the agent recorded the message itself) is labelled ``self_recorded`` (R13 Q4); on a
    host whose prompt hook is installed, such a prompt is refused (``owner_prompt``)."""
    entry = owner_prompt(core, prompt)
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
    left_out: list[str] = []
    set_digest: dict[str, str] | None = None
    triage: dict[str, Any] | None = None
    index = core.index()
    if (group or set_anchor) and (revoke or ids or exempt):
        raise ApprovalError("--group and --set approve a whole offered group or set; they "
                            "take no IDs, --revoke or --exempt")
    if group:
        for item in _stated_group(core, group, str(entry.get("at") or "")):
            record = index.get(item["id"])
            if record is None or record.hash != item["hash"]:
                left_out.append(item["id"])
                continue
            records.extend(_records(core, [item["id"]]))
        if not records:
            raise Refused(f"every record of group {group} changed since it was offered: "
                          + ", ".join(left_out))
        triage = {"group": group, "left_out": left_out}
    elif set_anchor:
        from plumb.capture.spec import SpecError, set_payload

        try:
            records, set_digest = set_payload(core, set_anchor)
        except SpecError as exc:
            raise ApprovalError(str(exc)) from exc
    elif ids or not extra:
        records = _revoked_records(core, ids) if revoke else _records(core, ids)
    stated, stated_ids = _stated(core, str(entry.get("at") or ""))
    if not revoke and records:
        relayed = [str(r["id"]) for r in records]
        _check_scope(normalize_text(text), normalized_quote, core.config.approve.affirmations,
                     relayed, group=group, set_anchor=set_anchor,
                     records=index, scope=stated_ids)
    if set_anchor:
        _check_set_shown(set_anchor, records, normalized_quote, stated)
    elif not group:
        for item in records:
            _check_shown(item["id"], index[item["id"]].hash, normalized_quote, stated)
    digest = str(entry["digest"])
    known = {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}
    if digest not in known:
        core.log_append("events", "prompt", {"digest": digest,
                                             "session": entry.get("session"),
                                             "at": entry.get("at")})
    payload: dict[str, Any] = {"records": records, "by": "agent-relayed",
                               "prompt_digest": digest, "quote": normalized_quote,
                               "quote_digest": sha256_text(normalized_quote),
                               # R13 Q4: the cited prompt did not reach the log through the
                               # host's prompt hook (`plumb turn start`, or a message the
                               # agent recorded itself): shown as "self-recorded message"
                               "self_recorded": entry.get("via") != "hook"}
    if revoke:
        payload["note"] = note
        return core.log_append("events", "revocation", payload)
    payload.update({"affirmation": affirmation, "stated_set": stated_ids or None,
                    "note": note, **extra})
    if objection_clauses(normalize_text(text)):
        # the owner's message also objected to or asked to change something (not these
        # records): the merge-boundary glance flags it beside the quote
        payload["prompt_objects"] = True
    if set_digest is not None:
        payload["set"] = set_digest
    if triage is not None:
        payload["triage"] = triage
    return core.log_append("events", "approval", payload)
