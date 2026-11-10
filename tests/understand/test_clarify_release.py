"""A failed check holds nothing (SR-225 EX-9, SR-378 EX-4): iaso says once that the check
could not be made and the agent works on; no "build anyway" card is filed."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt

from iaso.api import open_core
from iaso.understand import cmd_clarify, gate, hooks, worker

pytestmark = pytest.mark.sr("SR-225")

SESSION = "s1"


def _ctx() -> Any:
    return SimpleNamespace(session_id=SESSION)


def test_ex9_a_failed_check_opens_the_gate_and_files_no_card(
        repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.failing("run", "the model could not be reached")
    core = open_core(repo)
    text = "/iaso clarify let users export their data"
    digest = log_prompt(repo, text, session=SESSION)
    hooks.on_prompt(_ctx(), core, {"digest": digest, "text": text})
    assert gate.is_closed(repo, SESSION)                     # closed while the check runs
    worker.run_once(core, SESSION)
    outcome = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
    assert outcome.state == "couldnt_check" and "work on" in outcome.lines[0]
    assert not gate.is_closed(repo, SESSION)                 # the agent works on
    assert [e.payload["by"] for e in open_core(repo).events() if e.kind == "gate"] == [
        "couldnt-check"]
