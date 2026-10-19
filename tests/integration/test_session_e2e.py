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
import subprocess
import sys
from pathlib import Path

import pytest

from plumb import approvals, cli
from plumb.api import open_core

ROOT = Path(__file__).resolve().parents[2]
# End-to-end allowance includes process startup and filesystem scanning on Windows.
# The owner requested this increase; configured in-process hook budgets are unchanged.
HOOK_LIMIT_MS = 5000
STOP_LIMIT_MS = 20_000  # DEC-078: the stop hook's soft budget is 20 s

pytestmark = [pytest.mark.sr("SR-275"), pytest.mark.sr("SR-225"), pytest.mark.sr("SR-265")]

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
    approvals.approve(open_core(repo), ["INT-001", "SR-001", "SR-002", "FEAT-001"])
    assert cli.main(["tests", "map", *root]) == 0
    assert cli.main(["hooks", "install", "--launcher", "path", *root]) == 0
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "adopt plumb", "--no-verify")
    return repo


def test_session_through_installed_hooks(adopted: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # DEC-088: Stop judges the stale link's meaning; a scripted judge stands in for 'claude -p'
    script = adopted.parent / "judge.json"
    script.write_text(json.dumps({"repin": {"verdict": "unchanged", "confidence": 0.9,
                                            "reason": "only a comment was appended"}}), "utf-8")
    monkeypatch.setenv("PLUMB_FAKE_DISPATCH", str(script))
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

    # Every hook stays within the integration allowance; the test run has its own bound.
    for step in steps:
        if step.name != "covering tests":
            limit = STOP_LIMIT_MS if step.name.startswith("Stop") else HOOK_LIMIT_MS
            assert step.ms < limit, (step.name, step.ms)
    assert run.ms < 120_000



@pytest.mark.sr("SR-235")
@pytest.mark.sr("SR-223")
@pytest.mark.sr("SR-267")
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

    # INT-036/INT-037: no stop asks the decision or lists the proposed records in prose; the
    # request's read-back is the one card, drawn by the clarify check, and the owner's answer
    # is read by plumb itself, so the agent is told to relay nothing
    for name in ("Stop (asks the decision)", "Stop (read-back shown)", "Stop (not asked again)",
                 "Stop (summary again)"):
        assert "is unconfirmed" not in by_name[name].stdout and "block" not in by_name[name].stdout
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


SR_DIV = """---
id: SR-003
title: div returns the quotient of two numbers
feature: FEAT-001
statement: pkg.mod.div(a, b) returns the quotient a / b.
examples:
  - {id: EX-1, given: the numbers 6 and 3, when: div is called, then: it returns 2}
proof:
  plan: run div 6 3 and see 2
  kind: command
---
"""


@pytest.mark.sr("SR-260")
def test_merge_check_on_plumb_reports_the_owners_pending_confirmations(
        adopted: Path, write_record) -> None:
    """The owner's choice (a scratch repository): a commit into main delivers SR-003, which the
    owner has not confirmed and whose proof nobody has shown; plumb merge-check (report only,
    --no-run) lists it as awaiting and holds the merge."""
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=adopted, capture_output=True,
                          text=True, check=True).stdout.strip()
    mod = adopted / "src" / "pkg" / "mod.py"
    mod.write_text(mod.read_text(encoding="utf-8") + "\n\ndef div(a, b):\n    return a / b\n",
                   encoding="utf-8")
    write_record(adopted, SR_DIV)
    assert cli.main(["link", "SR-003", "derives_from", "INT-001", "--root", str(adopted)]) == 0
    assert cli.main(["link", "SR-003", "implemented_by", "src/pkg/mod.py",
                     "--root", str(adopted)]) == 0
    _git(adopted, "add", "-A")
    _git(adopted, "commit", "-q", "-m", "div\n\nSR: SR-003", "--no-verify")
    step = _driver().merge_check(adopted, base)
    assert step.code != 0, step.stdout[-2000:]
    report = json.loads(step.stdout)
    assert report["error"] is None and not report["integrity"]
    assert report["exit"] == step.code
    assert "SR-003" in {a["id"] for a in report["awaiting"]}, "the pending record is listed"
