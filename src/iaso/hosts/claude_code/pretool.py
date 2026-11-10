"""PreToolUse on Bash, the edit tools and the question tool (and Read, Grep, Glob, Agent and Task
for a waiting message): the guard, then the gate.

The guard (SP7 4.3, ``iaso.guard.denied``) refuses what only the owner does: the owner-only
commands in every launcher spelling, the iaso panel's own steps, anything naming the session
marker, and edits under ``.iaso/log/``. The plugin cannot add permission rules, so this hook is
where its guard lives; the legacy per-repository install keeps its deny rules (generated from
the same table) and registers ``gate.sh`` for the edit tools.

The gate (SHOW S4, SR-103): while the gate of the session is closed an edit is refused.

``templates/gate.sh`` is the fast route the installer registers (shell only, no Python, within
the hook's 50 ms); this module is the Python route of the same decision, for tests and for
launchers that cannot run the script (``iaso hook pre-tool``). The gate covers the edit tools
only: edits made through the shell are out of scope, and the reason says so. Standard library
and ``iaso.understand.files`` only."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, TextIO

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
REASON = ("iaso: edits are on hold until the owner has answered: {reason}. Run iaso clarify "
          "--wait, show the owner what it returns, and do not build until they have answered. "
          "This guard covers the edit tools only; edits made through the shell are not "
          "checked.")
FALLBACK_REASON = "your request is still being checked"


def _deny(reason: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


REASON_WORDS = re.compile(r"\b(because|since|reason|why|so that|so it|so the)\b"
                          r"|\brecommended\s*:\s*\S", re.I)   # the judge's "Recommended: <reason>"


def incomplete_question(tool_input: dict[str, Any]) -> str:
    """SR-267 EX-5 (DEC-437): what a question-tool call lacks, or "" when it is complete. Each
    option needs a description (its consequence); the "(Recommended)" one also needs its reason."""
    missing: list[str] = []
    for q in tool_input.get("questions") or []:
        for o in (q.get("options") or []) if isinstance(q, dict) else []:
            if not isinstance(o, dict):
                continue
            label, desc = str(o.get("label") or ""), str(o.get("description") or "").strip()
            if not desc:
                missing.append(f'the option "{label}" has no description of what it does')
            elif "(recommended)" in label.lower() and not REASON_WORDS.search(desc):
                missing.append(f'the recommended option "{label}" gives no reason for being '
                               "recommended")
    if not missing:
        return ""
    return ("iaso: this question is incomplete: " + "; ".join(missing) + ". Ask it again with "
            "each option's consequence in its description and the reason for the recommended "
            "one.")


def decide(root: Path | str, session: str, tool: str,
           tool_input: dict[str, Any] | None = None,
           data: dict[str, Any] | None = None) -> dict[str, Any]:
    """The hook answer for ``tool`` in ``session``: a ``deny`` when the guard refuses the call
    or, for an edit tool, while the gate is closed; else an empty mapping (allow). The judge's
    open questions never refuse a call (SR-378): ``data``, the hook's input, only notes them
    asked when the question tool ran."""
    if tool_input is not None:
        from iaso.guard import denied

        reason = denied(tool, tool_input)
        if reason:
            return _deny(reason)
    if tool_input is not None and (tool == "Bash" or tool in EDIT_TOOLS):
        from iaso import main_guard

        reason = main_guard.refusal(root, tool, tool_input, data)  # SR-384
        if reason:
            return _deny(reason)
    if tool == "AskUserQuestion" and tool_input:
        reason = incomplete_question(tool_input)
        if reason:
            return _deny(reason)
    if session and not (data or {}).get("agent_id"):   # SR-395: the main agent only
        from iaso.understand import loops

        got = loops.take_inbox(Path(root), session)
        if got:
            return _deny(loops.message_label(got) + " This step was held once so you read it "
                         "first; run it again if it still stands.")
    if data is not None:
        from iaso.hosts.claude_code import ask_gate

        ask_gate.decide(root, session, tool, tool_input or {}, data)
    if tool not in EDIT_TOOLS or not session:
        return {}
    path = str((tool_input or {}).get("file_path") or "").replace("\\", "/")
    if ".." not in path and re.search(r"\.iaso/session/[^/]+/diagrams/", path):
        return {}  # a card's diagram is drawn while the card is open (SR-146), as gate.sh lets it
    from iaso.understand import files

    state = files.gate_from_json(files.read_json(files.gate_path(Path(root), session)))
    if state.state != "closed":
        return {}
    reason = state.reason if state.reason and "\\" not in state.reason else FALLBACK_REASON
    return _deny(REASON.format(reason=reason))


def main(*, root: Path | str | None = None, watchdog: bool = True, start: float | None = None,
         stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    """Read the host's JSON, answer on stdout, always exit 0 (a failing guard never blocks)."""
    del watchdog, start
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    try:
        data = json.loads(stdin.read() or "{}")
        if not isinstance(data, dict):
            return 0
        if root:
            base = Path(root)
        else:  # the .iaso/ found by walking up, as gate.sh and the other hooks read it (SR-121)
            from iaso.hosts.claude_code.hookio import find_hook_root

            base = find_hook_root(data) or Path(".")
        tool_input = data.get("tool_input")
        answer = decide(base, str(data.get("session_id") or ""), str(data.get("tool_name") or ""),
                        tool_input if isinstance(tool_input, dict) else {}, data)
        if answer:
            stdout.write(json.dumps(answer, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - the guard never blocks on its own failure
        return 0
    return 0
