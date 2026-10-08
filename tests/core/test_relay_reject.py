"""SR-096 (DEC-026 A): the agent relays the owner's rejection of a proposed read-back.

``plumb relay <IDs> --reject capture-error|intent-change`` takes the same prompt-log and
quote checks as an approval (the quote must be a whole-word part of a logged prompt and name
the record), logs an append-only ``rejection`` event pinning the record's current hash and
the reason, and leaves the record proposed. A reason the owner's words do not give is an
intent change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import approvals
from plumb.api import open_core
from plumb.cli import main

pytestmark = pytest.mark.sr("SR-096")

MISREAD = "INT-016: that records your solution, not what I asked"
CHANGED = "INT-013: no. I don't know what to do with pi-agent-factory just yet"


def _record(record_id: str, title: str, quote: str) -> str:
    return f"---\nid: {record_id}\ntitle: {title}\nquote: {quote}\n---\n"


@pytest.fixture
def project(repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    write_record(repo, _record("INT-013", "Agents are registered", "register agents"))
    write_record(repo, _record("INT-016", "Spend is capped", "cap the spend"))
    return repo


def _log(root: Path, text: str, via: str = "hook") -> str:
    digest = approvals.prompt_digest(text)
    prompts = root / ".plumb" / "session" / "prompts.jsonl"
    prompts.parent.mkdir(parents=True, exist_ok=True)
    with prompts.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"digest": digest, "session": "s1",
                                 "at": "2026-10-06T03:00:00Z", "text": text,
                                 "via": via}) + "\n")
    return digest


def _rejections(root: Path) -> list:
    return list(open_core(root).log_read("events", ["rejection"]))


def test_ex1_capture_error_is_logged_at_the_current_hash(project: Path) -> None:
    core = open_core(project)
    pinned = core.index()["INT-016"].hash
    approvals.relay(core, ["INT-016"], prompt=_log(project, MISREAD), quote=MISREAD,
                    reject="capture-error")
    [entry] = _rejections(project)
    assert entry.payload["reason"] == "capture-error"
    assert entry.payload["records"][0]["id"] == "INT-016"
    assert entry.payload["records"][0]["hash"] == pinned
    assert entry.payload["by"] == "agent-relayed"
    assert open_core(project).status(["INT-016"])["INT-016"].confirmation == "proposed"


def test_ex2_intent_change_is_logged_as_such(project: Path) -> None:
    approvals.relay(open_core(project), ["INT-013"], prompt=_log(project, CHANGED),
                    quote="INT-013: no", reject="intent-change")
    [entry] = _rejections(project)
    assert entry.payload["reason"] == "intent-change"
    assert open_core(project).status(["INT-013"])["INT-013"].confirmation == "proposed"


def test_ex3_a_reason_the_words_do_not_give_is_an_intent_change(project: Path) -> None:
    approvals.relay(open_core(project), ["INT-013"], prompt=_log(project, "INT-013: no"),
                    quote="INT-013: no", reject="unknown")
    [entry] = _rejections(project)
    assert entry.payload["reason"] == "intent-change"


def test_ex4_words_no_logged_prompt_holds_are_refused(project: Path) -> None:
    _log(project, "something else entirely")
    with pytest.raises(approvals.Refused):
        approvals.relay(open_core(project), ["INT-013"],
                        prompt=approvals.prompt_digest("INT-013: no"), quote="INT-013: no",
                        reject="capture-error")
    assert _rejections(project) == []


def test_ex4_quote_not_in_the_logged_prompt_is_refused(project: Path) -> None:
    digest = _log(project, "INT-013: yes")
    with pytest.raises(approvals.Refused):
        approvals.relay(open_core(project), ["INT-013"], prompt=digest,
                        quote="INT-013: no", reject="capture-error")
    assert _rejections(project) == []


def test_quote_must_name_the_record(project: Path) -> None:
    digest = _log(project, "INT-013: no. INT-016: yes")
    with pytest.raises(approvals.Refused):
        approvals.relay(open_core(project), ["INT-016"], prompt=digest, quote="no",
                        reject="capture-error")
    assert _rejections(project) == []


def test_a_confirmed_record_is_not_rejected(project: Path, monkeypatch) -> None:
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    approvals.approve(open_core(project), ["INT-013"])
    with pytest.raises(approvals.ApprovalError):
        approvals.relay(open_core(project), ["INT-013"], prompt=_log(project, "INT-013: no"),
                        quote="INT-013: no", reject="capture-error")


def test_a_rejection_takes_no_revoke_or_exempt(project: Path) -> None:
    digest = _log(project, "INT-013: no")
    with pytest.raises(approvals.ApprovalError):
        approvals.relay(open_core(project), ["INT-013"], prompt=digest,
                        quote="INT-013: no", reject="capture-error", revoke=True)


def test_cli_flag_logs_the_rejection(project: Path, capsys) -> None:
    digest = _log(project, MISREAD)
    code = main(["relay", "INT-016", "--reject", "capture-error", "--prompt", digest,
                 "--quote", MISREAD, "--root", str(project)])
    assert code == 0
    assert "rejected INT-016" in capsys.readouterr().out
    [entry] = _rejections(project)
    assert entry.payload["reason"] == "capture-error"
