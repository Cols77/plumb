"""R13 Q4: a confirmation resting on a message the agent recorded itself is labelled
"self-recorded message" (SR-069). The prose relay that wrote the flag no longer exists
(SR-101 EX-9); the entries it wrote stay in the log, and the tests write one by hand."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import log_prompt, record_text, run, write_stated
from logutil import legacy_relay

from plumb.api import open_core
from plumb.capture.confirmations import confirmation_counts, confirmation_label

pytestmark = pytest.mark.sr("SR-208")


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "session-1")
    write_record(repo, record_text("SR-001", "add returns the sum", statement="add sums"))
    write_record(repo, record_text("SR-002", "sub returns the difference",
                                   statement="sub subtracts"))
    index = open_core(repo).index()
    write_stated(repo, [("SR-001", index["SR-001"].hash), ("SR-002", index["SR-002"].hash)])
    return repo


def test_self_recorded_message_is_labelled(project: Path, capsys) -> None:
    digest = log_prompt(project, "ok for both", via=None)  # no prompt hook recorded it
    legacy_relay(project, ["SR-001"], digest, "ok", self_recorded=True)
    core = open_core(project)
    [entry] = list(core.log_read("events", ["approval"]))
    assert entry.payload["self_recorded"] is True
    assert core.status(["SR-001"])["SR-001"].confirmation == "confirmed"
    assert confirmation_label(core, "SR-001") == "confirmed by you (relayed), " \
                                                 "self-recorded message"
    assert confirmation_counts(core)["self-recorded"] == 1
    assert run(project, "show", "SR-001") == 0
    out = capsys.readouterr().out
    assert "(requirement, confirmed by you (relayed), self-recorded message)" in out


def test_hook_recorded_prompt_carries_no_label(project: Path) -> None:
    digest = log_prompt(project, "ok for both")  # via: hook, as the prompt hook logs it
    legacy_relay(project, ["SR-002"], digest, "ok")
    core = open_core(project)
    [entry] = list(core.log_read("events", ["approval"]))
    assert entry.payload["self_recorded"] is False
    assert confirmation_label(core, "SR-002") == "confirmed by you (relayed)"
    assert confirmation_counts(core)["self-recorded"] == 0


def test_prompt_hook_marks_its_entries(tmp_path: Path) -> None:
    import json

    from plumb.hosts.claude_code.hookio import Deadline, HookContext
    from plumb.hosts.claude_code.prompt import log_prompt as hook_log

    root = tmp_path / "r"
    (root / ".plumb" / "session").mkdir(parents=True)
    ctx = HookContext(name="prompt", data={}, root=root, session_id="s",
                      deadline=Deadline(5.0))
    hook_log(ctx, "hello")
    line = (root / ".plumb" / "session" / "prompts.jsonl").read_text(encoding="utf-8")
    assert json.loads(line)["via"] == "hook"
