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

from plumb.capture.autoapprove import CALIBRATE_HINT, RECALIBRATE_HINT

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
    from plumb.judgment.jev import SYSTEM_ONE_PATH, credential_env, endpoint_url, key_source
    from plumb.judgment.tiers import normalize_version, same_version

    judgment = core.config.judgment
    jev = dict(judgment.jev or {})
    name = credential_env(core.config)
    source = key_source(core.root, name=name)
    configured = str(judgment.backend).strip().lower() == "jev"
    out: dict[str, Any] = {
        "configured": configured, "backend": judgment.backend,
        "provider": jev.get("provider"),
        "endpoint": endpoint_url(str(jev.get("base_url") or ""),
                                 str(jev.get("path") or SYSTEM_ONE_PATH)),
        "credential_env": name, "credential": "present" if source else "absent",
        "model": jev.get("model"), "validated_against": jev.get("validated_against"),
    }
    if source:
        out["credential_source"] = source  # a label (env, env-file, user-store), never a key
    if probe:
        reachable, version, note = _probe(core) if configured and source else \
            (False, None, "not configured" if not configured else "no credential")
        out.update({"reachable": reachable, "resolved_version": normalize_version(version),
                    "resolved_model": version, "probe": note})
        if version:
            validated = jev.get("validated_against")
            out["version_drift"] = bool(validated) and not same_version(version, validated)
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
        out["calibration"] = f"none yet ({CALIBRATE_HINT})"
    state = auto_approve_state(core)
    out["auto_approve"] = state.reason if state.configured else "off"
    if state.mirror_mismatch:
        out["auto_approve_mirror"] = ("the settings file says automatic confirmation is on, "
                                      "but you never turned it on yourself, so it stays off "
                                      "(only you can turn it on)")
    return out


def status_lines(data: Mapping[str, Any]) -> list[str]:
    source = f", from {data['credential_source']}" if data.get("credential_source") else ""
    lines = [f"configured: {'yes' if data['configured'] else 'no'} (judgment.backend: "
             f"{data['backend']})",
             f"provider: {data.get('provider')}",
             f"endpoint: {data.get('endpoint')}",
             f"credential: {data['credential']} (variable {data['credential_env']}{source}; "
             "the value is never shown)"]
    if "reachable" in data:
        lines.append(f"reachable: {'yes' if data['reachable'] else 'no'} ({data['probe']})"
                     + (f", resolved version {data['resolved_version']} "
                        f"({data['resolved_model']})" if data.get("resolved_version") else ""))
        if data.get("version_drift"):
            lines.append(f"version drift: validated against {data.get('validated_against')}; "
                         "confident answers are escalated until it is revalidated")
    lines.append(f"model: {data.get('model')} (validated against "
                 f"{data.get('validated_against')})")
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


def jev_setup(core: Core, *, env_var: str | None = None, base_url: str | None = None,
              provider: str | None = None, env_file: str | None = None) -> list[str]:
    """Record the provider, its model and the credential variable's NAME in the repository
    config; with ``env_file``, write the user-level ``jev.json`` that names the env file the
    key is read from in place. The key itself is never read into output, copied or logged."""
    import json
    from pathlib import Path

    from plumb.capture.configfile import update_section
    from plumb.capture.records import CaptureError
    from plumb.config import DEFAULT_JEV_PROVIDER, JEV_PROVIDERS, PROVIDER_KEYS
    from plumb.judgment.jev import parse_env_value, user_config_path

    chosen = (provider or "").strip().lower() or None
    if chosen is not None and chosen not in JEV_PROVIDERS:
        raise CaptureError(f"'{provider}' is not a JEV provider "
                           f"({', '.join(sorted(JEV_PROVIDERS))})")
    preset = JEV_PROVIDERS[chosen or DEFAULT_JEV_PROVIDER]
    name = (env_var or "").strip() or preset["credential_env"]
    if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
        raise CaptureError(f"'{env_var}' is not an environment variable name")
    root = Path(core.root).resolve()
    env_path: Path | None = None
    if env_file:
        env_path = Path(env_file).expanduser().resolve()
        if env_path.is_relative_to(root):
            raise CaptureError(f"the env file {env_path} is inside the repository; keys are "
                               "never repository state: keep it outside")
        if user_config_path().resolve().is_relative_to(root):
            raise CaptureError("the user-level jev.json would be inside the repository")
    jev: dict[str, Any] = {"credential_env": name}
    if chosen is not None:
        jev = {"provider": chosen, "model": preset["model"], "credential_env": name}
    if base_url:
        jev["base_url"] = base_url
    # a provider choice replaces every provider-specific value an earlier setup left (its
    # endpoint, path, model and validated version), so a switch never keeps the old endpoint
    stale = PROVIDER_KEYS if chosen is not None else frozenset()
    update_section(core.root, "judgment", {"backend": "jev", "jev": jev},
                   drop={"jev": stale})
    lines = [f"plumb: judgment.backend jev, provider {chosen or DEFAULT_JEV_PROVIDER} "
             f"(model {jev.get('model') or preset['model']}); the credential is read from "
             f"{name}"]
    if env_path is not None:
        config = user_config_path()
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"credential_env": name, "env_file": str(env_path)},
                                     indent=2) + "\n", encoding="utf-8")
        try:
            present = parse_env_value(env_path.read_text(encoding="utf-8-sig"), name)
        except (OSError, UnicodeDecodeError):
            present = None
        lines += [f"plumb: {name} is read in place from the env file {env_path} "
                  f"({'found' if present else 'not found'} there); the value is never copied",
                  f"plumb: wrote {config} (user-level, outside the repository)"]
    else:
        lines.append(f"plumb: set {name} in your own environment, never in the repository, or "
                     "name an env file outside it (\"/plumb jev setup "
                     f"{chosen or DEFAULT_JEV_PROVIDER} with the env file <path>\")")
    core.log_append("events", "jev-setup", {"credential_env": name, "base_url": base_url,
                                            "provider": chosen or DEFAULT_JEV_PROVIDER,
                                            "env_file": env_path is not None})
    lines.append("plumb: then check it with /plumb jev status")
    return lines


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
            raise ConfigRefused(f"no passing calibration ({CALIBRATE_HINT})")
        reachable, version, note = _probe(core)
        if not reachable:
            raise ConfigRefused(f"JEV did not answer ({note})")
        measured = calibration.payload.get("model_version")
        from plumb.judgment.tiers import same_version

        if not same_version(version, measured):
            raise ConfigRefused(f"the calibration measured {measured}, JEV now resolves "
                                f"{version} ({RECALIBRATE_HINT})")
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
