"""SP7 slice 3: cards only at the end of a turn (SR-012, SR-113 EX-2, SR-116; sp7-realign-sp8
C1, C7, C8). The stop hook's owner text is what the owner's words confirmed, then every card in
full; never a list of proposed records, never a status card."""

from __future__ import annotations

import io
import json
import subprocess
import time
from pathlib import Path

import pytest
from fakes import FakeVerify

from plumb import stale
from plumb.api import open_core
from plumb.contracts import NodeEvidence, Target
from plumb.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-265")

SESSION = "s1"
NODE = "tests/test_a.py::test_a"
QUOTE = "the calculator adds"
PROMPT = "please make sure the calculator adds two numbers, nothing fancy"
PROMPT_DIGEST = "sha256:" + "c5" * 32
INT1 = f"""---
id: INT-001
title: Arithmetic helpers
quote: "{QUOTE}"
readback: The calculator adds two numbers.
prompt: {PROMPT_DIGEST[7:23]}
---
"""
FEAT1 = """---
id: FEAT-001
title: Merge check
---
"""
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


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _log_prompt(repo: Path, text: str = PROMPT, digest: str = PROMPT_DIGEST,
                at: str = "2026-10-01T10:00:00Z") -> None:
    prompts = Path(open_core(repo).paths.prompts)
    prompts.parent.mkdir(parents=True, exist_ok=True)
    with prompts.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"digest": digest, "session": SESSION, "at": at, "text": text,
                              "via": "hook"}) + "\n")


@pytest.fixture
def project(repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(repo)
    write_record(repo, INT1)
    write_record(repo, FEAT1)
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    core.add_link("SR-001", "verified_by", Target(test=NODE))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    _log_prompt(repo)
    return repo


def start_turn(repo: Path) -> None:
    path = repo / ".plumb" / "session" / SESSION / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}), "utf-8")


def edit(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    with (repo / ".plumb" / "session" / SESSION / "touched.txt").open("a",
                                                                       encoding="utf-8") as f:
        f.write(rel + "\n")


def run_stop(repo: Path, hook_input, *, verify=None, active: bool = False) -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=SESSION, stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=repo,
                     verify=verify if verify is not None else FakeVerify(), unjudged=None) == 0
    return out.getvalue()


def owner(out: str) -> str:
    data = json.loads(out) if out.strip() else {}
    assert data.get("decision") != "block", data
    return data.get("systemMessage", "")


def no_list_summary(text: str) -> None:
    """SR-012: no list-style alignment summary, no status card, no summary lines."""
    for banned in ("▸", 'say "ok" to confirm', "plumb: touched", "questions:", "plumb ✓",
                   "plumb ✗", "plumb show"):
        assert banned not in text, banned


def owner_level(text: str) -> list[str]:
    from understand.fakes import owner_level as scan

    return scan(text)


# --------------------------------------------------------------------------- SR-012


def test_ex2_a_regression_is_a_card_naming_the_test_and_what_it_checks(project: Path,
                                                                       hook_input) -> None:
    """EX-2: a test that passed with recorded evidence now fails: a regression card naming
    the test, what it checks, the change, and the suggested resolutions."""
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return a * b\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(
        NODE, "fresh-fail", regression=True, last_run="run-2")})
    first = json.loads(run_stop(project, hook_input, verify=verify))
    assert first["decision"] == "block"            # the agent is told first (trigger 3)
    text = owner(run_stop(project, hook_input, verify=verify, active=True))
    lines = text.splitlines()
    assert lines[0] == "Adds numbers"
    assert lines[1] == 'a test that passed before now fails: "Adds numbers"'
    assert f"{NODE} passed in an earlier run and fails now (last run run-2)" in lines
    assert any(line.startswith("  1. Fix the code so it passes again (recommended)")
               for line in lines)
    assert any(line.startswith("  2. The test is wrong now") for line in lines)
    assert any(line.startswith("  3. Leave it failing for now") for line in lines)
    no_list_summary(text)
    # the card stays open: the next turn end draws it again while the test still fails
    start_turn(project)
    edit(project, "docs/notes.md", "notes\n")
    again = owner(run_stop(project, hook_input, verify=FakeVerify()))
    assert again.startswith("Adds numbers")


DEC1 = """---
id: DEC-001
title: Whole numbers only
chosen: whole numbers only
alternatives:
- decimals too
matters: true
---
"""



def test_ex5_nothing_for_the_owner_shows_nothing(project: Path, hook_input) -> None:
    """EX-5: nothing needs the owner and nothing settled: the hook shows the owner nothing."""
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(NODE, "fresh-pass")})
    assert run_stop(project, hook_input, verify=verify) == ""


# --------------------------------------------------------------------------- SR-113 EX-2

