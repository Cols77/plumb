"""SP8 lane JUDGE, J1 / J3 / J9a: the judge kind (SR-102). Nothing here calls a model: the
answers are scripted and applied in process."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.contracts import Job
from understand.fakes import FakeDispatcher, owner_level

pytestmark = pytest.mark.sr("SR-239")

SESSION = "s1"


# ---- helpers other JUDGE test files import ------------------------------------------------


def log_prompt(repo: Path, text: str, *, session: str = SESSION,
               at: str = "2026-10-06T10:00:00Z") -> str:
    """Append ``text`` to the prompt log as the prompt hook does; returns its digest."""
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = repo / ".plumb" / "session" / "prompts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"digest": digest, "session": session, "at": at,
                                 "text": text, "via": "hook"}) + "\n")
    return digest


def intent_text(n: int, quote: str, readback: str, *, prompt: str | None = None,
                question: str | None = None, assumptions: tuple[str, ...] = (),
                will: tuple[str, ...] = (), wont: tuple[str, ...] = ()) -> str:
    import yaml

    data: dict[str, Any] = {"id": f"INT-{n:03d}", "title": readback[:40], "quote": quote,
                            "readback": readback, "will": list(will), "wont": list(wont),
                            "assumptions": list(assumptions), "mode": "incremental"}
    if prompt:
        data["prompt"] = prompt.removeprefix("sha256:")[:16]
    if question:
        data["question"] = question
    return "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n"


def requirement_text(n: int, title: str, statement: str, *, intent: int | None = None,
                     feature: str | None = None,
                     examples: tuple[tuple[str, str, str], ...] = (),
                     links: list[dict[str, Any]] | None = None) -> str:
    import yaml

    data: dict[str, Any] = {"id": f"SR-{n:03d}", "title": title, "statement": statement}
    if feature:
        data["feature"] = feature
    data["examples"] = [{"id": f"EX-{i}", "given": g, "when": w, "then": t}
                        for i, (g, w, t) in enumerate(examples, start=1)]
    if intent is not None:
        data["links"] = [{"kind": "derives_from", "to": f"INT-{intent:03d}"}]
    if links:
        data["links"] = [*data.get("links", []), *links]
    return "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n"


def decision_text(n: int, question: str, chosen: str, *, intent: int | None = None,
                  alternatives: tuple[str, ...] = ()) -> str:
    import yaml

    data: dict[str, Any] = {"id": f"DEC-{n:03d}", "title": question[:40],
                            "question": question, "chosen": chosen,
                            "alternatives": list(alternatives), "matters": False}
    if intent is not None:
        data["links"] = [{"kind": "derives_from", "to": f"INT-{intent:03d}"}]
    return "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n"


def approve(core: Any, record_id: str, by: str = "owner") -> None:
    from plumb.approvals import approval_items

    core.log_append("events", "approval", {"records": approval_items(core, [record_id]),
                                           "by": by})


MESSAGE = "Build a calculator with add, subtract, multiply and divide."


def make_world(repo: Path, write_record, count: int = 2) -> list[str]:
    """One intent from MESSAGE and ``count`` requirements under it; their ids."""
    digest = log_prompt(repo, MESSAGE)
    write_record(repo, intent_text(1, "Build a calculator", "A calculator", prompt=digest))
    ids = []
    for n in range(1, count + 1):
        write_record(repo, requirement_text(
            n, f"Operation {n}", f"The calculator does operation {n}", intent=1,
            examples=((f"input {n}", "it runs", f"output {n}"),)))
        ids.append(f"SR-{n:03d}")
    return ids


def verdict_answer(*items: tuple[str, str, float], **extra: Any) -> dict[str, Any]:
    """A scripted judge answer: ``(id, verdict, confidence)`` per record."""
    return {"verdicts": [{"id": i, "verdict": v, "confidence": c,
                          "beyond": extra.get("beyond", {}).get(i, []),
                          "contradicts": extra.get("contradicts", {}).get(i, [])}
                         for i, v, c in items]}


# ---- fixtures -----------------------------------------------------------------------------


@pytest.fixture
def judge_kind():
    from plumb.understand import judge

    return judge


def build_job(core: Any, ids: list[str], **context: Any) -> Job:
    from plumb.understand import judge

    job = judge.build(core, SESSION, records=ids, **context)
    assert job is not None
    return job


def entry_of(job: Job, record_id: str) -> dict[str, Any]:
    return next(r for r in job.inputs["records"] if r["id"] == record_id)


MESSAGE = "I want pages to load faster. Don't add a cache layer, that is too much."


@pytest.fixture
def world(repo: Path, write_record):
    digest = log_prompt(repo, MESSAGE)
    write_record(repo, intent_text(1, "I want pages to load faster", "Make pages load faster",
                                   prompt=digest, will=("Pages load faster",),
                                   wont=("No cache layer",),
                                   assumptions=("Pages means the public ones",)))
    write_record(repo, requirement_text(
        1, "Pages load in two seconds", "Public pages load within two seconds",
        intent=1, feature="FEAT-001",
        examples=(("a public page", "it is requested", "it loads within 2 seconds"),)))
    return repo


# ---- J1 -----------------------------------------------------------------------------------


def test_ex6_short_answer_premise_holds_the_question(repo: Path, write_record) -> None:
    question = "Should plumb keep one log or two? A: one log. B: two logs."
    digest = log_prompt(repo, "A")
    write_record(repo, intent_text(2, "A", "Keep one log", prompt=digest, question=question,
                                   will=("One log holds everything",)))
    core = open_core(repo)
    job = build_job(core, ["INT-002"])
    premise = entry_of(job, "INT-002")["premise"]
    assert premise["question"] == question
    assert [m["text"] for m in premise["messages"]] == ["A"]
    assert premise["messages"][0]["digest"] == digest
    import plumb.understand as understand

    system = (Path(understand.__file__).parent / "agents" / "judge.md").read_text(
        encoding="utf-8")
    assert "would the owner object" in system.lower()
    assert "question" in system.lower()


def test_assumptions_shown_not_judged(world: Path) -> None:
    core = open_core(world)
    entry = entry_of(build_job(core, ["INT-001"]), "INT-001")
    assert entry["assumptions"] == ["Pages means the public ones"]
    assert "Pages means the public ones" not in entry["text"]
    assert "No cache layer" in entry["text"] and "Pages load faster" in entry["text"]
    assert entry["kind"] == "intent" and entry["hash"] == core.index()["INT-001"].hash
    requirement = entry_of(build_job(core, ["SR-001"]), "SR-001")
    assert "Public pages load within two seconds" in requirement["text"]
    assert "it loads within 2 seconds" in requirement["text"]


def test_a_decision_entry_holds_its_question_and_chosen_option(world: Path,
                                                               write_record) -> None:
    write_record(world, decision_text(1, "Which cache?", "none", intent=1,
                                      alternatives=("redis",)))
    core = open_core(world)
    entry = entry_of(build_job(core, ["DEC-001"]), "DEC-001")
    assert "Which cache?" in entry["text"] and "none" in entry["text"]
    assert entry["premise"]["messages"][0]["text"] == MESSAGE
    assert entry["premise"]["parent"] is None          # the intent is not confirmed yet


def test_premise_is_the_whole_logged_message_and_the_confirmed_parent(world: Path) -> None:
    core = open_core(world)
    approve(core, "INT-001")
    entry = entry_of(build_job(open_core(world), ["SR-001"]), "SR-001")
    assert [m["text"] for m in entry["premise"]["messages"]] == [MESSAGE]
    assert entry["premise"]["parent"] == "INT-001"


def test_related_are_confirmed_records_only(world: Path, write_record) -> None:
    write_record(world, requirement_text(
        2, "Pages load in five seconds", "Public pages load within five seconds",
        intent=1, feature="FEAT-001",
        examples=(("a public page", "it is requested", "it loads within 5 seconds"),)))
    core = open_core(world)
    assert entry_of(build_job(core, ["SR-002"]), "SR-002")["related"] == []
    approve(core, "SR-001")
    related = entry_of(build_job(open_core(world), ["SR-002"]), "SR-002")["related"]
    assert [r["id"] for r in related] == ["SR-001"]
    assert related[0]["status"] == "confirmed"
    assert "within 2 seconds" in related[0]["text"]


def test_build_is_none_without_records(world: Path) -> None:
    from plumb.understand import judge

    core = open_core(world)
    assert judge.build(core, SESSION, records=[]) is None
    assert judge.build(core, SESSION, records=["SR-404"]) is None


def test_same_records_same_job_id(world: Path) -> None:
    core = open_core(world)
    assert build_job(core, ["INT-001", "SR-001"]).id == build_job(
        core, ["INT-001", "SR-001"]).id


def _apply(core: Any, job: Job, answer: dict[str, Any]):
    from plumb.understand import judge

    return judge.apply(core, job, answer)


def test_verdict_logged_with_score(world: Path) -> None:
    core = open_core(world)
    job = build_job(core, ["INT-001", "SR-001"])
    applied = _apply(core, job, verdict_answer(
        ("INT-001", "supported", 0.93), ("SR-001", "beyond", 0.8),
        beyond={"SR-001": ["a two second limit"]}))
    verdicts = {e["payload"]["id"]: e["payload"] for e in applied.entries
                if e["kind"] == "verdict"}
    assert verdicts["INT-001"]["score"] == 0.93
    assert verdicts["INT-001"]["verdict"] == "supported"
    assert verdicts["SR-001"]["score"] == 0            # 0 unless supported
    assert verdicts["SR-001"]["beyond"] == ["a two second limit"]
    one = verdicts["INT-001"]
    assert one["job"] == job.id and one["hash"] == core.index()["INT-001"].hash
    assert one["premise_digest"] == entry_of(job, "INT-001")["premise"]["messages"][0]["digest"]
    assert one["model"]


def _open_readback(repo: Path, text: str = MESSAGE) -> str:
    """An open read-back card for the request ``text`` (what the clarify job draws)."""
    from plumb.contracts import CardState
    from plumb.understand import cardstore, clarify

    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    card = CardState(id=clarify.card_id(digest), kind="clarify", topic="your request",
                     issue="Make pages load faster", evidence="Assumed: public pages",
                     resolutions=("Yes", "No"), status="open")
    cardstore.save(repo, SESSION, [card])
    return card.id


def test_ex4_contradicts_names_both_examples(world: Path, write_record) -> None:
    write_record(world, requirement_text(
        2, "Pages load in five seconds", "Public pages load within five seconds",
        intent=1, feature="FEAT-001",
        examples=(("a public page", "it is requested", "it loads within 5 seconds"),)))
    core = open_core(world)
    approve(core, "SR-001")
    core = open_core(world)
    job = build_job(core, ["SR-002"])
    assert entry_of(job, "SR-002")["related"][0]["id"] == "SR-001"
    said = ["SR-002 EX-1 (loads within 5 seconds) conflicts with SR-001 EX-1 (loads "
            "within 2 seconds)"]
    applied = _apply(core, job, verdict_answer(("SR-002", "contradicts", 0.9),
                                               contradicts={"SR-002": said}))
    verdict = next(e["payload"] for e in applied.entries if e["kind"] == "verdict")
    assert verdict["verdict"] == "contradicts" and verdict["contradicts"] == said
    assert not [c for c in applied.cards if c.kind == "contradicts"]


@pytest.mark.sr("SR-239")
def test_sr152_ex3_no_finding_leaves_the_read_back_unchanged(world: Path) -> None:
    core = open_core(world)
    _open_readback(world)
    applied = _apply(core, build_job(core, ["SR-001"]), verdict_answer(("SR-001", "supported", 0.9)))
    assert not [c for c in applied.cards if c.kind == "clarify"]


def test_ex5_option_picked_decision_supported_is_not_settled_and_raises_no_card(
        repo: Path, write_record) -> None:
    question = "Cache or no cache? A: add a cache. B: no cache."
    digest = log_prompt(repo, "A")
    write_record(repo, intent_text(1, "A", "Add a cache", prompt=digest, question=question))
    write_record(repo, decision_text(1, "Cache or no cache?", "add a cache", intent=1,
                                     alternatives=("no cache",)))
    core = open_core(repo)
    job = build_job(core, ["DEC-001"])
    assert entry_of(job, "DEC-001")["premise"]["question"] == question
    applied = _apply(core, job, verdict_answer(("DEC-001", "supported", 0.99)))
    assert not [e for e in applied.entries if e["kind"] == "approval"]
    assert applied.cards == ()                  # no trial card: the question route (SR-252 EX-6)


def test_a_changed_record_is_not_carded_or_settled(world: Path) -> None:
    core = open_core(world)
    job = build_job(core, ["SR-001"])
    path = world / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace("two seconds", "3 seconds"),
                    encoding="utf-8")
    applied = _apply(open_core(world), job, verdict_answer(("SR-001", "beyond", 0.9),
                                                           beyond={"SR-001": ["x"]}))
    assert [e["kind"] for e in applied.entries] == ["verdict"]    # logged for the version judged
    assert applied.cards == ()


def test_judge_registers_trial_beyond_contradicts() -> None:
    from plumb.understand import effects

    for kind in ("trial", "beyond", "contradicts"):
        assert callable(effects.handler_for(kind)), kind


def test_recompute_rebuilds_from_the_logs(world: Path) -> None:
    from plumb.understand import judge

    core = open_core(world)
    job = build_job(core, ["SR-001"])
    path = world / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace("two seconds", "3 seconds"),
                    encoding="utf-8")
    fresh = judge.recompute(open_core(world), job)
    assert fresh is not None
    assert "3 seconds" in fresh["records"][0]["text"]
    assert fresh["records"][0]["hash"] != entry_of(job, "SR-001")["hash"]
    path.unlink()
    assert judge.recompute(open_core(world), job) is None


def test_describe_says_the_step_in_plain_words(world: Path) -> None:
    from plumb.understand import judge

    job = build_job(open_core(world), ["INT-001", "SR-001"])
    assert judge.describe(job) == "judging 2 records"
    assert owner_level(judge.describe(job)) == []


def test_the_schema_is_a_checkable_answer_shape() -> None:
    from plumb.understand import judge

    assert judge.schema["id"] == "judge.v1"
    item = judge.schema["properties"]["verdicts"]["items"]
    assert item["properties"]["verdict"]["enum"] == ["supported", "beyond", "contradicts",
                                                     "waiting"]
    assert set(item["required"]) >= {"id", "verdict", "confidence"}
    assert {"clear", "answer_corrects"} <= set(item["properties"])
    asked = judge.schema["properties"]["questions"]["items"]["properties"]
    assert set(asked) == {"question", "header", "options", "recommended_reason", "request",
                          "records", "principle", "blocking", "diagram"}
    assert FakeDispatcher().available() is None


# ---- J3: one job per capture ----------------------------------------------------------------

SIX = {"intent": {"quote": "add multiply next to add", "readback": "Add multiply beside add",
                  "will": ["multiply(a, b) returns a * b"]},
       "requirements": [{"title": f"multiply case {n}", "statement": f"multiply handles case {n}",
                         "examples": [{"given": f"case {n}", "when": "multiply runs",
                                       "then": f"it answers {n}"}]} for n in range(1, 7)]}
SAID = "please add multiply next to add; it should handle a few cases"


def _capture_six(repo: Path):
    from plumb.capture.capture import capture

    digest = log_prompt(repo, SAID)
    return capture(open_core(repo), SIX, prompt_digest=digest)


def _jobs(repo: Path) -> list[Job]:
    from plumb.understand import files

    folder = files.jobs_dir(repo, SESSION)
    return [files.job_from_json(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(folder.glob("*.json"))]


def test_ex9_capture_of_one_intent_and_six_requirements_queues_one_job_for_seven(
        repo: Path, engine_standins) -> None:
    """SR-104 EX-9 and SR-102 EX-7."""
    result = _capture_six(repo)
    (job,) = _jobs(repo)
    assert job.kind == "judge" and job.session == SESSION
    assert [r["id"] for r in job.inputs["records"]] == list(result.written)
    assert len(job.inputs["records"]) == 7
    premises = [e for e in open_core(repo).events() if e.kind == "premise"]
    assert [p.payload["text"] for p in premises] == [SAID]
    assert premises[0].payload["digest"] == job.inputs["records"][0]["premise"]["messages"][0][
        "digest"]


def test_the_same_capture_twice_queues_no_second_job(repo: Path, engine_standins) -> None:
    from plumb.understand import judge

    result = _capture_six(repo)
    judge.queue_for_capture(open_core(repo), result, prompt_digest=log_prompt(repo, SAID))
    assert len(_jobs(repo)) == 1


def test_an_updated_record_joins_the_job(repo: Path, engine_standins) -> None:
    from types import SimpleNamespace

    from plumb.understand import judge

    result = _capture_six(repo)
    after = SimpleNamespace(written=(), updated=(result.written[2],))
    judge.queue_for_capture(open_core(repo), after, prompt_digest=log_prompt(repo, SAID))
    jobs = _jobs(repo)
    assert len(jobs) == 2
    assert sorted(len(j.inputs["records"]) for j in jobs) == [1, 7]


def test_the_worker_applies_the_verdicts_and_raises_no_card(repo: Path, engine_standins) -> None:
    from plumb.understand import cardstore, worker

    result = _capture_six(repo)
    ids = list(result.written)
    engine_standins.dispatcher.script = {"judge": verdict_answer(
        (ids[0], "supported", 0.95), (ids[1], "supported", 0.9),
        (ids[2], "beyond", 0.8), beyond={ids[2]: ["a promise the owner did not make"]})}
    core = open_core(repo)
    core.log_append("events", "config", {"by": "owner", "auto_approve": {   # the owner's switch
        "enabled": True, "backend": "jev", "min_probability": 0.9, "min_confidence": "high"}})
    assert worker.run_once(core, SESSION)
    logged = [e.payload for e in open_core(repo).events() if e.kind == "verdict"]
    assert {v["id"]: (v["verdict"], v["score"]) for v in logged} == {
        ids[0]: ("supported", 0.95), ids[1]: ("supported", 0.9), ids[2]: ("beyond", 0)}
    assert cardstore.load(repo, SESSION) == []          # no trial or beyond card (SR-252 EX-6)
    status = open_core(repo).status(ids[:2])           # no approval without a question round
    assert [status[i].confirmation for i in ids[:2]] == ["proposed", "proposed"]


# ---- J9a: the judge cases of the evaluation set ---------------------------------------------


def _case(name: str) -> dict[str, Any]:
    from plumb.understand import evalrun

    return next(c for c in evalrun.load_cases("judge") if c["name"] == name)


def test_evalset_judge_cases_load_and_run_on_the_fake(repo: Path, capsys) -> None:
    from plumb.understand import evalrun

    cases = evalrun.load_cases("judge")
    assert [c["name"] for c in cases] == [
        "int016-first-readback-beyond", "int013-first-readback-beyond", "int004-supported",
        "int006-answer-b-supported", "int007-answer-b-supported",
        "int008-answer-a-supported"]
    for case in cases:                                   # frozen copies, never read live
        (entry,) = case["inputs"]["records"]
        assert entry["hash"].startswith("sha256:frozen-") and entry["premise"]["messages"]
        assert case["expect"]["verdicts"][0]["id"] == entry["id"]
    results = evalrun.run_cases(evalrun.FakeEvalDispatcher(), cases, "judge")
    assert all(r["passed"] for r in results)
    assert evalrun.run("eval", ["--fake", "--root", str(repo)]) == 0
    (run,) = [e for e in open_core(repo).events() if e.kind == "eval-run"]
    assert run.payload["passed"] >= 6 and run.payload["model"] == "fake"
    # the run holds every lane's cases now (read, judge, clarify): the judge's six are in it
    assert len([c for c in run.payload["cases"] if c["kind"] == "judge"]) == 6
    assert f"{len(run.payload['cases'])} cases" in capsys.readouterr().out


def _answers(*items: dict[str, Any]) -> dict[str, Any]:
    return {"verdicts": list(items)}


def test_ex1_int016_beyond_one_line_per_record_and_token_budget() -> None:
    from plumb.understand import judge

    case = _case("int016-first-readback-beyond")
    fake = FakeDispatcher({"judge": _answers({
        "id": "INT-016", "verdict": "beyond", "confidence": 0.9, "contradicts": [],
        "beyond": ["one line per record and a per-prompt token budget stated as your intent"]})})
    passed, answer = judge.evaluate_case(fake, case)
    assert passed is True
    (call,) = fake.calls
    assert "bloat the context" in call["user"] and "one line per record" in call["user"]
    assert "would the owner object" in call["system"].lower()
    wrong = FakeDispatcher({"judge": _answers({"id": "INT-016", "verdict": "supported",
                                              "confidence": 0.9})})
    assert judge.evaluate_case(wrong, case)[0] is False
    vague = FakeDispatcher({"judge": _answers({"id": "INT-016", "verdict": "beyond",
                                              "confidence": 0.9, "beyond": ["something else"]})})
    assert judge.evaluate_case(vague, case)[0] is False     # beyond, but not for that reason


def test_ex2_int013_beyond_maintenance_mode() -> None:
    from plumb.understand import judge

    case = _case("int013-first-readback-beyond")
    fake = FakeDispatcher({"judge": _answers({
        "id": "INT-013", "verdict": "beyond", "confidence": 0.95,
        "beyond": ["maintenance mode is stated as decided; you only said to consider stopping"]
    })})
    assert judge.evaluate_case(fake, case)[0] is True
    assert "consider stopping developments" in fake.calls[0]["user"]


def test_ex3_int006_answer_b_supported() -> None:
    from plumb.understand import judge

    case = _case("int006-answer-b-supported")
    (entry,) = case["inputs"]["records"]
    assert entry["premise"]["question"] and "B." in entry["premise"]["question"]
    fake = FakeDispatcher({"judge": _answers({"id": "INT-006", "verdict": "supported",
                                              "confidence": 0.92})})
    passed, _ = judge.evaluate_case(fake, case)
    assert passed is True
    assert entry["premise"]["question"] in fake.calls[0]["user"]


def test_the_other_supported_cases_match_only_a_supported_verdict() -> None:
    from plumb.understand import judge

    for name, rid in (("int004-supported", "INT-004"), ("int007-answer-b-supported", "INT-007"),
                      ("int008-answer-a-supported", "INT-008")):
        case = _case(name)
        good = FakeDispatcher({"judge": _answers({"id": rid, "verdict": "supported",
                                                  "confidence": 0.9})})
        bad = FakeDispatcher({"judge": _answers({"id": rid, "verdict": "beyond",
                                                 "confidence": 0.9, "beyond": ["x"]})})
        assert judge.evaluate_case(good, case)[0] is True
        assert judge.evaluate_case(bad, case)[0] is False
    assert _case("int008-answer-a-supported")["inputs"]["records"][0]["premise"][
        "messages"][0]["text"] == "A"

