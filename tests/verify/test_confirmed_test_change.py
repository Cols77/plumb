"""An owner-confirmed example's acceptance test cannot change meaning, or stop failing, without
the owner seeing it (SR-030); the merge boundary is never green while an acceptance test the
change can affect lacks passing evidence, or while the deferred full run is neither done nor
waived by the owner (SR-031).

Entry points: the stop hook, ``plumb validate --merge``, ``plumb status`` and ``plumb drift``
(SR-030); the merge boundary after a shared test infrastructure change and after a change to
one requirement's code that breaks another requirement's acceptance test (SR-031).
"""

from __future__ import annotations

import io
import json
import subprocess
import time
from pathlib import Path

import pytest
from verify_helpers import SR_TEXT, commit_all, make_project, write

from plumb import approvals, cli
from plumb.api import open_core
from plumb.contracts import Target
from plumb.hosts.claude_code import stop
from plumb.merge import merge_check
from plumb.verify import open_verify
from plumb.verify.evidence import _track_regression

FEAT = ("---\nid: FEAT-001\ntitle: Arithmetic\ndescription: d\n"
        "requirements: [SR-001, SR-002]\n---\n")
INT = "---\nid: INT-001\ntitle: Adding\nquote: q\nreadback: Add numbers.\n---\n"
SR2 = """---
id: SR-002
title: Doubling
feature: FEAT-001
statement: twice(a) returns a + a.
examples:
  - {id: EX-1, given: the number 2, when: doubled, then: it returns 4}
---
"""
SUBTRACT = "def add(a, b):\n    return a - b\n"
REWRITTEN = ("import pytest\n\nfrom pkg.mod import add\n\n\n@pytest.mark.sr(\"SR-001\")\n"
             "def test_add():\n    assert add(1, 2) == -1\n\n\ndef test_add_zero():\n"
             "    assert add(0, 0) == 0\n")


def _check(root: Path, base: str, *, as_json: bool = False) -> int:
    """The merge report after the reviewed link ends are repinned (a stale link of a touched
    requirement holds the merge with exit 1 before verification is read, sp3 5)."""
    from plumb.links import repin

    repin(open_core(root), all_stale=True)
    return merge_check(open_core(root), base, as_json=as_json)


