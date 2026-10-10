"""Hook input and output, the deadline and the catch-all (spec 6, 10).

Every hook is one process that reads the host's JSON on stdin, writes its answer on stdout
and always exits 0. On an internal error or an exhausted budget it prints a one-line notice
and the turn continues: plumb never blocks work because of its own failure.

A handler computes its intent-translation lines first (the read-back, the confirmed records,
the relay line) and hands them to ``HookContext.keep``. A budget cut, an internal error or
the watchdog then prints those kept lines followed by the notice naming the skipped step,
so a loaded machine drops evidence detail, never the read-back (spec 10).

Standard library only, so the post-edit fast path stays cheap.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import threading
import time
from collections.abc import Callable, Mapping
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


class HookOutput:
    """What a hook answers: context text, a system message, or a block. (Plain classes, not
    dataclasses: the module costs import time on every hook.)"""

    __slots__ = ("text", "system_message", "block_reason")

    def __init__(self, text: str = "", system_message: str = "", block_reason: str = "") -> None:
        self.text = text
        self.system_message = system_message
        self.block_reason = block_reason

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HookOutput):
            return NotImplemented
        return (self.text, self.system_message, self.block_reason) == (
            other.text, other.system_message, other.block_reason)

    def __repr__(self) -> str:
        return (f"HookOutput(text={self.text!r}, system_message={self.system_message!r}, "
                f"block_reason={self.block_reason!r})")

    def render(self) -> str:
        if self.block_reason:
            return json.dumps({"decision": "block", "reason": self.block_reason},
                              ensure_ascii=False)
        if self.system_message:
            return json.dumps({"systemMessage": self.system_message}, ensure_ascii=False)
        return self.text


class Kept:
    """The lines a handler has already computed and that must survive a cut."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def snapshot(self) -> list[str]:
        return list(self.lines)


class HookContext:
    """One hook run: its name, the host's JSON, the repository root, the session, the
    deadline and the kept lines."""

    def __init__(self, name: str, data: Mapping[str, Any], root: Path, session_id: str,
                 deadline: Deadline, extra: dict[str, Any] | None = None,
                 kept: Kept | None = None) -> None:
        self.name = name
        self.data = data
        self.root = root
        self.session_id = session_id
        self.deadline = deadline
        self.extra = {} if extra is None else extra
        self.kept = Kept() if kept is None else kept

    def keep(self, lines: list[str]) -> None:
        """Replace the output printed if a later step is cut (budget, error, watchdog)."""
        self.kept.lines = [line for line in lines if line]

    @property
    def plumb_dir(self) -> Path:
        return self.root / ".plumb"

    @property
    def session_dir(self) -> Path:
        return self.root / ".plumb" / "session"


def use_utf8_stdio() -> None:
    """Make the process's stdin and stdout UTF-8, as Claude Code sends and reads them.

    Python's default stdio encoding is the locale code page (cp1252 on Windows). Input bytes
    that are not UTF-8 are replaced rather than raised; output is strict UTF-8.
    """
    for stream, errors in ((sys.stdin, "replace"), (sys.stdout, "strict")):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors=errors)
        except (OSError, ValueError):
            pass


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
    return json.dumps({"systemMessage": text}, ensure_ascii=False) if json_output else text


def skip_line(step: str = "") -> str:
    """``plumb: check skipped (budget)``, naming the step when one is known."""
    return f"{SKIP_BUDGET}: {step}" if step else SKIP_BUDGET


def _format_exc() -> str:
    import traceback  # only on a failure: the module costs import time on every hook

    return traceback.format_exc()


# hooks that never hash link ends (the post-edit fast path stays standard library only)
NO_HASHING = frozenset({"post-edit"})
# The hook running in this process: ``plumb.hashing`` opens its ``stat_cached`` block for
# ``STAT_CACHE_ROOT`` at the first link-end hash (file-end hashes reused across processes,
# each end hashed once per process, statuses kept by the core) and parks the block in
# ``STAT_CACHE_STACK``, which ``run_hook`` closes. Nothing imports hashing before it is needed.
STAT_CACHE_ROOT: Path | None = None
STAT_CACHE_STACK: contextlib.ExitStack | None = None


def _close_hash_cache() -> None:
    global STAT_CACHE_ROOT, STAT_CACHE_STACK
    stack, STAT_CACHE_STACK, STAT_CACHE_ROOT = STAT_CACHE_STACK, None, None
    if stack is not None:
        try:
            stack.close()
        except Exception:  # noqa: BLE001 - a cache that cannot be saved never fails the hook
            pass


def _cut_output(kept: Kept, notice: str, json_output: bool) -> str:
    """The kept lines plus the notice; the bare notice when nothing was kept."""
    lines = kept.snapshot()
    return _notice("\n".join([*lines, notice]), json_output)


