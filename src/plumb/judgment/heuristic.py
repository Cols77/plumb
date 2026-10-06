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
from plumb.text import CHANGE_WORDS

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
    version = "heuristic"

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
        """``change`` only for a contradiction or an extension of the record's confirmed
        examples or statement (sp2 7.1, C6); change words alone never flag."""
        from plumb.judgment.textjudge import classify_all

        digest = sha256_text(prompt)
        labels = classify_all(prompt, records)
        out: list[Judgment] = []
        for record in records:
            item = labels[record.id]
            if item.verdict == "benign":
                out.append(self._judgment("intent-change", record.id, "no-change",
                                          CLEAR_CONFIDENCE, [item.reason], digest,
                                          record.hash))
            else:
                reasons = [f"{item.verdict}: {item.reason}"]
                if item.example:
                    reasons.append(f"example {item.example}")
                out.append(self._judgment("intent-change", record.id, "change",
                                          FLAG_CONFIDENCE, reasons, digest, record.hash))
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

    # -- sp2 11.2
    def entailment(self, premise: str, hypothesis: str, *, subject: str,
                   claim_kind: str) -> Judgment:
        """Term coverage of the hypothesis by the premise, with penalties (sp2 8.1). The
        heuristic never labels its confidence ``high``: it never auto-approves (R8 B)."""
        from plumb.judgment.textjudge import coverage

        score, reasons = coverage(premise, hypothesis)
        verdict = "entailed" if score >= 0.8 else ("not-entailed" if score < 0.5 else "unsure")
        judgment = self._judgment("faithfulness", subject, verdict, 0.5, reasons or
                                  [f"term coverage {score:.2f}"], claim_kind,
                                  sha256_text(premise), sha256_text(hypothesis))
        return _with(judgment, probability=score, confidence_label="low", tier="escalate-llm")

    def contradiction(self, prompt: str, record: Record) -> Judgment:
        from plumb.judgment.textjudge import classify

        item = classify(prompt, record)
        reasons = [item.reason] + ([f"example {item.example}"] if item.example else [])
        return self._judgment("contradiction", record.id, item.verdict, item.confidence,
                              reasons, sha256_text(prompt), record.hash)

    def choose(self, question: str, options: Sequence[str], *, subject: str,
               context: str = "") -> Judgment:
        """The option whose terms the context covers best, when its lead is clear; else
        ``none`` (sp2 10.1: "no judgments available")."""
        from plumb.judgment.textjudge import overlap_share, stems

        wanted = stems(context + " " + question)
        scored = sorted(((overlap_share(stems(o), wanted), o) for o in options),
                        key=lambda item: (-item[0], item[1]))
        if not scored or scored[0][0] <= 0:
            return self._judgment("ownership", subject, "none", 0.0, ["no overlap"],
                                  question, list(options), sha256_text(context))
        lead = scored[0][0] - (scored[1][0] if len(scored) > 1 else 0.0)
        if lead < 0.2:
            return self._judgment("ownership", subject, "none", 0.0,
                                  [f"no clear lead ({scored[0][1]} by {lead:.2f})"],
                                  question, list(options), sha256_text(context))
        return self._judgment("ownership", subject, scored[0][1], 0.55,
                              [f"term overlap {scored[0][0]:.2f}, lead {lead:.2f}"],
                              question, list(options), sha256_text(context))

    def ask(self, question: str, context: str, *, subject: str, action: str) -> Judgment:
        """The heuristic has no yes/no judgment: ``unsure``, confidence 0."""
        return self._judgment(action, subject, "unsure", 0.0,
                              ["the heuristic does not answer yes/no questions"],
                              question, sha256_text(context))


def confidence_label(confidence: float) -> str:
    return "high" if confidence >= 0.9 else ("medium" if confidence >= 0.7 else "low")


def _with(judgment: Judgment, **changes: object) -> Judgment:
    import dataclasses

    return dataclasses.replace(judgment, **changes)  # type: ignore[arg-type]
