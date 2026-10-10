"""SR-105: the judges side by side on the owner-labelled set (``eval --compare``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.understand import evalcompare, evalrun
from plumb.understand.evalcompare import CompareError, Verdict


def _item(n: int, expected: str) -> dict[str, Any]:
    return {"id": f"c{n}", "record_id": f"INT-{n:03d}", "record_hash": "",
            "kind": "intent-readback", "record_text": f"text {n}", "owner_words": f"words {n}",
            "owner_words_digest": "", "context_ids": [], "expected": expected,
            "calibration": "none", "source": "test"}


class Fake:
    def __init__(self, name: str, scores: list[float]) -> None:
        self.name, self.model, self.scores = name, "m1", list(scores)

    def judge(self, item: Any, context: Any) -> Verdict:
        s = self.scores.pop(0)
        return Verdict("supported" if s >= 0.5 else "not-supported", s)


ITEMS = [_item(1, "supported"), _item(2, "supported"), _item(3, "beyond"),
         _item(4, "contradicts")]


def test_scoring_metrics() -> None:
    verdicts = [Verdict("supported", 0.9), Verdict("not-supported", 0.4),
                Verdict("supported", 0.8), Verdict("not-supported", 0.1)]
    m = evalcompare.score_judge(ITEMS, verdicts)
    assert m["accuracy"] == 0.5
    assert m["false_accept"] == 0.5                      # one of two unsupported accepted
    assert m["recall"] == 0.5
    assert m["brier"] == pytest.approx((0.01 + 0.36 + 0.64 + 0.01) / 4)
    assert m["threshold"] == 0.9 and m["threshold_recall"] == 0.5   # above the 0.8 false accept


def test_threshold_none_when_no_supported_beats_the_unsupported() -> None:
    verdicts = [Verdict("supported", 0.6), Verdict("supported", 0.7),
                Verdict("supported", 0.95), Verdict("not-supported", 0.2)]
    m = evalcompare.score_judge(ITEMS, verdicts)
    assert m["threshold"] is None and m["threshold_recall"] == 0.0
    perfect = evalcompare.score_judge(ITEMS, [Verdict("supported", 1.0),
                                              Verdict("supported", 0.9),
                                              Verdict("not-supported", 0.2),
                                              Verdict("not-supported", 0.1)])
    assert perfect["accuracy"] == 1 and perfect["false_accept"] == 0
    assert perfect["threshold"] == 0.9 and perfect["threshold_recall"] == 1.0


def test_load_set_rejects_bad_items(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"v": 1, "items": [{"id": "x", "expected": "maybe"}]}))
    with pytest.raises(CompareError):
        evalcompare.load_set(path)
    assert len(evalcompare.load_set()) >= 6               # the shipped set


def test_compare_logs_one_eval_run_per_judge_and_prints_a_table(repo: Path) -> None:
    path = repo / "set.json"
    path.write_text(json.dumps({"v": 1, "items": ITEMS}))
    core = open_core(repo)
    text = evalcompare.run_compare(
        core, [], str(path), judges=[Fake("haiku", [0.9, 0.4, 0.2, 0.1]),
                                     Fake("jev", [0.99, 0.9, 0.1, 0.3])])
    assert "haiku" in text and "jev" in text and "false-accept" in text
    runs = [dict(e.payload) for e in open_core(repo).events() if e.kind == "eval-run"]
    assert [r["judge"] for r in runs] == ["haiku", "jev"]
    assert all(r["compare"] and len(r["cases"]) == 4 for r in runs)
    assert runs[1]["metrics"]["accuracy"] == 1.0 and runs[0]["metrics"]["accuracy"] == 0.75


def test_unreachable_judge_is_an_error_naming_it_and_logs_nothing(repo: Path) -> None:
    class Down:
        name, model = "jev", "m"

        def judge(self, item: Any, context: Any) -> Verdict:
            raise CompareError("jev", "unreachable (timeout)")

    path = repo / "set.json"
    path.write_text(json.dumps({"v": 1, "items": ITEMS}))
    core = open_core(repo)
    with pytest.raises(CompareError, match="jev"):
        evalcompare.run_compare(core, [], str(path), judges=[Fake("haiku", [0.9] * 4), Down()])
    assert not [e for e in open_core(repo).events() if e.kind == "eval-run"]


def test_no_jev_key_is_an_error_not_the_heuristic(repo: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(CompareError, match="jev"):
        evalcompare.open_judges(open_core(repo), ["jev"])
    assert evalrun.run("eval", ["--compare", "jev", "--root", str(repo)]) == 2


def test_jev_judge_maps_no_to_not_supported() -> None:
    asked: list[str] = []

    class Backend:
        version = "v1"

        def yes_probability(self, q: str, ctx: str, **kw: Any) -> float | None:
            asked.append(ctx)
            return 0.2

    verdict = evalcompare.JevJudge(Backend()).judge(
        _item(1, "supported"), [{"id": "REQ-1", "status": "confirmed", "text": "t"}])
    assert verdict == Verdict("not-supported", 0.2)
    assert "REQ-1" in asked[0] and "words 1" in asked[0]


def test_haiku_judge_confidence_becomes_probability_of_supported() -> None:
    class D:
        name = "d"

        def available(self) -> None:
            return None

        def run(self, job: Any, **_: Any) -> dict[str, Any]:
            rid = job.inputs["records"][0]["id"]
            return {"verdicts": [{"id": rid, "verdict": "beyond", "confidence": 0.8,
                                  "beyond": ["x"], "contradicts": []}]}

    verdict = evalcompare.HaikuJudge(D(), "haiku").judge(_item(1, "beyond"), [])
    assert verdict.label == "beyond" and verdict.score == pytest.approx(0.2)
