"""SR-396..SR-399 (INT-124): the independent proof evaluator run, with a fake ``claude``."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from plumb import cli
from plumb.api import open_core
from plumb.capture import proof
from plumb.capture.records import CaptureError
from plumb.contracts import Target
from plumb.evaluate import loop, proofcheck, tasks
from plumb.understand import cmd_intent

INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\nreadback: Ground the work.\n---\n"
SR = """---
id: {id}
title: Thing {id}
statement: The thing works.
examples:
- id: EX-1
  given: a thing
  when: it runs
  then: it works
---
"""
IDS = ("SR-001", "SR-002", "SR-003")


@pytest.fixture
def core(repo: Path, write_record):
    write_record(repo, INT)
    for i in IDS:
        write_record(repo, SR.format(id=i))
    c = open_core(repo)
    for i in IDS:
        c.add_link(i, "derives_from", Target(record="INT-001"))
        proof.set_plan(c, i, f"run the {i} command", "command", evaluator=(i != "SR-003"))
    return open_core(repo)


class Fake:
    """A ``claude`` double: writes verdict.json for the requirement the message names."""

    def __init__(self, verdicts=None, barrier=None, touch=None):
        self.verdicts, self.barrier, self.touch = verdicts or {}, barrier, touch
        self.calls = []

    def __call__(self, binary, scratch, message, **kw):
        self.calls.append({"scratch": scratch, "message": message, **kw})
        if self.barrier:
            self.barrier.wait()
        if self.touch:
            (Path(self.touch) / "README.md").write_text("changed\n", encoding="utf-8")
        sr = re.search(r"SR-\d+", message).group()
        verdict = self.verdicts.get(sr, ("verified", f"saw {sr} work"))
        if verdict:
            (scratch / "verdict.json").write_text(
                json.dumps({"verdict": verdict[0], "summary": verdict[1]}), encoding="utf-8")
        return {"text": "done", "session_id": "s", "capped": False, "error": ""}


def go(core, ids, fake, **kw):
    return proofcheck.evaluate_proofs(core, list(ids), claude=fake, binary="claude", **kw)


def test_sr397_ex1_verified_records_evidence_and_confirms(core) -> None:
    rows = go(core, ["SR-001"], Fake())
    core = open_core(core.root)
    assert proof.confirmed(core, "SR-001") and proof.shown_working(core.index()["SR-001"])
    assert core.index()["SR-001"].fields["evidence"]["where"] == \
        Path(rows[0]["run_dir"]).relative_to(core.root).as_posix()
    line = proofcheck.lines(rows)[0]
    assert "SR-001 verified" in line and "ask nothing" in line


@pytest.mark.parametrize("fake", [Fake({"SR-001": None}),
                                  Fake({"SR-001": ("could not check", "needs the owner's screen")})])
def test_sr397_ex3_could_not_check_asks_the_owner_and_writes_nothing(core, fake) -> None:
    rows = go(core, ["SR-001"], fake)
    line = proofcheck.lines(rows)[0]
    assert "could not be checked" in line and "plumb proof SR-001 --ask" in line
    assert "evidence" not in open_core(core.root).index()["SR-001"].fields


def test_sr397_ex7_fresh_session_with_only_the_subject_outside_the_repo(core) -> None:
    fake = Fake()
    go(core, ["SR-001"], fake)
    call = fake.calls[0]
    assert call["session_id"] is None and call["system"] == proofcheck.BRIEF
    for text in ("Thing SR-001", "given a thing; when it runs; then it works",
                 "run the SR-001 command", str(core.root)):
        assert text in call["message"]
    assert core.root not in call["scratch"].parents


def test_sr397_ex8_case_folder_loads_and_plumb_evaluate_case_runs_it(tmp_path, monkeypatch) -> None:
    assert "plumb evaluate case" in proofcheck.BRIEF
    folder = tmp_path / "mycase"
    folder.mkdir()
    (folder / "requests.json").write_text('["hello"]', encoding="utf-8")
    task = tasks.load_case(folder)
    assert (task.name, task.requests, task.agent_brief, task.owner_brief) == \
        ("mycase", ["hello"], "", "")
    seen = []
    monkeypatch.setattr("plumb.evaluate.run.run_task", lambda root, t, **kw: seen.append(t))
    assert cli.main(["evaluate", "case", str(folder), "--root", str(tmp_path)]) == 0
    assert seen == [task]


def test_dec471_an_evaluator_that_changes_the_tree_could_not_check(core) -> None:
    rows = go(core, ["SR-001"], Fake(touch=core.root))
    assert rows[0]["verdict"] == "could not check" and "changed the built tree" in rows[0]["summary"]
    assert "evidence" not in open_core(core.root).index()["SR-001"].fields


def test_dec471_an_edit_to_an_already_changed_file_is_seen(core) -> None:
    (Path(core.root) / "README.md").write_text("dirty before the run\n", encoding="utf-8")
    rows = go(core, ["SR-001"], Fake(touch=core.root))
    assert rows[0]["verdict"] == "could not check" and "changed the built tree" in rows[0]["summary"]


def test_sr397_ex6_reworded_while_the_evaluator_ran_is_not_recorded(core, write_record) -> None:
    def run(root, name, subject, **kw):   # the tree check aside: the verdict's own guard
        write_record(Path(root), SR.format(id="SR-001").replace("works.", "runs."))
        return proofcheck.Verdict(name, "verified", "saw it", Path(root))

    rows = proofcheck.evaluate_proofs(core, ["SR-001"], run=run)
    assert rows[0]["verdict"] == "could not check" and "reworded" in rows[0]["summary"]
    assert not proof.confirmed(open_core(core.root), "SR-001")


def test_one_evaluators_crash_keeps_the_others_verdicts(core) -> None:
    def run(root, name, subject, **kw):
        if name == "SR-002":
            raise RuntimeError("boom")
        return proofcheck.evaluate(root, name, subject, claude=Fake(), binary="claude")

    rows = proofcheck.evaluate_proofs(core, ["SR-001", "SR-002"], run=run)
    assert [r["verdict"] for r in rows] == ["verified", "could not check"]
    assert proof.confirmed(open_core(core.root), "SR-001")


def test_sr396_ex2_no_pick_raises_before_any_run(core) -> None:
    fake = Fake()
    with pytest.raises(ValueError, match="SR-003"):
        go(core, ["SR-001", "SR-003"], fake)
    assert fake.calls == []


def _answer(core, answer: str) -> None:
    core.log_append_many("events", [("question-answer", {
        "session": "s", "via": "question-tool", "question": "How will you see it working?",
        "options": [{"label": proof.EVALUATOR_OPTION}, {"label": "I check it myself"}],
        "answer": answer})])


def test_sr396_ex3_a_pick_needs_the_owners_answer_in_this_loop(core, monkeypatch, capsys) -> None:
    from plumb.capture.capture import capture

    monkeypatch.setenv("PLUMB_SESSION_ID", "s")
    pick = ["proof", "SR-003", "--evaluator", "--root", str(core.root)]
    loop_file = cmd_intent.loop_path(Path(core.root), "s", "d" * 64)
    assert cli.main(pick) != 0 and "did not pick" in capsys.readouterr().err   # never offered
    _answer(core, "I check it myself")
    assert cli.main(pick) != 0                                                 # declined
    _answer(core, proof.EVALUATOR_OPTION)
    cmd_intent.save(loop_file, {"opened_at": "2999-01-01T00:00:00Z", "stages": {}})
    assert cli.main(pick) != 0                                   # picked in an earlier loop
    update = {"updates": [{"id": "SR-003", "proof": {"plan": "p", "kind": "command",
                                                     "evaluator": True}}]}
    with pytest.raises(CaptureError, match="did not pick"):
        capture(open_core(core.root), update)
    cmd_intent.save(loop_file, {"opened_at": "2000-01-01T00:00:00Z", "stages": {}})
    assert cli.main(pick) == 0
    assert proof.evaluator_picked(open_core(core.root).index()["SR-003"])


def test_sr397_ex1_the_owner_is_not_asked_once_the_evaluator_verified(core) -> None:
    go(core, ["SR-001"], Fake())
    with pytest.raises(CaptureError, match="ask nothing"):
        proof.ask(open_core(core.root), "SR-001", "s")


def test_sr398_ex1_not_verified_names_what_was_missing_and_asks_nothing(core) -> None:
    rows = go(core, ["SR-001"], Fake({"SR-001": ("not verified", "the output line is absent")}))
    line = proofcheck.lines(rows)[0]
    assert "not verified: the output line is absent" in line and "owner is not asked" in line


def test_sr398_ex3_second_not_verified_has_no_retry_left(core) -> None:
    fake = Fake({"SR-001": ("not verified", "still absent")})
    go(core, ["SR-001"], fake)
    line = proofcheck.lines(go(open_core(core.root), ["SR-001"], fake))[0]
    assert "still not verified after the retry" in line and "nothing is merged" in line


def test_sr399_ex1_three_evaluators_run_at_the_same_time(core) -> None:
    for i in ("SR-003",):
        proof.set_plan(core, i, None, None, evaluator=True)
    core = open_core(core.root)
    fake = Fake(barrier=threading.Barrier(3, timeout=10))
    rows = go(core, IDS, fake)
    assert len(fake.calls) == 3 and len({r["run_dir"] for r in rows}) == 3
    assert [r["id"] for r in rows] == list(IDS)


def test_sr399_ex2_one_not_verified_leaves_the_others_confirmed(core) -> None:
    proof.set_plan(core, "SR-003", None, None, evaluator=True)
    core = open_core(core.root)
    go(core, IDS, Fake({"SR-002": ("not verified", "missing")}))
    core = open_core(core.root)
    assert [proof.confirmed(core, i) for i in IDS] == [True, False, True]


def test_sr399_ex3_one_id_one_run(core) -> None:
    fake = Fake()
    go(core, ["SR-001"], fake)
    assert len(fake.calls) == 1


def test_sr397_ex1_the_cli_prints_the_lines_and_exits_by_the_verdicts(core, monkeypatch, capsys) -> None:
    fake = Fake({"SR-001": ("not verified", "gap")})
    real = proofcheck.evaluate_proofs
    monkeypatch.setattr(proofcheck, "evaluate_proofs",
                        lambda c, ids, **kw: real(c, ids, claude=fake, binary="claude", **kw))
    assert cli.main(["evaluate", "proof", "SR-001", "--root", str(core.root)]) == 1
    assert "SR-001 not verified: gap" in capsys.readouterr().out
    assert cli.main(["evaluate", "proof", "SR-003", "--root", str(core.root)]) == 2


def test_sr396_ex5_check_runs_once_before_merge_and_a_reason_stops_the_merge(
        tmp_path, monkeypatch, capsys) -> None:
    from plumb.evaluate import issues
    monkeypatch.setattr("plumb.api.open_core", lambda root: object())
    monkeypatch.setattr("plumb.debug.all_cases", lambda root: [])
    monkeypatch.setattr("plumb.debug.report", lambda root, i, text: reports.append(i))
    monkeypatch.setattr("plumb.debug._update", lambda root, ids, **fields: 0)
    monkeypatch.setattr(issues, "open_cases", lambda root, found: ["eval-1", "eval-2"])
    reports, order = [], []
    run = lambda root, task, *, model, **kw: NS(issues=[1], score={})  # noqa: E731
    fix = lambda core, case: NS(state="fixed", branch=f"debug/{case['id']}", detail="d")  # noqa: E731

    def check(root, case, branch):
        order.append(("check", case["id"]))
        return "gap" if case["id"] == "eval-1" else ""

    merge = lambda root, branch: order.append(("merge", branch)) or ""  # noqa: E731
    loop.run_loop(tmp_path, None, model="m", rounds=1, run=run, fix=fix, merge=merge, check=check)
    assert order == [("check", "eval-1"), ("check", "eval-2"), ("merge", "debug/eval-2")]
    assert reports == ["eval-1"] and "not merged" in capsys.readouterr().out


def test_check_fix_returns_empty_when_verified(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("plumb.selfdebug._checked_out", lambda root, branch: tmp_path)
    ok = lambda tree, name, text, **kw: proofcheck.Verdict(name, "verified", "fine", tmp_path)  # noqa: E731
    no = lambda tree, name, text, **kw: proofcheck.Verdict(name, "could not check", "why", tmp_path)  # noqa: E731
    case = {"id": "c1", "detail": "it broke"}
    assert proofcheck.check_fix(tmp_path, case, "b", run=ok) == ""
    assert proofcheck.check_fix(tmp_path, case, "b", run=no) == "why"
    monkeypatch.setattr("plumb.selfdebug._checked_out", lambda root, branch: None)
    assert "no worktree" in proofcheck.check_fix(tmp_path, case, "b", run=ok)
