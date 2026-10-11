"""``plumb understand eval --repin --compare sonnet,haiku,sonnet-x3,jev [--set PATH]``: the
repin meaning judges side by side on the agreed labelled set ``evalset/repin_labelled.json``.

Each item is one stale link (``SR-064#10``) and whether its change leaves everything the
requirement relies on as it was (``unchanged``) or not (``changed``). The judge's inputs are
rebuilt exactly as ``plumb.links.repin_after_tests`` builds them: the requirement text, the
end as the pin saw it and as it is now, and their diff. An item whose inputs cannot be rebuilt
here (the pinned version is not in git, or the link was repinned since and shows no change) is
skipped and named, never guessed.

Judges: ``sonnet`` and ``haiku`` (the production ``ModelMeaningJudge`` through the configured
dispatcher; the verdict alone counts), ``sonnet-x3`` (Sonnet asked three times; the score is
the share of ``unchanged`` answers and it says unchanged only on 3/3) and ``jev`` (one
requirement-aware yes/no through JEV; the score is the probability of yes). Scored per judge:
accuracy, the FALSE REPIN rate (said unchanged when the label is changed: the error that
repins a link whose requirement is no longer met), recall of unchanged, and for a scored judge
the lowest threshold at which nothing changed is repinned, with the recall it keeps. A judge
that cannot be reached is an error naming it (INT-029): no fallback."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plumb.contracts import NoModel
from plumb.understand import repin
from plumb.understand.evalcompare import CompareError, Verdict

HERE = Path(__file__).resolve().parent
DEFAULT_SET = HERE / "evalset" / "repin_labelled.json"
JUDGES = ("sonnet", "haiku", "sonnet-x3", "jev")
LABELS = ("unchanged", "changed")
REPEATS = 3
JEV_QUESTION = repin.JEV_QUESTION   # the question production's JEV tier asks (SR-114)


@dataclass(frozen=True)
class Case:
    """One item with the judge's inputs rebuilt."""

    item: Mapping[str, Any]
    requirement: str
    link_id: str
    link_kind: str
    path: str
    before: str
    after: str
    diff: str

    @property
    def label(self) -> str:
        return str(self.item["label"])


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
        link = str(item.get("link") or "") if isinstance(item, Mapping) else ""
        record_id, _, position = link.partition("#")
        if not isinstance(item, Mapping) or item.get("label") not in LABELS \
                or not record_id or not position.isdigit():
            raise CompareError("set", f"item {n} of {target} is not a labelled link")
    return [dict(i) for i in items]


def build_case(core: Any, item: Mapping[str, Any]) -> Case | str:
    """The inputs ``repin_after_tests`` would give the judge for this link, or why they
    cannot be rebuilt here. ``"pin": "HEAD"`` takes the link's pin as committed at HEAD (the
    label was made against it), not one refreshed in the working tree since."""
    from plumb.hashing import target_path
    from plumb.links import _git_text, end_texts
    from plumb.model import parse_record
    from plumb.understand.judge import record_text
    from plumb.understand.repin import diff

    record_id, _, position = str(item["link"]).partition("#")
    record = core.index().get(record_id)
    if record is None:
        return f"no record {record_id}"
    if int(position) >= len(record.links):
        return f"{record_id} has no link #{position}"
    link = record.links[int(position)]
    if link.target.record is not None:
        return "it points at a record, not code"
    if str(item.get("pin") or "") == "HEAD":
        text = _git_text(Path(core.root), ["show", f"HEAD:{record.path}"])
        try:
            committed = parse_record(text, record.path) if text is not None else None
        except Exception:  # noqa: BLE001 - an unreadable committed record cannot be rebuilt
            committed = None
        if committed is None or int(position) >= len(committed.links) \
                or committed.links[int(position)].target != link.target:
            return "the link as committed at HEAD could not be read"
        link = dataclasses.replace(link, pin=committed.links[int(position)].pin)
    texts = end_texts(Path(core.root), link)
    if texts is None:
        return "the pinned version of the end is not in git"
    path = target_path(link.target) or ""
    change = diff(texts[0], texts[1], path)
    if not change:
        return "no change since the pin (repinned since it was labelled?)"
    return Case(item=item,
                requirement=f"{record.id}: {record.title}\n{record_text(record)}",
                link_id=link.id, link_kind=link.kind, path=path,
                before=texts[0], after=texts[1], diff=change)


# --------------------------------------------------------------------------- the judges


