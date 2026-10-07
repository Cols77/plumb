"""R17: intent conflicts caught at capture and read-back time, before any work (SR-081)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from awareness.scenario import capture, change, new_requirement, setup
from plumb.api import open_core
from plumb.awareness import inflight
from plumb.contracts import Judgment

pytestmark = pytest.mark.sr("SR-081")


class Judge:
    """A judgment backend whose compatibility verdict the test sets."""

    name = "jev"

    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, str]] = []

    def contradiction(self, prompt: str, record: Any) -> Judgment:
        self.calls.append((prompt, record.id))
        return Judgment(action="contradiction", subject=record.id, verdict=self.verdict,
                        confidence=0.9, tier="act", backend="jev", fingerprint="f")


def _decisions(root: Path) -> list[Any]:
    return [r for r in open_core(root).index().values() if r.kind == "decision"]


def test_same_record_conflict_card_and_one_decision(tmp_path: Path) -> None:
    """SR-081 EX-1: deterministic, no judgment needed."""
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    result = change(main, "A relay pins only the records the owner's words affirm.")
    text = "\n".join(result.lines)
    assert '▸ Conflict  SR-005 "relay checks"' in text
    assert "feat-x      A relay pins the stated group, named by its title." in text
    assert "this work   A relay pins only the records the owner's words affirm." in text
    assert "the same requirement is being changed on both branches" in text
    assert 'Say: "keep feat-x\'s", "keep this one", or "both"' in text
    decisions = _decisions(main)
    assert len(decisions) == 1
    dec = decisions[0]
    assert dec.fields["matters"] is True
    assert dec.fields["question"].startswith('Branch feat-x says "A relay pins the stated group')
    assert dec.fields["question"].endswith(": which one, or both?")
    assert {(link.kind, link.target.record) for link in dec.links} >= {("decides", "SR-005"),
                                                                       ("derives_from",
                                                                        "INT-001")}
    assert dec.id in result.written
    mine = [c for c in inflight.read(main, allow_git=True)[1]["claims"]
            if c["branch"] == "main"]
    assert mine[0]["conflicts"][0]["dec"] == dec.id
    assert mine[0]["conflicts"][0]["branch"] == "feat-x"


def test_feature_overlap_judged_contradictory_is_a_conflict(tmp_path: Path) -> None:
    """SR-081 EX-2: new intent in the same feature, judged contradictory."""
    main, other = setup(tmp_path)
    new_requirement(other, "relay groups", "A relay confirms a group named by its title.")
    judge = Judge("contradicts")
    result = new_requirement(main, "relay single", "A relay confirms one record at a time.",
                             backend=judge)
    assert judge.calls and judge.calls[0][0] == "A relay confirms a group named by its title."
    text = "\n".join(result.lines)
    assert "▸ Conflict" in text and "likely not (JEV, 0.90)" in text
    assert len(_decisions(main)) == 1


def test_feature_overlap_judged_compatible_is_one_line(tmp_path: Path) -> None:
    """SR-081 EX-3: compatible: one warning line, no decision."""
    main, other = setup(tmp_path)
    new_requirement(other, "relay groups", "A relay confirms a group named by its title.")
    result = new_requirement(main, "status colours", "The card is green when aligned.",
                             backend=Judge("benign"))
    warnings = [line for line in result.lines if "judged compatible" in line]
    assert len(warnings) == 1 and "feat-x" in warnings[0]
    assert not any("Conflict" in line for line in result.lines)
    assert _decisions(main) == []


def test_heuristic_fallback_without_jev(tmp_path: Path) -> None:
    """Without JEV the heuristic judges; the capture never fails for it."""
    main, other = setup(tmp_path)
    new_requirement(other, "relay groups", "A relay confirms a group named by its title.")
    result = new_requirement(main, "status colours", "The card is green when aligned.")
    assert any("feat-x" in line for line in result.lines)


def test_conflict_raised_once_for_both_branches(tmp_path: Path) -> None:
    """SR-081 EX-4: the other branch already raised it: no second decision; the line names
    that branch, then the owner's answer once given."""
    main, other = setup(tmp_path)
    change(main, "main's version of the relay")
    change(other, "feat-x's version of the relay")              # feat-x raises the DEC
    [dec] = _decisions(other)
    result = change(main, "main's version again, reworded")
    assert _decisions(main) == []
    known = [line for line in result.lines if "asked on branch feat-x" in line]
    assert known == ['plumb: SR-005 "relay checks": the owner is asked on branch feat-x '
                     "whether this work or that branch's holds; build on the answer"]
    from plumb import approvals

    approvals.approve(open_core(other), [dec.id])           # the owner answers on feat-x
    assert inflight.sync_decisions(open_core(other)) is True
    assert inflight.sync_decisions(open_core(other)) is False  # nothing new to carry
    result = change(main, "main's version, third wording")
    settled = [line for line in result.lines if "settled it on branch feat-x" in line]
    assert settled == ['plumb: SR-005 "relay checks": the owner settled it on branch feat-x: '
                       "\"this request's version\"; build on that"]


def test_clarify_shows_the_card_before_anything_is_written(tmp_path: Path) -> None:
    """SR-081 EX-5: the read-back check, nothing written."""
    from plumb.capture.clarify import clarify, view_lines

    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    before = sorted(p.name for p in (main / ".plumb").rglob("*.md"))
    view = clarify(open_core(main), "make SR-005 pin only the affirmed records")
    lines = view_lines(view)
    assert lines[0].startswith('▸ Conflict  SR-005 "relay checks"')
    assert "  feat-x      A relay pins the stated group, named by its title." in lines
    assert "ask this conflict first, before any other question or any work" in lines
    assert sorted(p.name for p in (main / ".plumb").rglob("*.md")) == before
    assert inflight.read(main, allow_git=True)[1]["claims"][0]["branch"] == "feat-x"


def test_dry_run_checks_and_records_nothing(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    result = change(main, "main's version", dry_run=True)
    assert any(line.startswith("▸ Conflict") for line in result.lines)
    assert "plumb: nothing recorded (a preview)" in result.lines
    assert _decisions(main) == []
    assert [c["branch"] for c in inflight.read(main, allow_git=True)[1]["claims"]] == [
        "feat-x"]


def test_own_branch_claims_never_conflict(tmp_path: Path) -> None:
    main, _other = setup(tmp_path)
    change(main, "first wording")
    result = change(main, "second wording")
    assert not any("Conflict" in line for line in result.lines)
    assert _decisions(main) == []


def test_capture_never_fails_on_an_inflight_error(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    main, _other = setup(tmp_path)

    def broken(*a: object, **k: object) -> None:
        raise RuntimeError("register unreadable")

    from plumb.awareness import early

    monkeypatch.setattr(early, "after_capture", broken)
    result = capture(main, {"intent": "INT-001",
                            "updates": [{"id": "SR-005", "statement": "still written"}]})
    assert "SR-005" in result.updated
    assert any("not checked" in line for line in result.lines)


def test_same_version_on_both_branches_asks_nothing(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group.")
    result = change(main, "A relay pins the stated group.")
    assert not any("Conflict" in line for line in result.lines)
    assert _decisions(main) == []
