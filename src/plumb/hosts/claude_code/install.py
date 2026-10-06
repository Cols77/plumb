"""``plumb hooks install|uninstall|status`` (alias ``plumb install claude-code``), spec 6.7.

Merges plumb's entries into ``.claude/settings.json`` idempotently, preserving every
non-plumb entry: the hooks whose modules exist in this build, the status line, the session
marker ``PLUMB_AGENT_SESSION`` and the ``permissions.deny`` rules of the self-approval guard
(spec 5.6). Writes the skill, the slash command and a marked ``CLAUDE.md`` block, and the
git ``commit-msg`` hook through BRIDGE's ``install_commit_msg_hook``.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IS_WINDOWS = os.name == "nt"
MARKER_NAME = "PLUMB_AGENT_SESSION"
MARKER_VALUE = "claude-code"
POST_EDIT_MATCHER = "Edit|Write|MultiEdit|NotebookEdit"
BLOCK_BEGIN = "<!-- plumb:begin -->"
BLOCK_END = "<!-- plumb:end -->"
COMMIT_MSG_MARK = "plumb trailers check-msg"

# (hook name, Claude Code event, matcher, async)
HOOKS: tuple[tuple[str, str, str | None, bool], ...] = (
    ("session-start", "SessionStart", None, False),
    ("prompt", "UserPromptSubmit", None, False),
    ("post-edit", "PostToolUse", POST_EDIT_MATCHER, True),
    ("stop", "Stop", None, False),
)
GUARDED = ("approve", "revoke", "tests waive", "triage --approve", "spec approve",
           "config auto-approve")
STANDARD_PREFIXES = ("plumb", "uv run plumb", "python -m plumb")
_PLUMB_COMMAND = re.compile(r"(?:^|[\s\"'/\\])plumb(?:\.exe)?[\"']?\s+(?:hook\s|statusline\b)")
_PLUMB_DENY = re.compile(r"plumb (?:approve|revoke|tests waive|triage --approve|spec approve"
                         r"|config auto-approve):\*\)$|PLUMB_AGENT_SESSION|"
                         r"^(?:Edit|Write|MultiEdit)\(\.plumb/log/\*\*\)$")


class InstallError(RuntimeError):
    """The installer refuses to touch a file it cannot read safely."""


@dataclass(frozen=True)
class Launcher:
    kind: str           # path | venv | uv
    hook_prefix: str    # what settings.json runs (hooks, status line)
    agent_prefix: str   # what the agent types in its shell (skill, slash command)


@dataclass
class InstallReport:
    lines: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- launcher


def _venv_python(root: Path) -> Path | None:
    candidates = ((".venv/Scripts/python.exe", ".venv/bin/python") if IS_WINDOWS
                  else (".venv/bin/python", ".venv/Scripts/python.exe"))
    for rel in candidates:
        if (root / rel).exists():
            return root / rel
    return None


def _inside(path: str, directory: Path) -> bool:
    try:
        Path(path).resolve().relative_to(directory.resolve())
    except (OSError, ValueError):
        return False
    return True


def choose_launcher(root: Path, requested: str = "auto", *,
                    which: Callable[[str], str | None] = shutil.which) -> Launcher:
    """``plumb`` when on PATH (and not only because this project's venv is active), else
    the project's venv interpreter, else ``uv run --no-sync plumb``."""
    root = Path(root)
    path_launcher = Launcher("path", "plumb", "plumb")
    uv_launcher = Launcher("uv", "uv run --no-sync plumb", "uv run --no-sync plumb")
    venv = _venv_python(root)

    def venv_launcher(python: Path) -> Launcher:
        rel = python.relative_to(root).as_posix()
        return Launcher("venv", f'"$CLAUDE_PROJECT_DIR/{rel}" -m plumb', f"{rel} -m plumb")

    if requested == "path":
        return path_launcher
    if requested == "uv":
        return uv_launcher
    if requested == "venv":
        if venv is None:
            default = ".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python"
            return venv_launcher(root / default)
        return venv_launcher(venv)
    if requested != "auto":
        raise InstallError(f"unknown launcher '{requested}' (path, venv, uv or auto)")
    found = which("plumb")
    if found and not _inside(found, root / ".venv"):
        return path_launcher
    if venv is not None:
        return venv_launcher(venv)
    return uv_launcher


# --------------------------------------------------------------------------- settings


def available_hooks() -> list[str]:
    """The hooks whose modules exist in this build."""
    out = []
    for name, *_ in HOOKS:
        module = "plumb.hosts.claude_code." + name.replace("-", "_")
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if found:
            out.append(name)
    return out


def is_plumb_command(command: Any) -> bool:
    return isinstance(command, str) and _PLUMB_COMMAND.search(command) is not None


def deny_rules(launcher: Launcher) -> list[str]:
    prefixes = list(STANDARD_PREFIXES)
    if launcher.agent_prefix not in prefixes:
        prefixes.append(launcher.agent_prefix)
    rules = [f"Bash({prefix} {command}:*)" for command in GUARDED for prefix in prefixes]
    rules.append(f"Bash(*{MARKER_NAME}*)")
    rules += [f"{tool}(.plumb/log/**)" for tool in ("Edit", "Write", "MultiEdit")]
    return rules


def is_plumb_deny(rule: Any) -> bool:
    return isinstance(rule, str) and _PLUMB_DENY.search(rule) is not None


def _strip_plumb_hooks(settings: dict[str, Any]) -> None:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                kept_groups.append(group)
                continue
            kept = [h for h in group["hooks"]
                    if not (isinstance(h, dict) and is_plumb_command(h.get("command")))]
            if kept:
                kept_groups.append({**group, "hooks": kept})
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]


