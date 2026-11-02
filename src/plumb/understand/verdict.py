"""The verdict cascade (SR-182, SR-242, INT-065, SR-372): who answers "does this record
contradict the owner's words or add intent they did not give?" for the judge job, like
``links.repin_after_tests`` (SR-114).

JEV is asked first for every record with a premise and a claim kind, calibrated or not, and its
score is logged with the verdict. It clears a record when every part is ``benign`` (a
restatement or a benign extension) strictly above the floor: 0.9, raised to the threshold of a
passing calibration of the same JEV version and question form (DEC-143: no calibration is
needed); a cleared record that may take the fast track (``capture.autoapprove.fast_track``) is
JEV's verdict, marked ``by: jev``, and the judge job approves it ``by: auto-jev``. Every other
record goes to the judge model (``understand.judge_model``, haiku by default, sonnet allowed),
marked ``by: model``: a model verdict never takes the fast track
(``plumb.judgment.verdict.refusal``); it asks only about a record that contradicts the owner or
adds intent they did not give. With neither reachable the verdict waits and the step says so
once (SR-174); nothing is decided by rule (INT-029). Which judge answered is in the log."""

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
    """The owner's whole messages, then each question-tool answer with its question and
    options (SR-212 EX-8); a premise with no answer is the messages unchanged (EX-10)."""
    premise = entry.get("premise") or {}
    messages = [m for m in premise.get("messages") or () if isinstance(m, Mapping)]
    if not messages or all(m.get("partial") for m in messages):
        return ""            # the owner's words are not on file: nothing to ask JEV about
    parts = [str(m.get("text") or "") for m in messages]
    for answer in premise.get("answers") or ():
        options = "; ".join(_option_text(o) for o in answer.get("options") or ())
        parts.append(f"Question: {answer.get('question')}\nOptions: {options}\n"
                     f"Answer: {answer.get('answer')}")
    return "\n\n".join(parts)


def _option_text(option: Any) -> str:
    if not isinstance(option, Mapping):
        return str(option)
    label, said = str(option.get("label") or ""), str(option.get("description") or "")
    return f"{label} ({said})" if said else label


def jev_verdict(core: Any, entry: Mapping[str, Any], backend: Any, calibration: Any
                ) -> dict[str, Any] | None:
    """JEV's scores of one entry, or None when it has no claim kind or no premise, or JEV did
    not answer as JEV: ``{score, verdict, clears, judge, model_version, confidence,
    confidence_label, fingerprints, parts, calibration, threshold, claim_kind}``. JEV is asked
    the approval question (SR-372: contradicts, extends or benign, never entailment);
    ``verdict`` is the worst label over the parts and ``score`` the lowest probability of
    ``benign``. ``clears`` when every part is ``benign`` strictly above the floor, max(0.9, the threshold of a passing calibration of the same
    version and question form) (SR-242 EX-5, DEC-143); ``threshold`` is that floor. Raises
    ``JudgmentUnavailable`` when JEV cannot answer."""
    from plumb.capture.autoapprove import JEV_FLOOR, _kind_threshold
    from plumb.capture.calibrate import _hypotheses, form_gap
    from plumb.judgment.tiers import same_version

    kind = CLAIM_KIND.get(str(entry.get("kind")))
    record = core.index().get(str(entry.get("id")))
    premise = _premise_text(entry)
    if kind is None or record is None or not premise:
        return None
    _, parts = _hypotheses(core.index(), record)
    judgments = [backend.approval(premise, part, subject=record.id, claim_kind=kind)
                 for part in parts]
    if not judgments or any(not j.backend.startswith("jev:") for j in judgments):
        return None
    version = judgments[0].backend.split(":", 1)[1]
    threshold = None
    if calibration is not None and not form_gap(core, calibration):   # SR-183: same form
        threshold = _kind_threshold(calibration, kind)
        if threshold is not None and not same_version(
                version, calibration.payload.get("model_version")):
            threshold = None            # another version's calibration raises nothing
    floor = max(JEV_FLOOR, threshold or 0.0)   # DEC-143: the floor needs no calibration
    weakest = min(judgments, key=lambda j: j.probability or 0.0)
    labels = {j.verdict for j in judgments}
    worst = next((v for v in ("contradicts", "extends") if v in labels), "benign")
    return {"score": round(weakest.probability or 0.0, 6), "verdict": worst,
            "clears": all(j.verdict == "benign" and (j.probability or 0.0) > floor
                          for j in judgments),
            "judge": judgments[0].backend, "model_version": version,
            "confidence": weakest.confidence, "confidence_label": weakest.confidence_label,
            "fingerprints": [j.fingerprint for j in judgments], "parts": len(judgments),
            "calibration": calibration.digest if threshold is not None else None,
            "threshold": floor, "claim_kind": kind}


def _ask_jev(core: Any, entries: list[Mapping[str, Any]], backend: Any
             ) -> tuple[dict[str, dict[str, Any]], str]:
    """``({id: JEV's scores}, why JEV stopped)``: JEV is asked whenever a backend exists; a
    missing or other-form calibration only means the 0.9 floor (DEC-143)."""
    from plumb.capture.calibrate import latest_calibration
    from plumb.judgment import JudgmentUnavailable, get_backend, judge_down, judge_up

    if backend is None:
        cause, code, detail = "JEV is not set up", "not-configured", ""
        try:            # SR-359: the exact cause, not only that JEV is missing
            get_backend(core, hook=False)
        except JudgmentUnavailable as exc:
            cause, code, detail = str(exc), exc.code, exc.detail
        judge_down(core.root, "JEV", cause, code=code, detail=detail)
        return {}, cause
    calibration = latest_calibration(core)
    scored: dict[str, dict[str, Any]] = {}
    for entry in entries:
        try:
            found = jev_verdict(core, entry, backend, calibration)
        except JudgmentUnavailable as exc:
            judge_down(core.root, "JEV", str(exc), code=exc.code, detail=exc.detail)
            return scored, str(exc)
        if found is not None:
            scored[str(entry["id"])] = found
    if scored:          # SR-359 EX-3: only an answer from JEV clears its red line
        judge_up(core.root, "JEV")
    return scored, ""