class _Writer:
    """Writes the hook's answer exactly once, even when the watchdog fires."""

    def __init__(self, stdout: TextIO) -> None:
        self.stdout = stdout
        self.lock = threading.Lock()
        self.done = False

    def write(self, text: str) -> bool:
        """Write ``text`` once. A failed write raises and leaves the writer open, so the
        catch-all can still print its skip notice."""
        with self.lock:
            if self.done:
                return False
            if text:
                self.stdout.write(text if text.endswith("\n") else text + "\n")
            self.done = True
            try:
                self.stdout.flush()
            except (OSError, ValueError):
                pass
            return True


def run_hook(name: str, handler: Callable[[HookContext], HookOutput | None], *,
             stdin: TextIO | None = None, stdout: TextIO | None = None,
             root: Path | str | None = None, budget_ms: float | Callable[[Path], float] = 800,
             json_output: bool = False, watchdog: bool = False,
             start: float | None = None, grace_s: float = 0.0) -> int:
    """Run one hook handler with the deadline and the catch-all. Always returns 0.

    ``grace_s``: a hook whose whole answer is lines it keeps (R1) waits this much longer when
    the hard limit finds nothing kept yet, since the bare notice would say nothing."""
    global STAT_CACHE_ROOT
    if os.environ.get("PLUMB_JOB"):
        return 0  # SR-104 EX-2: a hook inside a worker's job prints and queues nothing
    if stdin is None or stdout is None:
        use_utf8_stdio()
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    writer = _Writer(stdout)
    kept = Kept()
    found: Path | None = None
    timer: threading.Timer | None = None
    lane = _verify_lane()
    was_hook = getattr(lane, "HOOK_PROCESS", False)
    if lane is not None:  # every VerifyAPI this hook opens is in hook mode (R5)
        lane.HOOK_PROCESS = True
    try:
        data = read_input(stdin)
        found = find_hook_root(data, root)
        if found is None:
            return 0  # repository not adopted by plumb: nothing to do
        budget = budget_ms(found) if callable(budget_ms) else budget_ms
        graced: list[bool] = []
        if watchdog:
            def fire() -> None:
                nonlocal timer
                if grace_s > 0 and not kept.lines and not graced:
                    graced.append(True)  # nothing to show yet: give the read-back a last chance
                    timer = threading.Timer(grace_s, fire)
                    timer.daemon = True
                    timer.start()
                    return
                if writer.write(_cut_output(kept, SKIP_BUDGET, json_output)):
                    log_error(found, name, f"watchdog: hard limit {HARD_LIMIT_S}s reached")
                    flush = getattr(sys.modules.get("plumb.hashing"), "flush_stat_cache", None)
                    if flush is not None:
                        flush()  # the hash cache learned so far warms the next hook
                    os._exit(0)

            elapsed = 0.0 if start is None else time.monotonic() - start
            timer = threading.Timer(max(HARD_LIMIT_S - elapsed, 0.05), fire)
            timer.daemon = True
            timer.start()
        if name not in NO_HASHING:
            STAT_CACHE_ROOT = found
        ctx = HookContext(name=name, data=data, root=found,
                          session_id=safe_session_id(data.get("session_id")),
                          deadline=Deadline(budget, start), kept=kept)
        result = handler(ctx)
        writer.write(result.render() if result is not None else "")
    except BudgetExceeded as exc:
        log_error(found, name, f"budget exceeded at step: {exc}")
        step = str(exc)
        writer.write(_cut_output(kept, skip_line(step) if kept.lines else SKIP_BUDGET,
                                 json_output))
    except Exception:  # noqa: BLE001 - plumb never blocks work on its own failure
        log_error(found, name, _format_exc())
        try:
            writer.write(_cut_output(kept, SKIP_ERROR, json_output))
        except Exception:  # noqa: BLE001 - nothing more can be said on a broken stdout
            pass
    finally:
        if timer is not None:
            timer.cancel()
        _close_hash_cache()
        if lane is not None:
            lane.HOOK_PROCESS = was_hook
    return 0


def _verify_lane() -> Any:
    """``plumb.verify`` (a tiny module), or None in a build without it."""
    try:
        import plumb.verify as lane
    except ImportError:
        return None
    return lane


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
        from plumb.config import DEFAULT_HOOK_BUDGET_MS as defaults
        from plumb.config import load_config

        try:
            return float(load_config(root).hooks.budget_ms.get(name, defaults.get(name, 800)))
        except Exception:  # noqa: BLE001 - a broken config must not break the hook
            return float(defaults.get(name, 800))

    return budget
