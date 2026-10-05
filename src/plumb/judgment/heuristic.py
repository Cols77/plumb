"""The default judgment backend: deterministic, no network, no key (spec 8.2).

- ``intent_change`` (spec 6.2 step 3): a record matched by ID, or by strong term overlap,
  together with change language in the prompt is flagged ``change``. The flag only asks the
  agent to read back and confirm; deciding is the agent's (the cascade's LLM tier).
- ``drift_triage``: ``cosmetic`` when the before and after texts are equal once comments,
  docstrings and whitespace are stripped (Python: equal ``ast.dump``), else ``material``.
- ``fidelity``: always ``unsure`` with tier ``escalate-llm``, so the packet goes to the host
  agent (R4).

Judgments are advisory: they order, filter and annotate, never confirm or freshen anything.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from plumb.contracts import FidelityPacket, Judgment, LinkState, Record
from plumb.judgment.tiers import Thresholds, route
from plumb.normalize import canonical_json, sha256_bytes, sha256_text
from plumb.text import CHANGE_WORDS, overlap, terms

STRONG_OVERLAP = 1.0   # the prompt hook's "strong match" (HOST STRONG_MATCH)
FLAG_CONFIDENCE = 0.6  # a flag is a hint for the agent: escalate-llm, never accept
CLEAR_CONFIDENCE = 0.6
PY_SUFFIXES = (".py", ".pyi")

_ID_RE = re.compile(r"(?<![A-Za-z0-9-])((?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})(?![0-9])")
_CHANGE_RE = re.compile(
    r"(?<![\w'])(" + "|".join(sorted((r"\s+".join(re.escape(w) for w in phrase.split())
                                      for phrase in CHANGE_WORDS), key=len, reverse=True))
    + r")(?![\w'])")
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})


def fingerprint(*parts: object) -> str:
    return sha256_bytes(canonical_json(list(parts)))


def change_words(prompt: str) -> list[str]:
    """Change phrases found in ``prompt`` as whole words, in order of appearance."""
    lowered = prompt.lower().translate(_APOSTROPHES)
    return [" ".join(m.group(1).split()) for m in _CHANGE_RE.finditer(lowered)]


def record_text(record: Record) -> str:
    from plumb.query import record_text as _record_text

    return _record_text(record)


def _strip_docstrings(tree: object) -> None:
    import ast

    for node in ast.walk(tree):  # type: ignore[arg-type]
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            node.body = body[1:] or [ast.Pass()]  # type: ignore[attr-defined]


def _python_shape(text: str) -> str | None:
    import ast

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    _strip_docstrings(tree)
    return ast.dump(tree, annotate_fields=False, include_attributes=False)


def is_cosmetic(before: str, after: str, path: str | None) -> bool:
    if path and path.endswith(PY_SUFFIXES):
        shape_before, shape_after = _python_shape(before), _python_shape(after)
        if shape_before is not None and shape_after is not None:
            return shape_before == shape_after
    return "".join(before.split()) == "".join(after.split())


class HeuristicBackend:
    """``JudgmentBackend`` with deterministic rules and no I/O."""

    name = "heuristic"

    def __init__(self, thresholds: Thresholds | None = None,
                 notices: Sequence[str] = ()) -> None:
        self.thresholds = thresholds or Thresholds()
        self.notices: tuple[str, ...] = tuple(notices)

    def _judgment(self, action: str, subject: str, verdict: str, confidence: float,
                  reasons: Sequence[str], *inputs: object) -> Judgment:
        return Judgment(action=action, subject=subject, verdict=verdict,  # type: ignore[arg-type]
                        confidence=confidence, tier=route(confidence, self.thresholds),
                        backend=self.name,
                        fingerprint=fingerprint(self.name, action, subject, *inputs),
                        reasons=tuple(reasons))

    def intent_change(self, prompt: str, records: Sequence[Record]) -> Sequence[Judgment]:
        named = set(_ID_RE.findall(prompt))
        words = change_words(prompt)
        wanted = terms(prompt)
        digest = sha256_text(prompt)
        out: list[Judgment] = []
        for record in records:
            reasons: list[str] = []
            if record.id in named:
                reasons.append(f"named {record.id}")
            else:
                score = overlap(wanted, terms(record_text(record)))
                if score >= STRONG_OVERLAP:
                    reasons.append(f"term overlap {score:.2f}")
            if reasons and words:
                reasons.append("change words: " + ", ".join(dict.fromkeys(words)))
                out.append(self._judgment("intent-change", record.id, "change",
                                          FLAG_CONFIDENCE, reasons, digest, record.hash))
            else:
                why = reasons or ["no ID or strong overlap"]
                if not words:
                    why.append("no change words")
                out.append(self._judgment("intent-change", record.id, "no-change",
                                          CLEAR_CONFIDENCE, why, digest, record.hash))
        return out

    def drift_triage(self, states: Sequence[LinkState],
                     texts: Mapping[str, tuple[str, str]]) -> Sequence[Judgment]:
        from plumb.hashing import target_path

        out: list[Judgment] = []
        for state in states:
            pair = texts.get(state.link.id)
            if pair is None:
                continue
            before, after = pair
            path = target_path(state.link.target)
            cosmetic = is_cosmetic(before, after, path)
            verdict = "cosmetic" if cosmetic else "material"
            reason = ("equal once comments, docstrings and whitespace are stripped" if cosmetic
                      else "the content differs beyond comments, docstrings and whitespace")
            out.append(self._judgment("drift-triage", state.link.id, verdict, 0.95, [reason],
                                      sha256_text(before), sha256_text(after)))
        return out

    def fidelity(self, packet: FidelityPacket) -> Judgment:
        return Judgment(action="fidelity", subject=packet.requirement, verdict="unsure",
                        confidence=0.5, tier="escalate-llm", backend=self.name,
                        fingerprint=packet.fingerprint,
                        reasons=("the heuristic does not judge fidelity; the host agent "
                                 "judges the packet",))
