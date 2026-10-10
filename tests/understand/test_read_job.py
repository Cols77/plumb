"""R1: the reader kind builds one job per turn from the logs (SR-101, SR-104 EX-8)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from understand.fakes import FakeDispatcher

from plumb.api import open_core
from plumb.contracts import CardState, ClarifyQuestion
from plumb.understand import cardstore, files

pytestmark = pytest.mark.sr("SR-101")

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
    from plumb.approvals import prompt_digest

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


def open_card(core, card: CardState) -> None:
    cardstore.save(core.root, SESSION, [*cardstore.own_cards(core.root, SESSION), card])


def clarify_card(card_id: str = "card-1") -> CardState:
    return CardState(
        id=card_id, kind="clarify", topic="Export", issue="which format?",
        questions=(ClarifyQuestion(id="q1", text="Which format?",
                                   resolutions=("CSV", "JSON")),))


def ctx_for(core) -> SimpleNamespace:
    return SimpleNamespace(session_id=SESSION, root=core.root)


@pytest.fixture
def five(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(n) for n in range(1, 6)])


def test_ex12_five_records_and_a_card_one_job_one_entry_each(
        five, engine_standins, monkeypatch) -> None:
    from plumb.understand import read

    ids = [f"SR-{n:03d}" for n in range(1, 6)]
    state(five, ids)
    open_card(five, clarify_card())
    message = "SR-001 ok, SR-002 ok, 3 ok, 4 no, 5 ok, and CSV for the export"
    digest = log_prompt(five, message)
    job = read.build(five, SESSION, message={"digest": digest, "text": message})
    assert job is not None and job.kind == "read" and job.schema == "read.v1"
    assert [item["id"] for item in job.inputs["shown"]] == ids
    assert all(item["hash"] == five.index()[item["id"]].hash and item["text"]
               for item in job.inputs["shown"])
    assert job.inputs["message"] == {"digest": digest, "text": message}
    (card_item,) = job.inputs["cards"]
    assert card_item["card"] == "card-1" and card_item["resolutions"] == ["CSV", "JSON"]
    entries = [{"id": i, "hash": five.index()[i].hash, "answer": "accepted",
                "evidence": "ok", "confidence": 0.95} for i in ids]
    entries.append({"id": card_item["id"], "hash": "", "answer": "accepted",
                    "evidence": "CSV", "confidence": 0.9})
    engine_standins.dispatcher.script = {"read": {"entries": entries}}
    from plumb.understand import queue, worker

    queue.enqueue(five, job)
    assert worker.run_once(five, SESSION) == [job.id]
    (run,) = engine_standins.dispatcher.ran("read")
    assert run.id == job.id
    result = files.read_json(files.results_dir(five.root, SESSION) / f"{job.id}.json")
    assert len(result["answer"]["entries"]) == 6


def test_one_job_per_turn_six_items(five, engine_standins) -> None:
    """SR-104 EX-8: one read job covers the five records and the card; a retried hook
    queues nothing twice."""
    from plumb.understand import read

    state(five, [f"SR-{n:03d}" for n in range(1, 6)])
    open_card(five, clarify_card())
    message = "yes to all of it, CSV"
    log_prompt(five, message)
    entry = {"digest": __import__("plumb.approvals", fromlist=["x"]).prompt_digest(message),
             "text": message}
    first = read.on_prompt(ctx_for(five), five, entry)
    second = read.on_prompt(ctx_for(five), five, entry)
    assert first is not None and first == second
    queued = list(files.jobs_dir(five.root, SESSION).glob("*.json"))
    assert [p.stem for p in queued] == [first]
    job = files.job_from_json(files.read_json(queued[0]))
    assert len(job.inputs["shown"]) == 5 and len(job.inputs["cards"]) == 1


def test_no_job_when_nothing_stated(five, engine_standins) -> None:
    from plumb.understand import read

    message = "ok"
    digest = log_prompt(five, message)
    entry = {"digest": digest, "text": message}
    assert read.build(five, SESSION, message=entry) is None
    assert read.on_prompt(ctx_for(five), five, entry) is None
    assert list(files.jobs_dir(five.root, SESSION).glob("*.json")) == []


def test_unshown_records_are_not_in_the_shown_set(five) -> None:
    from plumb.understand import read

    state(five, ["SR-001"], shown=False)
    message = "ok"
    digest = log_prompt(five, message)
    assert read.build(five, SESSION, message={"digest": digest, "text": message}) is None


def test_schema_has_only_four_answers() -> None:
    from plumb.understand import read

    schema = json.loads((Path(read.__file__).parent / "schemas" / "read.json")
                        .read_text(encoding="utf-8"))
    item = schema["properties"]["entries"]["items"]
    assert item["properties"]["answer"]["enum"] == ["accepted", "rejected", "change", "open"]
    assert item["properties"]["rejection"]["enum"] == ["misread", "intent-changed", None]
    assert {"id", "hash", "answer", "rejection", "change", "evidence",
            "confidence"} == set(item["properties"])
    assert read.schema["properties"]["entries"] == schema["properties"]["entries"]
    system = (Path(read.__file__).parent / "agents" / "read.md").read_text(encoding="utf-8")
    assert "accepted" in system and "evidence" in system
