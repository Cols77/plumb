"""``plumb hosts install|uninstall|status codex`` (sp4 4.1, SR-054).

Writes, idempotently and preserving every foreign entry:

- the ``AGENTS.md`` block (the CLI-only fallback, sp4 3.2);
- plumb's ``SessionStart``, ``UserPromptSubmit`` and ``Stop`` hooks in ``.codex/hooks.json``
  (Codex 0.160 hooks share Claude Code's wire), each ``plumb hook <event> --host codex
  --format claude``;
- a marked block at the top of ``.codex/config.toml`` with ``notify`` (the owner summary
  after each turn; skipped when the project or user configuration already sets one) and the
  session marker ``shell_environment_policy.set.PLUMB_AGENT_SESSION = "codex"`` (skipped,
  and reported by ``status``, when the configuration already has its own
  ``shell_environment_policy``).

The owner-terminal guard of ``approvals.require_owner`` holds whether or not the marker is
set; this adapter adds no owner-only path.
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from plumb.hosts.common import (
    IS_WINDOWS,
    MARKER_NAME,
    InstallError,
    InstallReport,
    context_file,
    has_block,
    instruction_block,
    is_plumb_command,
    json_text,
    launcher_argv,
    marker_lines,
    prompt_lines,
    read_json_object,
    read_text,
    remove_file,
    remove_shared_block,
    shell_command,
    upsert_block,
    write_file,
)

HOST = "codex"
EVENTS = (("SessionStart", "session-start"), ("UserPromptSubmit", "prompt"),
          ("Stop", "stop"))
TOML_BEGIN = "# >>> plumb (plumb hosts install codex) >>>"
TOML_END = "# <<< plumb <<<"
HOOK_TIMEOUT_S = 10


def _codex_argv(argv: Sequence[str]) -> list[str]:
    """The ``notify`` program, which Codex executes directly (no shell): a relative venv
    interpreter takes backslashes on Windows."""
    out = list(argv)
    if IS_WINDOWS and out and "/" in out[0]:
        out[0] = out[0].replace("/", "\\")
    return out


def hook_command(argv: Sequence[str], event: str) -> str:
    """A hook ``command`` of .codex/hooks.json: Codex runs it through the platform shell, so
    it is rendered by the one shell renderer (common.shell_command)."""
    return shell_command([*argv, "hook", event, "--host", HOST, "--format", "claude"])


def notify_argv(argv: Sequence[str]) -> list[str]:
    return [*_codex_argv(argv), "hook", "stop", "--host", HOST, "--format", "text",
            "--notify"]


def _paths(root: Path) -> tuple[Path, Path]:
    return root / ".codex" / "hooks.json", root / ".codex" / "config.toml"


def _user_config() -> dict[str, Any]:
    home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    try:
        return tomllib.loads((Path(home) / "config.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------- hooks.json


def _without_plumb(groups: Any) -> list[Any]:
    """The event's matcher groups with plumb's handlers removed (empty groups dropped)."""
    out: list[Any] = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            out.append(group)
            continue
        kept = [h for h in group["hooks"]
                if not (isinstance(h, dict) and is_plumb_command(h.get("command")))]
        if kept:
            out.append({**group, "hooks": kept})
        elif not group["hooks"]:
            out.append(group)
    return out


def _hooks_data(path: Path, argv: Sequence[str] | None) -> dict[str, Any]:
    data = read_json_object(path)
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError(f"{path}: 'hooks' is not an object; fix it first")
    hooks = dict(hooks)
    for event, name in EVENTS:
        groups = _without_plumb(hooks.get(event, []))
        if argv is not None:
            groups.append({"hooks": [{"type": "command", "command": hook_command(argv, name),
                                      "timeout": HOOK_TIMEOUT_S}]})
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if hooks:
        data["hooks"] = hooks
    else:
        data.pop("hooks", None)
    return data


def installed_events(root: Path) -> list[str]:
    hooks_path, _ = _paths(root)
    try:
        data = read_json_object(hooks_path)
    except InstallError:
        return []
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    out = []
    for event, _name in EVENTS:
        for group in hooks.get(event) or []:
            if isinstance(group, dict) and any(
                    isinstance(h, dict) and is_plumb_command(h.get("command"))
                    for h in group.get("hooks") or []):
                out.append(event)
                break
    return out


# --------------------------------------------------------------------------- config.toml


def _strip_toml_block(text: str) -> str:
    start = text.find(TOML_BEGIN)
    end = text.find(TOML_END, start + 1) if start >= 0 else -1
    if start < 0 or end < 0:
        return text
    end += len(TOML_END)
    if text[end:end + 1] == "\n":
        end += 1
    return text[:start] + text[end:]


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a TOML basic string


def _config_text(current: str, argv: Sequence[str]) -> tuple[str, list[str]]:
    """``config.toml`` with plumb's block at the top, and the report lines."""
    foreign = _strip_toml_block(current)
    try:
        parsed = tomllib.loads(foreign)
    except ValueError as exc:
        raise InstallError(f".codex/config.toml is not valid TOML; fix it first ({exc})") from exc
    lines: list[str] = []
    body: list[str] = []
    if "notify" in parsed or "notify" in _user_config():
        lines.append("notify kept: your configuration already sets one (the Stop hook "
                     "still gives the summary)")
    else:
        body.append("notify = [" + ", ".join(_toml_string(a) for a in notify_argv(argv))
                    + "]")
    if "shell_environment_policy" in parsed:
        lines.append(f"session marker not set: your shell_environment_policy is kept; add "
                     f"set.{MARKER_NAME} = \"codex\" to it to set it")
    else:
        body.append(f'shell_environment_policy.set.{MARKER_NAME} = "{HOST}"')
    if not body:
        return foreign, lines
    block = "\n".join([TOML_BEGIN, *body, TOML_END]) + "\n"
    text = block + ("\n" + foreign.lstrip("\n") if foreign.strip() else "")
    try:
        tomllib.loads(text)
    except ValueError as exc:  # never write a configuration Codex cannot read
        raise InstallError(f"plumb's block would make .codex/config.toml invalid ({exc})") from exc
    return text, lines


