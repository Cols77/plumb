"""SR-378: the judge's questions never refuse a call. What stays of the ask gate (SR-361 EX-6)
is its bookkeeping for the pacing rule (SR-334): the question tool's call, or one the session's
transcript shows, marks the open questions asked (``judge.note_asked``). Only where the question
tool is there: never for a subagent's call (``agent_id``) or a session nobody attends
(``CLAUDE_CODE_SESSION_ATTENDED`` not ``1``: headless)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
TRANSCRIPT_TAIL = 4 << 20      # bytes of the transcript read back for the last question tool


def applies(data: dict[str, Any]) -> bool:
    """The question tool is there: the main agent of a session someone attends."""
    return not data.get("agent_id") and os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") == "1"


def _asked_in_transcript(data: dict[str, Any], store: Path) -> bool:
    """The question tool was called after the judge's last question arrived, as the session's
    transcript shows: a session started before the plugin update has no pre-tool hook on the
    question tool, so ``note_asked`` never ran there (hooks.json is read at session start)."""
    path = data.get("transcript_path")
    if not path:
        return False
    since = datetime.fromtimestamp(store.stat().st_mtime, UTC)
    with open(path, "rb") as f:
        f.seek(max(0, os.fstat(f.fileno()).st_size - TRANSCRIPT_TAIL))
        lines = f.read().splitlines()
    for line in reversed(lines):
        if b'"AskUserQuestion"' not in line or b'"tool_use"' not in line:
            continue
        try:
            at = str(json.loads(line).get("timestamp") or "")
            return datetime.fromisoformat(at.replace("Z", "+00:00")) > since
        except ValueError:
            continue
    return False


def decide(root: Path | str, session: str, tool: str, tool_input: dict[str, Any],
           data: dict[str, Any]) -> str:
    """Note the judge's questions asked when the question tool ran; always "" (allow). Never
    raises."""
    del tool_input
    if not session or not applies(data) or tool not in (*WRITE_TOOLS, "Bash", "AskUserQuestion"):
        return ""
    from plumb.understand import judge

    store = judge.questions_path(root, session)
    if not store.exists():
        return ""                      # the fast path: this session's judge never asked
    try:
        from plumb.api import open_core

        if tool == "AskUserQuestion" or _asked_in_transcript(data, store):
            judge.note_asked(open_core(Path(root)), session)
    except Exception:  # noqa: BLE001 - bookkeeping never blocks a call
        pass
    return ""
