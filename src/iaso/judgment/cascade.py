"""The cascade-to-LLM hook point (spec 8.2): ``HostAgentCascade``.

A judgment the backend is not sure of goes to a stronger judge. In sub-project 1 that judge
is the host agent itself: ``escalate`` queues the request's one-line instruction in
``.iaso/session/escalations.jsonl``, and the next prompt or stop hook prints it. iaso calls
no LLM. An ``escalate-human`` judgment reaches the owner only when the item also meets one
of the three interruption triggers (spec 6.5); otherwise the agent is told not to ask.
"""

from __future__ import annotations

from iaso.paths import state_dir

import json
from pathlib import Path

from iaso.contracts import EscalationRequest, Judgment

# The three interruption triggers of spec 6.5.
TRIGGERS = frozenset({"intent-change", "decision", "regression"})


def reaches_owner(judgment: Judgment, trigger: str | None) -> bool:
    """True only for ``escalate-human`` together with one of the three triggers."""
    return judgment.tier == "escalate-human" and trigger in TRIGGERS


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


class HostAgentCascade:
    """``LLMCascade`` that hands escalations to the host agent through a queue file."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.queue = state_dir(self.root) / "session" / "escalations.jsonl"

    def escalate(self, request: EscalationRequest) -> None:
        judgment = request.judgment
        if judgment.tier == "accept":
            return
        instruction = _one_line(request.instruction)
        if judgment.tier == "escalate-human":
            trigger = request.packet.get("trigger") if request.packet else None
            if reaches_owner(judgment, trigger):
                instruction += f" (low confidence, trigger {trigger}: ask the owner)"
            else:
                instruction += (" (low confidence, no interruption trigger: judge it "
                                "yourself and do not ask the owner)")
        from iaso.normalize import utc_now

        row = {"at": utc_now(), "subject": judgment.subject, "instruction": instruction}
        try:
            self.queue.parent.mkdir(parents=True, exist_ok=True)
            with self.queue.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            pass  # an escalation is advisory; losing one never blocks work
