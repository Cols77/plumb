"""SP8 lane STALE, HA5 (SR-111): resolving a stale link: repin after the tests pass and a
model judges the meaning unchanged, or ask the owner with the question tool."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from plumb import links, stale
from plumb.api import open_core
from plumb.cli import main
from plumb.contracts import Target
from plumb.understand import cardcontent
from plumb.understand.repin import Meaning

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
REFORMATTED = "def add(a, b):\n    return a  +  b\n"
CHANGED = "def add(a, b):\n    return a * b\n"
LINK = "SR-001#0"
DEF_F = "def f():" + chr(10) + "    return 1" + chr(10)
DEF_F_SPACED = "def f():" + chr(10) + "    return  1" + chr(10)


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
    return repo


def _edit(repo: Path, text: str) -> None:
    (repo / "src" / "calc.py").write_text(text, "utf-8")


class Judge:
    """A meaning judge with a fixed answer; it records what it was shown."""

    def __init__(self, unchanged: bool | None, reason: str = "only formatting") -> None:
        self.answer, self.asked = Meaning(unchanged, reason, 0.95), []

    def same_meaning(self, **shown):
        self.asked.append(shown)
        return self.answer


def _backend(verdict: str) -> Judge:
    return Judge({"cosmetic": True, "material": False}[verdict])


class Runner:
    def __init__(self, ok: bool = True) -> None:
        self.ok, self.calls = ok, []

    def __call__(self, paths):
        self.calls.append(list(paths))
        return self.ok, "ran" if self.ok else "1 failed"


def _state(repo: Path) -> str:
    (state,) = open_core(repo).link_states(["SR-001"])
    return state.state


def test_ex4_reformat_repinned_without_owner(project: Path) -> None:
    _edit(project, REFORMATTED)
    assert _state(project) == "stale"
    runner = Runner()
    result = links.repin_after_tests(open_core(project), LINK, runner=runner,
                                     judge=_backend("cosmetic"))
    assert [c["link"] for c in result.changes] == [LINK] and result.refused == []
    assert runner.calls == [["src/calc.py"]]
    assert _state(project) == "current"
    (entry,) = [e for e in open_core(project).log_read("events", ["repin"])]
    assert entry.payload["note"].startswith("tests pass, meaning unchanged")
    assert stale.read_cards(project, "s1") == []          # the owner was not involved


def test_meaning_changed_refused(project: Path) -> None:
    _edit(project, CHANGED)
    result = links.repin_after_tests(open_core(project), LINK, runner=Runner(),
                                     judge=_backend("material"))
    assert result.changes == [] and [r[0] for r in result.refused] == [LINK]
    assert "meaning changed" in result.refused[0][1]
    assert _state(project) == "stale"


def test_failing_tests_refused(project: Path) -> None:
    _edit(project, REFORMATTED)
    result = links.repin_after_tests(open_core(project), LINK, runner=Runner(ok=False),
                                     judge=_backend("cosmetic"))
    assert result.changes == [] and "tests" in result.refused[0][1]
    assert _state(project) == "stale"


@pytest.mark.parametrize("judge", ["raises", "no-answer"])
def test_model_unreachable_refuses_and_repins_nothing(project: Path, judge) -> None:
    _edit(project, REFORMATTED)

    class Broken:
        def same_meaning(self, **shown):
            raise OSError("unreachable")

    result = links.repin_after_tests(open_core(project), LINK, runner=Runner(),
                                     judge=Broken() if judge == "raises" else Judge(None))
    assert result.changes == []
    assert "no model" in result.refused[0][1]
    assert _state(project) == "stale"
    assert not list(open_core(project).log_read("events", ["repin"]))


@pytest.mark.sr("SR-198")
def test_pin_on_an_uncommitted_version_is_found_and_repinned(project: Path) -> None:
    """SR-166 EX-2: the pinned uncommitted version is kept in git's object store."""
    (project / "src" / "later.py").write_text(DEF_F, "utf-8")
    open_core(project).add_link("SR-001", "implemented_by", Target(path="src/later.py"))
    (project / "src" / "later.py").write_text(DEF_F_SPACED, "utf-8")
    result = links.repin_after_tests(open_core(project), "SR-001#1", runner=Runner(),
                                     judge=Judge(True))
    assert [c["link"] for c in result.changes] == ["SR-001#1"] and result.refused == []


