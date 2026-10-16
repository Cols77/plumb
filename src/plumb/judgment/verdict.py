"""Who gave a verdict on whether a record is supported by the owner's words (SR-182).

A verdict is JEV's (``by == "jev"``: its probability rose above max(0.9, the threshold
calibrated on the owner's labels with no false accept)) or the judge model's
(``by == "model"``). The first may take the fast track; the second never does, however high the
model's own confidence: a model verdict approves only after a question round, when it says the
intent is clear (DEC-141, SR-248)."""

from __future__ import annotations

from dataclasses import dataclass

JEV = "jev"
MODEL = "model"
BY = (JEV, MODEL)


@dataclass(frozen=True)
class Verdict:
    verdict: str            # supported | beyond | contradicts
    by: str                 # jev | model
    judge: str              # who answered: ``jev:<version>`` or ``<dispatcher>:<model>``
    confidence: float

    @property
    def auto_approvable(self) -> bool:
        return refusal(self.by, self.verdict) is None


def refusal(by: object, verdict: object = "supported") -> str | None:
    """Why a verdict may not feed auto-approval, or None. Only a supported verdict that is
    JEV's counts; a verdict with no marker (an old one) is not taken as JEV's."""
    if by == MODEL:
        return ("the verdict is the judge model's, which never takes the fast track: it "
                "approves only after a question round")
    if by != JEV:
        return "the verdict does not say JEV gave it"
    if verdict != "supported":
        return f"the verdict is {verdict}, not supported"
    return None