class MeaningJudge:
    """The production repin judge (``ModelMeaningJudge``) asked ``times`` times per link. The
    verdict alone counts; with several asks the score is the share of ``unchanged`` answers
    and the verdict is unchanged only when every ask says so."""

    def __init__(self, name: str, judge: Any, model: str, times: int = 1) -> None:
        self.name, self.inner, self.model, self.times = name, judge, model, times
        self.scored = times > 1

    def judge(self, case: Case) -> Verdict:
        from plumb.understand.repin import DIFF_MAX

        if len(case.diff) > DIFF_MAX:          # production refuses: nothing is repinned
            return Verdict("changed", 0.0)
        yes = 0
        for _ in range(self.times):
            meaning = self.inner.same_meaning(
                requirement=case.requirement, link_id=case.link_id, link_kind=case.link_kind,
                path=case.path, before=case.before, after=case.after)
            if meaning.unchanged is None:
                raise CompareError(self.name, f"no verdict for {case.link_id}: "
                                              f"{meaning.reason}")
            yes += 1 if meaning.unchanged else 0
        return Verdict("unchanged" if yes == self.times else "changed", yes / self.times)


class JevRepinJudge:
    """One requirement-aware yes/no through JEV, the requirement and the diff in the prefix."""

    name = "jev"
    scored = True

    def __init__(self, backend: Any) -> None:
        self.backend = backend

    @property
    def model(self) -> str:
        return str(getattr(self.backend, "version", None) or self.backend.model)

    @staticmethod
    def prompt(case: Case) -> str:
        return repin.jev_prompt(requirement=case.requirement, link_id=case.link_id,
                                link_kind=case.link_kind, path=case.path, change=case.diff)

    def judge(self, case: Case) -> Verdict:
        from plumb.judgment import JudgmentUnavailable

        try:
            p = repin.jev_probability(self.backend, self.prompt(case))
        except JudgmentUnavailable as exc:
            raise CompareError(self.name, f"unreachable ({exc})") from exc
        return Verdict("unchanged" if p >= 0.5 else "changed", p)


def _model_judge(core: Any, name: str, model: str, times: int) -> MeaningJudge:
    from plumb.understand.dispatch import configured
    from plumb.understand.repin import ModelMeaningJudge

    try:
        dispatcher = configured(core, model=model)
    except NoModel as exc:
        raise CompareError(name, f"no model ({exc})") from exc
    reason = dispatcher.available()
    if reason:
        raise CompareError(name, f"unavailable ({reason})")
    return MeaningJudge(name, ModelMeaningJudge(dispatcher), model, times)


def open_judges(core: Any, names: Sequence[str]) -> list[Any]:
    """The named judges, or a CompareError naming the one that cannot be had."""
    judges: list[Any] = []
    for name in names:
        if name in ("sonnet", "haiku"):
            judges.append(_model_judge(core, name, name, 1))
        elif name == "sonnet-x3":
            judges.append(_model_judge(core, name, "sonnet", REPEATS))
        elif name == "jev":
            from plumb.judgment import JudgmentUnavailable
            from plumb.judgment.jev import JevBackend, open_jev
            from plumb.judgment.tiers import Thresholds

            thresholds = Thresholds.from_config(core.config.judgment.jev)
            try:
                backend = open_jev(core, core.config, hook=False, thresholds=thresholds)
            except JudgmentUnavailable as exc:
                raise CompareError(name, str(exc)) from exc
            if not isinstance(backend, JevBackend):
                raise CompareError(name, "no decisions key")
            judges.append(JevRepinJudge(backend))
        else:
            raise CompareError(name, f"unknown judge (use {', '.join(JUDGES)})")
    return judges


# --------------------------------------------------------------------------- scoring


def score_judge(cases: Sequence[Case], verdicts: Sequence[Verdict],
                scored: bool) -> dict[str, Any]:
    """Accuracy, false-repin rate (of the changed items, the share said unchanged), recall of
    unchanged, and for a scored judge the lowest threshold (repin at or above it) at which no
    changed item is repinned, with the share of unchanged items it keeps."""
    truth = [c.label == "unchanged" for c in cases]
    said = [v.label == "unchanged" for v in verdicts]
    pos = [v.score for v, t in zip(verdicts, truth) if t]
    neg = [v.score for v, t in zip(verdicts, truth) if not t]
    n = len(cases)
    correct = sum(1 for a, t in zip(said, truth) if a == t)
    false_repins = sum(1 for a, t in zip(said, truth) if a and not t)
    kept = sum(1 for a, t in zip(said, truth) if a and t)
    threshold: float | None = None
    threshold_recall: float | None = None
    if scored:
        ceiling = max(neg) if neg else None
        above = sorted(s for s in pos if ceiling is None or s > ceiling)
        threshold = above[0] if above else None
        threshold_recall = (len(above) / len(pos)) if pos and above else 0.0
    return {
        "n": n, "unchanged": len(pos), "changed": len(neg),
        "accuracy": correct / n if n else 0.0,
        "false_repin": (false_repins / len(neg)) if neg else 0.0,
        "false_repins": false_repins,
        "recall": (kept / len(pos)) if pos else 0.0,
        "scored": scored, "threshold": threshold, "threshold_recall": threshold_recall}


