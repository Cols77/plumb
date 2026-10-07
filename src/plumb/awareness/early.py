"""The EARLY intent-conflict check, at capture and read-back time (ruling R17, SR-081).

Conflicts are caught when intent is captured, not at merge, so two branches never build two
incompatible versions of one requirement. ``plumb capture`` (after its records are written)
and ``plumb clarify`` (before anything is written) compare this work with the intent other
branches have in flight (``refs/plumb/claims``):

- the SAME record claimed on another branch is a conflict, caught deterministically;
- new intent in a feature another branch claims is judged for compatibility by the judgment
  backend (``contradiction``: JEV when configured, else the heuristic); ``contradicts`` is a
  conflict, anything else a one-line awareness warning.

A conflict is the owner's "real intent change" trigger: an early conflict card ("feat-x says
A, this request says B: which one, or both?") is shown at once, and ``capture`` records it
ONCE as a proposed decision that matters (a DEC deciding the record), noted in this branch's
claim so every other branch sees the question and, through ``inflight.sync_decisions``, the
owner's answer. A conflict another branch already raised is never raised twice: the line
names it, and the owner's answer once given. Nothing here refuses or holds anything.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from plumb.awareness import inflight
from plumb.present import owner_text as text


@dataclass(frozen=True)
class EarlyConflict:
    record: str
    title: str
    branch: str                      # the other branch
    claim: str                       # the other branch's claim ID
    theirs: str                      # the other branch's version, in the owner's words
    ours: str                        # this request's version
    judgment: str = ""               # "" for the same record (deterministic)


@dataclass
class EarlyCheck:
    conflicts: list[EarlyConflict] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)     # warnings and known conflicts


def _clip(value: str, width: int = 160) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= width else value[: width - 3].rstrip() + "..."


def _synthetic(record_id: str, title: str, statement: str) -> Any:
    from plumb.contracts import Record

    return Record(id=record_id, kind="requirement", title=title, path="",
                  fields={"statement": statement}, body="", links=())


def _backend(core: Any, backend: Any) -> Any:
    if backend is not None:
        return backend
    try:
        from plumb.judgment import get_backend

        return get_backend(core, hook=False)
    except Exception:  # noqa: BLE001 - no backend: overlaps stay warnings
        return None


def _known(my_branch: str | None, claims: Sequence[Mapping[str, Any]],
           record_id: str, other: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """A conflict on ``record_id`` between this branch and ``other``'s branch that either
    side already raised."""
    for claim in claims:
        for conflict in claim.get("conflicts") or []:
            if conflict.get("record") != record_id:
                continue
            pair = {claim.get("branch"), conflict.get("branch")}
            if pair == {my_branch, other.get("branch")}:
                return {**conflict, "raised_on": claim.get("branch")}
    return None


def known_line(record_id: str, title: str, known: Mapping[str, Any]) -> str:
    """The one line every surface (capture, the clarify read-back, the session brief, the
    prompt delta) shows for a conflict already raised: asked on that branch, or the owner's
    answer, always in branch-neutral words (``inflight.neutral_chosen``)."""
    branch = str(known.get("raised_on") or known.get("branch") or "")
    chosen = inflight.neutral_chosen(str(known.get("chosen") or ""), branch)
    if known.get("state") == "confirmed" and chosen:
        return text.EARLY_SETTLED.format(id=record_id, title=title, branch=branch,
                                         chosen=_clip(chosen, 120))
    return text.EARLY_KNOWN.format(id=record_id, title=title, branch=branch)


def _all_claims(core: Any) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """``(this branch, other branches' active claims, every active claim)``."""
    from plumb.awareness.publish import default_branch

    my_branch, others = inflight.others(core, allow_git=True)
    _oid, data = inflight.read(core.root, allow_git=True)
    every = inflight.active(core.root, data, default=default_branch(core), allow_git=True)
    return my_branch, others, every


def check_records(core: Any, mine: Sequence[Any], *, ours: Mapping[str, str] | None = None,
                  new: Iterable[str] = (), planned: Iterable[str] = (),
                  backend: Any = None) -> EarlyCheck:
    """``mine``: this work's records (``Record``). ``ours``: each record's version in the
    owner's words (default: its statement); ``new``: the IDs this work created (only those
    are judged by feature: an existing record is matched by ID); ``planned``: the IDs whose
    new version is only planned (a preview), so ``mine`` holds their old version."""
    result = EarlyCheck()
    my_branch, claims, every = _all_claims(core)
    if not claims:
        return result
    new_set = set(new)
    planned = set(planned)
    ours = dict(ours or {})
    judge = None
    for record in mine:
        our_text = ours.get(record.id) or inflight.record_entry(record)["text"]
        feature = str((record.fields or {}).get("feature") or "")
        for claim in claims:
            entry = (claim.get("records") or {}).get(record.id)
            if entry is not None and record.id not in new_set:
                if _same_version(entry, record, planned=record.id in planned):
                    continue  # both branches hold the same version: nothing to choose
                known = _known(my_branch, every, record.id, claim)
                if known is not None:
                    result.lines.append(known_line(record.id, record.title, known))
                    continue
                result.conflicts.append(EarlyConflict(
                    record=record.id, title=record.title, branch=str(claim["branch"]),
                    claim=str(claim.get("id")), theirs=str(entry.get("text") or
                                                          claim.get("summary") or ""),
                    ours=our_text))
                continue
            if record.id in new_set and feature and feature in (claim.get("features") or []):
                judge = judge if judge is not None else _backend(core, backend)
                theirs = "; ".join(str(e.get("text") or "") for e in
                                   (claim.get("records") or {}).values()
                                   if isinstance(e, Mapping) and e.get("feature") == feature)
                theirs = theirs or str(claim.get("summary") or "")
                verdict, why = _judge(judge, theirs, record)
                if verdict == "contradicts":
                    known = _known(my_branch, every, record.id, claim)
                    if known is not None:
                        result.lines.append(known_line(record.id, record.title, known))
                        continue
                    result.conflicts.append(EarlyConflict(
                        record=record.id, title=record.title, branch=str(claim["branch"]),
                        claim=str(claim.get("id")), theirs=_clip(theirs, 240), ours=our_text,
                        judgment=why))
                else:
                    result.lines.append(text.EARLY_COMPATIBLE.format(
                        id=record.id, title=record.title, branch=claim["branch"],
                        summary=_clip(str(claim.get("summary") or ""), 80)))
    return result


def _same_version(entry: Mapping[str, Any], record: Any, *, planned: bool) -> bool:
    """The other branch's claimed version IS this one: the same record hash (every field,
    examples and title included, and the whole statement), never the clipped words a claim
    keeps for the card. A version only planned (a preview: not written, so not hashed) is
    never the same."""
    if planned:
        return False
    theirs = str(entry.get("hash") or "")
    return bool(theirs) and theirs == str(getattr(record, "hash", "") or "")


def _judge(backend: Any, theirs: str, record: Any) -> tuple[str, str]:
    """The backend's compatibility verdict on ``record`` against the other branch's words:
    ``(verdict, the card's "Compatible?" text)``."""
    if backend is None:
        return "unsure", "no judgment available"
    try:
        judgment = backend.contradiction(theirs, record)
    except Exception:  # noqa: BLE001 - advisory
        return "unsure", "no judgment available"
    verdict = str(getattr(judgment, "verdict", "unsure"))
    name = str(getattr(judgment, "backend", "") or getattr(backend, "name", ""))
    confidence = float(getattr(judgment, "confidence", 0.0) or 0.0)
    label = {"contradicts": "likely not", "extends": "likely yes (it adds beside it)",
             "benign": "likely yes"}.get(verdict, "unsure")
    who = "JEV" if name == "jev" else ("a quick word check" if name == "heuristic" else name)
    return verdict, f"{label} ({who}, {confidence:.2f})"


def check_text(core: Any, request: str, *, backend: Any = None) -> EarlyCheck:
    """The read-back check of ``plumb clarify``: the records the request names or strongly
    matches, against other branches' claims, before anything is written."""
    from plumb.query import _ID_IN_TEXT

    result = EarlyCheck()
    my_branch, claims, every = _all_claims(core)
    if not claims or not request.strip():
        return result
    index = core.index()
    named = [i for i in _ID_IN_TEXT.findall(request) if i in index]
    ranked = [i for i, score in core.relevant(request, 5) if score >= 1.0]
    ids = list(dict.fromkeys([*named, *ranked]))
    features = {str(index[i].fields.get("feature")) for i in ids
                if index[i].fields.get("feature")}
    features |= {i for i in ids if index[i].kind == "feature"}
    ours = _clip(request, 240)
    judge = None
    for claim in claims:
        records = claim.get("records") or {}
        same = [i for i in ids if i in records]
        for record_id in same:
            known = _known(my_branch, every, record_id, claim)
            if known is not None:
                result.lines.append(known_line(record_id, index[record_id].title, known))
                continue
            result.conflicts.append(EarlyConflict(
                record=record_id, title=index[record_id].title, branch=str(claim["branch"]),
                claim=str(claim.get("id")), theirs=str(records[record_id].get("text") or ""),
                ours=ours))
        if same:
            continue
        shared = features & set(claim.get("features") or [])
        if not shared:
            continue
        judge = judge if judge is not None else _backend(core, backend)
        for record_id, entry in sorted(records.items()):
            if not isinstance(entry, Mapping) or entry.get("feature") not in shared:
                continue
            synthetic = _synthetic(record_id, str(entry.get("title") or ""),
                                   str(entry.get("text") or ""))
            verdict, why = _judge(judge, request, synthetic)
            title = str(entry.get("title") or record_id)
            if verdict == "contradicts":
                result.conflicts.append(EarlyConflict(
                    record=record_id, title=title, branch=str(claim["branch"]),
                    claim=str(claim.get("id")), theirs=str(entry.get("text") or ""),
                    ours=ours, judgment=why))
            else:
                result.lines.append(text.EARLY_COMPATIBLE.format(
                    id=record_id, title=title, branch=claim["branch"],
                    summary=_clip(str(claim.get("summary") or ""), 80)))
    return result


def card(conflict: EarlyConflict) -> list[str]:
    """The early intent-conflict card, in the owner's terms (R9 card format, sp5 4.2)."""
    return [text.EARLY_CARD_HEAD.format(id=conflict.record, title=conflict.title),
            text.EARLY_CARD_SIDE.format(label=conflict.branch, text=_clip(conflict.theirs)),
            text.EARLY_CARD_SIDE.format(label="this work", text=_clip(conflict.ours)),
            text.EARLY_CARD_JUDGED.format(judgment=conflict.judgment or text.EARLY_CARD_SAME),
            text.EARLY_CARD_SAY.format(branch=conflict.branch)]


def question(conflict: EarlyConflict) -> str:
    return text.EARLY_QUESTION.format(branch=conflict.branch, theirs=_clip(conflict.theirs, 160),
                                      ours=_clip(conflict.ours, 160))


def raise_conflicts(core: Any, conflicts: Sequence[EarlyConflict], *,
                    intent: str | None) -> list[dict[str, Any]]:
    """Record each conflict once as a proposed decision that matters (it decides the
    record); returns the claim's conflict entries."""
    from plumb.awareness import gitfiles
    from plumb.capture.records import decide

    index = core.index()
    me = gitfiles.current(core.root)
    mine = (text.EARLY_THEIRS.format(branch=me.branch) if me is not None and me.branch
            else "the version captured with this decision")
    entries: list[dict[str, Any]] = []
    for conflict in conflicts:
        derives = [intent] if intent and intent in index else []
        decides = [conflict.record] if conflict.record in index else []
        if not decides and not derives:
            continue
        theirs = text.EARLY_THEIRS.format(branch=conflict.branch)
        record = decide(core, question(conflict), mine,
                        [theirs, text.EARLY_BOTH], matters=True, decides=decides,
                        derives_from=derives,
                        rationale=(f"Raised at capture (R17): branch {conflict.branch} has "
                                   f"this requirement in flight; asked once for both."),
                        title=f"{conflict.record} {conflict.title}: which version holds")
        index = core.index()
        entries.append({"record": conflict.record, "branch": conflict.branch,
                        "with": conflict.claim, "dec": record.id,
                        "question": record.fields.get("question", ""), "state": "proposed",
                        "chosen": ""})
    return entries


def after_capture(core: Any, *, written: Sequence[str], updated: Sequence[str],
                  intent: str | None, summary: str = "", dry_run: bool = False,
                  backend: Any = None) -> list[str]:
    """``plumb capture``'s check (R17): compare this capture with other branches' intent in
    flight, show each conflict as an early card, record it once as a DEC and record this
    branch's claim (nothing is recorded on a dry run). Returns the lines to print."""
    index = core.index()
    ids = [i for i in [*updated, *written] if i in index]
    if not ids:
        return []
    mine = [index[i] for i in ids if index[i].kind != "decision"]
    result = check_records(core, mine, new=written, backend=backend)
    lines: list[str] = []
    for conflict in result.conflicts:
        lines += card(conflict)
    lines += result.lines
    if dry_run:
        return [*lines, text.EARLY_DRY_RUN] if lines else []
    entries = raise_conflicts(core, result.conflicts, intent=intent)
    for entry in entries:
        lines.append(text.EARLY_RECORDED.format(id=entry["record"],
                                                title=index[entry["record"]].title
                                                if entry["record"] in index else ""))
        lines.append(text.EARLY_ASK.format(dec=entry["dec"]))
    claimed = {i: inflight.record_entry(index[i]) for i in ids
               if index[i].kind in ("requirement", "intent", "feature")}
    if not summary and intent and intent in index:
        summary = index[intent].title
    try:
        inflight.record_claim(core, records=claimed, summary=summary or "", intent=intent,
                              conflicts=entries)
    except inflight.InflightBusy:
        lines.append(text.INFLIGHT_BUSY)
    return lines


def preview(core: Any, requirements: Sequence[Mapping[str, Any]],
            updates: Sequence[tuple[str, Mapping[str, Any]]], *, backend: Any = None
            ) -> list[str]:
    """A dry run's check, from the plan alone (nothing is written or recorded)."""
    index = core.index()
    mine: list[Any] = []
    ours: dict[str, str] = {}
    new: list[str] = []
    planned: list[str] = []
    for record_id, changes in updates:
        if record_id in index:
            mine.append(index[record_id])
            planned.append(record_id)
            words = changes.get("statement") or changes.get("readback") or changes.get("title")
            if words:
                ours[record_id] = _clip(str(words), 240)
    for n, item in enumerate(requirements, start=1):
        fields = dict(item.get("fields") or {})
        record_id = f"SR-new{n}"
        mine.append(_synthetic(record_id, str(fields.get("title") or ""),
                               str(fields.get("statement") or "")))
        if fields.get("feature"):
            mine[-1] = _with_feature(mine[-1], str(fields["feature"]))
        new.append(record_id)
    result = check_records(core, mine, ours=ours, new=new, planned=planned, backend=backend)
    lines = [line for conflict in result.conflicts for line in card(conflict)] + result.lines
    return [*lines, text.EARLY_DRY_RUN] if lines else []


def _with_feature(record: Any, feature: str) -> Any:
    import dataclasses

    return dataclasses.replace(record, fields={**record.fields, "feature": feature})