def merge_settings(settings: dict[str, Any], launcher: Launcher, hooks: Sequence[str],
                   report: InstallReport | None = None) -> dict[str, Any]:
    """``settings`` with plumb's entries (re)written; every other entry kept."""
    out = copy.deepcopy(settings)
    _strip_plumb_hooks(out)
    wanted = set(hooks)
    for name, event, matcher, is_async in HOOKS:
        if name not in wanted:
            continue
        hook: dict[str, Any] = {"type": "command",
                                "command": f"{launcher.hook_prefix} hook {name}"}
        if is_async:
            hook["async"] = True
        group: dict[str, Any] = {"matcher": matcher} if matcher else {}
        group["hooks"] = [hook]
        out.setdefault("hooks", {}).setdefault(event, []).append(group)
    status_line = out.get("statusLine")
    if status_line is None or (isinstance(status_line, dict)
                               and is_plumb_command(status_line.get("command"))):
        out["statusLine"] = {"type": "command", "command": f"{launcher.hook_prefix} statusline"}
    elif report is not None:
        report.lines.append("plumb: status line kept: a non-plumb statusLine is already set "
                            f"(run `{launcher.agent_prefix} statusline` from it to show plumb)")
    env = out.setdefault("env", {})
    env[MARKER_NAME] = MARKER_VALUE
    permissions = out.setdefault("permissions", {})
    deny = [r for r in permissions.get("deny", []) if not is_plumb_deny(r)]
    for rule in deny_rules(launcher):
        if rule not in deny:
            deny.append(rule)
    permissions["deny"] = deny
    return out


def unmerge_settings(settings: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(settings)
    _strip_plumb_hooks(out)
    status_line = out.get("statusLine")
    if isinstance(status_line, dict) and is_plumb_command(status_line.get("command")):
        del out["statusLine"]
    env = out.get("env")
    if isinstance(env, dict):
        env.pop(MARKER_NAME, None)
        if not env:
            del out["env"]
    permissions = out.get("permissions")
    if isinstance(permissions, dict) and isinstance(permissions.get("deny"), list):
        permissions["deny"] = [r for r in permissions["deny"] if not is_plumb_deny(r)]
        if not permissions["deny"]:
            del permissions["deny"]
        if not permissions:
            del out["permissions"]
    return out


def _settings_path(root: Path) -> Path:
    return root / ".claude" / "settings.json"


def read_settings(root: Path) -> dict[str, Any]:
    path = _settings_path(root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError) as exc:
        raise InstallError(f"{path} is not valid JSON ({exc}); fix it, then run install "
                           "again. Nothing was written.") from exc
    if not isinstance(data, dict):
        raise InstallError(f"{path} is not a JSON object; nothing was written")
    return data


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- files


def template(name: str, launcher: Launcher) -> str:
    text = (Path(__file__).parent / "templates" / name).read_text(encoding="utf-8")
    return text.replace("{plumb}", launcher.agent_prefix)


def skill_names() -> list[str]:
    """Every skill shipped under ``templates/skills/<name>/SKILL.md`` (sp2 9.1: the
    ``plumb`` skill and ``plumb-clarify`` beside it)."""
    base = Path(__file__).parent / "templates" / "skills"
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir() if (d / "SKILL.md").is_file())


