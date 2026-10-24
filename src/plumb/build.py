"""Which plumb build Claude Code runs (SR-357, SR-358): the loaded plugin's vendored wheel
against the one main's checkout holds, compared by the source digest in their MANIFEST.json."""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path


def _manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def outdated(root: Path | str) -> tuple[bool, str]:
    """``(True, <built date of main's wheel>)`` when the running plugin's build differs from
    main's; ``(False, "")`` when they match, either is unknown, or no plugin runs this."""
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin:
        return False, ""
    running = _manifest(Path(plugin) / "vendor" / "MANIFEST.json").get("source_digest")
    path = Path(root) / "plugin" / "vendor" / "MANIFEST.json"
    main = _manifest(path)
    if not running or not main.get("source_digest") or running == main["source_digest"]:
        return False, ""
    try:
        built = (path.parent / str(main.get("wheel", ""))).stat().st_mtime
    except OSError:
        built = path.stat().st_mtime
    return True, datetime.date.fromtimestamp(built).isoformat()
