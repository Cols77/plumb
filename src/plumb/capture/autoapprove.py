"""Narrow auto-approval, opt-in and off by default (R8 B, R12.1, R13 Q3; sp2 8.2, SR-041).

Effective only when all of these hold:

- the latest ``config`` event says on, written by the owner: with no session marker through
  ``approvals.require_owner`` (``plumb config auto-approve on``), or from their typed
  ``/plumb auto-approve on`` the prompt hook saw (``ownerconfig``, SR-115). ``config.yaml``'s
  ``auto_approve`` is a mirror: on without that event is off, and ``plumb validate`` warns;
- JEV is configured and its credential is present (nothing else auto-approves);
- a passing ``calibration`` exists for the resolved model version; a different resolved
  version suspends auto-approval until it is recalibrated.

Eligible only: an INT whose quote is a verbatim span of the logged prompt, and a requirement
written in the same capture whose every example quotes that prompt verbatim, when JEV judges
that the owner's logged words support the requirement's wording AND every one of its examples
(R13 Q3). Never: a DEC, an escalated spec or its members, a record that ever had an owner,
relayed or imported approval, any record without a prompt, a prompt the prompt hook did not
log (a message the agent recorded itself, R13 Q4), or when JEV is unavailable. Each
approval is ``by: auto-jev`` with its score, confidence, prompt digest, backend, model version
and the calibration it rests on, hash-pinned like any approval and revocable with ``plumb
revoke``.
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
    suspended = bool(configured and calibrated and seen
                     and not same_version(seen, calibrated))
    ready, why = jev_ready(core)
    if not configured:
        reason = "off"
    elif not ready:
        reason = why
    elif not passing:
        reason = f"no passing calibration ({CALIBRATE_HINT})"
    elif suspended:
        reason = f"auto-approve suspended: the JEV model changed ({RECALIBRATE_HINT})"
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


def gate(core: Core, ids: Sequence[str], *, prompt_digest: str | None,
         backend: Any = None) -> list[str]:
    """Approve ``by: auto-jev`` the eligible records among ``ids`` (written by one
    ``capture``); returns their IDs. Returns at once when auto-approval is off."""
    state = auto_approve_state(core)
    if not state.configured or not prompt_digest:
        return []
    if not state.effective and not state.reason.startswith("auto-approve suspended"):
        return []
    from plumb.approvals import Refused, approval_items, find_prompt, quote_in_prompt
    from plumb.capture.calibrate import latest_calibration
    from plumb.capture.spec import escalated_ids
    from plumb.capture.triage import approved_before
    from plumb.normalize import normalize_text

    try:
        prompt = find_prompt(core, prompt_digest)
    except Refused:
        return []
    if prompt.get("via") != "hook":
        # R13 Q4 / R8 B: a message the agent recorded itself is not the owner's own words
        # as the prompt hook logged them; no human sees an auto-approval, so none rests on it
        return []
    text = normalize_text(str(prompt["text"]))
    if backend is None:
        from plumb.judgment import JudgmentUnavailable, get_backend

        try:
            backend = get_backend(core, hook=False)
        except JudgmentUnavailable:
            return []  # no judge, no auto-approval
    if getattr(backend, "name", "") != "jev":
        return []  # only JEV auto-approves
    calibration = latest_calibration(core)
    if calibration is None:
        return []
    index = core.index()
    escalated = escalated_ids(core)
    before = approved_before(core)
    out: list[str] = []
    for record_id in ids:
        record = index.get(record_id)
        if record is None or record.kind not in CLAIM_KIND or record_id in escalated:
            continue  # an escalated spec set waits for the owner's set approval (R8 B)
        if record_id in before:
            continue
        kind = CLAIM_KIND[record.kind]
        threshold = _kind_threshold(calibration, kind)
        if threshold is None:
            continue
        if record.kind == "intent":
            if not quote_in_prompt(normalize_text(str(record.fields.get("quote") or "")),
                                   text):
                continue
        else:
            raw = [e for e in record.fields.get("examples") or [] if isinstance(e, Mapping)]
            if not raw or not all(e.get("quote") and quote_in_prompt(
                    normalize_text(str(e["quote"])), text) for e in raw):
                continue
        from plumb.capture.calibrate import _hypotheses

        _, parts = _hypotheses(index, record)
        from plumb.judgment import JudgmentUnavailable

        try:
            judgments = [backend.entailment(str(prompt["text"]), part, subject=record_id,
                                            claim_kind=kind) for part in parts]
        except JudgmentUnavailable:
            return out  # JEV unavailable: nothing more is auto-approved (INT-029)
        if not judgments or any(not j.backend.startswith("jev:") for j in judgments):
            return out  # JEV unavailable or errored: nothing more is auto-approved
        version = judgments[0].backend.split(":", 1)[1]
        if not same_version(version, calibration.payload.get("model_version")):
            return out  # model changed since calibration: suspended
        floor = max(state.min_probability, threshold)
        need = CONFIDENCE_RANK.get(state.min_confidence, 2)
        if any(j.verdict != "entailed" or (j.probability or 0.0) < floor
               or CONFIDENCE_RANK.get(str(j.confidence_label), -1) < need for j in judgments):
            continue
        weakest = min(judgments, key=lambda j: j.probability or 0.0)
        digest = str(prompt["digest"])
        known = {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}
        if digest not in known:
            core.log_append("events", "prompt", {"digest": digest,
                                                 "session": prompt.get("session"),
                                                 "at": prompt.get("at")})
        core.log_append("events", "approval", {
            "records": approval_items(core, [record_id]), "by": "auto-jev",
            "prompt_digest": digest, "quote": None, "quote_digest": None,
            "auto": {"score": weakest.probability, "confidence": weakest.confidence,
                     "confidence_label": weakest.confidence_label,
                     "backend": weakest.backend, "model_version": version,
                     "calibration": calibration.digest, "claim_kind": kind,
                     "threshold": threshold, "prompt_via": "hook",
                     "min_probability": state.min_probability,
                     "min_confidence": state.min_confidence, "parts": len(judgments),
                     "fingerprints": [j.fingerprint for j in judgments]}})
        out.append(record_id)
    return out


def recheck(entry: LogEntry, config: Mapping[str, Any] | None,
            calibrations: Mapping[str, LogEntry], prompts: set[str],
            approved: set[str], escalated: Collection[str] = ()) -> str | None:
    """Why an ``auto-jev`` approval fails its re-check, or None (sp2 8.2): an owner
    ``config`` on before it, a passing calibration for the same model version, a cited
    prompt event logged by the prompt hook (not self-recorded), a score at or above the
    recorded thresholds, an eligible record kind, and no earlier owner, relayed or imported
    approval of the record, and no record of an escalated spec set (``escalated``,
    ``spec.escalated_ids``)."""
    payload = entry.payload
    auto = payload.get("auto")
    if not isinstance(auto, Mapping):
        return "auto-jev approval carries no score"
    if not config or not config.get("enabled"):
        return "auto-jev approval without the owner's config auto-approve on before it"
    calibration = calibrations.get(str(auto.get("calibration")))
    if calibration is None:
        return "auto-jev approval cites no earlier calibration"
    if not same_version(calibration.payload.get("model_version"), auto.get("model_version")):
        return "auto-jev approval by a model version its calibration did not measure"
    kind = str(auto.get("claim_kind"))
    threshold = _kind_threshold(calibration, kind)
    if threshold is None:
        return f"auto-jev approval of claim kind {kind} without a passing calibration"
    if payload.get("prompt_digest") not in prompts:
        return "auto-jev approval cites no earlier prompt event"
    if auto.get("prompt_via") != "hook" or payload.get("self_recorded"):
        return ("auto-jev approval rests on a message the agent recorded itself (not logged "
                "by the prompt hook); only the owner or a relayed ok confirms it")
    try:
        score = float(auto.get("score"))
    except (TypeError, ValueError):
        return "auto-jev approval carries no score"
    floor = max(float(config.get("min_probability", 0.9)), threshold)
    if score < floor:
        return f"auto-jev score {score:.3f} is below the threshold {floor:.3f}"
    need = CONFIDENCE_RANK.get(str(config.get("min_confidence", "high")), 2)
    if CONFIDENCE_RANK.get(str(auto.get("confidence_label")), -1) < need:
        return "auto-jev confidence is below the owner's minimum"
    for item in payload.get("records") or []:
        record_id = str(item.get("id")) if isinstance(item, Mapping) else ""
        prefix = record_id.split("-", 1)[0]
        if {"INT": "intent-readback", "SR": "example-restatement"}.get(prefix) != kind:
            return f"auto-jev approval of {record_id}, which is not an eligible record"
        if record_id in approved:
            return f"auto-jev approval of {record_id}, which had an approval before"
        if record_id in escalated:
            return (f"auto-jev approval of {record_id}, which belongs to an escalated spec "
                    "set (only the owner's set approval confirms it)")
    return None
