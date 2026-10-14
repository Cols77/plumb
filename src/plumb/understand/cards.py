"""Cards (JUDGE): the builders of the issue cards plumb raises. Each card names the topic in the
owner's terms, the issue, the evidence (the owner's words and what conflicts with them) and its
choices, the recommended one first; each choice stores its answer and what it does. Rendering
is ``fullcard``. Record numbers, digests and plumb's own words never stand in what the owner
reads: ``plain`` puts a title where a sentence names a record."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from plumb.contracts import CardState, Choice, ClarifyQuestion
from plumb.present import owner_text

EVIDENCE_WIDTH = 500

_REF = re.compile(r"(?<![\w-])((?:INT|SR|DEC|FEAT|NC|IC)-\d{3,})"
                  r"(?:(?:\s+|/)(EX|AC|A)-(\d+))?(?![\w-])")
_BARE = re.compile(r"\b(?:EX|AC)-\d+\b")
_DIGEST = re.compile(r"\s*\b(?:sha256:[0-9a-f]+|[0-9a-f]{12,})\b")
_EMPTY = re.compile(r"\s*\(\s*\)")
_CARD = re.compile(r"\s*\b(?:clarify|choice|trial|beyond|contradicts|couldnt_check|regression|"
                   r"test_changed|conflict|early_conflict|stale):[\w@.#-]+")


def plain(text: str, index: Mapping[str, Any]) -> str:
    """``text`` as the owner reads it: each record number (and example number) replaced by the
    record's title (and "example n"; a number that names no record is left out of the sentence),
    digests and card ids dropped. Callers keep the owner's quoted words out of it."""

    def swap(match: re.Match[str]) -> str:
        record = index.get(match.group(1))
        if record is None:
            return "another record"
        title = f'"{record.title}"'
        if match.group(3):
            n = match.group(3)
            return f"{title} ({owner_text.EXAMPLE_N.format(n=n) if match.group(2) != 'A' else f'assumption {n}'})"
        return title

    text = _EMPTY.sub("", _DIGEST.sub("", _CARD.sub("", " ".join(str(text).split()))))
    return _BARE.sub("an example", _REF.sub(swap, text))


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
    return clip(f'You were asked "{question}" and said: {text}' if question and text
                else text or question)


def _question(cid: str, text: str, choices: Sequence[Choice], record: Any = None,
              n: int = 1) -> ClarifyQuestion:
    return ClarifyQuestion(
        id=f"{cid}#{n}", text=text, resolutions=tuple(c.label for c in choices),
        record=record.id if record is not None else None,
        hash=record.hash if record is not None else "", choices=tuple(choices))


def _card(kind: str, cid: str, topic: str, issue: str, evidence: str,
          choices: Sequence[Choice], questions: Sequence[tuple[str, Any]],
          turn: int = 0) -> CardState:
    """A card whose questions are ``(text, record or None)``; each carries ``choices`` (their
    answers and what each does, the recommended first) and the version of its record shown."""
    return CardState(
        id=cid, kind=kind, topic=topic, issue=issue, evidence=evidence,
        resolutions=tuple(c.label for c in choices), turn=turn,
        questions=tuple(_question(cid, text, choices, record, n)
                        for n, (text, record) in enumerate(questions, start=1)))


def issue_card(kind: str, record: Any, issue: str, evidence: str,
               choices: Sequence[Choice], *, turn: int = 0) -> CardState:
    """One card about one record: a single question the reader maps the owner's answer to."""
    return _card(kind, card_id(kind, record.id, record.hash), record.title, issue, evidence,
                 choices, [(issue, record)], turn)


KEEP_THIS, KEEP_OTHER, BOTH = "Keep this one", "Keep the other", "Both"


def _stated(says: str, premise: Mapping[str, Any], mine: str = "Written down as",
            yours: str = "You said") -> str:
    """What is written down, then the owner's words, each line named: the two a cold reader
    compares."""
    words = words_of(premise)
    if not words.startswith("You were asked"):
        words = f"{yours}: {words}"
    return (f"{mine}: {says}\n" if says else "") + words


