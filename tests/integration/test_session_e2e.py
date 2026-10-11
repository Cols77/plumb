"""End-to-end: a simulated Claude Code session through plumb's installed hooks.

A temporary repository is adopted by plumb (``init``, an ``INT``, two ``SR`` records with
examples, pinned links, owner approval in the owner's terminal, ``tests map``, ``hooks
install``). ``scripts/drive_session.py`` then runs each hook command from
``.claude/settings.json`` as its own process with the JSON Claude Code sends: SessionStart, a
prompt contradicting a confirmed requirement, a prompt naming one, an Edit and its
PostToolUse, Stop (blocks for the covering tests), the covering-test run, Stop again (the
alignment summary), and the status line.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from plumb import cli

ROOT = Path(__file__).resolve().parents[2]
HOOK_LIMIT_MS = 2000

pytestmark = [pytest.mark.sr("SR-014"), pytest.mark.sr("SR-010"), pytest.mark.sr("SR-012")]

INT = """---
id: INT-001
title: Arithmetic helpers
quote: "I need small arithmetic helpers that return exact results"
readback: Provide add and multiply helpers that return exact results.
---
"""

SR_ADD = """---
id: SR-001
title: add returns the sum of two numbers
feature: FEAT-001
statement: pkg.mod.add(a, b) returns the sum a + b.
examples:
  - {id: EX-1, given: the numbers 1 and 2, when: add is called, then: it returns 3}
---
"""

SR_MUL = """---
id: SR-002
title: mul returns the product of two numbers
feature: FEAT-001
statement: pkg.mod.mul(a, b) returns the product a * b.
examples:
  - {id: EX-1, given: the numbers 2 and 3, when: mul is called, then: it returns 6}
