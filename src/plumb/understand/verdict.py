"""The verdict cascade (SR-182, INT-065): who answers "is this record supported by the owner's
words?" for the judge job, like ``links.repin_after_tests`` (SR-114).

JEV is asked first, when it is configured and calibrated. A probability at or above the
threshold calibrated on the owner's labels with no false accept (per record kind) is JEV's
verdict, marked ``by: jev``: auto-approval may use it. Below it, or with JEV not configured or
not answering, the judge model (``understand.judge_model``, haiku by default, sonnet allowed)
gives the verdict, marked ``by: model``: cards and the tidy job use it, auto-approval never does
(``plumb.judgment.verdict.refusal``). With neither reachable the verdict waits and the step says
so once (SR-174); nothing is decided by rule (INT-029). Which judge answered is in the log."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from plumb.contracts import Job, NoModel
from plumb.judgment.verdict import JEV, MODEL

STEP = "the verdict"
CLAIM_KIND = {"intent": "intent-readback", "requirement": "example-restatement"}
_UNSET: Any = object()


class Waiting(Exception):
    """No judge can be reached: the job waits. ``line`` is the one line to say so, or ''
    when it was said already in this session window."""

    def __init__(self, cause: str, line: str = "") -> None:
        super().__init__(cause)
        self.cause, self.line = cause, line


@dataclass(frozen=True)
class Cascaded:
    answer: dict[str, Any]
    dispatcher: str          # who answered: "jev", "<dispatcher>", or both


def open_jev(core: Any) -> Any:
    """The JEV backend, or None when JEV is not configured or has no key."""
    from plumb.judgment import JudgmentUnavailable, get_backend

    try:
        backend = get_backend(core, hook=False)
    except JudgmentUnavailable:
        return None
    return backend if getattr(backend, "name", "") == JEV else None


def model_gap(core: Any, model: str) -> str:
    """Why the judge model cannot be reached ('' when it can)."""
    from plumb.understand import dispatch

    try:
        return dispatch.configured(core, model=model).available() or ""
    except NoModel as exc:
        return str(exc)


def _premise_text(entry: Mapping[str, Any]) -> str:
    premise = entry.get("premise") or {}
    messages = [m for m in premise.get("messages") or () if isinstance(m, Mapping)]
    if not messages or all(m.get("partial") for m in messages):
        return ""            # the owner's words are not on file: nothing to ask JEV about
    return "\n\n".join(str(m.get("text") or "") for m in messages)


def jev_verdict(core: Any, entry: Mapping[str, Any], backend: Any, calibration: Any
                ) -> dict[str, Any] | None:
    """JEV's verdict on one entry when its probability clears the calibrated threshold for
    the entry's record kind, else None. Raises ``JudgmentUnavailable`` when JEV cannot answer."""
    from plumb.capture.autoapprove import _kind_threshold
    from plumb.capture.calibrate import _hypotheses
    from plumb.judgment.tiers import same_version

    kind = CLAIM_KIND.get(str(entry.get("kind")))
    record = core.index().get(str(entry.get("id")))
    premise = _premise_text(entry)
    threshold = _kind_threshold(calibration, kind) if kind else None
    if kind is None or record is None or threshold is None or not premise:
        return None
    _, parts = _hypotheses(core.index(), record)
    judgments = [backend.entailment(premise, part, subject=record.id, claim_kind=kind)
                 for part in parts]
    if not judgments or any(not j.backend.startswith("jev:") for j in judgments):
        return None
    version = judgments[0].backend.split(":", 1)[1]
    if not same_version(version, calibration.payload.get("model_version")):
        return None
    if any(j.verdict != "entailed" or (j.probability or 0.0) < threshold for j in judgments):
        return None
    p = round(min(j.probability or 0.0 for j in judgments), 6)
    return {"id": entry["id"], "verdict": "supported", "confidence": p, "beyond": [],
            "contradicts": [], "by": JEV, "judge": judgments[0].backend, "model": version}


def _ask_jev(core: Any, entries: list[Mapping[str, Any]], backend: Any
             ) -> tuple[dict[str, dict[str, Any]], str]:
    """``({id: verdict}, why JEV stopped)``: the entries JEV's answer clears; the rest go on."""
    from plumb.capture.calibrate import latest_calibration
    from plumb.judgment import JudgmentUnavailable

    calibration = latest_calibration(core)
    if backend is None:
        return {}, "JEV is not set up"
    if calibration is None:
        return {}, "JEV has no calibration"
    cleared: dict[str, dict[str, Any]] = {}
    for entry in entries:
        try:
            found = jev_verdict(core, entry, backend, calibration)
        except JudgmentUnavailable as exc:
            return cleared, str(exc)
        if found is not None:
            cleared[str(entry["id"])] = found
    return cleared, ""


def cascade(core: Any, job: Job, *, system: str, schema: Mapping[str, Any],
            on_step: Callable[[str], None] = lambda text: None, jev: Any = _UNSET,
            dispatcher: Any = None) -> Cascaded:
    """The judge job's answer: JEV's verdicts where it clears the threshold, the judge model's
    for the rest. Raises ``Waiting`` when records are left and no model can be reached."""
    from plumb.understand import dispatch

    entries = [r for r in job.inputs.get("records") or () if isinstance(r, Mapping)]
    backend = open_jev(core) if jev is _UNSET else jev
    cleared, jev_cause = _ask_jev(core, entries, backend)
    rest = [e for e in entries if str(e.get("id")) not in cleared]
    verdicts = list(cleared.values())
    names = ["jev"] if cleared else []
    extra: dict[str, Any] = {}
    if rest:
        model = str(core.config.understand.judge_model)
        try:
            dispatcher = dispatcher or dispatch.configured(core, model=model)
            gap = dispatcher.available() or ""
        except NoModel as exc:
            gap = str(exc)
        if gap:
            from plumb.judgment import waiting_line

            cause = f"{jev_cause}; {gap}" if jev_cause else gap
            raise Waiting(cause, waiting_line(core.root, STEP, cause) or "")
        sub = dataclasses.replace(job, inputs={**job.inputs, "records": rest})
        answer = dict(dispatcher.run(
            sub, system=system, schema=schema, on_step=on_step,
            user=json.dumps(sub.inputs, ensure_ascii=False, sort_keys=True, indent=1)))
        label = f"{getattr(dispatcher, 'name', 'model')}:{model}"
        for raw in answer.get("verdicts") or ():
            if isinstance(raw, Mapping):
                verdicts.append({**raw, "by": MODEL, "judge": label, "model": model})
        extra = {k: v for k, v in answer.items() if k != "verdicts"}
        names.append(str(getattr(dispatcher, "name", "model")))
    return Cascaded({**extra, "verdicts": verdicts}, "+".join(names) or "none")
