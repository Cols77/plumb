"""Triage: proposed records grouped by faithfulness to the owner's words (R8 A, R13 Q2;
sp2 8.1, SR-040).

Each proposed or edited record is scored with ``JudgmentBackend.entailment``: the premise is
the owner's words it derives from, the hypothesis its restatement. The **low-risk** group
holds the records scored at least ``triage.low_risk_min`` that are not excluded; every other
record is shown individually with its rating. Always individual: a DEC with ``matters:
true``, a member of an escalated set, an edit of a record the owner confirmed before, and a
record with no owner words to compare.

The low-risk admission is one choke point: a record joins the group only when its premise
is the owner's verified words (every quote verbatim in a prompt the host's prompt hook
logged; otherwise "quote not verified") and nothing in it contradicts them (a changed
number, a flipped will/won't or result: ``textjudge.contradiction``). Either problem rates
the record "riskier" and shows it individually, whatever the backend scored.

Triage never approves anything by itself. ``plumb triage --approve low-risk`` is the owner's
one step from the owner's own terminal (``approvals.require_owner``) and approves exactly the
listed hashes; in a session, the owner's "ok" to the offer line is relayed with ``plumb relay
--group low-risk``, which approves exactly the group the reply offered (DEC-017).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Mapping, Sequence
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from plumb.capture.records import is_short_answer
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
CONTRADICTS = "contradicts your words"
BEYOND = "goes beyond your words"
CLAIM_VERSION = "claim2"  # the cache key changes when what is judged changes


class _Prompts:
    """The owner's logged prompts, read once per triage: ``text(prefix)`` is the text of the
    hook-logged prompt a record's ``prompt`` digest prefix names, or None (unknown, not
    hashing to its digest, or recorded by the agent itself: ``via`` other than ``hook``)."""

    def __init__(self, core: Core) -> None:
        self.core = core
        self.cache: dict[str, str | None] = {}

    def text(self, prefix: Any) -> str | None:
        key = str(prefix or "").strip()
        if not key:
            return None
        if key not in self.cache:
            from plumb.approvals import Refused, find_prompt

            try:
                entry = find_prompt(self.core, key)
            except Refused:
                entry = None
            ok = entry is not None and entry.get("via") == "hook"
            self.cache[key] = str(entry["text"]) if ok and entry is not None else None
        return self.cache[key]


def _holds(text: str | None, quote: str) -> bool:
    from plumb.approvals import quote_in_prompt
    from plumb.normalize import normalize_text

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


def _offer_path(core: Core) -> Any:
    return core.paths.cache / "triage_offer.json"


def _save_offer(core: Core, low: Sequence[TriageItem]) -> None:
    """The records the last whole triage rated faithful, kept for the session-start brief,
    which must not judge anything itself (a cold start reads this and nothing else)."""
    path = _offer_path(core)
    items = [{"id": i.id, "hash": i.hash, "title": i.title} for i in low]
    try:
        if path.exists() or items:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"items": items}), encoding="utf-8")
    except OSError:
        pass


def cached_offer(core: Core) -> tuple[bool, str | None]:
    """``(known, offer line)`` from the last whole triage, with no judgment: ``known`` is
    False when no triage has run (a cold start), the line is None when nothing it rated
    faithful still awaits (a record since changed or confirmed drops out)."""
    try:
        data = json.loads(_offer_path(core).read_text(encoding="utf-8"))
        raw = data.get("items") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return False, None
    if not isinstance(raw, list):
        return False, None
    index = core.index()
    statuses = core.status() if raw else {}
    left = [SimpleNamespace(id=str(r["id"]), title=str(r.get("title") or ""))
            for r in raw if isinstance(r, Mapping) and r.get("id") in index
            and index[r["id"]].hash == r.get("hash")
            and statuses[r["id"]].confirmation != "confirmed"]
    return True, offer_line(left)  # type: ignore[arg-type]


def approved_before(core: Core) -> set[str]:
    """Records with any valid approval in the log, by anyone (an edit of them is never
    low-risk, sp2 8.1)."""
    from plumb.confirm import checked

    out: set[str] = set()
    for entry, problem in checked(core):
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
    prompts = _Prompts(core)
    for record_id in wanted:
        record = index[record_id]
        kind, premise, hypothesis = claim(index, record, prompts)
        excluded = exclusion(core, record, statuses, before, members, premise)
        # the one low-risk admission (R8 A): the premise must be the owner's verified words
        # and nothing in the record may contradict them, whatever the backend scored
        unfaithful = None if excluded is not None else (
            premise_problem(prompts, index, record) or _contradiction(premise, hypothesis))
        score: float | None = None
        reason = ""
        used = name
        judged_against = False  # the judge itself found the claim contrary to the words
        if available and premise.strip():
            key = f"{CLAIM_VERSION}|{name}|{getattr(backend, 'version', '')}|{record.hash}"
            hit = cache.get(key)
            if isinstance(hit, list) and len(hit) == 4:
                score, reason, used = float(hit[0]), str(hit[1]), str(hit[2])
                judged_against = bool(hit[3])
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
                    judged_against = judgment.verdict in ("contradicts", "contradiction")
                    cache[key] = [score, reason, used, judged_against]
                    dirty = True
        rating = "unrated" if score is None else ("faithful" if score >= threshold
                                                  else "riskier")
        if unfaithful is None and judged_against and excluded is None:
            unfaithful = f"{CONTRADICTS}: the judge found it contrary to them"
        outcome = _outcome(rating, unfaithful)
        if unfaithful is not None:
            rating, excluded = "riskier", unfaithful
        item = TriageItem(id=record_id, hash=record.hash, title=record.title, kind=record.kind,
                          score=None if score is None else round(score, 3),
                          rating=rating, outcome=outcome, reason=reason, excluded=excluded,
                          backend=used)
        if rating == "faithful" and excluded is None:
            low.append(item)
        else:
            single.append(item)
    if dirty:
        _save_cache(core, cache)
    if ids is None:
        _save_offer(core, low)
    return TriageView(backend=name, available=available, low_risk=tuple(low),
                      individual=tuple(single), offer=offer_line(low))


def _outcome(rating: str, unfaithful: str | None) -> str:
    """What the judgment says of the record, in the owner's terms: ``faithful`` (the owner's
    words support it), ``contradicts`` (they say otherwise), ``beyond`` (it goes beyond
    them: not supported, not contradicted), ``unverified`` (the quote is not the owner's
    verified words) or ``unrated``."""
    if unfaithful is not None:
        return "contradicts" if unfaithful.startswith(CONTRADICTS) else "unverified"
    return {"faithful": "faithful", "riskier": "beyond"}.get(rating, "unrated")


def outcome_words(item: TriageItem) -> str:
    """The outcome of a triage item in words (never a probability next to a risk)."""
    outcome = getattr(item, "outcome", "") or {"faithful": "faithful",
                                               "riskier": "riskier"}.get(item.rating, "")
    return {"faithful": "faithful to your words", "contradicts": CONTRADICTS,
            "beyond": BEYOND, "unverified": UNVERIFIED,
            "unrated": "not rated"}.get(outcome, outcome or item.rating)


def _contradiction(premise: str, hypothesis: str) -> str | None:
    """A changed number or a flipped will/won't or result against the owner's words
    (``textjudge.contradiction``: the "no" cases of R13 Q1, which the calibration's
    ``variations`` generate)."""
    from plumb.judgment.textjudge import contradiction

    problem = contradiction(premise, hypothesis)
    return None if problem is None else f"{CONTRADICTS}: {problem}"


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
        lines += [f"  {i.id} {i.hash[:19]}  {i.title}" for i in view.low_risk]
        lines.append("  approve them: plumb triage --approve low-risk (your terminal), or "
                     "say \"ok\" to the offer in a session")
    if view.individual:
        lines.append(f"individually: {len(view.individual)} records")
        for item in view.individual:
            words = outcome_words(item)
            kept = item.excluded and not item.excluded.startswith(words)
            why = f"; {item.excluded}" if kept else ""
            lines.append(f"  {item.id} ({words}{why})  {item.title}")
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
        echo(f"  {item.id} {item.hash[:19]}  {item.title}")
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
