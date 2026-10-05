"""Confidence-tier routing with version-drift suspension (spec 8.2).

Extracted from pi-agent-factory's ``substrate/judgment/tiers.py``: confidence >= ``accept``
is ``accept``, >= ``escalate_llm`` is ``escalate-llm``, below is ``escalate-human``. When
the resolved model version differs from the version the thresholds were validated against,
``accept`` becomes ``escalate-llm``. ``escalate-human`` reaches the owner only when the item
also meets one of the three interruption triggers (spec 6.5); routing alone never asks.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from plumb.contracts import Tier


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
            and resolved_version != validated_against):
        return "escalate-llm"
    return tier