def beyond_card(index: Mapping[str, Any], record: Any, beyond: Sequence[str],
                premise: Mapping[str, Any], says: str = "") -> CardState:
    issue = "; ".join(plain(b, index) for b in beyond if str(b).strip()) \
        or "what is written down says more than your words"
    return issue_card("beyond", record, issue, _stated(says, premise), (
        Choice(owner_text.BEYOND_KEEP, "accepted", consequence=(
            "Confirms it, including the part beyond your words; nothing is removed")),
        Choice(owner_text.BEYOND_DROP, "rejected", consequence=(
            "Removes it; the work built on it is undone, and nothing beyond your words is "
            "kept")),
        Choice(owner_text.BEYOND_REWORD, "change", consequence=(
            "Rewrites it to what you say; nothing is confirmed until you see the new "
            "wording"))))


def contradicts_card(index: Mapping[str, Any], record: Any, contradicts: Sequence[str],
                     premise: Mapping[str, Any], says: str = "") -> CardState:
    issue = "; ".join(plain(c, index) for c in contradicts if str(c).strip()) \
        or "what is written down conflicts with something you said"
    return issue_card("contradicts", record, issue, _stated(
        says, premise, "This one is written down as", "The other is what you said"), (
        Choice(KEEP_THIS, "change", "Keep the record as it reads", (
            "What is written down stays as it reads; what you said that conflicts with it is not "
            "followed")),
        Choice(KEEP_OTHER, "change", "Keep what you said instead of the record", (
            "What you said replaces what is written down; the old wording no longer holds")),
        Choice(BOTH, "change", consequence=(
            "Writes one version from both as you say; neither holds as it reads until you "
            "see it"))))


WHICH_VERSION = "Which version do you mean?"
ANSWERED_VERSION, CURRENT_VERSION, REWORD_VERSION = (
    "Keep what you answered", "Keep how it reads now", "Reword it")


def which_version(record: Any, old: str, new: str, branch: str = "",
                  request: str = "") -> CardState:
    """SR-130 EX-2: a record changed after the owner answered it; one choice shows what they
    answered next to how it reads now (``old`` and ``new`` are one-line proposals; ``request``
    is the request that raised it, with its date)."""
    cid = f"choice:{record.id}:{str(record.hash).split(':')[-1][:12]}"
    options = (ANSWERED_VERSION, CURRENT_VERSION, REWORD_VERSION)
    question = ClarifyQuestion(
        id=f"{cid}#1", text=WHICH_VERSION, resolutions=options, record=record.id,
        hash=record.hash, choices=(
            Choice(ANSWERED_VERSION, "change", change=old, consequence=(
                "Puts back the wording you answered; nothing is confirmed until you see it")),
            Choice(CURRENT_VERSION, "accepted", consequence="Confirms it as it reads now"),
            Choice(REWORD_VERSION, "change", consequence=(
                "You say how it should read; nothing is confirmed until you see it"))))
    issue = f'{WHICH_VERSION} What you answered: "{clip(old, 200)}". How it reads now: "{clip(new, 200)}".'
    context = [f"Raised by: {request}"] if request else []
    context.append(f"What changes: {record.title} was reworded after you answered it")
    return CardState(id=cid, kind="choice", topic=record.title, issue=issue,
                     evidence="\n".join(context), resolutions=options, questions=(question,), branch=branch)


ORDER = ("choice", "clarify", "trial", "beyond", "contradicts", "couldnt_check", "regression",
         "test_changed", "drift", "conflict", "early_conflict")


def kind_rank(card: CardState) -> int:
    return ORDER.index(card.kind) if card.kind in ORDER else len(ORDER)


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
                 owner_text.REGRESSION_ISSUE.format(what=what), evidence, (
                     Choice(owner_text.REGRESSION_FIX, "accepted", consequence=(
                         "The agent changes the code until this test passes again; the "
                         "requirement and the test stay as they are")),
                     Choice(owner_text.REGRESSION_CHANGE, "change", consequence=(
                         "The test is rewritten to what you say; what it checked before is no "
                         "longer checked, so the old behaviour may stay broken")),
                     Choice(owner_text.REGRESSION_WAIT, "open", consequence=(
                         "Nothing changes; the test stays failing and this card stays open "
                         "until you answer it"))), questions, turn)


