"""PRESENT's provided interface (sp5 9, plan 3.5): read-only views in the owner's terms.

The CLI (``iaso brief``, ``show``, ``explain``, ``impact``, ``drift``, ``resolve``), the MCP
server (sp4 6.2) and the host adapters call these functions, so every surface shows the same
thing. None of them writes a record, a link, an approval or the log. Plain words are
accepted wherever something is named (R9); IDs and paths still work.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from iaso.contracts import Resolution

__all__ = ["brief", "drift", "explain", "impact", "relevant", "resolve", "show"]


def resolve(core: Any, words: str, *, kind: str | None = None) -> Resolution:
    """The owner's words as ranked records, paths and tests (sp5 5); ``.best`` is the one
    clear match, None when the words are ambiguous or match nothing."""
    from iaso.present.resolve import resolve as _resolve

    return _resolve(core, words, kind=kind)


def brief(core: Any, *, full: bool = False, max_lines: int | None = None) -> list[str]:
    """``iaso brief``: the short intent brief (``full``: every record), the tests line when
    verification is unavailable or a full run is pending, whether auto-approve is on and where
    that setting comes from once the owner switched it (SR-115), each while there is room."""
    from iaso.commands import auto_approve_line, verification_state
    from iaso.query import HARD_CAP, brief_lines

    cap = 10**6 if full else int(max_lines or core.config.hooks.brief_lines)
    lines = brief_lines(core, cap, show_all=full)
    verification = verification_state(core)
    if verification == "unavailable":
        tests: str | None = "tests: verification unavailable in this build"
    elif isinstance(verification, dict) and verification.get("full_pending"):
        tests = "tests: full verification pending (" + ", ".join(
            verification.get("full_pending_reasons") or []) + ")"
    else:
        tests = None
    for extra in (tests, auto_approve_line(core, quiet=True)):
        if extra and (full or len(lines) < min(cap, HARD_CAP)):
            at = len(lines) - 1 if lines and lines[-1].startswith("open NCs") else len(lines)
            lines.insert(at, extra)
    return lines


def relevant(core: Any, text: str, limit: int = 5) -> list[dict[str, Any]]:
    """The records relevant to ``text``, best first: ``{id, state, title}`` (the R9 delta
    shape, without the session's deduplication)."""
    index = core.index()
    ranked = [(i, score) for i, score in core.relevant(text, limit=limit) if i in index]
    statuses = core.status([i for i, _ in ranked]) if ranked else {}
    return [{"id": i, "state": statuses[i].confirmation if i in statuses else "?",
             "title": index[i].title} for i, _ in ranked]


def show(core: Any, ids: Sequence[str]) -> list[str]:
    """``iaso show``: each record in full (read-back, examples, tests, who confirmed it).
    Plain words are resolved first; an unknown ID is named on its own line."""
    from iaso.present.resolve import resolution_lines
    from iaso.readback import show_lines

    wanted = list(ids)
    index = core.index()
    if wanted and not all(i in index for i in wanted):
        resolution = resolve(core, " ".join(wanted))
        if resolution.how in ("words", "path", "test"):
            if resolution.ambiguous or not resolution.ids:
                return resolution_lines(resolution)
            wanted = list(resolution.ids)
    lines, missing = show_lines(core, wanted)
    return [*lines, *(f"iaso: no record {i}" for i in missing)]


def explain(core: Any, query: str) -> dict[str, Any]:
    """``iaso explain``: why a behaviour, a file or a record exists, in the owner's terms:
    ``{lines, ids, resolved}`` (``resolved``: how the words were read, the path and the
    candidates when they were ambiguous)."""
    from iaso.explain import explain_lines

    lines, data = explain_lines(core, query)
    return {"lines": lines, "ids": list(data.get("records") or []),
            "resolved": {k: v for k, v in data.items() if k != "records"}}


def impact(core: Any, ref: str) -> dict[str, Any]:
    """``iaso impact``: what a change would reach (records, code, covering tests with their
    evidence state). Plain words are resolved first; when they are ambiguous, nothing is
    guessed and the candidates are returned (``impacts`` empty)."""
    from iaso.present.resolve import as_dict

    resolution = resolve(core, ref)
    out: dict[str, Any] = {"ref": ref, "resolved": as_dict(resolution), "impacts": []}
    if resolution.ambiguous or resolution.how == "none":
        out["available"] = True
        return out
    refs = [i.ref for i in resolution.items][:3]
    try:
        from iaso.verify import open_verify
    except ImportError:
        out["available"] = False
        return out
    verify = open_verify(core)
    out["available"] = True
    out["impacts"] = [verify.impact(r) for r in refs]
    return out


def drift(core: Any) -> dict[str, Any]:
    """``iaso drift``: the drift signals, plus CAPTURE's hidden-dependency hints (R12.4) for
    the uncommitted paths, as hints only (``hints``; empty without CAPTURE)."""
    from iaso.commands import drift_data

    data = dict(drift_data(core))
    hints: list[str] = []
    try:
        from iaso.capture import api as capture
    except ImportError:
        capture = None
    if capture is not None and hasattr(capture, "drift_hints"):
        from iaso.hosts.claude_code.stop import git_changed

        try:
            hints = [str(h) for h in capture.drift_hints(core, git_changed(core.root))]
        except Exception:  # noqa: BLE001 - hints are advisory
            hints = []
    data["hints"] = hints
    return data
