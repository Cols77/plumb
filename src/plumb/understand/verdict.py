"""The verdict cascade (SR-182, SR-242, INT-065): who answers "is this record supported by the
owner's words?" for the judge job, like ``links.repin_after_tests`` (SR-114).

JEV is asked first for every record with a premise and a claim kind, calibrated or not, and its
score is logged with the verdict. It clears a record only with a passing same-version
calibration and every part strictly above max(0.9, the threshold calibrated on the owner's
labels with no false accept); a cleared record that may take the fast track
(``capture.autoapprove.fast_track``) is JEV's verdict, marked ``by: jev``, and the judge job
approves it ``by: auto-jev``. Every other record goes to the judge model
(``understand.judge_model``, haiku by default, sonnet allowed), marked ``by: model``: a model
verdict never takes the fast track (``plumb.judgment.verdict.refusal``). With neither reachable
the verdict waits and the step says so once (SR-174); nothing is decided by rule (INT-029).
Which judge answered is in the log."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from plumb.contracts import DispatchError, Job, NoModel
from plumb.judgment.verdict import JEV, MODEL

STEP = "the verdict"
CLAIM_KIND = {"intent": "intent-readback", "requirement": "example-restatement"}
INPUT_MAX = 60_000        # characters the judge model is given at most
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
    left: tuple[Mapping[str, Any], ...] = ()   # SR-185: the entries nobody could judge
    line: str = ""           # SR-185: the once-per-window line saying they wait


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
    """JEV's scores of one entry, or None when it has no claim kind or no premise, or JEV did
    not answer as JEV: ``{score, clears, judge, model_version, confidence, confidence_label,
    fingerprints, parts, calibration, threshold, claim_kind}``. ``clears`` only with a passing
    calibration of the same version and question form, and every part strictly above
    max(0.9, its threshold) (SR-242 EX-5). Raises ``JudgmentUnavailable`` when JEV cannot
    answer."""
    from plumb.capture.autoapprove import JEV_FLOOR, _kind_threshold
    from plumb.capture.calibrate import _hypotheses, form_gap
    from plumb.judgment.tiers import same_version

    kind = CLAIM_KIND.get(str(entry.get("kind")))
    record = core.index().get(str(entry.get("id")))
    premise = _premise_text(entry)
    if kind is None or record is None or not premise:
        return None
    _, parts = _hypotheses(core.index(), record)
    judgments = [backend.entailment(premise, part, subject=record.id, claim_kind=kind)
                 for part in parts]
    if not judgments or any(not j.backend.startswith("jev:") for j in judgments):
        return None
    version = judgments[0].backend.split(":", 1)[1]
    threshold = None
    if calibration is not None and not form_gap(core, calibration):   # SR-183: same form
        threshold = _kind_threshold(calibration, kind)
    current = threshold is not None and same_version(
        version, calibration.payload.get("model_version"))
    floor = max(JEV_FLOOR, threshold or 0.0)
    weakest = min(judgments, key=lambda j: j.probability or 0.0)
    return {"score": round(weakest.probability or 0.0, 6),
            "clears": current and all(j.verdict == "entailed" and (j.probability or 0.0) > floor
                                      for j in judgments),
            "judge": judgments[0].backend, "model_version": version,
            "confidence": weakest.confidence, "confidence_label": weakest.confidence_label,
            "fingerprints": [j.fingerprint for j in judgments], "parts": len(judgments),
            "calibration": calibration.digest if calibration is not None else None,
            "threshold": threshold, "claim_kind": kind}


def _ask_jev(core: Any, entries: list[Mapping[str, Any]], backend: Any
             ) -> tuple[dict[str, dict[str, Any]], str]:
    """``({id: JEV's scores}, why JEV stopped)``: JEV is asked whenever a backend exists; a
    missing or other-form calibration only means nothing clears."""
    from plumb.capture.calibrate import latest_calibration
    from plumb.judgment import JudgmentUnavailable

    if backend is None:
        return {}, "JEV is not set up"
    calibration = latest_calibration(core)
    scored: dict[str, dict[str, Any]] = {}
    for entry in entries:
        try:
            found = jev_verdict(core, entry, backend, calibration)
        except JudgmentUnavailable as exc:
            return scored, str(exc)
        if found is not None:
            scored[str(entry["id"])] = found
    return scored, ""


def _fast(core: Any, entries: list[Mapping[str, Any]], scored: Mapping[str, Mapping[str, Any]]
          ) -> dict[str, Mapping[str, Any]]:
    """The entries JEV clears that may take the fast track (SR-248): no model is asked."""
    from plumb.capture.autoapprove import fast_track

    index = core.index()
    out: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        jev = scored.get(str(entry.get("id")))
        record = index.get(str(entry.get("id")))
        if jev and jev["clears"] and record is not None and fast_track(core, record, jev):
            out[record.id] = jev
    return out


def _held_line(core: Any, cause: str) -> str:
    """SR-245 EX-3: with the owner's switch on and JEV unreachable, the fast track says once
    that the approval holds; nothing is approved by rule."""
    from plumb.capture.autoapprove import auto_approve_state, jev_ready

    if not auto_approve_state(core).configured:
        return ""
    from plumb.judgment import waiting_line

    ready, why = jev_ready(core)
    return waiting_line(core.root, "auto-approval", cause if ready else why) or ""


def cascade(core: Any, job: Job, *, system: str, schema: Mapping[str, Any],
            on_step: Callable[[str], None] = lambda text: None, jev: Any = _UNSET,
            dispatcher: Any = None) -> Cascaded:
    """The judge job's answer: JEV's verdicts where it clears and the fast track takes the
    record, the judge model's for the rest (with JEV's scores when JEV gave some). Raises
    ``Waiting`` when no record has a verdict and the model cannot judge them; otherwise the
    records it could not judge are ``left`` and ``line`` says so once (SR-185)."""
    from plumb.understand import dispatch

    entries = [r for r in job.inputs.get("records") or () if isinstance(r, Mapping)]
    backend = open_jev(core) if jev is _UNSET else jev
    scored, jev_cause = _ask_jev(core, entries, backend)
    fast = _fast(core, entries, scored)
    held = _held_line(core, jev_cause) if jev_cause else ""
    rest = [e for e in entries if str(e.get("id")) not in fast]
    verdicts: list[dict[str, Any]] = [
        {"id": i, "verdict": "supported", "confidence": j["score"], "beyond": [],
         "contradicts": [], "by": JEV, "judge": j["judge"], "model": j["model_version"],
         "jev": dict(j)} for i, j in fast.items()]
    names = ["jev"] if fast else []
    extra: dict[str, Any] = {}
    left, why = [], ""
    if rest:
        model = str(core.config.understand.judge_model)
        try:
            dispatcher = dispatcher or dispatch.configured(core, model=model)
            gap = dispatcher.available() or ""
        except NoModel as exc:
            gap = str(exc)
        sub = dataclasses.replace(job, inputs={**job.inputs, "records": rest})
        user = json.dumps(sub.inputs, ensure_ascii=False, sort_keys=True, indent=1)
        if not gap and len(user) > INPUT_MAX:     # SR-245 EX-8: the size is named
            gap = f"the records are too large for the judge model ({len(user)} characters)"
        try:
            if gap:
                raise DispatchError("start", f"{jev_cause}; {gap}" if jev_cause else gap)
            answer = dict(dispatcher.run(sub, system=system, schema=schema, on_step=on_step,
                                         user=user))
        except DispatchError as exc:     # SR-185: these records wait; the others go on
            left, why = rest, exc.message
        else:
            label = f"{getattr(dispatcher, 'name', 'model')}:{model}"
            for raw in answer.get("verdicts") or ():
                if isinstance(raw, Mapping):
                    got = scored.get(str(raw.get("id")))   # JEV's score is logged with it
                    verdicts.append({**raw, "by": MODEL, "judge": label, "model": model,
                                     **({"jev": dict(got)} if got else {})})
            extra = {k: v for k, v in answer.items() if k != "verdicts"}
            names.append(str(getattr(dispatcher, "name", "model")))
    line = held
    if left:
        from plumb.judgment import waiting_line

        why = f"{', '.join(str(e.get('id')) for e in left)}: {why}"
        line = "\n".join(t for t in (held, waiting_line(core.root, STEP, why)) if t)
        if not verdicts:
            raise Waiting(why, line)
    return Cascaded({**extra, "verdicts": verdicts}, "+".join(names) or "none", tuple(left), line)
