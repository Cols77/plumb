"""Shared install helpers of the Codex, Pi and Hermes adapters (sp4 4, 3.2).

Every adapter is thin: it writes a few files from templates, idempotently, preserving every
foreign entry, and leaves the CLI-only fallback (an instruction block plus ``plumb turn
start`` and ``plumb turn end``) on every host. No adapter imports another adapter; they share
only this module and ``plumb.hosts.neutral``.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.confirm import SELF_RECORDED

IS_WINDOWS = os.name == "nt"
MARKER_NAME = "PLUMB_AGENT_SESSION"
BLOCK_BEGIN = "<!-- plumb:begin -->"
BLOCK_END = "<!-- plumb:end -->"
HOSTS = ("codex", "pi", "hermes")

# sp4 3.2: said by `plumb hosts status` on a host whose adapter cannot set the marker
NO_MARKER_LINE = ("CLI fallback (runtime marker unverified): owner-only commands require "
                  "an interactive terminal; marker status is not verified")
TRUST_LINE = ("trust model: plumb's log is hash-chained and tamper-evident, not tamper-proof "
              "against a malicious agent; relayed approvals are listed at the merge boundary "
              "for your glance")
# R13 Q4: a chat "ok" confirms on a host without a prompt hook, labelled everywhere
FALLBACK_PROMPT_LINE = ("prompts: CLI fallback (runtime marker unverified; the agent runs plumb "
                        "turn start): a chat "
                        "\"ok\" still confirms, and every such confirmation is labelled "
                        f"\"{SELF_RECORDED}\"")


class InstallError(RuntimeError):
    """The installer refuses to touch a file it cannot read safely."""


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


def launcher_argv(root: Path, requested: str = "auto", *,
                  which: Callable[[str], str | None] = shutil.which) -> list[str]:
    """How the host runs plumb from the repository root: ``plumb`` when on PATH (and not
    only because this project's venv is active), else the project's venv interpreter
    (relative to the root, where every host starts its hooks), else ``uv run --no-sync
    plumb``."""
    root = Path(root)
    venv = _venv_python(root)
    if requested == "path":
        return ["plumb"]
    if requested == "uv":
        return ["uv", "run", "--no-sync", "plumb"]
    if requested == "venv":
        rel = (venv.relative_to(root).as_posix() if venv is not None else
               (".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python"))
        return [rel, "-m", "plumb"]
    if requested != "auto":
        raise InstallError(f"unknown launcher '{requested}' (path, venv, uv or auto)")
    found = which("plumb")
    if found and not _inside(found, root / ".venv"):
        return ["plumb"]
    if venv is not None:
        return [venv.relative_to(root).as_posix(), "-m", "plumb"]
    return ["uv", "run", "--no-sync", "plumb"]


def command_line(argv: Sequence[str]) -> str:
    """One command line for an agent to type (POSIX quoting; Windows paths use forward
    slashes, which bash and PowerShell both run)."""
    return " ".join(shlex.quote(part) for part in argv)


def shell_command(argv: Sequence[str], *, windows: bool = IS_WINDOWS) -> str:
    """The command line a host runs through the platform shell (a hook ``command``).

    The one renderer of every command plumb writes into a host's configuration for its shell
    to run: on POSIX, ``sh`` quoting; on Windows the line must run in both cmd and PowerShell
    (Codex uses either), so the program path takes backslashes and no token is quoted. A
    POSIX single quote, or a quoted program path, runs in neither; a token that would need
    quoting is refused (choose ``--launcher path`` or ``uv``)."""
    if not windows:
        return " ".join(shlex.quote(part) for part in argv)
    parts = list(argv)
    if parts:
        parts[0] = parts[0].replace("/", "\\")
    unsafe = set(" \t\"'&|<>^%()`$;,@{}")
    for part in parts:
        if not part or unsafe.intersection(part):
            raise InstallError(f"cannot write a hook command that cmd and PowerShell both run "
                               f"for the argument {part!r}; choose another launcher "
                               "(--launcher path or uv)")
    return " ".join(parts)


def is_plumb_command(command: Any) -> bool:
    """A command string this installer wrote (``... plumb hook <event> --host ...``)."""
    return isinstance(command, str) and " hook " in f" {command} " and "plumb" in command \
        and "--host" in command


# --------------------------------------------------------------------------- files


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise InstallError(f"cannot read {path}: {exc}") from exc


def write_file(root: Path, path: Path, content: str, report: InstallReport,
               dry_run: bool) -> None:
    """Write ``content`` when it differs, keeping the file's own line endings (CRLF stays
    CRLF; new files get LF)."""
    if read_text(path) == content:
        return
    report.changed.append(rel(root, path))
    if dry_run:
        return
    try:
        crlf = b"\r\n" in path.read_bytes()
    except OSError:
        crlf = False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\r\n" if crlf else "\n")


def remove_file(root: Path, path: Path, report: InstallReport, dry_run: bool) -> None:
    if not path.exists():
        return
    report.changed.append(rel(root, path))
    if dry_run:
        return
    path.unlink()
    parent = path.parent
    while parent != root and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def _strip_block(text: str) -> tuple[str, bool]:
    start = text.find(BLOCK_BEGIN)
    end = text.find(BLOCK_END, start + 1) if start >= 0 else -1
    if start < 0 or end < 0:
        return text, False
    end += len(BLOCK_END)
    if text[end:end + 1] == "\n":
        end += 1
    return text[:start] + text[end:], True


def upsert_block(root: Path, path: Path, body: str, report: InstallReport,
                 dry_run: bool) -> None:
    """Exactly one marked plumb block in ``path``, the owner's own text untouched."""
    current = read_text(path) or ""
    block = f"{BLOCK_BEGIN}\n{body.rstrip()}\n{BLOCK_END}\n"
    stripped, found = _strip_block(current)
    if found:
        start = current.find(BLOCK_BEGIN)
        new = stripped[:start] + block + stripped[start:]
    else:
        sep = "" if not current or current.endswith("\n\n") else (
            "\n" if current.endswith("\n") else "\n\n")
        new = current + sep + block
    write_file(root, path, new, report, dry_run)


