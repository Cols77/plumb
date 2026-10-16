"""Narrow auto-approval, opt-in and off by default (R8 B, R12.1, R13 Q3; sp2 8.2, SR-041).

Effective only when all of these hold:

- the latest ``config`` event says on, written by the owner: with no session marker through
  ``approvals.require_owner`` (``plumb config auto-approve on``), or from their typed
  ``/plumb auto-approve on`` the prompt hook saw (``ownerconfig``, SR-115). ``config.yaml``'s
  ``auto_approve`` is a mirror: on without that event is off, and ``plumb validate`` warns;
- JEV is configured and its credential is present (nothing else auto-approves);
- a passing ``calibration`` exists for the resolved model version; a different resolved
  version suspends auto-approval until it is recalibrated.

The judge job asks JEV for every record (one cascade, SR-242); ``fast_track`` says whether a
record JEV clears is approved there without a question (SR-248): a proposed INT or requirement
whose every quote is verbatim in a prompt the prompt hook logged, when JEV scores its wording
AND every one of its examples strictly above max(0.9, the calibrated threshold). Never: a
record that ever had an approval, an edit of a confirmed record, a member of an escalated set,
a prompt the prompt hook did not log (a message the agent recorded itself, R13 Q4), or when
JEV is unavailable. Each approval is ``by: auto-jev``, written by the worker only, with its
score, confidence, prompt digest, backend, model version and the calibration it rests on,
hash-pinned like any approval.

After a question round (``after_round``) JEV approves a record the owner answered about without
the switch, which governs approval without a question (SR-248): the approval cites the
owner's answers, and a passing calibration, the strict floor and the minimum confidence label
still apply (SR-251).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.contracts import AutoApproveState, LogEntry
from plumb.judgment.tiers import same_version

# R14/R18: owner-visible JEV and auto-approval text names the /plumb command or plain words,
# never a CLI command (jev status, config show, the refusals of config auto-approve on).
CALIBRATE_HINT = "say /plumb jev calibrate to measure it"
RECALIBRATE_HINT = "say /plumb jev calibrate to measure it again"
SETUP_HINT = "say /plumb jev setup openrouter, or /plumb jev setup typesafe"

if TYPE_CHECKING:
    from plumb.api import Core

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
CLAIM_KIND = {"intent": "intent-readback", "requirement": "example-restatement"}


def owner_config(entries: Sequence[LogEntry]) -> Mapping[str, Any] | None:
    """The ``auto_approve`` settings of the latest owner ``config`` event (from the owner's
    terminal, or their typed ``/plumb auto-approve``: ``ownerconfig``), or None."""
    from plumb.capture.ownerconfig import latest

    entry = latest(entries)
    return entry.payload["auto_approve"] if entry is not None else None


def _last_model_version(entries: Sequence[LogEntry]) -> str | None:
    for entry in reversed(entries):
        if entry.kind == "judgment":
            backend = str(entry.payload.get("backend") or "")
            if backend.startswith("jev:"):
                return backend.split(":", 1)[1] or None
    return None


def jev_ready(core: Core) -> tuple[bool, str]:
    """Whether JEV is configured with its credential present (never reads the value
    beyond presence)."""
    if str(core.config.judgment.backend).strip().lower() != "jev":
        return False, f"JEV is not set up ({SETUP_HINT})"
    from plumb.judgment.jev import credential_env, key_source

    name = credential_env(core.config)
    if key_source(core.root, name=name) is None:
        return False, f"the JEV credential is absent ({name} is not set)"
    return True, "ok"


def auto_approve_state(core: Core) -> AutoApproveState:
    from plumb.capture.calibrate import latest_calibration
    from plumb.capture.ownerconfig import latest, source_of

    entries = core.events()
    switch = latest(entries)
    settings = switch.payload["auto_approve"] if switch is not None else None
    configured = bool(settings and settings.get("enabled"))
    mirror = bool(core.config.auto_approve.enabled)
    calibration = latest_calibration(core)
    calibrated = str(calibration.payload.get("model_version")) if calibration else None
    passing = bool(calibration and any(
        k.get("passing") for k in (calibration.payload.get("per_kind") or {}).values()
        if isinstance(k, Mapping)))
    seen = _last_model_version(entries)
    from plumb.capture.calibrate import fingerprint_stale

    suspended = bool(configured and calibrated and (
        (seen and not same_version(seen, calibrated)) or fingerprint_stale(core)))
    ready, why = jev_ready(core)
    from plumb.capture.calibrate import form_gap

    wrong_form = form_gap(core, calibration)
    if not configured:
        reason = "off"
    elif not ready:
        reason = why
    elif wrong_form:
        reason = f"{wrong_form}; {CALIBRATE_HINT}"
    elif not passing:
        reason = f"no passing calibration ({CALIBRATE_HINT})"
    elif suspended:
        reason = ("auto-approve suspended: the judge model, prompt or JEV model changed "
                  f"({RECALIBRATE_HINT})")
    else:
        reason = "on"
    settings = settings or {}
    return AutoApproveState(
        configured=configured, effective=reason == "on", reason=reason,
        backend=str(settings.get("backend") or "jev") if configured else None,
        min_probability=float(settings.get("min_probability", 0.9)),
        min_confidence=str(settings.get("min_confidence", "high")),
        calibrated_version=calibrated, model_version=seen, suspended=suspended,
        mirror_mismatch=mirror and not configured, source=source_of(switch))


def state_line(state: AutoApproveState) -> str:
    """``auto-approve: ...`` with where the current setting comes from (SR-115), for
    ``plumb status`` and ``plumb brief``."""
    if state.effective:
        now = "on"
    elif state.configured:
        now = f"switched on, not in effect: {state.reason}"
    else:
        now = "off"
    if state.source:
        return f"auto-approve: {now} (set by {state.source})"
    if state.mirror_mismatch:
        return (f"auto-approve: {now} (config.yaml says on, but you never switched it on; "
                "type /plumb auto-approve on)")
    return f"auto-approve: {now} (never switched on)"


def _kind_threshold(calibration: LogEntry, kind: str) -> float | None:
    per_kind = calibration.payload.get("per_kind") or {}
    result = per_kind.get(kind) if isinstance(per_kind, Mapping) else None
    if not isinstance(result, Mapping) or not result.get("passing"):
        return None
    threshold = result.get("threshold")
    return float(threshold) if threshold is not None else None


def verdict_refusal(verdict: Mapping[str, Any]) -> str | None:
    """SR-182: why a logged verdict may not feed auto-approval, or None. Only a supported
    verdict marked as JEV's does; the judge model's never takes the fast track (it approves
    only after a question round, ``by: auto-model``), and one that says nobody never does."""
    from plumb.judgment.verdict import refusal

    return refusal(verdict.get("by"), verdict.get("verdict"))


JEV_FLOOR = 0.9   # SR-248: JEV's floor; no threshold or owner setting lowers it


def _jev_auto(record: Any, jev: Mapping[str, Any], state: AutoApproveState
              ) -> dict[str, Any] | None:
    """The ``auto`` payload of JEV's scores ``jev`` on ``record``, or None unless JEV clears
    it: a passing same-version calibration, every part strictly above max(0.9, the owner's
    minimum, the threshold), and the owner's minimum confidence label."""
    if not jev.get("clears") or jev.get("threshold") is None:
        return None
    if CLAIM_KIND.get(record.kind) != jev.get("claim_kind"):
        return None
    floor = max(JEV_FLOOR, state.min_probability, float(jev["threshold"]))
    if float(jev.get("score") or 0.0) <= floor:
        return None
    if CONFIDENCE_RANK.get(str(jev.get("confidence_label")), -1) < CONFIDENCE_RANK.get(
            state.min_confidence, 2):
        return None
    return {"score": jev["score"], "confidence": jev.get("confidence"),
            "confidence_label": jev.get("confidence_label"), "backend": jev.get("judge"),
            "model_version": jev.get("model_version"), "calibration": jev.get("calibration"),
            "claim_kind": jev["claim_kind"], "judge": "jev", "threshold": jev["threshold"],
            "min_probability": state.min_probability, "min_confidence": state.min_confidence,
            "parts": jev.get("parts"), "fingerprints": list(jev.get("fingerprints") or ())}


