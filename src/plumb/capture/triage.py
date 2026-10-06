"""Triage: proposed records grouped by faithfulness to the owner's words (R8 A, R13 Q2;
sp2 8.1, SR-040).

Each proposed or edited record is scored with ``JudgmentBackend.entailment``: the premise is
the owner's words it derives from, the hypothesis its restatement. The **low-risk** group
holds the records scored at least ``triage.low_risk_min`` that are not excluded; every other
record is shown individually with its rating. Always individual: a DEC with ``matters:
true``, a member of an escalated set, an edit of a record the owner confirmed before, and a
record with no owner words to compare.

Triage never approves anything by itself. ``plumb triage --approve low-risk`` is the owner's
one step from the owner's own terminal (``approvals.require_owner``) and approves exactly the
listed hashes; in a session, the owner's "ok" to the offer line is relayed with ``plumb relay
--group low-risk``, which approves exactly the group the reply offered (DEC-017).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.contracts import Record, TriageItem, TriageView

if TYPE_CHECKING:
    from plumb.api import Core

GROUP = "low-risk"
OFFER_TITLES = 5          # R13 Q2: name up to about 5 records by title, then "+N more"
JEV_BUDGET_S = 8.0        # scoring new records with JEV on the command line
HOOK_BUDGET_S = 0.6       # a hook scores only what fits; the rest stays unrated


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


def _intent_quotes(index: Mapping[str, Record], record: Record) -> list[str]:
    out = []
    for link in record.links:
        if link.kind == "derives_from" and link.target.record in index:
            parent = index[link.target.record]
            if parent.kind == "intent" and _flat(parent.fields.get("quote")):
                out.append(_flat(parent.fields.get("quote")))
    return out


def claim(index: Mapping[str, Record], record: Record) -> tuple[str, str, str]:
    """``(claim kind, premise, hypothesis)`` of a record (sp2 8.1 step 2)."""
    fields = record.fields
    if record.kind == "intent":
        lines = [_flat(fields.get("readback") or record.title)]
        lines += [f"will: {w}" for w in _items(fields.get("will"))]
        lines += [f"won't: {w}" for w in _items(fields.get("wont"))]
        lines += [f"assumed: {a}" for a in _items(fields.get("assumptions"))]
        return "intent-readback", _flat(fields.get("quote")), "\n".join(lines)
    if record.kind == "requirement":
        premise = _intent_quotes(index, record)
        raw = fields.get("examples") or []
        premise += [_flat(e.get("quote")) for e in raw
                    if isinstance(e, Mapping) and _flat(e.get("quote"))]
        lines = [_flat(fields.get("statement") or record.title)]
        lines += [f"given {e.given}, when {e.when}, then {e.then}" for e in record.examples]
        return "example-restatement", "\n".join(premise), "\n".join(lines)
    if record.kind == "decision":
        premise = [_flat(fields.get("question"))] + _intent_quotes(index, record)
        return ("decision", "\n".join(p for p in premise if p),
                _flat(fields.get("chosen")))
    return record.kind, "", record.title


def exclusion(core: Core, record: Record, statuses: Mapping[str, Any],
              approved_before: set[str], set_members: Mapping[str, str],
              premise: str) -> str | None:
    if record.kind == "decision" and record.fields.get("matters") is True:
        return "a decision that matters"
    if record.id in set_members:
        return f"a member of the escalated spec {set_members[record.id]}"
    if record.kind == "intent" and record.fields.get("mode") == "escalated":
        return "an escalated spec (approved as a set: plumb spec show)"
    if record.id in approved_before or statuses[record.id].confirmation == "unconfirmed-edit":
        return "an edit of a record you confirmed before"
    if not premise.strip():
        return "no owner words to compare"
    return None


def _cache_path(core: Core) -> Any:
    return core.paths.cache / "triage_scores.json"


def _load_cache(core: Core) -> dict[str, list[Any]]:
    try:
        data = json.loads(_cache_path(core).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(core: Core, cache: Mapping[str, Any]) -> None:
    path = _cache_path(core)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def approved_before(core: Core) -> set[str]:
    """Records with any valid approval in the log, by anyone (an edit of them is never
    low-risk, sp2 8.1)."""
    from plumb.confirm import checked_entries

    out: set[str] = set()
    for entry, problem in checked_entries(core.events(), core.config.approve.affirmations):
        if problem is None and entry.kind == "approval":
            out.update(str(r.get("id")) for r in entry.payload.get("records") or []
                       if isinstance(r, Mapping))
    return out


def triage(core: Core, ids: Iterable[str] | None = None, *, backend: Any = None,
           hook: bool = False) -> TriageView:
    """The triage view of the proposed or edited records (all, or ``ids``)."""
    from plumb.capture.spec import set_of

    index = core.index()
    statuses = core.status()
    wanted = [i for i in (ids if ids is not None else sorted(index, key=_order))
              if i in index and statuses[i].confirmation != "confirmed"]
    if backend is None:
        from plumb.judgment import get_backend

        backend = get_backend(core, hook=hook)
    name = str(getattr(backend, "name", "none"))
    available = name not in ("disabled", "none")
    before = approved_before(core)
    members = set_of(core)
    threshold = float(core.config.triage.low_risk_min)
    cache = _load_cache(core)
    deadline = time.monotonic() + (HOOK_BUDGET_S if hook else JEV_BUDGET_S)
    dirty = False
    low: list[TriageItem] = []
    single: list[TriageItem] = []
    for record_id in wanted:
        record = index[record_id]
        kind, premise, hypothesis = claim(index, record)
        excluded = exclusion(core, record, statuses, before, members, premise)
        score: float | None = None
        reason = ""
        used = name
        if available and premise.strip():
            key = f"{name}|{getattr(backend, 'version', '')}|{record.hash}"
            hit = cache.get(key)
            if isinstance(hit, list) and len(hit) == 3:
                score, reason, used = float(hit[0]), str(hit[1]), str(hit[2])
            elif name == "heuristic" or time.monotonic() < deadline:
                judgment = backend.entailment(premise, hypothesis, subject=record_id,
                                              claim_kind=kind)
                probability = judgment.probability
                if probability is not None and judgment.verdict != "unsure" or \
                        judgment.backend == "heuristic":
                    score = float(probability if probability is not None
                                  else judgment.confidence)
                    if judgment.verdict == "not-entailed" and judgment.backend != "heuristic":
                        score = 1.0 - score  # the probability of the not-entailed verdict
                    reason = "; ".join(judgment.reasons)[:200]
                    used = judgment.backend
                    cache[key] = [score, reason, used]
                    dirty = True
        rating = "unrated" if score is None else ("faithful" if score >= threshold
                                                  else "riskier")
        item = TriageItem(id=record_id, hash=record.hash, title=record.title, kind=record.kind,
                          score=None if score is None else round(score, 3),
                          rating=rating, reason=reason, excluded=excluded, backend=used)
        if rating == "faithful" and excluded is None:
            low.append(item)
        else:
            single.append(item)
    if dirty:
        _save_cache(core, cache)
    return TriageView(backend=name, available=available, low_risk=tuple(low),
                      individual=tuple(single), offer=offer_line(low))


def _order(record_id: str) -> tuple[int, int]:
    prefix, _, number = record_id.partition("-")
    rank = {"INT": 0, "SR": 1, "DEC": 2, "FEAT": 3, "NC": 4}.get(prefix, 5)
    return rank, int(number) if number.isdigit() else 0


def offer_line(low: Sequence[TriageItem]) -> str | None:
    """The one-line offer of the end-of-turn summary and the brief (R13 Q2): up to about 5
    records by title, then "+N more (see plumb triage)". The owner's "ok" approves exactly
    the pinned list, which ``plumb triage`` shows in full."""
    if not low:
        return None
    named = ", ".join(f"\"{_clip(i.title)}\" ({i.id})" for i in low[:OFFER_TITLES])
    more = f" +{len(low) - OFFER_TITLES} more (see plumb triage)" if len(low) > OFFER_TITLES \
        else ""
    noun = "record" if len(low) == 1 else "records"
    return (f"plumb: approve the {len(low)} {noun} rated faithful to your words: {named}"
            f"{more}? say \"ok\" or see plumb triage")


def _clip(text: str, width: int = 40) -> str:
    text = _flat(text)
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def stated_group(view: TriageView) -> dict[str, Any] | None:
    """The group the stop hook writes into the stated set with the offer (sp2 C5)."""
    if not view.low_risk:
        return None
    return {"group": GROUP, "records": [{"id": i.id, "hash": i.hash} for i in view.low_risk]}


def view_lines(view: TriageView) -> list[str]:
    lines: list[str] = []
    if not view.available:
        lines.append("plumb triage: no judgments available; every record is shown "
                     "individually")
    else:
        lines.append(f"plumb triage ({view.backend}; advisory, it approves nothing)")
    if view.low_risk:
        lines.append(f"low-risk group: {len(view.low_risk)} records rated faithful to your "
                     "words")
        lines += [f"  {i.id} {i.hash[:19]} {i.score:.2f}  {i.title}" for i in view.low_risk]
        lines.append("  approve them: plumb triage --approve low-risk (your terminal), or "
                     "say \"ok\" to the offer in a session")
    if view.individual:
        lines.append(f"individually: {len(view.individual)} records")
        for item in view.individual:
            rating = item.rating if item.score is None else f"{item.rating} {item.score:.2f}"
            why = f"; {item.excluded}" if item.excluded else ""
            lines.append(f"  {item.id} ({rating}{why})  {item.title}")
    if not view.low_risk and not view.individual:
        lines.append("nothing awaits your confirmation")
    return lines


def log_triage(core: Core, view: TriageView) -> None:
    """A ``triage`` event with the groups shown (for later calibration), only when they
    differ from the last one."""
    from plumb.normalize import canonical_json, sha256_bytes

    payload = {"backend": view.backend,
               "low_risk": [{"id": i.id, "hash": i.hash, "score": i.score}
                            for i in view.low_risk],
               "individual": [{"id": i.id, "hash": i.hash, "score": i.score,
                               "excluded": i.excluded} for i in view.individual]}
    digest = sha256_bytes(canonical_json(payload))
    last = [e for e in core.events() if e.kind == "triage"]
    if last and last[-1].payload.get("digest") == digest:
        return
    core.log_append("events", "triage", {**payload, "digest": digest})
    try:
        path = core.paths.session / "triage.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stated_group(view) or {}), encoding="utf-8")
    except OSError:
        pass


def approve_low_risk(core: Core, *, backend: Any = None, note: str = "",
                     echo: Any = print) -> Any:
    """``plumb triage --approve low-risk``: the owner's one step, from the owner's own
    terminal only. Lists the group with hashes, asks y/N (no flag skips it), then approves
    exactly the listed hashes; a record changed since the listing is left out and named."""
    from plumb.approvals import (
        ApprovalError,
        approval_items,
        refuse_under_marker,
        require_owner,
    )

    refuse_under_marker("triage --approve")
    view = triage(core, backend=backend)
    if not view.low_risk:
        raise ApprovalError("the low-risk group is empty: nothing to approve")
    for item in view.low_risk:
        echo(f"  {item.id} {item.hash[:19]} {item.score:.2f}  {item.title}")
    require_owner("triage --approve", f"approve these {len(view.low_risk)} records at the "
                  "listed content, as yourself (by: owner)?")
    from plumb.api import open_core

    fresh = open_core(core.root)
    index = fresh.index()
    kept = [i for i in view.low_risk if i.id in index and index[i.id].hash == i.hash]
    left_out = [i.id for i in view.low_risk if i not in kept]
    if not kept:
        raise ApprovalError("every listed record changed since the listing: "
                            + ", ".join(left_out))
    payload = {"records": approval_items(fresh, [i.id for i in kept]), "by": "owner",
               "prompt_digest": None, "quote": None, "quote_digest": None,
               "affirmation": None, "stated_set": None, "note": note,
               "triage": {"group": GROUP, "backend": view.backend,
                          "scores": {i.id: i.score for i in kept}, "left_out": left_out}}
    return fresh.log_append("events", "approval", payload)
