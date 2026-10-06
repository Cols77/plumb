"""``plumb mcp serve`` and ``plumb mcp install|uninstall claude-code|codex|hermes`` (sp4 6).

``serve`` runs the read-only server on stdio. ``install`` registers it with a host,
preserving every foreign entry, with the launcher of ``plumb hosts`` (sp4 6.4):

- Claude Code: ``mcpServers.plumb`` in the project's ``.mcp.json``;
- Codex: a marked ``[mcp_servers.plumb]`` table at the end of ``.codex/config.toml``;
- Hermes: a marked ``mcp_servers`` block in the user's ``config.yaml`` (``HERMES_HOME``),
  only when that file has no ``mcp_servers`` of its own; otherwise the entry is printed for
  the owner to add, and nothing is written.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path

HOSTS = ("claude-code", "codex", "hermes")
TOML_BEGIN = "# >>> plumb mcp (plumb mcp install codex) >>>"
TOML_END = "# <<< plumb mcp <<<"
YAML_BEGIN = "# >>> plumb mcp (plumb mcp install hermes) >>>"
YAML_END = "# <<< plumb mcp <<<"


def server_argv(root: Path, launcher: str = "auto") -> list[str]:
    from plumb.hosts.common import launcher_argv

    return [*launcher_argv(root, launcher), "mcp", "serve"]


def hermes_config() -> Path:
    home = os.environ.get("HERMES_HOME", "").strip()
    if home:
        return Path(home) / "config.yaml"
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "hermes" / "config.yaml"
    return Path.home() / ".hermes" / "config.yaml"


def _strip(text: str, begin: str, end: str) -> tuple[str, bool]:
    start = text.find(begin)
    stop = text.find(end, start + 1) if start >= 0 else -1
    if start < 0 or stop < 0:
        return text, False
    stop += len(end)
    if text[stop:stop + 1] == "\n":
        stop += 1
    return text[:start] + text[stop:], True


def _write(path: Path, text: str | None, changed: list[str], label: str, dry_run: bool) -> None:
    """Write (or, with None, remove) ``path`` when it changes, keeping CRLF files CRLF."""
    from plumb.hosts.common import read_text

    current = read_text(path)
    if current == text:
        return
    changed.append(label)
    if dry_run:
        return
    if text is None:
        path.unlink()
        return
    try:
        crlf = b"\r\n" in path.read_bytes()
    except OSError:
        crlf = False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\r\n" if crlf else "\n")


def _kept(foreign: str) -> str | None:
    """The foreign text once plumb's block and its separator are gone (None: nothing)."""
    return foreign.rstrip("\n") + "\n" if foreign.strip() else None


# --------------------------------------------------------------------------- per host


def _claude(root: Path, argv: list[str] | None, changed: list[str], lines: list[str],
            dry_run: bool) -> None:
    from plumb.hosts.common import json_text, read_json_object

    path = root / ".mcp.json"
    if argv is None and not path.exists():
        return
    data = read_json_object(path)
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(".mcp.json: mcpServers is not an object; fix it first")
    servers = dict(servers)
    if argv is None:
        servers.pop("plumb", None)
    else:
        servers["plumb"] = {"type": "stdio", "command": argv[0], "args": argv[1:]}
    if servers:
        data["mcpServers"] = servers
    else:
        data.pop("mcpServers", None)
    _write(path, json_text(data) if data else None, changed, ".mcp.json", dry_run)


def _codex(root: Path, argv: list[str] | None, changed: list[str], lines: list[str],
           dry_run: bool) -> None:
    from plumb.hosts.common import read_text

    path = root / ".codex" / "config.toml"
    current = read_text(path)
    if current is None and argv is None:
        return
    foreign, _found = _strip(current or "", TOML_BEGIN, TOML_END)
    if argv is None:
        _write(path, _kept(foreign), changed, ".codex/config.toml", dry_run)
        return
    parsed = tomllib.loads(foreign)
    if "plumb" in (parsed.get("mcp_servers") or {}):
        lines.append("kept: .codex/config.toml already has its own [mcp_servers.plumb]")
        return
    block = "\n".join([TOML_BEGIN, "[mcp_servers.plumb]",
                       f"command = {json.dumps(argv[0])}",
                       "args = [" + ", ".join(json.dumps(a) for a in argv[1:]) + "]",
                       TOML_END]) + "\n"
    text = foreign.rstrip("\n") + ("\n\n" if foreign.strip() else "") + block
    tomllib.loads(text)  # never write a configuration Codex cannot read
    _write(path, text, changed, ".codex/config.toml", dry_run)


def _hermes(root: Path, argv: list[str] | None, changed: list[str], lines: list[str],
            dry_run: bool) -> None:
    import yaml

    from plumb.hosts.common import read_text

    path = hermes_config()
    current = read_text(path)
    if current is None and argv is None:
        return
    foreign, _found = _strip(current or "", YAML_BEGIN, YAML_END)
    if argv is None:
        _write(path, _kept(foreign), changed, str(path), dry_run)
        return
    entry = {"mcp_servers": {"plumb": {"command": argv[0], "args": argv[1:],
                                        "cwd": str(Path(root).resolve())}}}
    snippet = yaml.safe_dump(entry, sort_keys=False, allow_unicode=True)
    parsed = yaml.safe_load(foreign) if foreign.strip() else {}
    if isinstance(parsed, dict) and "mcp_servers" in parsed:
        lines.append(f"not written: {path} has its own mcp_servers; add this entry under it:")
        lines.extend("  " + line for line in snippet.splitlines()[1:])
        return
    text = foreign.rstrip("\n") + ("\n\n" if foreign.strip() else "") \
        + f"{YAML_BEGIN}\n{snippet}{YAML_END}\n"
    yaml.safe_load(text)
    _write(path, text, changed, str(path), dry_run)


WRITERS = {"claude-code": _claude, "codex": _codex, "hermes": _hermes}


def install(root: Path, host: str, *, launcher: str = "auto", dry_run: bool = False,
            remove: bool = False) -> tuple[list[str], list[str]]:
    """``(changed paths, report lines)``."""
    changed: list[str] = []
    lines: list[str] = []
    argv = None if remove else server_argv(root, launcher)
    WRITERS[host](Path(root), argv, changed, lines, dry_run)
    return changed, lines


# --------------------------------------------------------------------------- CLI


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="plumb mcp", description=(
        "The read-only MCP server on stdio (serve), and its registration with a host "
        "(install, uninstall)."))
    parser.add_argument("action", choices=("serve", "install", "uninstall"))
    parser.add_argument("host", nargs="?", choices=HOSTS)
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--launcher", default="auto", choices=("auto", "path", "venv", "uv"))
    args = parser.parse_args(argv)
    from plumb.hosts.claude_code.hookio import find_hook_root

    root = find_hook_root({"cwd": os.getcwd()}, args.root)
    if root is None:
        print("plumb: no .plumb/ here; run plumb init first", file=sys.stderr)
        return 2
    if args.action == "serve":
        from plumb.mcp.server import serve

        return serve(root)
    if args.host is None:
        parser.error(f"{args.action} needs a host: claude-code, codex or hermes")
    import yaml

    from plumb.hosts.common import InstallError

    try:
        changed, lines = install(root, args.host, launcher=args.launcher,
                                 dry_run=args.dry_run, remove=args.action == "uninstall")
    except (ValueError, OSError, InstallError, yaml.YAMLError) as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    verb = "would change" if args.dry_run else "changed"
    print(f"plumb mcp {args.action} {args.host}: {verb} " + (", ".join(changed) or "nothing"))
    for line in lines:
        print(line)
    return 0
