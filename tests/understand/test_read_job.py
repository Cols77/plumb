"""R1: the reader kind builds one job per turn from the logs (SR-101, SR-104 EX-8)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from iaso.api import open_core
from iaso.understand import files, judge

pytestmark = pytest.mark.sr("SR-214")

SESSION = "s1"


def record_text(n: int, title: str = "") -> str:
    return (f"---\nid: SR-{n:03d}\ntitle: {title or f'Requirement {n}'}\nfeature: FEAT-001\n"
            f"statement: statement {n}\nexamples:\n- id: EX-1\n  given: a\n  when: b\n"
            f"  then: c\n---\n")


def int_text(n: int, title: str = "") -> str:
    return f"---\nid: INT-{n:03d}\ntitle: {title or f'Intent {n}'}\nstatus: proposed\n---\nbody\n"


def make_core(repo: Path, write_record, texts: list[str]):
    for text in texts:
        write_record(repo, text)
    return open_core(repo)


def log_prompt(core, text: str, *, at: str = "2026-10-10T10:00:00Z", via: str = "hook") -> str:
    from iaso.approvals import prompt_digest

    digest = prompt_digest(text)
    path = core.paths.prompts
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"digest": digest, "session": SESSION, "at": at, "text": text,
                                 "via": via, "host": "claude-code"}) + "\n")
    return digest


def state(core, ids: list[str], *, shown: bool = True, at: str = "2026-10-10T09:00:00Z"):
    index = core.index()
    data = {"at": at, "session": SESSION, "reply_after_prompt": None,
            "records": [{"id": i, "hash": index[i].hash, "shown": shown} for i in ids]}
    core.paths.stated.parent.mkdir(parents=True, exist_ok=True)
    core.paths.stated.write_text(json.dumps(data), encoding="utf-8")


def open_question(core, key: str = "Which format?", options=("CSV", "JSON")) -> None:
    """One open judge question about SR-001 (a typed answer can answer it)."""
    judge.add_question(core, SESSION, {
        "key": judge.question_key(key), "job": "judge-q", "principle": "", "blocking": False,
        "diagram": False, "reword": False, "question": key, "header": "Export",
        "records": [{"id": "SR-001", "hash": core.index()["SR-001"].hash}],
        "options": [{"label": o, "description": f"use {o}"} for o in options]})


def ctx_for(core) -> SimpleNamespace:
    return SimpleNamespace(session_id=SESSION, root=core.root)


@pytest.fixture
def five(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(n) for n in range(1, 6)])


def test_ex12_five_records_and_a_question_one_job_one_entry_each(
        five, engine_standins, monkeypatch) -> None:
    from iaso.understand import read

    ids = [f"SR-{n:03d}" for n in range(1, 6)]
    state(five, ids)
    open_question(five)
    message = "SR-001 ok, SR-002 ok, 3 ok, 4 no, 5 ok, and CSV for the export"
    digest = log_prompt(five, message)
    job = read.build(five, SESSION, message={"digest": digest, "text": message})
    assert job is not None and job.kind == "read" and job.schema == "read.v1"
    assert [item["id"] for item in job.inputs["shown"]] == ids
    assert all(item["hash"] == five.index()[item["id"]].hash and item["text"]
               for item in job.inputs["shown"])
    assert job.inputs["message"] == {"digest": digest, "text": message}
    (question_item,) = job.inputs["questions"]
    assert question_item["kind"] == "judge" and question_item["resolutions"] == ["CSV", "JSON"]
    entries = [{"id": i, "hash": five.index()[i].hash, "answer": "accepted",
                "evidence": "ok", "confidence": 0.95} for i in ids]
    entries.append({"id": question_item["id"], "hash": "", "answer": "accepted",
                    "evidence": "CSV", "confidence": 0.9})
    engine_standins.dispatcher.script = {"read": {"entries": entries}}
    from iaso.understand import queue, worker

    queue.enqueue(five, job)
    # the judge job the read queues runs in the same pass (the queue is read before each job)
    assert worker.run_once(five, SESSION)[0] == job.id
    (run,) = engine_standins.dispatcher.ran("read")
    assert run.id == job.id
    result = files.read_json(files.results_dir(five.root, SESSION) / f"{job.id}.json")
    assert len(result["answer"]["entries"]) == 6


def test_one_job_per_turn_six_items(five, engine_standins) -> None:
    """SR-104 EX-8: one read job covers the five records and the question; a retried hook
    queues nothing twice."""
    from iaso.understand import read

    state(five, [f"SR-{n:03d}" for n in range(1, 6)])
    open_question(five)
    message = "yes to all of it, CSV"
    log_prompt(five, message)
    entry = {"digest": __import__("iaso.approvals", fromlist=["x"]).prompt_digest(message),
             "text": message}
    first = read.on_prompt(ctx_for(five), five, entry)
    second = read.on_prompt(ctx_for(five), five, entry)
    assert first is not None and first == second
    queued = list(files.jobs_dir(five.root, SESSION).glob("*.json"))
    assert [p.stem for p in queued] == [first]
    job = files.job_from_json(files.read_json(queued[0]))
    assert len(job.inputs["shown"]) == 5 and len(job.inputs["questions"]) == 1


def test_no_job_when_nothing_stated(five, engine_standins) -> None:
    from iaso.understand import read

    message = "ok"
    digest = log_prompt(five, message)
    entry = {"digest": digest, "text": message}
    assert read.build(five, SESSION, message=entry) is None
    assert read.on_prompt(ctx_for(five), five, entry) is None
    assert list(files.jobs_dir(five.root, SESSION).glob("*.json")) == []


def test_unshown_records_are_not_in_the_shown_set(five) -> None:
    from iaso.understand import read

    state(five, ["SR-001"], shown=False)
    message = "ok"
    digest = log_prompt(five, message)
    assert read.build(five, SESSION, message={"digest": digest, "text": message}) is None


def test_schema_has_only_four_answers() -> None:
    from iaso.understand import read

    schema = json.loads((Path(read.__file__).parent / "schemas" / "read.json")
                        .read_text(encoding="utf-8"))
    item = schema["properties"]["entries"]["items"]
    assert item["properties"]["answer"]["enum"] == ["accepted", "rejected", "change", "open"]
    assert item["properties"]["rejection"]["enum"] == ["misread", "intent-changed", None]
    assert {"id", "hash", "answer", "rejection", "option", "change",
            "evidence", "confidence"} == set(item["properties"])
    assert read.schema["properties"]["entries"] == schema["properties"]["entries"]
    system = (Path(read.__file__).parent / "agents" / "read.md").read_text(encoding="utf-8")
    assert "accepted" in system and "evidence" in system


def test_evalset_reader_cases_load_and_run_on_the_fake() -> None:
    from iaso.understand import evalrun, read

    cases = evalrun.load_cases("read")
    names = {c["name"] for c in cases}
    assert {"int008-ok-sr088-change", "confirm-three-int24-loose",
            "reject-all-g-ten-variations"} <= names
    results = evalrun.run_cases(evalrun.FakeEvalDispatcher(), cases, "read")
    assert len(results) == len(cases) and all(r["passed"] for r in results)
    for each in cases:
        inputs, entries = each["inputs"], each["expect"]["entries"]
        shown = {i["id"] for i in inputs["shown"]}
        card_ids = {i["id"] for i in inputs["questions"]}
        text = inputs["message"]["text"]
        for answer in entries:
            assert answer["id"] in shown | card_ids, each["name"]
            assert read.evidence_in(answer["evidence"], text), each["name"]
            assert answer["answer"] in ("accepted", "rejected", "change", "open")
    (ten,) = [c for c in cases if c["name"] == "reject-all-g-ten-variations"]
    assert len(ten["inputs"]["shown"]) == 10 and len(ten["expect"]["entries"]) == 10