INT8 = """---
id: INT-008
title: Cards only at the end of a turn
quote: no list-style summary at the end of a turn, cards only
readback: The end of a turn shows cards only.
---
"""
SR12 = """---
id: SR-012
title: End-of-turn cards
statement: the end-of-turn hook prints no list-style summary of proposed records.
examples:
- id: EX-1
  given: a turn proposed a record
  when: the turn ends
  then: no list-style line names it
---
"""
STOP_CODE = "def summary():\n    return []\n"
STOP_LIST = "def summary():\n    return ['- SR-030 proposed, say ok to confirm']\n"
REQUEST = "add a short list of the proposed records at the end of each turn"


@pytest.mark.sr("SR-198")
def test_sr113_ex2_code_that_drifted_from_an_agreed_intent_is_a_drift_card(
        repo: Path, write_record, hook_input, monkeypatch) -> None:
    """SR-113 EX-2: INT-008 and SR-012 agree, and a turn the owner asked for adds a list-style
    summary to the end-of-turn hook: the owner gets a card naming the intent, the
    requirement, the change and the request behind it, with keep-and-reword or undo."""
    monkeypatch.chdir(repo)
    write_record(repo, INT8)
    write_record(repo, SR12)
    (repo / "src").mkdir()
    (repo / "src" / "stophook.py").write_text(STOP_CODE, "utf-8")
    core = open_core(repo)
    core.add_link("SR-012", "derives_from", Target(record="INT-008"))
    core.add_link("SR-012", "implemented_by", Target(path="src/stophook.py"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    _log_prompt(repo, REQUEST, "sha256:" + "d1" * 32, "2026-10-01T09:00:00Z")
    start_turn(repo)
    edit(repo, "src/stophook.py", STOP_LIST)
    link = next(f"SR-012#{n}" for n, item in enumerate(open_core(repo).index()["SR-012"].links)
                if item.kind == "implemented_by")
    stale.add_card(repo, SESSION, link=link, record="SR-012", path="src/stophook.py",
                   topic="End-of-turn cards",
                   issue="the end of a turn now lists the proposed records",
                   options=["Keep the change and reword the requirement", "Undo the change"],
                   recommended=1, by="diagnosis",
                   consequences=["the list stays and the requirement says so; cards-only is "
                                 "dropped", "the list goes; the turn's request is not done"],
                   why="your intent says cards only, and the requirement still agrees with it")
    text = owner(run_stop(repo, hook_input))
    lines = text.splitlines()
    assert lines[:2] == ["End-of-turn cards", "the end of a turn now lists the proposed records"]
    assert f'the request behind the change: "{REQUEST}"' in lines[3]
    assert "  1. Undo the change (recommended) - the list goes; the turn's request is not done" in (
        lines)
    assert lines[2] == ("your intent says cards only, and the requirement still agrees with it")



# --------------------------------------------------------------------------- SR-116


@pytest.mark.sr("SR-267")
def test_sr116_ex1_a_stale_card_shows_everything_to_choose(project: Path,
                                                            hook_input) -> None:
    """EX-1: the end-of-turn text shows the requirement's current wording, the change itself,
    the owner's words it came from, each option's consequence and why the first."""
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return a * b\n")
    link = next(f"SR-001#{n}" for n, item in enumerate(open_core(project).index()["SR-001"].links)
                if item.kind == "implemented_by")
    stale.add_card(project, SESSION, link=link, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="add now multiplies",
                   options=["Undo the change", "Keep it and reword the requirement"],
                   consequences=["add sums again; the multiplying is dropped",
                                 "add keeps multiplying and the requirement says so"],
                   why="your words ask for a sum")
    verify = FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(NODE, "fresh-pass")})
    text = owner(run_stop(project, hook_input, verify=verify))
    lines = text.splitlines()
    assert lines[:3] == ["Adds numbers", "add now multiplies", "your words ask for a sum"]
    assert "  1. Undo the change (recommended) - add sums again; the multiplying is dropped" in (
        lines)
    assert owner_level(text) == []


def test_a_failure_of_a_test_since_removed_is_not_a_regression(tmp_path: Path) -> None:
    """SR-012 EX-2: a regression card is raised only for a test still defined in its file."""
    from plumb.hosts.claude_code.stop import test_exists

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_kept(): pass\n", encoding="utf-8")
    assert test_exists(tmp_path, "tests/test_x.py::test_kept")
    assert test_exists(tmp_path, "tests/test_x.py::test_kept[a-b]")
    assert not test_exists(tmp_path, "tests/test_x.py::test_gone[a-b]")
    assert not test_exists(tmp_path, "tests/test_x.py::test_kep")
    assert not test_exists(tmp_path, "tests/test_missing.py::test_kept")
