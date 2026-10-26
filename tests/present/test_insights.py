"""SR-374: what plumb tells the coding agent is one table, condition to insight, said once per
session per state, with the full picture of a condition on demand (plumb context)."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from plumb import cli, stale, trace
from plumb.api import open_core
from plumb.contracts import Target
from plumb.hosts.claude_code import edit_check, hookio, prompt, session_start
from plumb.understand import cmd_intent

pytestmark = pytest.mark.sr("SR-374")

SESSION = "s-insights"
INT = "---\nid: INT-001\ntitle: Faster merges\nquote: make merges faster\n---\n"
SR5 = """---
id: SR-005
title: Relay checks the quote
statement: relay checks the quote.
examples:
- id: EX-1
  given: a quote
  when: relay runs
  then: it checks it
---
"""
CODE = "def f(a, b):\n    return a + b\n"


@pytest.fixture(autouse=True)
def _quiet_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """What the hooks say, not how fast the machine is, nor the understanding layer's gate."""
    monkeypatch.setattr(session_start, "hook_budget", lambda name: (lambda root: 8000.0))
    monkeypatch.setattr(prompt, "hook_budget", lambda name: (lambda root: 8000.0))
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])


def _start(repo: Path, hook_input, source: str = "startup", session: str = SESSION) -> str:
    out = io.StringIO()
    payload = hook_input("SessionStart", source=source, session_id=session)
    assert session_start.main(stdin=io.StringIO(payload), stdout=out, root=repo,
                              verify=None) == 0
    return out.getvalue()


def _prompt(repo: Path, hook_input, text: str, session: str = SESSION) -> str:
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=text, session_id=session)
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo, verify=None,
                       backend=None) == 0
    return out.getvalue()


def _open_loop(repo: Path, tasks: dict | None = None) -> None:
    path = cmd_intent.open_loop(repo, SESSION, "sha256:" + "a" * 64)
    data = json.loads(path.read_text("utf-8"))
    data["intent"] = "INT-001"
    data["tasks"] = tasks or {"label": "building: P7", "done": 6, "total": 9, "left": ["P8"]}
    cmd_intent.save(path, data)


@pytest.fixture
def looped(repo: Path, write_record) -> Path:
    write_record(repo, INT)
    _open_loop(repo)
    return repo


INTENT_LINE = "plumb: working on INT-001 Faster merges: step clarify; now building: P7 6/9; left: P8"


def test_ex1_after_compaction_the_intent_line_comes_back_once(looped: Path, hook_input) -> None:
    _start(looped, hook_input)
    _prompt(looped, hook_input, "go on")
    said = _start(looped, hook_input, source="compact") + _prompt(looped, hook_input, "continue")
    assert said.count(INTENT_LINE) == 1


def test_ex2_the_intent_line_once_and_not_when_the_message_names_it(looped: Path,
                                                                     hook_input) -> None:
    assert INTENT_LINE in _prompt(looped, hook_input, "fix the parser")
    _open_loop(looped, {"label": "building: P8", "done": 7, "total": 9})   # the state moves on
    assert "working on" not in _prompt(looped, hook_input, "carry on with INT-001")


@pytest.fixture
def linked(repo: Path, write_record) -> Path:
    write_record(repo, SR5)
    (repo / "src").mkdir()
    (repo / "src" / "x.py").write_text(CODE, encoding="utf-8")
    core = open_core(repo)
    core.add_link("SR-005", "implemented_by", Target(path="src/x.py", symbol="f"))
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text("def test_f():\n    assert True\n", "utf-8")
    open_core(repo).add_link("SR-005", "verified_by", Target(test="tests/test_x.py::test_f"),
                             example="EX-1")
    stale.ensure_linkmap(open_core(repo))
    return repo


def test_ex3_an_edit_names_the_requirement_examples_tests_and_stale_link(
        linked: Path, hook_input) -> None:
    (linked / "src" / "x.py").write_text(CODE.replace("a + b", "a - b"), encoding="utf-8")
    out = io.StringIO()
    payload = hook_input("PostToolUse", tool_name="Edit", session_id=SESSION,
                         tool_input={"file_path": str(linked / "src" / "x.py")})
    assert edit_check.main(stdin=io.StringIO(payload), stdout=out, root=linked) == 0
    text = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
    assert ("plumb: src/x.py serves SR-005 Relay checks the quote; examples EX-1; tests "
            "tests/test_x.py::test_f") in text
    assert "SR-005's link to src/x.py is stale" in text


def test_ex4_a_test_that_never_passed_is_not_yet_passing_and_names_its_example(
        linked: Path) -> None:
    from types import SimpleNamespace

    from plumb.verify.cli import report_lines

    report = SimpleNamespace(
        selection=None, run_id="r1", outcomes={"tests/test_x.py::test_f": "failed"},
        regressions=[], failed=["tests/test_x.py::test_f"],
        not_yet_passing=["tests/test_x.py::test_f"], elapsed_s=1, full=False, timed_out=False,
        aborted=None, discarded=None, collection_errors=[], flaky=[],
        removed_after_passing=[], notes=[], full_pending=None)
    text = "\n".join(report_lines(report, open_core(linked)))
    assert ("plumb: not yet passing: tests/test_x.py::test_f (it never passed); it proves "
            "SR-005/EX-1") in text
    assert "regression" not in text


