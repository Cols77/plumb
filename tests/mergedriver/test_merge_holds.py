"""SR-260 (DEC-252, DEC-255 to DEC-257): what holds a merge, and what is only listed: a proof
the owner has not confirmed holds a merge into the default branch (EX-28) and only that one
(EX-29), a question waiting for the owner holds (EX-30), records waiting on a judge are
counted and never hold (EX-31); ``plumb proof --ask`` and the question-answer hook carry the
owner's yes."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from mergedriver.mdhelpers import commit_all, ex, make_repo, record, run_git, write_record
from plumb import cli
from plumb.api import open_core
from plumb.boundary.premerge import check
from plumb.capture import proof
from plumb.hosts.claude_code import question_answer

pytestmark = pytest.mark.sr("SR-260")

TITLE = "links pin both ends"


def _sr001(root: Path) -> None:
    write_record(root, record("SR-001", TITLE, statement="Both ends are pinned.",
                              examples=[ex(1)]))


def _branch(root: Path, name: str, where: Path) -> Path:
    run_git(root, "worktree", "add", "-q", "-b", name, str(where))
    return where


def _change(root: Path, rel: str, message: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{message}\n", encoding="utf-8")
    commit_all(root, message)


def _shown(root: Path) -> None:
    core = open_core(root)
    proof.set_plan(core, "SR-001", "run plumb show SR-001", "command")
    proof.set_evidence(open_core(root), "SR-001", "https://x.test/run", "it printed both pins",
                       passed=True)


def _answer(root: Path, hook_input, asked: dict, answer: str) -> None:
    question = asked["questions"][0]["question"]
    payload = hook_input("PostToolUse", tool_name="AskUserQuestion", tool_input=asked,
                         tool_response={"answers": {question: answer}})
    assert question_answer.main(stdin=io.StringIO(payload), stdout=io.StringIO(),
                                root=root) == 0


@pytest.fixture
def delivered(tmp_path: Path) -> tuple[Path, Path]:
    """main holds SR-001; feat-x delivers it (its commit's SR trailer) with a proof shown
    working; main moved too, so the merge records a merge commit."""
    root = make_repo(tmp_path / "main")
    _sr001(root)
    commit_all(root, "SR-001")
    feat = _branch(root, "feat-x", tmp_path / "feat")
    _shown(feat)
    _change(feat, "src/x.py", "deliver\n\nSR: SR-001")
    _change(root, "notes.txt", "main side")
    return root, feat


def test_unconfirmed_proof_holds_a_merge_into_main_until_the_owner_says_yes(
        delivered, hook_input) -> None:
    """EX-28: shown working, not confirmed: exit 5 naming SR-001's proof by title; after the
    owner's yes in the question tool, exit 0."""
    root, _ = delivered
    run_git(root, "merge", "--no-commit", "--no-ff", "--no-verify", "feat-x")
    report = check(open_core(root))
    assert report.exit == 5, report.lines
    assert [(r["id"], r["why"]) for r in report.proofs] == [("SR-001", "not confirmed by you")]
    text = "\n".join(report.lines)
    assert f'"{TITLE}": you have not said you saw it working' in text
    asked = proof.ask(open_core(root), "SR-001", "test-session")
    _answer(root, hook_input, asked, proof.YES)
    assert proof.owner_confirmed(open_core(root), "SR-001")
    run_git(root, "add", "-A", ".plumb")       # the answer's log entry goes with the merge
    report = check(open_core(root))
    assert report.exit == 0, report.lines


def test_a_proof_never_shown_holds_a_merge_into_main(tmp_path: Path) -> None:
    """EX-26, EX-28: a delivered requirement with no evidence holds the merge into main, by
    title, before the owner can be asked."""
    root = make_repo(tmp_path / "main")
    _sr001(root)
    commit_all(root, "SR-001")
    feat = _branch(root, "feat-x", tmp_path / "feat")
    _change(feat, "src/x.py", "deliver\n\nSR: SR-001")
    _change(root, "notes.txt", "main side")
    run_git(root, "merge", "--no-commit", "--no-ff", "--no-verify", "feat-x")
    report = check(open_core(root))
    assert report.exit == 5
    assert f'"{TITLE}": its proof is not shown working yet' in "\n".join(report.lines)


def test_main_merged_into_a_feature_branch_holds_no_proof(tmp_path: Path) -> None:
    """EX-29: main's commits name SR-001, its proof unconfirmed; merging main into feat-y:
    no proof holds."""
    root = make_repo(tmp_path / "main")
    _sr001(root)
    commit_all(root, "SR-001")
    feat = _branch(root, "feat-y", tmp_path / "feat")
    _change(root, "src/x.py", "deliver on main\n\nSR: SR-001")
    _change(feat, "notes.txt", "feature side")
    run_git(feat, "merge", "--no-commit", "--no-ff", "--no-verify", "main")
    report = check(open_core(feat))
    assert report.proofs == () and report.exit == 0, report.lines


def test_a_question_waiting_for_the_owner_holds_with_4(tmp_path: Path) -> None:
    """EX-30: an open judge question about SR-001, which the merge touches: exit 4, and the
    report says a question waits for the owner, by the record's title."""
    root = make_repo(tmp_path / "main")
    _sr001(root)
    commit_all(root, "SR-001")
    feat = _branch(root, "feat-y", tmp_path / "feat")
    _change(root, "src/x.py", "work\n\nSR: SR-001")
    _change(feat, "notes.txt", "feature side")
    core = open_core(feat)
    question = "Should links pin both ends?"
    path = feat / ".plumb" / "session" / "s1" / "judge_questions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{
        "key": question.lower(), "question": question, "header": "Pins", "job": "j1",
        "options": [{"label": "yes", "description": ""}],
        "records": [{"id": "SR-001", "hash": core.index()["SR-001"].hash}]}]),
        encoding="utf-8")
    run_git(feat, "merge", "--no-commit", "--no-ff", "--no-verify", "main")
    report = check(open_core(feat))
    assert report.exit == 4, report.lines
    assert [q["records"] for q in report.questions] == [["SR-001"]]
    assert f'a question waits for you on "{TITLE}"' in "\n".join(report.lines)


