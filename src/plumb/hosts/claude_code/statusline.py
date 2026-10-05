"""``plumb statusline``: one line from ``.plumb/session/status.json`` (spec 6.6).

Reads one JSON file and recomputes nothing. Standard library only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

NO_STATUS = "plumb | no status yet"


def render(data: Any) -> str:
    """The status line for a snapshot mapping, or the no-status line."""
    if not isinstance(data, dict):
        return NO_STATUS
    try:
        total = int(data["requirements_total"])
        confirmed = int(data["requirements_confirmed"])
        proposed = int(data.get("proposed", 0))
        stale = int(data.get("stale_links", 0))
        ask = int(data.get("ask", 0))
    except (KeyError, TypeError, ValueError):
        return NO_STATUS
    tests = data.get("tests")
    if tests == "ok":
        tests_text = "ok"
    elif tests == "failing":
        tests_text = f"failing {len(data.get('failing') or ())}"
    elif tests == "regression":
        tests_text = f"regression {len(data.get('regressions') or ())}"
    elif tests == "not-run":
        tests_text = "not run"
    else:
        tests_text = "?"
    parts = ["plumb", f"SR {confirmed}/{total} ok", f"proposed {proposed}", f"stale {stale}",
             f"tests {tests_text}"]
    if data.get("full_pending"):
        parts.append("full pending")
    parts.append(f"ask {ask}")
    return " | ".join(parts)


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
        line = NO_STATUS
    try:
        stdout.write(line + "\n")
    except (OSError, ValueError):  # UnicodeEncodeError included: fall back to plain ASCII
        stdout.write(NO_STATUS + "\n")
    return 0
