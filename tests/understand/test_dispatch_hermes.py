"""SR-104: the Hermes dispatcher asks a delegated, tool-less session (behind HermesDelegate)."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping, Sequence

import pytest

from plumb.contracts import DispatchError, Job
from plumb.understand.dispatch import hermes

pytestmark = pytest.mark.sr("SR-273")

SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
JOB = Job(id="read-0123456789abcdef", kind="read", session="s1", schema="read.v1")
_REAL_ENV = dict(os.environ)    # before the isolation fixtures


class RecordingDelegate:
    def __init__(self, text: str = '{"n": 2}', reason: str | None = None,
                 error: Exception | None = None) -> None:
        self.text, self.reason, self.error = text, reason, error
        self.calls: list[dict] = []

    def available(self) -> str | None:
        return self.reason

    def delegate(self, prompt: str, *, tools: Sequence[str], model: str, timeout_s: float,
                 job_id: str) -> str:
        self.calls.append({"prompt": prompt, "tools": tuple(tools), "model": model,
                           "timeout_s": timeout_s, "job": job_id})
        if self.error is not None:
            raise self.error
        return self.text


def _run(delegate: RecordingDelegate) -> Mapping:
    return hermes.HermesDispatcher(delegate=delegate, model="haiku", timeout_s=30).run(
        JOB, system="You read the owner's answer.", user='{"message": "yes"}', schema=SCHEMA,
        on_step=lambda step: None)


def test_delegate_called_without_tools_with_schema() -> None:
    delegate = RecordingDelegate()
    assert _run(delegate) == {"n": 2}
    (call,) = delegate.calls
    assert call["tools"] == () and call["job"] == JOB.id and call["timeout_s"] == 30
    prompt = call["prompt"]
    assert "You read the owner's answer." in prompt and '{"message": "yes"}' in prompt
    assert json.dumps(SCHEMA, sort_keys=True) in prompt        # the schema travels in the prompt


def test_an_answer_in_a_code_fence_or_with_chatter_is_read() -> None:
    assert _run(RecordingDelegate('```json\n{"n": 5}\n```')) == {"n": 5}
    assert _run(RecordingDelegate('Here you are: {"n": 6} Hope that helps.')) == {"n": 6}


def test_unavailable_is_a_plain_error() -> None:
    delegate = RecordingDelegate(reason="Hermes is not installed here")
    dispatcher = hermes.HermesDispatcher(delegate=delegate, model="haiku", timeout_s=5)
    assert dispatcher.available() == "Hermes is not installed here"
    with pytest.raises(DispatchError) as caught:
        dispatcher.run(JOB, system="s", user="u", schema=SCHEMA, on_step=lambda s: None)
    assert caught.value.step == "start" and delegate.calls == []


def test_a_failing_delegate_and_a_bad_answer_are_errors() -> None:
    with pytest.raises(DispatchError) as caught:
        _run(RecordingDelegate(error=OSError("pipe closed")))
    assert caught.value.step == "run"
    with pytest.raises(DispatchError) as caught:
        _run(RecordingDelegate("no json here"))
    assert caught.value.step == "answer"
    with pytest.raises(DispatchError) as caught:
        _run(RecordingDelegate('{"n": "two"}'))
    assert caught.value.step == "schema"


def test_the_command_line_delegate_runs_one_shot_in_an_empty_directory(
        tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    class Done:
        returncode, stdout, stderr = 0, '{"n": 1}\n', ""

    def fake_run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return Done()

    monkeypatch.setattr(hermes.subprocess, "run", fake_run)
    monkeypatch.setattr(hermes.shutil, "which", lambda name, path=None: "/bin/hermes")
    cli = hermes.HermesCliDelegate(env={"PATH": "x", "PLUMB_WORKER": "secret"})
    assert cli.delegate("the prompt", tools=(), model="haiku", timeout_s=9,
                        job_id="read-1") == '{"n": 1}\n'
    command = seen["command"]
    assert command[0] == "/bin/hermes" and command[1:3] == ["-z", "the prompt"]
    assert "--safe-mode" in command
    assert command[command.index("-t") + 1] == hermes.NARROWEST_TOOLSET
    assert "-m" not in command                      # "haiku" is not a Hermes model name
    assert "PLUMB_WORKER" not in seen["env"] and seen["env"]["PLUMB_JOB"] == "read-1"
    assert seen["timeout"] == 9 and not str(seen["cwd"]).startswith(str(tmp_path))


def test_the_command_line_delegate_is_unavailable_without_hermes(tmp_path) -> None:
    cli = hermes.HermesCliDelegate(env={"PATH": str(tmp_path)})
    assert "Hermes" in (cli.available() or "")


@pytest.mark.dispatch_live
def test_live_hermes_answers_the_schema() -> None:
    if os.environ.get("DISPATCH_LIVE") != "1" or not shutil.which("hermes"):
        pytest.skip("set DISPATCH_LIVE=1 with hermes installed")
    answer = hermes.HermesDispatcher(
        delegate=hermes.HermesCliDelegate(env=_REAL_ENV), model="haiku", timeout_s=120).run(
        JOB, system="Answer with the schema only.", user="n is 3", schema=SCHEMA,
        on_step=lambda step: None)
    assert isinstance(answer["n"], int)