def test_forty_records_waiting_on_a_judge_are_counted_and_do_not_hold(tmp_path: Path) -> None:
    """EX-31: the merge's only finding is 40 touched requirements waiting on a judge: they
    are listed, counted, and the check exits 0."""
    root = make_repo(tmp_path / "main")
    for n in range(101, 141):
        write_record(root, record(f"SR-{n}", f"rule {n}", statement=f"Rule {n} holds.",
                                  examples=[ex(1)]))
    commit_all(root, "forty")
    feat = _branch(root, "feat-y", tmp_path / "feat")
    trailer = ", ".join(f"SR-{n}" for n in range(101, 141))
    _change(root, "src/y.py", f"touch forty\n\nSR: {trailer}")
    _change(feat, "notes.txt", "feature side")
    run_git(feat, "merge", "--no-commit", "--no-ff", "--no-verify", "main")
    report = check(open_core(feat))
    assert len(report.unconfirmed) == 40
    text = "\n".join(report.lines)
    assert "40 requirements this merge touches wait on a judge (listed; this does not hold " \
           "the merge):" in text
    assert "+30 more" in text
    assert report.exit == 0, report.lines


# --------------------------------------------------------------------------- proof --ask


def test_ask_is_refused_until_the_evidence_passed(tmp_path: Path, capsys) -> None:
    """DEC-257: the agent asks only once its evidence showed it working; nothing is filed."""
    root = make_repo(tmp_path / "main")
    _sr001(root)
    assert cli.main(["proof", "SR-001", "--ask", "--root", str(root)]) != 0
    assert "not shown working" in capsys.readouterr().err
    assert not list((root / ".plumb" / "session").glob("*/" + proof.QUESTIONS_FILE))


def test_ask_prints_the_question_and_files_it(tmp_path: Path, capsys,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_repo(tmp_path / "main")
    _sr001(root)
    _shown(root)
    monkeypatch.setenv("PLUMB_SESSION_ID", "s9")
    capsys.readouterr()
    assert cli.main(["proof", "SR-001", "--ask", "--root", str(root)]) == 0
    (asked,) = json.loads(capsys.readouterr().out)["questions"]
    assert asked["question"].startswith(f"Did you see {TITLE} working?\n\nit printed both pins")
    assert asked["header"] == "Proof"
    assert [o["label"] for o in asked["options"]] == [proof.YES, proof.NO]
    record = open_core(root).index()["SR-001"]
    (pending,) = proof.pending(root, "s9")
    assert pending["record"] == "SR-001" and pending["hash"] == record.hash
    assert pending["evidence_at"] == record.fields["evidence"]["at"]


def test_the_hook_tags_the_answer_and_only_yes_confirms(tmp_path: Path, hook_input) -> None:
    """DEC-257: the answer to a pending proof question carries ``proof``; the pending
    question goes; "No, not yet" confirms nothing; new evidence needs a new yes."""
    root = make_repo(tmp_path / "main")
    _sr001(root)
    _shown(root)
    asked = proof.ask(open_core(root), "SR-001", "test-session")
    _answer(root, hook_input, asked, proof.NO)
    (entry,) = open_core(root).log_read("events", ["question-answer"])
    assert entry.payload["proof"]["record"] == "SR-001"
    assert proof.pending(root, "test-session") == []
    assert not proof.owner_confirmed(open_core(root), "SR-001")
    asked = proof.ask(open_core(root), "SR-001", "test-session")
    _answer(root, hook_input, asked, proof.YES)
    assert proof.owner_confirmed(open_core(root), "SR-001")
    proof.set_evidence(open_core(root), "SR-001", "https://x.test/run2", "printed again",
                       passed=True, at="2099-01-01T00:00:00Z")
    assert not proof.owner_confirmed(open_core(root), "SR-001")


def test_an_unrelated_answer_carries_no_proof(tmp_path: Path, hook_input) -> None:
    root = make_repo(tmp_path / "main")
    _sr001(root)
    _shown(root)
    proof.ask(open_core(root), "SR-001", "test-session")
    other = {"questions": [{"question": "Did you see it working?", "header": "x",
                            "options": [{"label": proof.YES, "description": ""}],
                            "multiSelect": False}]}
    _answer(root, hook_input, other, proof.YES)
    (entry,) = open_core(root).log_read("events", ["question-answer"])
    assert "proof" not in entry.payload
    assert not proof.owner_confirmed(open_core(root), "SR-001")
    assert len(proof.pending(root, "test-session")) == 1
