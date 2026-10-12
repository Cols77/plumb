"""``plumb statusline``: the status card from ``.plumb/session/status.json`` (spec 6.6,
sp5 4.1).

Reads one JSON file and recomputes nothing. Standard library only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

from plumb.paths import holds_records

NO_STATUS = "plumb | no status yet"


def render(data: Any, *, ascii: bool | None = None) -> str:
    """The status card (sp5 4.1, ``plumb.present.render.status_card``) for a snapshot
    mapping, or the no-status line. ``present.ascii`` in the snapshot asks for ASCII."""
    if not isinstance(data, dict):
        return NO_STATUS
    try:
        int(data["requirements_total"])
        int(data["requirements_confirmed"])
    except (KeyError, TypeError, ValueError):
        return NO_STATUS
    from plumb.present.render import status_card

    if ascii is None:
        prefs = data.get("present") if isinstance(data.get("present"), dict) else {}
        ascii = bool(prefs.get("ascii"))
    return status_card(data, ascii=ascii)


def _plumb_root(start: str | None) -> Path | None:
    if not start:
        return None
    try:
        path = Path(start).resolve()
    except OSError:
        return None
    for candidate in (path, *path.parents):
        if holds_records(candidate):            # never plumb's own home (~/.plumb)
            return candidate
    return None


def _read_stdin(stdin: TextIO) -> dict[str, Any]:
    try:
        if stdin.isatty():
            return {}
        raw = stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError, AttributeError):
        return {}
    return data if isinstance(data, dict) else {}


def find_root(root: Path | str | None, data: dict[str, Any]) -> Path | None:
    if root:
        return _plumb_root(str(root))
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    for candidate in (os.environ.get("CLAUDE_PROJECT_DIR"), workspace.get("project_dir"),
                      workspace.get("current_dir"), data.get("cwd"), os.getcwd()):
        found = _plumb_root(candidate if isinstance(candidate, str) else None)
        if found is not None:
            return found
    return None


def _progress_parts(root: Path, session: str | None, data: Any) -> tuple[str, str, str]:
    """``(shell, session, flag)``: what an execution started from a shell is doing (it replaces
    the card while it runs), what the session's worker is doing (it follows the card), and the
    note that checks keep failing. Each is empty when there is nothing to say; a missing or
    unreadable file adds nothing."""
    from plumb.progress import FAILURES_FLAG, shown

    try:
        shell = shown(root, None)
        worker = shown(root, session) if session else ""
        flag = ""
        if session and (root / ".plumb" / "session" / session / "failures.json").exists():
            from plumb.progress import failure_flag

            flag = failure_flag(root, session)
        elif isinstance(data, dict) and int(data.get("understand_failures") or 0) >= 3:
            flag = FAILURES_FLAG.format(n=int(data["understand_failures"]))
        return shell, worker, flag
    except Exception:  # noqa: BLE001 - the status line never fails
        return "", "", ""


def compose(data: Any, parts: tuple[str, str, str], *, ascii: bool | None = None) -> str:
    shell, worker, flag = parts
    card = render(data, ascii=ascii)
    if ascii is None:
        prefs = data.get("present") if isinstance(data, dict) and isinstance(
            data.get("present"), dict) else {}
        ascii = bool(prefs.get("ascii"))
    if ascii:
        from plumb.present.render import to_ascii

        shell, worker, flag = (to_ascii(t) for t in (shell, worker, flag))
    if shell:
        card = f"plumb | {shell}" if ascii else f"plumb ⏳ {shell}"
    extras = [e for e in (worker, flag) if e]
    return " | ".join([card, *extras])


def main(*, root: Path | str | None = None, stdin: TextIO | None = None,
         stdout: TextIO | None = None) -> int:
    if stdin is None or stdout is None:
        from plumb.hosts.claude_code.hookio import use_utf8_stdio

        use_utf8_stdio()
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    session = None
    parts = ("", "", "")
    try:
        stdin_data = _read_stdin(stdin)
        if isinstance(stdin_data.get("session_id"), str):
            session = stdin_data["session_id"]
        found = find_root(root, stdin_data)
        data = None
        if found is not None:
            try:
                data = json.loads((found / ".plumb" / "session" / "status.json")
                                  .read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            parts = _progress_parts(found, session, data)
        line = compose(data, parts)
    except Exception:  # noqa: BLE001 - the status line never fails
        data, line = None, NO_STATUS
    try:
        stdout.write(line + "\n")
    except (OSError, ValueError):  # UnicodeEncodeError included: the ASCII card
        try:
            stdout.write(compose(data, parts, ascii=True) + "\n")
        except Exception:  # noqa: BLE001
            stdout.write(NO_STATUS + "\n")
    return 0
