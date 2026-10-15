"""Approvals pinned to exact content, and the self-approval guard (spec 5.6).

Only these confirm a record: the owner, with ``plumb approve`` in their own terminal (refused
while the agent session marker ``PLUMB_AGENT_SESSION`` is set, and written only after a y/N
answered in an interactive terminal: ``require_owner``, the one choke point of every owner-only
write); the owner's typed ``/plumb approve`` naming record numbers; and the worker plumb starts,
applying the reader's reading of the owner's own logged message (``plumb.understand``).

The coding agent decides nothing about what the owner approved: there is no relay command
(SR-101 EX-9, SR-135). No fixed rule about the owner's words (affirmation words,
objection words, clause splitting, plain-words matching) is left here (INT-029).
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.contracts import LogEntry
from plumb.normalize import sha256_bytes, sha256_text
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


# The host marks a message from another Claude session with this wrapper; plumb reads the
# mark (a structured format), never the words.
_PEER_WRAPPER = re.compile(r"\s*<cross-session-message\b([^>]*)>")
# Host-marked non-owner text: a cross-session delivery notice, and the caveat or command tags
# of a slash command the owner typed (a command, not a request).
_NOTICE = re.compile(r"\s*\[Cross-session delivery notice\]")
_COMMAND = re.compile(r"\s*<(?:local-command-caveat|command-name)>")
_FROM_NAME = re.compile(r'from-name=(?:"([^"]*)"|(\S+))')


def prompt_origin(text: str) -> tuple[str, str]:
    """``(origin, from-name)`` of a prompt: ``peer`` when the host wrapped it as another
    session's message, ``notification`` or ``command`` for host-marked notices, else ``owner`` (SR-168)."""
    wrapped = _PEER_WRAPPER.match(text)
    if _NOTICE.match(text):
        return "notification", ""
    if _COMMAND.match(text):
        return "command", ""
    if wrapped is None:
        return "owner", ""
    name = _FROM_NAME.search(wrapped.group(1))
    return "peer", (name.group(1) or name.group(2)) if name else ""


def is_owner_entry(entry: Mapping[str, Any]) -> bool:
    """Whether a prompt-log entry holds the owner's own words. Entries logged before origins
    existed have no ``origin``: they count as the owner's unless the host wrapped them."""
    origin = entry.get("origin")
    if origin is None:
        return prompt_origin(str(entry.get("text") or ""))[0] == "owner"
    return origin == "owner"


def marker() -> str | None:
    value = os.environ.get("PLUMB_AGENT_SESSION")
    return value or None


def refuse_under_marker(command: str) -> None:
    value = marker()
    if value:
        raise Refused(f"plumb {command} refused: the agent session marker is set "
                      f"(PLUMB_AGENT_SESSION={value}). Only the owner approves, in their own "
                      "terminal, or by typing /plumb approve with the record numbers.")


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
                      "(stdin and stdout both terminals; in mintty, prefix winpty). The owner "
                      "can also type /plumb approve with the record numbers.")
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
    """Each record with the hash of the approval being revoked (its latest one), read
    through the confirmation choke point (``confirm.remaining``: an approval a renumber
    carried to a new ID is revoked under that ID, sp6 5.4)."""
    from plumb.confirm import remaining

    approvals = {rid: [(h, by) for h, by, _ in items]
                 for rid, items in remaining(core).items()}
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


# --------------------------------------------------------------------------- prompts


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
    if not is_owner_entry(entry):
        raise Refused(f"prompt {digest[:19]} is not the owner's words (origin: "
                      f"{entry.get('origin') or 'peer'})")
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
    """The logged prompt that grounds an owner decision the agent presents (``plumb escalate
    decline --prompt``, a conflict answer): the one choke point of R2's "the owner's explicit
    words".

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
