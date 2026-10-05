"""BRIDGE BS4: precision of the intent-change heuristic on 20 labelled prompts.

The result is recorded in docs/followups.md. The floor guards against a regression of the
heuristic; it is not a claim about real-world precision.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.judgment.heuristic import HeuristicBackend

pytestmark = pytest.mark.sr("SR-010")

FIXTURE = Path(__file__).parent / "fixtures" / "intent_prompts.json"


def measure(repo: Path, write_record) -> dict[str, float]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for text in data["records"].values():
        write_record(repo, text)
    index = open_core(repo).index()
    records = [index[i] for i in sorted(data["records"])]
    backend = HeuristicBackend()
    tp = fp = fn = 0
    for item in data["prompts"]:
        flagged = {j.subject for j in backend.intent_change(item["text"], records)
                   if j.verdict == "change"}
        expected = set(item["change"])
        tp += len(flagged & expected)
        fp += len(flagged - expected)
        fn += len(expected - flagged)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"prompts": len(data["prompts"]), "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 3), "recall": round(recall, 3)}


def test_intent_change_precision_fixture(repo: Path, write_record) -> None:
    result = measure(repo, write_record)
    print(f"intent-change heuristic: {result}")
    assert result["prompts"] == 20
    assert result["precision"] >= 0.6
    assert result["recall"] >= 0.5
