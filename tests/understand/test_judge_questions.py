"""The judge model returns questions about the owner's intent; no trial card (task 2 of the
judge-approval plan). A record the fast track does not take is asked about through the question
tool: the judge job writes ``judge_questions.json`` (only the worker writes it) and
``clarify --wait`` answers ``ask`` with them. A question in plumb's words, or out of shape, is
never shown: its records wait with the waiting line. JEV and the model are stubs."""

from __future__ import annotations

import dataclasses
import json
import re
import types
from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.understand import cmd_clarify, files, gate, judge, queue, summary, verdict
from understand.fakes import FakeDispatcher, owner_level
from understand.test_judge_cascade import StubJev, configure, fast_track_on, world  # noqa: F401
from understand.test_judge_job import (
    SESSION,
    build_job,
    intent_text,
    log_prompt,
    requirement_text,
)

TITLES = ("Make pages load faster", "Pages load in two seconds")


def asking(*ids: str, **change: Any) -> dict[str, Any]:
    """One well-shaped judge question settling ``ids``; ``change`` overrides its fields."""
    return {"question": "Should every page load faster, or only the public ones?",
            "header": "Which pages",
            "options": [{"label": "Public pages", "consequence": "Speeds up what visitors see; "
                                                                 "leaves the admin pages."},
                        {"label": "Every page", "consequence": "Speeds up all of them; "
                                                               "more work."}],
            "recommended_reason": "you spoke of pages visitors load",
            "request": {"words": "I want pages to load faster", "date": "6 Oct"},
            "records": list(ids), **change}


def answer(*verdicts: tuple[str, str], questions: list[dict[str, Any]] | None = None,
           **extra: Any) -> dict[str, Any]:
    """A judge model's answer: ``(id, verdict)`` each, and its questions."""
    return {"verdicts": [{"id": i, "verdict": v, "confidence": 0.9, **extra.get(i, {})}
                         for i, v in verdicts], "questions": questions or []}


def applied_on(repo: Path, ids: list[str], given: dict[str, Any]) -> Any:
    core = open_core(repo)
    return judge.apply(core, build_job(core, ids), given)


def written(repo: Path) -> list[dict[str, Any]]:
    path = judge.questions_path(repo, SESSION)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def notes(repo: Path) -> list[str]:
    path = files.session_dir(repo, SESSION) / "agent_notes.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def shown_text(question: dict[str, Any]) -> str:
    return "\n".join([question["question"], question["header"],
                      *(o["label"] for o in question["options"]),
                      *(o["description"] for o in question["options"])])


# ---- SR-248 ---------------------------------------------------------------------------------


