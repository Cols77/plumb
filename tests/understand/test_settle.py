"""SP8 lane JUDGE, J5: settling (SR-106 EX-3, EX-5; SR-102 EX-5; spec 7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from understand.fakes import as_worker
from understand.test_judge_job import (
    approve,
    decision_text,
    intent_text,
    log_prompt,
    requirement_text,
    verdict_answer,
)

pytestmark = pytest.mark.sr("SR-106")

SESSION = "s1"


@pytest.fixture(autouse=True)
def in_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The re-check of a settled entry reads the log of the repository it runs in."""
    monkeypatch.chdir(repo)


MESSAGE = "Build a calculator with add, subtract, multiply and divide."


def make_world(repo: Path, write_record, count: int = 2) -> list[str]:
    digest = log_prompt(repo, MESSAGE)
    write_record(repo, intent_text(1, "Build a calculator", "A calculator", prompt=digest))
    ids = []
    for n in range(1, count + 1):
        write_record(repo, requirement_text(
            n, f"Operation {n}", f"The calculator does operation {n}", intent=1,
            examples=((f"input {n}", "it runs", f"output {n}"),)))
        ids.append(f"SR-{n:03d}")
    return ids


def calibration_passing(core: Any, threshold: float = 0.8,
                        kinds: tuple[str, ...] = ("example-restatement",)) -> Any:
    """A passing judge calibration under the current model and prompt."""
    from plumb.capture.calibrate import fingerprint

    return core.log_append("events", "calibration", {
        "backend": "judge", "model_version": "fake", "source": "logged",
        "per_kind": {k: {"passing": True, "threshold": threshold} for k in kinds},
        **fingerprint(core)})


def settling_on(core: Any, kind: str = "requirement", **cal: Any) -> Any:
    """Calibration passes and settling for ``kind`` is on (as plumb switches it on itself)."""
    kinds = ("example-restatement",) if kind == "requirement" else ("intent-readback",)
    entry = calibration_passing(core, kinds=kinds, **cal)
    core.log_append("events", "settle-config", {"kind": kind, "on": True, "via": "calibration",
                                                "calibration": entry.digest})
    return entry


def judged(core: Any, ids: list[str], scores: list[float], verdict: str = "supported"):
    from plumb.understand import judge

    job = judge.build(core, SESSION, records=ids)
    assert job is not None
    answer = verdict_answer(*((i, verdict, s) for i, s in zip(ids, scores, strict=True)))
    return job, judge.apply(core, job, answer)


def approvals(applied: Any) -> list[dict[str, Any]]:
    return [e["payload"] for e in applied.entries if e["kind"] == "approval"]


def test_a_supported_record_settles_when_settling_is_on_and_the_score_passes(
        repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 2)
    core = open_core(repo)
    calibration = settling_on(core, threshold=0.8)
    job, applied = judged(open_core(repo), ids, [0.95, 0.7])
    (settled,) = approvals(applied)
    assert settled["by"] == "settled" and settled["job"] == job.id
    assert [r["id"] for r in settled["records"]] == ["SR-001"]
    assert settled["records"][0]["hash"] == open_core(repo).index()["SR-001"].hash
    assert settled["score"] == 0.95 and settled["model"]
    assert settled["calibration"] == calibration.digest
    verdict = next(e["payload"] for e in applied.entries
                   if e["kind"] == "verdict" and e["payload"]["id"] == "SR-001")
    assert settled["premise_digest"] == verdict["premise_digest"] != ""
    assert settled["session"] == SESSION
    waiting = [q.record for c in applied.cards if c.kind == "trial" for q in c.questions]
    assert waiting == ["SR-002"]                       # below the threshold: a trial card


def test_nothing_settles_while_settling_is_off(repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 1)
    calibration_passing(open_core(repo))
    _, applied = judged(open_core(repo), ids, [0.99])
    assert approvals(applied) == []
    assert [c.kind for c in applied.cards] == ["trial"]


def test_a_settled_entry_is_written_by_the_worker_and_counts_as_confirmed(
        repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 1)
    settling_on(open_core(repo))
    _, applied = judged(open_core(repo), ids, [0.95])
    core = open_core(repo)
    (payload,) = approvals(applied)
    with pytest.raises(Exception, match="worker"):
        core.log_append("events", "approval", payload)          # not the worker: refused
    with as_worker(repo, SESSION):
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])
    status = open_core(repo).status(["SR-001"])["SR-001"]
    assert status.confirmation == "confirmed" and status.settled is True
    assert status.approved_by == "settled"


