"""``.plumb/config.yaml`` (spec 11, 12.4).

YAML is imported only on a cache miss: the parsed config is cached as JSON in
``.plumb/cache/config.json`` keyed by the YAML file's size and mtime.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_INFRA_GLOBS = ("**/conftest.py", "pyproject.toml", "uv.lock", "pytest.ini", "tox.ini",
                       "setup.cfg")
DEFAULT_AFFIRMATIONS = ("ok", "okay", "yes", "approve", "approved", "confirm", "confirmed",
                        "agreed", "lgtm", "go ahead", "sounds good")


@dataclass(frozen=True)
class VerifyConfig:
    turn_budget_s: float = 15
    hard_limit_factor: float = 1.5
    fill_fraction: float = 0.65  # a selection's estimate fills this share of the budget
    sample_size: int = 10
    default_test_s: float = 1.0
    workers: int = 0
    flaky_rerun: bool = True
    infra_globs: tuple[str, ...] = DEFAULT_INFRA_GLOBS


# Soft budgets per hook, from process start. Near the 2-second ceiling on purpose: on a
# loaded 2-core machine a tighter budget cut the read-back first. The watchdog (1.9 s) is
# the hard bound, and a cut keeps the intent-translation lines (hookio.HookContext.keep).
DEFAULT_HOOK_BUDGET_MS: Mapping[str, int] = {
    "session_start": 1400, "prompt": 1200, "stop": 1400, "post_edit": 300}


@dataclass(frozen=True)
class HooksConfig:
    budget_ms: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_HOOK_BUDGET_MS))
    brief_lines: int = 30
    prompt_lines: int = 20
    # R9 context economy: the most a prompt hook injects (records are one line each, and only
    # when new or changed this session); estimated at 4 characters per token
    prompt_tokens: int = 200
    # the session-start brief: a few lines plus a pointer (compact), or the long brief (full)
    session_brief: str = "compact"
    summary_proposed_cap: int = 3


@dataclass(frozen=True)
class ApproveConfig:
    affirmations: tuple[str, ...] = DEFAULT_AFFIRMATIONS


@dataclass(frozen=True)
class JudgmentConfig:
    backend: str = "heuristic"
    hook_timeout_ms: int = 800
    jev: Mapping[str, Any] = field(default_factory=lambda: {
        "model": "jev-latest", "validated_against": "jev-1.13.0",
        "base_url": "https://api.typesafe.ai",
        "thresholds": {"accept": 0.9, "escalate_llm": 0.5},
        # the NAME of the environment variable holding the credential (sp2 C7); plumb never
        # stores the secret
        "credential_env": "TYPESAFE_API_KEY"})


DEFAULT_SHARED_GLOBS = (".plumb/claims.yaml", "**/contracts.py", "**/cli.py",
                        "**/migrations/**", "**/schema*", "**/*.schema.json")
DEFAULT_IRREVERSIBLE = ("delete", "drop", "migrate", "migration", "publish", "release",
                        "credential", "secret", "password", "security", "purge", "wipe")


@dataclass(frozen=True)
class EscalationConfig:
    max_requirements: int = 3
    max_features: int = 1
    diff_lines: int = 400
    diff_files: int = 10
    # sp2 6.1 trigger 3: shared surfaces (path globs; verify.infra_globs count too)
    shared_globs: tuple[str, ...] = DEFAULT_SHARED_GLOBS
    # sp2 6.1 trigger 4: hard-to-undo effects (words in the request, or path globs with "/")
    irreversible: tuple[str, ...] = DEFAULT_IRREVERSIBLE


@dataclass(frozen=True)
class TriageConfig:
    low_risk_min: float = 0.8


@dataclass(frozen=True)
class AutoApproveConfig:
    """The ``config.yaml`` mirror only: the effective state is the owner's ``config``
    event (sp2 C4)."""

    enabled: bool = False
    backend: str = "jev"
    min_probability: float = 0.9
    min_confidence: str = "high"


@dataclass(frozen=True)
class CalibrationConfig:
    min_items: int = 20          # the owner's own past decisions, per record kind (R13 Q1)
    min_negatives: int = 5       # 'no' examples; generated ones count up to half
    max_false_accept: float = 0.0


@dataclass(frozen=True)
class ClarifyConfig:
    answered_min: float = 0.5    # share of a question's terms a confirmed record covers


@dataclass(frozen=True)
class HintsConfig:
    hidden_deps_max: int = 5
    hidden_deps_s: float = 1.0
    authoritative_docs: tuple[str, ...] = ("docs/concept.md", "docs/specs/**")


@dataclass(frozen=True)
class TraceConfig:
    # source paths (fnmatch globs, ``*`` crosses ``/``) the owner says need no requirement
    exempt: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    source_dirs: tuple[str, ...] = ("src", "tests")
    # whether config.yaml names source_dirs; when it does not, plumb.trace also counts a code
    # file anywhere outside tests, docs and dot directories as source (a flat layout)
    source_dirs_set: bool = False
    test_dirs: tuple[str, ...] = ("tests",)
    verify: VerifyConfig = field(default_factory=VerifyConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    approve: ApproveConfig = field(default_factory=ApproveConfig)
    judgment: JudgmentConfig = field(default_factory=JudgmentConfig)
    escalation: EscalationConfig = field(default_factory=EscalationConfig)
    trace: TraceConfig = field(default_factory=TraceConfig)
    triage: TriageConfig = field(default_factory=TriageConfig)
    auto_approve: AutoApproveConfig = field(default_factory=AutoApproveConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    clarify: ClarifyConfig = field(default_factory=ClarifyConfig)
    hints: HintsConfig = field(default_factory=HintsConfig)


_NESTED = {"verify": VerifyConfig, "hooks": HooksConfig, "approve": ApproveConfig,
           "judgment": JudgmentConfig, "escalation": EscalationConfig, "trace": TraceConfig,
           "triage": TriageConfig, "auto_approve": AutoApproveConfig,
           "calibration": CalibrationConfig, "clarify": ClarifyConfig, "hints": HintsConfig}


def _build(cls: type, data: Mapping[str, Any]) -> Any:
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        nested = _NESTED.get(f.name) if cls is Config else None
        if nested is not None and isinstance(value, Mapping):
            value = _build(nested, value)
        elif isinstance(value, list):
            value = tuple(value)
        elif isinstance(f.default, tuple) and isinstance(value, str):
            value = (value,)
        elif isinstance(value, Mapping) and f.default_factory is not dataclasses.MISSING:
            merged = dict(f.default_factory())  # type: ignore[misc]
            merged.update(value)
            value = merged
        kwargs[f.name] = value
    return cls(**kwargs)


def config_from_mapping(data: Mapping[str, Any] | None) -> Config:
    data = {k: v for k, v in (data or {}).items() if k != "source_dirs_set"}
    return dataclasses.replace(_build(Config, data), source_dirs_set="source_dirs" in data)


def load_config(root: Path) -> Config:
    """Config for ``root``; defaults when ``.plumb/config.yaml`` is absent."""
    plumb_dir = Path(root) / ".plumb"
    path = plumb_dir / "config.yaml"
    try:
        stat = path.stat()
    except OSError:
        return Config()
    key = f"{stat.st_size}:{stat.st_mtime_ns}"
    cache = plumb_dir / "cache" / "config.json"
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("key") == key:
            return config_from_mapping(cached.get("data"))
    except (OSError, ValueError):
        pass
    import yaml

    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=loader) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"key": key, "data": data}, default=str), encoding="utf-8")
    except OSError:
        pass
    return config_from_mapping(data)
