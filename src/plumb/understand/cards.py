"""Cards (JUDGE): the builders of the issue cards the judge raises, and (J7) their rendering
for the end-of-turn summary.

Every card names the topic in the owner's terms, the issue, the evidence (the owner's words and
what conflicts with them) and two or three suggested resolutions, the recommended one first.
Record numbers never stand alone in what the owner reads: ``plain`` puts a title where a model's
sentence names a record."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from plumb.contracts import CardState, Choice, ClarifyQuestion
from plumb.present import owner_text

EVIDENCE_WIDTH = 500

_REF = re.compile(r"(?<![\w-])((?:INT|SR|DEC|FEAT)-\d{3,})(?:[ \t]+(?:EX|AC)-(\d+))?(?![\w-])")


def plain(text: str, index: Mapping[str, Any]) -> str:
    """``text`` with each record number (and example number) replaced by the record's title
    (and "example n"); a number that names no record is left out of the sentence."""

    def swap(match: re.Match[str]) -> str:
        record = index.get(match.group(1))
        if record is None:
            return "another record"
        title = f'"{record.title}"'
        if match.group(2):
            return f"{title} ({owner_text.EXAMPLE_N.format(n=match.group(2))})"
        return title

    return _REF.sub(swap, " ".join(str(text).split()))


def clip(text: str, width: int = EVIDENCE_WIDTH) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."


def card_id(kind: str, *parts: str) -> str:
    """``<kind>:`` plus what the card is about, so the same facts are the same card."""
    if len(parts) == 1 and len(parts[0]) <= 24 and re.fullmatch(r"[\w.-]+", parts[0]):
        return f"{kind}:{parts[0]}"
    return f"{kind}:" + hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]


def words_of(premise: Mapping[str, Any]) -> str:
    """The owner's words a premise holds, for a card's evidence."""
    messages = [str(m.get("text") or "") for m in premise.get("messages") or ()]
    text = " / ".join(m for m in messages if m.strip())
    question = str(premise.get("question") or "").strip()
    return clip(f"{question} -> {text}" if question and text else text or question)


# What each kind's suggested resolutions answer (sp7-realign-sp8 C2, SP8 4.1): keep = accepted,
# drop = rejected, reword = change (the owner's words say how); a resolution not listed here is
# a pick (a version, a gap's suggestion, a stale link's option): change, carrying its label.
PICK = "pick"
_CHOICES: dict[str, dict[str, str]] = {
    "trial": {owner_text.TRIAL_YES: "accepted", owner_text.TRIAL_NO: "rejected"},
    "backlog": {owner_text.BACKLOG_YES: "accepted", owner_text.BACKLOG_EXCEPT: "change",
                owner_text.BACKLOG_NO: "rejected", owner_text.NO_ORIGINAL_ACCEPT: "accepted",
                owner_text.NO_ORIGINAL_CORRECT: "change"},
    "beyond": {owner_text.BEYOND_KEEP: "accepted", owner_text.BEYOND_DROP: "rejected",
               owner_text.BEYOND_REWORD: "change"},
    "contradicts": {owner_text.CONTRADICTS_KEEP_OLD: PICK, owner_text.CONTRADICTS_KEEP_NEW: PICK,
                    owner_text.CONTRADICTS_COMBINE: "change"},
    "couldnt_check": {owner_text.GATE_BUILD_ANYWAY: "accepted", owner_text.GATE_WAIT: "rejected",
                      owner_text.COULDNT_CHECK_GO: "accepted",
                      owner_text.COULDNT_CHECK_WAIT: "rejected"},
    "show_first": {owner_text.UNDONE_CONFIRM: "accepted", owner_text.UNDONE_CHANGE: "change",
                   owner_text.UNDONE_DROP: "rejected", owner_text.SHOW_FIRST_YES: "accepted",
                   owner_text.SHOW_FIRST_NO: "rejected"},
    "settle_offer": {owner_text.SETTLE_TURN_ON: "accepted",
                     owner_text.SETTLE_LEAVE_OFF: "rejected"},
    "clarify": {owner_text.READBACK_YES: "accepted", owner_text.READBACK_NOT_QUITE: "change"},
    "stale_link": {},
    # slice 3: the kinds the stop hook drew its own way (sp7-realign-sp8 C1)
    "regression": {owner_text.REGRESSION_FIX: "accepted", owner_text.REGRESSION_CHANGE: "change",
                   owner_text.REGRESSION_WAIT: "open"},
    "decision": {owner_text.DECISION_KEEP: "accepted", owner_text.DECISION_SWITCH: PICK,
                 owner_text.DECISION_OTHER: "change"},
    "conflict": {owner_text.CONFLICT_COMBINED: "accepted", owner_text.CONFLICT_KEEP: PICK,
                 owner_text.CONFLICT_COMBINE: "change"},
    "early_conflict": {owner_text.EARLY_KEEP_OURS: PICK, owner_text.EARLY_KEEP_THEIRS: PICK,
                       owner_text.EARLY_BOTH_OPTION: "change"},
    "drift": {},
    "proposed": {owner_text.PROPOSED_YES: "accepted", owner_text.PROPOSED_EXCEPT: "change",
                 owner_text.PROPOSED_LATER: "open"},
    "test_changed": {owner_text.TEST_CHANGED_RESTORE: "change",
                     owner_text.TEST_CHANGED_KEEP: "accepted",
                     owner_text.TEST_CHANGED_LATER: "open"},
}


def _answer_of(table: Mapping[str, str], label: str) -> str:
    """``label``'s answer in ``table``; a template entry ("... {kind} ...") matches any filling."""
    if label in table:
        return table[label]
    for template, answer in table.items():
        if "{" in template and re.fullmatch(
                re.sub(r"\\\{\w+\\\}", ".+", re.escape(template)), label):
            return answer
    return PICK


