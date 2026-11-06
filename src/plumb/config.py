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
    turn_budget_s: float = 60
    hard_limit_factor: float = 1.5
    fill_fraction: float = 0.65  # a selection's estimate fills this share of the budget
    sample_size: int = 10
    default_test_s: float = 1.0
    workers: int = 0
    # the interpreter that runs the tests: "" picks the repository's .venv when it has one,
    # else the interpreter plumb runs in (the plugin's own has no pytest)
    python: str = ""
    flaky_rerun: bool = True
    infra_globs: tuple[str, ...] = DEFAULT_INFRA_GLOBS
    # SR-110: tests chosen by the functions they execute (auto), or by imports only (off)
    coverage: str = "auto"


# Soft budgets per hook, from process start (SR-181, SR-310). Generous on purpose: on a loaded 2-core
# machine a 4 s budget still skipped the check on most turns (pytest alone starts in 15 s
# there). They sit under the watchdog's hard limit (hookio.HARD_LIMIT_S, 90 s, or
# hooks.hard_limit_s), which is the bound; a cut keeps the intent-translation lines
# (hookio.HookContext.keep). The host's own hook timeouts (120 s, SR-310) stay above the hard
# limit plus the stop hook's grace.
DEFAULT_HOOK_BUDGET_MS: Mapping[str, int] = {
    "session_start": 60000, "prompt": 60000, "stop": 60000, "post_edit": 15000}


@dataclass(frozen=True)
class HooksConfig:
    budget_ms: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_HOOK_BUDGET_MS))
    # SR-181: the watchdog's hard limit in seconds; unset = hookio.HARD_LIMIT_S
    hard_limit_s: float | None = None
    brief_lines: int = 30
    prompt_lines: int = 20
    # R9 context economy: the most a prompt hook injects (records are one line each, and only
    # when new or changed this session); estimated at 4 characters per token
    prompt_tokens: int = 200
    summary_proposed_cap: int = 3
    # sp5 3: the most the stop hook's agent instructions inject (4 characters per token)
    stop_tokens: int = 150
    # SR-111: how many times a turn is held open for stale links before it is let go
    stale_holds_max: int = 3


@dataclass(frozen=True)
class ApproveConfig:
    affirmations: tuple[str, ...] = DEFAULT_AFFIRMATIONS


@dataclass(frozen=True)
class JudgmentConfig:
    backend: str = ""
    hook_timeout_ms: int = 5000
    jev: Mapping[str, Any] = field(default_factory=lambda: jev_settings({}))


# A provider preset supplies the JEV defaults; explicit judgment.jev values still win.
# credential_env is the NAME of the environment variable holding the credential (sp2 C7);
# plumb never stores the secret.
JEV_PROVIDERS: Mapping[str, Mapping[str, str]] = {
    "typesafe": {"base_url": "https://api.typesafe.ai", "path": "/v1/systemone",
                 "model": "jev-latest", "validated_against": "jev-1.13.0",
                 "credential_env": "TYPESAFE_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai", "path": "/api/alpha/decisions",
                   "model": "typesafe/jev-1.13", "validated_against": "typesafe/jev-1.13",
                   "credential_env": "OPENROUTER_API_KEY"},
}
DEFAULT_JEV_PROVIDER = "typesafe"
# the provider-specific ``judgment.jev`` keys a new provider choice replaces (jev setup)
PROVIDER_KEYS = frozenset({"base_url", "path", "model", "validated_against", "credential_env"})


