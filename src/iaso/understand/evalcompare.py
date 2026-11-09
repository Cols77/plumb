"""``iaso understand eval --compare haiku,jev [--set PATH]``: the judges side by side on the
owner-labelled set ``evalset/judge_labelled.json``.

Each item is one record version with the owner's words and the confirmed records it must
agree with, and the verdict the owner's own answer implies. Every judge gives a verdict and a
score, its probability that the record is ``supported`` (Haiku: its confidence when it says
supported, one minus it otherwise; JEV: the probability of ``yes``). Scored per judge:
accuracy on supported-versus-not, false-accept rate, recall of supported, Brier score of the
score, and the lowest threshold at which no unsupported item is accepted, with the recall it
keeps. A judge that cannot be reached is an error naming it (INT-029): no fallback, no
heuristic."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iaso.contracts import DispatchError, Job, NoModel
from iaso.judgment.jev import JEV_CHOICE_QUESTION, JEV_CHOICES  # SR-183: moved there

HERE = Path(__file__).resolve().parent
DEFAULT_SET = HERE / "evalset" / "judge_labelled.json"
JUDGES = ("haiku", "jev", "jev-choice")
EXPECTED = ("supported", "beyond", "contradicts")
JEV_QUESTION = ("Is this record faithful to the owner's words and consistent with the "
                "confirmed records? yes means supported: it says what the owner said, with "
                "nothing added, dropped or changed, and it does not conflict with the "
                "confirmed records.")

class CompareError(Exception):
    """A judge could not answer; ``judge`` names it."""

    def __init__(self, judge: str, message: str) -> None:
        super().__init__(f"{judge}: {message}")
        self.judge = judge
        self.message = message


@dataclass(frozen=True)
class Verdict:
    label: str          # supported | beyond | contradicts | not-supported
    score: float        # the judge's probability that the record is supported


# --------------------------------------------------------------------------- the set


def load_set(path: Path | str | None = None) -> list[dict[str, Any]]:
    target = Path(path) if path else DEFAULT_SET
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CompareError("set", f"cannot read {target}: {exc}") from exc
    items = data.get("items") if isinstance(data, Mapping) else None
    if not isinstance(items, list) or not items:
        raise CompareError("set", f"{target} has no items")
    for n, item in enumerate(items):
        if not isinstance(item, Mapping) or item.get("expected") not in EXPECTED \
                or not str(item.get("record_text") or "").strip() \
                or not str(item.get("owner_words") or "").strip():
            raise CompareError("set", f"item {n} of {target} is not a labelled item")
    return [dict(i) for i in items]


def context_for(core: Any, item: Mapping[str, Any]) -> list[dict[str, str]]:
    """The confirmed records the item must agree with, as ``{id, status, text}``."""
    out: list[dict[str, str]] = []
    index = core.index() if core is not None else {}
    for rid in item.get("context_ids") or ():
        record = index.get(str(rid))
        if record is None:
            continue
        from iaso.understand.judge import record_text

        out.append({"id": str(rid), "status": "confirmed", "text": record_text(record)})
    return out


# --------------------------------------------------------------------------- the judges


class HaikuJudge:
    """The SP8 judge path: the judge prompt, the entry as the worker builds it, the schema."""

    name = "haiku"

    def __init__(self, dispatcher: Any, model: str) -> None:
        self.dispatcher = dispatcher
        self.model = model

    def judge(self, item: Mapping[str, Any], context: Sequence[Mapping[str, str]]) -> Verdict:
        from iaso.understand.evalrun import _real_answer

        text = str(item["record_text"])
        entry = {
            "id": str(item.get("record_id") or item["id"]),
            "hash": str(item.get("record_hash") or "sha256:" + hashlib.sha256(
                text.encode("utf-8")).hexdigest()),
            "kind": "intent" if item.get("kind") == "intent-readback" else str(item["kind"]),
            "text": text, "assumptions": [],
            "premise": {"messages": [{"digest": str(item.get("owner_words_digest") or ""),
                                      "text": str(item["owner_words"])}],
                        "question": "", "parent": None},
            "related": [dict(c) for c in context]}
        job = Job(id=f"compare-haiku-{item['id']}", kind="judge", schema="judge.v1",
                  inputs={"records": [entry]})
        try:
            answer = _real_answer(self.dispatcher, job, "judge")
        except DispatchError as exc:
            raise CompareError(self.name, f"unreachable ({exc.step}: {exc.message})") from exc
        for raw in answer.get("verdicts") or ():
            if isinstance(raw, Mapping) and str(raw.get("id")) == entry["id"]:
                label = str(raw.get("verdict") or "").lower()
                if label not in EXPECTED:
                    break
                try:
                    conf = min(1.0, max(0.0, float(raw.get("confidence"))))
                except (TypeError, ValueError):
                    conf = 1.0
                return Verdict(label, conf if label == "supported" else 1.0 - conf)
        raise CompareError(self.name, f"no usable verdict for {item['id']}")


class JevJudge:
    """One typed yes/no question through the JEV backend; no heuristic fallback. A "no" is
    mapped to not-supported (no second contradiction question: the verdict kinds beyond and
    contradicts are not told apart by one yes/no)."""

    name = "jev"

    def __init__(self, backend: Any) -> None:
        self.backend = backend

    @property
    def model(self) -> str:
        return str(self.backend.version)

    @staticmethod
    def prompt(item: Mapping[str, Any], context: Sequence[Mapping[str, str]]) -> str:
        lines = [f"Owner's words:\n{item['owner_words']}\n",
                 f"Record {item.get('record_id') or item['id']} ({item.get('kind')}):\n"
                 f"{item['record_text']}\n"]
        if context:
            lines.append("Confirmed records:\n" + "\n".join(
                f"{c['id']}: {c['text']}" for c in context) + "\n")
        return "\n".join(lines)

    def unreachable(self) -> CompareError:
        err = getattr(getattr(self.backend, "client", None), "last_error", None)
        return CompareError(self.name, f"unreachable ({err or 'no answer'})")

    def judge(self, item: Mapping[str, Any], context: Sequence[Mapping[str, str]]) -> Verdict:
        p = self.backend.yes_probability(JEV_QUESTION, self.prompt(item, context),
                                         true="supported", false="not supported")
        if p is None:
            raise self.unreachable()
        return Verdict("supported" if p >= 0.5 else "not-supported", p)


class JevChoiceJudge(JevJudge):
    """JEV asked one choice over the three verdicts: the label is JEV's choice and the score
    its probability of ``supported``, so beyond and contradicts are told apart."""

    name = "jev-choice"

    def judge(self, item: Mapping[str, Any], context: Sequence[Mapping[str, str]]) -> Verdict:
        from iaso.judgment.model import JudgmentQuestion

        question = JudgmentQuestion.choice(JEV_CHOICE_QUESTION, JEV_CHOICES)
        record = self.backend._ask([("verdict", question)], self.prompt(item, context))
        if record is None:
            raise self.unreachable()
        answer = record.answers["verdict"]
        label = str(answer.value)
        p = answer.probabilities.get("supported", 1.0 if label == "supported" else 0.0)
        return Verdict(label if label in EXPECTED else "not-supported", float(p))


def open_judges(core: Any, names: Sequence[str]) -> list[Any]:
    """The named judges, or a CompareError naming the one that cannot be had."""
    judges: list[Any] = []
    for name in names:
        if name == "haiku":
            from iaso.understand.dispatch import configured

            try:
                dispatcher = configured(core, model=core.config.understand.judge_model)
            except NoModel as exc:
                raise CompareError("haiku", f"no model ({exc})") from exc
            reason = dispatcher.available()
            if reason:
                raise CompareError("haiku", f"unavailable ({reason})")
            judges.append(HaikuJudge(dispatcher, core.config.understand.judge_model))
        elif name in ("jev", "jev-choice") or name.startswith("decide:"):
            from iaso.judgment import JudgmentUnavailable
            from iaso.judgment.jev import JevBackend, open_jev
            from iaso.judgment.tiers import Thresholds

            thresholds = Thresholds.from_config(core.config.judgment.jev)
            try:
                backend = open_jev(core, core.config, hook=False, thresholds=thresholds)
            except JudgmentUnavailable as exc:
                raise CompareError(name, str(exc)) from exc
            if not isinstance(backend, JevBackend):
                raise CompareError(name, "no decisions key")
            if name.startswith("decide:"):
                # Another decision model behind the same Decisions endpoint and key.
                backend = JevBackend(core, backend.client, model=name.split(":", 1)[1],
                                     validated_against=None, thresholds=thresholds)
                judge = JevJudge(backend)
                judge.name = name
                judges.append(judge)
            else:
                judges.append(JevJudge(backend) if name == "jev" else JevChoiceJudge(backend))
        else:
            raise CompareError(name, f"unknown judge (use {', '.join(JUDGES)} or decide:<model>)")
    return judges


# --------------------------------------------------------------------------- scoring


def score_judge(items: Sequence[Mapping[str, Any]],
                verdicts: Sequence[Verdict]) -> dict[str, Any]:
    """Accuracy, false-accept rate, recall of supported, Brier score, and the best threshold
    at which no unsupported item is accepted (an item is accepted when its score is at or
    above the threshold) with the recall it keeps."""
    truth = [i["expected"] == "supported" for i in items]
    said = [v.label == "supported" for v in verdicts]
    pos = [s for s, t in zip((v.score for v in verdicts), truth) if t]
    neg = [s for s, t in zip((v.score for v in verdicts), truth) if not t]
    n = len(items)
    correct = sum(1 for a, t in zip(said, truth) if a == t)
    false_accepts = sum(1 for a, t in zip(said, truth) if a and not t)
    kept = sum(1 for a, t in zip(said, truth) if a and t)
    brier = sum((v.score - (1.0 if t else 0.0)) ** 2 for v, t in zip(verdicts, truth)) / n
    ceiling = max(neg) if neg else None
    above = sorted(s for s in pos if ceiling is None or s > ceiling)
    threshold = above[0] if above else None
    return {
        "n": n, "supported": len(pos), "unsupported": len(neg),
        "accuracy": correct / n,
        "false_accept": (false_accepts / len(neg)) if neg else 0.0,
        "recall": (kept / len(pos)) if pos else 0.0,
        "brier": brier,
        "threshold": threshold,
        "threshold_recall": (len(above) / len(pos)) if pos and threshold is not None else 0.0}


def compare(judges: Sequence[Any], items: Sequence[Mapping[str, Any]],
            contexts: Sequence[Sequence[Mapping[str, str]]]) -> dict[str, dict[str, Any]]:
    """Run every judge over every item. Any judge failure raises (no partial comparison)."""
    out: dict[str, dict[str, Any]] = {}
    for judge in judges:
        verdicts = [judge.judge(item, ctx) for item, ctx in zip(items, contexts)]
        out[judge.name] = {"model": judge.model, "verdicts": verdicts,
                           "metrics": score_judge(items, verdicts)}
    return out


def table(results: Mapping[str, Mapping[str, Any]]) -> str:
    def pct(x: float) -> str:
        return f"{100 * x:.0f}%"

    names = list(results)
    rows = [("measure", *names)]
    m = {k: results[k]["metrics"] for k in names}
    rows.append(("items (supported/not)", *[f"{m[k]['n']} ({m[k]['supported']}/"
                                           f"{m[k]['unsupported']})" for k in names]))
    rows.append(("accuracy", *[pct(m[k]["accuracy"]) for k in names]))
    rows.append(("false-accept rate", *[pct(m[k]["false_accept"]) for k in names]))
    rows.append(("recall of supported", *[pct(m[k]["recall"]) for k in names]))
    rows.append(("Brier score (lower is better)", *[f"{m[k]['brier']:.3f}" for k in names]))
    rows.append(("best threshold, no false accept", *[
        "none" if m[k]["threshold"] is None else f"{m[k]['threshold']:.3f}" for k in names]))
    rows.append(("recall kept at that threshold", *[pct(m[k]["threshold_recall"])
                                                   for k in names]))
    width = [max(len(r[c]) for r in rows) for c in range(len(rows[0]))]
    return "\n".join("  ".join(cell.ljust(w) for cell, w in zip(r, width)).rstrip()
                     for r in rows)


def log_runs(core: Any, items: Sequence[Mapping[str, Any]],
             results: Mapping[str, Mapping[str, Any]]) -> None:
    """One ``eval-run`` entry per judge, through iaso's own log."""
    from iaso.understand.evalrun import prompt_digest

    for name, res in results.items():
        cases = [{"kind": "judge-compare", "case": item["id"],
                  "passed": (v.label == "supported") == (item["expected"] == "supported"),
                  "false_gap": False, "expected": item["expected"], "verdict": v.label,
                  "score": round(v.score, 6), "calibration": item.get("calibration", "none")}
                 for item, v in zip(items, res["verdicts"])]
        core.log_append("events", "eval-run", {
            "model": f"{name}:{res['model']}", "prompt_digest": prompt_digest(),
            "cases": cases, "passed": sum(1 for c in cases if c["passed"]),
            "false_gap_rate": 0.0, "compare": True, "judge": name,
            "metrics": res["metrics"]})


def run_compare(core: Any, names: Sequence[str], set_path: str | None,
                judges: Sequence[Any] | None = None) -> str:
    """The whole comparison: returns the printed table. Raises CompareError."""
    items = load_set(set_path)
    chosen = list(judges) if judges is not None else open_judges(core, names)
    contexts = [context_for(core, i) for i in items]
    results = compare(chosen, items, contexts)
    log_runs(core, items, results)
    return table(results)
