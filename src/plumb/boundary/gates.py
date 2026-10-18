"""Exit-1 gates of the merge boundary (sp3 5, SR-049): claims, links of touched records and
log integrity. Each finding carries its fix."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def claims_gate(core: Any, fork: str) -> dict[str, Any]:
    """``plumb claims check --range FORK..HEAD``, plus whether it holds the merge.

    Lists an undeclared path, and a commit without an ``SR:`` trailer (touching a
    non-exempt path) while ``require_trailer: true``; holds only when the check failed."""
    from plumb.claims import claims_check, load_policy

    try:
        result = claims_check(core.root, f"{fork}..HEAD")
    except Exception as exc:  # an unreadable range is reported, never a crash
        return {"range": f"{fork}..HEAD", "undeclared": [], "unclaimed_commits": [],
                "problems": [f"claims check failed: {exc}"], "holds": True}
    policy = load_policy(core.root)
    unclaimed = list(result.get("unclaimed_commits") or []) if policy.require_trailer else []
    out = dict(result)
    out["unclaimed_commits"] = unclaimed
    # SR-260 EX-4 (DEC-252): undeclared paths and unclaimed commits are listed, never held;
    # only a claims check that could not read its policy holds (integrity, DEC-255)
    out["holds"] = bool(result.get("problems"))
    return out


def claims_lines(claims: dict[str, Any]) -> list[tuple[str, str]]:
    """(row, fix) per finding."""
    rows: list[tuple[str, str]] = []
    for item in claims.get("undeclared") or []:
        sr = (item.get("claims") or ["SR-###"])[0]
        rows.append((f"undeclared path {item['path']} in {str(item['commit'])[:12]} "
                     f"(claims {', '.join(item.get('claims') or [])})",
                     f"plumb link {sr} implemented_by {item['path']}, or an NC-backed "
                     "baseline entry in .plumb/claims.yaml"))
    for sha in claims.get("unclaimed_commits") or []:
        rows.append((f"no SR: trailer on {str(sha)[:12]} (require_trailer: true)",
                     "reword the commit with an 'SR: SR-###' trailer"))
    for problem in claims.get("problems") or []:
        rows.append((f"claims.yaml: {problem}", "fix .plumb/claims.yaml"))
    return rows


def link_rows(core: Any, touched: Sequence[str]) -> list[dict[str, Any]]:
    """Stale and dangling links of the touched requirements, with the fix."""
    rows: list[dict[str, Any]] = []
    if not touched:
        return rows
    for status in core.status(touched).values():
        for state in status.links:
            if state.state not in ("stale", "dangling"):
                continue
            link = state.link
            target = link.target.record or link.target.test or link.target.path or "?"
            if state.state == "stale":
                fix = f"review the change, then plumb repin {link.id}"
            else:
                fix = f"restore {target}, or relink {link.source} to where it went"
            rows.append({"link": link.id, "kind": link.kind, "target": target,
                         "state": state.state, "moved": state.moved, "fix": fix})
    return rows


def link_line(row: dict[str, Any]) -> str:
    moved = f" ({row['moved']} moved)" if row.get("moved") else ""
    return (f"  {row['state']} link {row['link']} {row['kind']} {row['target']}{moved}: "
            f"{row['fix']}")
