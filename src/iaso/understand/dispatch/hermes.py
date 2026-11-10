"""The ``hermes`` dispatcher: a delegated Hermes session answers the job (spec section 5).

The exact call is the spec's question 12.1, so it sits behind a small seam, ``HermesDelegate``:
``delegate(prompt, tools=..., ...)`` returns the child's text. The dispatcher puts the system
prompt, the schema and the inputs in the prompt, asks for no tools, and reads one JSON object
back, which it checks against the schema.

What was verified (Hermes on this machine, 2026-10-10): ``hermes -z <prompt>`` is a one-shot
call that prints only the final text; ``--safe-mode`` drops the user's configuration, rules,
plugins and MCP servers. There is no flag for a session with no tools: ``-t ""`` is ignored
(all tools stay on) and an unknown toolset is rejected, so ``HermesCliDelegate`` asks for the
narrowest toolset it accepts (``memory``). A true tool-less child needs Hermes' delegation
interface from inside a Hermes session; ``HermesDelegate`` is where that goes."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from iaso.contracts import DispatchError, Job
from iaso.understand import schema as schema_check

NARROWEST_TOOLSET = "memory"
MAX_PROMPT_CHARS = 28000        # the Windows command line holds about 32 000 characters


class HermesDelegate(Protocol):
    def available(self) -> str | None: ...

    def delegate(self, prompt: str, *, tools: Sequence[str], model: str, timeout_s: float,
                 job_id: str) -> str: ...


class HermesCliDelegate:
    """``hermes -z`` in an empty directory, with the worker's token left out of its
    environment and the job id in it."""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env = dict(os.environ if env is None else env)

    def _binary(self) -> str | None:
        return shutil.which("hermes", path=self._env.get("PATH", ""))

    def available(self) -> str | None:
        if self._binary() is None:
            return "Hermes was not found on this machine"
        return None

    def delegate(self, prompt: str, *, tools: Sequence[str], model: str, timeout_s: float,
                 job_id: str) -> str:
        binary = self._binary()
        if binary is None:
            raise DispatchError("start", self.available() or "Hermes is not available")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise DispatchError("start", "the request is too long for Hermes' command line")
        command = [binary, "-z", prompt, "--safe-mode",
                   "-t", ",".join(tools) if tools else NARROWEST_TOOLSET]
        if "/" in model:                  # a Hermes model name; "haiku" is Claude's alias
            command += ["-m", model]
        env = {k: v for k, v in self._env.items() if k != "IASO_WORKER"}
        env["IASO_JOB"] = job_id
        workdir = tempfile.mkdtemp(prefix="iaso-job-")
        try:
            done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                  cwd=workdir, env=env, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise DispatchError("timeout", f"no answer within {timeout_s:g} seconds") from exc
        except OSError as exc:
            raise DispatchError("start", f"Hermes could not be started: {exc}") from exc
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        if done.returncode != 0 and not done.stdout.strip():
            raise DispatchError("run", (done.stderr or f"exit code {done.returncode}").strip()
                                [:300])
        return done.stdout


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _json_object(text: str) -> Mapping[str, Any] | None:
    candidates = [text.strip(), *(m.strip() for m in _FENCE.findall(text))]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            found = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(found, Mapping):
            return found
    return None


class HermesDispatcher:
    name = "hermes"

    def __init__(self, *, delegate: HermesDelegate | None = None, model: str = "",
                 timeout_s: float = 120) -> None:
        self.delegate = delegate or HermesCliDelegate()
        self.model = model
        self.timeout_s = timeout_s

    def available(self) -> str | None:
        return self.delegate.available()

    def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
            on_step: Callable[[str], None]) -> Mapping[str, Any]:
        reason = self.available()
        if reason:
            raise DispatchError("start", reason)
        on_step("asking the model")
        prompt = (f"{system}\n\nAnswer with one JSON object that follows this JSON schema, "
                  f"and nothing else:\n{json.dumps(dict(schema), sort_keys=True)}\n\n"
                  f"Inputs:\n{user}")
        try:
            text = self.delegate.delegate(prompt, tools=(), model=self.model,
                                          timeout_s=self.timeout_s, job_id=job.id)
        except DispatchError:
            raise
        except Exception as exc:  # noqa: BLE001 - whatever the seam raises is a run error
            raise DispatchError("run", f"the delegated session failed: {exc}") from exc
        answer = _json_object(text)
        if answer is None:
            raise DispatchError("answer", "the delegated session gave no JSON object")
        found = schema_check.problems(answer, schema)
        if found:
            raise DispatchError("schema", "; ".join(found[:3]))
        return dict(answer)