def test_ex5_a_symptom_of_an_open_known_issue_is_said_once(repo: Path, hook_input) -> None:
    (repo / ".plumb" / "known-issues.json").write_text(json.dumps({"issues": [{
        "id": "KI-9", "title": "stop hook times out", "symptom": "stop hook .*timed? ?out",
        "cause": "the full check runs inside the hook", "fix": "update the plugin"}]}), "utf-8")
    first = _prompt(repo, hook_input, "the stop hook timed out again")
    assert ("plumb: known issue KI-9 stop hook times out; cause: the full check runs inside "
            "the hook; fix or workaround: update the plugin") in first
    assert "KI-9" not in _prompt(repo, hook_input, "the stop hook timed out again")


def test_ex6_the_merge_check_prints_only_what_holds(repo: Path, capsys) -> None:
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                          text=True, check=True).stdout.strip()
    (repo / "src").mkdir()
    (repo / "src" / "m.py").write_text("x = 1\n", encoding="utf-8")      # untraced: listed only
    code = cli.main(["merge-check", base, "--no-run", "--root", str(repo)])
    out = capsys.readouterr().out
    assert out.startswith(f"plumb merge-check: {base}..HEAD: ")
    for info in ("untraced", "approvals in range", "log integrity: ok", "touched requirements",
                 "fidelity", "full run:"):
        assert info not in out
    assert ("nothing holds the merge" in out) == (code == 0)


def test_ex7_a_cut_names_the_skipped_step_once_per_session(repo: Path, hook_input) -> None:
    def cut(ctx: hookio.HookContext) -> None:
        ctx.keep(["plumb: a kept line"])
        raise hookio.BudgetExceeded("tests")

    said = []
    for _ in range(2):
        out = io.StringIO()
        hookio.run_hook("session-start", cut, stdin=io.StringIO(hook_input(
            "SessionStart", session_id=SESSION)), stdout=out, root=repo)
        said.append(out.getvalue())
    assert "plumb: check skipped (budget): tests" in said[0]
    assert "check skipped" not in said[1] and "plumb: a kept line" in said[1]


def test_ex8_plumb_context_edit_prints_the_full_picture(linked: Path, capsys) -> None:
    (linked / "src" / "x.py").write_text(CODE.replace("a + b", "a - b"), encoding="utf-8")
    assert cli.main(["context", "edit", "src/x.py", "--root", str(linked)]) == 0
    out = capsys.readouterr().out
    assert "SR-005 Relay checks the quote" in out                            # requirement
    assert "example EX-1: given a quote, when relay runs, then it checks it" in out
    assert "test tests/test_x.py::test_f" in out                             # tests
    assert "link SR-005#0 implemented_by src/x.py::f" in out                 # links
    assert "stale: plumb: SR-005's link to src/x.py is stale" in out         # drift


def test_ex9_the_brief_says_what_changed_and_what_blocks_and_no_counts(
        repo: Path, write_record, hook_input) -> None:
    for i in range(1, 401):
        write_record(repo, f"---\nid: SR-{i:03d}\ntitle: Rule {i}\nstatement: s{i}.\n---\n")
    (repo / "src").mkdir()
    for i in range(1, 4):   # stale links
        (repo / "src" / f"m{i}.py").write_text("x = 1\n", encoding="utf-8")
        open_core(repo).add_link(f"SR-{i:03d}", "implemented_by", Target(path=f"src/m{i}.py"))
        (repo / "src" / f"m{i}.py").write_text("x = 2\n", encoding="utf-8")
    first = _start(repo, hook_input, session="a")
    write_record(repo, "---\nid: SR-007\ntitle: Rule seven, reworded\nstatement: t.\n---\n")
    second = _start(repo, hook_input, session="b")
    for out in (first, second):
        assert "400" not in out and "stale" not in out and "waiting on a judge" not in out
        assert "plumb brief:" not in out
    assert "changed since" not in first                         # nothing seen before
    assert "plumb: changed since you last looked: SR-007 Rule seven, reworded" in second


def test_ex10_vendored_example_files_are_never_untraced(repo: Path) -> None:
    vendored = "src/plumb/hosts/claude_code/templates/skills/x/vendor/scene.py"
    beside = vendored.replace("/vendor/", "/own/")
    core = open_core(repo)
    assert trace.is_source_path(core.config, beside)          # the vendor folder is the reason
    assert not trace.is_source_path(core.config, vendored)
    assert trace.untraced_paths(core, [vendored, beside]) == [beside]
