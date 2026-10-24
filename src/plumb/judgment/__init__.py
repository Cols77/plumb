"""Optional, advisory judgment (spec 8.2): ``get_backend`` and ``get_cascade``.

Parts of plumb that need no judgment work without any judgment service. ``judgment.backend``
in ``.plumb/config.yaml`` picks the judge: ``jev`` (needs a key outside the repository),
``disabled`` or ``fake`` (tests). There is no rule-based stand-in (INT-029): with no judge
configured, or a judge that has no key, times out or fails, judging raises
``JudgmentUnavailable`` naming the judge and the cause. Judgments order, filter and annotate;
they never confirm a record or freshen evidence.

Kept import-light: the prompt hook calls ``get_backend`` every turn.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import FidelityPacket, Judgment, LinkState, Record

BACKENDS = ("jev", "disabled", "fake")
NOTICE_WINDOW_S = 12 * 3600

# Canned answers for the ``fake`` backend: {(action, subject): (verdict, confidence)}.
FAKE_ANSWERS: dict[tuple[str, str], tuple[str, float]] = {}


class JudgmentUnavailable(RuntimeError):
    """The configured judge cannot answer: not configured, no key, timed out or failed.

    ``judge`` names the judge (``JEV``, or ``no judge`` when none is configured) and ``cause``
    says why; the message is one line. ``code`` is the cause code when the raiser knows it and
    ``detail`` the band's short words for it (SR-359). No rule-based judge answers in its place
    (INT-029)."""

    def __init__(self, judge: str, cause: str, *, code: str = "", detail: str = "") -> None:
        self.judge = judge
        self.cause = cause
        self.code = code
        self.detail = detail
        super().__init__(f"{judge}: {cause}")


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
        from plumb.judgment.common import fingerprint
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
                   claim_kind: str, quote_only: str | None = None) -> Judgment:
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


class UnavailableBackend:
    """Stands for a judge that cannot answer: every judging call raises the error that
    ``get_backend`` raised. For callers that only optionally judge and say why they could
    not (``judging unavailable: <cause>``); it never answers."""

    name = "unavailable"
    version = "none"

    def __init__(self, error: JudgmentUnavailable) -> None:
        self.error = error
        self.notices: tuple[str, ...] = ()

    def __getattr__(self, attr: str) -> Any:
        if attr.startswith("_"):
            raise AttributeError(attr)

        def refuse(*args: object, **kwargs: object) -> Any:
            raise self.error

        return refuse


def optional_backend(core: Any, *, hook: bool) -> Any:
    """``get_backend``, or an ``UnavailableBackend`` carrying the error when no judge can be
    opened."""
    try:
        return get_backend(core, hook=hook)
    except JudgmentUnavailable as exc:
        return UnavailableBackend(exc)


def waiting_line(root: Path, step: str, cause: object) -> str | None:
    """SR-174: the one line saying ``step`` waits because no judge can be reached (no key,
    timeout, API down), the first time in this session window, else None. The step is left
    undone and runs again when a judge is back; nothing stands in for it (INT-029)."""
    return notice_once(Path(root), f"waiting:{step}",
                       f"plumb: {step} is waiting: no judge can be reached ({cause}); it runs "
                       "again when one is back")


# SR-359: a cause code from a provider's or dispatcher's text, first match wins, and its plain
# words; plumb's own causes carry their code on ``JudgmentUnavailable`` instead
CAUSES: tuple[tuple[str, str, str], ...] = (
    ("quota", r"HTTP (402|429)|quota|rate.?limit|credit", "a quota"),
    ("no-key", r"\bno (\w+ )?key\b|not in the environment|API_KEY (is )?(not set|missing)",
     "no key"),
    ("not-configured", r"not set|not a judge|not available|not configured|not installed|"
                       r"could not be started", "not configured"),
    ("timeout", r"time ?out|timed out|no answer within", "timed out"),
    ("network", r"could not be reached|URLError|Connection|network|getaddrinfo|OSError",
     "network down"),
    ("unusable-answer", r"malformed|not JSON|no structured answer|no answer in it|schema|"
                        r"invalid", "an unusable answer"),
    ("provider-error", r"", "the provider's error"),
)


def cause_code(cause: str) -> str:
    """SR-359: the cause code of a judge's failure told only as text."""
    import re

    return next(code for code, pattern, _ in CAUSES if re.search(pattern, cause, re.I))