def fast_track(core: Core, record: Any, jev: Mapping[str, Any]) -> dict[str, Any] | None:
    """The ``auto`` payload of a ``by: auto-jev`` approval of ``record`` on JEV's scores
    ``jev`` (``understand.verdict.jev_verdict``), or None when it may not take the fast track
    (SR-248, SR-250): the owner's switch in effect with a passing same-version calibration,
    JEV clearing every part strictly above its floor, the premise the owner's verified words,
    the owner's minimum confidence label, and a proposed record never approved before and in
    no escalated set."""
    state = auto_approve_state(core)
    if not state.effective:
        return None
    auto = _jev_auto(record, jev, state)
    if auto is None:
        return None
    from plumb.capture.spec import escalated_ids
    from plumb.capture.triage import _Prompts, approved_before, premise_problem

    if premise_problem(_Prompts(core), core.index(), record) is not None:
        return None   # quote-only: the verdict is logged so, the judge model asks
    if core.status([record.id])[record.id].confirmation != "proposed":
        return None   # an edit of a confirmed record goes to the judge model's questions
    if record.id in approved_before(core) or record.id in escalated_ids(core):
        return None   # a set is approved whole (P6)
    return {**auto, "prompt_via": "hook"}


def after_round(core: Core, record: Any, jev: Mapping[str, Any]) -> dict[str, Any] | None:
    """The ``auto`` payload of an answer-cited ``by: auto-jev`` approval of ``record`` after a
    question round (SR-248 EX-4), or None: JEV clears it as for the fast track, without the
    switch; with no passing calibration JEV approves nothing (SR-251)."""
    return _jev_auto(record, jev, auto_approve_state(core))


