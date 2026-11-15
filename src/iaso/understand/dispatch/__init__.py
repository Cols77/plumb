"""Dispatchers (ENGINE): ``configured(core)`` returns the one dispatcher the config names.

``understand.dispatch`` in the config picks it: one name, or several in order
(``claude-code,codex``). ``auto`` is ``claude-code`` under Claude Code and ``hermes`` under
Hermes (an error elsewhere); ``codex`` and ``openrouter`` only when set. Only when a host cannot
serve (out of quota, not installed) does the next named host take the job
(``FallbackDispatcher``); any other failure fails the job with an error and nothing else is
tried. shortcut: ``understand.levels`` names one model for every host, so with several hosts
leave the levels unmapped (each host then uses its own default per level)."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from iaso.contracts import Dispatcher, DispatchError, Job, NoModel, host_unavailable


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


class FallbackDispatcher:
    """report-6fb712c4: the hosts named in ``understand.dispatch`` (``claude-code,codex``), in
    order. A job goes to the first; when that host cannot serve (out of quota, not installed:
    ``host_unavailable``) the same job goes to the next and the step line says so. Any other
    failure (a timeout, a bad answer) is not about the host and is not retried. When every host
    fails, the error names each host and its cause."""

    def __init__(self, hosts: list[Dispatcher]) -> None:
        self.hosts = hosts
        self.name = hosts[0].name

    def available(self) -> str | None:
        why = [f"{h.name}: {r}" for h in self.hosts if (r := h.available())]
        return "; ".join(why) if len(why) == len(self.hosts) else None

    def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
            on_step: Callable[[str], None]) -> Mapping[str, Any]:
        failed: list[str] = []
        for i, host in enumerate(self.hosts):
            try:
                answer = host.run(job, system=system, user=user, schema=schema, on_step=on_step)
            except DispatchError as exc:
                failed.append(f"{host.name}: {exc.message}")
                if i + 1 < len(self.hosts) and host_unavailable(exc):
                    on_step(f"{host.name} cannot serve ({exc.message[:80]}): "
                            f"trying {self.hosts[i + 1].name}")
                    continue
                raise DispatchError(exc.step, "; ".join(failed)) from exc
            self.name = host.name
            return answer
        raise DispatchError("run", "no host is configured")   # unreachable: hosts is not empty


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
    choices = [c.strip() for c in str(settings.dispatch or "auto").lower().split(",") if c.strip()]
    hosts = [_host(core, choice or "auto", model, timeout_s) for choice in choices or ["auto"]]
    return hosts[0] if len(hosts) == 1 else FallbackDispatcher(hosts)


def _host(core: Any, choice: str, model: str, timeout_s: float) -> Dispatcher:
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