def choices_for(kind: str, resolutions: Sequence[str]) -> tuple[Choice, ...]:
    """The choices of a ``kind`` card question whose suggested resolutions are
    ``resolutions``, in their order (the recommended one first): what the reader's prompt
    lists and what a button answers."""
    table = _CHOICES.get(kind, {})
    out: list[Choice] = []
    for label in map(str, resolutions):
        answer: Any = _answer_of(table, label)
        out.append(Choice(label, "change", label) if answer == PICK else Choice(label, answer))
    return tuple(out)


def issue_card(kind: str, record: Any, issue: str, evidence: str,
               resolutions: Sequence[str], *, turn: int = 0) -> CardState:
    """One card about one record: a single question the reader maps the owner's answer to."""
    cid = card_id(kind, record.id, record.hash)
    return CardState(
        id=cid, kind=kind, topic=record.title, issue=issue, evidence=evidence,
        resolutions=tuple(resolutions),
        questions=(ClarifyQuestion(id=f"{cid}#1", text=issue, resolutions=tuple(resolutions),
                                   record=record.id, hash=record.hash,
                                   choices=choices_for(kind, resolutions)),),
        turn=turn)


def beyond_card(index: Mapping[str, Any], record: Any, beyond: Sequence[str],
                premise: Mapping[str, Any]) -> CardState:
    issue = "; ".join(plain(b, index) for b in beyond if str(b).strip()) \
        or "the record says more than your words"
    return issue_card("beyond", record, issue, words_of(premise),
                      (owner_text.BEYOND_KEEP, owner_text.BEYOND_DROP,
                       owner_text.BEYOND_REWORD))


def contradicts_card(index: Mapping[str, Any], record: Any, contradicts: Sequence[str],
                     premise: Mapping[str, Any]) -> CardState:
    issue = "; ".join(plain(c, index) for c in contradicts if str(c).strip()) \
        or "the record conflicts with something you said"
    return issue_card("contradicts", record, issue, words_of(premise),
                      (owner_text.CONTRADICTS_KEEP_OLD, owner_text.CONTRADICTS_KEEP_NEW,
                       owner_text.CONTRADICTS_COMBINE))


HEADS = {"clarify": owner_text.CARD_CLARIFY, "trial": owner_text.CARD_TRIAL,
         "backlog": owner_text.CARD_BACKLOG, "beyond": owner_text.CARD_BEYOND,
         "contradicts": owner_text.CARD_CONTRADICTS,
         "couldnt_check": owner_text.CARD_COULDNT_CHECK,
         "show_first": owner_text.CARD_SHOW_FIRST, "stale_link": owner_text.CARD_STALE_LINK,
         "settle_offer": owner_text.CARD_SETTLE_OFFER,
         "regression": owner_text.CARD_REGRESSION, "decision": owner_text.CARD_DECISION,
         "conflict": owner_text.CARD_CONFLICT, "early_conflict": owner_text.CARD_EARLY_CONFLICT,
         "drift": owner_text.CARD_DRIFT, "proposed": owner_text.CARD_PROPOSED,
         "test_changed": owner_text.CARD_TEST_CHANGED}