def _judges(root: Path) -> tuple[Path, dict[str, Any]]:
    path = Path(root) / ".plumb" / "session" / "judges.json"
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        held = {}
    return path, held if isinstance(held, dict) else {}


def _keep(path: Path, held: Mapping[str, Any]) -> None:
    """Atomic, so the band never reads a torn file. shortcut: two judge jobs writing at once
    can lose one's change until its next run; take a lock if the band ever shows it."""
    from plumb.understand.files import write_json_atomic

    try:
        write_json_atomic(path, dict(held))
    except OSError:
        pass


def judge_down(root: Path, judge: str, cause: str, *, code: str = "", detail: str = "",
               slot: str = "") -> None:
    """SR-359 EX-1: note in ``.plumb/session/judges.json`` that ``judge`` cannot settle a
    record and why, for the band's red line, until ``judge_up``. ``slot`` (the judge by
    default) is where it is kept: the model judge keeps one slot whatever its label, so a
    changed model replaces its line."""
    code = code or cause_code(cause)
    detail = detail or cause.removeprefix(f"{judge}: ")
    plain = next(words for c, _, words in CAUSES if c == code)
    slot = slot or judge
    path, held = _judges(root)
    down = held.get("down") if isinstance(held.get("down"), dict) else {}
    line = f"{judge} judge, {plain} ({detail})"
    if (down.get(slot) or {}).get("line") != line:
        _keep(path, {**held, "down": {**down, slot: {"code": code, "cause": cause,
                                                     "line": line}}})


def judge_up(root: Path, slot: str) -> None:
    """SR-359 EX-3: the judge in ``slot`` answered: its red line goes."""
    path, held = _judges(root)
    down = held.get("down") if isinstance(held.get("down"), dict) else {}
    if slot in down:
        _keep(path, {**held, "down": {k: v for k, v in down.items() if k != slot}})


def set_aside(root: Path, questions: Sequence[tuple[str, str]]) -> None:
    """SR-359 EX-2: the judge's questions plumb set aside (the question, why), shown apart
    from a judge that cannot be reached; the last judge job's list replaces the earlier one."""
    path, held = _judges(root)
    aside = [{"question": q, "why": w} for q, w in questions]
    if held.get("set_aside", []) != aside:
        _keep(path, {**held, "set_aside": aside})


def report_unavailable(root: Path, exc: BaseException) -> str | None:
    """The one-line report of ``exc`` the first time it is seen in this session window, else
    None. Hooks print it without blocking the prompt."""
    return notice_once(Path(root), f"unavailable:{exc}", f"plumb: judging unavailable: {exc}")


def get_backend(core: Any, *, hook: bool) -> Any:
    """The configured ``JudgmentBackend`` (spec 12.2).

    Raises ``JudgmentUnavailable`` when no judge is configured or the configured one has no
    key; there is no rule-based fallback (INT-029)."""
    from plumb.judgment.tiers import Thresholds

    config = _config(core)
    judgment = config.judgment
    thresholds = Thresholds.from_config(judgment.jev)
    name = str(judgment.backend or "").strip().lower()
    if name == "disabled":
        return DisabledBackend(thresholds)
    if name == "fake":
        return FakeBackend(thresholds=thresholds)
    if name == "jev":
        try:
            from plumb.judgment.jev import open_jev
        except ImportError:
            raise JudgmentUnavailable("JEV", "the jev backend is not available in this "
                                      "build", code="not-configured") from None
        return open_jev(core, config, hook=hook, thresholds=thresholds)
    if not name:
        raise JudgmentUnavailable("no judge", "judgment.backend is not set in "
                                  ".plumb/config.yaml; set it to jev", code="not-configured")
    raise JudgmentUnavailable("no judge", f"judgment.backend is {name!r}, which is not a "
                              "judge; set judgment.backend to jev", code="not-configured")
