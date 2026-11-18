"""The ``claude-code`` dispatcher: one ``claude -p`` call per job (spec section 5).

The call selects a iaso-shipped agent (``--agent iaso-<kind>`` defined by ``--agents``),
has no tools, answers the job's schema, keeps no session and loads nothing of the owner's
setup (``--setting-sources ""``, ``--strict-mcp-config``, ``--disable-slash-commands``). It
runs in a new empty temporary directory, never the repository, so the model sees only the
job's inputs. The job id goes into the child's environment as ``IASO_JOB`` (iaso's own hooks
exit at once on it); the worker's token never does."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from typing import Any

from iaso.contracts import DispatchError, Job
from iaso.understand import agents
from iaso.understand import schema as schema_check


def cli_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """The schema as the claude command accepts it: our own ``id`` label (``read.v1``) is not
    a JSON Schema keyword there (it asks for ``$id``, a URI), so it is left off."""
    return {key: value for key, value in schema.items() if key != "id"}


class ClaudeCodeDispatcher:
    name = "claude-code"

    def __init__(self, *, model: str = "haiku", timeout_s: float = 120,
                 env: Mapping[str, str] | None = None) -> None:
        self.model = model
        self.timeout_s = timeout_s
        self._env = dict(os.environ if env is None else env)

    def _binary(self) -> str | None:
        from iaso.hosts.claude_code import claude_binary

        return claude_binary(self._env.get("PATH", ""))

    def available(self) -> str | None:
        if self._binary() is None:
            from iaso.hosts.claude_code import claude_missing

            return claude_missing(self._env.get("PATH", ""))
        return None

    def command(self, binary: str, job: Job, system: str, schema: Mapping[str, Any]
                ) -> list[str]:
        kind = job.kind
        return [binary, "-p", "--agent", agents.name(kind),
                "--agents", json.dumps(agents.definition(kind, system), ensure_ascii=False),
                "--model", self.model, "--tools", "",
                "--json-schema", json.dumps(cli_schema(schema), ensure_ascii=False),
                "--output-format", "json", "--no-session-persistence",
                "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands"]

    def child_env(self, job: Job) -> dict[str, str]:
        env = {k: v for k, v in self._env.items() if k != "IASO_WORKER"}
        env["IASO_JOB"] = job.id
        return env

    def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
            on_step: Callable[[str], None]) -> Mapping[str, Any]:
        binary = self._binary()
        if binary is None:
            raise DispatchError("start", self.available() or "claude is not available")
        on_step("asking the model")
        workdir = tempfile.mkdtemp(prefix="iaso-job-")
        try:
            done = subprocess.run(
                self.command(binary, job, system, schema), input=user, capture_output=True,
                text=True, encoding="utf-8", cwd=workdir, env=self.child_env(job),
                timeout=self.timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise DispatchError("timeout",
                                f"no answer within {self.timeout_s:g} seconds") from exc
        except OSError as exc:
            raise DispatchError("start", f"claude could not be started: {exc}") from exc
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        return self.answer_of(done.stdout, done.returncode, done.stderr, schema)

    @staticmethod
    def answer_of(stdout: str, code: int, stderr: str, schema: Mapping[str, Any]
                  ) -> Mapping[str, Any]:
        try:
            data = json.loads(stdout)
        except ValueError:
            data = None
        if not isinstance(data, Mapping):
            detail = (stderr or stdout).strip()[:200] or f"exit code {code}"
            raise DispatchError("answer", f"the answer was not JSON ({detail})")
        if data.get("is_error") or (code != 0 and "structured_output" not in data):
            raise DispatchError("run", str(data.get("result") or stderr.strip()
                                           or f"exit code {code}")[:300])
        answer = data.get("structured_output")
        if not isinstance(answer, Mapping):
            raw = data.get("result")
            try:
                answer = json.loads(raw) if isinstance(raw, str) else None
            except ValueError:
                answer = None
        if not isinstance(answer, Mapping):
            raise DispatchError("answer", "the model gave no structured answer")
        found = schema_check.problems(answer, schema)
        if found:
            raise DispatchError("schema", "; ".join(found[:3]))
        return dict(answer)
