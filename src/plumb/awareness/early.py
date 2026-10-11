"""The EARLY intent-conflict check, at capture and read-back time (ruling R17, SR-081).

Conflicts are caught when intent is captured, not at merge, so two branches never build two
incompatible versions of one requirement. ``plumb clarify`` (before anything is written)
and every write of this branch's claim (``claim``: ``plumb capture``, and the stop hook after
a direct edit or ``plumb new``) compare this work with the intent other branches have in
flight (``refs/plumb/claims``, and the default branch's changes since this branch started
from it: ``inflight.since_fork``, so a claim cleared by landing still reaches a branch that
holds the words it replaced):

- the SAME record claimed on another branch is a conflict, caught deterministically;
- new intent in a feature another branch claims is judged for compatibility by the judgment
  backend (``contradiction``: the configured judge); ``contradicts`` is a
  conflict, anything else a one-line awareness warning.

A conflict is the owner's "real intent change" trigger: an early conflict card ("feat-x says
A, this request says B: which one, or both?") is shown at once, and ``claim`` records it
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
    theirs_hash: str = ""            # the other branch's version of the record, when claimed
    ours_label: str = ""             # "" (this work) or, off both branches, the 2nd branch


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
        from plumb.judgment import optional_backend

        return optional_backend(core, hook=False)
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
    every = inflight.active(core.root, data, default=default_branch(core), allow_git=True,
                            paths=inflight.record_paths(core))
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
                if _not_changed_here(claim, entry, record, planned=record.id in planned):
                    continue  # this branch still holds the version the default replaced
                known = _known(my_branch, every, record.id, claim)
                if known is not None:
                    result.lines.append(known_line(record.id, record.title, known))
                    continue
                result.conflicts.append(EarlyConflict(
                    record=record.id, title=record.title, branch=str(claim["branch"]),
                    claim=str(claim.get("id")), theirs=str(entry.get("text") or
                                                          claim.get("summary") or ""),
                    ours=our_text, theirs_hash=str(entry.get("hash") or "")))
                continue
            if record.id in new_set and feature and feature in (claim.get("features") or []):
                judge = judge if judge is not None else _backend(core, backend)
                theirs = "; ".join(str(e.get("text") or "") for e in
                                   (claim.get("records") or {}).values()
                                   if isinstance(e, Mapping) and e.get("feature") == feature)
                theirs = theirs or str(claim.get("summary") or "")
                verdict, why, sure = _judge(judge, theirs, record)
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
                    result.lines.append(overlap_line(
                        record.id, record.title, str(claim["branch"]),
                        str(claim.get("summary") or ""), theirs, our_text, why, sure))
    return result


def overlap_line(record_id: str, title: str, branch: str, summary: str, theirs: str,
                 ours: str, why: str, sure: bool) -> str:
    """The one line for an overlap judged not contradictory (R17, R12), wherever it is
    checked (capture, the clarify read-back): "judged compatible, nothing to ask" only on a
    confident JEV verdict; a word check, an unsure verdict or no judgment names both
    versions so the agent can still ask."""
    if sure:
        return text.EARLY_COMPATIBLE.format(id=record_id, title=title, branch=branch,
                                            summary=_clip(summary, 80))
    who = why[why.find("(") + 1:why.rfind(")")] if "(" in why else why
    return text.EARLY_UNJUDGED.format(id=record_id, title=title, branch=branch,
                                      who=who or "no judgment available",
                                      theirs=_clip(theirs, 120), ours=_clip(ours, 120))


def _not_changed_here(claim: Mapping[str, Any], entry: Mapping[str, Any], record: Any, *,
                      planned: bool) -> bool:
    """A change the default branch made after this branch started (``inflight.fork_claim``)
    is a conflict only when this work changes the record too: a record still at the version
    this branch started from is merely behind (its new version, only planned, always
    counts)."""
    if planned or not claim.get("since_fork"):
        return False
    return bool(entry.get("base")) and entry.get("base") == str(getattr(record, "hash", ""))


def _same_version(entry: Mapping[str, Any], record: Any, *, planned: bool) -> bool:
    """The other branch's claimed version IS this one: the same record hash (every field,
    examples and title included, and the whole statement), never the clipped words a claim
    keeps for the card. A version only planned (a preview: not written, so not hashed) is
    never the same."""
    if planned:
        return False
    theirs = str(entry.get("hash") or "")
    return bool(theirs) and theirs == str(getattr(record, "hash", "") or "")


# a JEV verdict at or above this confidence may say "compatible" on its own (R12, R17)
CONFIDENT = 0.8


def _judge(backend: Any, theirs: str, record: Any) -> tuple[str, str, bool]:
    """The backend's compatibility verdict on ``record`` against the other branch's words:
    ``(verdict, the card's "Compatible?" text, whether the verdict is confident)``. Only
    JEV, above ``CONFIDENT`` and not escalating, is confident; no rule-based judge stands in
    for an unreachable one (INT-029): the card says why it could not judge."""
    if backend is None:
        return "unsure", "no judgment available", False
    try:
        judgment = backend.contradiction(theirs, record)
    except Exception as exc:  # noqa: BLE001 - advisory
        from plumb.judgment import JudgmentUnavailable

        if isinstance(exc, JudgmentUnavailable):
            return "unsure", f"judging unavailable: {exc}", False
        return "unsure", "no judgment available", False
    verdict = str(getattr(judgment, "verdict", "unsure"))
    name = str(getattr(judgment, "backend", "") or getattr(backend, "name", ""))
    confidence = float(getattr(judgment, "confidence", 0.0) or 0.0)
    label = {"contradicts": "likely not", "extends": "likely yes (it adds beside it)",
             "benign": "likely yes"}.get(verdict, "unsure")
    jev = name == "jev" or name.startswith("jev:")
    who = "JEV" if jev else name
    tier = str(getattr(judgment, "tier", "") or "")
    sure = jev and confidence >= CONFIDENT and not tier.startswith("escalate")
    return verdict, f"{label} ({who}, {confidence:.2f})", sure


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
        if claim.get("since_fork"):     # this checkout already took the default's version
            same = [i for i in same if index[i].hash != records[i].get("hash")]
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
            verdict, why, sure = _judge(judge, request, synthetic)
            title = str(entry.get("title") or record_id)
            if verdict == "contradicts":
                result.conflicts.append(EarlyConflict(
                    record=record_id, title=title, branch=str(claim["branch"]),
                    claim=str(claim.get("id")), theirs=str(entry.get("text") or ""),
                    ours=ours, judgment=why))
            else:
                result.lines.append(overlap_line(
                    record_id, title, str(claim["branch"]), str(claim.get("summary") or ""),
                    str(entry.get("text") or ""), ours, why, sure))
    return result


def card(conflict: EarlyConflict) -> list[str]:
    """The early intent-conflict card, in the owner's terms (R9 card format, sp5 4.2). On a
    branch that is neither side (``ours_label`` names the second branch) both versions are
    labelled by branch and the answer names a branch, never "this one"."""
    say = (text.EARLY_CARD_SAY_NAMED.format(a=conflict.branch, b=conflict.ours_label)
           if conflict.ours_label else text.EARLY_CARD_SAY.format(branch=conflict.branch))
    return [text.EARLY_CARD_HEAD.format(id=conflict.record, title=conflict.title),
            text.EARLY_CARD_SIDE.format(label=conflict.branch, text=_clip(conflict.theirs)),
            text.EARLY_CARD_SIDE.format(label=conflict.ours_label or "this work",
                                        text=_clip(conflict.ours)),
            text.EARLY_CARD_JUDGED.format(judgment=conflict.judgment or text.EARLY_CARD_SAME),
            say]


REQUESTED_FILE = "early-requested.json"


def request_cards(core: Any, conflicts: Sequence[EarlyConflict]) -> None:
    """Ask the stop hook to show these cards to the owner at the end of the turn and to put
    them in the stated set (``turn_cards``), so the owner's answer ("keep feat-x's") is
    relayed against a card the owner saw, even when nothing is written yet (the clarify
    read-back)."""
    if not conflicts:
        return
    import json
    import os

    from plumb.normalize import utc_now

    path = core.paths.session / REQUESTED_FILE
    now = utc_now()
    cards = [{"record": c.record, "title": c.title, "branch": c.branch, "claim": c.claim,
              "theirs": c.theirs, "ours": c.ours, "judgment": c.judgment,
              "theirs_hash": c.theirs_hash, "ours_label": c.ours_label, "at": now}
             for c in conflicts]
    # several steps of one turn may ask (the clarify read-back, capture, the stop hook's
    # claim): each card keeps its own time, and a newer one of the same pair replaces it
    fresh = {(c["record"], c["branch"]) for c in cards}
    kept = [c for c in requested(core.paths.session)
            if (c.get("record"), c.get("branch")) not in fresh][-20:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"at": now, "cards": [*kept, *cards]}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def turn_cards(session_dir: Any, turn_start: str = "") -> tuple[list[str], list[dict[str, Any]]]:
    """``(lines, stated entries)``: the early cards ``capture`` or ``clarify`` asked for this
    turn, for the stop hook's reply. Reads one small session file; never fails."""
    lines: list[str] = []
    entries: list[dict[str, Any]] = []
    for conflict in turn_conflicts(session_dir, turn_start):
        lines += card(conflict)
        entries.append(stated_entry(conflict))
    return lines, entries


def turn_conflicts(session_dir: Any, turn_start: str = "") -> list[EarlyConflict]:
    """The early conflicts ``capture`` or ``clarify`` asked for this turn (the stop hook draws
    each as an ``early_conflict`` card). Reads one small session file; never fails."""
    import json
    from pathlib import Path

    try:
        data = json.loads((Path(session_dir) / REQUESTED_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, Mapping) or str(data.get("at") or "") < turn_start:
        return []
    out: list[EarlyConflict] = []
    for item in data.get("cards") or []:
        if not isinstance(item, Mapping) or not item.get("record"):
            continue
        if str(item.get("at") or data.get("at") or "") < turn_start:
            continue  # asked in an earlier turn
        out.append(EarlyConflict(
            record=str(item["record"]), title=str(item.get("title") or ""),
            branch=str(item.get("branch") or ""), claim=str(item.get("claim") or ""),
            theirs=str(item.get("theirs") or ""), ours=str(item.get("ours") or ""),
            judgment=str(item.get("judgment") or ""),
            theirs_hash=str(item.get("theirs_hash") or ""),
            ours_label=str(item.get("ours_label") or "")))
    return out


def stated_entry(conflict: EarlyConflict) -> dict[str, Any]:
    """What the stated set keeps of a card the owner was shown: its record and branch (the
    relay's check that the card was shown; with ``requested`` they rebuild the card, so an
    answer given before any decision was written is still recorded as one,
    ``answer.raise_shown``) and, off both branches, the second branch's label."""
    entry: dict[str, Any] = {"record": conflict.record, "branch": conflict.branch}
    if conflict.ours_label:
        entry["ours_label"] = conflict.ours_label
    return entry


def from_stated(item: Mapping[str, Any], cards: Sequence[Mapping[str, Any]] = ()
                ) -> EarlyConflict | None:
    """The card a stated entry names, rebuilt from the cards the session asked for."""
    for found in cards:
        if found.get("record") == item.get("record") and found.get("branch") == item.get(
                "branch"):
            return EarlyConflict(
                record=str(found["record"]), title=str(found.get("title") or ""),
                branch=str(found.get("branch") or ""), claim=str(found.get("claim") or ""),
                theirs=str(found.get("theirs") or ""), ours=str(found.get("ours") or ""),
                judgment=str(found.get("judgment") or ""),
                theirs_hash=str(found.get("theirs_hash") or ""),
                ours_label=str(found.get("ours_label") or ""))
    return None


def requested(session_dir: Any) -> list[Mapping[str, Any]]:
    """The early cards the session last asked the stop hook to show (any age)."""
    import json
    from pathlib import Path

    try:
        data = json.loads((Path(session_dir) / REQUESTED_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    cards = data.get("cards") if isinstance(data, Mapping) else None
    return [c for c in cards or [] if isinstance(c, Mapping) and c.get("record")]


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
        extra: dict[str, Any] = {}
        if me is not None and me.branch and decides:
            # which question this is and, by branch, the two versions it chooses between
            # (their hashes and their words): the owner's answer then settles a merge of
            # exactly these versions, and the card reads the same on any branch (answer.py)
            hashes = {me.branch: index[conflict.record].hash}
            if conflict.theirs_hash:
                hashes[conflict.branch] = conflict.theirs_hash
            extra["early"] = {"record": conflict.record, "raised_on": me.branch,
                              "other": conflict.branch, "hashes": hashes,
                              "texts": {conflict.branch: _clip(conflict.theirs, 240),
                                        me.branch: _clip(conflict.ours, 240)}}
        record = decide(core, question(conflict), mine,
                        [theirs, text.EARLY_BOTH], matters=True, decides=decides,
                        derives_from=derives,
                        rationale=(f"Raised at capture (R17): branch {conflict.branch} has "
                                   f"this requirement in flight; asked once for both."),
                        title=f"{conflict.record} {conflict.title}: which version holds",
                        extra=extra)
        index = core.index()
        entry = {"record": conflict.record, "branch": conflict.branch,
                 "with": conflict.claim, "dec": record.id,
                 "question": record.fields.get("question", ""), "state": "proposed",
                 "chosen": ""}
        block = extra.get("early")
        if block:
            # each side's version as asked, so the side the owner turns down can tell
            # whether it still holds that version (``answer.superseded``)
            entry["versions"] = {branch: {"hash": block["hashes"].get(branch, ""),
                                          "text": block["texts"].get(branch, "")}
                                 for branch in (block["raised_on"], block["other"])}
        entries.append(entry)
    return entries


CLAIMED_KINDS = inflight.CLAIMED_KINDS


@dataclass
class Claimed:
    """What ``claim`` did: the check, the decisions it raised (the claim's conflict
    entries) and the lines telling the agent to ask the owner now."""

    check: EarlyCheck
    entries: list[dict[str, Any]] = field(default_factory=list)
    ask: list[str] = field(default_factory=list)


def claim(core: Any, ids: Sequence[str], *, summary: str, intent: str | None,
          new: Iterable[str] = (), backend: Any = None) -> Claimed:
    """The ONE place a branch's claim on records is written (R17): ``plumb capture``
    (``after_capture``) and the stop hook (``turn.claim_changes``: a direct edit, ``plumb
    new``, an edit after the clarify read-back; ``plumb inflight sync`` too) both come here.
    Before the claim is recorded, the records are checked against the other branches'
    claims (``check_records``): the same record claimed elsewhere at another version is a
    conflict, caught deterministically; a new record in a feature another branch claims is
    judged (``backend``). Each conflict is raised ONCE as a proposed decision that matters
    and its card is asked of the stop hook, so every card the owner sees has a decision the
    owner's words answer. Raises ``inflight.InflightBusy`` when the register kept moving."""
    index = core.index()
    ids = [i for i in ids if i in index]
    mine = [index[i] for i in ids if index[i].kind != "decision"]
    result = check_records(core, mine, new=new, backend=backend)
    request_cards(core, result.conflicts)
    entries = raise_conflicts(core, result.conflicts, intent=intent)
    ask: list[str] = []
    for entry in entries:
        ask.append(text.EARLY_RECORDED.format(id=entry["record"],
                                              title=index[entry["record"]].title
                                              if entry["record"] in index else ""))
        ask.append(text.EARLY_ASK.format(dec=entry["dec"]))
    claimed = {i: inflight.record_entry(index[i]) for i in ids
               if index[i].kind in CLAIMED_KINDS}
    done = Claimed(check=result, entries=entries, ask=ask)
    if claimed or entries:
        inflight.record_claim(core, records=claimed, summary=summary or "", intent=intent,
                              conflicts=entries)
    return done


def after_capture(core: Any, *, written: Sequence[str], updated: Sequence[str],
                  intent: str | None, summary: str = "", dry_run: bool = False,
                  backend: Any = None) -> list[str]:
    """``plumb capture``'s check (R17): compare this capture with other branches' intent in
    flight, show each conflict as an early card, record it once as a DEC and record this
    branch's claim (``claim``; nothing is recorded on a dry run). Returns the lines to
    print."""
    index = core.index()
    ids = [i for i in [*updated, *written] if i in index]
    if not ids:
        return []
    if dry_run:
        mine = [index[i] for i in ids if index[i].kind != "decision"]
        result = check_records(core, mine, new=written, backend=backend)
        lines = [line for conflict in result.conflicts for line in card(conflict)]
        lines += result.lines
        return [*lines, text.EARLY_DRY_RUN] if lines else []
    if not summary and intent and intent in index:
        summary = index[intent].title
    try:
        done = claim(core, ids, summary=summary, intent=intent, new=written,
                     backend=backend)
    except inflight.InflightBusy:
        return [text.INFLIGHT_BUSY]
    lines = [line for conflict in done.check.conflicts for line in card(conflict)]
    return [*lines, *done.check.lines, *done.ask]


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
