"""SR-300 EX-2, EX-3 and SR-220: a decision pinned to a record that was reworded since is a
debug case the repin step handles: no tests to run, the record as pinned and as it is now go to
the meaning cascade; a kept meaning repins, a changed meaning is one owner question through the
question tool (never a card). ``plumb debug`` runs the cases once and says what each did.
Judges are stubbed."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from plumb import stale
from plumb.api import open_core
from plumb.cli import main
from plumb.contracts import Target
from plumb.understand import judge, repin
from plumb.understand.repin import Meaning

pytestmark = pytest.mark.sr("SR-300")

SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum{suffix}.
---
"""
DEC1 = """---
id: DEC-001
title: Does add round its result?
question: Does add round its result?
chosen: 'No: add returns the exact sum'
alternatives:
- Round to two decimals
---
"""
LINK = "DEC-001#0"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    """A decision pinned to SR-001; the pinned version committed."""
    write_record(repo, SR1.format(suffix=""))
    write_record(repo, DEC1)
    open_core(repo).add_link("DEC-001", "decides", Target(record="SR-001"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    return repo


def _reword(repo: Path, write_record, suffix: str) -> None:
    write_record(repo, SR1.format(suffix=suffix))
    assert _state(repo) == "stale"


def _state(repo: Path) -> str:
    (state,) = [s for s in open_core(repo).link_states(["DEC-001"]) if s.link.id == LINK]
    return state.state


class Judge:
    def __init__(self, unchanged: bool | None, reason: str = "wording only") -> None:
        self.answer, self.asked = Meaning(unchanged, reason, 0.9), []

    def same_meaning(self, **shown):
        self.asked.append(shown)
        return self.answer


def _no_tests(paths):
    raise AssertionError(f"no test should run for a record link, got {paths}")


def _resolve(repo: Path, judge_: Judge, **kw):
    from plumb.links import repin_after_tests

    return repin_after_tests(open_core(repo), LINK, runner=_no_tests, judge=judge_,
                             jev=None, diagnoser=None, session="s1", **kw)


def test_ex2_a_reworded_record_under_a_decision_is_repinned_when_the_meaning_kept(
        project: Path, write_record) -> None:
    _reword(project, write_record, " of its two numbers")
    sonnet = Judge(True)
    result = _resolve(project, sonnet)
    (shown,) = sonnet.asked
    assert "add returns the sum." in shown["before"]
    assert "add returns the sum of its two numbers." in shown["after"]
    assert "chosen: No: add returns the exact sum" in shown["requirement"]
    assert [c["link"] for c in result.changes] == [LINK] and result.refused == []
    assert result.changes[0]["tier"] == "sonnet" and _state(project) == "current"


def test_ex3_a_changed_meaning_is_one_owner_question_not_a_card(
        project: Path, write_record) -> None:
    _reword(project, write_record, ", rounded to two decimals")
    result = _resolve(project, Judge(False, "the sum is now rounded"))
    assert result.changes == [] and _state(project) == "stale"
    ((link, why),) = result.refused
    assert link == LINK and "question tool" in why and "the sum is now rounded" in why
    assert stale.read_cards(project, "s1") == []
    (question,) = judge.open_questions(open_core(project), "s1")
    assert {r["id"] for r in question["records"]} == {"SR-001", "DEC-001"}
    assert "Adds numbers" in question["question"] and "exact sum" in question["question"]
    assert "SR-001" not in question["question"] and "#" not in question["question"]
    assert len(question["options"]) == 3 and all(o["description"] for o in question["options"])
    # SR-267: the recommended option first with its reason, each one's consequence, the evidence
    assert question["options"][0]["label"].endswith("(Recommended)")
    assert "Recommended:" in question["options"][0]["description"]
    assert "the sum is now rounded" in question["question"]
    assert "comes from your decision" in question["question"]
    assert "Then: add returns the sum." in question["question"]
    assert "Now: add returns the sum, rounded to two decimals." in question["question"]
    import re
    import time

    assert "judge" not in question["question"].lower()
    assert time.strftime("%Y-") in question["question"]           # the decision's date
    assert not re.search(r"(?<!\w)the (record|agent|rewording|link)(?!\w)",
                         question["question"] + " ".join(o["description"]
                                                         for o in question["options"]))
    assert all("Leaves undone" in o["description"] for o in question["options"])
    # asked again, the same question is not repeated; a dry run asks nothing
    _resolve(project, Judge(False, "the sum is now rounded"))
    _resolve(project, Judge(False, "the sum is now rounded"), dry_run=True)
    assert len(judge.open_questions(open_core(project), "s1")) == 1


def test_pinned_version_not_in_git_is_refused_with_nothing_to_compare(
        repo: Path, write_record) -> None:
    write_record(repo, SR1.format(suffix=""))
    write_record(repo, DEC1)
    open_core(repo).add_link("DEC-001", "decides", Target(record="SR-001"))
    _reword(repo, write_record, " of two numbers")       # the pinned version was never committed
    sonnet = Judge(True)
    ((link, why),) = _resolve(repo, sonnet).refused
    assert link == LINK and "nothing to compare" in why and sonnet.asked == []


def test_a_reworded_decision_is_still_refused(project: Path, write_record) -> None:
    path = project / ".plumb" / "decisions" / "DEC-001.md"   # the links stay
    path.write_text(path.read_text("utf-8").replace("exact sum", "sum as is"), "utf-8")
    ((link, why),) = _resolve(project, Judge(True)).refused
    assert link == LINK and "reworded since the pin" in why


def test_the_turn_end_heal_covers_record_links(project: Path, write_record, monkeypatch) -> None:
    """SR-175's heal runs the same step, so a kept meaning is repinned without the owner."""
    _reword(project, write_record, " of its two numbers")
    monkeypatch.setattr(repin, "open_judge", lambda core: Judge(True))
    monkeypatch.setattr(repin, "open_jev_tier", lambda core: None)
    core = open_core(project)
    said = stale.settle_drift(core, "s1", stale.stale_rows(core, ["DEC-001"]))
    assert said == [] and _state(project) == "current"


def test_plumb_debug_runs_the_cases_and_counts_them(project: Path, write_record, monkeypatch,
                                                    capsys) -> None:
    """SR-220: the debug workflow reruns the step once and says what each case did."""
    from plumb import debug

    _reword(project, write_record, " of its two numbers")
    monkeypatch.setattr(repin, "open_judge", lambda core: Judge(True))
    monkeypatch.setattr(repin, "open_jev_tier", lambda core: None)
    monkeypatch.chdir(project)
    assert main(["debug", "--dry-run"]) == 0            # it would resolve them all
    out = capsys.readouterr().out
    assert "1 cases, 1 resolved, 0 still in debugging" in out and "would resolve" in out
    assert _state(project) == "stale"
    assert main(["debug"]) == 0
    assert "1 cases, 1 resolved" in capsys.readouterr().out and _state(project) == "current"
    assert main(["debug"]) == 0 and "0 cases" in capsys.readouterr().out
    assert debug.cases(open_core(project), ["DEC-999"])[0]["what"] == "no record DEC-999"


DEC2 = """---
id: DEC-002
title: Is the sum rounded?
question: Is the sum rounded?
chosen: 'Yes: add rounds the sum to two decimals'
alternatives:
- Keep the exact sum
---
"""


def test_a_newer_decision_pinned_to_the_reworded_record_is_read_by_the_judge(
        project: Path, write_record) -> None:
    """The owner decided again after the pin (DEC-002 is pinned to SR-001 as reworded): the
    judge reads the rewording next to that answer and the verdict stays the cascade's
    (SR-242); a kept meaning repins without the owner."""
    _reword(project, write_record, ", rounded to two decimals")
    write_record(project, DEC2)
    open_core(project).add_link("DEC-002", "decides", Target(record="SR-001"))
    sonnet = Judge(True, "the rewording applies the later decision")
    result = _resolve(project, sonnet)
    (shown,) = sonnet.asked
    assert "The owner decided later" in shown["requirement"]
    assert "DEC-002: question: Is the sum rounded?" in shown["requirement"]
    assert result.refused == [] and result.changes[0]["tier"] == "sonnet"
    assert _state(project) == "current"
    assert judge.open_questions(open_core(project), "s1") == []


def test_a_rerun_replaces_the_question_and_a_repin_withdraws_it(
        project: Path, write_record) -> None:
    from plumb import links

    _reword(project, write_record, ", rounded to two decimals")
    _resolve(project, Judge(False, "the sum is now rounded"))
    _resolve(project, Judge(False, "add rounds its result"))        # a rerun, read otherwise
    (question,) = judge.open_questions(open_core(project), "s1")
    assert "add rounds its result" in question["question"]
    links.repin(open_core(project), LINK, note="the owner said it still holds")
    assert judge.open_questions(open_core(project), "s1") == []
    assert _state(project) == "current"