def test_unlocatable_earlier_version_refused_without_the_blob_map(project: Path) -> None:
    (project / "src" / "later.py").write_text(DEF_F, "utf-8")
    open_core(project).add_link("SR-001", "implemented_by", Target(path="src/later.py"))
    (project / ".git" / "plumb" / "pin_blobs.json").unlink()
    (project / "src" / "later.py").write_text(DEF_F_SPACED, "utf-8")
    result = links.repin_after_tests(open_core(project), "SR-001#1", runner=Runner(),
                                     judge=Judge(True))
    assert result.changes == [] and "earlier version" in result.refused[0][1]


def test_a_requirement_reworded_is_judged_against_its_wording_now(project: Path) -> None:
    """A test run alone cannot settle a reworded requirement: the judge reads the end against
    the wording now, shown the earlier wording, and a kept meaning repins (SR-198 EX-12)."""
    path = project / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text("utf-8").replace("add returns the sum.",
                                                    "add returns the total."), "utf-8")
    judge = _backend("cosmetic")
    result = links.repin_after_tests(open_core(project), LINK, runner=Runner(), judge=judge)
    (shown,) = judge.asked
    assert "add returns the sum." in shown["requirement_before"]
    assert "add returns the total." in shown["requirement"]
    assert [c["link"] for c in result.changes] == [LINK] and result.refused == []


def test_repin_never_confirms(project: Path) -> None:
    core = open_core(project)
    before = core.status(["SR-001"])["SR-001"].confirmation
    _edit(project, REFORMATTED)
    links.repin_after_tests(open_core(project), LINK, runner=Runner(),
                            judge=_backend("cosmetic"))
    after = open_core(project).status(["SR-001"])["SR-001"].confirmation
    assert before == after == "proposed"
    kinds = {e.kind for e in open_core(project).log_read("events")}
    assert not kinds & {"approve", "relay", "confirm"}


def test_cli_after_tests_refuses_without_a_model(project: Path, capsys, monkeypatch) -> None:
    _edit(project, REFORMATTED)
    monkeypatch.setattr(links, "default_runner", lambda core: Runner())
    assert main(["repin", "--after-tests", LINK, "--root", str(project)]) == 1
    assert "no model" in capsys.readouterr().err
    assert _state(project) == "stale"


def test_ex5_owner_question_becomes_card_and_turn_may_end(project: Path, capsys) -> None:
    core = open_core(project)
    turn_id = "t1"
    stale.write_baseline(core, "s1", turn_id)           # the turn starts with nothing stale
    _edit(project, CHANGED)
    state = stale.turn_state(open_core(project), "s1", turn_id)
    assert [r.link for r in stale.unresolved(core, "s1", state)] == [LINK]
    code = main(["stale", "card", LINK, "--topic", "Adds numbers", "--issue",
                 "add now multiplies instead of adding", "--options",
                 "Keep it|Reword it|Undo the change", "--recommended", "3",
                 "--consequences", "keeps the product|says product|sums again",
                 "--why", "the owner asked for a sum",
                 "--session", "s1", "--root", str(project)])
    assert code == 0, capsys.readouterr().err
    state = stale.turn_state(open_core(project), "s1", turn_id)
    assert stale.unresolved(open_core(project), "s1", state) == []   # resolved for the hold
    (card,) = stale.read_cards(project, "s1")
    assert card["status"] == "open" and card["recommended"] == 2


def test_recommended_flag_counts_options_from_one(project: Path, capsys) -> None:
    code = main(["stale", "card", LINK, "--topic", "T", "--issue", "i", "--options",
                 "Keep it|Undo it", "--recommended", "1", "--consequences", "a|b",
                 "--why", "keep", "--session", "s1", "--root", str(project)])
    assert code == 0, capsys.readouterr().err
    (card,) = stale.read_cards(project, "s1")
    assert card["recommended"] == 0          # option 1, "Keep it"


def test_refiled_card_never_binds_recommended_to_an_unseen_order(project: Path,
                                                                  capsys) -> None:
    # eval-0cf3090d: the agent meant "--recommended 1" as keep the change; the kept card's
    # options were in another order, so undo was recommended against its own reason
    stale.add_card(project, "s1", link=LINK, record="SR-001", path="src/calc.py",
                   topic="T", issue="i", options=["Undo the change", "Keep the change"])
    code = main(["stale", "card", LINK, "--consequences", "keeps it|undoes it", "--why",
                 "keep it, as asked", "--recommended", "1", "--session", "s1",
                 "--root", str(project)])
    err = capsys.readouterr().err
    assert code != 0
    assert "1. Undo the change; 2. Keep the change" in err and "--options" in err
    (card,) = stale.read_cards(project, "s1")
    assert "why" not in card and "consequences" not in card    # nothing misrecorded
    code = main(["stale", "card", LINK, "--options", "Keep the change|Undo the change",
                 "--consequences", "keeps it|undoes it", "--why", "keep it, as asked",
                 "--recommended", "1", "--session", "s1", "--root", str(project)])
    assert code == 0, capsys.readouterr().err
    (card,) = stale.read_cards(project, "s1")
    shown = cardcontent.options(card)
    assert shown[0]["text"] == "Keep the change" and shown[0]["recommended"]
    assert shown[0]["consequence"] == "keeps it"


