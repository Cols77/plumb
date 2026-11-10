"""Hook input and output, the deadline and the catch-all (spec 6, 10).

Every hook is one process that reads the host's JSON on stdin, writes its answer on stdout
and always exits 0. On an internal error or an exhausted budget it prints a one-line notice
and the turn continues: iaso never blocks work because of its own failure.

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

from iaso.paths import holds_records

SKIP_BUDGET = "iaso: check skipped (budget)"
SKIP_ERROR = "iaso: check skipped (error, see .iaso/session/errors.log)"
HARD_LIMIT_S = 90.0  # SR-310: the watchdog's last resort when hooks.hard_limit_s is unset
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
    """What a hook answers: context text, a system message, a block, or additional context
    for the agent after a tool call (``additional_context``, the PostToolUse form). (Plain
    classes, not dataclasses: the module costs import time on every hook.)"""

    __slots__ = ("text", "system_message", "block_reason", "additional_context")

    def __init__(self, text: str = "", system_message: str = "", block_reason: str = "",
                 additional_context: str = "") -> None:
        self.text = text
        self.system_message = system_message
        self.block_reason = block_reason
        self.additional_context = additional_context

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HookOutput):
            return NotImplemented
        return (self.text, self.system_message, self.block_reason,
                self.additional_context) == (
            other.text, other.system_message, other.block_reason, other.additional_context)

    def __repr__(self) -> str:
        return (f"HookOutput(text={self.text!r}, system_message={self.system_message!r}, "
                f"block_reason={self.block_reason!r}, "
                f"additional_context={self.additional_context!r})")

    def render(self) -> str:
        if self.block_reason:
            block = {"decision": "block", "reason": self.block_reason}
            if self.system_message:  # SR-373 EX-5: the owner's line beside the agent's block
                block["systemMessage"] = self.system_message
            return json.dumps(block, ensure_ascii=False)
        if self.additional_context:
            return json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": self.additional_context}}, ensure_ascii=False)
        if self.system_message:
            return json.dumps({"systemMessage": self.system_message}, ensure_ascii=False)
        return self.text


class Kept:
    """The lines a handler has already computed and that must survive a cut."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.retained: list[str] = []  # acknowledged one-shot handoffs survive later keep calls
        # nothing is owed by this hook (iaso's panel holds the session background): a cut,
        # the watchdog's included, prints nothing at all, not even the skip notice
        self.quiet = False

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
        self.steps: list[tuple[str, float]] = []   # SR-375: (step, ms) when profiling
        self._mark = deadline.start

    def mark(self, step: str) -> None:
        """End the named step: its duration goes to the profile (``IASO_HOOK_PROFILE=1``)."""
        now = time.monotonic()
        self.steps.append((step, round((now - self._mark) * 1000, 1)))
        self._mark = now

    def keep(self, lines: list[str]) -> None:
        """Replace the output printed if a later step is cut (budget, error, watchdog)."""
        self.kept.lines = [*self.kept.retained,
                           *(line for line in lines if line and line not in self.kept.retained)]

    @property
    def iaso_dir(self) -> Path:
        return self.root / ".iaso"

    @property
    def session_dir(self) -> Path:
        return self.root / ".iaso" / "session"


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


def _iaso_root(start: Path) -> Path | None:
    try:
        start = start.resolve()
    except OSError:
        return None
    for candidate in (start, *start.parents):
        if holds_records(candidate):            # never iaso's own home (~/.iaso)
            return candidate
    return None


def find_hook_root(data: Mapping[str, Any], explicit: Path | str | None = None) -> Path | None:
    """The adopted repository: ``--root``, ``CLAUDE_PROJECT_DIR``, the input's ``cwd``, or
    the working directory, whichever first leads up to a ``.iaso/`` directory."""
    candidates: list[str] = []
    if explicit:
        return _iaso_root(Path(explicit))
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        candidates.append(env)
    cwd = data.get("cwd")
    if isinstance(cwd, str) and cwd:
        candidates.append(cwd)
    candidates.append(os.getcwd())
    for candidate in candidates:
        root = _iaso_root(Path(candidate))
        if root is not None:
            return root
    return None


def log_error(root: Path | None, name: str, detail: str) -> None:
    if root is None:
        return
    try:
        path = root / ".iaso" / "session" / "errors.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"--- {stamp} iaso hook {name}\n{detail.rstrip()}\n")
    except OSError:
        pass


PROFILE_ENV = "IASO_HOOK_PROFILE"
PROFILE_FILE = "hook-timing.jsonl"


def write_profile(root: Path | None, name: str, ctx: HookContext | None, start: float,
                  cut: str = "") -> None:
    """SR-375 EX-1: one line per hook run in ``.iaso/session/hook-timing.jsonl`` (its total
    and each step marked so far), only while ``IASO_HOOK_PROFILE=1``."""
    if root is None or os.environ.get(PROFILE_ENV) != "1":
        return
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hook": name,
             "total_ms": round((time.monotonic() - start) * 1000, 1),
             "steps": list(ctx.steps) if ctx is not None else [], "cut": cut}
    try:
        path = root / ".iaso" / "session" / PROFILE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _open_case(root: Path | None, name: str, detail: str) -> None:
    """SR-325, SR-375: a hook that raised or was cut leaves one debug case."""
    try:
        from iaso import debug

        debug.hook_error(root, name, detail)
    except Exception:  # noqa: BLE001 - recording the case must not break the notice
        pass


def _notice(text: str, json_output: bool) -> str:
    return json.dumps({"systemMessage": text}, ensure_ascii=False) if json_output else text


def skip_line(step: str = "") -> str:
    """``iaso: check skipped (budget)``, naming the step when one is known."""
    return f"{SKIP_BUDGET}: {step}" if step else SKIP_BUDGET