ORDER = ("clarify", "trial", "backlog", "beyond", "contradicts", "couldnt_check", "regression",
         "test_changed", "drift", "conflict", "early_conflict", "decision", "proposed")
RESOLUTIONS_MAX = 3
ITEMS_MAX = 30


def render(card: CardState) -> str:
    """A card as the owner reads it: its head (the topic and the issue), the items a batch or
    a feature card covers, the evidence, and two or three suggested resolutions, the
    recommended one first."""
    head = HEADS.get(card.kind, owner_text.CARD_GENERIC)
    lines = [head.format(topic=card.topic, issue=card.issue)]
    items = [q.text for q in card.questions if q.text and q.text != card.issue]
    if len(items) >= 2:
        lines += [owner_text.CARD_ITEM.format(text=t) for t in items[:ITEMS_MAX]]
        if len(items) > ITEMS_MAX:
            lines.append(owner_text.CARD_ITEM.format(
                text=owner_text.CARD_MORE.format(n=len(items) - ITEMS_MAX)))
    if card.evidence and card.kind != "clarify":  # SR-147: the read-back's lines stay stored
        lines.append(owner_text.CARD_EVIDENCE.format(evidence=card.evidence))
    lines += [owner_text.CARD_RESOLUTION.format(n=n, text=text)
              for n, text in enumerate(card.resolutions[:RESOLUTIONS_MAX], start=1)]
    return "\n".join(lines)


def kind_rank(card: CardState) -> int:
    return ORDER.index(card.kind) if card.kind in ORDER else len(ORDER)


def undone_cards(core: Any, session: str, *, turn: int = 0) -> list[CardState]:
    """A card for each settled record the owner took back (SR-105 EX-3): it is proposed again
    and shown as a card. One card per record, made once: a card the session already holds (open,
    answered or closed) is not made again, and a record the owner confirmed since needs none."""
    from plumb.understand import cardstore, premise, recheck_settled

    undone = recheck_settled.undone_records(core)
    if not undone:
        return []
    index = core.index()
    wanted = [rid for rid, _ in undone if rid in index]
    held = {c.id for c in cardstore.load(core.root, session, open_only=False)}
    statuses = core.status(wanted)
    known = premise.committed(core)
    out: list[CardState] = []
    for rid in dict.fromkeys(wanted):
        record = index[rid]
        cid = f"show_first:{rid}"
        if cid in held or statuses[rid].confirmation == "confirmed":
            continue
        given = premise.premise_of(core, record, known=known).as_input()
        options = (owner_text.UNDONE_CONFIRM, owner_text.UNDONE_CHANGE, owner_text.UNDONE_DROP)
        out.append(CardState(
            id=cid, kind="show_first", topic=record.title, issue=owner_text.UNDONE_ISSUE,
            evidence=words_of(given), resolutions=options,
            questions=(ClarifyQuestion(id=f"{cid}#1", text=owner_text.UNDONE_ISSUE,
                                       resolutions=options, record=rid, hash=record.hash,
                                       choices=choices_for("show_first", options)),),
            turn=turn))
    return out


# --------------------------------------------------------------------------- slice 3 kinds
# The owner items the stop hook drew its own way, as cards (sp7-realign-sp8 C1): a regression,
# a decision that matters, a merge conflict, an early conflict, and the records a turn proposed
# (one card per feature, C8). The drift card is a stale card the diagnosis filed (``fullcard``).


def _card(kind: str, cid: str, topic: str, issue: str, evidence: str,
          resolutions: Sequence[str], questions: Sequence[tuple[str, Any]],
          turn: int = 0) -> CardState:
    """A card whose questions are ``(text, record or None)``; each question carries the
    choices of ``resolutions`` and the version of its record shown."""
    made = tuple(ClarifyQuestion(
        id=f"{cid}#{n}", text=text, resolutions=tuple(resolutions),
        record=record.id if record is not None else None,
        hash=record.hash if record is not None else "",
        choices=choices_for(kind, resolutions))
        for n, (text, record) in enumerate(questions, start=1))
    return CardState(id=cid, kind=kind, topic=topic, issue=issue, evidence=evidence,
                     resolutions=tuple(resolutions), questions=made, turn=turn)


