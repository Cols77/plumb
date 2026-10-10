"""SP8 lane STALE, HA5 (SR-111): resolving a stale link: repin after the tests pass and a
model judges the meaning unchanged, or bring it to the owner as a card."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from plumb import links, stale
from plumb.api import open_core
from plumb.cli import main
from plumb.contracts import Target
from plumb.judgment import DisabledBackend, FakeBackend
from plumb.judgment import JudgmentUnavailable, UnavailableBackend

pytestmark = pytest.mark.sr("SR-111")

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


def _backend(verdict: str, confidence: float = 0.95) -> FakeBackend:
    return FakeBackend({("drift-triage", LINK): (verdict, confidence)})


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
                                     backend=_backend("cosmetic"))
    assert [c["link"] for c in result.changes] == [LINK] and result.refused == []
    assert runner.calls == [["src/calc.py"]]
    assert _state(project) == "current"
    (entry,) = [e for e in open_core(project).log_read("events", ["repin"])]
    assert entry.payload["note"] == "tests pass, meaning unchanged"
    assert stale.read_cards(project, "s1") == []          # the owner was not involved


def test_meaning_changed_refused(project: Path) -> None:
    _edit(project, CHANGED)
    result = links.repin_after_tests(open_core(project), LINK, runner=Runner(),
                                     backend=_backend("material"))
    assert result.changes == [] and [r[0] for r in result.refused] == [LINK]
    assert "meaning changed" in result.refused[0][1]
    assert _state(project) == "stale"


def test_failing_tests_refused(project: Path) -> None:
    _edit(project, REFORMATTED)
    result = links.repin_after_tests(open_core(project), LINK, runner=Runner(ok=False),
                                     backend=_backend("cosmetic"))
    assert result.changes == [] and "tests" in result.refused[0][1]
    assert _state(project) == "stale"


@pytest.mark.parametrize("backend", [DisabledBackend(), UnavailableBackend(JudgmentUnavailable("JEV", "timeout")), None])
def test_model_unreachable_refuses_and_repins_nothing(project: Path, backend) -> None:
    _edit(project, REFORMATTED)

    class Broken:
        name = "jev"

        def drift_triage(self, states, texts):
            raise OSError("unreachable")

    result = links.repin_after_tests(open_core(project), LINK, runner=Runner(),
                                     backend=Broken() if backend is None else backend)
    assert result.changes == []
    assert "no model" in result.refused[0][1]
    assert _state(project) == "stale"
    assert not list(open_core(project).log_read("events", ["repin"]))


def test_unlocatable_earlier_version_refused(project: Path) -> None:
    (project / "src" / "later.py").write_text(DEF_F, "utf-8")
    open_core(project).add_link("SR-001", "implemented_by", Target(path="src/later.py"))
    (project / "src" / "later.py").write_text(DEF_F_SPACED, "utf-8")
    result = links.repin_after_tests(open_core(project), "SR-001#1", runner=Runner(),
                                     backend=FakeBackend({("drift-triage", "SR-001#1"):
                                                          ("cosmetic", 0.95)}))
    assert result.changes == [] and "earlier version" in result.refused[0][1]


def test_a_requirement_reworded_is_not_repinned_by_tests(project: Path) -> None:
    path = project / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text("utf-8").replace("add returns the sum.",
                                                    "add returns the total."), "utf-8")
    result = links.repin_after_tests(open_core(project), LINK, runner=Runner(),
                                     backend=_backend("cosmetic"))
    assert result.changes == [] and "requirement itself" in result.refused[0][1]


def test_repin_never_confirms(project: Path) -> None:
    core = open_core(project)
    before = core.status(["SR-001"])["SR-001"].confirmation
    _edit(project, REFORMATTED)
    links.repin_after_tests(open_core(project), LINK, runner=Runner(),
                            backend=_backend("cosmetic"))
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
                 "Keep it|Reword it|Undo the change", "--recommended", "2",
                 "--session", "s1", "--root", str(project)])
    assert code == 0, capsys.readouterr().err
    state = stale.turn_state(open_core(project), "s1", turn_id)
    assert stale.unresolved(open_core(project), "s1", state) == []   # resolved for the hold
    (card,) = stale.read_cards(project, "s1")
    assert card["status"] == "open" and card["recommended"] == 2


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
    assert stale.card_lines(project, "s1") == []
    assert json.loads((project / ".plumb" / "session" / "s1" / "stale_cards.json")
                      .read_text("utf-8"))[0]["status"] == "resolved"
    # the phase C adapter reads it back as a card
    from plumb.understand import cardstore

    stale.add_card(project, "s1", link=LINK, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="the sum changed", options=["a", "b", "c"])
    (card,) = cardstore.load(project, "s1")
    assert card.kind == "stale_link" and card.topic == "Adds numbers"