def _head(root: Path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()


@pytest.fixture
def confirmed(repo: Path, write_record) -> tuple[Path, str]:
    """SR-001 (add, owns src/pkg/mod.py, EX-1 verified_by tests/test_mod.py) and SR-002
    (doubling, owns src/pkg/helper.py, EX-1 verified_by tests/test_helper.py), both confirmed
    by the owner, with a passing full run recorded."""
    make_project(repo)
    write_record(repo, FEAT)
    write_record(repo, INT)
    write_record(repo, SR_TEXT)
    write_record(repo, SR2)
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/pkg/mod.py"))
    core.add_link("SR-001", "verified_by", Target(path="tests/test_mod.py"), example="EX-1")
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    core.add_link("SR-002", "implemented_by", Target(path="src/pkg/helper.py"))
    core.add_link("SR-002", "verified_by", Target(path="tests/test_helper.py"),
                  example="EX-1")
    core.add_link("SR-002", "implemented_by", Target(path="src/pkg/lonely.py"))
    write(repo, "tests/test_paths.py", "def test_mentions():\n    assert True\n")
    commit_all(repo, "base")
    base = _head(repo)
    approvals.approve(open_core(repo), ["SR-001", "SR-002", "INT-001"])
    assert open_verify(open_core(repo)).run(full=True).ok
    return repo, base


def _rewrite_test_to_pass(root: Path) -> None:
    """The reproduced scenario: add() becomes subtract, the run reports the regression, then
    the test is rewritten to expect the new result and passes."""
    write(root, "src/pkg/mod.py", SUBTRACT)
    report = open_verify(open_core(root)).run(nodes=["tests/test_mod.py"])
    assert [r["node"] for r in report.regressions] == ["tests/test_mod.py::test_add"]
    write(root, "tests/test_mod.py", REWRITTEN)
    assert open_verify(open_core(root)).run(nodes=["tests/test_mod.py"]).ok


# -- SR-030: the regression is kept until a pass on the same test body ------------------------


def test_a_pass_after_the_test_body_changed_does_not_resolve_a_regression() -> None:
    entry: dict = {"last_pass": {"run_id": "r1", "test_hash": "h1"}}
    _track_regression(entry, {"run_id": "r2", "outcome": "failed", "test_hash": "h1"})
    assert entry["regressed"]["passed_in"] == "r1"
    _track_regression(entry, {"run_id": "r3", "outcome": "passed", "test_hash": "h2"})
    assert entry["regressed"]["masked_by"] == "r3"
    _track_regression(entry, {"run_id": "r4", "outcome": "passed", "test_hash": "h1"})
    assert "regressed" not in entry


# -- report-fba0ba92: a background judge reads the test change before the flag drops ------------


def _judge_answers(tmp_path: Path, monkeypatch, answer: dict) -> Path:
    script = tmp_path / "answers.json"
    script.write_text(json.dumps({"testchange": answer}), encoding="utf-8")
    monkeypatch.setenv("PLUMB_FAKE_DISPATCH", str(script))
    return script


def test_a_hidden_regression_queues_a_background_judge_and_the_flag_stays_until_it_answers(
        confirmed, monkeypatch, tmp_path) -> None:
    """SR-207 EX-6, SR-273: finding the hidden regression queues a job (no model is called in
    the check); until it answers, and when it says the edit was made to pass or is unsure,
    the flag stays; a confident "real, needed" drops it."""
    import plumb.judgment as judgment
    from plumb.understand import jobs, worker

    root, base = confirmed
    monkeypatch.setenv("PLUMB_SESSION_ID", "s1")
    monkeypatch.setattr(judgment, "get_backend", lambda *a, **k: pytest.fail("a hook asked"))
    _rewrite_test_to_pass(root)

    [item] = open_verify(open_core(root)).masked_regressions()
    assert item["node"] == "tests/test_mod.py::test_add" and item["judge"]["pending"]
    [job] = jobs.pending(root, "s1")  # queued once, whatever the number of checks
    assert job.kind == "testchange"
    open_verify(open_core(root)).masked_regressions()
    assert len(jobs.queued(root, "s1")) == 1
    # it read the change itself, from the body that passed to the current one ...
    context = job.inputs["context"]
    assert "-    assert add(1, 2) == 3" in context and "+    assert add(1, 2) == -1" in context
    assert f"commit {base}" in context
    # ... against the requirement and its example
    assert "Requirement SR-001: Modules add numbers The module adds numbers." in context
    assert ("EX-1 (verified by this test): given two numbers, when added, then the sum is "
            "returned") in context

    # the judge says it was made just to pass, or is unsure: the flag stays
    for answer in ({"verdict": "to_pass", "probability": 0.95},
                   {"verdict": "real", "probability": 0.5}):
        _judge_answers(tmp_path, monkeypatch, answer)
        open_verify(open_core(root)).masked_regressions()  # queues it again
        assert worker.run_once(open_core(root), "s1") == [job.id]
        [item] = open_verify(open_core(root)).masked_regressions()
        assert not item["judge"]["real"] and not item["judge"].get("pending")
        for path in (jobs.job_path(root, "s1", job.id), jobs.result_path(root, "s1", job.id)):
            path.unlink()
        from plumb.understand import ledger

        ledger.forget(root, "s1", job.id)
        for entry in list(root.glob(".plumb/log/test-change-verdict/*.json")):
            entry.unlink()

    _judge_answers(tmp_path, monkeypatch, {"verdict": "real", "probability": 0.9,
                                           "reason": "subtraction is what SR-001 wants"})
    open_verify(open_core(root)).masked_regressions()
    assert worker.run_once(open_core(root), "s1") == [job.id]
    assert open_verify(open_core(root)).masked_regressions() == []
    _check(root, base, as_json=False)  # SR-002's own regression may still hold it


def test_a_failed_judge_job_keeps_the_flag(confirmed, monkeypatch, tmp_path) -> None:
    from plumb.understand import jobs, worker

    root, _ = confirmed
    monkeypatch.setenv("PLUMB_SESSION_ID", "s1")
    _rewrite_test_to_pass(root)
    open_verify(open_core(root)).masked_regressions()
    _judge_answers(tmp_path, monkeypatch, {"error": "the model could not be reached"})
    [ran] = worker.run_once(open_core(root), "s1")
    assert jobs.result(root, "s1", ran).status == "error"
    [item] = open_verify(open_core(root)).masked_regressions()
    assert item["judge"]["pending"] and not item["judge"]["real"]


# -- SR-030 entry point: validate --merge ------------------------------------------------------


def test_a_counted_full_run_does_not_clear_a_hidden_regression(confirmed, capsys,
                                                              monkeypatch) -> None:
    """SR-207, SR-254 EX-21: a green full run of the merged tree from another checkout counts,
    but the test was rewritten to pass: the hidden regression still holds the merge."""
    from plumb.boundary import fullrun

    root, base = confirmed
    _rewrite_test_to_pass(root)
    monkeypatch.setattr(fullrun, "run_of_merged_tree", lambda core, verify: {"run_id": "r9"})
    code = _check(root, base, as_json=False)
    out = capsys.readouterr().out
    assert code == 5, out
    assert ("failing acceptance tests: SR-001 EX-1 tests/test_mod.py (regression, hidden: the "
            "test was changed to pass and you have not confirmed the change)") in out


def test_merge_holds_a_regression_hidden_by_rewriting_the_test(confirmed, capsys) -> None:
    root, base = confirmed
    _rewrite_test_to_pass(root)
    code = _check(root, base, as_json=False)
    out = capsys.readouterr().out
    assert code == 5, out
    assert ("failing acceptance tests: SR-001 EX-1 tests/test_mod.py (regression, hidden: the "
            "test was changed to pass and you have not confirmed the change)") in out
    assert "SR-001 (acceptance test changed)" in out
    assert "acceptance test changed since you confirmed it: tests/test_mod.py (verifies EX-1)" \
        in out
    assert "EX-1 you confirmed: given two numbers, when added, then the sum is returned" in out
    assert "+    assert add(1, 2) == -1" in out
    assert "confirmation: every touched requirement is confirmed" not in out
    assert cli.main(["validate", "--root", str(root), "--merge", base]) == 5
    capsys.readouterr()
    # the owner looks and confirms the new test: SR-001 no longer waits; SR-002, whose
    # doubling the subtraction broke, still holds the merge until its test is rerun
    approvals.approve(open_core(root), ["SR-001"])
    code = _check(root, base, as_json=False)
    out = capsys.readouterr().out
    assert code == 5, out
    assert "hidden" not in out and "SR-001 (acceptance test changed)" not in out
    assert "unverified acceptance tests: SR-002 EX-1 tests/test_helper.py" in out


def test_merge_lists_a_changed_acceptance_test_for_the_owner(confirmed, capsys) -> None:
    """Listed as waiting, never held (SR-260, DEC-252): the test passes, so nothing holds."""
    root, base = confirmed
    write(root, "tests/test_mod.py", (root / "tests/test_mod.py").read_text("utf-8")
          + "\n\ndef test_add_more():\n    assert add(2, 2) == 4\n")
    assert open_verify(open_core(root)).run(nodes=["tests/test_mod.py"]).ok
    code = _check(root, base, as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert code == 0, data
    assert data["awaiting"][0]["id"] == "SR-001"
    assert data["awaiting"][0]["state"] == "acceptance test changed"
    assert data["awaiting"][0]["changed_tests"] == ["tests/test_mod.py"]


# -- SR-030 entry points: status and drift -----------------------------------------------------


def test_status_and_drift_name_the_changed_acceptance_test(confirmed, capsys) -> None:
    root, _ = confirmed
    _rewrite_test_to_pass(root)
    assert cli.main(["drift", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert ("SR-001 acceptance test changed since you confirmed it: tests/test_mod.py") in out
    assert "SR-001 failing acceptance test: EX-1 tests/test_mod.py (regression, hidden" in out
    assert cli.main(["status", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "acceptance test changed since you confirmed it: SR-001 tests/test_mod.py" in out
    assert "1 failing (SR-001)" in out


# -- SR-030 entry point: the stop hook ---------------------------------------------------------


def _start_turn(root: Path, session: str = "s1") -> None:
    path = root / ".plumb" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}), "utf-8")
    (path.parent / "touched.txt").write_text("src/pkg/mod.py\ntests/test_mod.py\n", "utf-8")


def _stop(root: Path, hook_input, active: bool) -> dict:
    out = io.StringIO()
    payload = hook_input("Stop", session_id="s1", stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=root, unjudged=None) == 0
    return json.loads(out.getvalue()) if out.getvalue().strip() else {}


def test_stop_asks_when_a_test_was_rewritten_to_hide_a_regression(confirmed,
                                                                   hook_input) -> None:
    root, _ = confirmed
    _start_turn(root)
    _rewrite_test_to_pass(root)
    data = _stop(root, hook_input, active=False)
    assert data.get("decision") == "block", data
    reason = data["reason"]
    assert "plumb: regression hidden: tests/test_mod.py::test_add" in reason
    assert ("SR-001 EX-1 \"given two numbers, when added, then the sum is returned\""
            in reason)
    # SR-373, SR-207 EX-2: the owner gets one plain line naming the behaviour, with the block
    owner = data.get("systemMessage", "")
    assert "worked before and now fails" in owner and "SR-001" not in owner, data
    # DEC-384: no card follows; the block named it, and the stop after it adds no owner text
    assert "systemMessage" not in _stop(root, hook_input, active=True)


@pytest.mark.sr("SR-245", "SR-207")
def test_stop_line_says_a_judge_is_reading_while_the_job_is_queued(confirmed, hook_input,
                                                                   monkeypatch) -> None:
    root, _ = confirmed
    monkeypatch.setenv("PLUMB_SESSION_ID", "s1")
    _start_turn(root)
    _rewrite_test_to_pass(root)
    reason = _stop(root, hook_input, active=False)["reason"]
    assert "A judge is reading the change; the flag stays until it answers." in reason


@pytest.mark.sr("SR-245", "SR-207")
def test_stop_line_names_the_judge_and_the_reason_when_the_job_failed(
        confirmed, hook_input, monkeypatch, tmp_path) -> None:
    from plumb.understand import worker

    root, _ = confirmed
    monkeypatch.setenv("PLUMB_SESSION_ID", "s1")
    _start_turn(root)
    _rewrite_test_to_pass(root)
    open_verify(open_core(root)).masked_regressions()
    _judge_answers(tmp_path, monkeypatch, {"error": "the model could not be reached"})
    worker.run_once(open_core(root), "s1")
    reason = _stop(root, hook_input, active=False)["reason"]
    assert "No judge could read the change (" in reason
    assert "the model could not be reached" in reason and "A judge is reading" not in reason


# -- SR-031: the merge boundary's verification guarantee ---------------------------------------


def test_infrastructure_change_holds_the_merge_until_a_full_run_or_an_owner_waiver(
        confirmed, capsys) -> None:
    root, base = confirmed
    write(root, "tests/conftest.py", "import pkg.helper\n\npkg.helper.twice = lambda a: 0\n")
    commit_all(root, "conftest")
    code = _check(root, base, as_json=False)
    out = capsys.readouterr().out
    assert code == 5, out
    assert "full verification pending (tests/conftest.py changed); it holds the merge" in out
    assert "acceptance tests this change can affect (other requirements): SR-001, SR-002" \
        in out
    open_verify(open_core(root)).run(nodes=["tests/test_mod.py", "tests/test_helper.py"])
    code = _check(root, base, as_json=False)
    out = capsys.readouterr().out
    assert code == 5, out
    assert "failing acceptance tests: SR-002 EX-1 tests/test_helper.py (regression)" in out


def test_owner_waiver_of_the_full_run_covers_exactly_this_change(confirmed, capsys) -> None:
    root, base = confirmed
    write(root, "pyproject.toml", (root / "pyproject.toml").read_text("utf-8") + "# note\n")
    commit_all(root, "pyproject comment")
    code = _check(root, base, as_json=False)
    out = capsys.readouterr().out
    assert code == 5, out
    assert "full verification pending (pyproject.toml changed); it holds the merge" in out
    # the owner waives the full run for exactly this change, in their own terminal
    assert cli.main(["tests", "waive", "--root", str(root), "--merge", base,
                     "--reason", "comment only"]) == 0
    capsys.readouterr()
    code = _check(root, base, as_json=False)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "waived by the owner for this exact change" in out
    write(root, "src/pkg/lonely.py", "VALUE = 2\n")  # any later edit voids the waiver
    assert _check(root, base, as_json=False) == 5
    capsys.readouterr()


def test_waiver_is_refused_under_the_agent_marker(confirmed, monkeypatch, capsys) -> None:
    root, base = confirmed
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    assert cli.main(["tests", "waive", "--root", str(root), "--merge", base,
                     "--reason", "x"]) == 3
    capsys.readouterr()


def test_change_to_one_requirement_holds_another_requirements_acceptance_test(
        confirmed, capsys) -> None:
    root, base = confirmed
    # add still passes its own tests, but twice() (SR-002) now breaks
    write(root, "src/pkg/mod.py", "def add(a, b):\n    return a + b if a != b else 0\n")
    assert open_verify(open_core(root)).run(nodes=["tests/test_mod.py"]).ok
    code = _check(root, base, as_json=False)
    out = capsys.readouterr().out
    assert code == 5, out
    assert "touched requirements: SR-001" in out
    assert "acceptance tests this change can affect (other requirements): SR-002" in out
    assert ("unverified acceptance tests: SR-002 EX-1 tests/test_helper.py (stale since its "
            "last pass)") in out
    open_verify(open_core(root)).run(nodes=["tests/test_helper.py"])
    code = _check(root, base, as_json=False)
    out = capsys.readouterr().out
    assert code == 5, out
    assert "failing acceptance tests: SR-002 EX-1 tests/test_helper.py (regression)" in out