def verifying(index: Mapping[str, Any], node: str) -> list[Any]:
    """The requirements a test node verifies (its ``verified_by`` links, by node or file)."""
    path = node.split("::", 1)[0]
    out = []
    for record in index.values():
        for link in getattr(record, "links", ()):
            if link.kind != "verified_by":
                continue
            end = link.target.test or link.target.path or ""
            if end == node or (link.target.test is None and end == path):
                out.append(record)
                break
    return sorted(out, key=lambda r: r.id)


def regression_card(index: Mapping[str, Any], node: str, *, last_run: str = "",
                    test_changed: bool = False, hidden: bool = False,
                    turn: int = 0) -> CardState:
    """SR-012 EX-2: a test that passed with recorded evidence now fails (or passes only because
    it was changed): the test, what it checks, and the suggested resolutions."""
    records = verifying(index, node)
    what = "; ".join(f'"{r.title}"' for r in records) or node
    if hidden:
        evidence = owner_text.REGRESSION_HIDDEN.format(test=node)
    else:
        note = (owner_text.REGRESSION_TEST_CHANGED if test_changed else "") + (
            owner_text.REGRESSION_LAST_RUN.format(run=last_run) if last_run else "")
        evidence = owner_text.REGRESSION_EVIDENCE.format(test=node, note=note)
    topic = records[0].title if records else node
    questions = [(r.title, r) for r in records] or [(node, None)]
    return _card("regression", card_id("regression", node), topic,
                 owner_text.REGRESSION_ISSUE.format(what=what), evidence,
                 (owner_text.REGRESSION_FIX, owner_text.REGRESSION_CHANGE,
                  owner_text.REGRESSION_WAIT), questions, turn)


def test_changed_card(record: Any, ends: Sequence[str], *, turn: int = 0) -> CardState:
    """SR-030: a confirmed requirement whose acceptance test changed since the owner confirmed
    it (``RecordStatus.changed_tests``): which test, the examples it verifies, and the choices
    of putting it back, confirming the new test, or leaving it."""
    tests = []
    for end in ends:
        examples = [link.example for link in record.links if link.kind == "verified_by"
                    and (link.target.test or link.target.path) == end and link.example]
        tests.append(end + (f" ({', '.join(examples)})" if examples else ""))
    what = "; ".join(tests)
    issue = owner_text.TEST_CHANGED_ISSUE.format(tests=what)
    return _card("test_changed", card_id("test_changed", record.id, *ends), record.title, issue,
                 owner_text.TEST_CHANGED_EVIDENCE.format(tests=what),
                 (owner_text.TEST_CHANGED_RESTORE, owner_text.TEST_CHANGED_KEEP,
                  owner_text.TEST_CHANGED_LATER), [(issue, record)], turn)


def _alternatives(record: Any) -> list[str]:
    raw = record.fields.get("alternatives") or []
    raw = [raw] if isinstance(raw, str) else raw
    return [" ".join(str(a).split()) for a in raw if str(a).strip()]


def decision_card(index: Mapping[str, Any], record: Any, *, touched: Sequence[str] = (),
                  turn: int = 0) -> CardState:
    """An unconfirmed decision that matters and that this work relies on (SR-012): what was
    assumed, what else fits, and what the turn changed that relies on it. A decision that
    holds an early conflict (R17) is an ``early_conflict`` card with its own answers."""
    from plumb.awareness.answer import early_of

    chosen = " ".join(str(record.fields.get("chosen") or "").split()) or record.title
    others = _alternatives(record)
    relies = [index[i].title for i in touched if i in index and i != record.id and any(
        link.target.record == i for link in record.links)]
    evidence = owner_text.DECISION_EVIDENCE.format(
        what="; ".join(f'"{t}"' for t in relies)) if relies else ""
    if early_of(record) is not None:
        question = " ".join(str(record.fields.get("question") or record.title).split())
        return _card("early_conflict", card_id("early_conflict", record.id, record.hash),
                     record.title, question, evidence, [chosen, *others][:RESOLUTIONS_MAX],
                     [(question, record)], turn)
    other = others[0] if others else owner_text.DECISION_NO_ALTERNATIVE
    options = [owner_text.DECISION_KEEP.format(chosen=chosen),
               *(owner_text.DECISION_SWITCH.format(other=o) for o in others[:1]),
               owner_text.DECISION_OTHER]
    issue = owner_text.DECISION_ISSUE.format(chosen=chosen, other=other)
    return _card("decision", card_id("decision", record.id, record.hash), record.title, issue,
                 evidence, options, [(issue, record)], turn)


