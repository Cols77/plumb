"""R12.3 / SR-044 EX-1: every untraced-change instruction names the proposed owner (audit
round 3).

SR-001 owns src/app/calc.py; the agent writes src/app/mod.py in the same package. The one
builder of the untraced instruction (``plumb.trace.trace_instruction`` with the core) carries
CAPTURE's ownership proposal, bounded in paths and time. One test per entry point: the Claude
Code Stop hook's block, the prompt hook's queued instruction, ``plumb turn end`` (the
host-neutral turn API every adapter falls back to) and ``plumb review``, which now reads
uncommitted changes as ``plumb merge-check`` does.
"""

from __future__ import annotations

import io
import json
import subprocess
import time
from pathlib import Path

import pytest
from capture_helpers import record_text

from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-200")

PROPOSED = "src/app/mod.py: SR-001 may own this (proposed)"
DEC1 = record_text("DEC-001", "Integers only", question="Should add accept floats?",
                   chosen="integers only", alternatives=["floats too"], matters=True,
                   links=[{"kind": "decides", "to": "SR-001"}])


@pytest.fixture(autouse=True)
def owner_judge(monkeypatch) -> None:
    """The configured judge chooses SR-001 (INT-029: no rule-based judge stands in)."""
    import plumb.judgment
    from plumb.judgment import FakeBackend

    judge = FakeBackend({("ownership", "src/app/mod.py"): ("SR-001: add returns the sum", 0.9)})
    monkeypatch.setattr(plumb.judgment, "get_backend", lambda core, hook: judge)


@pytest.fixture
def calc(repo: Path, write_record) -> Path:
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "src" / "app" / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                                  encoding="utf-8")
    write_record(repo, record_text(
        "SR-001", "add returns the sum", statement="add(a, b) returns the sum",
        examples=[{"id": "EX-1", "given": "a = 1 and b = 2", "when": "add runs",
                   "then": "it returns the sum 3"}]))
    write_record(repo, DEC1)
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/app/calc.py"))
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "setup"], cwd=repo, check=True,
                   capture_output=True)
    return repo


def _start_turn(repo: Path, session: str = "s1") -> None:
    path = repo / ".plumb" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}), "utf-8")


def _write_mod(repo: Path, session: str = "s1") -> None:
    (repo / "src" / "app" / "mod.py").write_text("def mod(a, b):\n    return a % b\n",
                                                 encoding="utf-8")
    touched = repo / ".plumb" / "session" / session / "touched.txt"
    touched.parent.mkdir(parents=True, exist_ok=True)
    with touched.open("a", encoding="utf-8") as handle:
        handle.write("src/app/mod.py\n")


class UnrunVerify:
    """A VerifyAPI whose one covering test has no evidence: the stop hook blocks to ask
    for it, and the untraced instruction rides along that block."""

    NODE = "tests/test_calc.py::test_add"

    def select(self, changed, *, budget_s=None):
        from plumb.contracts import Selection

        return Selection(changed=tuple(changed), nodes=(self.NODE,),
                         reasons={self.NODE: "verified_by"}, deferred=(),
                         infra_changed=(), doc_only=False, expected_s=1.0)

    def evidence(self, nodes):
        from plumb.contracts import NodeEvidence

        return {n: NodeEvidence(n, "none") for n in nodes}

    def full_pending(self):
        from plumb.contracts import FullPending

        return FullPending(False)

    def tests_for(self, refs):
        return {r: () for r in refs}


def test_stop_hook_queues_the_untraced_note_for_the_next_prompt(calc: Path, hook_input) -> None:
    """R1: an untraced file never blocks the stop; its note waits for the next prompt hook
    (the next test), which names the proposed owner."""
    from plumb.hosts.claude_code import stop

    _start_turn(calc)
    _write_mod(calc)
    out = io.StringIO()
    payload = hook_input("Stop", session_id="s1", stop_hook_active=False)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=calc,
                     verify=UnrunVerify(),
                     unjudged=None) == 0
    assert "untraced change" not in out.getvalue()
    note = json.loads((calc / ".plumb" / "session" / "s1" / "untraced.json").read_text("utf-8"))
    assert note["paths"] == ["src/app/mod.py"]


def test_prompt_hook_queued_instruction_names_the_proposed_owner(calc: Path,
                                                                 hook_input) -> None:
    from plumb.hosts.claude_code import prompt as prompt_hook

    _write_mod(calc)
    note = calc / ".plumb" / "session" / "s1" / "untraced.json"
    note.write_text(json.dumps({"paths": ["src/app/mod.py"]}), encoding="utf-8")
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt="carry on", session_id="s1")
    assert prompt_hook.main(stdin=io.StringIO(payload), stdout=out, root=calc,
                            verify=None, backend=None) == 0
    lines = out.getvalue().splitlines()
    [line] = [x for x in lines if x.startswith("plumb: untraced change:")]
    assert PROPOSED in line


def test_turn_end_names_the_proposed_owner(calc: Path, monkeypatch, capsys) -> None:
    from plumb.cli import main

    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    monkeypatch.chdir(calc)
    monkeypatch.setattr("sys.stdin", io.StringIO("make add accept floats"))
    assert main(["turn", "start", "--session", "t1"]) == 0
    capsys.readouterr()
    (calc / "src" / "app" / "calc.py").write_text(
        "def add(a, b):\n    return int(a) + int(b)\n", encoding="utf-8")
    _write_mod(calc, "t1")
    assert main(["turn", "end", "--session", "t1"]) == 0
    out = capsys.readouterr().out
    [line] = [x for x in out.splitlines() if x.startswith("plumb: untraced change:")]
    assert PROPOSED in line


def test_review_names_the_proposed_owner_of_an_uncommitted_change(calc: Path,
                                                                  capsys) -> None:
    from plumb.cli import main

    _write_mod(calc)
    assert main(["review", "--root", str(calc)]) in (0, 1)
    out = capsys.readouterr().out
    assert f"ownership: {PROPOSED}" in out
