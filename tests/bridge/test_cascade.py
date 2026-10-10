"""BRIDGE BS1: the cascade-to-LLM hook point and ``plumb judgment status`` (spec 8.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import cli
from plumb.api import open_core
from plumb.contracts import EscalationRequest, Judgment, LLMCascade
from plumb.judgment import get_cascade
from plumb.judgment.cascade import HostAgentCascade, reaches_owner

pytestmark = [pytest.mark.sr("SR-024"), pytest.mark.sr("SR-021")]


def _judgment(tier: str, subject: str = "SR-004") -> Judgment:
    return Judgment(action="intent-change", subject=subject, verdict="change",
                    confidence={"accept": 0.95, "escalate-llm": 0.7,
                                "escalate-human": 0.3}[tier],
                    tier=tier, backend="fake", fingerprint="sha256:" + "0" * 64)  # type: ignore[arg-type]


def _queue(repo: Path) -> list[dict]:
    path = repo / ".plumb" / "session" / "escalations.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_host_agent_cascade_queues_instruction(repo: Path) -> None:
    cascade = get_cascade(open_core(repo))
    assert isinstance(cascade, HostAgentCascade)
    assert isinstance(cascade, LLMCascade)
    cascade.escalate(EscalationRequest(judgment=_judgment("escalate-llm"),
                                       instruction="compare the request with SR-004 EX-1"))
    [row] = _queue(repo)
    assert row["subject"] == "SR-004"
    assert row["instruction"] == "compare the request with SR-004 EX-1"
    assert set(row) == {"at", "subject", "instruction"}
    # an accepted judgment needs no escalation
    cascade.escalate(EscalationRequest(judgment=_judgment("accept"), instruction="x"))
    assert len(_queue(repo)) == 1
    # the instruction stays one line
    cascade.escalate(EscalationRequest(judgment=_judgment("escalate-llm"),
                                       instruction="two\nlines"))
    assert _queue(repo)[-1]["instruction"] == "two lines"


def test_escalate_human_only_with_trigger(repo: Path) -> None:
    low = _judgment("escalate-human")
    assert not reaches_owner(low, None)
    assert not reaches_owner(_judgment("escalate-llm"), "intent-change")
    assert reaches_owner(low, "intent-change")
    assert reaches_owner(low, "regression")
    assert not reaches_owner(low, "stale-link")
    cascade = HostAgentCascade(repo)
    cascade.escalate(EscalationRequest(judgment=low, instruction="check SR-004"))
    cascade.escalate(EscalationRequest(judgment=low, instruction="check SR-004",
                                       packet={"trigger": "intent-change"}))
    first, second = _queue(repo)
    assert "do not ask the owner" in first["instruction"]
    assert "ask the owner" in second["instruction"]
    assert "do not ask" not in second["instruction"]


def test_judgment_status_never_prints_key(repo: Path, capsys, monkeypatch) -> None:
    secret = "ts-secret-key-1234567890"
    monkeypatch.setenv("TYPESAFE_API_KEY", secret)
    assert cli.main(["judgment", "status", "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "backend: none" in out and "judging unavailable" in out
    assert secret not in out
    assert cli.main(["judgment", "status", "--json", "--root", str(repo)]) == 0
    raw = capsys.readouterr().out
    assert secret not in raw
    assert json.loads(raw)["backend"] == "none"