def _fast(core: Any, entries: list[Mapping[str, Any]], scored: Mapping[str, Mapping[str, Any]]
          ) -> dict[str, Mapping[str, Any]]:
    """The entries JEV clears that may take the fast track, or that JEV clears after a question
    round outside an escalated set (SR-248): no model is asked."""
    from plumb.capture.autoapprove import after_round, fast_track
    from plumb.capture.spec import escalated_ids

    index = core.index()
    in_sets = escalated_ids(core)
    out: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        jev = scored.get(str(entry.get("id")))
        record = index.get(str(entry.get("id")))
        if not jev or not jev["clears"] or record is None:
            continue
        if (entry.get("premise") or {}).get("answers"):
            if record.id not in in_sets and after_round(core, record, jev):
                out[record.id] = jev
        elif fast_track(core, record, jev):
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


def _dump(inputs: Mapping[str, Any]) -> str:
    return json.dumps(inputs, ensure_ascii=False, sort_keys=True, indent=1)


def _split(job: Job, entries: list[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    """The entries in consecutive parts each under ``INPUT_MAX`` as sent (SR-298 EX-2): a job
    is never failed for its size while its records can be sent apart."""
    parts: list[list[Mapping[str, Any]]] = [[]]
    for entry in entries:
        if parts[-1] and len(_dump({**job.inputs, "records": [*parts[-1], entry]})) > INPUT_MAX:
            parts.append([])
        parts[-1].append(entry)
    return parts


def _ask(core: Any, dispatcher: Any, sub: Job, part: list[Mapping[str, Any]], system: str,
         schema: Mapping[str, Any], on_step: Callable[[str], None], user: str) -> dict[str, Any]:
    """The judge model's answer; asked once more when a question of it cannot be shown
    (SR-299 EX-3). The second answer stands: its unusable questions wait as before, and the
    job goes to debugging as a case."""
    from plumb.understand import judge, summary

    def unusable(answer: Mapping[str, Any]) -> list[str]:
        return [why for q in answer.get("questions") or ()
                for made, why in [judge._shaped(core, q, sub, judged, index)] if made is None]

    answer = dict(dispatcher.run(sub, system=system, schema=schema, on_step=on_step, user=user))
    index = core.index()
    judged = {str(e["id"]): str(e.get("hash")) for e in part}
    if unusable(answer):
        answer = dict(dispatcher.run(sub, system=system, schema=schema, on_step=on_step,
                                     user=user))
        why = unusable(answer)
        if why:
            summary.write_cases(core, f"judge-{sub.id}-{part[0]['id']}", [{
                "id": f"judge-question:{sub.id}", "kind": "judge-question",
                "target": ", ".join(judged), "detail": f"asked twice: {why[0]}"}])
    return answer


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
        label = f"{getattr(dispatcher, 'name', 'model')}:{model}"
        questions: list[Any] = []
        unreachable = bool(gap)         # SR-359: a record too large is not the judge's fault
        parts = _split(job, rest)       # SR-298: split before sending
        for n, part in enumerate(parts):
            sub = dataclasses.replace(job, inputs={**job.inputs, "records": part})
            user = _dump(sub.inputs)
            if not gap and len(user) > INPUT_MAX:     # SR-245 EX-8: one record alone too big
                gap = f"the records are too large for the judge model ({len(user)} characters)"
            try:
                if gap:
                    raise DispatchError("start", f"{jev_cause}; {gap}" if jev_cause else gap)
                answer = _ask(core, dispatcher, sub, part, system, schema, on_step, user)
            except DispatchError as exc:     # SR-185: these records wait; the others go on
                left, why = [e for p in parts[n:] for e in p], exc.message
                unreachable = unreachable or not gap
                break
            for raw in answer.get("verdicts") or ():
                if isinstance(raw, Mapping):
                    got = scored.get(str(raw.get("id")))   # JEV's score is logged with it
                    verdicts.append({**raw, "by": MODEL, "judge": label, "model": model,
                                     **({"jev": dict(got)} if got else {})})
            questions += answer.get("questions") or ()
            extra = {k: v for k, v in answer.items() if k not in ("verdicts", "questions")}
        if questions:
            extra["questions"] = questions
        from plumb.judgment import judge_down, judge_up

        if len(left) < len(rest):
            names.append(str(getattr(dispatcher, "name", "model")))
            judge_up(core.root, "model")
        if unreachable:     # SR-359: the band's red line names this judge and the cause
            judge_down(core.root, label, why.removeprefix(f"{jev_cause}; "), slot="model")
    line = held
    if left:
        from plumb.judgment import waiting_line

        why = f"{', '.join(str(e.get('id')) for e in left)}: {why}"
        line = "\n".join(t for t in (held, waiting_line(core.root, STEP, why)) if t)
        if not verdicts:
            raise Waiting(why, line)
    return Cascaded({**extra, "verdicts": verdicts}, "+".join(names) or "none", tuple(left), line)
