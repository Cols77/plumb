"""``iaso.capture.api``: what CAPTURE provides to the other lanes (sp2 11.1).

PRESENT (hooks, cards, review, drift), MERGE (``diff_serves`` in ``trailers check-msg``) and
HOSTS (through PRESENT) call these functions only. Each returns within about 1 s with the
heuristic and degrades to an empty result on any error, so a hook that calls it never fails
because of it. None of them confirms anything; ``capture`` writes proposed records only
(and, only when the owner turned it on, the narrow auto-approval of sp2 8.2).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from iaso.contracts import (
    AutoApproveState,
    CaptureResult,
    ClarifyView,
    DiffStats,
    EscalationSuggestion,
    IntentFlag,
    Proposal,
)

if TYPE_CHECKING:
    from iaso.api import Core

def _safe[T](default: T, call: Callable[[], T]) -> T:
    try:
        return call()
    except Exception:  # noqa: BLE001 - an advisory lane never fails its caller
        return default


def capture(core: Core, doc: Mapping[str, Any], *, prompt_digest: str | None = None,
            dry_run: bool = False) -> CaptureResult:
    """Write the read-back ``doc`` as proposed records (sp2 5.1). Raises ``CaptureError``
    on a bad document (the command maps it to exit 2): a writer is told, never silenced."""
    from iaso.capture.capture import capture as _capture

    return _capture(core, doc, prompt_digest=prompt_digest, dry_run=dry_run)


def intent_flags(core: Core, prompt: str, matched: Sequence[str]) -> Sequence[IntentFlag]:
    from iaso.capture.flags import intent_flags as _flags

    return _safe([], lambda: _flags(core, prompt, matched))


def escalation(core: Core, *, prompt: str | None = None, matched: Sequence[str] = (),
               diff: DiffStats | None = None) -> Sequence[EscalationSuggestion]:
    from iaso.capture.escalation import escalation as _escalation

    return _safe([], lambda: _escalation(core, prompt=prompt, matched=matched, diff=diff))


def next_question(core: Core, touched: Sequence[str]) -> str | None:
    """The one DEC to ask next (R11 "ONE per message"): the earliest-recorded unconfirmed
    decision that matters among ``touched`` or deciding a touched record, else None."""
    from iaso.capture.clarify import next_question as _next

    return _safe(None, lambda: _next(core, touched))


def confirmation_counts(core: Core) -> Mapping[str, int]:
    """``{"owner", "agent-relayed", "auto-jev", "import", "proposed", "self-recorded"}``."""
    from iaso.capture.confirmations import confirmation_counts as _counts

    return _safe({}, lambda: _counts(core))


def confirmation_label(core: Core, record_id: str) -> str:
    """"confirmed by you", "confirmed by JEV", "..., self-recorded message" (R8 B, R13 Q4)."""
    from iaso.capture.confirmations import confirmation_label as _label

    return _safe("", lambda: _label(core, record_id))


def auto_approve_state(core: Core) -> AutoApproveState:
    from iaso.capture.autoapprove import auto_approve_state as _state

    return _safe(AutoApproveState(), lambda: _state(core))


def ownership_proposals(core: Core, paths: Sequence[str]) -> Mapping[str, Proposal]:
    from iaso.capture.ownership import ownership_proposals as _proposals

    return _safe({}, lambda: _proposals(core, paths))


def diff_serves(core: Core, sr_ids: Sequence[str], paths: Sequence[str]) -> Sequence[str]:
    """Warning lines for claimed SRs the diff may not serve (non-blocking, sp2 10.1)."""
    from iaso.capture.ownership import diff_serves as _serves

    return _safe([], lambda: _serves(core, sr_ids, paths))


def drift_hints(core: Core, changed: Sequence[str]) -> Sequence[str]:
    """Hint lines: hidden dependencies and proposed test nodes; never edges (sp2 10)."""
    from iaso.capture.hints import drift_hints as _hints

    return _safe([], lambda: _hints(core, changed))


def clarify(core: Core, request: str,
            questions: Sequence[Mapping[str, Any]] = ()) -> ClarifyView:
    from iaso.capture.clarify import clarify as _clarify

    return _safe(ClarifyView(), lambda: _clarify(core, request, questions))
