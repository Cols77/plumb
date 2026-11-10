"""SR-111: the repin meaning judges side by side on the agreed labelled set
(``eval --repin --compare``), with fake judges."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from iaso import links
from iaso.api import open_core
from iaso.contracts import NoModel, Target
from iaso.understand import evalrepin, evalrun
from iaso.understand.evalcompare import CompareError, Verdict
from iaso.understand.evalrepin import Case
from iaso.understand.repin import Meaning

pytestmark = pytest.mark.sr("SR-198")

SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""
CODE = "def add(a, b):\n    return a + b\n"
CHANGED = "def add(a, b):\n    return a * b\n"
LINK = "SR-001#0"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by",
                             Target(path="src/calc.py", symbol="add"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    (repo / "src" / "calc.py").write_text(CHANGED, "utf-8")
    return repo


def _case(label: str, n: int = 0) -> Case:
    return Case(item={"id": f"i{n}", "link": f"SR-{n:03d}#0", "label": label},
                requirement="SR: r", link_id=f"SR-{n:03d}#0", link_kind="implemented_by",
                path="a.py", before="x\n", after="y\n", diff="-x\n+y\n")


CASES = [_case("unchanged", 1), _case("unchanged", 2), _case("unchanged", 3),
         _case("changed", 4), _case("changed", 5)]


class Fake:
    def __init__(self, name: str, scores: list[float], scored: bool = True) -> None:
        self.name, self.model, self.scores, self.scored = name, "m1", list(scores), scored

    def judge(self, case: Case) -> Verdict:
        s = self.scores.pop(0)
        return Verdict("unchanged" if s >= 0.5 else "changed", s)


class Inner:
    """A ModelMeaningJudge stand-in: scripted answers, records what it was shown."""

    def __init__(self, answers: list[bool | None]) -> None:
        self.answers, self.shown = list(answers), []

    def same_meaning(self, **shown: Any) -> Meaning:
        self.shown.append(shown)
        return Meaning(self.answers.pop(0), "because", 0.1)


def test_shipped_set_is_the_agreed_labels() -> None:
    items = evalrepin.load_set()
    assert len(items) == 26
    assert sum(i["label"] == "changed" for i in items) == 8
    data = json.loads(evalrepin.DEFAULT_SET.read_text(encoding="utf-8"))
    disputed = {d["link"] for d in data["disputed"]}
    assert len(disputed) == 6 and not disputed & {i["link"] for i in items}
    assert {i["link"] for i in items if i.get("pin") == "HEAD"} == {"SR-026#6", "SR-005#14"}


def test_load_set_rejects_bad_items(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"v": 1, "items": [{"id": "x", "link": "SR-1", "label": "ok"}]}))
    with pytest.raises(CompareError):
        evalrepin.load_set(path)


def test_scoring_counts_false_repins_and_the_safe_threshold() -> None:
    verdicts = [Verdict("unchanged", 0.9), Verdict("unchanged", 0.7),
                Verdict("changed", 0.3), Verdict("unchanged", 0.6), Verdict("changed", 0.1)]
    m = evalrepin.score_judge(CASES, verdicts, scored=True)
    assert m["accuracy"] == 0.6
    assert m["false_repin"] == 0.5 and m["false_repins"] == 1      # SR-004 repinned wrongly
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["threshold"] == 0.7 and m["threshold_recall"] == pytest.approx(2 / 3)
    plain = evalrepin.score_judge(CASES, verdicts, scored=False)
    assert plain["threshold"] is None and plain["threshold_recall"] is None


def test_build_case_rebuilds_what_repin_after_tests_shows(project: Path) -> None:
    core = open_core(project)
    shown = Inner([True])
    links.repin_after_tests(core, LINK, judge=shown, dry_run=True)
    case = evalrepin.build_case(core, {"id": "a", "link": LINK, "label": "changed"})
    assert isinstance(case, Case)
    assert shown.shown == [dict(requirement=case.requirement, link_id=case.link_id,
                                link_kind=case.link_kind, path=case.path,
                                before=case.before, after=case.after, requirement_before="")]
    assert "-    return a + b" in case.diff and "+    return a * b" in case.diff


def test_head_pin_survives_a_working_tree_repin(project: Path) -> None:
    links.repin(open_core(project), LINK)                       # not committed
    core = open_core(project)
    skipped = evalrepin.build_case(core, {"id": "a", "link": LINK, "label": "changed"})
    # skipped, not guessed: the uncommitted pin is kept (SR-166 EX-2), so the diff is empty
    assert skipped == "no change since the pin (repinned since it was labelled?)"
    case = evalrepin.build_case(core, {"id": "a", "link": LINK, "label": "changed",
                                       "pin": "HEAD"})
    assert isinstance(case, Case) and "+    return a * b" in case.diff
    assert evalrepin.build_case(core, {"id": "b", "link": "SR-001#5",
                                       "label": "changed"}) == "SR-001 has no link #5"


def test_sonnet_x3_needs_three_unchanged_and_scores_the_share() -> None:
    inner = Inner([True, False, True])
    judge = evalrepin.MeaningJudge("sonnet-x3", inner, "sonnet", times=3)
    assert judge.scored
    v = judge.judge(_case("changed"))
    assert v.label == "changed" and v.score == pytest.approx(2 / 3) and len(inner.shown) == 3
    once = evalrepin.MeaningJudge("sonnet", Inner([True]), "sonnet")
    assert not once.scored and once.judge(_case("changed")) == Verdict("unchanged", 1.0)


def test_a_model_without_a_verdict_is_an_error_naming_it() -> None:
    judge = evalrepin.MeaningJudge("haiku", Inner([None]), "haiku")
    with pytest.raises(CompareError) as err:
        judge.judge(_case("changed"))
    assert err.value.judge == "haiku"


def test_jev_is_asked_about_the_requirement_with_the_diff() -> None:
    from iaso.judgment import JudgmentUnavailable

    asked = []

    class Backend:
        version, model = "jev-1", "jev"

        def _ask(self, questions, prefix):
            asked.append((questions, prefix))
            return SimpleNamespace(answers={"yes_no": SimpleNamespace(value=0.25)})

    v = evalrepin.JevRepinJudge(Backend()).judge(_case("changed"))
    assert v == Verdict("changed", 0.25)
    ((name, question),), prefix = asked[0]
    assert question.kind == "noul" and question.instructions == evalrepin.JEV_QUESTION
    assert "SR: r" in prefix and "-x\n+y" in prefix

    class Down(Backend):
        def _ask(self, questions, prefix):
            raise JudgmentUnavailable("JEV", "timed out")

    with pytest.raises(CompareError) as err:
        evalrepin.JevRepinJudge(Down()).judge(_case("changed"))
    assert err.value.judge == "jev"


def test_unreachable_or_unknown_judge_is_an_error(repo: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso.understand import dispatch

    def none(core, *, model=None):
        raise NoModel("nothing configured")

    monkeypatch.setattr(dispatch, "configured", none)
    with pytest.raises(CompareError) as err:
        evalrepin.open_judges(open_core(repo), ["sonnet"])
    assert err.value.judge == "sonnet"
    with pytest.raises(CompareError) as err:
        evalrepin.open_judges(open_core(repo), ["gpt"])
    assert err.value.judge == "gpt"


def test_compare_logs_one_eval_run_per_judge_and_names_false_repins(project: Path) -> None:
    path = project / "set.json"
    path.write_text(json.dumps({"v": 1, "items": [
        {"id": "a", "link": LINK, "label": "changed"},
        {"id": "b", "link": "SR-001#7", "label": "unchanged"}]}))
    core = open_core(project)
    text = evalrepin.run_compare(core, [], str(path), judges=[
        Fake("sonnet", [0.0], scored=False), Fake("jev", [0.9])])
    assert "FALSE REPIN" in text and "jev false repins: SR-001#0" in text
    assert "skipped SR-001#7" in text
    runs = [dict(e.payload) for e in open_core(project).events() if e.kind == "eval-run"]
    assert [r["judge"] for r in runs] == ["sonnet", "jev"]
    assert all(r["set"] == "repin" and len(r["cases"]) == 1 for r in runs)
    assert runs[0]["metrics"]["false_repin"] == 0.0 and runs[1]["metrics"]["false_repin"] == 1.0


def test_cli_repin_needs_compare(capsys: pytest.CaptureFixture[str]) -> None:
    assert evalrun.run("eval", ["--repin"]) == 2
    assert "--compare" in capsys.readouterr().err
