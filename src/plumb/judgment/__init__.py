"""Optional, advisory judgment (spec 8.2): ``get_backend`` and ``get_cascade``.

plumb works without any judgment service. ``judgment.backend`` in ``.plumb/config.yaml``
picks the backend: ``heuristic`` (default), ``jev`` (only when a key exists outside the
repository; any failure falls back to the heuristic with one notice per session),
``disabled`` or ``fake`` (tests). Judgments order, filter and annotate; they never confirm a
record or freshen evidence.

Kept import-light: the prompt hook calls ``get_backend`` every turn.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import FidelityPacket, Judgment, LinkState, Record

BACKENDS = ("heuristic", "jev", "disabled", "fake")
NOTICE_WINDOW_S = 12 * 3600

# Canned answers for the ``fake`` backend: {(action, subject): (verdict, confidence)}.
FAKE_ANSWERS: dict[tuple[str, str], tuple[str, float]] = {}


def _config(core: Any) -> Any:
    config = getattr(core, "config", None)
    if config is None:
        from plumb.config import load_config

        config = load_config(Path(core.root))
    return config


def notice_once(root: Path, key: str, text: str, *, now: float | None = None) -> str | None:
    """``text`` the first time ``key`` is seen in this session window, else None.

    Kept in the gitignored ``.plumb/session/judgment_notices.json``; a notice repeats after
    ``NOTICE_WINDOW_S`` (a working session), never on every turn.
    """
    path = Path(root) / ".plumb" / "session" / "judgment_notices.json"
    now = time.time() if now is None else now
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(seen, dict):
            seen = {}
    except (OSError, ValueError):
        seen = {}
    last = seen.get(key)
    if isinstance(last, (int, float)) and now - last < NOTICE_WINDOW_S:
        return None
    seen[key] = now
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seen, sort_keys=True), encoding="utf-8")
    except OSError:
        pass
    return text


class _FixedBackend:
    """Shared shape of the ``disabled`` and ``fake`` backends."""

    name = "disabled"

    def __init__(self, thresholds: Any = None) -> None:
        from plumb.judgment.tiers import Thresholds

        self.thresholds = thresholds or Thresholds()
        self.notices: tuple[str, ...] = ()

    def answer(self, action: str, subject: str) -> tuple[str, float]:
        return "unsure", 0.5

    def _judgment(self, action: str, subject: str, *inputs: object) -> Judgment:
        from plumb.judgment.heuristic import fingerprint
        from plumb.judgment.tiers import route

        verdict, confidence = self.answer(action, subject)
        tier = "escalate-llm" if verdict == "unsure" else route(confidence, self.thresholds)
        return Judgment(action=action, subject=subject, verdict=verdict,  # type: ignore[arg-type]
                        confidence=confidence, tier=tier, backend=self.name,  # type: ignore[arg-type]
                        fingerprint=fingerprint(self.name, action, subject, *inputs))

    def intent_change(self, prompt: str, records: Sequence[Record]) -> Sequence[Judgment]:
        from plumb.normalize import sha256_text

        digest = sha256_text(prompt)
        return [self._judgment("intent-change", r.id, digest, r.hash) for r in records]

    def drift_triage(self, states: Sequence[LinkState],
                     texts: Mapping[str, tuple[str, str]]) -> Sequence[Judgment]:
        return [self._judgment("drift-triage", s.link.id) for s in states
                if s.link.id in texts]

    def fidelity(self, packet: FidelityPacket) -> Judgment:
        return self._judgment("fidelity", packet.requirement, packet.fingerprint)

    # -- sp2 11.2
    version = "none"

    def _typed(self, action: str, subject: str, *inputs: object) -> Judgment:
        import dataclasses

        judgment = self._judgment(action, subject, *inputs)
        if judgment.verdict == "unsure":
            judgment = dataclasses.replace(judgment, confidence=0.0)
        return dataclasses.replace(judgment, probability=judgment.confidence,
                                   confidence_label="low")

    def entailment(self, premise: str, hypothesis: str, *, subject: str,
                   claim_kind: str) -> Judgment:
        return self._typed("faithfulness", subject, claim_kind, premise, hypothesis)

    def contradiction(self, prompt: str, record: Record) -> Judgment:
        return self._typed("contradiction", record.id, prompt, record.hash)

    def choose(self, question: str, options: Sequence[str], *, subject: str,
               context: str = "") -> Judgment:
        return self._typed("ownership", subject, question, list(options), context)

    def ask(self, question: str, context: str, *, subject: str, action: str) -> Judgment:
        return self._typed(action, subject, question, context)


class DisabledBackend(_FixedBackend):
    """Every call returns ``unsure`` with tier ``escalate-llm``."""

    name = "disabled"


class FakeBackend(_FixedBackend):
    """Canned answers from ``FAKE_ANSWERS`` (tests only); ``unsure`` otherwise."""

    name = "fake"

    def __init__(self, answers: Mapping[tuple[str, str], tuple[str, float]] | None = None,
                 thresholds: Any = None) -> None:
        super().__init__(thresholds)
        self.answers = FAKE_ANSWERS if answers is None else dict(answers)

    def answer(self, action: str, subject: str) -> tuple[str, float]:
        return self.answers.get((action, subject), ("unsure", 0.5))


def get_cascade(core: Any) -> Any:
    """The ``LLMCascade`` (spec 12.2): the host agent, through the escalation queue."""
    from plumb.judgment.cascade import HostAgentCascade

    return HostAgentCascade(Path(core.root))


def get_backend(core: Any, *, hook: bool) -> Any:
    """The configured ``JudgmentBackend`` (spec 12.2). Never raises for configuration."""
    from plumb.judgment.heuristic import HeuristicBackend
    from plumb.judgment.tiers import Thresholds

    config = _config(core)
    judgment = config.judgment
    thresholds = Thresholds.from_config(judgment.jev)
    name = str(judgment.backend or "heuristic").strip().lower()
    root = Path(core.root)
    if name == "heuristic":
        return HeuristicBackend(thresholds)
    if name == "disabled":
        return DisabledBackend(thresholds)
    if name == "fake":
        return FakeBackend(thresholds=thresholds)
    if name == "jev":
        try:
            from plumb.judgment.jev import open_jev
        except ImportError:
            note = notice_once(root, "jev-missing", "plumb: judgment backend jev is not "
                               "available in this build; using the heuristic")
            return HeuristicBackend(thresholds, [note] if note else [])
        return open_jev(core, config, hook=hook, thresholds=thresholds)
    note = notice_once(root, f"unknown-{name}", f"plumb: unknown judgment backend {name!r}; "
                       "using the heuristic")
    return HeuristicBackend(thresholds, [note] if note else [])