def test_ex5_decision_set_member_owner_edit_never_settled(repo: Path, write_record) -> None:
    """SR-106 EX-5 and SR-102 EX-5: each waits as a trial or confirm card."""
    ids = make_world(repo, write_record, 3)
    write_record(repo, decision_text(1, "Which radix?", "decimal", intent=1,
                                     alternatives=("binary",)))
    # SR-002 is a member of an escalated set: its anchor lists it
    write_record(repo, intent_text(2, "Plan the whole thing", "The whole plan",
                                   prompt=log_prompt(repo, "Plan it all up front."))
                 .replace("mode: incremental", "mode: escalated\nmembers:\n- SR-002"))
    # SR-003 was confirmed by the owner and then edited
    core = open_core(repo)
    approve(core, "SR-003")
    path = repo / ".plumb" / "requirements" / "SR-003.md"
    path.write_text(path.read_text(encoding="utf-8").replace("operation 3", "operation three"),
                    encoding="utf-8")
    settling_on(open_core(repo))
    _, applied = judged(open_core(repo), ids + ["DEC-001"], [0.99, 0.99, 0.99, 0.99])
    assert [a["records"][0]["id"] for a in approvals(applied)] == ["SR-001"]
    carded = {q.record for c in applied.cards if c.kind == "trial" for q in c.questions}
    assert carded == {"SR-002", "SR-003", "DEC-001"}


def test_an_intent_with_a_bare_option_answer_never_settles(repo: Path, write_record) -> None:
    digest = log_prompt(repo, "B")
    write_record(repo, intent_text(1, "B", "Two logs", prompt=digest,
                                   question="One log or two? A: one. B: two."))
    core = open_core(repo)
    entry = calibration_passing(core, kinds=("intent-readback",))
    core.log_append("events", "settle-config", {
        "kind": "intent", "on": True, "via": "typed", "calibration": entry.digest})
    _, applied = judged(open_core(repo), ["INT-001"], [0.99])
    assert approvals(applied) == []
    (card,) = [c for c in applied.cards if c.kind == "trial"]
    assert card.questions[0].record == "INT-001"


def test_a_yes_to_one_proposal_shown_whole_may_settle(repo: Path, write_record) -> None:
    digest = log_prompt(repo, "yes")
    write_record(repo, intent_text(1, "yes", "Two logs", prompt=digest,
                                   question="Shall I keep two logs, one per stream?"))
    core = open_core(repo)
    entry = calibration_passing(core, kinds=("intent-readback",))
    core.log_append("events", "settle-config", {
        "kind": "intent", "on": True, "via": "typed", "calibration": entry.digest})
    _, applied = judged(open_core(repo), ["INT-001"], [0.99])
    assert len(approvals(applied)) == 1


def test_ex3_premise_message_edited_record_proposed_again(repo: Path, write_record) -> None:
    """SR-106 EX-3: a settled record whose premise message is edited is proposed again."""
    from plumb.understand import settle

    ids = make_world(repo, write_record, 1)
    settling_on(open_core(repo))
    _, applied = judged(open_core(repo), ids, [0.95])
    with as_worker(repo, SESSION):
        core = open_core(repo)
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])
    assert open_core(repo).status(["SR-001"])["SR-001"].settled is True
    assert settle.revalidate(open_core(repo)) == []             # nothing has moved
    # the owner's message the record rests on is replaced by another one
    other = log_prompt(repo, "Something else entirely, said later.")
    path = repo / ".plumb" / "intents" / "INT-001.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(f"prompt: {_prefix(repo, MESSAGE)}",
                                 f"prompt: {other.removeprefix('sha256:')[:16]}"),
                    encoding="utf-8")
    again = settle.revalidate(open_core(repo))
    assert again == ["SR-001"]
    status = open_core(repo).status(["SR-001"])["SR-001"]
    assert status.confirmation == "proposed" and status.settled is False
    assert settle.revalidate(open_core(repo)) == []             # said once


def _prefix(repo: Path, text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def test_a_settled_records_text_change_returns_it_to_proposed(repo: Path,
                                                               write_record) -> None:
    ids = make_world(repo, write_record, 1)
    settling_on(open_core(repo))
    _, applied = judged(open_core(repo), ids, [0.95])
    with as_worker(repo, SESSION):
        core = open_core(repo)
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])
    path = repo / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace("operation 1", "operation one"),
                    encoding="utf-8")
    status = open_core(repo).status(["SR-001"])["SR-001"]
    assert status.confirmation == "unconfirmed-edit" and status.settled is False


def test_eligibility_names_why_a_record_is_never_settled(repo: Path, write_record) -> None:
    from plumb.understand import settle

    make_world(repo, write_record, 1)
    write_record(repo, decision_text(1, "Which radix?", "decimal", intent=1))
    core = open_core(repo)
    assert settle.ineligible(core, core.index()["DEC-001"]) == settle.DECISION
    assert settle.ineligible(core, core.index()["SR-001"]) == ""
    assert settle.ineligible(core, core.index()["INT-001"]) == ""