def remove_block(root: Path, path: Path, report: InstallReport, dry_run: bool) -> None:
    current = read_text(path)
    if current is None:
        return
    stripped, found = _strip_block(current)
    if not found:
        return
    if stripped.strip():
        write_file(root, path, stripped.rstrip("\n") + "\n", report, dry_run)
    else:
        remove_file(root, path, report, dry_run)


def has_block(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return BLOCK_BEGIN in text and BLOCK_END in text


def read_json_object(path: Path) -> dict[str, Any]:
    text = read_text(path)
    if text is None or not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise InstallError(f"{path} is not valid JSON; fix it first ({exc})") from exc
    if not isinstance(data, dict):
        raise InstallError(f"{path} is not a JSON object; fix it first")
    return data


def json_text(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- instructions


def instruction_block(argv: Sequence[str], host: str, *, hooks: bool) -> str:
    """The always-loaded instruction block (sp4 3.2): the same content as the Claude Code
    ``CLAUDE.md`` block, plus the CLI-only fallback."""
    plumb = command_line(argv)
    when = ("When no plumb lines reach your context at the start of a task (the host's hooks "
            "are not active), run" if hooks else "At the start of every task run")
    return "\n".join([
        "## plumb",
        "",
        "- Records of the owner's intent live in `.plumb/` (INT, SR, DEC, FEAT, NC); the test",
        "  map is `.plumb/test_map.txt`.",
        "- Read back each request in the owner's terms (what will and won't be done, "
        "assumptions",
        "  labelled) and record it as proposed with `" + plumb + " capture`; it never "
        "blocks the work.",
        f"- `{plumb} brief` prints the current intent; `{plumb} show <ID>` prints a record's",
        f"  examples and tests; `{plumb} explain <words>` says why something exists.",
        f"- {when} `{plumb} turn start --session <id>` with the owner's message on stdin",
        f"  (or `--prompt-file F`), and before your final reply `{plumb} turn end --session "
        "<id>`;",
        "  read their output and follow any instruction they print. Put the summary "
        "`turn end`",
        "  prints in your final reply as printed: a bare \"ok\" confirms only what the "
        "owner saw.",
        "- A message `/plumb <words>` is the owner asking about the project in plain words:",
        f"  resolve them to records (`{plumb} explain`, `{plumb} status`, `{plumb} show`) "
        "and",
        "  answer in the owner's terms, not code terms.",
        "- Only the owner confirms. Relay the owner's own affirming words with `"
        + plumb + " relay`",
        "  (never silence, never your own words); never run approve, revoke, triage "
        "--approve,",
        f"  spec approve or config auto-approve (adapter: {host}).",
    ])


# --------------------------------------------------------------------------- status


def marker_lines(marker: bool, how: str) -> list[str]:
    """The guard's status: the marker when the adapter sets it, else the 3.2 line."""
    if marker:
        return [f"session marker: {MARKER_NAME} set {how}; owner-only commands also require "
                "an interactive terminal", TRUST_LINE]
    return [NO_MARKER_LINE, TRUST_LINE]


def self_recorded_count(root: Path) -> int:
    """Valid confirmations standing on a message the agent recorded itself (R13 Q4): the
    approvals ``plumb relay`` marked ``self_recorded`` (confirm.is_self_recorded)."""
    try:
        from plumb.api import open_core
        from plumb.confirm import self_recorded_approvals

        core = open_core(root)
        return self_recorded_approvals(core.events(), core.config.approve.affirmations)
    except Exception:  # noqa: BLE001 - status never fails on a broken log
        return 0


def prompt_lines(root: Path, prompt_hook: bool, how: str) -> list[str]:
    """Where the owner's prompts come from, and the Q4 label when the agent records them."""
    count = self_recorded_count(root)
    lines = [f"prompts: recorded by the host's prompt hook ({how})" if prompt_hook
             else FALLBACK_PROMPT_LINE]
    if count or not prompt_hook:
        lines.append(f"confirmations resting on a {SELF_RECORDED}: {count}")
    return lines


def installed_hosts(root: Path, detectors: Iterable[tuple[str, Callable[[Path], bool]]],
                    skip: str) -> list[str]:
    return [name for name, installed in detectors if name != skip and installed(root)]


# --------------------------------------------------------------------------- shared block

# What each adapter leaves in the repository, by path only (no adapter imports another).
ADAPTER_FILES = {
    "codex": (".codex/hooks.json", ".codex/config.toml"),
    "pi": (".pi/extensions/plumb/index.ts",),
    "hermes": (".hermes/plugins/plumb/plugin.yaml",),
}


def adapter_installed(root: Path, host: str) -> bool:
    """Whether ``host``'s adapter files carry plumb's entries."""
    for name in ADAPTER_FILES.get(host, ()):
        path = root / name
        text = read_text(path) if path.exists() else None
        if text is None:
            continue
        if host != "codex" or "plumb hook" in text or "# >>> plumb" in text:
            return True
    return False


def context_file(root: Path, host: str) -> Path:
    """Select a nonempty root-local context without shadowing another host's rules."""
    if host == "hermes":
        # Hermes first selects the first regular Hermes-named file, then falls
        # through to the AGENTS context type if that file is empty/unreadable.
        for name in (".hermes.md", "HERMES.md"):
            candidate = root / name
            if not candidate.is_file():
                continue
            try:
                if candidate.read_text(encoding="utf-8").strip():
                    return candidate
            except (OSError, UnicodeDecodeError):
                pass
            break
        for name in ("AGENTS.override.md", "AGENTS.md", "agents.md"):
            candidate = root / name
            if not candidate.is_file():
                continue
            try:
                if candidate.read_text(encoding="utf-8").strip():
                    return candidate
            except (OSError, UnicodeDecodeError):
                continue
        for name in ("CLAUDE.md", "claude.md"):
            candidate = root / name
            if not candidate.is_file():
                continue
            try:
                if candidate.read_text(encoding="utf-8").strip():
                    return candidate
            except (OSError, UnicodeDecodeError):
                continue
    return root / "AGENTS.md"


def remove_shared_block(root: Path, host: str, report: InstallReport, dry_run: bool) -> None:
    """Remove the instruction block unless another installed adapter still reads it."""
    path = context_file(root, host)
    others = [h for h in HOSTS if h != host and adapter_installed(root, h)
              and context_file(root, h) == path]
    if others:
        report.lines.append(f"{rel(root, path)} block kept: still used by "
                            + ", ".join(others))
        return
    remove_block(root, path, report, dry_run)
