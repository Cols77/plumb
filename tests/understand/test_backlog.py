"""SP8 lane JUDGE, J8: the backlog pass (SR-107; SR-105 EX-7; spec 8)."""

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
from understand.test_judge_job import intent_text, log_prompt, requirement_text
from understand.test_settle import SESSION

pytestmark = pytest.mark.sr("SR-107")

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


def answering(score: float = 0.95, verdicts: dict[str, str] | None = None):
    """A fake judge: every record in the job is supported at ``score`` unless named."""
    def answer(job: Job) -> dict[str, Any]:
        said = verdicts or {}
        return {"verdicts": [{"id": r["id"], "verdict": said.get(r["id"], "supported"),
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

    queued = sorted(files.jobs_dir(repo, SESSION).glob("*.json"))
    for path in queued[:jobs]:
        ran += worker.run_once(open_core(repo), SESSION, path.stem)
    return ran


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


def test_sr107_ex2_fragment_premise_says_words_not_on_file(repo: Path, write_record,
                                                           engine_standins) -> None:
    from plumb.understand import backlog

    bulk(repo, write_record, {"the checks": 0}, prompt=False)    # a quote, no logged message
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.99)}
    run_pass(repo, engine_standins)
    (card,) = open_cards(repo)
    assert card.kind == "backlog" and card.topic == "Intent about the checks"
    assert "original words are not on file" in card.issue
    assert "Intent about the checks" in card.issue                # offers its read-back
    assert card.resolutions == (owner_text.NO_ORIGINAL_ACCEPT, owner_text.NO_ORIGINAL_CORRECT)
    assert card.questions[0].record == "INT-001"
    seen = engine_standins.dispatcher.jobs[0].inputs["records"][0]["premise"]["messages"][0]
    assert seen["partial"] is True


def test_sr107_ex3_18_supported_one_feature_card_yes_confirms_all_labelled(
        repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog

    bulk(repo, write_record, {"the merge check": 17})        # and their intent: 18 records
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.95)}
    run_pass(repo, engine_standins)
    cards = [c for c in open_cards(repo) if c.kind == "backlog"]
    assert len(cards) == 1
    card = cards[0]
    assert card.topic == "the merge check"
    assert card.issue == "these 18 about the merge check would be settled; right?"
    assert len(card.questions) == 18
    assert {q.record for q in card.questions} == {"INT-001",
                                                  *(f"SR-{n:03d}" for n in range(1, 18))}
    assert card.resolutions == (owner_text.BACKLOG_YES, owner_text.BACKLOG_EXCEPT,
                                owner_text.BACKLOG_NO)
    # the owner's yes: every record on the card is confirmed, labelled yes
    confirmed: list[tuple[Any, ...]] = []
    from plumb.understand import effects

    handler = effects.handler_for("backlog")
    answered = card.__class__(**{**card.__dict__, "status": "answered"})
    handler(core=open_core(repo), job=None, card=answered, question=None,
            entry={"answer": "accepted", "confidence": 0.95, "evidence": "yes"},
            message="yes", digest="sha256:0", accepted=True,
            confirm=lambda *a, **k: confirmed.append((a, k)))
    assert len(confirmed) == 18
    assert {a[0] for a, _ in confirmed} == {q.record for q in card.questions}
    assert all(k.get("label") == "yes" for _, k in confirmed)
    hashes = {a[0]: a[1] for a, _ in confirmed}
    index = open_core(repo).index()
    assert all(hashes[r] == index[r].hash for r in hashes)


def test_a_record_answered_one_by_one_is_left_to_the_reader(repo: Path, write_record,
                                                            engine_standins) -> None:
    """"yes, except SR-040": the reader maps each record; the handler adds nothing on a
    per-record answer (READ confirmed the 17, labelled yes)."""
    from plumb.understand import backlog, effects

    bulk(repo, write_record, {"the merge check": 3})
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.95)}
    run_pass(repo, engine_standins)
    card = next(c for c in open_cards(repo) if c.kind == "backlog")
    called: list[Any] = []
    result = effects.handler_for("backlog")(
        core=open_core(repo), job=None, card=card, question=card.questions[0].id,
        entry={"answer": "accepted", "record": card.questions[0].record, "hash": "h"},
        message="m", digest="d", accepted=True, confirm=lambda *a, **k: called.append(a))
    assert called == [] and result is None