def test_stale_cards_file_format(project: Path) -> None:
    stale.add_card(project, "s1", link=LINK, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="the sum changed", options=["a", "b", "c"],
                   recommended=1, turn=4)
    raw = json.loads((project / ".plumb" / "session" / "s1" / "stale_cards.json")
                     .read_text("utf-8"))
    assert raw == [{"link": LINK, "record": "SR-001", "path": "src/calc.py",
                    "topic": "Adds numbers", "issue": "the sum changed",
                    "options": ["a", "b", "c"], "recommended": 1, "turn": 4,
                    "status": "open"}]
    assert stale.close_card(project, "s1", LINK) is True
    assert json.loads((project / ".plumb" / "session" / "s1" / "stale_cards.json")
                      .read_text("utf-8"))[0]["status"] == "resolved"
    # the phase C adapter reads it back as a card
    from plumb.understand import cardstore

    stale.add_card(project, "s1", link=LINK, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="the sum changed", options=["a", "b", "c"])
    (card,) = cardstore.load(project, "s1")
    assert card.kind == "stale_link" and card.topic == "Adds numbers"


def test_the_judge_is_shown_the_requirement_and_the_link(project: Path) -> None:
    _edit(project, REFORMATTED)
    judge = Judge(True)
    links.repin_after_tests(open_core(project), LINK, runner=Runner(), judge=judge)
    (shown,) = judge.asked
    assert "add returns the sum." in shown["requirement"] and "EX-1" in shown["requirement"]
    assert shown["link_id"] == LINK and shown["link_kind"] == "implemented_by"
    assert shown["path"] == "src/calc.py"
    assert "a + b" in shown["before"] and "a  +  b" in shown["after"]


def test_dry_run_asks_the_model_only(project: Path) -> None:
    _edit(project, REFORMATTED)
    runner = Runner()
    result = links.repin_after_tests(open_core(project), LINK, runner=runner,
                                     judge=Judge(True), dry_run=True)
    assert result.would == [(LINK, "sonnet: only formatting")] and result.changes == []
    assert runner.calls == [] and _state(project) == "stale"


def test_model_judge_sends_the_diff_and_reads_the_verdict() -> None:
    from plumb.understand.repin import ModelMeaningJudge

    class Dispatcher:
        name, model = "claude-code", "sonnet"

        def __init__(self, answer):
            self.answer, self.seen = answer, []

        def run(self, job, *, system, user, schema, on_step):
            self.seen.append(json.loads(user))
            return self.answer

    shown = dict(requirement="SR-001: add returns the sum.", link_id=LINK,
                 link_kind="implemented_by", path="src/calc.py", before=CODE, after=CHANGED)
    changed = Dispatcher({"verdict": "changed", "reason": "add now multiplies",
                          "confidence": 0.9})
    assert ModelMeaningJudge(changed).same_meaning(**shown) == Meaning(
        False, "add now multiplies", 0.9)
    assert "-    return a + b" in changed.seen[0]["diff"]
    # the verdict alone decides: a low self-reported confidence still repins
    unsure = Dispatcher({"verdict": "unchanged", "reason": "r", "confidence": 0.1})
    assert ModelMeaningJudge(unsure).same_meaning(**shown).unchanged is True
    sure = Dispatcher({"verdict": "unchanged", "reason": "r", "confidence": 0.9})
    assert ModelMeaningJudge(sure).same_meaning(**shown).unchanged is True
    bad = Dispatcher({"verdict": "maybe"})
    assert ModelMeaningJudge(bad).same_meaning(**shown).unchanged is None


def test_a_run_stopped_at_the_time_limit_says_so(project: Path, monkeypatch) -> None:
    """A run that names no failed test says why it did not pass, not 'failed: '."""
    from plumb.verify import api as verify_api

    report = verify_api.RunReport(run_id="r1", timed_out=True) \
        if hasattr(verify_api, "RunReport") else None
    if report is None:
        pytest.skip("no RunReport class")

    class Lane:
        def run(self, changed, budget_s=None):
            return report

    monkeypatch.setattr("plumb.verify.open_verify", lambda core: Lane())
    ok, detail = links.default_runner(open_core(project))(["src/a.py"])
    assert not ok and detail == "stopped at the time limit"
