"""SP8 lane JUDGE, J8: the backlog pass (SR-107, SR-133; spec 8)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from plumb.api import open_core
from plumb.contracts import DispatchError, Job
from plumb.hosts.claude_code.hookio import Deadline, HookContext
from plumb.present import owner_text
from understand.fakes import FakeDispatcher, owner_level
from understand.test_judge_job import SESSION, intent_text, log_prompt, requirement_text

pytestmark = pytest.mark.sr("SR-252")

MESSAGE = "Build the whole checking story: what holds a merge, what it says, how it recovers."


@pytest.fixture(autouse=True)
def in_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)


def feature_text(n: int, title: str) -> str:
    return "---\n" + yaml.safe_dump({"id": f"FEAT-{n:03d}", "title": title,
                                     "description": "a feature"}, sort_keys=False) + "---\n"


def bulk(repo: Path, write_record, plan: dict[str, int], *, prompt: bool = True) -> dict[str, Any]:
    """``plan``: feature title -> how many requirements; one intent per feature, each
    requirement derived from it. Returns ids by feature title."""
    digest = log_prompt(repo, MESSAGE) if prompt else None
    out: dict[str, list[str]] = {}
    sr = 0
    for n, (title, count) in enumerate(plan.items(), start=1):
        write_record(repo, feature_text(n, title))
        write_record(repo, intent_text(n, "build the checking story", f"Intent about {title}",
                                       prompt=digest))
        ids = [f"INT-{n:03d}"]
        for _ in range(count):
            sr += 1
            write_record(repo, requirement_text(
                sr, f"Rule {sr} of {title}", f"The rule {sr} holds", intent=n,
                feature=f"FEAT-{n:03d}", examples=(("g", "w", f"t{sr}"),)))
            ids.append(f"SR-{sr:03d}")
        out[title] = ids
    return out


def question(*ids: str, words: str = MESSAGE) -> dict[str, Any]:
    """One well-shaped judge question settling ``ids``."""
    return {"question": "Should a held merge say why in one line?", "header": "Merge hold",
            "options": [{"label": "One line", "consequence": "Says it briefly; no detail."},
                        {"label": "A full report", "consequence": "Says all; it is long."}],
            "recommended_reason": "you asked for what it says, briefly",
            "request": {"words": words, "date": "6 Oct"}, "records": list(ids)}


def answering(score: float = 0.95, verdicts: dict[str, str] | None = None):
    """A fake judge: every record in the job goes beyond the owner's words at ``score`` unless
    named (SR-372: only that or a contradiction asks), and one question settles them all."""
    def answer(job: Job) -> dict[str, Any]:
        said = verdicts or {}
        return {"questions": [question(*(r["id"] for r in job.inputs["records"]))],
                "verdicts": [{"id": r["id"], "verdict": said.get(r["id"], "beyond"),
                              "confidence": score,
                              "beyond": ["more than you said"] if said.get(r["id"]) == "beyond"
                              else [],
                              "contradicts": ["SR-001 conflicts"] if said.get(r["id"]) ==
                              "contradicts" else []} for r in job.inputs["records"]]}
    return answer


def run_pass(repo: Path, box: Any, jobs: int | None = None) -> list[str]:
    from plumb.understand import worker

    ran: list[str] = []
    from plumb.understand import files

    if jobs is None:
        return worker.run_once(open_core(repo), SESSION)
    queued = sorted(files.jobs_dir(repo, SESSION).glob("*.json"))
    for path in queued[:jobs]:
        ran += worker.run_once(open_core(repo), SESSION, path.stem)
    return ran


@pytest.mark.sr("SR-232")
def test_one_worker_pass_sees_prior_verdicts_and_finishes_all_jobs(
        repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog, judge, worker

    ids = bulk(repo, write_record, {"alpha": 3, "beta": 3, "gamma": 3})
    backlog.start(open_core(repo), SESSION)
    core = open_core(repo)
    core.events()  # prime the same instance the worker reuses across all jobs
    seen = []

    def answer(job):
        seen.append(len([e for e in core.events() if e.kind == "verdict"]))
        return answering()(job)

    engine_standins.dispatcher.script = {"judge": answer}
    ran = worker.run_once(core, SESSION)
    assert len(ran) == 3 and seen == [0, 4, 8]
    assert len([e for e in core.events() if e.kind == "verdict"]) == sum(map(len, ids.values()))
    assert progress(repo).state == "done"
    assert progress(repo).step == owner_text.BACKLOG_DONE.format(judged=12, questions=1)
    assert open_cards(repo) == []                       # questions, no trial card (SR-252 EX-6)
    (asked,) = judge.open_questions(open_core(repo), SESSION)    # one question asked once
    assert len(asked["records"]) == 12
    assert worker.run_once(core, SESSION) == []


def progress(repo: Path):
    from plumb.understand import files

    return files.progress_from_json(files.read_json(files.progress_path(repo, SESSION)))


def open_cards(repo: Path):
    from plumb.understand import cardstore

    return cardstore.load(repo, SESSION)


def test_sr107_ex1_150_records_one_pass_no_per_turn_limit_done_jobs_not_rerun(
        repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog, files

    plan = {f"feature {n}": 4 for n in range(1, 31)}              # 30 intents x 5 = 150 records
    bulk(repo, write_record, plan)
    engine_standins.dispatcher.script = {"judge": answering()}
    started = backlog.start(open_core(repo), SESSION)
    assert started.records == 150 and started.total == 150
    assert len(started.jobs) == 30                                # one job per intent
    assert len(list(files.jobs_dir(repo, SESSION).glob("*.json"))) == 30
    assert len(run_pass(repo, engine_standins)) == 30             # no per-turn limit
    judged = {j for job in engine_standins.dispatcher.jobs for j in
              (r["id"] for r in job.inputs["records"])}
    assert len(judged) == 150
    before = len(engine_standins.dispatcher.jobs)
    again = backlog.start(open_core(repo), SESSION)
    assert again.jobs == [] and run_pass(repo, engine_standins) == []
    assert len(engine_standins.dispatcher.jobs) == before         # done jobs are not rerun
    # a record that changed is judged again, and only its intent's job runs
    path = repo / ".plumb" / "requirements" / "SR-007.md"
    path.write_text(path.read_text(encoding="utf-8").replace("rule 7", "rule seven"),
                    encoding="utf-8")
    changed = backlog.start(open_core(repo), SESSION)
    assert len(changed.jobs) == 1
    assert run_pass(repo, engine_standins)
    (last,) = engine_standins.dispatcher.jobs[before:]
    assert [r["id"] for r in last.inputs["records"]] == ["SR-007"]


def test_sr107_ex2_fragment_premise_takes_the_question_route(
        repo: Path, write_record, engine_standins) -> None:
    """SR-248 EX-6: a record judged on a fragment of the owner's words is asked about through
    the question tool, not on a trial card."""
    from plumb.understand import backlog, judge

    bulk(repo, write_record, {"the checks": 0}, prompt=False)    # a quote, no logged message
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.99)}
    run_pass(repo, engine_standins)
    assert open_cards(repo) == []
    (asked,) = judge.open_questions(open_core(repo), SESSION)
    assert [r["id"] for r in asked["records"]] == ["INT-001"]
    seen = engine_standins.dispatcher.jobs[0].inputs["records"][0]["premise"]["messages"][0]
    assert seen["partial"] is True


def test_sr107_ex3_18_supported_take_one_question_and_no_trial_card(
        repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog, judge

    bulk(repo, write_record, {"the merge check": 17})        # and their intent: 18 records
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.95)}
    run_pass(repo, engine_standins)
    assert open_cards(repo) == []
    (asked,) = judge.open_questions(open_core(repo), SESSION)
    assert len(asked["records"]) == 18
    assert not [e for e in open_core(repo).events() if e.kind == "approval"]


def test_sr107_ex5_three_flagged_are_not_trial_cards_and_raise_no_card(
        repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog

    ids = bulk(repo, write_record, {"the merge check": 7})["the merge check"]
    backlog.start(open_core(repo), SESSION)
    flagged = {ids[2]: "beyond", ids[3]: "beyond", ids[4]: "contradicts"}
    engine_standins.dispatcher.script = {"judge": answering(0.95, flagged)}
    run_pass(repo, engine_standins)
    assert open_cards(repo) == []                       # flagged or not: no card
    assert progress(repo).step == owner_text.BACKLOG_DONE.format(judged=8, questions=1)


def test_sr107_ex6_progress_10_of_160(repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog

    bulk(repo, write_record, {f"feature {n}": 4 for n in range(1, 33)})   # 32 x 5 = 160
    started = backlog.start(open_core(repo), SESSION)
    assert started.total == 160
    engine_standins.dispatcher.script = {"judge": answering()}
    run_pass(repo, engine_standins, jobs=2)                       # two intents: 10 records
    shown = progress(repo)
    assert shown.step == owner_text.STEP_JUDGING_BACKLOG
    assert (shown.done, shown.total, shown.state) == (10, 160, "running")
    assert shown.kind == "judge"


def test_backlog_end_line_counts_judged_and_questions_awaiting(
        repo: Path, write_record, engine_standins) -> None:
    """Spec 8: when the pass ends the progress file is done, with the end line."""
    from plumb.understand import backlog

    plan = {"alpha": 38, "beta": 37, "gamma": 37, "delta": 44}   # 4 intents + 156 = 160
    ids = bulk(repo, write_record, plan)
    assert sum(len(v) for v in ids.values()) == 160
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.95)}
    run_pass(repo, engine_standins)
    shown = progress(repo)
    assert shown.state == "done"
    assert shown.step == owner_text.BACKLOG_DONE.format(judged=160, questions=1)
    assert owner_level(shown.step) == []
    assert open_cards(repo) == []


def test_sr107_ex7_model_unreachable_midway_resumes_without_rejudging(
        repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog, files

    bulk(repo, write_record, {f"feature {n}": 4 for n in range(1, 7)})        # 6 jobs
    backlog.start(open_core(repo), SESSION)
    served: list[str] = []

    def flaky(job: Job):
        if len(served) >= 3:
            return DispatchError("run", "the model could not be reached")
        served.append(job.id)
        return answering()(job)

    engine_standins.dispatcher.script = {"judge": flaky}
    run_pass(repo, engine_standins)
    first = {r["id"] for job in engine_standins.dispatcher.jobs[:3] for r in job.inputs["records"]}
    assert len(served) == 3 and len(first) == 15
    # the next turn: the failed jobs are queued again (queue.retry_failed), the pass resumes
    for result in files.results_dir(repo, SESSION).glob("*.json"):
        if files.read_json(result)["status"] == "error":
            result.unlink()
            (files.ran_dir(repo, SESSION) / result.stem).unlink(missing_ok=True)
    engine_standins.dispatcher.script = {"judge": answering()}
    resumed = backlog.start(open_core(repo), SESSION)
    assert len(resumed.jobs) == 3 and resumed.total == 30
    before = len(engine_standins.dispatcher.jobs)
    run_pass(repo, engine_standins)
    redone = {r["id"] for job in engine_standins.dispatcher.jobs[before:]
              for r in job.inputs["records"]}
    assert redone.isdisjoint(first) and len(redone) == 15
    assert progress(repo).state == "done"


def test_a_pass_that_is_not_started_is_not_resumed(repo: Path, write_record) -> None:
    from plumb.understand import backlog

    bulk(repo, write_record, {"feature": 2})
    assert backlog.resume(open_core(repo), SESSION).jobs == []
    started = backlog.start(open_core(repo), SESSION)
    resumed = backlog.resume(open_core(repo), SESSION)
    assert resumed.jobs == started.jobs != []                     # the same jobs: none twice


def test_the_pass_holds_its_records_back_from_the_trial_until_it_ends(
        repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog, trial

    bulk(repo, write_record, {"alpha": 4, "beta": 4})
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering()}
    run_pass(repo, engine_standins, jobs=1)                       # half done
    assert trial.top_up(open_core(repo), SESSION) == []           # no trial batch mid-pass


def test_a_decision_in_the_backlog_takes_the_question_route(repo: Path, write_record,
                                                          engine_standins) -> None:
    from plumb.understand import backlog, judge
    from understand.test_judge_job import decision_text

    bulk(repo, write_record, {"alpha": 2})
    write_record(repo, decision_text(1, "Which radix?", "decimal", intent=1))
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.99)}
    run_pass(repo, engine_standins)
    assert open_cards(repo) == []
    asked = {r["id"] for q in judge.open_questions(open_core(repo), SESSION)
             for r in q["records"]}
    assert "DEC-001" in asked


def test_a_record_below_the_threshold_is_asked_like_the_others(repo: Path, write_record,
                                                              engine_standins) -> None:
    from plumb.understand import backlog, judge

    ids = bulk(repo, write_record, {"alpha": 5})["alpha"]

    def graded(job: Job):
        return {"questions": [question(*(r["id"] for r in job.inputs["records"]))],
                "verdicts": [{"id": r["id"], "verdict": "beyond",
                              "confidence": 0.5 if r["id"] == ids[3] else 0.95,
                              "beyond": [], "contradicts": []}
                             for r in job.inputs["records"]]}

    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": graded}
    run_pass(repo, engine_standins)
    assert open_cards(repo) == []
    (asked,) = judge.open_questions(open_core(repo), SESSION)
    assert ids[3] in {r["id"] for r in asked["records"]}
    assert FakeDispatcher().available() is None


def test_the_turns_end_continues_a_started_pass_and_only_a_started_one(
        repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog, files, summary

    bulk(repo, write_record, {"alpha": 2, "beta": 2})
    ctx = HookContext("stop", {}, repo, SESSION, Deadline(1400))
    summary.stop_parts(ctx, open_core(repo), {"turn_start": time.time() - 60})
    assert list(files.jobs_dir(repo, SESSION).glob("*.json")) == []   # never started: not queued
    backlog.start(open_core(repo), SESSION)
    queued = sorted(files.jobs_dir(repo, SESSION).glob("*.json"))
    queued[0].unlink()                                                # a queue file was lost
    summary.stop_parts(ctx, open_core(repo), {"turn_start": time.time() - 60})
    assert sorted(files.jobs_dir(repo, SESSION).glob("*.json")) == queued
