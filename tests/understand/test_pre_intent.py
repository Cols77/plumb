"""The pre-intent with its context, and the trail (task 6 of the judge-approval plan). The judge
worker keeps each source of a judged premise once as a ``pre-intent``: the owner's words
verbatim, the question and options they answered and the excerpt of the reply they answered;
an approval names those sources in its ``trail``. A message answering what the last reply
showed is kept the same way, naming only the records the reading covers, and judged with them.
JEV and the model are stubs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "capture"))
from capture_helpers import run as iaso_run  # noqa: E402

from iaso.api import open_core  # noqa: E402
from iaso.understand import clarify, files, jobs, read  # noqa: E402
from understand import test_judge_cascade  # noqa: E402
from understand.fakes import FakeDispatcher, as_worker  # noqa: E402
from understand.test_cascade_fast_track import approvals, judged, model_for, write  # noqa: E402
from understand.test_judge_cascade import StubJev, configure, fast_track_on  # noqa: E402
from understand.test_judge_job import (  # noqa: E402
    SESSION,
    decision_text,
    intent_text,
    log_prompt,
    requirement_text,
)
from understand.test_read_apply import entry_of, write_applied  # noqa: E402
from understand.test_read_job import ctx_for  # noqa: E402
from understand.test_read_job import log_prompt as log_message  # noqa: E402
from understand.test_read_job import state as shown  # noqa: E402

world = test_judge_cascade.world   # INT-001 and SR-001 from the owner's logged MESSAGE


def pre_intents(root: Path) -> list[Any]:
    return [e for e in open_core(root).events() if e.kind == "pre-intent"]


def status(root: Path, record_id: str) -> tuple[str, str | None]:
    found = open_core(root).status([record_id])[record_id]
    return found.confirmation, found.approved_by


def reads(root: Path, ids: list[str], words: str, entries: list[dict]) -> Any:
    """The last reply showed ``ids``; the owner writes ``words``; the reader's ``entries``
    are applied and written as the worker does. Returns the read job."""
    core = open_core(root)
    shown(core, ids)
    digest = log_message(core, words)
    job = read.build(core, SESSION, message={"digest": digest, "text": words})
    assert job is not None
    with as_worker(root, SESSION):
        applied = read.apply(core, job, {"entries": [e(core) for e in entries]})
    write_applied(core, applied)
    return job


# ---- SR-208 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-208")
def test_ex4_the_pre_intent_keeps_the_sentence_with_its_context_and_the_intent_links_back(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-208 EX-4: the owner says "the reminders should go by email" while discussing the
    notification settings; the pre-intent keeps the sentence verbatim with the reply it
    answered, and the intent drawn from it links back to it."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    words = "the reminders should go by email"
    reply = "Here are the notification settings: reminders go by push, quiet hours are off."
    digest = log_prompt(repo, words)
    files.write_json_atomic(clarify.context_path(repo, SESSION, digest), {
        "repository": {}, "context": {"last_reply": reply, "earlier_messages": []}})
    write_record(repo, intent_text(1, words, "Reminders go by email", prompt=digest,
                                   will=("Reminders are sent by email",)))
    core = configure(repo)
    _, _, applied = judged(core, ["INT-001"], StubJev(0.5), model_for("INT-001"))
    write(repo, applied)
    [kept] = [e.payload for e in pre_intents(repo)]
    assert (kept["text"], kept["context"], kept["source"]) == (words, reply, digest)
    assert digest.removeprefix("sha256:").startswith(
        open_core(repo).index()["INT-001"].fields["prompt"])
    _, _, again = judged(open_core(repo), ["INT-001"], StubJev(0.5), model_for("INT-001"))
    assert [e for e in again.entries if e["kind"] == "pre-intent"] == []   # once per source


def test_ex4_the_prompt_hook_freezes_the_context_of_an_ordinary_message(
        repo: Path, tmp_path: Path) -> None:
    """SR-208 EX-4: the reply the sentence answered is frozen when the message arrives (the
    judge worker has no transcript), for an ordinary message as for a commanded one."""
    from types import SimpleNamespace

    from iaso.understand import judge

    words = "the reminders should go by email"
    reply = "Here are the notification settings: reminders go by push, quiet hours are off."
    transcript = tmp_path / "t.jsonl"
    with transcript.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in ({"type": "user", "message": {"role": "user", "content": "settings?"}},
                      {"type": "assistant", "message": {"role": "assistant", "content": [
                          {"type": "text", "text": reply}]}},
                      {"type": "user", "message": {"role": "user", "content": words}}):
            handle.write(json.dumps(entry) + "\n")
    digest = log_prompt(repo, words)
    core = open_core(repo)
    ctx = SimpleNamespace(session_id=SESSION, data={"transcript_path": str(transcript)})
    assert clarify.on_prompt(ctx, core, {"digest": digest, "text": words}) == []
    assert judge.context_of(core, digest) == reply


# ---- SR-212 -------------------------------------------------------------------------------


def capture_intent(repo: Path, intent: dict) -> int:
    path = repo / "capture.json"
    path.write_text(json.dumps({"intent": intent}), encoding="utf-8")
    return iaso_run(repo, "capture", "--file", str(path))


@pytest.mark.sr("SR-212")
def test_ex9_a_quote_of_a_bare_answer_warns_once_and_still_records(repo: Path, capsys) -> None:
    """SR-212 EX-9: a capture whose quote is "A" with no question warns that the answer
    needs its question and still records the intent."""
    assert capture_intent(repo, {"quote": "A", "readback": "run in the background"}) == 0
    assert capsys.readouterr().out.count("this answer needs its question") == 1
    assert [r.kind for r in open_core(repo).index().values()] == ["intent"]


@pytest.mark.sr("SR-212")
def test_a_bare_answer_the_owner_gave_in_the_question_tool_needs_no_warning(
        repo: Path, capsys) -> None:
    """SR-212: "A" picked in the question tool is an answered question; no warning."""
    open_core(repo).log_append("events", "question-answer", {
        "session": SESSION, "question": "Background or every turn?", "answer": "A",
        "options": [{"label": "A", "description": ""}, {"label": "B", "description": ""}],
        "via": "question-tool"})
    assert capture_intent(repo, {"quote": "A", "readback": "run in the background"}) == 0
    assert "this answer needs its question" not in capsys.readouterr().out


# ---- SR-248 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-248")
def test_ex2_a_yes_to_one_proposal_shown_whole_is_approved_by_jev_with_the_yes_kept(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-248 EX-2: fast track on and calibrated; the owner says "yes" to one proposal shown
    whole; JEV judges above 0.9: approved by auto-jev with its score, marked judge-approved,
    the "yes" kept with the proposal it answered; no question is asked."""
    fast_track_on(configure(world), monkeypatch, 0.93)
    job = reads(world, ["SR-001"], "yes", [lambda c: entry_of(c, "SR-001", "accepted", "yes")])
    [kept] = pre_intents(world)
    core = open_core(world)
    record = core.index()["SR-001"]
    assert kept.payload["text"] == "yes" and kept.payload["asked"]["records"] == [
        {"id": "SR-001", "hash": record.hash}]
    assert "Public pages load within two seconds" in kept.payload["question"]
    assert [j.inputs["records"] for j in jobs.queued(world, SESSION)
            if j.kind == "judge" and j.needs == job.id] == [["SR-001"]]
    model = FakeDispatcher()
    _, _, applied = judged(core, ["SR-001"], StubJev(0.96), model)
    [approval] = approvals(applied)
    assert approval["by"] == "auto-jev" and approval["auto"]["score"] == 0.96
    assert approval["answers"] == [kept.digest] and model.jobs == []
    assert kept.payload["source"] in approval["trail"]
    write(world, applied)
    assert status(world, "SR-001") == ("confirmed", "auto-jev")


