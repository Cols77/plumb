"""Deterministic text judgments behind the heuristic backend (sp2 7.1, 8.1, 11.2).

- ``classify``: is a request a contradiction of a confirmed record (it negates, replaces or
  reverses a confirmed example's ``then`` or the statement), an extension (new behaviour
  beside it), or benign (a mention, a tidy-up, a question)? Change words alone never flag
  (sp2 C6).
- ``coverage``: how much of a restatement the owner's words support (term coverage), with a
  penalty for each won't item or assumption the words do not support at all (sp2 8.1).

Standard library only, no I/O: hooks call it every turn.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from plumb.text import STOPWORDS

_WORD = re.compile(r"[a-z]{3,}")
_ID = re.compile(r"(?<![A-Za-z0-9-])((?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})(?![0-9])")
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})


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


# --------------------------------------------------------------------------- classify

# tidy-ups, tests and docs: a request touching only these leaves behaviour as it is
_TIDY = re.compile(
    r"(?<![\w])(?:docstrings?|comments?|typos?|format(?:ting)?|reformat\w*|whitespace|lint\w*"
    r"|indent\w*|type\s+hints?|annotations?|readme|changelog|docs?|documentation|spelling"
    r"|tests?|coverage|rename\s+(?:the\s+)?(?:local\s+)?variables?|log\s+messages?|tidy"
    r"|clean\s*up|cleanup)(?![\w])")
_CONTRA = re.compile(
    r"(?<![\w'])(?:instead|no\s+longer|any\s*more|remove|delete|drop|replace|stop|never"
    r"|don't|do\s+not|doesn't|does\s+not|shouldn't|should\s+not|must\s+not|should\s+now"
    r"|rather\s+than|switch\s+to|rename\s+\S+\s+to|change\s+(?:\S+\s+){0,3}?(?:to|so|into)"
    r"|reverse|invert|forbid|disallow|turn\s+off|disable)(?![\w'])")
_STRONG_CONTRA = re.compile(r"(?<![\w'])(?:instead|no\s+longer|any\s*more|replace|rather\s+than"
                            r"|switch\s+to)(?![\w'])")
_EXT = re.compile(
    r"(?<![\w'])(?:also|as\s+well|too|next\s+to|beside|in\s+addition|additionally|another"
    r"|new|support\w*|extend\w*|plus|allow\w*|include\w*|add\s+(?:a|an|another|new|some)"
    r"|accept\w*|let\s+\S+\s+accept)(?![\w'])")
_MAKE = re.compile(r"(?<![\w])make\s+(?:the\s+|it\s+|a\s+)?([a-z]+)\s+([a-z]+)")
_QUALITY = frozenset({
    "faster", "quicker", "slower", "better", "cleaner", "simpler", "smaller", "readable",
    "robust", "safer", "clearer", "nicer", "prettier", "shorter", "work", "pass", "compile",
    "strict", "stricter", "consistent", "more", "less", "sure", "easier", "testable"})
_QUESTION_START = re.compile(
    r"^\s*(?:why|what|how|where|which|who|when|is|are|does|do|did|can\s+you\s+explain"
    r"|could\s+you\s+explain)\b", re.IGNORECASE)
_NOT_ASKING_CHANGE = re.compile(r"just\s+asking|no\s+change\s+yet|don't\s+change|do\s+not\s+change",
                                re.IGNORECASE)

CONTRA_NAMED = 0.8
CONTRA_MATCHED = 0.65
EXTENDS = 0.6
BENIGN = 0.6


@dataclass(frozen=True)
class Classified:
    verdict: str                 # contradicts | extends | benign
    confidence: float
    example: str | None
    reason: str
    shared: int = 0              # subject terms shared with the record


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


def _is_question(prompt: str) -> bool:
    if _NOT_ASKING_CHANGE.search(prompt):
        return True
    for sentence in re.split(r"(?<=[.!])\s+|\n", prompt):
        if "?" in sentence and _QUESTION_START.match(sentence):
            return True
    return False


def classify(prompt: str, record: object, *, others_named: bool = False) -> Classified:
    """Contradiction, extension or benign, for one confirmed record (sp2 7.1)."""
    text = prompt.translate(_APOSTROPHES)
    lowered = text.lower()
    record_id = str(getattr(record, "id", ""))
    named = record_id in set(_ID.findall(text))
    wanted = stems(text)
    subject = stems(record_subject_text(record))
    title = stems(str(getattr(record, "title", "")))
    shared = wanted & subject
    if not named:
        needed = 3 if others_named else 1
        if len(shared) < needed or (len(shared) < 2 and not shared & title):
            return Classified("benign", BENIGN, None, "no subject in common", len(shared))
    examples = _example_texts(record)
    example = None
    if examples:
        scored = [(len(wanted & stems(full)), ex_id) for ex_id, full, _ in examples]
        best = max(scored)
        example = best[1] if best[0] > 0 else examples[0][0]
    then_terms = stems(" ".join(t for _, _, t in examples) + " "
                       + str((getattr(record, "fields", {}) or {}).get("statement") or ""))
    if _is_question(text):
        return Classified("benign", BENIGN, None, "a question, not a change", len(shared))
    contra = _CONTRA.search(lowered)
    make = None
    for match in _MAKE.finditer(lowered):
        target, result = stem(match.group(1)), match.group(2)
        if (target in shared or named) and result not in _QUALITY \
                and stem(result) not in then_terms and result not in STOPWORDS:
            make = match
            break
    tidy = _TIDY.search(lowered)
    if tidy and not _STRONG_CONTRA.search(lowered) and make is None:
        return Classified("benign", BENIGN, None, f"tidy-up ({tidy.group(0)})", len(shared))
    confidence = CONTRA_NAMED if named else CONTRA_MATCHED
    if make is not None:
        return Classified("contradicts", confidence, example,
                          f"'{make.group(0)}' replaces the confirmed behaviour", len(shared))
    if contra is not None:
        return Classified("contradicts", confidence, example,
                          f"'{contra.group(0)}' negates or replaces the confirmed behaviour",
                          len(shared))
    ext = _EXT.search(lowered)
    if ext is not None and wanted - subject:
        new = ", ".join(sorted(wanted - subject)[:3])
        return Classified("extends", EXTENDS, example,
                          f"'{ext.group(0)}' adds behaviour beside it ({new})", len(shared))
    return Classified("benign", BENIGN, None, "a mention without a change", len(shared))


def classify_all(prompt: str, records: Sequence[object]) -> dict[str, Classified]:
    """``classify`` for each record, keeping a flag only where the record is among the
    request's main subjects (shared terms at least 3/4 of the best flagged record's)."""
    ids_named = set(_ID.findall(prompt))
    out: dict[str, Classified] = {}
    for record in records:
        record_id = str(getattr(record, "id", ""))
        out[record_id] = classify(prompt, record,
                                  others_named=bool(ids_named) and record_id not in ids_named)
    flagged = [c.shared for i, c in out.items() if c.verdict != "benign" and i not in ids_named]
    best = max(flagged, default=0)
    for record_id, item in list(out.items()):
        if item.verdict != "benign" and record_id not in ids_named and item.shared < 0.75 * best:
            out[record_id] = Classified("benign", BENIGN, None,
                                        "another record is the request's subject", item.shared)
    return out


# --------------------------------------------------------------------------- coverage

PENALTY = 0.15
_LABEL = re.compile(r"^\s*(will|won't|wont|assumed|assume|assumption)\s*:\s*", re.IGNORECASE)


def coverage(premise: str, hypothesis: str) -> tuple[float, list[str]]:
    """Share of the hypothesis's terms found in the premise, minus ``PENALTY`` for each
    won't item or assumption line with no term in the premise. ``(score, reasons)``."""
    supported = stems(premise)
    if not supported:
        return 0.0, ["no owner words to compare"]
    reasons: list[str] = []
    wanted: set[str] = set()
    penalty = 0.0
    for line in hypothesis.splitlines():
        label = _LABEL.match(line)
        body = line[label.end():] if label else line
        line_terms = stems(body)
        wanted |= line_terms
        if label and label.group(1).lower() != "will" and line_terms \
                and not line_terms & supported:
            penalty += PENALTY
            reasons.append(f"unsupported {label.group(1).lower()}: {body.strip()[:60]}")
    if not wanted:
        return 0.0, ["nothing to compare"]
    covered = len(wanted & supported) / len(wanted)
    missing = sorted(wanted - supported)
    if missing:
        reasons.insert(0, "not in the owner's words: " + ", ".join(missing[:6]))
    score = max(0.0, round(covered - penalty, 4))
    return score, reasons


def overlap_share(a: Iterable[str], b: Iterable[str]) -> float:
    """Share of ``a`` found in ``b``."""
    a, b = set(a), set(b)
    return len(a & b) / len(a) if a else 0.0
