"""CAPTURE C3: intent-change flags against confirmed examples (sp2 7.1, SR-038)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from plumb.api import open_core
from plumb.capture.flags import flag_line, intent_flags

pytestmark = pytest.mark.sr("SR-038")

FIXTURE = Path(__file__).parent / "fixtures" / "intent_prompts.yaml"
DATA = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def confirmed(repo: Path, write_record):
    from plumb.approvals import approve

    for text in DATA["records"].values():
        write_record(repo, text)
    approve(open_core(repo), sorted(DATA["records"]))
    return open_core(repo)


def flags(core, prompt: str) -> dict[str, str]:
    return {f.record: f.kind for f in intent_flags(core, prompt, sorted(DATA["records"]))}


def test_contradiction_flagged(confirmed) -> None:
    [flag] = intent_flags(confirmed, "make add subtract", ["SR-001"])
    assert (flag.record, flag.kind, flag.example) == ("SR-001", "contradicts", "EX-1")
    assert flag.reason and 0 < flag.confidence < 1
    assert "contradict SR-001 (confirmed), EX-1" in flag_line(flag)


def test_extension_flagged(confirmed) -> None:
    assert flags(confirmed, "add a multiply function next to add") == {"SR-001": "extends"}


def test_benign_mention_not_flagged(confirmed) -> None:
    assert flags(confirmed, "also tidy the add docstring for SR-001") == {}


def test_proposed_record_never_flagged(repo: Path, write_record) -> None:
    for text in DATA["records"].values():
        write_record(repo, text)
    core = open_core(repo)  # nothing approved: every record is proposed
    assert intent_flags(core, "make add subtract", ["SR-001"]) == []


def test_precision_fixture_all_contradictions_no_benign(confirmed) -> None:
    prompts = DATA["prompts"]
    assert len(prompts) >= 30
    counts = {"tp": 0, "fp": 0, "fn": 0}
    missed: list[str] = []
    wrong: list[str] = []
    for item in prompts:
        got = flags(confirmed, item["text"])
        if item["label"] == "benign":
            if got:
                wrong.append(f"{item['text']!r} -> {got}")
            counts["fp"] += len(got)
            continue
        if got.get(item["record"]) == item["label"]:
            counts["tp"] += 1
        else:
            counts["fn"] += 1
            if item["label"] == "contradicts":
                missed.append(f"{item['text']!r} -> {got}")
        counts["fp"] += len(set(got) - {item["record"]})
    flagged = counts["tp"] + counts["fp"]
    precision = counts["tp"] / flagged if flagged else 1.0
    recall = counts["tp"] / (counts["tp"] + counts["fn"])
    print(f"intent flags: {len(prompts)} prompts, precision {precision:.2f}, "
          f"recall {recall:.2f} ({counts})")
    extends = [item for item in prompts if item["label"] == "extends"]
    found = sum(flags(confirmed, item["text"]).get(item["record"]) == "extends"
                for item in extends)
    print(f"extends recall {found / len(extends):.2f}")
    assert found / len(extends) >= 0.8  # a floor for trigger 1's extensions
    assert not missed, "contradictions not flagged: " + "; ".join(missed)
    assert not wrong, "benign prompts flagged: " + "; ".join(wrong)
