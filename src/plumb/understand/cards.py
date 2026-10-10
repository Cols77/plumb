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

from plumb.contracts import CardState, ClarifyQuestion
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


def issue_card(kind: str, record: Any, issue: str, evidence: str,
               resolutions: Sequence[str], *, turn: int = 0) -> CardState:
    """One card about one record: a single question the reader maps the owner's answer to."""
    cid = card_id(kind, record.id, record.hash)
    return CardState(
        id=cid, kind=kind, topic=record.title, issue=issue, evidence=evidence,
        resolutions=tuple(resolutions),
        questions=(ClarifyQuestion(id=f"{cid}#1", text=issue, resolutions=tuple(resolutions),
                                   record=record.id),),
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
