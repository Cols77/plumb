"""SR-396..SR-398 (INT-124): the evaluator's verdict confirms a proof the way the owner's yes
does; only ``record_verdict`` writes one, and it counts for the words and evidence it saw."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from iaso.api import open_core
from iaso.boundary import landing
from iaso.capture import proof
from iaso.capture.records import CaptureError, record_fields
from iaso.contracts import Target
from iaso.understand import cmd_intent

INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\nreadback: Ground the work.\n---\n"
SR = "---\nid: {id}\ntitle: Thing {id}\nstatement: The thing works.\n---\n"


@pytest.fixture
def core(repo: Path, write_record):
    write_record(repo, INT)
    write_record(repo, SR.format(id="SR-001"))
    write_record(repo, SR.format(id="SR-002"))
    (repo / "run").mkdir()
    (repo / "run" / "out.txt").write_text("ok\n", encoding="utf-8")
    c = open_core(repo)
    for i in ("SR-001", "SR-002"):
        c.add_link(i, "derives_from", Target(record="INT-001"))
    proof.set_plan(c, "SR-001", "run the thing", "command", evaluator=True)
    return open_core(repo)


@pytest.fixture(autouse=True)
def _loop(monkeypatch):
    """Stub the loop file so ``cmd_done`` only judges the proofs of SR-001."""
    monkeypatch.setattr(cmd_intent, "requirements_of", lambda c, i: ["SR-001"])
    monkeypatch.setattr(cmd_intent, "_intent", lambda c, i: None)
    monkeypatch.setattr(cmd_intent, "_find", lambda *a: (Path("x"), {"stages": {}, "digest": "d"}))
    monkeypatch.setattr(cmd_intent, "_passed", lambda d, s: True)
    monkeypatch.setattr(cmd_intent, "_session", lambda a, r: "s")
    for name in ("_stop", "save", "reset_head", "_clean_up"):
        monkeypatch.setattr(cmd_intent, name, lambda *a, **k: None)


def _done(core) -> int:
    return cmd_intent.cmd_done(core, argparse.Namespace(intent="INT-001"))


def _verdict(core, verdict="verified", id="SR-001"):
    return proof.record_verdict(core, id, verdict, "saw it", "run/out.txt")


def test_sr397_ex2_verified_verdict_confirms_done_and_merge(core) -> None:
    assert _verdict(core) == {"verdict": "verified"}
    core = open_core(core.root)
    assert proof.unconfirmed_proofs(core, ["SR-001"]) == []
    assert _done(core) == 0


def test_sr397_ex4_overrule_opens_the_proof_again(core) -> None:
    _verdict(core)
    core = open_core(core.root)
    proof.overrule(core, "SR-001")
    core = open_core(core.root)
    assert [r["id"] for r in proof.unconfirmed_proofs(core, ["SR-001"])] == ["SR-001"]
    assert _done(core) != 0
    with pytest.raises(CaptureError):
        proof.overrule(core, "SR-001")


def test_sr397_ex5_hand_written_evidence_is_not_confirmed(core) -> None:
    proof.set_evidence(core, "SR-001", "run/out.txt", "by hand", passed=True)
    core = open_core(core.root)
    assert [r["id"] for r in proof.unverified(core, ["SR-001"])] == ["SR-001"]
    assert [r["id"] for r in proof.unconfirmed_proofs(core, ["SR-001"])] == ["SR-001"]
    assert _done(core) != 0


def test_sr397_ex6_reworded_after_the_verdict_is_not_confirmed(core) -> None:
    _verdict(core)
    core = open_core(core.root)
    record = core.index()["SR-001"]
    fields = record_fields(record)
    fields["statement"] = "The thing works differently."
    core.write_record("requirement", fields, record.body, record_id="SR-001")
    core = open_core(core.root)
    assert not proof.evaluator_confirmed(core, "SR-001")
    assert [r["id"] for r in proof.unconfirmed_proofs(core, ["SR-001"])] == ["SR-001"]


def test_sr398_ex1_not_verified_fails_the_evidence_and_keeps_done_closed(core) -> None:
    assert _verdict(core, "not verified") == {"verdict": "not verified", "retry_left": True}
    core = open_core(core.root)
    assert core.index()["SR-001"].fields["evidence"]["passed"] is False
    assert _done(core) != 0


def test_sr398_ex2_verified_after_the_retry_confirms(core) -> None:
    _verdict(core, "not verified")
    _verdict(open_core(core.root))
    assert proof.evaluator_confirmed(open_core(core.root), "SR-001")


def test_sr398_ex3_second_not_verified_has_no_retry_left(core) -> None:
    _verdict(core, "not verified")
    assert _verdict(open_core(core.root), "not verified")["retry_left"] is False
    core = open_core(core.root)
    assert _done(core) != 0
    assert [r["id"] for r in proof.unconfirmed_proofs(core, ["SR-001"])] == ["SR-001"]


def test_sr397_ex3_could_not_check_writes_nothing(core) -> None:
    assert _verdict(core, "could not check") == {"verdict": "could not check"}
    assert open_core(core.root).index()["SR-001"].fields.get("evidence") is None
    with pytest.raises(CaptureError):
        _verdict(core, "maybe")


def test_sr396_ex3_the_pick_is_not_carried_to_another_requirement(core) -> None:
    index = open_core(core.root).index()
    assert proof.evaluator_picked(index["SR-001"])
    proof.set_plan(core, "SR-002", "run it", "command")
    assert not proof.evaluator_picked(open_core(core.root).index()["SR-002"])


def test_sr396_ex4_landing_names_the_evaluator_for_a_post_merge_proof(core) -> None:
    proof.set_plan(core, "SR-001", "run the thing", "command", post=True)
    proof.set_plan(core, "SR-002", "run it", "command", post=True)
    lines = dict(landing.proof_lines(Path(core.root), ["SR-001", "SR-002"]))
    picked, plain = lines["post-merge-proof:SR-001"], lines["post-merge-proof:SR-002"]
    assert "iaso evaluate proof SR-001" in picked and "--ask" not in picked
    assert "--ask" in plain and "evaluate" not in plain


@pytest.mark.sr("SR-397")
def test_a_verdict_names_its_evidence_by_repo_path_or_not_kept(core, tmp_path_factory) -> None:
    """report-bb6888e4: the evaluator passes its run directory as an absolute path; the record
    and the tracked proof-verified entry keep it repo-relative, or ``<name> (not kept)``
    outside the repository, never the machine path."""
    proof.record_verdict(core, "SR-001", "verified", "saw it", str(core.root / "run" / "out.txt"))
    outside = tmp_path_factory.mktemp("elsewhere") / "run-7"
    outside.mkdir()
    proof.set_plan(open_core(core.root), "SR-002", "run it", "command", evaluator=True)
    proof.record_verdict(open_core(core.root), "SR-002", "verified", "saw it", str(outside))
    core = open_core(core.root)
    logged = {e.payload["record"]: e.payload["where"] for e in core.events()
              if e.kind == proof.VERIFIED}
    assert logged == {"SR-001": "run/out.txt", "SR-002": "run-7 (not kept)"}
    assert [proof.evidence_of(core.index()[i])["where"] for i in ("SR-001", "SR-002")] == [
        "run/out.txt", "run-7 (not kept)"]
