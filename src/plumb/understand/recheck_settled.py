"""Re-check of ``by: settled`` approvals and ``by: undone`` revocations (JUDGE, SR-105, SR-106).

A ``settled`` revocation is plumb withdrawing a settling that no longer stands
(``settle.revalidate``); it can only return a record to proposed, so it needs no more than its
shape. A settled approval is written by the worker only (the log checks the worker token when it is
written), but a hand-written entry file never passes through the log's writer: this re-check is
what makes a forged or altered entry confirm nothing. It is called with no log context by
``confirm.entry_problem``, so it reads the log of the repository the process runs in
(``ambient_core``); an entry it cannot find there is refused. It checks:

- the shape (the job, the model, the score, the premise digest and the calibration it names);
- in the log: a ``supported`` judgment of that very job, record version, score, model and
  premise exists in the log; settling was on for the kind when it was written, under a passing
  calibration the entry names; the record is of a kind that settles (not a decision, not a
  member of an escalated set, not an option picked among several); and the premise it rests on is
  unchanged (the digest of the premise now is the digest it was settled on).

An ``undone`` revocation is the owner's: written from the owner's own terminal or button (no
agent marker), or carrying the owner's typed ``/plumb undo ...`` as the quote of a logged prompt
(its digest is the digest of that text). Anything else undoes nothing; prose does not."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from plumb.contracts import LogEntry
from plumb.present import owner_text
from plumb.understand.typed import PREFIX

# SR-120: typed as /plumb or as the plugin's /plumb:plumb, in lower case as typed.parse reads
# every typed command
UNDO = re.compile(r"^" + PREFIX + r"\s+undo\s+(\S.*?)\s*$")


_AMBIENT: dict[str, tuple[Any, Any]] = {}


def ambient_core() -> Any:
    """The Core of the repository the process runs in, for a re-check that is called with no
    log context (``confirm.entry_problem``). Kept while the events do not change; None when
    there is no repository here. The check never reads confirmations (that would recurse)."""
    try:
        from pathlib import Path

        from plumb.api import open_core
        from plumb.log import stream_stamp
        from plumb.paths import PlumbPaths, find_root

        root = find_root(Path.cwd())
        stamp = stream_stamp(PlumbPaths(root), "events")
        held = _AMBIENT.get(str(root))
        if held is not None and held[0] == stamp:
            return held[1]
        core = open_core(root)
        _AMBIENT[str(root)] = (stamp, core)
        return core
    except Exception:  # noqa: BLE001 - no repository here: the entry is refused, not trusted
        return None


def _records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]] | None:
    records = payload.get("records")
    if not isinstance(records, list) or not records or not all(
            isinstance(r, Mapping) and isinstance(r.get("id"), str) and r.get("hash")
            for r in records):
        return None
    return records


def problem(entry: LogEntry, core: Any, *, known: Mapping[str, Any] | None = None
            ) -> str | None:
    """Why a settled approval or an undone revocation fails its re-check, or None."""
    by = entry.payload.get("by")
    if by == "settled":
        return _settled(entry, core, known)
    if by == "undone":
        return _undone(entry)
    return None


# --------------------------------------------------------------------------- settled


def _settled(entry: LogEntry, core: Any, known: Mapping[str, Any] | None) -> str | None:
    payload = entry.payload
    if entry.kind == "revocation":         # plumb withdrawing a settling: it can only demote
        return None if _records(payload) is not None else (
            "settled revocation names no record at a version")
    if entry.kind != "approval":
        return f"settled {entry.kind}: only an approval is settled"
    records = _records(payload)
    if records is None:
        return "settled approval names no record at a version"
    for key in ("job", "model", "premise_digest", "calibration"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            return f"settled approval does not name its {key.replace('_', ' ')}"
    score = payload.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        return "settled approval carries no score from 0 to 1"
    if core is None:
        core = ambient_core()
    if core is None:
        return f"settled approval cannot be checked here ({owner_text.NOT_AVAILABLE})"
    from plumb.understand import premise, settle

    events = core.events()
    position = next((n for n, e in enumerate(events) if e.digest == entry.digest), None)
    if position is None:
        return ("settled approval is not in the log it is checked against "
                f"({owner_text.NOT_AVAILABLE})")
    before = events[:position]
    index = core.index()
    held = premise.committed(core) if known is None else known
    for item in records:
        record = index.get(str(item["id"]))
        if record is None:
            continue                       # gone: the pin matches nothing
        why = _one(core, entry, before, record, str(item["hash"]), held, settle, premise)
        if why:
            return why
    return None


def _one(core: Any, entry: LogEntry, before: list[LogEntry], record: Any, pinned: str,
         known: Mapping[str, Any], settle: Any, premise: Any) -> str | None:
    payload = entry.payload
    verdict = next((e for e in reversed(before) if e.kind == "verdict"
                    and e.payload.get("job") == payload["job"]
                    and e.payload.get("id") == record.id and e.payload.get("hash") == pinned),
                   None)
    if verdict is None:
        return f"settled {record.id}: no judgment of that job and version is in the log"
    said = verdict.payload
    if said.get("verdict") != "supported":
        return f"settled {record.id}: the judge did not find it supported"
    if float(said.get("score") or 0) != float(payload["score"]) \
            or said.get("model") != payload["model"] \
            or said.get("premise_digest") != payload["premise_digest"]:
        return f"settled {record.id}: the entry differs from the judgment it rests on"
    if record.kind not in settle.KINDS:
        return f"settled {record.id}: a {record.kind} is never settled"
    from plumb.capture.spec import escalated_ids, set_of

    if record.id in escalated_ids(core) or record.id in set_of(core):
        return f"settled {record.id}: a member of an escalated set is never settled"
    if settle.option_picked(core, record):
        return f"settled {record.id}: an option picked among several is never settled"
    config = settle.state_in(before, record.kind)
    if not config.on:
        return f"settled {record.id}: settling was not on for {record.kind}"
    calibration = next((e for e in before if e.kind == "calibration"
                        and e.digest == payload["calibration"]), None)
    if not settle.passing(calibration, settle.claim_kind(record.kind)):
        return f"settled {record.id}: no passing calibration came before it"
    # no statuses: reading confirmations from inside a re-check of them would recurse
    if record.hash == pinned and premise.premise_of(
            core, record, statuses={}, known=known).digest != payload["premise_digest"]:
        return f"settled {record.id}: the words it rests on have changed"
    return None


# --------------------------------------------------------------------------- undone


def _undone(entry: LogEntry) -> str | None:
    payload = entry.payload
    if entry.kind != "revocation":
        return f"undone {entry.kind}: only a revocation is undone"
    if _records(payload) is None:
        return "undone revocation names no record at a version"
    if payload.get("via") not in ("typed", "button"):
        return "undone revocation does not say whether it was typed or a button"
    if entry.marker == "none":
        return None                        # the owner's own terminal or button
    from plumb.approvals import prompt_digest
    from plumb.normalize import sha256_text

    quote, digest = payload.get("quote"), payload.get("prompt_digest")
    if not isinstance(quote, str) or not isinstance(digest, str) \
            or digest not in (prompt_digest(quote), sha256_text(quote)):
        return owner_text.UNDO_REFUSED
    if UNDO.match(quote.strip()) is None:
        return owner_text.UNDO_REFUSED
    return None


def undone_records(core: Any) -> list[tuple[str, str]]:
    """``(record id, hash)`` of the settled records the owner took back, in log order, that
    stand revoked (the revocation passed its re-check)."""
    out: list[tuple[str, str]] = []
    settled: set[tuple[str, str]] = set()
    for entry in core.events():
        if entry.kind == "approval" and entry.payload.get("by") == "settled":
            settled |= {(str(r.get("id")), str(r.get("hash")))
                        for r in entry.payload.get("records") or () if isinstance(r, Mapping)}
        elif entry.kind == "revocation" and entry.payload.get("by") == "undone" \
                and _undone(entry) is None:
            for r in entry.payload.get("records") or ():
                pair = (str(r.get("id")), str(r.get("hash")))
                if isinstance(r, Mapping) and pair in settled and pair not in out:
                    out.append(pair)
    return out
