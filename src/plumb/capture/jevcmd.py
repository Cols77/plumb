"""``plumb jev status``, ``plumb jev setup`` (sp2 7.3, SR-039) and ``plumb config``
(sp2 8.2, SR-041).

``jev setup`` records only the NAME of the environment variable that holds the credential;
plumb never reads, prints or stores the secret. ``config auto-approve on|off`` writes the
owner's ``config`` event through ``approvals.require_owner`` (refused under the session marker
and outside an interactive terminal, on every host) and the ``config.yaml`` mirror; ``on``
refuses, writing nothing, without JEV, its credential, or a passing calibration for the
current resolved model version.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plumb.api import Core

PROBE_TIMEOUT_S = 2.0
CARD_MODES = ("full", "compact", "off")


class ConfigRefused(ValueError):
    """``config auto-approve on`` cannot be turned on (exit 1); nothing was written."""


def _probe(core: Core) -> tuple[bool, str | None, str]:
    """One cheap JEV call with a 2 s limit: ``(reachable, resolved version, note)``."""
    from plumb.judgment import get_backend

    backend = get_backend(core, hook=False)
    if getattr(backend, "name", "") != "jev":
        return False, None, "; ".join(getattr(backend, "notices", ())) or "not configured"
    client = getattr(backend, "client", None)
    if client is not None:
        client.timeout_s = PROBE_TIMEOUT_S
    judgment = backend.entailment("ok", "ok", subject="probe", claim_kind="probe")
    if judgment.backend.startswith("jev:"):
        return True, judgment.backend.split(":", 1)[1], "ok"
    return False, None, getattr(client, "last_error", None) or "no answer"


def jev_status(core: Core, *, probe: bool = False) -> dict[str, Any]:
    from plumb.capture.autoapprove import auto_approve_state
    from plumb.capture.calibrate import latest_calibration
    from plumb.judgment.jev import credential_env, key_source

    judgment = core.config.judgment
    name = credential_env(core.config)
    source = key_source(core.root, name=name)
    configured = str(judgment.backend).strip().lower() == "jev"
    out: dict[str, Any] = {
        "configured": configured, "backend": judgment.backend,
        "credential_env": name, "credential": "present" if source else "absent",
        "model": (judgment.jev or {}).get("model"),
    }
    if source:
        out["credential_source"] = source
    if probe:
        reachable, version, note = _probe(core) if configured and source else \
            (False, None, "not configured" if not configured else "no credential")
        out.update({"reachable": reachable, "resolved_version": version, "probe": note})
    calibration = latest_calibration(core)
    if calibration is not None:
        per_kind = calibration.payload.get("per_kind") or {}
        out["calibrated_version"] = calibration.payload.get("model_version")
        out["calibration"] = {
            kind: {"passing": r.get("passing"), "threshold": r.get("threshold"),
                   "decisions": r.get("items"), "real_no": r.get("real_negatives"),
                   "generated_no": r.get("generated_negatives"),
                   "generated_counted": r.get("generated_counted")}
            for kind, r in per_kind.items() if isinstance(r, Mapping)}
    else:
        out["calibration"] = "none (plumb jev calibrate)"
    state = auto_approve_state(core)
    out["auto_approve"] = state.reason if state.configured else "off"
    if state.mirror_mismatch:
        out["auto_approve_mirror"] = ("config.yaml says on, but no owner config event: off "
                                      "(plumb config auto-approve on, in your terminal)")
    return out


def status_lines(data: Mapping[str, Any]) -> list[str]:
    lines = [f"configured: {'yes' if data['configured'] else 'no'} (judgment.backend: "
             f"{data['backend']})",
             f"credential: {data['credential']} (variable {data['credential_env']}; the "
             "value is never shown)"]
    if "reachable" in data:
        lines.append(f"reachable: {'yes' if data['reachable'] else 'no'} ({data['probe']})"
                     + (f", resolved version {data['resolved_version']}"
                        if data.get("resolved_version") else ""))
    lines.append(f"model: {data.get('model')}")
    calibration = data["calibration"]
    if isinstance(calibration, Mapping):
        lines.append(f"calibrated against: {data.get('calibrated_version')}")
        for kind, r in calibration.items():
            lines.append(f"  {kind}: {'passing' if r['passing'] else 'not passing'}; "
                         f"{r['decisions']} of your decisions, 'no' examples "
                         f"{r['real_no']} real + {r['generated_counted']} generated counted "
                         f"(of {r['generated_no']})")
    else:
        lines.append(f"calibration: {calibration}")
    lines.append(f"auto-approve: {data['auto_approve']}")
    if data.get("auto_approve_mirror"):
        lines.append(f"warning: {data['auto_approve_mirror']}")
    return lines


def jev_setup(core: Core, *, env_var: str, base_url: str | None = None) -> list[str]:
    from plumb.capture.configfile import update_section

    name = env_var.strip()
    if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
        from plumb.capture.records import CaptureError

        raise CaptureError(f"'{env_var}' is not an environment variable name")
    jev: dict[str, Any] = {"credential_env": name}
    if base_url:
        jev["base_url"] = base_url
    update_section(core.root, "judgment", {"backend": "jev", "jev": jev})
    core.log_append("events", "jev-setup", {"credential_env": name,
                                            "base_url": base_url})
    return [f"plumb: judgment.backend jev; the credential is read from {name}",
            "plumb: set it in your own shell, never in the repository:",
            f"  bash:        export {name}=<your key>",
            f"  PowerShell:  $env:{name} = \"<your key>\"",
            "plumb: then plumb jev status --probe, and plumb jev calibrate"]


def _mirror(core: Core, settings: Mapping[str, Any]) -> None:
    from plumb.capture.configfile import update_section

    update_section(core.root, "auto_approve", dict(settings))


def auto_approve(core: Core, on: bool, *, backend: str = "jev", min_probability: float = 0.9,
                 min_confidence: str = "high") -> Any:
    """The owner's switch. ``on`` checks JEV, its credential and a passing calibration for
    the resolved model version first (exit 1, nothing written), then asks y/N in the owner's
    terminal (``require_owner``)."""
    from plumb.approvals import refuse_under_marker, require_owner
    from plumb.capture.autoapprove import jev_ready
    from plumb.capture.calibrate import latest_calibration

    command = f"config auto-approve {'on' if on else 'off'}"
    refuse_under_marker(command)
    settings = {"enabled": on, "backend": backend, "min_probability": float(min_probability),
                "min_confidence": min_confidence}
    if on:
        if backend != "jev":
            raise ConfigRefused("only the jev backend auto-approves; the heuristic never does")
        if min_confidence not in ("low", "medium", "high"):
            raise ConfigRefused("--min-confidence is low, medium or high")
        ready, why = jev_ready(core)
        if not ready:
            raise ConfigRefused(why)
        calibration = latest_calibration(core)
        per_kind = (calibration.payload.get("per_kind") or {}) if calibration else {}
        if not any(isinstance(r, Mapping) and r.get("passing") for r in per_kind.values()):
            raise ConfigRefused("no passing calibration (plumb jev calibrate)")
        reachable, version, note = _probe(core)
        if not reachable:
            raise ConfigRefused(f"JEV did not answer ({note})")
        measured = calibration.payload.get("model_version")
        if version != measured:
            raise ConfigRefused(f"the calibration measured {measured}, JEV now resolves "
                                f"{version}: recalibrate first")
    require_owner(command, f"turn auto-approval {'ON' if on else 'off'}"
                  + (f" (jev, min probability {min_probability}, min confidence "
                     f"{min_confidence}) for records restating your own words" if on else "")
                  + ", as yourself (by: owner)?")
    entry = core.log_append("events", "config", {"auto_approve": settings, "by": "owner"})
    _mirror(core, settings)
    return entry


def config_show(core: Core) -> list[str]:
    from plumb.approvals import refuse_under_marker
    from plumb.capture.autoapprove import auto_approve_state

    refuse_under_marker("config show")
    state = auto_approve_state(core)
    mirror = core.config.auto_approve
    lines = [f"auto-approve: {'effective' if state.effective else state.reason}",
             f"  your last switch: {'on' if state.configured else 'off'}"
             + (f" (min probability {state.min_probability}, min confidence "
                f"{state.min_confidence})" if state.configured else ""),
             f"  config.yaml mirror: {'on' if mirror.enabled else 'off'}"
             + (" (no owner event: off)" if state.mirror_mismatch else ""),
             f"  calibrated against: {state.calibrated_version or 'none'}; last model seen: "
             f"{state.model_version or 'none'}"]
    present = getattr(core.config, "present", None)
    card = getattr(present, "card", None) if present is not None else None
    lines.append(f"card: {card or _raw_card(core) or 'compact (default)'}")
    lines.append(f"judgment backend: {core.config.judgment.backend}")
    return lines


def _raw_card(core: Core) -> str | None:
    import yaml

    try:
        data = yaml.safe_load((core.paths.config).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    present = data.get("present") if isinstance(data, dict) else None
    return str(present.get("card")) if isinstance(present, dict) and present.get("card") \
        else None


def set_card(core: Core, mode: str) -> str:
    """``plumb config card full|compact|off`` (R9: the card's verbosity)."""
    from plumb.capture.configfile import update_section

    if mode not in CARD_MODES:
        from plumb.capture.records import CaptureError

        raise CaptureError(f"card is one of {', '.join(CARD_MODES)}")
    update_section(core.root, "present", {"card": mode})
    return mode
