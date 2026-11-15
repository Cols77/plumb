"""The ``codex`` dispatcher: one ``codex exec`` call per job (report-6fb712c4).

For an owner who works in Codex and has no Claude tokens. The call is non-interactive and
read-only, keeps no session and runs in a new empty temporary directory, never the repository,
so the model sees only the job's inputs (as the Claude Code dispatcher does). Codex has no
system-prompt flag: the system text leads the prompt on stdin. The answer is the last message,
written to a file and checked against the job's schema."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from iaso.contracts import DispatchError, Job
from iaso.understand import schema as schema_check
from iaso.understand.dispatch.claude_code import cli_schema


def strict(schema: Mapping[str, Any]) -> dict[str, Any]:
    """The schema as Codex's structured output takes it: every object closes
    (``additionalProperties: false``) and requires all its properties, so a property the job
    leaves optional may be null instead. ``unnull`` takes those nulls out of the answer.
    shortcut: a free-form object (a schema with no properties) can only come back empty, and
    min/max limits are dropped here (the answer is still checked against the original)."""
    kind = schema.get("type")
    out = {k: v for k, v in schema.items()
           if k in ("type", "enum", "properties", "required", "items", "additionalProperties")}
    if kind == "object" or "properties" in schema:
        needed = set(schema.get("required") or ())
        props: dict[str, Any] = {}
        for name, sub in (schema.get("properties") or {}).items():
            sub = strict(sub)
            if name not in needed:
                if isinstance(sub.get("type"), str):
                    sub["type"] = [sub["type"], "null"]
                if "enum" in sub:
                    sub["enum"] = [*sub["enum"], None]
            props[name] = sub
        out.update(type="object", properties=props, required=list(props),
                   additionalProperties=False)
    elif isinstance(schema.get("items"), Mapping):
        out["items"] = strict(schema["items"])
    return out


def unnull(value: Any, schema: Mapping[str, Any]) -> Any:
    """``value`` without the nulls ``strict`` allowed for properties the schema leaves optional."""
    if isinstance(value, Mapping) and isinstance(schema.get("properties"), Mapping):
        needed = set(schema.get("required") or ())
        return {k: unnull(v, schema["properties"].get(k) or {}) for k, v in value.items()
                if not (v is None and k not in needed)}
    if isinstance(value, list) and isinstance(schema.get("items"), Mapping):
        return [unnull(v, schema["items"]) for v in value]
    return value


class CodexDispatcher:
    name = "codex"

    def __init__(self, *, model: str = "", timeout_s: float = 120,
                 env: Mapping[str, str] | None = None) -> None:
        self.model = model              # empty: the model Codex is set up with
        self.timeout_s = timeout_s
        self._env = dict(os.environ if env is None else env)

    def _binary(self) -> str | None:
        return shutil.which("codex", path=self._env.get("PATH", ""))

    def available(self) -> str | None:
        return None if self._binary() else "the codex command was not found on this machine"

    def command(self, binary: str, workdir: Path) -> list[str]:
        return [binary, "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                "--color", "never", "-C", str(workdir),
                "--output-schema", str(workdir / "schema.json"),
                "-o", str(workdir / "answer.json"),
                *(["-m", self.model] if self.model else []), "-"]

    def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
            on_step: Callable[[str], None]) -> Mapping[str, Any]:
        binary = self._binary()
        if binary is None:
            raise DispatchError("start", self.available() or "codex is not available")
        on_step("asking the model")
        workdir = Path(tempfile.mkdtemp(prefix="iaso-job-"))
        try:
            (workdir / "schema.json").write_text(
                json.dumps(strict(cli_schema(schema)), ensure_ascii=False), encoding="utf-8")
            env = {k: v for k, v in self._env.items() if k != "IASO_WORKER"}
            env["IASO_JOB"] = job.id    # iaso's own hooks exit at once on it
            try:
                done = subprocess.run(self.command(binary, workdir), input=f"{system}\n\n{user}",
                                      capture_output=True, text=True, encoding="utf-8",
                                      cwd=workdir, env=env, timeout=self.timeout_s)
            except subprocess.TimeoutExpired as exc:
                raise DispatchError("timeout",
                                    f"no answer within {self.timeout_s:g} seconds") from exc
            except OSError as exc:
                raise DispatchError("start", f"codex could not be started: {exc}") from exc
            try:
                text = (workdir / "answer.json").read_text(encoding="utf-8")
            except OSError:
                text = ""
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        return self.answer_of(text, done.returncode, done.stderr, schema)

    @staticmethod
    def answer_of(text: str, code: int, stderr: str, schema: Mapping[str, Any]
                  ) -> Mapping[str, Any]:
        try:
            answer = json.loads(text) if text.strip() else None
        except ValueError:
            answer = None
        if not isinstance(answer, Mapping):
            detail = stderr.strip()[-300:] or f"exit code {code}"
            kind = "run" if code != 0 or not text.strip() else "answer"
            raise DispatchError(kind, f"codex gave no structured answer ({detail})")
        answer = unnull(answer, schema)
        found = schema_check.problems(answer, schema)
        if found:
            raise DispatchError("schema", "; ".join(found[:3]))
        return dict(answer)