def test_sr107_ex5_three_flagged_are_issue_cards_not_on_the_feature_card(
        repo: Path, write_record, engine_standins) -> None:
    from plumb.understand import backlog

    ids = bulk(repo, write_record, {"the merge check": 7})["the merge check"]
    backlog.start(open_core(repo), SESSION)
    flagged = {ids[2]: "beyond", ids[3]: "beyond", ids[4]: "contradicts"}
    engine_standins.dispatcher.script = {"judge": answering(0.95, flagged)}
    run_pass(repo, engine_standins)
    cards = open_cards(repo)
    issue = [c for c in cards if c.kind in ("beyond", "contradicts")]
    assert sorted(c.questions[0].record for c in issue) == sorted(flagged)
    (feature,) = [c for c in cards if c.kind == "backlog"]
    on_card = {q.record for q in feature.questions}
    assert on_card.isdisjoint(flagged) and len(on_card) == 5       # 8 records, 3 flagged
    assert "these 5 about the merge check" in feature.issue


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


def test_backlog_end_line_counts_judged_and_cards_awaiting(
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
    assert shown.step == owner_text.BACKLOG_DONE.format(judged=160, cards=4)
    assert owner_level(shown.step) == []
    assert len([c for c in open_cards(repo) if c.kind == "backlog"]) == 4


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


def test_sr105_ex7_eighteen_merge_check_records_one_card(repo: Path, write_record,
                                                         engine_standins) -> None:
    from plumb.understand import backlog, summary

    bulk(repo, write_record, {"the merge check": 17})
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.95)}
    run_pass(repo, engine_standins)
    ctx = HookContext("stop", {}, repo, SESSION, Deadline(1400))
    out = summary.stop_parts(ctx, open_core(repo), {"turn_start": time.time() - 3600})
    (text,) = out.cards
    assert text.splitlines()[0].endswith("these 18 about the merge check would be settled; right?")
    assert text.count("\n  - ") == 18                            # lists them in the owner's terms
    assert owner_level(text) == []


def test_cards_per_turn_metered_most_records_first(repo: Path, write_record,
                                                   engine_standins) -> None:
    from plumb.understand import backlog, summary

    (repo / ".plumb" / "config.yaml").write_text(
        "understand:\n  backlog_cards_per_turn: 2\n", encoding="utf-8")
    bulk(repo, write_record, {"small one": 3, "big one": 10, "middle one": 7})
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.95)}
    run_pass(repo, engine_standins)

    def turn(n: int) -> list[str]:
        ctx = HookContext("stop", {}, repo, SESSION, Deadline(1400))
        return list(summary.stop_parts(ctx, open_core(repo),
                                       {"turn_start": time.time() - 3600 + n}).cards)

    first = turn(0)
    assert len(first) == 2
    assert "these 11 about big one" in first[0] and "these 8 about middle one" in first[1]
    second = turn(1)
    assert len(second) == 1 and "these 4 about small one" in second[0]
    assert turn(2) == []
    # all three are still open cards for the reader: metering is of what is shown
    assert len([c for c in open_cards(repo) if c.kind == "backlog"]) == 3


def test_a_decision_in_the_backlog_is_asked_on_its_own(repo: Path, write_record,
                                                       engine_standins) -> None:
    from plumb.understand import backlog
    from understand.test_judge_job import decision_text

    bulk(repo, write_record, {"alpha": 2})
    write_record(repo, decision_text(1, "Which radix?", "decimal", intent=1))
    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": answering(0.99)}
    run_pass(repo, engine_standins)
    cards = open_cards(repo)
    single = [c for c in cards if c.kind == "trial"]
    assert [c.questions[0].record for c in single] == ["DEC-001"]
    (feature,) = [c for c in cards if c.kind == "backlog"]
    assert "DEC-001" not in {q.record for q in feature.questions}


def test_one_below_threshold_record_rides_on_the_feature_card(repo: Path, write_record,
                                                               engine_standins) -> None:
    from plumb.understand import backlog

    ids = bulk(repo, write_record, {"alpha": 5})["alpha"]

    def graded(job: Job):
        return {"verdicts": [{"id": r["id"], "verdict": "supported",
                              "confidence": 0.5 if r["id"] == ids[3] else 0.95,
                              "beyond": [], "contradicts": []}
                             for r in job.inputs["records"]]}

    backlog.start(open_core(repo), SESSION)
    engine_standins.dispatcher.script = {"judge": graded}
    run_pass(repo, engine_standins)
    (feature,) = [c for c in open_cards(repo) if c.kind == "backlog"]
    assert feature.issue == "these 5 about alpha would be settled; right?"
    assert len(feature.questions) == 6
    assert feature.questions[-1].record == ids[3]
    assert owner_text.TRIAL_BELOW in feature.questions[-1].text
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