def recheck(entry: LogEntry, config: Mapping[str, Any] | None,
            calibrations: Mapping[str, LogEntry], prompts: set[str],
            approved: set[str], escalated: Collection[str] = (),
            answers: Mapping[str, Mapping[str, Any]] | None = None) -> str | None:
    """Why an ``auto-jev`` approval fails its re-check, or None (sp2 8.2): a passing
    calibration for the same model version, a score strictly above the recorded thresholds
    and 0.9, the owner's minimum confidence label and an eligible record kind. On the fast
    track, also an owner ``config`` on before it, a cited prompt event logged by the prompt
    hook (not self-recorded), no earlier owner, relayed or imported approval of the record and
    no record of an escalated spec set (``escalated``, ``spec.escalated_ids``). After a question
    round (it cites ``answers``), each cited answer is a question-tool answer logged before it
    (``answers``: digest -> payload) asked about each record at that version, in place of the
    switch and the prompt event (SR-248 EX-4)."""
    from plumb.understand.recheck_model import cited_answers_problem

    payload = entry.payload
    auto = payload.get("auto")
    if not isinstance(auto, Mapping):
        return "auto-jev approval carries no score"
    after_answers = bool(payload.get("answers"))
    if not after_answers and (not config or not config.get("enabled")):
        return "auto-jev approval without the owner's config auto-approve on before it"
    calibration = calibrations.get(str(auto.get("calibration")))
    if calibration is None:
        return "auto-jev approval cites no earlier calibration"
    if not same_version(calibration.payload.get("model_version"), auto.get("model_version")):
        return "auto-jev approval by a model version its calibration did not measure"
    if auto.get("judge", "jev") != "jev":
        return "auto-jev approval rests on a judge model's verdict, which never approves"
    kind = str(auto.get("claim_kind"))
    threshold = _kind_threshold(calibration, kind)
    if threshold is None:
        return f"auto-jev approval of claim kind {kind} without a passing calibration"
    if after_answers:
        why = cited_answers_problem(payload, answers or {}, "auto-jev")
        if why:
            return why
    elif payload.get("prompt_digest") not in prompts:
        return "auto-jev approval cites no earlier prompt event"
    elif auto.get("prompt_via") != "hook" or payload.get("self_recorded"):
        return ("auto-jev approval rests on a message the agent recorded itself (not logged "
                "by the prompt hook); only the owner or a relayed ok confirms it")
    try:
        score = float(auto.get("score"))
    except (TypeError, ValueError):
        return "auto-jev approval carries no score"
    settings = config or {}
    floor = max(JEV_FLOOR, float(settings.get("min_probability", JEV_FLOOR)), threshold)
    if score <= floor:     # SR-242 EX-5: only a score above the threshold stands on JEV
        return f"auto-jev score {score:.3f} is not above the threshold {floor:.3f}"
    need = CONFIDENCE_RANK.get(str(settings.get("min_confidence", "high")), 2)
    if CONFIDENCE_RANK.get(str(auto.get("confidence_label")), -1) < need:
        return "auto-jev confidence is below the owner's minimum"
    for item in payload.get("records") or []:
        record_id = str(item.get("id")) if isinstance(item, Mapping) else ""
        prefix = record_id.split("-", 1)[0]
        if {"INT": "intent-readback", "SR": "example-restatement"}.get(prefix) != kind:
            return f"auto-jev approval of {record_id}, which is not an eligible record"
        if after_answers:
            continue      # an edit or a set member is approved after its round
        if record_id in approved:
            return f"auto-jev approval of {record_id}, which had an approval before"
        if record_id in escalated:
            return (f"auto-jev approval of {record_id}, which belongs to an escalated spec "
                    "set (only the owner's set approval confirms it)")
    return None