@pytest.mark.sr("SR-248")
def test_ex3_below_the_calibrated_threshold_the_judge_models_questions_are_written(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """SR-248 EX-3: threshold 0.93, JEV 0.92: not fast-tracked; the judge model's question is
    written for the question tool, the recommended option first."""
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    model = FakeDispatcher({"judge": answer(("SR-001", "supported"),
                                            questions=[asking("SR-001")])})
    job = build_job(core, ["SR-001"])
    done = verdict.cascade(core, job, system="judge", schema={}, jev=StubJev(0.92),
                           dispatcher=model)
    applied = judge.apply(core, job, done.answer)
    assert not [e for e in applied.entries if e["kind"] == "approval"]
    (question,) = written(world)
    assert question["records"] == [{"id": "SR-001", "hash": core.index()["SR-001"].hash}]
    assert question["job"] == job.id
    assert question["options"][0]["label"] == "Public pages (Recommended)"
    assert question["options"][0]["description"].endswith(
        "Recommended: you spoke of pages visitors load")
    assert 'You said on 6 Oct: "I want pages to load faster"' in question["question"]
    assert question["key"] == judge.question_key(question["question"])
    assert notes(world) == []                          # every record is asked: nothing waits


@pytest.mark.sr("SR-248")
def test_ex7_linked_tested_and_consistent_is_not_approved_and_says_nothing_settled(
        world: Path) -> None:  # noqa: F811
    """SR-248 EX-7: a requirement the model finds supported and clear, with code and passing
    tests, stays proposed after the judge job and the turn's end; no settled line or offer."""
    applied = applied_on(world, ["SR-001"], answer(
        ("SR-001", "supported"), questions=[asking("SR-001")],
        **{"SR-001": {"clear": True, "confidence": 0.99}}))
    assert [e["kind"] for e in applied.entries
            if e["kind"] != "pre-intent"] == ["verdict"] and applied.cards == ()
    assert summary._upkeep(open_core(world), SESSION, recalibrate=False) == []
    status = open_core(world).status(["SR-001"])["SR-001"]
    assert status.confirmation == "proposed"
    assert not any("settled" in line.lower() for line in [*applied.notes, *notes(world)])


# ---- SR-252, SR-209 ---------------------------------------------------------------------


@pytest.mark.sr("SR-252")
def test_ex6_supported_records_without_calibration_raise_no_trial_or_read_back_card(
        world: Path, write_record) -> None:  # noqa: F811
    """SR-252 EX-6: no passing calibration, three supported records: no trial or read-back card
    from the judge, the turn's end or the request's check; they take the question route."""
    from plumb.understand import cardstore, clarify

    write_record(world, requirement_text(
        2, "Pages load in one second", "Home loads within one second", intent=1,
        examples=(("the home page", "it is requested", "it loads within 1 second"),)))
    ids = ["INT-001", "SR-001", "SR-002"]
    applied = applied_on(world, ids, answer(*((i, "supported") for i in ids),
                                            questions=[asking(*ids)]))
    assert applied.cards == ()
    assert summary._upkeep(open_core(world), SESSION, recalibrate=False) == []
    digest = log_prompt(world, "/plumb clarify make the pages faster")
    gate.close(world, SESSION, digest, clarify.GATE_REASON_CHECKING)
    job = clarify.build(open_core(world), SESSION, message={
        "digest": digest, "text": "/plumb clarify make the pages faster"})
    assert job is not None
    checked = clarify.apply(open_core(world), job, {"intent": "yes", "gaps": [], "readback": {
        "proposal": "Make pages faster"}})
    assert checked.cards == () and cardstore.own_cards(world, SESSION) == []
    assert not gate.is_closed(world, SESSION)
    (question,) = written(world)
    assert {r["id"] for r in question["records"]} == set(ids)


@pytest.mark.sr("SR-209")
def test_ex5_the_session_start_brief_offers_no_ok_and_no_read_back(
        world: Path) -> None:  # noqa: F811
    """SR-209 EX-5: low-risk records judged and asked about: the brief asks for no "ok" and
    shows no read-back card."""
    from plumb.hosts.claude_code import session_start
    from plumb.understand import cardstore, clarify

    applied_on(world, ["INT-001", "SR-001"], answer(
        ("INT-001", "supported"), ("SR-001", "supported"),
        questions=[asking("INT-001", "SR-001")]))
    lines = session_start.brief(open_core(world), "tests: none")
    text = "\n".join(lines)
    assert not re.search(r"\b(?:say|type|reply) ok\b|\bok to\b", text, re.IGNORECASE)
    assert clarify.READBACK_QUESTION not in text
    assert cardstore.own_cards(world, SESSION) == []


# ---- SR-267 ---------------------------------------------------------------------------------


@pytest.mark.sr("SR-267")
def test_ex4_ids_and_digests_are_stripped_and_plumb_words_make_the_question_wait(
        world: Path) -> None:  # noqa: F811
    """SR-267 EX-4: a record id is put in the owner's terms and a digest dropped from every
    field shown; a question still saying "settled" or "trial" is not shown and its record
    waits with the waiting line."""
    digest = "sha256:" + "ab" * 32
    applied_on(world, ["SR-001"], answer(("SR-001", "supported"), questions=[asking(
        "SR-001", question=f"Is SR-001 right for every page ({digest})?",
        options=[{"label": "Keep SR-001", "consequence": "It stays as written."},
                 {"label": "Narrow it", "consequence": f"Only public pages {digest}."}])]))
    (question,) = written(world)
    text = shown_text(question)
    assert '"Pages load in two seconds"' in question["question"]
    assert "SR-001" not in text and "sha256" not in text and "abab" not in text
    assert owner_level(text.replace('"Pages load in two seconds"', "")) == []
    for word in ("settled", "trial"):
        judge.questions_path(world, SESSION).unlink(missing_ok=True)
        applied_on(world, ["SR-001"], answer(("SR-001", "supported"), questions=[asking(
            "SR-001", question=f"Was this {word} by your earlier answer?")]))
        assert written(world) == []
    (line,) = notes(world)                               # said once in the window
    assert "SR-001" in line and "plumb's own words" in line


@pytest.mark.sr("SR-267")
def test_ex9_a_doubt_about_the_agents_own_records_puts_nothing_to_the_owner(
        world: Path) -> None:  # noqa: F811
    """SR-267 EX-9: the judge doubts whether the records converge, not what the owner meant:
    no question is written, the record waits with the waiting line naming the reason."""
    applied = applied_on(world, ["SR-001"], answer(
        ("SR-001", "waiting"), **{"SR-001": {"reason": "the two timing rules may not converge"}}))
    (logged,) = [e["payload"] for e in applied.entries if e["kind"] == "verdict"]
    assert logged["verdict"] == "waiting"
    assert logged["reason"] == "the two timing rules may not converge"
    assert written(world) == [] and applied.cards == ()
    (line,) = notes(world)
    assert "the two timing rules may not converge" in line


# ---- SR-245 ---------------------------------------------------------------------------------


@pytest.mark.sr("SR-245")
def test_ex7_a_question_out_of_schema_waits_with_the_waiting_line(
        world: Path) -> None:  # noqa: F811
    """SR-245 EX-7: the model's question lacks its consequences and the recommended reason:
    nothing is shown, the record waits with the waiting line, no error."""
    bare = asking("SR-001", options=[{"label": "Public pages"}, {"label": "Every page"}],
                  recommended_reason="")
    applied = applied_on(world, ["SR-001"], answer(("SR-001", "supported"), questions=[bare]))
    assert written(world) == []
    (line,) = notes(world)
    assert line.startswith("plumb: the verdict is waiting") and "consequences" in line
    assert any(n.startswith("waiting: SR-001") for n in applied.notes)


@pytest.mark.sr("SR-245")
def test_ex8_records_too_large_for_the_judge_model_wait_and_the_size_is_named(
        repo: Path, write_record) -> None:
    """SR-245 EX-8: the job's input is larger than the judge model takes: the model is not
    called, the records wait and the line names the size."""
    said = "Make the report page fast. " + "Every line of the report matters. " * 2500
    digest = log_prompt(repo, said)
    write_record(repo, intent_text(1, "Make the report page fast", "A fast report page",
                                   prompt=digest))
    core = open_core(repo)
    model = FakeDispatcher({"judge": answer(("INT-001", "supported"))})
    with pytest.raises(verdict.Waiting) as waited:
        verdict.cascade(core, build_job(core, ["INT-001"]), system="judge", schema={},
                        jev=None, dispatcher=model)
    assert model.jobs == []
    assert re.search(r"too large for the judge model \(\d{5,} characters\)", waited.value.line)
    assert "INT-001" in waited.value.cause


@pytest.mark.sr("SR-245")
def test_ex9_every_record_answered_nothing_waits_and_no_line(
        world: Path) -> None:  # noqa: F811
    """SR-245 EX-9: each record is asked about: nothing waits, no line is printed."""
    applied = applied_on(world, ["INT-001", "SR-001"], answer(
        ("INT-001", "supported"), ("SR-001", "beyond"),
        questions=[asking("INT-001"), asking("SR-001", question="Did you ask for a limit?")]))
    assert len(written(world)) == 2
    assert notes(world) == [] and not any(n.startswith("waiting") for n in applied.notes)


# ---- one question per point, in the owner's words --------------------------------------------


@pytest.mark.sr("SR-248")
def test_three_records_sharing_one_gap_give_one_question_with_no_record_title(
        world: Path, write_record) -> None:  # noqa: F811
    """One question settles the three records it covers; plumb keeps them apart from what is
    shown, and no record's title is in the question."""
    write_record(world, requirement_text(
        2, "Pages load in one second", "Home loads within one second", intent=1,
        examples=(("the home page", "it is requested", "it loads within 1 second"),)))
    ids = ["INT-001", "SR-001", "SR-002"]
    applied_on(world, ids, answer(*((i, "supported") for i in ids),
                                  questions=[asking(*ids), asking(*ids)]))
    (question,) = written(world)
    assert [r["id"] for r in question["records"]] == ids
    text = shown_text(question)
    assert not any(t in text for t in (*TITLES, "Pages load in one second"))
    assert owner_level(text) == []


# ---- clarify --wait ---------------------------------------------------------------------------


def _queue(repo: Path, ids: list[str]) -> None:
    core = open_core(repo)
    queue.enqueue(core, build_job(core, ids))


@pytest.mark.sr("SR-248")
def test_wait_after_a_capture_with_no_clarify_job_answers_ask(
        world: Path, engine_standins: Any) -> None:  # noqa: F811
    """An ordinary message (no clarify job), a capture's judge job queued: ``clarify --wait``
    runs it and answers ``ask`` with the questions ready for the question tool; the gate stays
    open."""
    engine_standins.dispatcher.script = {"judge": answer(
        ("INT-001", "supported"), ("SR-001", "supported"),
        questions=[asking("INT-001", "SR-001")])}
    _queue(world, ["INT-001", "SR-001"])
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert outcome.state == "ask"
    assert outcome.lines == [cmd_clarify.ASK_QUESTIONS.format(n=1)]
    shown = outcome.as_json()["questions"]
    assert [set(q) for q in shown] == [{"question", "header", "options", "multiSelect"}]
    assert shown[0]["options"][0]["label"].endswith("(Recommended)")
    assert not gate.is_closed(world, SESSION)
    assert owner_level("\n".join(outcome.lines)) == []


@pytest.mark.sr("SR-248")
def test_wait_after_an_answer_collects_the_judge_job_queued_since(
        world: Path, engine_standins: Any) -> None:  # noqa: F811
    """The owner answers in the question tool; the judge job queued after the answer is run by
    the next ``--wait`` (no new message); the answered question is no longer asked."""
    engine_standins.dispatcher.script = {"judge": answer(
        ("INT-001", "supported"), ("SR-001", "supported"),
        questions=[asking("INT-001", "SR-001")])}
    _queue(world, ["INT-001", "SR-001"])
    first = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    (asked,) = first.questions
    open_core(world).log_append("events", "question-answer", {
        "session": SESSION, "question": asked["question"],
        "options": [o["label"] for o in asked["options"]], "answer": "Public pages"})
    engine_standins.dispatcher.script = {"judge": answer(("SR-001", "supported"),
                                                         questions=[])}
    _queue(world, ["SR-001"])
    again = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert len(engine_standins.dispatcher.ran("judge")) == 2
    assert again.state == "ready"
    assert judge.open_questions(open_core(world), SESSION) == []


@pytest.mark.sr("SR-248")
def test_open_questions_leave_the_gate_open_a_choice_card_closes_it_and_its_answer_opens(
        world: Path, engine_standins: Any) -> None:  # noqa: F811
    """P6: a judge question never closes the gate; a blocking-gap choice card does, and
    answering it opens it again."""
    from plumb.contracts import ClarifyAnswer
    from plumb.understand import cardstore, clarify, worker

    engine_standins.dispatcher.script = {"judge": answer(
        ("SR-001", "supported"), questions=[asking("SR-001")])}
    _queue(world, ["SR-001"])
    assert cmd_clarify.wait(open_core(world), SESSION, timeout=10).state == "ask"
    assert not gate.is_closed(world, SESSION)
    text = "/plumb clarify make the admin pages faster too"
    digest = log_prompt(world, text)
    gate.close(world, SESSION, digest, clarify.GATE_REASON_CHECKING)
    engine_standins.dispatcher.script = {"clarify": {
        "intent": "yes", "topic": "pages", "gap": True, "gaps": [{
            "id": "which", "question": "Which admin pages?", "blocking": True,
            "suggestions": ["all of them", "the list only"],
            "consequences": ["more work", "less work"]}]}}
    assert clarify.build(open_core(world), SESSION, message={"digest": digest, "text": text})
    worker.run_once(open_core(world), SESSION)
    assert gate.is_closed(world, SESSION)
    (card,) = [c for c in cardstore.own_cards(world, SESSION) if c.kind == "choice"]
    answered = card.__class__(**{**card.__dict__, "status": "answered", "answers": (
        ClarifyAnswer("which", "accepted", digest),)})
    cardstore.save(world, SESSION, [answered])
    clarify._choice_effect(core=open_core(world), card=answered,
                           job=types.SimpleNamespace(session=SESSION), digest=digest)
    assert not gate.is_closed(world, SESSION)


# ---- SR-299, SR-298 ---------------------------------------------------------------------------

LOGGED_ANSWER = Path(__file__).parent / "fixtures" / "judge-malformed-questions.json"


@pytest.mark.sr("SR-299")
def test_ex1_the_logged_answer_without_records_reaches_the_owner(
        world: Path) -> None:  # noqa: F811
    """SR-299 EX-1: the 2026-10-16 answer (three questions, none naming records) is replayed:
    three questions are written for the question tool and no verdict waits."""
    logged = json.loads(LOGGED_ANSWER.read_text(encoding="utf-8"))["answer"]
    assert len(logged["questions"]) == 3 and not any(q.get("records") for q in logged["questions"])
    applied = applied_on(world, ["SR-001"], {
        "verdicts": [{"id": "SR-001", "verdict": "beyond", "confidence": 0.3, "beyond": ["x"]}],
        "questions": logged["questions"]})
    assert len(written(world)) == 3
    assert all(q["records"][0]["id"] == "SR-001" for q in written(world))
    assert notes(world) == [] and applied.notes == ()


@pytest.mark.sr("SR-299")
def test_ex2_the_answer_format_requires_the_records_of_each_question() -> None:
    """SR-299 EX-2: the schema and the judge's instructions require ``records`` and two to four
    options."""
    item = judge._load_schema()["properties"]["questions"]["items"]
    assert "records" in item["required"]
    assert (item["properties"]["options"]["minItems"], item["properties"]["options"]["maxItems"]
            ) == (2, 4)
    assert "required" in judge.system_prompt().split("- `records`:")[1].split("\n")[0]


@pytest.mark.sr("SR-299")
def test_ex3_a_question_with_one_option_is_asked_again_once(
        world: Path) -> None:  # noqa: F811
    """SR-299 EX-3: a one-option question is retried once; when it fails again it waits and
    the other verdicts are applied."""
    core = configure(world)
    bad = asking("SR-001", options=[{"label": "Only", "consequence": "Nothing else."}])
    model = FakeDispatcher({"judge": answer(("SR-001", "supported"), questions=[bad])})
    job = build_job(core, ["SR-001"])
    done = verdict.cascade(core, job, system="judge", schema={}, jev=StubJev(0.1),
                           dispatcher=model)
    assert len(model.ran("judge")) == 2                 # asked again once, no more
    applied = judge.apply(core, job, done.answer)
    assert written(world) == [] and any(e["kind"] == "verdict" for e in applied.entries)
    assert notes(world)                                  # the record waits and says why
    (case,) = summary.open_cases(world)[0]               # and the job goes to debugging
    assert case["kind"] == "judge-question" and "SR-001" in case["target"]
    good = FakeDispatcher({"judge": answer(("SR-001", "supported"),
                                           questions=[asking("SR-001")])})
    verdict.cascade(core, job, system="judge", schema={}, jev=StubJev(0.1), dispatcher=good)
    assert len(good.ran("judge")) == 1                   # a usable question is not retried


@pytest.mark.sr("SR-298")
def test_ex2_a_job_over_the_limit_is_split_not_failed(world: Path) -> None:  # noqa: F811
    """SR-298 EX-2: records making a 62,000-character job go as two or more model jobs each
    under the limit, and none fails as too large."""
    core = configure(world)
    job = build_job(core, ["SR-001"])
    entries = [{**job.inputs["records"][0], "id": f"SR-{n:03d}", "text": "x" * 20_000}
               for n in range(100, 103)]
    big = dataclasses.replace(job, inputs={**job.inputs, "records": entries})
    model = FakeDispatcher({"judge": lambda j: answer(*[(r["id"], "supported")
                                                        for r in j.inputs["records"]])})
    done = verdict.cascade(core, big, system="judge", schema={}, jev=StubJev(0.1),
                           dispatcher=model)
    assert len(model.ran("judge")) >= 2 and not done.left
    assert all(len(c["user"]) <= verdict.INPUT_MAX for c in model.calls)
    assert {v["id"] for v in done.answer["verdicts"]} == {e["id"] for e in entries}


# ---- SR-309 ---------------------------------------------------------------------------------


def shaped_of(repo: Path, *questions: dict[str, Any]) -> list[dict[str, Any]]:
    applied_on(repo, ["SR-001"], answer(("SR-001", "supported"), questions=list(questions)))
    return written(repo)


@pytest.mark.sr("SR-309")
def test_ex1_a_long_header_keeps_whole_words_within_the_chip(world: Path) -> None:  # noqa: F811
    (question,) = shaped_of(world, asking("SR-001", header="Existing validate errors"))
    assert question["header"] == "Existing"
    assert judge._whole_words("Hand clean-up first") == "Hand"
    assert judge._whole_words("Which pages") == "Which pages"


@pytest.mark.sr("SR-309")
def test_ex2_one_recommended_marker_whatever_the_model_wrote(world: Path) -> None:  # noqa: F811
    options = [{"label": "Public pages (recommended)", "consequence": "Speeds up visitors."},
               {"label": "Every page", "consequence": "Speeds up all."}]
    (question,) = shaped_of(world, asking("SR-001", options=options))
    labels = [o["label"] for o in question["options"]]
    assert labels == ["Public pages (Recommended)", "Every page"]


@pytest.mark.sr("SR-309")
def test_ex3_a_question_the_owner_already_answered_is_dropped(world: Path,
                                                              write_record) -> None:  # noqa: F811
    write_record(world, "---\nid: DEC-001\ntitle: Which pages\nquestion: Which pages?\n"
                 "chosen: Every page, whatever it costs\nalternatives:\n- Public pages\n"
                 "rationale: The owner chose it.\nmatters: true\nrecommended: Every page\n"
                 "links:\n- kind: decides\n  to: SR-001\n---\n")
    options = [{"label": "Public pages", "consequence": "Speeds up visitors."},
               {"label": "Every page (recommended)", "consequence": "Speeds up all."}]
    assert shaped_of(world, asking("SR-001", options=options)) == []


@pytest.mark.sr("SR-309")
def test_ex4_the_quote_is_the_owners_words_the_question_is_about_or_none(
        world: Path) -> None:  # noqa: F811
    (said,) = shaped_of(world, asking("SR-001"))
    assert 'You said on 6 Oct: "I want pages to load faster"' in said["question"]
    off = {"words": "/plumb intent Keep plumb fit by itself.", "date": "6 Oct"}
    (question,) = shaped_of(world, asking("SR-001", request=off))
    assert "You said" not in question["question"]


# ---- DEC-191, DEC-192, SR-299 #2 ---------------------------------------------------------------


def _transcript(repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str) -> None:
    from plumb.understand import recover

    folder = tmp_path / "projects" / recover.project_dir_name(repo)
    folder.mkdir(parents=True)
    line = {"type": "user", "timestamp": "2026-10-04T09:12:00.000Z", "sessionId": "s1",
            "message": {"role": "user", "content": text}}
    (folder / "s1.jsonl").write_text(json.dumps(line), encoding="utf-8")
    monkeypatch.setenv("PLUMB_TRANSCRIPTS_DIR", str(tmp_path / "projects"))


@pytest.mark.sr("SR-309")
@pytest.mark.sr("SR-249")
def test_dec191_words_found_in_a_past_transcript_are_quoted_with_their_date(
        world: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: F811
    _transcript(world, monkeypatch, tmp_path, "Please also cache the front page")
    ask = asking("SR-001", request={"words": "also cache the front page", "date": "9 Oct"})
    (question,) = shaped_of(world, ask)
    assert 'You said on 4 Oct: "also cache the front page"' in question["question"]


@pytest.mark.sr("SR-309")
@pytest.mark.sr("SR-249")
def test_dec191_an_older_record_with_words_in_no_transcript_says_none_were_found(
        world: Path, write_record, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:  # noqa: F811
    write_record(world, intent_text(2, "Cache the front page", "Cache the front page"))
    monkeypatch.setenv("PLUMB_TRANSCRIPTS_DIR", str(tmp_path / "none"))
    applied_on(world, ["INT-002"], answer(("INT-002", "supported"), questions=[
        asking("INT-002", request={"words": "cache it", "date": "9 Oct"})]))
    (question,) = written(world)
    assert "You said" not in question["question"]
    assert "found none of your words" in question["question"]


@pytest.mark.sr("SR-299")
def test_dec192_a_question_without_a_quote_reaches_the_owner(world: Path) -> None:  # noqa: F811
    (question,) = shaped_of(world, asking("SR-001", request={}))
    assert "You said" not in question["question"] and len(question["options"]) == 2


@pytest.mark.sr("SR-299")
def test_ex1_ex3_a_question_short_of_records_or_options_does_not_reject_the_answer(
        world: Path) -> None:  # noqa: F811
    from plumb.understand import schema as schema_check

    bare = {k: v for k, v in asking("SR-001").items() if k != "records"}
    one = asking("SR-001", options=[{"label": "Only", "consequence": "Nothing else."}])
    given = answer(("SR-001", "supported"), questions=[bare, one])
    assert schema_check.problems(given, judge.schema) == []
    applied = applied_on(world, ["SR-001"], given)
    (question,) = written(world)                     # the bare one is shown with the job's records
    assert question["records"][0]["id"] == "SR-001"
    assert any(e["kind"] == "verdict" for e in applied.entries)
