"""``plumb jev calibrate``: the backend measured on the owner's own decisions before any
auto-approval (R12.1, R13 Q1; sp2 8.3, SR-042, DEC-018).

The labelled set is built from the log, per record kind (claim kind ``intent-readback`` for
INT read-backs, ``example-restatement`` for requirements: their wording and every example):

- yes: records the owner confirmed (``by: owner`` or ``agent-relayed``) at their current
  content and never revoked;
- no (real): records the owner revoked, records edited after an auto-approval, and read-backs
  the owner rejected as a misreading of their words (a ``capture-error`` rejection, pinned at
  its hash; an ``intent-change`` rejection gets no label, SR-096, DEC-026 A);
- no (generated): deterministic variations of the yes records (a will flipped to won't, a
  flipped result, a changed number), labelled ``generated``.

Passing, per kind (R13 Q1, "mixed evidence"): at least ``calibration.min_items`` (20) of the
owner's own decisions, at least ``calibration.min_negatives`` (5) 'no' examples of which at
most half are generated, JEV wrongly accepting none of the 'no' examples (every generated one
included) at the chosen threshold, and at least half of the 'yes' records accepted. The
threshold is the lowest at which no 'no' example would have been accepted. The result is one
``calibration`` event with the real/generated split; the agent may run it, only the owner can
turn auto-approval on.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plumb.api import Core

KINDS = {"intent": "intent-readback", "requirement": "example-restatement"}
NOT_APPLICABLE = "heuristic: no auto-approval, calibration not applicable"
NO_JUDGMENTS = "no judgments available"
STEP = 0.001


class CalibrationUnavailable(RuntimeError):
    """No calibration is possible with this backend; nothing was written."""


@dataclass(frozen=True)
class Item:
    record: str
    kind: str                     # claim kind
    label: str                    # yes | no
    source: str                   # owner | revoked | edited-after-auto | generated
    premise: str
    hypotheses: tuple[str, ...]   # every part must be supported (R13 Q3)


@dataclass
class KindResult:
    items: int = 0                # real items: the owner's own decisions
    positives: int = 0
    real_negatives: int = 0
    generated_negatives: int = 0
    generated_counted: int = 0
    negatives: int = 0            # counted: real + generated up to half
    threshold: float | None = None
    false_accept: float = 0.0
    recall: float = 0.0
    passing: bool = False
    reasons: list[str] = field(default_factory=list)


def _hypotheses(index: Mapping[str, Any], record: Any,
                prompts: Any = None) -> tuple[str, tuple[str, ...]]:
    """``(premise, parts)``: the claim triage judges (SR-040), with the same premise (the
    owner's whole logged prompt when ``prompts`` has it). An INT's read-back is one claim; a
    requirement's wording and each of its examples are separate parts, all of which must be
    supported."""
    from plumb.capture.triage import claim

    _, premise, hypothesis = claim(index, record, prompts)
    if record.kind != "requirement":
        return premise, (hypothesis,)
    parts = [" ".join(str(record.fields.get("statement") or record.title).split())]
    parts += [f"given {e.given}, when {e.when}, then {e.then}" for e in record.examples]
    return premise, tuple(parts)


def _prompts(core: Core | None) -> Any:
    if core is None:
        return None
    from plumb.capture.triage import _Prompts

    return _Prompts(core)


def snapshot(index: Mapping[str, Any], record: Any, core: Core | None = None
             ) -> dict[str, Any]:
    """The read-back of ``record`` as it stands now (kind, premise, parts), kept in a
    rejection event so the rejected version can be labelled after a recapture."""
    premise, parts = _hypotheses(index, record, _prompts(core))
    return {"kind": KINDS.get(record.kind), "premise": premise, "hypotheses": list(parts)}


_NUMBER = re.compile(r"\d+")


def variations(item: Item) -> list[Item]:
    """The generated 'no' examples of a 'yes' item: a will flipped to won't, a flipped
    result, a changed number (each only when it changes the text)."""
    out: list[Item] = []

    def add(parts: Sequence[str], how: str) -> None:
        if tuple(parts) != item.hypotheses:
            out.append(Item(item.record, item.kind, "no", f"generated:{how}", item.premise,
                            tuple(parts)))

    text = list(item.hypotheses)
    flipped = [re.sub(r"(?m)^will: ", "won't: ", text[0], count=1)] + text[1:]
    add(flipped, "will-to-wont")
    result = [re.sub(r"\bthen (.+)$", r"then it is not true that \1", p, count=1)
              for p in text]
    if result == text:
        result = [f"not: {text[0]}"] + text[1:]
    add(result, "flipped-result")
    changed = [_NUMBER.sub(lambda m: str(int(m.group()) + 1), p, count=1) for p in text]
    add(changed, "changed-number")
    return out


def labelled_set(core: Core) -> list[Item]:
    from plumb.confirm import checked, remaining

    index = core.index()
    statuses = core.status()
    prompts = _prompts(core)
    revoked: set[str] = set()
    auto: set[str] = set()
    for entry, problem in checked(core):
        if problem is not None:
            continue
        ids = {str(r.get("id")) for r in entry.payload.get("records") or []
               if isinstance(r, Mapping)}
        if entry.kind == "revocation" and entry.payload.get("by") in ("owner",
                                                                      "agent-relayed"):
            revoked |= ids
        if entry.kind == "approval" and entry.payload.get("by") == "auto-jev":
            auto |= ids
    standing = remaining(core)
    items: list[Item] = []
    seen_rejected: set[tuple[str, str]] = set()
    for entry in core.events():
        if entry.kind != "rejection" or entry.payload.get("reason") != "capture-error":
            continue  # an intent change gets no label (SR-096, DEC-026 A)
        for pinned in entry.payload.get("records") or []:
            if not isinstance(pinned, Mapping):
                continue
            record_id, pin = str(pinned.get("id")), str(pinned.get("hash"))
            kind, premise = pinned.get("kind"), str(pinned.get("premise") or "")
            parts = tuple(str(p) for p in pinned.get("hypotheses") or [])
            if kind not in KINDS.values() or not premise.strip() or not parts \
                    or (record_id, pin) in seen_rejected:
                continue
            current = index.get(record_id)
            if current is not None and current.hash == pin and \
                    statuses[record_id].confirmation == "confirmed":
                continue  # the owner went on to confirm this very version
            seen_rejected.add((record_id, pin))
            items.append(Item(record_id, str(kind), "no", "rejected", premise, parts))
    for record_id in sorted(index):
        record = index[record_id]
        kind = KINDS.get(record.kind)
        if kind is None:
            continue
        premise, parts = _hypotheses(index, record, prompts)
        if not premise.strip():
            continue
        status = statuses[record_id]
        latest = standing.get(record_id) or []
        if record_id in revoked:
            items.append(Item(record_id, kind, "no", "revoked", premise, parts))
        elif record_id in auto and status.confirmation == "unconfirmed-edit":
            items.append(Item(record_id, kind, "no", "edited-after-auto", premise, parts))
        elif status.confirmation == "confirmed" and latest and \
                latest[-1][1] in ("owner", "agent-relayed"):
            items.append(Item(record_id, kind, "yes", "owner", premise, parts))
    generated = [v for item in items if item.label == "yes" for v in variations(item)]
    return items + generated


def score(backend: Any, item: Item) -> tuple[float, str]:
    """The probability that the owner's words support the whole item (the lowest over its
    parts), and the backend that answered."""
    lowest = 1.0
    used = ""
    for part in item.hypotheses:
        judgment = backend.entailment(item.premise, part, subject=item.record,
                                      claim_kind=item.kind)
        used = judgment.backend
        p = judgment.probability if judgment.probability is not None else 0.0
        p_true = p if judgment.verdict == "entailed" else 1.0 - p
        if judgment.verdict == "unsure":
            p_true = min(p, 1.0 - p)
        lowest = min(lowest, p_true)
    return round(lowest, 6), used


def measure(core: Core, items: Sequence[Item], scores: Sequence[float]) -> dict[str, KindResult]:
    config = core.config.calibration
    out: dict[str, KindResult] = {}
    for kind in KINDS.values():
        result = KindResult()
        pairs = [(i, s) for i, s in zip(items, scores, strict=True) if i.kind == kind]
        yes = [s for i, s in pairs if i.label == "yes"]
        real_no = [s for i, s in pairs if i.label == "no" and not i.source.startswith("gen")]
        gen_no = [s for i, s in pairs if i.label == "no" and i.source.startswith("gen")]
        result.positives = len(yes)
        result.real_negatives = len(real_no)
        result.generated_negatives = len(gen_no)
        result.items = len(yes) + len(real_no)
        result.generated_counted = min(len(gen_no), len(real_no))  # at most half
        result.negatives = len(real_no) + result.generated_counted
        negatives = real_no + gen_no
        if negatives:
            result.threshold = round(min(1.0 + STEP, max(negatives) + STEP), 6)
            accepted = [s for s in negatives if s >= result.threshold]
            result.false_accept = len(accepted) / len(negatives)
            result.recall = (sum(s >= result.threshold for s in yes) / len(yes)) if yes else 0.0
        if result.items < config.min_items:
            result.reasons.append(f"{result.items} of your decisions, {config.min_items} "
                                  "needed")
        if result.negatives < config.min_negatives:
            result.reasons.append(f"{result.negatives} 'no' examples counted (generated ones "
                                  f"up to half), {config.min_negatives} needed")
        if result.false_accept > config.max_false_accept:
            result.reasons.append(f"false accepts {result.false_accept:.2f}")
        if result.recall < 0.5:
            result.reasons.append(f"accepts {result.recall:.0%} of your confirmed records, "
                                  "half needed")
        result.passing = not result.reasons
        out[kind] = result
    return out


def calibrate(core: Core, *, backend: Any = None) -> tuple[Any, dict[str, KindResult]]:
    """Score the labelled set and append one ``calibration`` event. Raises
    ``CalibrationUnavailable`` (nothing written) without JEV."""
    from plumb.normalize import canonical_json, sha256_bytes

    if backend is None:
        from plumb.judgment import get_backend

        backend = get_backend(core, hook=False)
    name = str(getattr(backend, "name", "none"))
    if name in ("disabled", "none"):
        raise CalibrationUnavailable(NO_JUDGMENTS)
    if name != "jev":
        raise CalibrationUnavailable(NOT_APPLICABLE)
    items = labelled_set(core)
    scores: list[float] = []
    for item in items:
        value, used = score(backend, item)
        if not used.startswith("jev:"):
            raise CalibrationUnavailable(f"jev unavailable during calibration ({used} "
                                         "answered); no calibration written")
        scores.append(value)
    results = measure(core, items, scores)
    digest = sha256_bytes(canonical_json([[i.record, i.kind, i.label, i.source,
                                           list(i.hypotheses)] for i in items]))
    payload = {"backend": "jev", "model_version": getattr(backend, "version", None),
               "per_kind": {k: {key: getattr(r, key) for key in (
                   "items", "positives", "real_negatives", "generated_negatives",
                   "generated_counted", "negatives", "threshold", "false_accept", "recall",
                   "passing", "reasons")} for k, r in results.items()},
               "labelled_set_digest": digest}
    entry = core.log_append("events", "calibration", payload)
    return entry, results


def latest_calibration(core: Core) -> Any:
    entries = [e for e in core.events() if e.kind == "calibration"]
    return entries[-1] if entries else None


def result_lines(results: Mapping[str, Any], version: str | None) -> list[str]:
    lines = [f"calibration (jev {version or '?'}; per record kind)"]
    for kind, r in results.items():
        get = r.get if isinstance(r, Mapping) else (lambda k, r=r: getattr(r, k))
        threshold = get("threshold")
        lines.append(
            f"  {kind}: {'passing' if get('passing') else 'not passing'}; "
            f"{get('items')} of your decisions ({get('positives')} yes, "
            f"{get('real_negatives')} no), 'no' examples {get('negatives')} counted "
            f"({get('real_negatives')} real, {get('generated_counted')} of "
            f"{get('generated_negatives')} generated); threshold "
            f"{'-' if threshold is None else f'{threshold:.3f}'}, false accepts "
            f"{get('false_accept'):.2f}, recall {get('recall'):.2f}")
        for reason in get("reasons") or []:
            lines.append(f"    {reason}")
    return lines
