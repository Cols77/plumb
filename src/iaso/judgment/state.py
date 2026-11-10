"""Deterministic judgment state from repository-tracked material (spec 8.2).

Extracted from pi-agent-factory's ``substrate/judgment/state.py``: only git-tracked files
inside the root are read, secret-bearing paths are skipped, environment values found in the
text are redacted, and the result is truncated to the vendor's context limits with a
conservative character-based token estimate (the vendor does not publish its tokenizer).
"""

from __future__ import annotations

import fnmatch
import math
import os
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from iaso.judgment.model import JudgmentQuestion, TruncationReport

CHARS_PER_TOKEN = 3
MIN_REDACTED_ENV_LENGTH = 8
REDACTED_ENV = "[redacted-env]"

SECRET_NAME_PATTERNS = (
    ".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", ".npmrc", ".pypirc", ".netrc",
    ".git-credentials", "*credential*", "*secret*",
)
SECRET_DIR_NAMES = frozenset({".ssh", ".aws", ".gnupg", ".azure", ".kube"})


@dataclass(frozen=True)
class ContextLimits:
    """Per-version token limits: the whole request, and state plus the longest question."""

    request_tokens: int
    state_and_longest_question_tokens: int


VERSION_LIMITS: Mapping[str, ContextLimits] = {"jev-1.13.0": ContextLimits(64000, 32000)}


@dataclass(frozen=True)
class AssembledState:
    text: str
    included: tuple[str, ...]
    excluded: dict[str, str]
    redactions: int
    truncation: TruncationReport


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def context_limits(version: str | None) -> ContextLimits:
    """A version's limits, or the smallest known limits for an unknown version."""
    from iaso.judgment.tiers import same_version

    for known, limits in VERSION_LIMITS.items():
        if same_version(version, known):
            return limits
    return min(VERSION_LIMITS.values(), key=lambda lim: lim.state_and_longest_question_tokens)


def is_secret_path(path: str) -> bool:
    for part in PurePosixPath(path).parts:
        lowered = part.lower()
        if lowered in SECRET_DIR_NAMES or lowered == "secrets":
            return True
        if any(fnmatch.fnmatchcase(lowered, pattern) for pattern in SECRET_NAME_PATTERNS):
            return True
    return False


def tracked_files(root: Path) -> set[str]:
    """Git-tracked files; an unreadable index yields none (fail closed)."""
    try:
        result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True,
                                check=False)
    except OSError:
        return set()
    if result.returncode != 0:
        return set()
    return {p for p in result.stdout.decode("utf-8", "replace").split("\0") if p}


def _secrets(env: Mapping[str, str] | None) -> list[str]:
    values = (os.environ if env is None else env).values()
    return sorted({v for v in values if len(v.strip()) >= MIN_REDACTED_ENV_LENGTH},
                  key=lambda v: (-len(v), v))


def redact(text: str, env: Mapping[str, str] | None = None) -> tuple[str, int]:
    """``text`` with environment values replaced; returns the number of redactions."""
    count = 0
    for value in _secrets(env):
        count += text.count(value)
        text = text.replace(value, REDACTED_ENV)
    return text, count


def assemble_state(root: Path, paths: Iterable[str],
                   questions: Sequence[tuple[str, JudgmentQuestion]] = (), *,
                   tracked: Iterable[str] | None = None, env: Mapping[str, str] | None = None,
                   limits: ContextLimits | None = None, prefix: str = "") -> AssembledState:
    """State from tracked files (after ``prefix``), fitted to the vendor budget."""
    root = Path(root).resolve()
    tracked_set = set(tracked) if tracked is not None else tracked_files(root)
    included: list[str] = []
    excluded: dict[str, str] = {}
    prefix, redactions = redact(prefix, env)
    chunks: list[str] = [prefix] if prefix else []
    for path in sorted({PurePosixPath(p).as_posix() for p in paths}):
        target = (root / path).resolve()
        # the requested path and what it resolves to must both pass (no symlink smuggling)
        resolved = target.relative_to(root).as_posix() if target.is_relative_to(root) else None
        if resolved is None:
            excluded[path] = "outside-project"
        elif is_secret_path(path) or is_secret_path(resolved):
            excluded[path] = "secret-path"
        elif path not in tracked_set or resolved not in tracked_set:
            excluded[path] = "untracked"
        else:
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                excluded[path] = "unreadable"
                continue
            content, count = redact(content, env)
            redactions += count
            if not content.endswith("\n"):
                content += "\n"
            included.append(path)
            chunks.append(f"--- {path} ---\n{content}")
    text, report = _truncate("".join(chunks), questions, limits or context_limits(None))
    return AssembledState(text, tuple(included), excluded, redactions, report)


def _truncate(text: str, questions: Sequence[tuple[str, JudgmentQuestion]],
              limits: ContextLimits) -> tuple[str, TruncationReport]:
    question_tokens = [estimate_tokens(q.prompt_text()) for _, q in questions]
    budget = max(0, min(limits.state_and_longest_question_tokens
                        - max(question_tokens, default=0),
                        limits.request_tokens - sum(question_tokens)))
    kept = text[: budget * CHARS_PER_TOKEN]
    report = TruncationReport(truncated=len(kept) < len(text), chars_per_token=CHARS_PER_TOKEN,
                              budget_tokens=budget, estimated_tokens=estimate_tokens(text),
                              original_chars=len(text), kept_chars=len(kept))
    return kept, report
