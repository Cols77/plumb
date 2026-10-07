"""The hooks' awareness steps, each bounded by the hook's deadline (sp6 9.2, 9.4, 9.5; R17).

- session start: refresh this worktree's ``changing.json`` when HEAD (or the default
  branch's tip) moved; learn which claimed branches and which other worktrees' branches
  merged (git, cached); then the brief's lines (the branch scan runs here, within its cap);
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
    try:  # learn which other worktrees' branches were merged (cached), likewise
        from plumb.awareness.scan import learn_landed

        learn_landed(core, deadline=deadline)
    except Exception as exc:  # noqa: BLE001
        _log(core, "merged worktrees", exc)
    try:
        return brief_entries(core, deadline)
    except Exception as exc:  # noqa: BLE001
        _log(core, "brief", exc)
        return []


def claim_changes(core: Any, data: Mapping[str, Any] | None, *,
                  asked: list[str] | None = None, backend: Any = None) -> bool:
    """Record (or refresh) this branch's claim for the records it changed that no claim of
    this branch holds at their current version, and move this branch's claims to its tip
    when it committed since. Reads git's files first; writes only when something is missing
    or moved. The claim goes through ``early.claim``, the same check capture runs: another
    branch claiming one of these records at another version raises the early decision once
    and asks for its card (its "ask the owner now" lines are appended to ``asked``).
    Returns whether it wrote."""
    if not data or not data.get("branch"):
        return False
    index = core.index()
    changed = {i: item for i, item in (data.get("records") or {}).items()
               if isinstance(item, Mapping) and item.get("how") in ("edited", "new")
               and i in index and index[i].kind in CLAIMED_KINDS}
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
        # the branch committed since its claims were written: move them to its tip, so they
        # clear once that commit merges (R17), and not before (one write per commit)
        from plumb.awareness.publish import default_branch

        if inflight.moved_claims(register, str(data["branch"]), data.get("head"),
                                 default_branch(core)):
            return inflight.refresh(core, changing=data)
        return False
    titles = ", ".join(index[i].title for i in sorted(missing))
    from plumb.awareness.early import claim

    new = _created(core, register, data, {i: changed[i] for i in missing})
    done = claim(core, sorted(missing), summary=titles, intent=None, new=new,
                 backend=backend if backend is not None else _hook_backend(core) if new
                 else None)
    if asked is not None:
        asked.extend(done.ask)
    return True


def _created(core: Any, register: Mapping[str, Any], data: Mapping[str, Any],
             changed: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """The records this branch created (``plumb new``, a new file), so the claim judges them
    against the intent other branches have in flight in their feature: committed as added
    (``how: new``), or a file git does not track yet. A record another branch claims is an
    existing record (matched by ID, never judged). At most one git call, and only when a
    record of a feature another branch claims is not known to be new."""
    claimed = {i for c in register.get("claims") or [] if c.get("branch") != data.get("branch")
               for i in (c.get("records") or {})}
    features = {f for c in register.get("claims") or [] if c.get("branch") != data.get("branch")
                for f in c.get("features") or []}
    index = core.index()
    new = [i for i, item in changed.items() if item.get("how") == "new" and i not in claimed]
    unsure = [i for i, item in changed.items()
              if item.get("how") != "new" and i not in claimed
              and str(index[i].fields.get("feature") or "") in features]
    if unsure:
        import subprocess

        paths = [index[i].path for i in unsure]
        try:
            out = subprocess.run(["git", "ls-files", "-z", "--", *paths], cwd=core.root,
                                 capture_output=True, timeout=5).stdout.decode("utf-8",
                                                                                "replace")
        except (OSError, subprocess.SubprocessError):
            out = None
        if out is not None:
            tracked = {p for p in out.split(chr(0)) if p}
            new += [i for i in unsure if index[i].path not in tracked]
    return sorted(new)


def _hook_backend(core: Any) -> Any:
    """The judgment backend in its hook mode (a new record in a feature another branch
    claims is judged; the same record changed elsewhere never needs it)."""
    try:
        from plumb.judgment import get_backend

        return get_backend(core, hook=True)
    except Exception:  # noqa: BLE001 - no backend: overlaps stay warnings
        return None


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
    asked: list[str] = []
    if _remaining(deadline) >= MIN_GIT_S:
        try:
            claim_changes(core, data, asked=asked)
            if _remaining(deadline) >= MIN_GIT_S:
                inflight.sync_decisions(core)
        except inflight.InflightBusy as exc:
            _log(core, "claims", exc)
        except Exception as exc:  # noqa: BLE001
            _log(core, "claims", exc)
    else:
        skipped(Path(core.root), "intent in flight")
    from plumb.present.delta import Line

    # R17: a conflict this claim raised is asked at once: the agent must show the card
    # (the stop hook shows it to the owner) and ask before any further work
    ask = [Line(line, subject=f"early-ask:{n}", state=line, must=True)
           for n, line in enumerate(asked)]
    try:
        return [*ask, *delta_lines(core, list(touched))]
    except Exception as exc:  # noqa: BLE001
        _log(core, "delta", exc)
        return ask
