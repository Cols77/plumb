"""The hooks' awareness steps, each bounded by the hook's deadline (sp6 9.2, 9.4, 9.5; R17).

- session start: refresh this worktree's ``changing.json`` when HEAD moved, then the brief's
  lines (the branch scan runs here, within its cap);
- stop: publish this turn's paths; keep this branch's claim in ``refs/plumb/claims`` in step
  with the records it changed (whatever wrote them: capture, ``plumb new``, an edit) and
  carry the owner's answers to raised conflicts to the other branches; then the overlap lines
  of the records the turn touched. The git writes run only when something changed and the
  budget leaves room; a skipped step goes to the error log ("awareness skipped (budget)").

Every step is advisory: an error is logged and the hook goes on.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.awareness import inflight
from plumb.awareness.scan import skipped

MIN_GIT_S = 0.4      # the budget a git write needs before the stop hook starts it
CLAIMED_KINDS = ("requirement", "intent", "feature")


def _remaining(deadline: Any) -> float:
    try:
        return float(deadline.remaining_s()) if deadline is not None else 10.0
    except Exception:  # noqa: BLE001
        return 10.0


def _log(core: Any, where: str, exc: Exception) -> None:
    try:
        from plumb.hosts.claude_code.hookio import log_error

        log_error(Path(core.root), "awareness", f"{where}: {exc!r}")
    except Exception:  # noqa: BLE001
        pass


def at_session_start(core: Any, deadline: Any = None) -> list[Any]:
    from plumb.awareness.lines import brief_entries
    from plumb.awareness.publish import publish

    try:
        publish(core, [])            # git only when HEAD moved since the file was written
    except Exception as exc:  # noqa: BLE001
        _log(core, "publish", exc)
    try:  # learn which claims' branches were merged (cached), so the brief drops them
        inflight.others(core, allow_git=True, deadline=deadline)
    except Exception as exc:  # noqa: BLE001
        _log(core, "claims", exc)
    try:
        return brief_entries(core, deadline)
    except Exception as exc:  # noqa: BLE001
        _log(core, "brief", exc)
        return []


def claim_changes(core: Any, data: Mapping[str, Any] | None) -> bool:
    """Record (or refresh) this branch's claim for the records it changed that no claim of
    this branch holds at their current version. Reads git's files first; writes only when
    something is missing. Returns whether it wrote."""
    if not data or not data.get("branch"):
        return False
    index = core.index()
    changed = {i: item for i, item in (data.get("records") or {}).items()
               if isinstance(item, Mapping) and item.get("how") in ("edited", "new")
               and i in index and index[i].kind in CLAIMED_KINDS}
    if not changed:
        return False
    _oid, register = inflight.read(Path(core.root))
    held: dict[str, str] = {}
    for claim in register.get("claims") or []:
        if claim.get("branch") == data["branch"]:
            for record_id, entry in (claim.get("records") or {}).items():
                if isinstance(entry, Mapping):
                    held[record_id] = str(entry.get("hash") or "")
    missing = {i: inflight.record_entry(index[i]) for i in changed
               if held.get(i) != index[i].hash}
    if not missing:
        return False
    titles = ", ".join(index[i].title for i in sorted(missing))
    inflight.record_claim(core, records=missing, summary=titles, intent=None)
    return True


def at_stop(core: Any, changed: Sequence[str], touched: Iterable[str],
            deadline: Any = None) -> list[Any]:
    """Publish, keep the claim in step, and the overlap lines of ``touched``."""
    from plumb.awareness.lines import delta_lines
    from plumb.awareness.publish import publish

    data = None
    try:
        data = publish(core, changed)
    except Exception as exc:  # noqa: BLE001
        _log(core, "publish", exc)
    if _remaining(deadline) >= MIN_GIT_S:
        try:
            claim_changes(core, data)
            if _remaining(deadline) >= MIN_GIT_S:
                inflight.sync_decisions(core)
        except inflight.InflightBusy as exc:
            _log(core, "claims", exc)
        except Exception as exc:  # noqa: BLE001
            _log(core, "claims", exc)
    else:
        skipped(Path(core.root), "intent in flight")
    try:
        return delta_lines(core, list(touched))
    except Exception as exc:  # noqa: BLE001
        _log(core, "delta", exc)
        return []