def conflict_card(index: Mapping[str, Any], conflict: Any, *, turn: int = 0) -> CardState:
    """An intent conflict a merge left (sp6 8.3): what each side says, field by field, and the
    choices of keeping one side or combining them."""
    from plumb.mergedriver.conflicts import field_name, show_value

    ours, theirs = conflict.labels
    sides = []
    for side, label in (("ours", ours), ("theirs", theirs)):
        text = " | ".join(f"{field_name(n)}: {show_value(n, v.get(side))}"
                          for n, v in conflict.fields.items())
        sides.append(owner_text.CONFLICT_SIDE.format(side=label, text=text))
    keep = [owner_text.CONFLICT_KEEP.format(side=ours), owner_text.CONFLICT_KEEP.format(
        side=theirs)]
    options = ([owner_text.CONFLICT_COMBINED, *keep] if conflict.proposed
               else [*keep, owner_text.CONFLICT_COMBINE])
    record = index.get(conflict.record)
    issue = owner_text.CONFLICT_ISSUE.format(ours=ours, theirs=theirs)
    return _card("conflict", card_id("conflict", conflict.ic), conflict.title, issue,
                 " / ".join(sides), options, [(issue, record)], turn)


def early_conflict_card(index: Mapping[str, Any], conflict: Any, *,
                        turn: int = 0) -> CardState:
    """An early intent conflict this turn's claim raised (R17): the other branch's version and
    this work's, in the owner's words. On a branch that is neither side (``ours_label`` names
    the second branch) both are labelled and offered by branch, never "this work"."""
    record = index.get(conflict.record)
    other = conflict.ours_label
    issue = (owner_text.EARLY_ISSUE_NAMED.format(branch=conflict.branch, other=other,
                                                 theirs=conflict.theirs, ours=conflict.ours)
             if other else owner_text.EARLY_ISSUE.format(
                 branch=conflict.branch, theirs=conflict.theirs, ours=conflict.ours))
    keep = owner_text.EARLY_KEEP_THEIRS.format(branch=conflict.branch)
    ours = (owner_text.EARLY_KEEP_THEIRS.format(branch=other) if other
            else owner_text.EARLY_KEEP_OURS)
    options = ((keep, ours) if other else (ours, keep)) + (owner_text.EARLY_BOTH_OPTION,)
    return _card("early_conflict", card_id("early_conflict", conflict.record, conflict.branch),
                 conflict.title or conflict.record, issue, str(conflict.judgment or ""),
                 options, [(issue, record)], turn)


def _group_of(index: Mapping[str, Any], record: Any) -> tuple[str, str]:
    """``(key, topic)`` of the feature card a proposed record joins (DEC-029): its feature, else
    the intent it derives from (an intent is its own group), else the turn's work."""
    feature = str(record.fields.get("feature") or "")
    if feature:
        found = index.get(feature)
        return feature, found.title if found is not None else owner_text.PROPOSED_NO_FEATURE
    if record.kind == "intent":
        return record.id, record.title
    for link in record.links:
        target = link.target.record
        if link.kind in ("derives_from", "decides") and target in index:
            return _group_of(index, index[target])
    return "", owner_text.PROPOSED_NO_FEATURE


def proposed_cards(index: Mapping[str, Any], ids: Sequence[str], *,
                   turn: int = 0) -> list[CardState]:
    """SR-012 EX-3, EX-4: the records a turn proposed that nothing settled, one card per
    feature (DEC-029), each record a question of its card (never a list of lines)."""
    groups: dict[str, tuple[str, list[Any]]] = {}
    for record_id in dict.fromkeys(ids):
        record = index.get(record_id)
        if record is None:
            continue
        key, topic = _group_of(index, record)
        groups.setdefault(key, (topic, []))[1].append(record)
    out = []
    for key, (topic, records) in groups.items():
        issue = (owner_text.PROPOSED_ISSUE_ONE if len(records) == 1
                 else owner_text.PROPOSED_ISSUE.format(n=len(records)))
        out.append(_card("proposed", card_id("proposed", key or "turn"), topic, issue, "",
                         (owner_text.PROPOSED_YES, owner_text.PROPOSED_EXCEPT,
                          owner_text.PROPOSED_LATER),
                         [(r.title, r) for r in records], turn))
    return out
