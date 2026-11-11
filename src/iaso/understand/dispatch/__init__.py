"""Dispatchers (ENGINE): ``configured(core)`` returns exactly one, never a second route.

``understand.dispatch`` in the config picks it: ``auto`` is ``claude-code`` under Claude Code and
``hermes`` under Hermes (an error elsewhere), ``codex`` and ``openrouter`` only when set. When the one
dispatcher fails, the job fails with an error; nothing else is tried."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from iaso.contracts import Dispatcher, DispatchError, Job, NoModel


class ScriptedDispatcher:
    """``IASO_FAKE_DISPATCH=<file>``: answers each job kind with the file's ``{kind: answer}``
    (the test harness's way of giving a worker process a fake model). A number under
    ``"$delay"`` makes every run wait that many seconds first, and ``"$fail_when": {"kind":
    ..., "contains": text}`` fails the runs whose inputs hold ``text``. It never reaches a
    model; its results say ``fake`` as the dispatcher."""

    name = "fake"

    def __init__(self, script: Path) -> None:
        self.script = Path(script)

    def available(self) -> str | None:
        return None if self.script.is_file() else "the scripted answers file is missing"

    def _log(self, job: Job) -> None:
        """One line per call in ``<script>.calls`` (a test counts the model calls)."""
        try:
            path = self.script.with_name(self.script.name + ".calls")
            with path.open("a", encoding="utf-8") as out:
                out.write(json.dumps({"kind": job.kind, "job": job.id}) + "\n")
        except OSError:
            pass

    def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
            on_step: Callable[[str], None]) -> Mapping[str, Any]:
        try:
            data = json.loads(self.script.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DispatchError("run", f"the scripted answers cannot be read: {exc}") from exc
        pause = data.get("$delay") if isinstance(data, Mapping) else None
        if isinstance(pause, (int, float)) and 0 < pause <= 30:
            time.sleep(float(pause))  # lets a test look at the status line meanwhile
        self._log(job)
        fail = data.get("$fail_when") if isinstance(data, Mapping) else None
        if (isinstance(fail, Mapping) and fail.get("kind", job.kind) == job.kind
                and str(fail.get("contains", "")) in json.dumps(job.inputs, default=str)):
            raise DispatchError("run", "the model could not be reached")
        answer = data.get(job.kind, {}) if isinstance(data, Mapping) else {}
        if isinstance(answer, Mapping) and "error" in answer and len(answer) == 1:
            raise DispatchError("run", str(answer["error"]))
        return dict(answer) if isinstance(answer, Mapping) else {}


def host_dispatcher() -> str | None:
    """``claude-code`` or ``hermes`` from the environment the process runs in, else None."""
    if os.environ.get("CLAUDE_PROJECT_DIR") or any(
            name.startswith("CLAUDE_CODE_") for name in os.environ):
        return "claude-code"
    if any(name.startswith("HERMES_") for name in os.environ):
        return "hermes"
    return None


# SR-325 EX-5, DEC-260: a job retried after a failure gets a larger budget each time; the
# worker sets the scale from the failures in a row before asking
class Unlocked:
    """SR-387: ``inner`` whose ``method`` (a dispatcher's ``run``, the JEV client's ``judge``)
    lets go of ``guard`` while the model call is out."""

    def __init__(self, inner: Any, guard: Any, method: str = "run") -> None:
        self.inner, self.guard, self.method = inner, guard, method

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self.inner, name)
        if name != self.method:
            return attr

        def out(*args: Any, **kwargs: Any) -> Any:
            self.guard.release()
            try:
                return attr(*args, **kwargs)
            finally:
                self.guard.acquire()
        return out


budget_scale: ContextVar[int] = ContextVar("iaso_budget_scale", default=1)


def configured(core: Any, *, model: str | None = None) -> Dispatcher:
    """The one dispatcher; ``model`` overrides ``understand.model`` for one kind of job."""
    script = os.environ.get("IASO_FAKE_DISPATCH")
    if script:
        return ScriptedDispatcher(Path(script))
    from iaso.config import Config, UnderstandConfig, model_of

    settings = core.config.understand if core is not None else UnderstandConfig()
    # SR-389: the stage settings name levels; a name that is no level is a model
    model = model_of(core.config if core is not None else Config(), model or settings.model)
    timeout_s = float(settings.timeout_s) * max(1, budget_scale.get())
    choice = str(settings.dispatch or "auto").strip().lower()
    if choice == "auto":
        choice = host_dispatcher() or ""
        if not choice:
            raise NoModel("no model configured: this is neither Claude Code nor Hermes, so "
                          "set which one to use (understand.dispatch)")
    if choice == "claude-code":
        from iaso.understand.dispatch.claude_code import ClaudeCodeDispatcher

        return ClaudeCodeDispatcher(model=model, timeout_s=timeout_s)
    if choice == "codex":
        from iaso.config import LEVELS
        from iaso.understand.dispatch.codex import CodexDispatcher

        # a level left unmapped (understand.levels) is no Codex model: Codex uses its own
        return CodexDispatcher(model="" if model in LEVELS else model, timeout_s=timeout_s)
    if choice == "hermes":
        from iaso.understand.dispatch.hermes import HermesDispatcher

        return HermesDispatcher(model=model, timeout_s=timeout_s)
    if choice == "openrouter":
        from iaso.understand.dispatch.openrouter import OpenRouterDispatcher

        dispatcher = OpenRouterDispatcher.from_core(core)
        if model and "/" in model:
            dispatcher.model = model
        return dispatcher
    raise NoModel(f"no model configured: {choice!r} is not a dispatcher "
                  "(claude-code, codex, hermes or openrouter)")
