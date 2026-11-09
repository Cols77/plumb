"""Exact text helpers (sp2 7.1, 8.1, 11.2): stems, term overlap and the contradiction check.

These are not a judge. There is no rule-based judge (INT-029); a judgment is the configured
judge's alone. What remains is exact and deterministic:

- ``stems`` and ``overlap_share``: term overlap, to match requests and records;
- ``contradiction``: a number, a flipped will/won't or a negated result between a restatement
  and the owner's words, which keeps a record out of the low-risk group whatever the judge
  scored.

Standard library only, no I/O: hooks call it every turn.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from iaso.text import STOPWORDS

_WORD = re.compile(r"[a-z]{3,}")
_ID = re.compile(r"(?<![A-Za-z0-9-])((?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})(?![0-9])")
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})
_LABEL = re.compile(r"^\s*(will|won't|wont|assumed|assume|assumption)\s*:\s*", re.IGNORECASE)


def stem(word: str) -> str:
    """A light stem so "exports", "exporting" and "export" meet."""
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 5 and word.endswith("ed"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiouls":
        word = word[:-1]  # "pinn" (pinning) -> "pin"
    return word


def stems(text: str) -> frozenset[str]:
    return frozenset(stem(w) for w in _WORD.findall(text.lower().translate(_APOSTROPHES))
                     if w not in STOPWORDS)


def _example_texts(record: object) -> list[tuple[str, str, str]]:
    """``(EX id, full text, then text)`` of each example."""
    out = []
    for example in getattr(record, "examples", ()) or ():
        full = " ".join((example.given, example.when, example.then, example.criterion))
        out.append((example.id, full, example.then or example.criterion))
    return out


def record_subject_text(record: object) -> str:
    fields = getattr(record, "fields", {}) or {}
    parts = [str(getattr(record, "title", ""))]
    for key in ("statement", "readback", "quote", "chosen"):
        value = fields.get(key)
        if isinstance(value, str):
            parts.append(value)
    parts.extend(full for _, full, _ in _example_texts(record))
    return " ".join(parts)


def overlap_share(a: Iterable[str], b: Iterable[str]) -> float:
    """Share of ``a`` found in ``b``."""
    a, b = set(a), set(b)
    return len(a & b) / len(a) if a else 0.0


# --------------------------------------------------------------------------- contradiction

_NEGATION = re.compile(
    r"(?<![\w'])(?:not|no|never|none|nothing|without|cannot|can't|don't|doesn't|didn't"
    r"|won't|wont|isn't|aren't|shouldn't|mustn't|no\s+longer|neither|nor)(?![\w'])")
_SENTENCE = re.compile(r"[.!?;]+(?=\s|$)|\n")
_CLAUSE = re.compile(r"[.!?;,:]+(?=\s|$)|\n|(?<![\w])(?:but|however|and\s+then)(?![\w])")
# words a negated statement wraps around its subject ("it is not true that ...")
_FILLER = frozenset({"true", "case", "that"})


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE.split(text) if c and c.strip()]


def contradiction(premise: str, hypothesis: str) -> str | None:
    """Why ``hypothesis`` contradicts the owner's words ``premise``, or None (R8 A, R13 Q1).

    Cheap, deterministic checks for the "no" cases the owner named: a flipped will/won't (a
    will line, a read-back or a result holding every word of something the premise negates:
    "change add" against "do not change add") and the reverse (a won't line, or a negated
    result, whose words all sit in a clause the premise states positively: "it is not true
    that it returns 8" against "then it returns 8"). Term coverage alone ignores both. A
    number the owner never said is the agent's formalization, not a contradiction (DEC-140).
    """
    text = premise.translate(_APOSTROPHES).lower()
    negated_scopes: list[frozenset[str]] = []
    positive: list[frozenset[str]] = []
    for clause in _clauses(text):
        match = _NEGATION.search(clause)
        if match is None:
            positive.append(stems(clause))
        else:
            scope = stems(clause[match.end():])
            if scope:
                negated_scopes.append(scope)
    # a whole sentence stated positively ("given 2, when pow is called, then it returns 8")
    positive += [stems(s) for s in _SENTENCE.split(text) if s.strip()
                 and _NEGATION.search(s) is None]
    for raw in hypothesis.splitlines():
        line = raw.translate(_APOSTROPHES)
        label = _LABEL.match(line)
        kind = label.group(1).lower() if label else ""
        body = (line[label.end():] if label else line).strip()
        if not body:
            continue
        words = stems(body) - _FILLER
        negation = _NEGATION.search(body.lower())
        negated = kind in ("won't", "wont") or negation is not None
        if negation is not None and kind not in ("won't", "wont"):
            # what the line negates: "then it is not true that it returns 8" -> "returns 8"
            words = stems(body[negation.end():]) - _FILLER or words
        if not words:
            continue
        if not negated:
            for scope in negated_scopes:
                if scope <= words:
                    return (f"\"{body[:60]}\" does what your words rule out "
                            f"({', '.join(sorted(scope))})")
        elif any(words <= clause for clause in positive) \
                and not any(words <= scope or scope <= words for scope in negated_scopes):
            return f"\"{body[:60]}\" rules out what your words ask for"
    return None
