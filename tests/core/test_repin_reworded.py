"""SR-198 EX-12, INT-075: the repin check judges the linked end against the requirement as it
is now. A requirement reworded since the pin is judged with its earlier wording shown, even
when the code did not change; a change that does what the requirement states is kept; the
owner's later decisions on the record supersede the earlier answer; a long diff is judged."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from iaso.api import open_core
from iaso.contracts import Target
from iaso.understand import repin
from iaso.understand.repin import Meaning, ModelMeaningJudge

pytestmark = pytest.mark.sr("SR-198")

SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum{suffix}.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""
CODE = "def add(a, b):\n    return a + b\n"
LINK = "SR-001#0"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR1.format(suffix=""))
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py", symbol="add"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    return repo


class Judge:
    def __init__(self, unchanged: bool, reason: str = "still the sum") -> None:
        self.answer, self.asked = Meaning(unchanged, reason, 0.9), []

    def same_meaning(self, **shown):
        self.asked.append(shown)
        return self.answer


def _state(repo: Path) -> str:
    (state,) = [s for s in open_core(repo).link_states(["SR-001"]) if s.link.id == LINK]
    return state.state


def test_a_reworded_requirement_is_judged_with_its_old_wording_even_if_the_code_stood(
        project: Path, write_record) -> None:
    from iaso.links import repin_after_tests

    sr = project / ".iaso" / "requirements" / "SR-001.md"             # the source moved
    sr.write_text(sr.read_text("utf-8").replace("the sum.", "the sum of its two numbers."),
                  "utf-8")                                              # the links stay
    sonnet = Judge(True)
    result = repin_after_tests(open_core(project), LINK, runner=lambda paths: (True, "ran"),
                               judge=sonnet, jev=None, diagnoser=None, session="s1")
    (shown,) = sonnet.asked
    assert "add returns the sum." in shown["requirement_before"]
    assert "add returns the sum of its two numbers." in shown["requirement"]
    assert shown["before"] == shown["after"]
    assert result.refused == [] and [c["link"] for c in result.changes] == [LINK]
    assert _state(project) == "current"


def test_the_model_is_asked_when_only_the_requirement_changed() -> None:
    """No code change and no rewording is identical and asks no model; a rewording with no
    code change asks the model, with the end as it is and the earlier wording."""

    class Dispatcher:
        name, model = "claude-code", "sonnet"

        def __init__(self) -> None:
            self.seen = []

        def run(self, job, *, system, user, schema, on_step):
            self.seen.append(json.loads(user))
            return {"verdict": "unchanged", "reason": "the sum is still returned",
                    "confidence": 0.9}

    dispatcher = Dispatcher()
    judge = ModelMeaningJudge(dispatcher)
    same = dict(link_id=LINK, link_kind="implemented_by", path="src/calc.py", before=CODE,
                after=CODE)
    assert judge.same_meaning(requirement="SR-001: add returns the sum.", **same).unchanged
    assert dispatcher.seen == []
    meaning = judge.same_meaning(requirement="SR-001: add returns the sum of two numbers.",
                                 requirement_before="add returns the sum.", **same)
    assert meaning.unchanged is True
    (inputs,) = dispatcher.seen
    assert inputs["requirement_before"] == "add returns the sum." and inputs["end"] == CODE
    assert inputs["diff"] == ""


def test_the_question_is_about_the_end_now_and_later_decisions_supersede() -> None:
    prompt = (Path(repin.__file__).parent / "agents" / "repin.md").read_text("utf-8")
    assert "as it is now" in repin.JEV_QUESTION
    assert "supersedes the earlier one" in prompt and "now does what the requirement" in prompt
    assert repin.DIFF_MAX >= 100_000
    text = repin.jev_prompt(requirement="R", link_id=LINK, link_kind="implemented_by",
                            path="src/calc.py", change="", requirement_before="old", end=CODE)
    assert "as it was when the link was pinned" in text and "did not change" in text