---
"""

FEAT = """---
id: FEAT-001
title: Arithmetic
description: Small arithmetic helpers.
requirements: [SR-001, SR-002]
---
"""

FILES = {
    "pyproject.toml": "[tool.pytest.ini_options]\npythonpath = [\"src\"]\n"
                      "testpaths = [\"tests\"]\n"
                      "markers = [\"sr(id): links a test to a plumb requirement\"]\n",
    "src/pkg/__init__.py": "",
    "src/pkg/mod.py": "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n"
                      "    return a * b\n",
    "tests/test_mod.py": "import pytest\n\nfrom pkg.mod import add, mul\n\n\n"
                         "@pytest.mark.sr(\"SR-001\")\ndef test_add():\n"
                         "    assert add(1, 2) == 3\n\n\n@pytest.mark.sr(\"SR-002\")\n"
                         "def test_mul():\n    assert mul(2, 3) == 6\n",
    ".plumb/config.yaml": "verify:\n  flaky_rerun: false\n",
}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _driver():
    spec = importlib.util.spec_from_file_location("drive_session",
                                                  ROOT / "scripts" / "drive_session.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["drive_session"] = module  # dataclasses look their module up
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def adopted(repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> Path:
    # hooks run `plumb` from PATH, as an installed tool would
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep
                       + os.environ.get("PATH", ""))
    for rel, text in FILES.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    for text in (INT, SR_ADD, SR_MUL, FEAT):
        write_record(repo, text)
    root = ["--root", str(repo)]
    for sr in ("SR-001", "SR-002"):
        assert cli.main(["link", sr, "derives_from", "INT-001", *root]) == 0
        assert cli.main(["link", sr, "implemented_by", "src/pkg/mod.py", *root]) == 0
        assert cli.main(["link", sr, "verified_by", "tests/test_mod.py", "--example", "EX-1",
                         *root]) == 0
    # the owner confirms in their own terminal (no session marker in this process)
    assert cli.main(["approve", "INT-001", "SR-001", "SR-002", "FEAT-001",
                     *root]) == 0
    assert cli.main(["tests", "map", *root]) == 0
    assert cli.main(["hooks", "install", "--launcher", "path", *root]) == 0
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "adopt plumb", "--no-verify")
    return repo


def test_session_through_installed_hooks(adopted: Path) -> None:
    driver = _driver()
    steps = driver.drive(
        adopted, edit="src/pkg/mod.py",
        prompt_change="Change SR-001: add should no longer return the sum, return the "
                      "difference instead.",
        prompt="Tidy up the add helper of SR-001 without changing what it returns.")
    by_name = {s.name: s for s in steps}
    timings = {s.name: s.ms for s in steps}
    print("\n" + json.dumps(timings, indent=2))  # visible with -s
    assert all(s.code == 0 for s in steps), [(s.name, s.code, s.stderr) for s in steps]

    # SessionStart: the compact brief (R9), with the counts, the tests line and a pointer
    brief = by_name["SessionStart"].stdout
    assert brief.startswith("plumb brief: 1 feature(s), 2 SR (2 confirmed), 1 INT (1 confirmed)")
    assert "tests:" in brief and "plumb show <ID>" in brief
    assert len(brief.splitlines()) <= 6

    # no judge is configured here (INT-029): the hook says so in one line, flags nothing by
    # rules, and still gives the prompt its record
    change = by_name["UserPromptSubmit (contradicts)"].stdout
    assert "SR-001 [confirmed]" in change
    assert change.count("plumb: judging unavailable:") == 1 and "judgment.backend" in change
    assert "this may change" not in change
    assert not (adopted / ".plumb" / "session" / "intent_flags.jsonl").exists()

    # a turn that changed nothing prints nothing
    assert by_name["Stop (no change)"].stdout.strip() == ""

    # the contradicting prompt gave SR-001 one line; the next prompt naming it in the same
    # session injects no repeat (R9 delta), and its examples come from plumb show
    assert "EX-1" not in change and "tests/test_mod.py" not in change
    named = by_name["UserPromptSubmit (names SR)"].stdout
    assert "SR-001 [confirmed]" not in named
    assert "this may change" not in named

    # the edit is tracked; Stop blocks once for the covering tests
    touched = adopted / ".plumb" / "session" / "plumb-driven-1" / "touched.txt"
    assert touched.read_text("utf-8").splitlines() == ["src/pkg/mod.py"]
    block = json.loads(by_name["Stop"].stdout)
    assert block["decision"] == "block"
    assert "plumb tests run --paths src/pkg/mod.py" in block["reason"]

    # the covering tests ran and their evidence was appended
    run = by_name["covering tests"]
    assert "2 passed" in run.stdout
    from logutil import entries

    evidence = json.dumps(entries(adopted, "evidence"))
    assert "tests/test_mod.py::test_add" in evidence
    assert "test-run" in evidence

    # SR-012 EX-5: nothing needs the owner (confirmed records, covering tests passing, no
    # question): the stop shows nothing; the state is the status line's (sp5 2), no summary
    assert by_name["Stop (stop_hook_active)"].stdout.strip() == ""

    assert by_name["statusline"].stdout.startswith("plumb ")  # the status card (sp5 2)

    # every hook well under 2 s; the test run is bounded by the tests themselves
    for step in steps:
        if step.name != "covering tests":
            assert step.ms < HOOK_LIMIT_MS, (step.name, step.ms)
    assert run.ms < 120_000



@pytest.mark.sr("SR-034")
@pytest.mark.sr("SR-043")
@pytest.mark.sr("SR-062")
def test_capture_flow_through_installed_hooks(adopted: Path) -> None:
    """The capture flow (sp2, R1, R2, R11): a read-back shown as an intent card, a proposed
    example, the decision that matters asked once, and the owner's "ok" relayed for exactly
    what the summary showed is left for plumb's own reader: the agent is told to relay nothing."""
    from plumb.api import open_core

    driver = _driver()
    steps = driver.drive_capture(adopted)
    by_name = {s.name: s for s in steps}
    print("\n" + json.dumps({s.name: s.ms for s in steps}, indent=2))  # visible with -s
    assert all(s.code == 0 for s in steps), [(s.name, s.code, s.stderr) for s in steps]

    # the agent records the read-back in one call; everything stays proposed (R1)
    captured = by_name["plumb capture"].stdout
    for line in ("INT-002 proposed", "SR-003 proposed", "DEC-001 proposed"):
        assert line in captured

    # the decision that matters is asked, alone, in the next message (R11)
    asked = json.loads(by_name["Stop (asks the decision)"].stdout)
    assert asked["decision"] == "block"
    assert re.findall(r"plumb: (DEC-\d+) is unconfirmed", asked["reason"]) == ["DEC-001"]
    assert "I assumed integers only; floats too also fits" in asked["reason"]

    # the end-of-turn summary shows the read-back and its examples, proposed
    # (SR-012: as cards, the decision's and one for the feature's proposed records, each in full)
    shown = json.loads(by_name["Stop (read-back shown)"].stdout)["systemMessage"]
    lines = shown.splitlines()
    assert lines[0].startswith('A choice this work relies on, "Floats too, or integers only?": '
                               "I assumed integers only; floats too also fits.")
    assert ('Proposed this turn, "Add sub(a, b) beside add, returning a - b": these 2 were '
            "written from your words this turn and are not settled; are they right?") in lines
    assert "  - Add sub(a, b) beside add, returning a - b" in lines
    assert "    will: sub(a, b) returns a - b" in lines
    assert "    won't: no change to add or mul" in lines
    assert "    assumed: integers, like add" in lines
    assert "    EX-1: given the numbers 5 and 3, when sub is called, then it returns 2" in lines
    assert "    EX-2: given the numbers 3 and 5, when sub is called, then it returns -2" in lines

    # a later stop in the same turn does not ask the decision again
    again = json.loads(by_name["Stop (not asked again)"].stdout)
    assert again.get("decision") != "block"
    assert "is unconfirmed" not in json.dumps(again)

    # the owner's "ok": the summary showed these records, and the prompt hook no longer tells
    # the agent to confirm them (the reader of the answer does, INT-028)
    stated = json.loads((adopted / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    shown_ids = [r["id"] for r in stated["records"] if r.get("shown")]
    assert shown_ids == ["DEC-001", "INT-002", "SR-003"]
    answer = by_name["UserPromptSubmit (owner ok)"].stdout
    assert "plumb relay" not in answer and "awaiting confirmation" not in answer
    assert "plumb relay" not in by_name
    core = open_core(adopted)
    assert not [e for e in core.events()
                if e.kind == "approval" and e.payload.get("by") == "agent-relayed"]

    hooks = [s for s in steps if s.name.startswith(("SessionStart", "UserPromptSubmit",
                                                     "Stop", "statusline"))]
    slow = {s.name: s.ms for s in hooks if s.ms > HOOK_LIMIT_MS}
    assert not slow, slow


# the batch's base: the merge boundary of sub-projects 2 to 5 on plumb itself
BATCH_BASE = "9dd86c6"


@pytest.mark.sr("SR-047")
def test_merge_check_on_plumb_reports_the_owners_pending_confirmations() -> None:
    """plumb merge-check on plumb's own repository (report only, --no-run): plumb's records
    await the owner (no agent approves them), so the boundary is not green and lists them."""
    if not (ROOT / ".claude" / "settings.json").is_file():
        pytest.skip("plumb's hooks are not installed in this checkout")
    known = subprocess.run(["git", "cat-file", "-e", f"{BATCH_BASE}^{{commit}}"], cwd=ROOT,
                           capture_output=True, check=False)
    if known.returncode != 0:
        pytest.skip(f"{BATCH_BASE} is not in this clone's history")
    step = _driver().merge_check(ROOT, BATCH_BASE)
    assert step.code != 0, step.stdout[-2000:]
    report = json.loads(step.stdout)
    assert report["error"] is None and not report["integrity"]
    assert report["exit"] == step.code
    assert report["awaiting"], "the owner's pending confirmations are listed"
    assert {"SR-034", "SR-047", "SR-053", "SR-061"} <= {a["id"] for a in report["awaiting"]}
