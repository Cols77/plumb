"""``plumb status --card`` (``/plumb`` and ``/plumb status``): the status card, what awaits
the owner and drift, in a few lines (sp5 6.1)."""

from __future__ import annotations

import json
from typing import Any


def _intent_summary(core: Any) -> str:
    """The session's intent from the last snapshot the hooks wrote (it recomputes nothing)."""
    try:
        data = json.loads((core.root / ".plumb" / "session" / "status.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("intent_summary") or "") if isinstance(data, dict) else ""


def status_card_lines(core: Any) -> dict[str, Any]:
    from plumb.hosts.claude_code.snapshot import build_snapshot, tests_state
    from plumb.present.render import status_card

    statuses = core.status()
    evidence = None
    pending = None
    try:
        from plumb.verify import open_verify

        verify = open_verify(core)
        index = core.index()
        mapped = verify.tests_for([i for i, r in index.items() if r.kind == "requirement"])
        nodes = sorted({n for found in mapped.values() for n in found})
        evidence = verify.evidence(nodes) if nodes else None
        pending = verify.full_pending()
    except Exception:  # noqa: BLE001 - VERIFY is optional for the card
        evidence = None
    snapshot = build_snapshot(core, statuses=statuses, full_pending=pending,
                              tests_summary=tests_state(evidence),
                              intent_summary=_intent_summary(core))
    present = getattr(core.config, "present", None)
    lines = [status_card(snapshot, ascii=bool(getattr(present, "ascii", False)))]
    from plumb.present.cards import awaiting_lines, judge_lines

    awaiting = sorted(i for i, s in statuses.items() if s.confirmation != "confirmed")
    lines += awaiting_lines(core, statuses)          # counted, no id, no approve hint (SR-267)
    judged = judge_lines(core, statuses)
    if judged:
        lines += ["judge-approved:", *judged]        # SR-251
    stale = [s.link.id for st in statuses.values() for s in st.links if s.state == "stale"]
    dangling = [s.link.id for st in statuses.values() for s in st.links
                if s.state == "dangling"]
    if stale or dangling:
        lines.append(f"drift: {len(stale)} stale, {len(dangling)} dangling link(s) "
                     "(plumb drift, plumb review)")
    overlaps = _overlap_lines(core)
    lines += overlaps
    return {"lines": lines, "state": snapshot.state, "awaiting": awaiting,
            "stale": stale, "dangling": dangling, "elsewhere": overlaps}


def _overlap_lines(core: Any) -> list[str]:
    """sp6 9.4: what other worktrees and branches are changing (``/plumb status``)."""
    try:
        from plumb.awareness.lines import status_section

        return status_section(core)
    except Exception:  # noqa: BLE001 - awareness is advisory
        return []