def _format_exc() -> str:
    import traceback  # only on a failure: the module costs import time on every hook

    return traceback.format_exc()


# hooks that never hash link ends (the post-edit fast path stays standard library only)
NO_HASHING = frozenset({"post-edit"})
# The hook running in this process: ``iaso.hashing`` opens its ``stat_cached`` block for
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
    """The kept lines plus the notice; the bare notice when nothing was kept; nothing when the
    hook owed nothing (``Kept.quiet``)."""
    if kept.quiet:
        return ""
    lines = [*kept.snapshot(), *([notice] if notice else [])]
    return _notice("\n".join(lines), json_output) if lines else ""


def _once(ctx: HookContext | None, step: str = "") -> str:
    """SR-374 EX-7: the skipped step, named once per session (the insight table's ``cut``);
    "" when this session was told already."""
    if ctx is None:
        return skip_line(step)
    try:
        from iaso.present import insights
        from iaso.present.delta import Emitter, seen_path

        emitter = Emitter(seen_path(ctx.session_dir, ctx.session_id), "cut", None)
        out = emitter.add(insights.lines("cut", None, {"hook": ctx.name, "step": step}))
        emitter.close()
        return out[0] if out else ""
    except Exception:  # noqa: BLE001 - the notice is said rather than lost
        return skip_line(step)


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
    if os.environ.get("IASO_JOB"):
        return 0  # SR-104 EX-2: a hook inside a worker's job prints and queues nothing
    if stdin is None or stdout is None:
        use_utf8_stdio()
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    writer = _Writer(stdout)
    kept = Kept()
    found: Path | None = None
    ctx: HookContext | None = None
    began = time.monotonic() if start is None else start
    timer: threading.Timer | None = None
    lane = _verify_lane()
    was_hook = getattr(lane, "HOOK_PROCESS", False)
    if lane is not None:  # every VerifyAPI this hook opens is in hook mode (R5)
        lane.HOOK_PROCESS = True
    from iaso import log as iaso_log

    was_live = iaso_log.LIVE_ONLY
    iaso_log.LIVE_ONLY = True  # SR-287 EX-4: a hook never opens an archive segment
    try:
        data = read_input(stdin)
        found = find_hook_root(data, root)
        if found is None:
            return 0  # repository not adopted by iaso: nothing to do
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
                if writer.write(_cut_output(kept, _once(ctx), json_output)):
                    detail = f"watchdog: hard limit {limit}s reached"
                    log_error(found, name, detail)
                    write_profile(found, name, ctx, began, cut="watchdog")
                    _open_case(found, name, detail)  # SR-375 EX-2: a cut is a defect
                    flush = getattr(sys.modules.get("iaso.hashing"), "flush_stat_cache", None)
                    if flush is not None:
                        flush()  # the hash cache learned so far warms the next hook
                    os._exit(0)

            limit = hard_limit_s(found)
            elapsed = 0.0 if start is None else time.monotonic() - start
            timer = threading.Timer(max(limit - elapsed, 0.05), fire)
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
        writer.write(_cut_output(kept, _once(ctx, step if kept.lines else ""), json_output))
    except Exception:  # noqa: BLE001 - iaso never blocks work on its own failure
        detail = _format_exc()
        log_error(found, name, detail)
        _open_case(found, name, detail)  # SR-325: one debug case, turn not held
        try:
            writer.write(_cut_output(kept, SKIP_ERROR, json_output))
        except Exception:  # noqa: BLE001 - nothing more can be said on a broken stdout
            pass
    finally:
        if timer is not None:
            timer.cancel()
        if found is not None:
            write_profile(found, name, ctx, began)
        _close_hash_cache()
        if lane is not None:
            lane.HOOK_PROCESS = was_hook
        iaso_log.LIVE_ONLY = was_live
    return 0


def _verify_lane() -> Any:
    """``iaso.verify`` (a tiny module), or None in a build without it."""
    try:
        import iaso.verify as lane
    except ImportError:
        return None
    return lane


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON through a temporary file and ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n",
                   encoding="utf-8", newline="\n")
    # Windows refuses the replace while a reader holds the target open: retry briefly
    for attempt in range(_REPLACE_TRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == _REPLACE_TRIES - 1:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                raise
            time.sleep(0.05 * (attempt + 1))


_REPLACE_TRIES = 8


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def hard_limit_s(root: Path) -> float:
    """The watchdog's hard limit: ``hooks.hard_limit_s`` when set, else ``HARD_LIMIT_S``."""
    try:
        # the post-edit fast path stays standard library only (SR-011): the config is parsed
        # only when config.yaml sets the key (a commented-out default does not count)
        if not re.search(r"^\s*hard_limit_s\s*:",
                         (root / ".iaso" / "config.yaml").read_text(encoding="utf-8"), re.M):
            return HARD_LIMIT_S
        from iaso.config import load_config

        configured = load_config(root).hooks.hard_limit_s
        return float(configured) if configured is not None else HARD_LIMIT_S
    except Exception:  # noqa: BLE001 - a broken config must not break the hook
        return HARD_LIMIT_S


def hook_budget(name: str) -> Callable[[Path], float]:
    """The configured budget of one hook (``hooks.budget_ms``)."""

    def budget(root: Path) -> float:
        from iaso.config import DEFAULT_HOOK_BUDGET_MS as defaults
        from iaso.config import load_config

        try:
            return float(load_config(root).hooks.budget_ms.get(name, defaults.get(name, 800)))
        except Exception:  # noqa: BLE001 - a broken config must not break the hook
            return float(defaults.get(name, 800))

    return budget
