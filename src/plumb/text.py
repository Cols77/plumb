"""Cheap term matching for relevance and intent-change hints (spec 12.4)."""

from __future__ import annotations

import math
import re

_WORD_RE = re.compile(r"[a-z]{3,}")

STOPWORDS: frozenset[str] = frozenset("""
the and for are but not you all any can had her was one our out has have this that with from
they them then than there their what when where which while who whom why how its into also
been being were will would should could does did doing done each every some such only own
same very just more most other over under again further once here both few nor too off
your yours about above below after before between through during until upon via per out
let lets get got make made use used using onto these those itself himself herself
""".split()) - {"both"}

CHANGE_WORDS: frozenset[str] = frozenset({
    "instead", "no longer", "remove", "rename", "also", "change", "should now", "don't",
    "stop", "replace",
})


def terms(s: str) -> frozenset[str]:
    """Lowercase words of three or more letters, minus stopwords."""
    return frozenset(w for w in _WORD_RE.findall(s.lower()) if w not in STOPWORDS)


def overlap(a: frozenset[str], b: frozenset[str]) -> float:
    """``|a & b| / sqrt(|b|)``; 0 when either side is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(b))
