"""SP8 lane JUDGE, J6: the re-check of settled approvals and undone revocations, the owner's
Undo (SR-105 EX-3, EX-6; SR-106 EX-3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from understand.fakes import as_worker
from understand.test_judge_job import log_prompt
from understand.test_settle import (
    MESSAGE,
    SESSION,
    calibration_passing,
    judged,
    make_world,
    settling_on,
)

pytestmark = pytest.mark.sr("SR-105")


@pytest.fixture(autouse=True)
def in_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)


def settled_world(repo: Path, write_record, count: int = 1) -> tuple[Any, list[str]]:
    """Settling on, one verdict applied and written by the worker; returns the settled entry."""
    ids = make_world(repo, write_record, count)
    settling_on(open_core(repo))
    _, applied = judged(open_core(repo), ids, [0.95] * count)
    core = open_core(repo)
    with as_worker(repo, SESSION):
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])
    approval = next(e for e in open_core(repo).events()
                    if e.kind == "approval" and e.payload.get("by") == "settled")
    return approval, ids


def forge(repo: Path, **changes: Any) -> Any:
    """A hand-written settled approval of SR-001 (the agent dropping an entry in the log,
    which never passes through the log's guard of the worker token)."""
    from plumb.approvals import approval_items

    core = open_core(repo)
    payload = {"records": approval_items(core, ["SR-001"]), "by": "settled",
               "session": SESSION, "job": "judge-forged", "model": "fake", "score": 0.99,
               "premise_digest": "sha256:" + "1" * 64, "calibration": "sha256:" + "2" * 64,
               **changes}
    with as_worker(repo, SESSION):
        return core.log_append("events", "approval", payload)


def problem(repo: Path, entry: Any, core: Any | None = None) -> str | None:
    from plumb.understand import recheck_settled

    return recheck_settled.problem(entry, core or open_core(repo))


def test_a_real_settled_entry_passes_its_recheck(repo: Path, write_record) -> None:
    approval, _ = settled_world(repo, write_record)
    assert problem(repo, approval) is None
    assert problem(repo, approval, core=None) is None            # no context: the repo it runs in
    status = open_core(repo).status(["SR-001"])["SR-001"]
    assert status.confirmation == "confirmed" and status.settled is True


def test_forged_settled_entry_is_a_problem(repo: Path, write_record) -> None:
    make_world(repo, write_record, 1)
    settling_on(open_core(repo))
    forged = forge(repo)
    assert "no judgment" in problem(repo, forged)
    status = open_core(repo).status(["SR-001"])["SR-001"]
    assert status.confirmation == "proposed" and status.settled is False
    # a shape that is not even an approval of a record at a version
    from plumb.understand import recheck_settled

    bare = type(forged)(forged.stream, "approval", forged.at, forged.marker,
                        {"by": "settled", "records": []}, forged.prev, forged.digest)
    assert "no record" in recheck_settled.problem(bare, None)


def test_a_forged_entry_next_to_a_real_judgment_still_differs(repo: Path,
                                                               write_record) -> None:
    approval, _ = settled_world(repo, write_record)
    payload = dict(approval.payload)
    for change, text in (({"score": 0.999}, "differs"), ({"model": "other"}, "differs"),
                         ({"premise_digest": "sha256:" + "3" * 64}, "differs"),
                         ({"calibration": "sha256:" + "4" * 64}, "calibration"),
                         ({"job": "judge-other"}, "no judgment")):
        forged = forge(repo, **{**payload, **change})
        assert text in (problem(repo, forged) or ""), change


def test_settled_while_settling_was_off_is_a_problem(repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 1)
    calibration_passing(open_core(repo))                  # passing, but settling never switched on
    _, applied = judged(open_core(repo), ids, [0.95])
    verdict = next(e["payload"] for e in applied.entries if e["kind"] == "verdict")
    open_core(repo).log_append("events", "verdict", verdict)
    forged = forge(repo, job=verdict["job"], score=verdict["score"], model=verdict["model"],
                   premise_digest=verdict["premise_digest"],
                   calibration=open_core(repo).events()[0].digest)
    assert "settling was not on" in problem(repo, forged) or "no passing" in problem(repo, forged)


def test_a_decision_is_never_settled(repo: Path, write_record) -> None:
    from plumb.approvals import approval_items
    from plumb.understand import judge
    from understand.test_judge_job import decision_text

    ids = make_world(repo, write_record, 1)
    write_record(repo, decision_text(1, "Which radix?", "decimal", intent=1))
    cal = settling_on(open_core(repo))
    job = judge.build(open_core(repo), SESSION, records=["DEC-001"])
    core = open_core(repo)
    applied = judge.apply(core, job, {"verdicts": [{"id": "DEC-001", "verdict": "supported",
                                                    "confidence": 0.99}]})
    verdict = next(e["payload"] for e in applied.entries if e["kind"] == "verdict")
    core.log_append("events", "verdict", verdict)
    with as_worker(repo, SESSION):
        entry = core.log_append("events", "approval", {
            "records": approval_items(core, ["DEC-001"]), "by": "settled", "session": SESSION,
            "job": job.id, "model": verdict["model"], "score": 0.99,
            "premise_digest": verdict["premise_digest"], "calibration": cal.digest})
    assert "never settled" in problem(repo, entry)
    assert ids


def test_changed_premise_invalidates(repo: Path, write_record) -> None:
    approval, _ = settled_world(repo, write_record)
    other = log_prompt(repo, "Something else entirely, said later.")
    path = repo / ".plumb" / "intents" / "INT-001.md"
    import hashlib

    old = hashlib.sha256(MESSAGE.encode("utf-8")).hexdigest()[:16]
    path.write_text(path.read_text(encoding="utf-8").replace(
        f"prompt: {old}", f"prompt: {other.removeprefix('sha256:')[:16]}"), encoding="utf-8")
    assert "the words it rests on have changed" in problem(repo, approval)


def test_text_change_needs_no_recheck_the_pin_moves(repo: Path, write_record) -> None:
    settled_world(repo, write_record)
    path = repo / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace("operation 1", "operation one"),
                    encoding="utf-8")
    status = open_core(repo).status(["SR-001"])["SR-001"]
    assert status.confirmation == "unconfirmed-edit"