def compare(judges: Sequence[Any], cases: Sequence[Case]) -> dict[str, dict[str, Any]]:
    """Run every judge over every case. Any judge failure raises (no partial comparison)."""
    out: dict[str, dict[str, Any]] = {}
    for judge in judges:
        verdicts = [judge.judge(case) for case in cases]
        out[judge.name] = {"model": judge.model, "verdicts": verdicts,
                           "metrics": score_judge(cases, verdicts,
                                                  bool(getattr(judge, "scored", False)))}
    return out


def table(results: Mapping[str, Mapping[str, Any]], cases: Sequence[Case] = (),
          skipped: Sequence[tuple[str, str]] = ()) -> str:
    def pct(x: float) -> str:
        return f"{100 * x:.0f}%"

    names = list(results)
    m = {k: results[k]["metrics"] for k in names}
    rows = [("measure", *names)]
    rows.append(("items (unchanged/changed)", *[f"{m[k]['n']} ({m[k]['unchanged']}/"
                                               f"{m[k]['changed']})" for k in names]))
    rows.append(("accuracy", *[pct(m[k]["accuracy"]) for k in names]))
    rows.append(("FALSE REPIN rate", *[f"{pct(m[k]['false_repin'])} ({m[k]['false_repins']})"
                                       for k in names]))
    rows.append(("recall of unchanged", *[pct(m[k]["recall"]) for k in names]))
    rows.append(("best threshold, no false repin", *[
        "-" if not m[k]["scored"] else "none" if m[k]["threshold"] is None
        else f"{m[k]['threshold']:.3f}" for k in names]))
    rows.append(("recall kept at that threshold", *[
        "-" if not m[k]["scored"] else pct(m[k]["threshold_recall"]) for k in names]))
    width = [max(len(r[c]) for r in rows) for c in range(len(rows[0]))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(r, width)).rstrip() for r in rows]
    for name in names:
        wrong = [c.link_id for c, v in zip(cases, results[name]["verdicts"])
                 if c.label == "changed" and v.label == "unchanged"]
        if wrong:
            lines.append(f"{name} false repins: {', '.join(wrong)}")
    for link, why in skipped:
        lines.append(f"skipped {link}: {why}")
    return "\n".join(lines)


def log_runs(core: Any, cases: Sequence[Case], results: Mapping[str, Mapping[str, Any]],
             skipped: Sequence[tuple[str, str]] = ()) -> None:
    """One ``eval-run`` entry per judge, through plumb's own log."""
    from plumb.understand.evalrun import prompt_digest

    for name, res in results.items():
        rows = [{"kind": "repin-compare", "case": c.item.get("id") or c.link_id,
                 "link": c.link_id,
                 "passed": (v.label == "unchanged") == (c.label == "unchanged"),
                 "false_gap": False, "expected": c.label, "verdict": v.label,
                 "score": round(v.score, 6)}
                for c, v in zip(cases, res["verdicts"])]
        core.log_append("events", "eval-run", {
            "model": f"{name}:{res['model']}", "prompt_digest": prompt_digest(),
            "cases": rows, "passed": sum(1 for r in rows if r["passed"]),
            "false_gap_rate": 0.0, "compare": True, "set": "repin", "judge": name,
            "metrics": res["metrics"],
            "skipped": [{"link": link, "why": why} for link, why in skipped]})


def run_compare(core: Any, names: Sequence[str], set_path: str | None,
                judges: Sequence[Any] | None = None) -> str:
    """The whole comparison: returns the printed table. Raises CompareError."""
    items = load_set(set_path)
    chosen = list(judges) if judges is not None else open_judges(core, names)
    cases: list[Case] = []
    skipped: list[tuple[str, str]] = []
    for item in items:
        built = build_case(core, item)
        if isinstance(built, Case):
            cases.append(built)
        else:
            skipped.append((str(item["link"]), built))
    if not cases:
        raise CompareError("set", "no item's inputs could be rebuilt here: " + "; ".join(
            f"{link}: {why}" for link, why in skipped))
    results = compare(chosen, cases)
    log_runs(core, cases, results, skipped)
    return table(results, cases, skipped)
