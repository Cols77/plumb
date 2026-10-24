"""Which plumb build Claude Code runs, against main's (SR-358): the loaded plugin's vendored
source digest beside ``<root>/plugin/vendor/MANIFEST.json``. Nothing is reinstalled."""

from __future__ import annotations

import datetime
import json
from pathlib import Path


def _digest(manifest: Path) -> str:
    try:
        return str(json.loads(manifest.read_text(encoding="utf-8")).get("source_digest") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def outdated(root: Path | str) -> tuple[bool, str]:
    """``(True, "<main's build date>")`` when the plugin plumb runs from (``PLUMB_PLUGIN_ROOT``,
    set by the plugin's launcher) was built from another source than main's; ``(False, "")``
    otherwise, or when plumb does not run from a plugin or either manifest is missing."""
    from plumb.launcher import plugin_root

    loaded = plugin_root()
    main = Path(root) / "plugin" / "vendor" / "MANIFEST.json"
    ours = _digest(Path(loaded) / "vendor" / "MANIFEST.json") if loaded else ""
    theirs = _digest(main)
    if not ours or not theirs or ours == theirs:
        return False, ""
    # shortcut: the manifest's mtime stands for the build date; record it in MANIFEST.json if
    # a checkout's mtime ever misleads
    return True, datetime.date.fromtimestamp(main.stat().st_mtime).isoformat()
