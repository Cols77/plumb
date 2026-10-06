"""Single-record helpers (sp2 5.2, SR-035): ``plumb new``, ``intent``, ``example`` and
``decide``.

Every record is written through ``CoreAPI.write_record`` (IDs only through ``Store.next_id``,
the one choke point sub-project 6 replaces) and every link through ``CoreAPI.add_link``, so
links are pinned at once. Nothing here confirms anything: every record is ``proposed``, and an
edit of a confirmed record is an unconfirmed edit (sp1 5.6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.contracts import KIND_PREFIX, Record, Target
from plumb.model import link_to_dict

if TYPE_CHECKING:
    from plumb.api import Core

KINDS = tuple(KIND_PREFIX)
TITLE_WIDTH = 70


class CaptureError(ValueError):
    """A capture request that cannot be written (exit 2); nothing was written."""


def short_title(text: str, width: int = TITLE_WIDTH) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= width:
        return text
    cut = text[: width - 3].rsplit(" ", 1)[0]
    return (cut or text[: width - 3]) + "..."


def _clean_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    return [" ".join(str(v).split()) for v in values if str(v).strip()]


def record_fields(record: Record) -> dict[str, Any]:
    """The writable frontmatter of ``record``: title, its fields and its links."""
    fields: dict[str, Any] = {"title": record.title, **dict(record.fields)}
    if record.links:
        fields["links"] = [link_to_dict(link) for link in record.links]
    return fields


def rewrite(core: Core, record: Record, changes: Mapping[str, Any]) -> Record:
    """Rewrite ``record`` with ``changes`` applied, keeping its links and body; the links
    whose only moved end is this record are repinned (``repin`` event, never a
    confirmation)."""
    fields = record_fields(record)
    fields.update(changes)
    updated = core.write_record(record.kind, fields, record.body, record_id=record.id)
    repin_own_source(core, updated.id)
    return core.index()[updated.id]


def repin_own_source(core: Core, record_id: str) -> list[dict[str, Any]]:
    """Repin the links of ``record_id`` that are stale only because the record itself
    changed (plumb wrote it); a moved target stays stale."""
    from plumb.links import repin

    states = core.link_states([record_id])
    moved = [s.link.index for s in states if s.state == "stale" and s.moved == "source"]
    changes: list[dict[str, Any]] = []
    for position in moved:
        changes += repin(core, f"{record_id}#{position}",
                         note="plumb capture: the record was edited by plumb")
    return changes


def new_record(core: Core, kind: str, fields: Mapping[str, Any], body: str = "", *,
               derives_from: Sequence[str] = ()) -> Record:
    """``plumb new <kind>``: one record with the next ID, proposed."""
    if kind not in KINDS:
        raise CaptureError(f"unknown kind {kind!r} (one of {', '.join(KINDS)})")
    title = short_title(str(fields.get("title") or ""))
    if not title:
        raise CaptureError("a record needs a title")
    index = core.index()
    for parent in derives_from:
        if parent not in index:
            raise CaptureError(f"no record {parent}")
    record = core.write_record(kind, {**fields, "title": title}, body)  # type: ignore[arg-type]
    for parent in derives_from:
        core.add_link(record.id, "derives_from", Target(record=parent))
    return core.index()[record.id]


def intent_fields(quote: str, readback: str, *, will: Any = (), wont: Any = (),
                  assumptions: Any = (), mode: str = "incremental", title: str = "",
                  members: Sequence[str] = (), prompt: str | None = None) -> dict[str, Any]:
    quote = str(quote or "").strip()
    if not quote:
        raise CaptureError("an intent needs the owner's verbatim words (quote)")
    if mode not in ("incremental", "escalated"):
        raise CaptureError("mode is incremental or escalated")
    fields: dict[str, Any] = {
        "title": short_title(title or readback or quote), "quote": quote,
        "readback": " ".join(str(readback or quote).split()),
        "will": _clean_list(will), "wont": _clean_list(wont),
        "assumptions": _clean_list(assumptions), "mode": mode}
    if members:
        fields["members"] = list(members)
    if prompt:
        fields["prompt"] = prompt.removeprefix("sha256:")[:16]
    return fields


def write_intent(core: Core, quote: str, readback: str, **kwargs: Any) -> Record:
    """``plumb intent``: an INT holding the owner's words and their read-back."""
    return new_record(core, "intent", intent_fields(quote, readback, **kwargs))


