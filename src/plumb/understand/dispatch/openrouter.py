"""The ``openrouter`` dispatcher: a direct chat-completions call with the job's schema as the
response format and no tools. It is used only when ``understand.dispatch`` is ``openrouter``
(never as a silent fallback), with the credential ``judgment/jev.py`` already reads
(``OPENROUTER_API_KEY`` from the environment or the user's env file; never from the repository)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any

from plumb.contracts import DispatchError, Job
from plumb.understand import schema as schema_check

API_KEY_ENV = "OPENROUTER_API_KEY"
DEFAULT_BASE_URL = "https://openrouter.ai"
CHAT_PATH = "/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"


class OpenRouterDispatcher:
    name = "openrouter"

    def __init__(self, *, key: str | None = None, base_url: str | None = None,
                 model: str | None = None, timeout_s: float = 120) -> None:
        self.key = key
        self.base_url = (base_url or os.environ.get("OPENROUTER_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.model = model if model and "/" in model else DEFAULT_MODEL
        self.timeout_s = timeout_s

    @classmethod
    def from_core(cls, core: Any) -> OpenRouterDispatcher:
        from plumb.config import UnderstandConfig
        from plumb.judgment import jev

        settings = core.config.understand if core is not None else UnderstandConfig()
        root = getattr(core, "root", None)
        key = None
        if jev.key_source(root, name=API_KEY_ENV) != "user-store":    # that store is TypeSafe's
            key = jev.resolve_key(root, name=API_KEY_ENV)
        return cls(key=key, model=settings.model, timeout_s=settings.timeout_s)

    def available(self) -> str | None:
        if not self.key:
            return f"no OpenRouter credential was found (set {API_KEY_ENV})"
        return None

    def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
            on_step: Callable[[str], None]) -> Mapping[str, Any]:
        import urllib.error
        import urllib.request

        from plumb import __version__

        reason = self.available()
        if reason:
            raise DispatchError("start", reason)
        on_step("asking the model")
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": f"{job.kind}_answer", "strict": True, "schema": dict(schema)}},
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + CHAT_PATH, data=body, method="POST", headers={
                "Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                "Accept": "application/json", "User-Agent": f"plumb/{__version__}"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise DispatchError("run", f"OpenRouter answered HTTP {exc.code}") from exc
        except TimeoutError as exc:
            raise DispatchError("timeout", f"no answer within {self.timeout_s:g} seconds"
                                ) from exc
        except (urllib.error.URLError, OSError) as exc:
            if "timed out" in str(exc):
                raise DispatchError("timeout", f"no answer within {self.timeout_s:g} seconds"
                                    ) from exc
            raise DispatchError("run", f"OpenRouter could not be reached ({exc})") from exc
        return self.answer_of(raw, schema)

    @staticmethod
    def answer_of(raw: bytes, schema: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            data = json.loads(raw.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise DispatchError("answer", "OpenRouter's reply had no answer in it") from exc
        try:
            answer = json.loads(content) if isinstance(content, str) else content
        except ValueError as exc:
            raise DispatchError("answer", "the answer was not JSON") from exc
        if not isinstance(answer, Mapping):
            raise DispatchError("answer", "the answer was not a JSON object")
        found = schema_check.problems(answer, schema)
        if found:
            raise DispatchError("schema", "; ".join(found[:3]))
        return dict(answer)
