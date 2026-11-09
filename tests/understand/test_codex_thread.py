"""SR-439: a Codex $plumb-intent opens the current thread's loop, never another session's."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt

from plumb.api import open_core
from plumb.stale import SESSION_ENV
from plumb.understand import clarify, cmd_intent, hooks, typed, worker

pytestmark = pytest.mark.sr("SR-439")

THREAD = "01a1bf49-bca0-7973-8a1c-dad67830ff3b"
WORDS = "add multiply next to add"
NO_GAP = {"intent": "yes", "topic": "multiply", "gap": False, "gaps": []}


def test_codex_skill_spelling_is_the_intent_command() -> None:
    assert typed.parse("$plumb-intent " + WORDS) == typed.Typed("intent", words=WORDS)
    assert clarify.commanded_words("$plumb-clarify " + WORDS) == WORDS
    assert typed.parse("$plumb-intents " + WORDS) is None


def test_ex1_the_thread_id_picks_this_threads_request(repo: Path, engine_standins: Any,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SESSION_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD)
    engine_standins.dispatcher.script = {"clarify": NO_GAP}
    text = "$plumb-intent " + WORDS
    digest = log_prompt(repo, text, session=THREAD)
    hooks.on_prompt(SimpleNamespace(session_id=THREAD), open_core(repo),
                    {"digest": digest, "text": text})
    worker.run_once(open_core(repo), THREAD)
    # a later request of another session is the newest prompt in the log
    log_prompt(repo, "/plumb intent something else", session="claude-other",
               at="2999-01-01T00:00:00Z")
    assert cmd_intent.run("intent", ["open", "--wait", "--timeout", "5",
                                     "--root", str(repo)]) == 0
    assert cmd_intent.loop_path(repo, THREAD, digest).exists()
    assert not (repo / ".plumb" / "session" / "claude-other").exists()