def config_state(root: Path) -> dict[str, bool]:
    _, config_path = _paths(root)
    text = read_text(config_path) or ""
    start = text.find(TOML_BEGIN)
    block = text[start:text.find(TOML_END, start + 1)] if start >= 0 else ""
    return {"notify": "notify =" in block, "marker": MARKER_NAME in block}


# --------------------------------------------------------------------------- commands


def install(root: Path, *, launcher: str = "auto", dry_run: bool = False) -> InstallReport:
    root = Path(root)
    report = InstallReport()
    argv = launcher_argv(root, launcher)
    hooks_path, config_path = _paths(root)
    hooks_data = _hooks_data(hooks_path, argv)
    config_text, lines = _config_text(read_text(config_path) or "", argv)
    upsert_block(root, context_file(root, HOST), instruction_block(argv, HOST, hooks=True),
                 report, dry_run)
    write_file(root, hooks_path, json_text(hooks_data), report, dry_run)
    if config_text.strip():
        write_file(root, config_path, config_text, report, dry_run)
    report.lines.extend(lines)
    report.lines.append("trust plumb's hooks once in Codex (it keeps a hash per hook) so "
                        "they run; until then the AGENTS.md fallback applies")
    return report


def uninstall(root: Path, *, dry_run: bool = False) -> InstallReport:
    root = Path(root)
    report = InstallReport()
    hooks_path, config_path = _paths(root)
    if hooks_path.exists():
        data = _hooks_data(hooks_path, None)
        if data:
            write_file(root, hooks_path, json_text(data), report, dry_run)
        else:
            remove_file(root, hooks_path, report, dry_run)
    current = read_text(config_path)
    if current is not None and TOML_BEGIN in current:
        rest = _strip_toml_block(current).lstrip("\n")
        if rest.strip():
            write_file(root, config_path, rest, report, dry_run)
        else:
            remove_file(root, config_path, report, dry_run)
    remove_shared_block(root, HOST, report, dry_run)
    return report


def status(root: Path) -> list[str]:
    root = Path(root)
    events = installed_events(root)
    state = config_state(root)
    lines = ["hooks: " + (", ".join(events) if events else "not installed")
             + " (.codex/hooks.json; Codex asks you to trust them once)",
             "notify: " + ("installed" if state["notify"] else "not installed"),
             "instruction block: " + ("present" if has_block(context_file(root, HOST))
                                      else "missing") + " (AGENTS.md, plumb turn start/end)"]
    lines += marker_lines(state["marker"], "through shell_environment_policy in "
                          ".codex/config.toml")
    lines += prompt_lines(root, "UserPromptSubmit" in events, "UserPromptSubmit")
    return lines
