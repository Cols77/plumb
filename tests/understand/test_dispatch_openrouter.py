"""SR-104: the OpenRouter dispatcher is a direct call, configured only, never a fallback."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from plumb.api import Core
from plumb.contracts import DispatchError, Job
from plumb.understand import dispatch, jobs, queue, worker
from plumb.understand.dispatch import openrouter
from understand.fakes import FakeKind, fake_claude, fake_kinds

pytestmark = pytest.mark.sr("SR-104")

SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
JOB = Job(id="read-0123456789abcdef", kind="read", session="s1", schema="read.v1")
_REAL_ENV = dict(os.environ)    # before the isolation fixtures


class _Server:
    def __init__(self, reply: dict | None = None, status: int = 200) -> None:
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append({"path": self.path, "body": body,
                                       "auth": self.headers.get("Authorization")})
                payload = json.dumps(reply if reply is not None else {
                    "choices": [{"message": {"content": json.dumps({"n": 4})}}]}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.http = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)

    def __enter__(self) -> _Server:
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.http.shutdown()
        self.http.server_close()


def test_posts_schema_and_reads_answer() -> None:
    with _Server() as server:
        dispatcher = openrouter.OpenRouterDispatcher(
            key="sk-or-test", base_url=server.url, model="vendor/small-model", timeout_s=10)
        assert dispatcher.available() is None
        answer = dispatcher.run(JOB, system="You read.", user='{"message": "yes"}',
                                schema=SCHEMA, on_step=lambda step: None)
    assert answer == {"n": 4}
    (request,) = server.requests
    assert request["path"] == "/api/v1/chat/completions"
    assert request["auth"] == "Bearer sk-or-test"
    body = request["body"]
    assert body["model"] == "vendor/small-model"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][0]["content"] == "You read."
    assert body["messages"][1]["content"] == '{"message": "yes"}'
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert "tools" not in body


def test_errors_name_the_step() -> None:
    with _Server(status=500, reply={"error": {"message": "boom"}}) as server:
        dispatcher = openrouter.OpenRouterDispatcher(
            key="k", base_url=server.url, model="v/m", timeout_s=10)
        with pytest.raises(DispatchError) as caught:
            dispatcher.run(JOB, system="s", user="u", schema=SCHEMA, on_step=lambda s: None)
        assert caught.value.step == "run" and "500" in caught.value.message
    with _Server(reply={"choices": [{"message": {"content": "{\"n\": \"x\"}"}}]}) as server:
        dispatcher = openrouter.OpenRouterDispatcher(
            key="k", base_url=server.url, model="v/m", timeout_s=10)
        with pytest.raises(DispatchError) as caught:
            dispatcher.run(JOB, system="s", user="u", schema=SCHEMA, on_step=lambda s: None)
        assert caught.value.step == "schema"
    with _Server(reply={"unexpected": True}) as server:
        dispatcher = openrouter.OpenRouterDispatcher(
            key="k", base_url=server.url, model="v/m", timeout_s=10)
        with pytest.raises(DispatchError) as caught:
            dispatcher.run(JOB, system="s", user="u", schema=SCHEMA, on_step=lambda s: None)
        assert caught.value.step == "answer"
    unreachable = openrouter.OpenRouterDispatcher(
        key="k", base_url="http://127.0.0.1:9", model="v/m", timeout_s=2)
    with pytest.raises(DispatchError) as caught:
        unreachable.run(JOB, system="s", user="u", schema=SCHEMA, on_step=lambda s: None)
    assert caught.value.step in ("run", "timeout")


def test_not_configured_is_an_error_not_a_fallback(
        repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No credential: the job fails at the dispatch step; Claude is not tried instead."""
    claude = fake_claude(tmp_path / "bin", json.dumps(
        {"type": "result", "is_error": False, "structured_output": {"n": 1}}))
    monkeypatch.setenv("PATH", claude.env()["PATH"])
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))     # we are "under Claude Code"
    (repo / ".plumb" / "config.yaml").write_text("understand:\n  dispatch: openrouter\n",
                                                 encoding="utf-8")
    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    core = Core(repo)
    chosen = dispatch.configured(core)
    assert chosen.name == "openrouter" and "OPENROUTER_API_KEY" in (chosen.available() or "")
    job = jobs.new_job("a", "s1", "a.v1", {"n": 1})
    queue.enqueue(core, job)
    worker.run_once(core, "s1")
    result = jobs.result(repo, "s1", job.id)
    assert result.status == "error" and result.error.step == "dispatch"
    assert claude.calls() == []


def test_the_key_comes_from_the_credential_plumb_already_reads(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-from-env")
    (repo / ".plumb" / "config.yaml").write_text("understand:\n  dispatch: openrouter\n",
                                                 encoding="utf-8")
    chosen = dispatch.configured(Core(repo))
    assert chosen.available() is None and chosen.key == "sk-or-from-env"


@pytest.mark.dispatch_live
def test_live_openrouter_answers_the_schema() -> None:
    key = _REAL_ENV.get("OPENROUTER_API_KEY")
    if os.environ.get("DISPATCH_LIVE") != "1" or not key:
        pytest.skip("set DISPATCH_LIVE=1 with OPENROUTER_API_KEY")
    answer = openrouter.OpenRouterDispatcher(key=key, timeout_s=90).run(
        JOB, system="Answer with the schema only.", user="n is 3", schema=SCHEMA,
        on_step=lambda step: None)
    assert isinstance(answer["n"], int)