# ---- SR-209 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-209")
def test_ex2_a_partial_answer_approves_one_sends_one_back_and_leaves_one_proposed(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-209 EX-2: the last reply mentioned the rounding rule, the amount type and the
    reminder intent; the owner writes "the rounding is fine but amounts should be floats":
    the rounding requirement is approved with the owner's words, the amount decision is sent
    back for the agent to reword, and the reminder intent stays proposed."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    digest = log_prompt(repo, "Send a reminder before each invoice is due, amounts rounded.")
    write_record(repo, intent_text(1, "Send a reminder before each invoice is due",
                                   "Invoice reminders", prompt=digest))
    write_record(repo, requirement_text(1, "Amounts are rounded", "Amounts round to cents",
                                        intent=1))
    write_record(repo, decision_text(1, "Which type holds amounts?", "integer cents",
                                     intent=1, alternatives=("floats",)))
    configure(repo)
    words = "the rounding is fine but amounts should be floats"
    reads(repo, ["INT-001", "SR-001", "DEC-001"], words, [
        lambda c: entry_of(c, "SR-001", "accepted", "the rounding is fine"),
        lambda c: entry_of(c, "DEC-001", "change", "amounts should be floats",
                           change="amounts are floats"),
        lambda c: entry_of(c, "INT-001", "open", "", confidence=0.2)])
    [kept] = pre_intents(repo)
    assert [r["id"] for r in kept.payload["asked"]["records"]] == ["SR-001", "DEC-001"]
    model = FakeDispatcher({"judge": {"verdicts": [
        {"id": "SR-001", "verdict": "supported", "confidence": 0.8, "beyond": [],
         "contradicts": [], "clear": True},
        {"id": "DEC-001", "verdict": "contradicts", "confidence": 0.9, "beyond": [],
         "contradicts": ["the owner wants floats"], "clear": False}]}})
    _, _, applied = judged(open_core(repo), ["SR-001", "DEC-001"], StubJev(0.5), model)
    [approval] = approvals(applied)
    assert [r["id"] for r in approval["records"]] == ["SR-001"]
    assert approval["by"] == "auto-model" and approval["answers"] == [kept.digest]
    assert approval["trail"] == [digest, kept.payload["source"]]
    write(repo, applied)
    assert status(repo, "SR-001") == ("confirmed", "auto-model")
    notes = files.read_json(files.session_dir(repo, SESSION) / "agent_notes.json")
    assert any("DEC-001" in n and "reword" in n for n in notes)
    assert status(repo, "DEC-001")[0] == status(repo, "INT-001")[0] == "proposed"


@pytest.mark.sr("SR-209")
def test_a_prose_ok_with_no_question_open_approves_nothing(world: Path) -> None:
    """SR-209: a bare "ok" when the last reply showed nothing and no question is open is
    read by no one: no pre-intent, no judge job, no approval."""
    core = open_core(world)
    digest = log_message(core, "ok")
    assert read.on_prompt(ctx_for(core), core, {"digest": digest, "text": "ok"}) is None
    assert pre_intents(world) == [] and jobs.queued(world, SESSION) == []
    assert status(world, "SR-001") == ("proposed", None)
