"""Hook input and output, the deadline and the catch-all (spec 6, 10).

Every hook is one process that reads the host's JSON on stdin, writes its answer on stdout
and always exits 0. On an internal error or an exhausted budget it prints a one-line notice
and the turn continues: plumb never blocks work because of its own failure.

Standard library only, so the post-edit fast path stays cheap.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

SKIP_BUDGET = "plumb: check skipped (budget)"
SKIP_ERROR = "plumb: check skipped (error, see .plumb/session/errors.log)"
HARD_LIMIT_S = 1.9  # the per-turn 2-second rule; the watchdog's last resort
_SESSION_RE = re.compile(r"[^A-Za-z0-9_-]+")


class BudgetExceeded(Exception):
    """A step would pass the hook's deadline."""


class Deadline:
    """A ``time.monotonic()`` deadline; ``check`` raises once it has passed."""

    def __init__(self, budget_ms: float, start: float | None = None) -> None:
        self.start = time.monotonic() if start is None else start
        self.budget_s = max(float(budget_ms), 0.0) / 1000.0

    def elapsed_s(self) -> float:
        return time.monotonic() - self.start

    def remaining_s(self) -> float:
        return self.budget_s - self.elapsed_s()

    def expired(self) -> bool:
        return self.remaining_s() <= 0

    def check(self, step: str = "") -> None:
        if self.expired():
            raise BudgetExceeded(step)


@dataclass
class HookOutput:
    """What a hook answers: context text, a system message, or a block."""

    text: str = ""
    system_message: str = ""
    block_reason: str = ""

    def render(self) -> str:
        if self.block_reason:
            return json.dumps({"decision": "block", "reason": self.block_reason},
                              ensure_ascii=False)
        if self.system_message:
            return json.dumps({"systemMessage": self.system_message}, ensure_ascii=False)
        return self.text


@dataclass
class HookContext:
    name: str
    data: Mapping[str, Any]
    root: Path
    session_id: str
    deadline: Deadline
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def plumb_dir(self) -> Path:
        return self.root / ".plumb"

    @property
    def session_dir(self) -> Path:
        return self.root / ".plumb" / "session"


def read_input(stream: TextIO) -> dict[str, Any]:
    """The host's JSON, or ``{}`` when it is missing or unreadable."""
    try:
        raw = stream.read()
    except (OSError, ValueError):
        return {}
    try:
        data = json.loads(raw) if raw and raw.strip() else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def safe_session_id(value: Any) -> str:
    """A session id usable as one directory name."""
    cleaned = _SESSION_RE.sub("-", str(value or "")).strip("-")
    return cleaned[:80] or "default"


def _plumb_root(start: Path) -> Path | None:
    try:
        start = start.resolve()
    except OSError:
        return None
    for candidate in (start, *start.parents):
        if (candidate / ".plumb").is_dir():
            return candidate
    return None


def find_hook_root(data: Mapping[str, Any], explicit: Path | str | None = None) -> Path | None:
    """The adopted repository: ``--root``, ``CLAUDE_PROJECT_DIR``, the input's ``cwd``, or
    the working directory, whichever first leads up to a ``.plumb/`` directory."""
    candidates: list[str] = []
    if explicit:
        return _plumb_root(Path(explicit))
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        candidates.append(env)
    cwd = data.get("cwd")
    if isinstance(cwd, str) and cwd:
        candidates.append(cwd)
    candidates.append(os.getcwd())
    for candidate in candidates:
        root = _plumb_root(Path(candidate))
        if root is not None:
            return root
    return None


def log_error(root: Path | None, name: str, detail: str) -> None:
    if root is None:
        return
    try:
        path = root / ".plumb" / "session" / "errors.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"--- {stamp} plumb hook {name}\n{detail.rstrip()}\n")
    except OSError:
        pass


def _notice(text: str, json_output: bool) -> str:
    return json.dumps({"systemMessage": text}) if json_output else text


class _Writer:
    """Writes the hook's answer exactly once, even when the watchdog fires."""

    def __init__(self, stdout: TextIO) -> None:
        self.stdout = stdout
        self.lock = threading.Lock()
        self.done = False

    def write(self, text: str) -> bool:
        with self.lock:
            if self.done:
                return False
            self.done = True
            if text:
                self.stdout.write(text if text.endswith("\n") else text + "\n")
            try:
                self.stdout.flush()
            except (OSError, ValueError):
                pass
            return True


def run_hook(name: str, handler: Callable[[HookContext], HookOutput | None], *,
             stdin: TextIO | None = None, stdout: TextIO | None = None,
             root: Path | str | None = None, budget_ms: float | Callable[[Path], float] = 800,
             json_output: bool = False, watchdog: bool = False,
             start: float | None = None) -> int:
    """Run one hook handler with the deadline and the catch-all. Always returns 0."""
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    writer = _Writer(stdout)
    found: Path | None = None
    timer: threading.Timer | None = None
    try:
        data = read_input(stdin)
        found = find_hook_root(data, root)
        if found is None:
            return 0  # repository not adopted by plumb: nothing to do
        budget = budget_ms(found) if callable(budget_ms) else budget_ms
        if watchdog:
            def fire() -> None:
                if writer.write(_notice(SKIP_BUDGET, json_output)):
                    log_error(found, name, f"watchdog: hard limit {HARD_LIMIT_S}s reached")
                    os._exit(0)

            elapsed = 0.0 if start is None else time.monotonic() - start
            timer = threading.Timer(max(HARD_LIMIT_S - elapsed, 0.05), fire)
            timer.daemon = True
            timer.start()
        ctx = HookContext(name=name, data=data, root=found,
                          session_id=safe_session_id(data.get("session_id")),
                          deadline=Deadline(budget, start))
        result = handler(ctx)
        writer.write(result.render() if result is not None else "")
    except BudgetExceeded as exc:
        log_error(found, name, f"budget exceeded at step: {exc}")
        writer.write(_notice(SKIP_BUDGET, json_output))
    except Exception:  # noqa: BLE001 - plumb never blocks work on its own failure
        log_error(found, name, traceback.format_exc())
        writer.write(_notice(SKIP_ERROR, json_output))
    finally:
        if timer is not None:
            timer.cancel()
    return 0


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON through a temporary file and ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def hook_budget(name: str) -> Callable[[Path], float]:
    """The configured budget of one hook (``hooks.budget_ms``)."""

    def budget(root: Path) -> float:
        from plumb.config import load_config

        defaults = {"session_start": 900, "prompt": 600, "stop": 800, "post_edit": 300}
        try:
            return float(load_config(root).hooks.budget_ms.get(name, defaults.get(name, 800)))
        except Exception:  # noqa: BLE001 - a broken config must not break the hook
            return float(defaults.get(name, 800))

    return budget
