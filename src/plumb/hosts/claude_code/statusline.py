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
        if (candidate / ".plumb").is_dir():
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


def main(*, root: Path | str | None = None, stdin: TextIO | None = None,
         stdout: TextIO | None = None) -> int:
    if stdin is None or stdout is None:
        from plumb.hosts.claude_code.hookio import use_utf8_stdio

        use_utf8_stdio()
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    try:
        found = find_root(root, _read_stdin(stdin))
        data = None
        if found is not None:
            try:
                data = json.loads((found / ".plumb" / "session" / "status.json")
                                  .read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
        line = render(data)
    except Exception:  # noqa: BLE001 - the status line never fails
        data, line = None, NO_STATUS
    try:
        stdout.write(line + "\n")
    except (OSError, ValueError):  # UnicodeEncodeError included: the ASCII card
        try:
            stdout.write(render(data, ascii=True) + "\n")
        except Exception:  # noqa: BLE001
            stdout.write(NO_STATUS + "\n")
    return 0