# ---- undone ---------------------------------------------------------------------------------


def undo_entry(repo: Path, record_id: str = "SR-001", **payload: Any) -> Any:
    core = open_core(repo)
    record = core.index()[record_id]
    return core.log_append("events", "revocation", {
        "records": [{"id": record_id, "hash": record.hash}], "by": "undone", "via": "typed",
        **payload})


def test_undone_only_by_typed_or_button(repo: Path, write_record,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.approvals import prompt_digest

    settled_world(repo, write_record)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    by_agent = undo_entry(repo)                                    # the agent, no proof
    assert problem(repo, by_agent) is not None
    assert open_core(repo).status(["SR-001"])["SR-001"].settled is True    # nothing undone
    prose = "undo that"
    by_prose = undo_entry(repo, quote=prose, prompt_digest=prompt_digest(prose))
    assert problem(repo, by_prose) is not None
    typed = "/plumb undo Operation 1"
    proven = undo_entry(repo, quote=typed, prompt_digest=prompt_digest(typed))
    assert problem(repo, proven) is None
    assert open_core(repo).status(["SR-001"])["SR-001"].confirmation == "proposed"
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    button = undo_entry(repo, via="button")                        # the owner's own terminal
    assert problem(repo, button) is None
    assert problem(repo, undo_entry(repo, via="whisper")) is not None


def run_undo(repo: Path, *argv: str) -> int:
    from plumb.understand import cmd_settle

    return cmd_settle.run("undo", [*argv, "--root", str(repo)])


def test_undo_by_the_typed_command_names_the_record_by_its_title(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    settled_world(repo, write_record)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    typed = log_prompt(repo, "/plumb undo Operation 1")
    assert run_undo(repo, "Operation", "1", "--prompt", typed) == 0
    out = capsys.readouterr().out
    assert "Operation 1" in out and "proposed again" in out
    status = open_core(repo).status(["SR-001"])["SR-001"]
    assert status.confirmation == "proposed" and status.settled is False


def test_ex6_undo_in_prose_undoes_nothing_and_names_the_button_and_the_command(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """SR-105 EX-6."""
    settled_world(repo, write_record)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    prose = log_prompt(repo, "undo that")
    assert run_undo(repo, "that", "--prompt", prose) == 3
    err = capsys.readouterr().err
    assert "Undo button" in err and "/plumb undo" in err
    assert run_undo(repo, "Operation", "1") == 3                    # the agent's shell
    assert open_core(repo).status(["SR-001"])["SR-001"].settled is True


def test_undo_from_the_owners_terminal_by_id_or_title(repo: Path, write_record,
                                                       capsys) -> None:
    settled_world(repo, write_record, 2)
    assert run_undo(repo, "SR-002") == 0
    assert run_undo(repo, "Nothing", "like", "this") == 2
    assert "Nothing settled is called" in capsys.readouterr().out
    statuses = open_core(repo).status(["SR-001", "SR-002"])
    assert statuses["SR-001"].settled is True and statuses["SR-002"].settled is False


def test_sr105_ex3_undone_record_proposed_again_and_carded(repo: Path, write_record,
                                                           capsys) -> None:
    from plumb.understand import cards, cardstore, recheck_settled

    settled_world(repo, write_record)
    assert run_undo(repo, "SR-001") == 0
    core = open_core(repo)
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    assert [r for r, _ in recheck_settled.undone_records(core)] == ["SR-001"]
    (card,) = cards.undone_cards(core, SESSION)
    assert card.kind == "show_first" and card.topic == "Operation 1"
    assert card.questions[0].record == "SR-001" and card.evidence
    cardstore.save(repo, SESSION, [card])
    assert cards.undone_cards(open_core(repo), SESSION) == []       # carded once
    # the owner confirmed it again meanwhile: no card
    from understand.test_judge_job import approve

    approve(open_core(repo), "SR-001")
    cardstore.save(repo, SESSION, [])
    assert cards.undone_cards(open_core(repo), SESSION) == []


def test_an_undone_settling_is_a_labelled_no(repo: Path, write_record) -> None:
    from plumb.capture import calibrate

    settled_world(repo, write_record)
    assert run_undo(repo, "SR-001") == 0
    labels = [(i.record, i.label, i.source) for i in calibrate.labelled_set(open_core(repo))
              if i.source == "revoked"]
    assert labels == [("SR-001", "no", "revoked")]
