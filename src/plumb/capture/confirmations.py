"""Who confirmed what, in the owner's terms (R8 B, R13 Q4; sp2 8.2, 11.1).

- "confirmed by you": an owner approval (``plumb approve``, ``spec approve``, ``triage
  --approve``);
- "confirmed by you (relayed)": the agent relayed the owner's own words (R2);
- "confirmed by JEV": a ``by: auto-jev`` approval (R8 B), revocable with ``plumb revoke``;
- "self-recorded message": the relayed words come from a message the agent recorded itself
  (a host without a prompt hook, R13 Q4), not from the prompt hook. The label follows the
  confirmation everywhere it is shown.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plumb.api import Core

SELF_RECORDED = "self-recorded message"
WORDS = {"owner": "you", "agent-relayed": "you (relayed)", "auto-jev": "JEV",
         "import": "import"}


def standing(core: Core) -> dict[str, tuple[str, str, Any]]:
    """``{id: (hash, by, entry)}`` of each record's latest standing approval."""
    from plumb.confirm import remaining_entries

    out: dict[str, tuple[str, str, Any]] = {}
    for record_id, approvals in remaining_entries(
            core.events(), core.config.approve.affirmations).items():
        if approvals:
            out[record_id] = approvals[-1]
    return out


def is_self_recorded(entry: Any) -> bool:
    return bool(entry is not None and entry.payload.get("self_recorded"))


def labels_for(core: Core, ids: Iterable[str]) -> dict[str, str]:
    """``{id: "self-recorded message"}`` for confirmations resting on such a message."""
    index = core.index()
    latest = standing(core)
    out: dict[str, str] = {}
    for record_id in ids:
        item = latest.get(record_id)
        record = index.get(record_id)
        if item and record is not None and item[0] == record.hash \
                and is_self_recorded(item[2]):
            out[record_id] = SELF_RECORDED
    return out


def confirmation_label(core: Core, record_id: str) -> str:
    """"proposed", "confirmed by you", "confirmed by JEV", ..., with the Q4 label."""
    status = core.status([record_id]).get(record_id)
    if status is None:
        return "unknown"
    if status.confirmation != "confirmed":
        return "edited since confirmed" if status.confirmation == "unconfirmed-edit" \
            else "proposed"
    text = f"confirmed by {WORDS.get(str(status.approved_by), str(status.approved_by))}"
    label = labels_for(core, [record_id]).get(record_id)
    return f"{text}, {label}" if label else text


def confirmation_counts(core: Core) -> Mapping[str, int]:
    """``{"owner", "agent-relayed", "auto-jev", "import", "proposed", "self-recorded"}``:
    confirmed records by the source of their confirmation, and the records awaiting the
    owner (proposed or edited)."""
    counts = {"owner": 0, "agent-relayed": 0, "auto-jev": 0, "import": 0, "proposed": 0,
              "self-recorded": 0}
    statuses = core.status()
    latest = standing(core)
    for record_id, status in statuses.items():
        if status.confirmation != "confirmed":
            counts["proposed"] += 1
            continue
        by = str(status.approved_by)
        counts[by] = counts.get(by, 0) + 1
        item = latest.get(record_id)
        if item and is_self_recorded(item[2]):
            counts["self-recorded"] += 1
    return counts