def _write(path: Path, content: str, report: InstallReport, root: Path, dry_run: bool) -> None:
    rel = path.relative_to(root).as_posix()
    try:
        current = path.read_text(encoding="utf-8")
    except OSError:
        current = None
    if current == content:
        report.lines.append(f"plumb: {rel} unchanged")
        return
    report.changed.append(rel)
    if dry_run:
        report.lines.append(f"plumb: would write {rel}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    report.lines.append(f"plumb: wrote {rel}")


_BLOCK_RE = re.compile(re.escape(BLOCK_BEGIN) + r".*?" + re.escape(BLOCK_END) + r"\n?",
                       re.DOTALL)


def with_block(text: str, block: str) -> str:
    block = block if block.endswith("\n") else block + "\n"
    if _BLOCK_RE.search(text):
        return _BLOCK_RE.sub(lambda _: block, text, count=1)
    if not text:
        return block
    return text + ("" if text.endswith("\n") else "\n") + "\n" + block


def without_block(text: str) -> str:
    stripped = _BLOCK_RE.sub("", text)
    if stripped != text:
        stripped = stripped.rstrip("\n") + "\n" if stripped.strip() else ""
    return stripped


def _commit_msg_hook(root: Path, interpreter: str, report: InstallReport,
                     dry_run: bool) -> None:
    try:
        from plumb.claims import install_commit_msg_hook
    except ImportError:
        report.lines.append("plumb: commit-msg hook skipped: the trailer check (plumb.claims) "
                            "is not available in this build")
        return
    if dry_run:
        report.lines.append("plumb: would install the git commit-msg hook")
        return
    try:
        path = install_commit_msg_hook(root, interpreter)
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        report.lines.append(f"plumb: commit-msg hook not installed: {exc}")
        return
    report.lines.append(f"plumb: commit-msg hook installed ({path})")


# --------------------------------------------------------------------------- commands


def install(root: Path, *, launcher: Launcher | str = "auto", dry_run: bool = False,
            hooks: Iterable[str] | None = None, interpreter: str | None = None,
            commit_hook: bool = True) -> InstallReport:
    root = Path(root)
    report = InstallReport()
    chosen = launcher if isinstance(launcher, Launcher) else choose_launcher(root, launcher)
    names = list(available_hooks() if hooks is None else hooks)
    settings = read_settings(root)
    merged = merge_settings(settings, chosen, names, report)
    settings_path = _settings_path(root)
    current = settings_path.read_text(encoding="utf-8") if settings_path.exists() else None
    new = _dump(merged)
    if current is not None and json.loads(current) == merged:
        new = current
    _write(settings_path, new, report, root, dry_run)
    report.lines.append(f"plumb: launcher {chosen.kind}: {chosen.hook_prefix}")
    report.lines.append("plumb: hooks " + (", ".join(names) if names else "none")
                        + f"; status line; {MARKER_NAME}; deny rules")
    claude = root / ".claude"
    for name in skill_names():
        _write(claude / "skills" / name / "SKILL.md",
               template(f"skills/{name}/SKILL.md", chosen), report, root, dry_run)
    _write(claude / "commands" / "plumb.md", template("plumb-command.md", chosen), report,
           root, dry_run)
    claude_md = root / "CLAUDE.md"
    try:
        text = claude_md.read_text(encoding="utf-8")
    except OSError:
        text = ""
    _write(claude_md, with_block(text, template("claude-md-block.md", chosen)), report, root,
           dry_run)
    if commit_hook:
        _commit_msg_hook(root, interpreter or sys.executable, report, dry_run)
    return report


def uninstall(root: Path, *, dry_run: bool = False) -> InstallReport:
    root = Path(root)
    report = InstallReport()
    settings_path = _settings_path(root)
    if settings_path.exists():
        cleaned = unmerge_settings(read_settings(root))
        current = read_settings(root)
        if cleaned != current:
            _write(settings_path, _dump(cleaned), report, root, dry_run)
    claude = root / ".claude"
    skills = [claude / "skills" / name / "SKILL.md" for name in skill_names()]
    for path in (*skills, claude / "commands" / "plumb.md"):
        if path.exists():
            report.changed.append(path.relative_to(root).as_posix())
            if not dry_run:
                path.unlink()
                if path.name == "SKILL.md":
                    try:
                        path.parent.rmdir()
                    except OSError:
                        pass
            report.lines.append(f"plumb: {'would remove' if dry_run else 'removed'} "
                                f"{path.relative_to(root).as_posix()}")
    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
        stripped = without_block(text)
        if stripped != text:
            if stripped:
                _write(claude_md, stripped, report, root, dry_run)
            else:
                report.changed.append("CLAUDE.md")
                if not dry_run:
                    claude_md.unlink()
                report.lines.append("plumb: removed CLAUDE.md (it held only plumb's block)")
    hook = _commit_msg_path(root)
    if hook is not None and hook.exists():
        try:
            body = hook.read_text(encoding="utf-8", errors="replace")
        except OSError:
            body = ""
        if COMMIT_MSG_MARK in body:
            report.changed.append("commit-msg")
            if not dry_run:
                hook.unlink()
            report.lines.append(f"plumb: {'would remove' if dry_run else 'removed'} the "
                                "commit-msg hook")
    if not report.changed:
        report.lines.append("plumb: nothing of plumb's is installed")
    return report


def _commit_msg_path(root: Path) -> Path | None:
    git = root / ".git"
    if git.is_dir():
        return git / "hooks" / "commit-msg"
    if git.is_file():
        try:
            import subprocess

            out = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=root,
                                 capture_output=True, text=True, check=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        hooks_dir = Path(out.stdout.strip())
        return (hooks_dir if hooks_dir.is_absolute() else root / hooks_dir) / "commit-msg"
    return None


def status(root: Path) -> list[str]:
    root = Path(root)
    lines: list[str] = []
    try:
        settings = read_settings(root)
    except InstallError as exc:
        return [f"plumb: {exc}"]
    hooks = settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}
    installed = []
    for name, event, *_ in HOOKS:
        commands = [h.get("command") for g in hooks.get(event, []) if isinstance(g, dict)
                    for h in g.get("hooks", []) if isinstance(h, dict)]
        if any(is_plumb_command(c) and f" hook {name}" in str(c) for c in commands):
            installed.append(name)
    missing = [name for name, *_ in HOOKS if name not in installed]
    lines.append("hooks: " + (", ".join(installed) or "none")
                 + (f" (not installed: {', '.join(missing)})" if missing else ""))
    status_line = settings.get("statusLine")
    plumb_line = isinstance(status_line, dict) and is_plumb_command(status_line.get("command"))
    lines.append("statusLine: " + ("plumb" if plumb_line else
                                   "not installed" if status_line is None else "non-plumb"))
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    lines.append(f"{MARKER_NAME}: " + (str(env[MARKER_NAME]) if MARKER_NAME in env
                                       else "not installed"))
    permissions = settings.get("permissions")
    deny = permissions.get("deny", []) if isinstance(permissions, dict) else []
    lines.append(f"deny rules: {sum(is_plumb_deny(r) for r in deny)} plumb rules")
    claude = root / ".claude"
    skill = claude / "skills" / "plumb" / "SKILL.md"
    lines.append("skill: " + (".claude/skills/plumb/SKILL.md" if skill.exists()
                              else "not installed"))
    others = [n for n in skill_names() if n != "plumb"
              and (claude / "skills" / n / "SKILL.md").exists()]
    if others:
        lines.append("other skills: " + ", ".join(others))
    command = claude / "commands" / "plumb.md"
    lines.append("slash command: " + ("/plumb" if command.exists() else "not installed"))
    try:
        has_block = BLOCK_BEGIN in (root / "CLAUDE.md").read_text(encoding="utf-8")
    except OSError:
        has_block = False
    lines.append("CLAUDE.md block: " + ("present" if has_block else "not installed"))
    hook = _commit_msg_path(root)
    if hook is None or not hook.exists():
        lines.append("commit-msg hook: not installed")
    else:
        body = hook.read_text(encoding="utf-8", errors="replace")
        lines.append("commit-msg hook: " + ("plumb" if COMMIT_MSG_MARK in body else "non-plumb"))
    return lines


def run_cli(command: str, argv: list[str]) -> int:
    import argparse

    from plumb.cliutil import add_common, emit, resolve_root

    if command == "install":
        parser = argparse.ArgumentParser(prog="plumb install",
                                         description="Install plumb into a host's settings.")
        parser.add_argument("host", choices=["claude-code"])
        action = "install"
    else:
        parser = argparse.ArgumentParser(prog="plumb hooks",
                                         description="Claude Code hooks, status line, skill "
                                         "and guard settings.")
        parser.add_argument("action", choices=["install", "uninstall", "status"])
        action = None
    add_common(parser)
    parser.add_argument("--launcher", default="auto", choices=["auto", "path", "venv", "uv"],
                        help="how hooks start plumb (default: auto)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    action = action or args.action
    root = resolve_root(args.root)
    try:
        if action == "status":
            emit({"status": status(root)} if args.as_json else status(root), args.as_json)
            return 0
        if action == "uninstall":
            report = uninstall(root, dry_run=args.dry_run)
        else:
            report = install(root, launcher=args.launcher, dry_run=args.dry_run)
    except InstallError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    emit({"lines": report.lines, "changed": report.changed} if args.as_json else report.lines,
         args.as_json)
    return 0
