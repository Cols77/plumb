"""Record paths git left unmerged (sp6 8.5, 7.6, 10): the merge report's ``unmerged`` rows.

One ``git ls-files -u -- .iaso/`` call. A path with stages 1 and only one of 2 or 3 is a
modify/delete; stages 1, 2 and 3 left unmerged mean the driver fell back to a text merge (a
side that is not a record) or no driver is configured; stages 2 and 3 without 1 are an add/add
of one ID, reported by ``iaso.ids.collisions`` when this build has it.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from iaso.present import owner_text

RECORD_FILE = re.compile(r"^\.iaso/(?:intents|requirements|decisions|features|ncs)/[^/]+\.md$")


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def unmerged_stages(root: Path) -> dict[str, set[int]]:
    """``{record path: {stages}}`` of the record files git left unmerged."""
    out = _git(Path(root), "ls-files", "-u", "-z", "--", ".iaso/")
    stages: dict[str, set[int]] = {}
    for item in (out or "").split("\0"):
        if "\t" not in item:
            continue
        meta, path = item.split("\t", 1)
        parts = meta.split()
        if len(parts) == 3 and RECORD_FILE.match(path):
            stages.setdefault(path, set()).add(int(parts[2]))
    return stages


def _title(root: Path, path: str) -> tuple[str, str]:
    from iaso.mergedriver.merge import _guess_id

    try:
        text = (Path(root) / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    record, title = _guess_id(text)
    if record == "this record":
        record = Path(path).stem
    return record, title


def _ids_report_add_add() -> bool:
    try:
        from iaso import ids
    except ImportError:
        return False
    return callable(getattr(ids, "collisions", None))


def unmerged_rows(core: Any) -> list[dict[str, Any]]:
    """``[{path, record, title, how, line}]``; ``how`` is modify/delete, text, no-driver or
    add/add (the last only when ``iaso.ids`` does not report it)."""
    root = Path(core.root)
    stages = unmerged_stages(root)
    if not stages:
        return []
    from iaso.mergedriver.driver import labels_of
    from iaso.mergedriver.gitconfig import KEYS

    ours, theirs = labels_of(root, [])
    configured = bool((_git(root, "config", "--get", KEYS[1]) or "").strip())
    skip_add_add = _ids_report_add_add()
    rows: list[dict[str, Any]] = []
    for path, found in sorted(stages.items()):
        record, title = _title(root, path)
        row: dict[str, Any] = {"path": path, "record": record, "title": title}
        if 1 in found and len(found) == 2:
            changed, removed = (ours, theirs) if 2 in found else (theirs, ours)
            row["how"] = "modify/delete"
            row["line"] = owner_text.MODIFY_DELETE.format(record=record, title=title,
                                                          changed=changed, removed=removed)
        elif found == {2, 3}:
            if skip_add_add:
                continue
            row["how"] = "add/add"
            row["line"] = "  " + owner_text.ADD_ADD.format(record=record)
        else:
            row["how"] = "text" if configured else "no-driver"
            text = owner_text.UNPARSABLE if configured else owner_text.NO_DRIVER
            row["line"] = "  " + text.format(record=record, title=title)
        rows.append(row)
    return rows


def unmerged_lines(rows: list[Mapping[str, Any]]) -> list[str]:
    if not rows:
        return []
    return [owner_text.UNMERGED_HEADER, *(str(r["line"]) for r in rows)]