def jev_settings(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """``judgment.jev`` resolved: the provider preset's defaults (``typesafe`` unless
    ``provider`` names another), then every value given explicitly."""
    raw = dict(raw or {})
    provider = str(raw.get("provider") or DEFAULT_JEV_PROVIDER).strip().lower()
    preset = JEV_PROVIDERS.get(provider, JEV_PROVIDERS[DEFAULT_JEV_PROVIDER])
    settings: dict[str, Any] = {"provider": provider, **preset,
                                "thresholds": {"accept": 0.9, "escalate_llm": 0.5}}
    settings.update({k: v for k, v in raw.items() if v is not None})
    settings["provider"] = provider
    return settings


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
    answered_min: float = 0.6    # share of a question's terms a confirmed record covers


@dataclass(frozen=True)
class HintsConfig:
    hidden_deps_max: int = 5
    hidden_deps_s: float = 1.0
    authoritative_docs: tuple[str, ...] = ("docs/concept.md", "docs/specs/**")


@dataclass(frozen=True)
class TraceConfig:
    # source paths (fnmatch globs, ``*`` crosses ``/``) the owner says need no requirement
    exempt: tuple[str, ...] = ()


CARD_RETIRED = ("plumb: the card setting (full, compact, off) is retired and has no effect; "
                "cards go to the agent as text and the owner sees one plumb line at most")


@dataclass(frozen=True)
class PresentConfig:
    # retired (SR-173): the intent card's full | compact | off; read as off, ignored
    card: str = ""
    ascii: bool = False          # the status card without glyphs


@dataclass(frozen=True)
class AwarenessConfig:
    # sp6 9 (SR-078, SR-079): what other worktrees and branches are changing, read-only
    enabled: bool = True
    branches: bool = True        # local branches without a worktree, scanned at session start
    remotes: bool = False        # remote-tracking branches (off: other clones meet at merge)
    max_age_days: int = 7        # another worktree's changing.json older than this is ignored
    branch_max: int = 8          # branches scanned per session start
    branch_scan_ms: int = 400    # time cap of that scan
    brief_lines: int = 3         # overlap lines in the session brief, then "+N more"


@dataclass(frozen=True)
class ResolveConfig:
    # sp5 5: the owner's words resolve to one thing only when its score is at least
    # min_score and more than margin ahead of the next candidate; otherwise plumb asks
    min_score: float = 0.34
    margin: float = 0.1


LEVELS = ("haiku", "sonnet", "opus", "fable")   # SR-389: smallest to largest


@dataclass(frozen=True)
class UnderstandConfig:
    """SP8: the model-backed understanding layer."""

    dispatch: str = "auto"       # auto | claude-code | hermes | openrouter
    model: str = "haiku"
    judge_model: str = "haiku"       # SR-182: gives the verdict below JEV's threshold (or without JEV)
    repin_model: str = "sonnet"      # SR-111 EX-4: judges whether a stale link's change matters
    # SR-114: JEV repins alone at or above this probability, set from the labelled repin set
    # (``eval --repin``: the lowest threshold with no false repin); None leaves the tier off
    repin_jev_threshold: float | None = None
    diagnose_model: str = "opus"     # SR-114: diagnoses a change Sonnet says matters (SR-113)
    timeout_s: float = 120
    clarify_wait_s: float = 45
    reader_threshold_start: float = 0.9
    backlog_cards_per_turn: int = 3
    progress_min_s: float = 2
    progress_interval_s: float = 1
    max_consecutive_failures: int = 3
    # SR-387: independent model calls of a queue sent together (DEC-427: 3, the owner)
    parallel_calls: int = 3
    # SR-389: the model each capability level runs; the stage settings above name a level
    levels: dict[str, str] = field(default_factory=lambda: {n: n for n in LEVELS})

    def __post_init__(self) -> None:
        if self.parallel_calls < 1:
            raise ValueError(f"understand.parallel_calls is at least 1; got {self.parallel_calls}")
        if set(self.levels) != set(LEVELS):
            raise ValueError("understand.levels names exactly the four levels "
                             + ", ".join(LEVELS) + f"; got {', '.join(map(str, self.levels))}")


def model_of(config: "Config", level: str) -> str:
    """SR-389: the model a level runs; a name that is no level is a model and stays as it is."""
    return config.understand.levels.get(level, level)


@dataclass(frozen=True)
class DebugConfig:
    """SR-327: self-debug outside plumb's own repository, and issue reporting, both off."""

    self_fix: bool = False
    source: str = ""             # plumb's source checkout, where the fix lands on a branch
    report_issues: bool = False
    issues_repo: str = ""        # owner/name; empty: plumb's own GitHub repository


@dataclass(frozen=True)
class MergeConfig:
    """The merge boundary (``plumb.boundary.cli.merge_settings``)."""

    default_base: str | None = None   # unset: the detected default branch
    prepush_run_full: bool = True
    guard_main: bool = True           # SR-384: the pre-tool hook refuses writes in main's checkout


@dataclass(frozen=True)
class Config:
    source_dirs: tuple[str, ...] = ("src", "tests")
    # whether config.yaml names source_dirs; when it does not, plumb.trace also counts a code
    # file anywhere outside tests, docs and dot directories as source (a flat layout)
    source_dirs_set: bool = False
    test_dirs: tuple[str, ...] = ("tests",)
    # SR-380: parts that take no part in drift, the brief or the merge hold (plumb.frozen)
    freeze: tuple[str, ...] = ()
    verify: VerifyConfig = field(default_factory=VerifyConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    approve: ApproveConfig = field(default_factory=ApproveConfig)
    judgment: JudgmentConfig = field(default_factory=JudgmentConfig)
    escalation: EscalationConfig = field(default_factory=EscalationConfig)
    trace: TraceConfig = field(default_factory=TraceConfig)
    auto_approve: AutoApproveConfig = field(default_factory=AutoApproveConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    clarify: ClarifyConfig = field(default_factory=ClarifyConfig)
    hints: HintsConfig = field(default_factory=HintsConfig)
    present: PresentConfig = field(default_factory=PresentConfig)
    resolve: ResolveConfig = field(default_factory=ResolveConfig)
    awareness: AwarenessConfig = field(default_factory=AwarenessConfig)
    understand: UnderstandConfig = field(default_factory=UnderstandConfig)
    merge: MergeConfig = field(default_factory=MergeConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)


_NESTED = {"verify": VerifyConfig, "hooks": HooksConfig, "approve": ApproveConfig,
           "judgment": JudgmentConfig, "escalation": EscalationConfig, "trace": TraceConfig,
           "auto_approve": AutoApproveConfig,
           "calibration": CalibrationConfig, "clarify": ClarifyConfig, "hints": HintsConfig,
           "present": PresentConfig, "resolve": ResolveConfig,
           "awareness": AwarenessConfig, "understand": UnderstandConfig, "merge": MergeConfig,
           "debug": DebugConfig}


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
        elif cls is JudgmentConfig and f.name == "jev" and isinstance(value, Mapping):
            value = jev_settings(value)
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
