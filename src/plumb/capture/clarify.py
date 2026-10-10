"""``plumb clarify``: the facts the plumb-clarify skill needs (R11; sp2 9.2, SR-043).

- ``depth``: ``escalated`` when a trigger of sp2 6.1 fires; ``trivial`` when every matched
  record is confirmed, no intent flag fires and the request's ambiguity is low; else
  ``incremental``. The backend may rate ambiguity (``ask``); the heuristic counts the
  request's content terms no matched record covers.
- ``answered``: the confirmed records that already answer parts of the request.
- With drafted questions (``{question, options, recommended}``; an option is a label or
  ``{label, will, wont}``): a question is dropped when a confirmed record answers it or when
  every option builds the same thing; the rest are ranked ("does the answer change what gets
  built?") and the agent asks the first, ONE per message.

``open_decisions`` is the one rule for decisions that matter (stop hook, ``next_question``,
the escalation trigger): unconfirmed and not superseded; only the earliest is asked, and the
next one only after it is answered (sp2 5.3).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.contracts import ClarifyView

if TYPE_CHECKING:
    from plumb.api import Core

AMBIGUITY_TERMS = 2      # unmatched content terms a trivial request may carry


def _number(record_id: str) -> int:
    tail = record_id.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


DECIDING_LINKS = ("decides", "derives_from")


def superseded_ids(index: Mapping[str, Any]) -> set[str]:
    """Records another record's ``supersedes`` link points at (``plumb decide --supersede``
    never edits the old decision, so only this link says it is no longer open)."""
    return {link.target.record for record in index.values() for link in record.links
            if link.kind == "supersedes" and link.target.record in index}


def open_decisions(index: Mapping[str, Any], statuses: Mapping[str, Any],
                   touched: Iterable[str]) -> list[str]:
    """THE open decisions that matter (the one rule behind the stop hook's question, the
    clarify queue and the escalation trigger, R1/R11): DECs with ``matters: true`` that are
    neither confirmed nor superseded, and are touched or decide (or derive from) a touched
    record; earliest-recorded first. A superseded DEC is closed: the owner answered it by the
    decision that replaced it, so it never blocks the queue (one question per message)."""
    touched_set = set(touched)
    closed = superseded_ids(index)
    out = []
    for record_id, record in index.items():
        if record.kind != "decision" or record.fields.get("matters") is not True:
            continue
        if record_id in closed:
            continue
        status = statuses.get(record_id)
        if status is not None and (status.confirmation == "confirmed"
                                   or getattr(status, "superseded_by", None)):
            continue
        linked = {link.target.record for link in record.links
                  if link.kind in DECIDING_LINKS and link.target.record}
        if record_id in touched_set or linked & touched_set:
            out.append(record_id)
    return sorted(out, key=lambda i: (_number(i), i))


def next_question(core: Core, touched: Sequence[str]) -> str | None:
    """The one decision to ask now: the first of ``open_decisions``."""
    found = open_decisions(core.index(), core.status(), touched)
    return found[0] if found else None


def _option_label(option: Any) -> str:
    if isinstance(option, Mapping):
        return " ".join(str(option.get("label") or option.get("text") or "").split())
    return " ".join(str(option).split())


def _option_build(option: Any) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """What an option builds, when the draft says so (``will`` and ``wont`` items)."""
    if not isinstance(option, Mapping) or ("will" not in option and "wont" not in option):
        return None

    def items(key: str) -> tuple[str, ...]:
        raw = option.get(key) or []
        raw = [raw] if isinstance(raw, str) else raw
        return tuple(sorted(" ".join(str(i).lower().split()) for i in raw))

    return items("will"), items("wont")


def _record_text(record: Any) -> str:
    from plumb.judgment.textjudge import record_subject_text

    return record_subject_text(record)


def _answered_by(core: Core, question: Mapping[str, Any],
                 confirmed: Sequence[Any]) -> tuple[str, float] | None:
    """The confirmed record that answers ``question``: it covers enough of the question's
    terms (``clarify.answered_min``) and names exactly one of its options."""
    from plumb.judgment.textjudge import overlap_share, stems

    wanted = stems(str(question.get("question") or ""))
    options = [stems(_option_label(o)) for o in question.get("options") or []]
    best: tuple[str, float] | None = None
    for record in confirmed:
        text = stems(_record_text(record))
        share = overlap_share(wanted, text)
        covered = [o for o in options if o and o <= text]
        enough = share >= float(core.config.clarify.answered_min)
        if enough and len(covered) == 1 and (best is None or share > best[1]):
            best = (record.id, share)
    return best


def _distinct_builds(question: Mapping[str, Any]) -> int:
    builds = [_option_build(o) for o in question.get("options") or []]
    known = [b for b in builds if b is not None]
    if len(known) < 2 or len(known) < len(builds):
        return -1  # the draft does not say what each option builds
    return len(set(known))


def clarify(core: Core, request: str, questions: Sequence[Mapping[str, Any]] = (), *,
            backend: Any = None) -> ClarifyView:
    from plumb.capture.escalation import escalation, matched_ids
    from plumb.capture.flags import intent_flags
    from plumb.judgment.textjudge import stems

    index = core.index()
    statuses = core.status()
    matched = matched_ids(core, request, ())
    unavailable: str | None = None
    if backend is None:
        from plumb.judgment import JudgmentUnavailable, get_backend

        try:
            backend = get_backend(core, hook=False)
        except JudgmentUnavailable as exc:  # INT-029: said, never answered by rules
            unavailable = str(exc)
    name = str(getattr(backend, "name", "none")) if backend is not None else "none"
    confirmed_ids = [i for i in matched if statuses[i].confirmation == "confirmed"]
    relevant_confirmed = [index[i] for i, _ in core.relevant(request, 8)
                          if statuses[i].confirmation == "confirmed"]
    answered = tuple(f"{r.id} (confirmed): {r.title}"
                     for r in {r.id: r for r in [index[i] for i in confirmed_ids]
                               + relevant_confirmed}.values())
    suggestions = tuple(s for s in escalation(core, prompt=request, matched=matched,
                                              backend=backend) if s.trigger != "diff")
    flags = intent_flags(core, request, matched, backend) \
        if confirmed_ids and backend is not None else []
    covered = set().union(*(stems(_record_text(index[i])) for i in matched)) if matched \
        else set()
    unmatched = sorted(stems(request) - covered)
    ambiguous = len(unmatched) > AMBIGUITY_TERMS
    if backend is not None:
        judged = backend.ask("Is this request ambiguous given these records: could two "
                             "reasonable readings build different things?",
                             request + "\n" + "\n".join(answered), subject="request",
                             action="ambiguity")
        if judged.verdict in ("yes", "no") and judged.confidence >= 0.7:
            ambiguous = judged.verdict == "yes"
    if suggestions:
        depth, reason = "escalated", "; ".join(s.reason for s in suggestions)
    elif (matched and len(confirmed_ids) == len(matched) and not flags and not ambiguous
          and unavailable is None):
        depth, reason = "trivial", "maps to confirmed " + ", ".join(confirmed_ids)
    else:
        why = []
        if not matched:
            why.append("no record covers it yet")
        elif len(confirmed_ids) < len(matched):
            why.append("it touches unconfirmed records")
        if flags:
            why.append("it may change " + ", ".join(f.record for f in flags))
        if ambiguous:
            why.append("terms no record covers: " + ", ".join(unmatched[:5]))
        depth, reason = "incremental", "; ".join(why) or "new or partly specified intent"
    if unavailable is not None:
        reason += f"; judging unavailable: {unavailable}"

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    all_confirmed = [r for r in index.values() if statuses[r.id].confirmation == "confirmed"
                     and r.kind in ("requirement", "decision", "intent")]
    for draft in questions:
        question = dict(draft)
        hit = _answered_by(core, question, all_confirmed)
        if hit is not None:
            question["dropped_because"] = (f"answered by {hit[0]} (confirmed): "
                                           f"{index[hit[0]].title}")
            dropped.append(question)
            continue
        if _distinct_builds(question) == 1:
            question["dropped_because"] = "every option builds the same thing"
            dropped.append(question)
            continue
        judgment = None if backend is None else backend.ask(
            "Does the answer to this question change what gets built?",
            json.dumps(question, ensure_ascii=False), subject="question", action="ambiguity")
        if judgment is not None and judgment.verdict == "no" and judgment.confidence >= 0.7:
            question["dropped_because"] = "the backend judges every answer builds the same"
            dropped.append(question)
            continue
        score = (judgment.confidence if judgment is not None and judgment.verdict == "yes"
                 else 0.0,
                 _distinct_builds(question), 1 if question.get("recommended") else 0)
        question["rank_score"] = list(score)
        kept.append(question)
    kept.sort(key=lambda q: tuple(-x for x in q["rank_score"]))
    # R17: other branches' intent in flight, checked before any implementation
    inflight, conflicted = _inflight(core, request, backend)
    if conflicted and depth == "trivial":
        depth, reason = "incremental", "another branch has this intent in flight"
    if depth == "trivial":
        dropped += [{**q, "dropped_because": "trivial: no questions"} for q in kept]
        kept = []
    return ClarifyView(depth=depth, reason=reason, answered=answered,  # type: ignore[arg-type]
                       questions=tuple(kept), dropped=tuple(dropped), escalation=suggestions,
                       backend=name, inflight=tuple(inflight))


def _inflight(core: Core, request: str, backend: Any) -> tuple[list[str], bool]:
    """The early intent-conflict check of the read-back (R17, SR-081): ``(lines, whether a
    card is among them)``. Advisory: an error shows nothing."""
    try:
        from plumb.awareness.early import card, check_text, request_cards

        result = check_text(core, request, backend=backend)
        request_cards(core, result.conflicts)  # the owner sees them at the end of the turn
    except Exception:  # noqa: BLE001 - intent in flight never fails the read-back
        return [], False
    lines = [line for conflict in result.conflicts for line in card(conflict)]
    return lines + list(result.lines), bool(result.conflicts)


def write_session(core: Core, view: ClarifyView, request: str) -> None:
    """``.plumb/session/<sid>/clarify.json``: the depth of the current intent, so the stop
    hook can tell an escalated intent from an incremental one."""
    session = os.environ.get("PLUMB_AGENT_SESSION") or "cli"
    safe = "".join(c for c in session if c.isalnum() or c in "-_") or "cli"
    path = core.paths.session / safe / "clarify.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"depth": view.depth, "reason": view.reason,
                                    "request": request,
                                    "questions": [q.get("question") for q in view.questions]},
                                   ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def view_lines(view: ClarifyView) -> list[str]:
    lines = list(getattr(view, "inflight", ()) or ())
    if any(line.startswith(("▸ Conflict", "> Conflict")) for line in lines):
        lines.append("ask this conflict first, before any other question or any work")
    lines.append(f"depth: {view.depth} ({view.reason})")
    if view.answered:
        lines.append("already answered (do not ask):")
        lines += [f"  {a}" for a in view.answered]
    for suggestion in view.escalation:
        lines.append(suggestion.line)
    if view.questions:
        lines.append("questions that matter, ask the first, one per message:")
        for n, q in enumerate(view.questions, start=1):
            options = " / ".join(_option_label(o) for o in q.get("options") or [])
            rec = f" (recommended: {q['recommended']})" if q.get("recommended") else ""
            lines.append(f"  {n}. {q.get('question')} [{options}]{rec}")
    for q in view.dropped:
        lines.append(f"  dropped: {q.get('question')} ({q.get('dropped_because')})")
    if view.depth == "trivial":
        lines.append("no questions: read back in one line and proceed")
    return lines