def example_entry(example_id: str, given: str, when: str, then: str,
                  quote: str | None = None, prompt: str | None = None) -> dict[str, Any]:
    if not (given or when or then):
        raise CaptureError("an example needs given, when and then")
    entry: dict[str, Any] = {"id": example_id, "given": " ".join(str(given).split()),
                             "when": " ".join(str(when).split()),
                             "then": " ".join(str(then).split())}
    if quote:
        entry["quote"] = " ".join(str(quote).split())
        if prompt:  # checked against that logged prompt (R8 A: triage verifies it again)
            entry["prompt"] = prompt.removeprefix("sha256:")[:16]
    return entry


def next_example_id(raw: Sequence[Mapping[str, Any]]) -> str:
    numbers = [int(str(e.get("id", ""))[3:]) for e in raw
               if str(e.get("id", "")).startswith("EX-") and str(e.get("id", ""))[3:].isdigit()]
    return f"EX-{(max(numbers) + 1) if numbers else 1}"


def add_example(core: Core, sr_id: str, given: str, when: str, then: str,
                quote: str | None = None, prompt: str | None = None) -> tuple[Record, str]:
    """``plumb example SR-###``: append ``EX-n``; returns the record and the example ID."""
    record = core.index().get(sr_id)
    if record is None or record.kind != "requirement":
        raise CaptureError(f"no requirement {sr_id}")
    raw = [dict(e) for e in record.fields.get("examples") or [] if isinstance(e, Mapping)]
    example_id = next_example_id(raw)
    raw.append(example_entry(example_id, given, when, then, quote, prompt))
    return rewrite(core, record, {"examples": raw}), example_id


def decide(core: Core, question: str, chosen: str, alternatives: Sequence[str], *,
           matters: bool = False, recommended: str | None = None,
           decides: Sequence[str] = (), derives_from: Sequence[str] = (),
           supersede: str | None = None, rationale: str = "", title: str = "") -> Record:
    """``plumb decide``: "I assumed A; B also fits" as a DEC. With ``supersede``, a new DEC
    with a ``supersedes`` link; the superseded decision is never edited in place."""
    index = core.index()
    old = None
    if supersede is not None:
        old = index.get(supersede)
        if old is None or old.kind != "decision":
            raise CaptureError(f"no decision {supersede}")
        question = question or str(old.fields.get("question") or old.title)
        if not alternatives:
            previous = str(old.fields.get("chosen") or "")
            alternatives = [previous] if previous and previous != chosen else []
    question = " ".join(str(question or "").split())
    chosen = " ".join(str(chosen or "").split())
    if not question or not chosen:
        raise CaptureError("a decision needs a question and the chosen option")
    alts = _clean_list(alternatives)
    if recommended is not None and recommended not in [chosen, *alts]:
        raise CaptureError("the recommended option must be the chosen one or an alternative")
    for target in [*decides, *derives_from]:
        if target not in index:
            raise CaptureError(f"no record {target}")
    fields: dict[str, Any] = {"title": short_title(title or question), "question": question,
                              "chosen": chosen, "alternatives": alts, "matters": bool(matters)}
    if rationale:
        fields["rationale"] = " ".join(rationale.split())
    if recommended is not None:
        fields["recommended"] = recommended
    record = core.write_record("decision", fields)
    for target in derives_from:
        core.add_link(record.id, "derives_from", Target(record=target))
    for target in decides:
        core.add_link(record.id, "decides", Target(record=target))
    if old is not None:
        core.add_link(record.id, "supersedes", Target(record=old.id))
        for link in old.links:  # the new decision decides what the old one decided
            if link.kind in ("decides", "derives_from") and link.target.record and \
                    link.target.record not in [*decides, *derives_from]:
                core.add_link(record.id, link.kind, Target(record=link.target.record))
    return core.index()[record.id]
