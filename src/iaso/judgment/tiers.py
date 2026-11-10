"""Confidence-tier routing with version-drift suspension (spec 8.2).

Extracted from pi-agent-factory's ``substrate/judgment/tiers.py``: confidence >= ``accept``
is ``accept``, >= ``escalate_llm`` is ``escalate-llm``, below is ``escalate-human``. When
the resolved model version differs from the version the thresholds were validated against,
``accept`` becomes ``escalate-llm``; versions are compared only through ``same_version``
(one normalizer: a gateway's ``typesafe/jev-1.13-20260917`` is ``jev-1.13.0``).
``escalate-human`` reaches the owner only when the item also meets one of the three
interruption triggers (spec 6.5); routing alone never asks.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from iaso.contracts import Tier


@dataclass(frozen=True)
class Thresholds:
    accept: float = 0.9
    escalate_llm: float = 0.5

    @classmethod
    def from_config(cls, jev: Mapping[str, Any] | None) -> Thresholds:
        raw = (jev or {}).get("thresholds") or {}
        try:
            return cls(accept=float(raw.get("accept", 0.9)),
                       escalate_llm=float(raw.get("escalate_llm", 0.5)))
        except (TypeError, ValueError, AttributeError):
            return cls()


_DEFAULT = Thresholds()
_SNAPSHOT = re.compile(r"-\d{8}$")
_ZERO_PATCH = re.compile(r"(\d+\.\d+)(?:\.0+)+$")


def normalize_version(version: str | None) -> str | None:
    """The one model-version normalizer: lower case, no leading ``~`` (a gateway alias
    marker), no vendor prefix (``typesafe/``), no trailing ``-YYYYMMDD`` snapshot date and no
    zero patch, so ``jev-1.13``, ``jev-1.13.0`` and ``typesafe/jev-1.13-20260917`` are one
    version. None for an empty version."""
    if version is None:
        return None
    text = str(version).strip().lower().lstrip("~")
    text = text.rsplit("/", 1)[-1].lstrip("~")
    text = _ZERO_PATCH.sub(lambda m: m.group(1), _SNAPSHOT.sub("", text))
    return text or None


def same_version(a: str | None, b: str | None) -> bool:
    """Whether two model names denote the same version (both present)."""
    na, nb = normalize_version(a), normalize_version(b)
    return na is not None and na == nb


def route(confidence: float, thresholds: Thresholds = _DEFAULT, *,
          resolved_version: str | None = None, validated_against: str | None = None) -> Tier:
    """The tier of one answer. Drift is checked only when ``validated_against`` is given."""
    if confidence >= thresholds.accept:
        tier: Tier = "accept"
    elif confidence >= thresholds.escalate_llm:
        tier = "escalate-llm"
    else:
        tier = "escalate-human"
    if (tier == "accept" and validated_against is not None
            and not same_version(resolved_version, validated_against)):
        return "escalate-llm"
    return tier
