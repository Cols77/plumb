"""H7: the Stop hook: covering tests, the three triggers and the summary (spec 6.4, 6.5)."""

from __future__ import annotations

import io
import json
import subprocess
import time
from pathlib import Path

import pytest
from fakes import FakeVerify

from plumb import approvals
from plumb.api import open_core
from plumb.contracts import FullPending, NodeEvidence
from plumb.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-012")

NODE = "tests/test_a.py::test_a"
NODE2 = "tests/test_a.py::test_b"
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
DEC1 = """---
id: DEC-001
title: Integers only
question: Should add accept floats?
chosen: integers only
alternatives:
- floats too
matters: true
links:
- kind: decides
  to: SR-001
---
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "notes.md").write_text("notes\n", "utf-8")
    from plumb.contracts import Target

    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    return repo


def start_turn(repo: Path, session: str = "s1", asked: dict | None = None) -> None:
    path = repo / ".plumb" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64,
                                "asked": asked or {}}), "utf-8")


def edit(repo: Path, rel: str, text: str, session: str = "s1") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    touched = repo / ".plumb" / "session" / session / "touched.txt"
    with touched.open("a", encoding="utf-8") as handle:
        handle.write(rel + "\n")


def run_stop(repo: Path, hook_input, *, active: bool = False, session: str = "s1",
             verify=None, **kwargs) -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=session, stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=repo, verify=verify,
                     unjudged=kwargs.pop("unjudged", None), **kwargs) == 0
    return out.getvalue()


def _block(out: str) -> str | None:
    if not out.strip():
        return None
    data = json.loads(out)
    return data["reason"] if data.get("decision") == "block" else None


def _summary(out: str) -> str:
    return json.loads(out)["systemMessage"] if out.strip() else ""


def fresh(*nodes: str, state: str = "fresh-pass", **kw) -> dict[str, NodeEvidence]:
    return {n: NodeEvidence(n, state, **kw) for n in nodes}


def test_blocks_once_when_covering_tests_not_fresh(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE, NODE2), evidence_map=fresh(NODE))
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert reason == ("plumb: run 'plumb tests run --changed' (covering tests, budget 15 s), "
                      "then finish your reply.")
    assert verify.select_calls == [("src/calc.py",)]


def test_no_block_when_stop_hook_active(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE,))
    out = run_stop(project, hook_input, verify=verify, active=True)
    assert _block(out) is None
    assert "1 not run" in _summary(out)


def test_summary_when_evidence_fresh(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE, NODE2), deferred=("tests/test_z.py::test_z",),
                        evidence_map={**fresh(NODE), **fresh(NODE2, state="fresh-fail")},
                        pending=FullPending(True, ("tests/conftest.py changed",)))
    summary = _summary(run_stop(project, hook_input, verify=verify))
    lines = summary.splitlines()
    assert lines[0].startswith("plumb: touched SR-001")
    assert ("plumb: covering tests 2: 1 fresh pass, 1 not yet passing, 1 deferred (budget)"
            in lines)
    assert "plumb: full verification pending (tests/conftest.py changed)" in lines
    assert "plumb: questions: none" in lines
    assert len(lines) <= 5


def test_summary_shows_stale_link(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return a - b\n")
    summary = _summary(run_stop(project, hook_input, verify=FakeVerify()))
    assert "stale: SR-001#0 -> src/calc.py (target moved)" in summary.splitlines()[0]


def test_summary_caps_proposed_lines(project: Path, hook_input, write_record) -> None:
    start_turn(project)
    for i in range(2, 7):
        text = (f"---\nid: SR-00{i}\ntitle: Rule {i}\nstatement: rule {i} holds\nexamples:\n"
                f"- id: EX-1\n  given: g{i}\n  when: w{i}\n  then: t{i}\n---\n")
        edit(project, f".plumb/requirements/SR-00{i}.md", text)
    summary = _summary(run_stop(project, hook_input, verify=FakeVerify()))
    lines = summary.splitlines()
    proposed = [line for line in lines if line.startswith("plumb: proposed")]
    assert len(proposed) == 3
    assert proposed[0] == "plumb: proposed SR-002: rule 2 holds"
    assert "plumb: proposed SR-002/EX-1: given g2, when w2, then t2" in proposed
    assert lines[-1].startswith("plumb: +") and lines[-1].endswith("more (plumb status)")
    assert len(lines) <= 5 + 3 + 1
    assert _block(json.dumps({"systemMessage": summary})) is None


def test_regression_blocks_with_owner_instruction(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return a * b\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map=fresh(
        NODE, state="fresh-fail", regression=True, last_run="run-2"))
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert reason == (f"plumb: regression: {NODE} passed in an earlier run and now fails "
                      "(last run run-2). Tell the owner, with a read-back, and ask how to "
                      "proceed.")
    # asked once per failing run: the next stop does not block again
    start_turn(project, asked=json.loads((project / ".plumb" / "session" / "s1" /
                                          "turn.json").read_text("utf-8"))["asked"])
    out = run_stop(project, hook_input, verify=verify)
    assert _block(out) is None
    assert f"plumb: questions: regression {NODE}" in _summary(out)


@pytest.mark.sr("SR-020")
def test_edited_test_regression_still_blocks(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "tests/test_a.py", "def test_a():\n    assert False\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map=fresh(
        NODE, state="fresh-fail", regression=True, test_changed_since_pass=True,
        last_run="run-3"))
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert reason is not None
    assert "now fails (test source changed since the pass)" in reason


def test_matters_dec_asked_once_per_hash(project: Path, hook_input, write_record) -> None:
    write_record(project, DEC1)
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "dec")
    verify = FakeVerify(nodes=(NODE,), evidence_map=fresh(NODE))
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return int(a) + int(b)\n")
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert reason == ('plumb: DEC-001 is unconfirmed and this work relies on it. Ask the '
                      'owner: "I assumed integers only; floats too also fits. Which one?"')
    stated = json.loads((project / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    assert "DEC-001" in [r["id"] for r in stated["records"]]
    asked = json.loads((project / ".plumb" / "session" / "s1" / "turn.json")
                       .read_text("utf-8"))["asked"]
    start_turn(project, asked=asked)
    edit(project, "src/calc.py", "def add(a, b):\n    return int(b) + int(a)\n")
    assert _block(run_stop(project, hook_input, verify=verify)) is None
    # a new hash of the decision asks again
    dec = project / ".plumb" / "decisions" / "DEC-001.md"
    dec.write_text(DEC1.replace("integers only", "ints only"), "utf-8")
    start_turn(project, asked=asked)
    edit(project, "src/calc.py", "def add(a, b):\n    return int(a) + int(b)\n")
    assert "DEC-001" in (_block(run_stop(project, hook_input, verify=verify)) or "")


@pytest.mark.sr("SR-020")
def test_new_red_test_never_asks(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "tests/test_new.py", "def test_new():\n    assert False\n")
    node = "tests/test_new.py::test_new"
    verify = FakeVerify(nodes=(node,), evidence_map=fresh(node, state="fresh-fail"))
    out = run_stop(project, hook_input, verify=verify)
    assert _block(out) is None
    summary = _summary(out)
    assert "1 not yet passing" in summary
    assert "plumb: questions: none" in summary


def test_doc_only_turn_prints_at_most_one_line(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "docs/notes.md", "more notes\n")
    verify = FakeVerify(nodes=(NODE,))
    out = run_stop(project, hook_input, verify=verify)
    assert _block(out) is None
    assert len(_summary(out).splitlines()) <= 1


def test_writes_stated_set(project: Path, hook_input) -> None:
    start_turn(project)
    text = SR1.replace("SR-001", "SR-002").replace("Adds numbers", "Subtracts")
    edit(project, ".plumb/requirements/SR-002.md", text)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    run_stop(project, hook_input, verify=FakeVerify(), active=True)
    stated = json.loads((project / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    index = open_core(project).index()
    assert stated["records"] == [{"id": "SR-002", "hash": index["SR-002"].hash}]
    assert stated["session"] == "s1" and stated["reply_after_prompt"] == "sha256:" + "a" * 64
    # the stated set is what plumb relay accepts on the owner's next "ok"
    text = "ok, sounds right"
    prompts = project / ".plumb" / "session" / "prompts.jsonl"
    prompts.write_text(json.dumps({"digest": approvals.prompt_digest(text), "session": "s1",
                                   "at": "2999-01-01T00:00:00Z", "text": text}) + "\n",
                       "utf-8")
    approvals.relay(open_core(project), ["SR-002"], prompt=approvals.prompt_digest(text),
                    quote="ok")
    assert open_core(project).status(["SR-002"])["SR-002"].confirmation == "confirmed"


def test_no_change_turn_prints_nothing(project: Path, hook_input) -> None:
    start_turn(project)
    verify = FakeVerify(nodes=(NODE,))
    assert run_stop(project, hook_input, verify=verify) == ""
    assert verify.select_calls == []


def test_old_uncommitted_changes_are_not_this_turn(project: Path, hook_input) -> None:
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return 0\n", "utf-8")
    time.sleep(0.05)
    path = project / ".plumb" / "session" / "s1" / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() + 1, "asked": {}}), "utf-8")
    assert run_stop(project, hook_input, verify=FakeVerify(nodes=(NODE,))) == ""


def test_git_status_changes_count_without_touched(project: Path, hook_input) -> None:
    start_turn(project)
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return b + a\n", "utf-8")
    verify = FakeVerify(nodes=(NODE,), evidence_map=fresh(NODE))
    run_stop(project, hook_input, verify=verify)
    assert verify.select_calls == [("src/calc.py",)]


def test_verify_unavailable_degrades(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    out = run_stop(project, hook_input, verify=None)
    assert _block(out) is None
    assert "plumb: verification unavailable" in _summary(out)


def test_confirmation_and_unjudged_fidelity_in_summary(project: Path, hook_input) -> None:
    start_turn(project)
    approvals.approve(open_core(project), ["SR-001"])
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    out = run_stop(project, hook_input, verify=FakeVerify(),
                   unjudged=lambda core, ids: tuple(i for i in ids or () if i == "SR-001"))
    summary = _summary(out)
    assert "plumb: confirmed SR-001 by the owner | fidelity unjudged: SR-001" in summary


def test_writes_status_snapshot(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map=fresh(
        NODE, state="fresh-fail", regression=True, last_run="r"))
    run_stop(project, hook_input, verify=verify)
    data = json.loads((project / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert data["tests"] == "regression" and data["ask"] == 1
