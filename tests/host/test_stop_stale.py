"""SP8 lane STALE, HA4 and HA5 (SR-111): the end-of-turn hook holds the turn open while a link
this turn made stale is unresolved, and shows the stale cards the owner has waiting."""

from __future__ import annotations

import io
import json
import re
import subprocess
import time
from pathlib import Path

import pytest
from fakes import FakeVerify

from plumb import stale
from plumb.api import open_core
from plumb.contracts import NodeEvidence, Target
from plumb.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-111")

NODE = "tests/test_a.py::test_a"
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
TURN = "turn-1"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "notes.md").write_text("notes\n", "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    return repo


def start_turn(repo: Path, session: str = "s1", turn_id: str = TURN) -> None:
    """What the prompt hook does at a turn start: the turn file and the stale baseline."""
    path = repo / ".plumb" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5, "turn_id": turn_id,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}), "utf-8")
    stale.write_baseline(open_core(repo), session, turn_id)


def edit(repo: Path, rel: str, text: str, session: str = "s1") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    touched = repo / ".plumb" / "session" / session / "touched.txt"
    with touched.open("a", encoding="utf-8") as handle:
        handle.write(rel + "\n")


def run_stop(repo: Path, hook_input, *, active: bool = False, session: str = "s1",
             verify=None) -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=session, stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=repo, verify=verify,
                     unjudged=None) == 0
    return out.getvalue()


def _block(out: str) -> str | None:
    if not out.strip():
        return None
    data = json.loads(out)
    return data["reason"] if data.get("decision") == "block" else None


def _summary(out: str) -> str:
    return json.loads(out).get("systemMessage", "") if out.strip() else ""


def _verify() -> FakeVerify:
    return FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(NODE, "fresh-pass")})


CHANGED = "def add(a, b):\n    return b + a\n"


def test_ex3_unresolved_link_holds_the_turn_and_names_it(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", CHANGED)
    reason = _block(run_stop(project, hook_input, verify=_verify()))
    assert reason is not None
    assert "SR-001's link to src/calc.py is stale and unresolved (SR-001#0)" in reason
    assert "plumb repin --after-tests" in reason and "Held 1 of 3" in reason


def test_pre_existing_stale_listed_once_not_blocking(project: Path, hook_input) -> None:
    (project / "src" / "calc.py").write_text(CHANGED, "utf-8")   # stale before the turn
    start_turn(project)
    edit(project, "docs/notes.md", "more notes\n")
    out = run_stop(project, hook_input, verify=_verify())
    assert _block(out) is None
    assert "1 links were already stale before this turn" in _summary(out)
    start_turn(project, turn_id="turn-2")
    edit(project, "docs/notes.md", "even more notes\n")
    out = run_stop(project, hook_input, verify=_verify())
    assert _block(out) is None
    assert "already stale" not in _summary(out)


def test_hold_ends_after_max_with_card(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", CHANGED)
    for n in (1, 2, 3):                               # hooks.stale_holds_max defaults to 3
        reason = _block(run_stop(project, hook_input, verify=_verify(), active=n > 1))
        assert reason is not None and f"Held {n} of 3" in reason
    out = run_stop(project, hook_input, verify=_verify(), active=True)
    assert _block(out) is None
    summary = _summary(out)
    assert 'I held the turn open 3 times for "Adds numbers" and then let it go' in summary
    assert 'Something you confirmed may have changed, "Adds numbers"' in summary
    (card,) = stale.read_cards(project, "s1")
    assert card["link"] == "SR-001#0" and card["status"] == "open"


def test_active_flag_still_holds_for_stale_only(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", CHANGED)
    unrun = FakeVerify(nodes=(NODE,))                 # covering tests lack evidence
    reason = _block(run_stop(project, hook_input, verify=unrun, active=True))
    assert reason is not None and "stale and unresolved" in reason
    assert "plumb tests run" not in reason            # the once-only reasons stay once-only


def test_card_counts_as_resolved_for_the_hold(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", CHANGED)
    stale.add_card(project, "s1", link="SR-001#0", record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="the order of the sum changed",
                   options=["Keep it", "Reword it"], turn=1)
    out = run_stop(project, hook_input, verify=_verify())
    assert _block(out) is None


def test_no_baseline_no_hold(project: Path, hook_input) -> None:
    start_turn(project)
    (project / ".plumb" / "session" / "s1" / "stale_baseline.json").unlink()
    edit(project, "src/calc.py", CHANGED)
    assert _block(run_stop(project, hook_input, verify=_verify())) is None


def test_ex5_summary_names_requirement_change_and_resolutions_and_the_card_waits(
        project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", CHANGED)
    stale.add_card(project, "s1", link="SR-001#0", record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="add now sums its arguments in the other order",
                   options=["Keep the wording as it is", "Reword it to match the change",
                            "Undo the change"], recommended=1, turn=1)
    out = run_stop(project, hook_input, verify=_verify())
    assert _block(out) is None                         # the turn may end with the card waiting
    lines = _summary(out).splitlines()
    head = lines.index('Something you confirmed may have changed, "Adds numbers": add now '
                       "sums its arguments in the other order")
    assert lines[head + 1:head + 4] == ["  1. Reword it to match the change",
                                        "  2. Keep the wording as it is",
                                        "  3. Undo the change"]


_BARE_ID = re.compile(r"(?<![\w-])(?:(?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})(?![\w-])")
_INTERNAL = re.compile(r"\b(jobs?|dispatchers?|hash(?:es)?|workers?)\b", re.IGNORECASE)


def test_stale_card_text_passes_both_owner_text_scanners(project: Path) -> None:
    from plumb.present import owner_text
    from plumb.present.owner_text import bare_cli_verbs

    row = stale.Row("SR-001#0", "SR-001", "src/calc.py", "implemented_by", ("a", "b"),
                    ("a", "c"))
    card = stale.default_card(row, "Adds numbers")
    stale.add_card(project, "s1", turn=1, **card)
    text = "\n".join([*stale.card_lines(project, "s1"), owner_text.STALE_HOLD_ENDED.format(
        n=3, title="Adds numbers")])
    assert bare_cli_verbs(text) == []
    assert _BARE_ID.findall(text) == [] and _INTERNAL.findall(text) == []
    assert "Adds numbers" in text


def test_prompt_hook_writes_the_turn_baseline(project: Path, hook_input) -> None:
    from plumb.hosts.claude_code import prompt

    (project / "src" / "calc.py").write_text(CHANGED, "utf-8")      # stale at the turn start
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", session_id="s1", prompt="please tidy up")
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=project) == 0
    turn = json.loads((project / ".plumb" / "session" / "s1" / "turn.json").read_text("utf-8"))
    baseline = json.loads((project / ".plumb" / "session" / "s1"
                           / "stale_baseline.json").read_text("utf-8"))
    assert baseline["turn"] == turn["turn_id"]
    assert list(baseline["links"]) == ["SR-001#0"]
    assert set(baseline["links"]["SR-001#0"]) == {"pin", "now"}