def test_changed_card(record: Any, ends: Sequence[str], *, turn: int = 0) -> CardState:
    """SR-030: a confirmed requirement whose acceptance test changed since the owner confirmed
    it (``RecordStatus.changed_tests``): which test, the examples it verifies, and the choices
    of putting it back, confirming the new test, or leaving it."""
    checked = {link.example for link in record.links if link.kind == "verified_by"
               and (link.target.test or link.target.path) in ends and link.example}
    says = [f"given {e.given}, when {e.when}, then {e.then}"
            for e in record.examples if e.id in checked]
    evidence = owner_text.TEST_CHANGED_SAYS.format(text=record.fields.get("statement") or
                                                   record.title)
    if says:
        evidence += "\n" + owner_text.TEST_CHANGED_EXAMPLES.format(text="; ".join(says))
    issue = owner_text.TEST_CHANGED_ISSUE.format(tests="; ".join(ends))
    return _card("test_changed", card_id("test_changed", record.id, *ends), record.title, issue,
                 evidence, (
                     Choice(owner_text.TEST_CHANGED_RESTORE, "change", consequence=(
                         "The test is put back as you confirmed it; the change to it is "
                         "undone, and the code is fixed if it no longer passes")),
                     Choice(owner_text.TEST_CHANGED_KEEP, "accepted", consequence=(
                         "Confirms the requirement with the new test; what the old test "
                         "checked and the new one does not is no longer checked")),
                     Choice(owner_text.TEST_CHANGED_LATER, "open", consequence=(
                         "Nothing changes; the requirement waits for you and holds the merge, "
                         "and this card is shown again at the end of the next turn"))),
                 [(issue, record)], turn)


def _sides(ours: str, theirs: str, *, both: str, combined: bool = False) -> list[Choice]:
    """SR-130 EX-3: keep this one, keep the other, or both, each saying what it means."""
    keep = [Choice(KEEP_THIS, "change", f"Keep {ours}'s version", (
                f"Keeps {ours}'s version as the one that holds; the other is dropped")),
            Choice(KEEP_OTHER, "change", f"Keep {theirs}'s version", (
                f"Keeps {theirs}'s version as the one that holds; the other is dropped"))]
    if combined:
        return [Choice(BOTH, "accepted", consequence=both), *keep]
    return [*keep, Choice(BOTH, "change", consequence=both)]


def conflict_card(index: Mapping[str, Any], conflict: Any, *, turn: int = 0) -> CardState:
    """An intent conflict a merge left (sp6 8.3): what each side says, field by field, and the
    choices of keeping one side, the other or both."""
    from plumb.mergedriver.conflicts import field_name, show_value

    ours, theirs = conflict.labels
    sides = []
    for side, label in (("ours", ours), ("theirs", theirs)):
        text = " | ".join(f"{field_name(n)}: {show_value(n, v.get(side))}"
                          for n, v in conflict.fields.items())
        sides.append(owner_text.CONFLICT_SIDE.format(side=label, text=text))
    both = ("Keeps the combined version already proposed; what each side had that it leaves "
            "out is dropped" if conflict.proposed else
            "Writes one version from both as you say; neither holds as it reads until you "
            "see it")
    record = index.get(conflict.record)
    issue = owner_text.CONFLICT_ISSUE.format(ours=ours, theirs=theirs)
    return _card("conflict", card_id("conflict", conflict.ic), conflict.title, issue,
                 " / ".join(sides), _sides(ours, theirs, both=both, combined=conflict.proposed),
                 [(issue, record)], turn)


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
    both = ("One version is written from both as you say; both branches build on it once you "
            "have seen it")
    return _card("early_conflict", card_id("early_conflict", conflict.record, conflict.branch),
                 conflict.title or conflict.record, issue, str(conflict.judgment or ""),
                 _sides(other or "this work", conflict.branch, both=both), [(issue, record)], turn)
