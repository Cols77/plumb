"""The debug workflow (SR-220, SR-221, SR-300), standalone: ``plumb debug [ID ...] [--dry-run]``.

The cases plumb could not settle on its own (today: stale and dangling links) are rerun once
through the step the turn end runs, ``links.repin_after_tests`` (tests, then the meaning
cascade). What each case did and what it still needs is reported as text; a record whose
meaning changed under a decision becomes one owner question through the question tool (SR-300
EX-3), never a card. The plumb line counts the cases in debugging and the ones resolved.
Nothing here confirms anything or changes a record's meaning.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

LINE = "plumb: debug: {n} cases, {resolved} resolved, {open} still in debugging"
STORE = (".plumb", "cache", "debug")
DANGLING = "its target no longer exists, so there is nothing to repin to: relink it"


def _case_path(root: Path | str, case_id: str) -> Path:
    return Path(root).joinpath(*STORE, re.sub(r"[^\w.-]", "_", case_id) + ".json")


def open_case(root: Path | str, *, id: str, kind: str, target: str, detail: str,
              log: str = "") -> None:
    """SR-325: one case file per id, written the moment a failure happens (idempotent; a
    failure to write it is swallowed, since it runs inside the failing step)."""
    try:
        path = _case_path(root, id)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"id": id, "kind": kind, "target": target, "detail": detail, "state": "open",
               "log": log}
        path.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001 - recording a case never fails the step that failed
        pass


def all_cases(root: Path | str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(Path(root).joinpath(*STORE).glob("*.json")):
        try:
            row = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(row, dict) and row.get("id"):
            out.append(row)
    return out


def open_cases(root: Path | str) -> list[dict[str, Any]]:
    return [r for r in all_cases(root) if r.get("state") == "open"]


def _update(root: Path | str, ids: list[str], **fields: Any) -> int:
    changed = 0
    for case_id in ids:
        path = _case_path(root, case_id)
        try:
            row = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if any(row.get(k) != v for k, v in fields.items()):
            path.write_text(json.dumps({**row, **fields}, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            changed += 1
    return changed


def resolve(root: Path | str, ids: list[str]) -> int:
    """Mark cases resolved; returns how many changed."""
    return _update(root, ids, state="resolved")


def report(root: Path | str, id: str, text: str) -> None:
    _update(root, [id], report=text)


def hook_error(root: Path | None, name: str, detail: str) -> None:
    """SR-325 EX-1: a hook that raised leaves one case, the same error once."""
    if root is None:
        return
    lines = detail.strip().splitlines()
    open_case(root, id=f"hook-{name}-{hashlib.sha1(detail.encode()).hexdigest()[:8]}",
              kind="hook-error", target=name, detail=lines[-1] if lines else name, log=detail)


def cases(core: Any, selectors: list[str], *, dry_run: bool = False,
          session: str | None = None, **test_doubles: Any) -> list[dict[str, str]]:
    """One ``{case, state, what}`` per stale or dangling link of ``selectors`` (record IDs or
    link ids; none: every record with one). ``state`` is ``resolved``, ``would resolve`` (dry
    run) or ``open``; ``what`` says what happened or what is missing."""
    from plumb import stale
    from plumb.links import LinkError, repin_after_tests

    states = [s for s in core.link_states() if s.state in ("stale", "dangling")]
    records = selectors or sorted({s.link.source for s in states})
    where = session or stale.current_session(core.root)
    out: list[dict[str, str]] = []
    for record in records:
        wanted = record.split("#")[0]
        out += [{"case": s.link.id, "state": "open", "what": DANGLING} for s in states
                if s.state == "dangling" and s.link.source == wanted
                and (record == wanted or s.link.id == record)]
        try:
            step = repin_after_tests(core, record, session=where, dry_run=dry_run,
                                     **test_doubles)
        except LinkError as exc:
            out.append({"case": record, "state": "open", "what": str(exc)})
            continue
        out += [{"case": c["link"], "state": "resolved",
                 "what": f"repinned ({c.get('tier', 'tests pass')})"} for c in step.changes]
        out += [{"case": link, "state": "would resolve", "what": why} for link, why in step.would]
        out += [{"case": link, "state": "open", "what": why} for link, why in step.refused]
    return out


def _store_cases(root: Path | str, found: list[dict[str, str]],
                 dry_run: bool) -> list[dict[str, str]]:
    """The store's cases beside the links: a refused link whose rerun resolved it (or that is
    no longer stale) is marked resolved; the other kinds have no step to rerun yet."""
    out: list[dict[str, str]] = []
    for row in all_cases(root):
        link, state = str(row["target"]), row.get("state")
        if state == "open" and row.get("kind") == "stale-refused":
            mine = [c for c in found if c["case"] == link]
            if all(c["state"] == "resolved" for c in mine) and not dry_run:
                resolve(root, [row["id"]])
                state = "resolved"
            if mine:
                continue  # listed with the links
        out.append({"case": row["id"], "state": "open" if state == "open" else "resolved",
                    "what": str(row.get("detail") or row.get("kind"))})
    return out


def run(command: str, argv: list[str]) -> int:
    import argparse

    from plumb.api import open_core
    from plumb.cliutil import add_common, emit, resolve_root

    parser = argparse.ArgumentParser(
        prog=f"plumb {command}",
        description="Run the debug cases once (stale links through tests and the meaning "
                    "cascade) and say what each did and what it still needs. Never confirms.")
    add_common(parser)
    parser.add_argument("selector", nargs="*", help="record IDs or link ids; default: all")
    parser.add_argument("--dry-run", action="store_true",
                        help="ask the models only: no tests, no repin, no owner question")
    args = parser.parse_args(argv)
    core = open_core(resolve_root(args.root))
    if args.selector[:1] == ["done"]:
        print(f"plumb: debug: {resolve(core.root, args.selector[1:])} cases marked resolved")
        return 0
    found = cases(core, args.selector, dry_run=args.dry_run)
    if not args.selector:
        found += _store_cases(core.root, found, args.dry_run)
    resolved = sum(c["state"] != "open" for c in found)
    if args.as_json:
        emit({"cases": found, "resolved": resolved}, True)
    else:
        print(LINE.format(n=len(found), resolved=resolved, open=len(found) - resolved))
        for c in found:
            print(f"  {c['case']}: {c['state']}: {c['what']}")
    return 1 if resolved < len(found) else 0


if __name__ == "__main__":
    sys.exit(run("debug", sys.argv[1:]))
