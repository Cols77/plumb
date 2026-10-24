"""Phase I end-to-end flows (sp8 plan 12.2, SR-101 to SR-111).

Every flow runs through the real hook entry points as subprocesses (``harness.Session``), with a
scripted model: ``PLUMB_FAKE_DISPATCH`` names a file of ``{kind: answer}`` that the worker
reads before each job, so a test changes the model's next answers by rewriting that file. The
worker is the real worker, started by the hooks as in a session. Nothing here reaches a model.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from plumb import links, stale
from plumb.api import open_core
from plumb.present import owner_text
from plumb.understand import files
from plumb.understand.repin import Meaning
from understand.fakes import owner_level
from understand.harness import Session
from understand.test_read_job import int_text, record_text

pytestmark = pytest.mark.sr("SR-214", "SR-239", "SR-223", "SR-273", "SR-267", "SR-252")

SID = "harness"
NOTHING = {"intent": "no", "gap": False, "gaps": []}
GAPS = {"intent": "yes", "topic": "exporting data", "gap": True,
        "gaps": [{"id": "format", "question": "Which format?", "suggestions": ["csv", "json"],
                  "blocking": True}]}
CLEAR = {"intent": "yes", "topic": "exporting data", "gap": False, "gaps": []}
ROOMY = ("calibration: {min_items: 5, min_negatives: 1}\n"
         "hooks:\n  budget_ms: {stop: 8000}\n")


class FixedMeaning:
    """A repin meaning judge with a fixed answer."""

    def __init__(self, unchanged: bool) -> None:
        self.answer = Meaning(unchanged, "fixed", 0.95)

    def same_meaning(self, **shown: Any) -> Meaning:
        return self.answer


# ---- helpers -----------------------------------------------------------------------------


def model(s: Session, **kinds: Any) -> None:
    """The scripted model's next answers (a kind left out answers 'nothing to say')."""
    base: dict[str, Any] = {"clarify": NOTHING, "read": {"entries": []},
                            "judge": {"verdicts": []}}
    s.script_path.write_text(json.dumps({**base, **kinds}), encoding="utf-8")


def calls(s: Session, kind: str | None = None) -> list[dict[str, str]]:
    """The model calls so far (one line per call, written by the scripted dispatcher)."""
    path = s.script_path.with_name(s.script_path.name + ".calls")
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [r for r in rows if kind in (None, r["kind"])]


def plumb(s: Session, *argv: str, timeout: float = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "plumb", *argv], capture_output=True,
                          text=True, encoding="utf-8", cwd=s.repo, env=s.env(), timeout=timeout)


def events(repo: Path, kind: str) -> list[Any]:
    return [e for e in open_core(repo).events() if e.kind == kind]


def owner_words_approvals(repo: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in events(repo, "approval"):
        if e.payload.get("by") == "owner-words":
            for record in e.payload["records"]:
                out[record["id"]] = dict(e.payload)
    return out


def judge_approvals(repo: Path) -> dict[str, dict[str, Any]]:
    """The judge's approvals (``auto-model``, ``auto-jev``) by record id."""
    return {r["id"]: dict(e.payload) for e in events(repo, "approval")
            if e.payload.get("by") in ("auto-model", "auto-jev") for r in e.payload["records"]}


def judge_clear(*ids: str, **contradicted: list[str]) -> dict[str, Any]:
    """The scripted judge model: each of ``ids`` supported and clear; each of
    ``contradicted`` (id with '-' as '_') contradicted by the owner's words."""
    return {"verdicts": [
        *({"id": i, "verdict": "supported", "confidence": 0.9, "clear": True} for i in ids),
        *({"id": i.replace("_", "-"), "verdict": "contradicts", "confidence": 0.9,
           "contradicts": why, "clear": False} for i, why in contradicted.items())]}


def last_digest(repo: Path) -> str:
    rows = (repo / ".plumb" / "session" / "prompts.jsonl").read_text(
        encoding="utf-8").splitlines()
    return json.loads(rows[-1])["digest"]


def short(digest: str) -> str:
    return digest.removeprefix("sha256:")[:16]


def text_of(out: str) -> str:
    """The owner-facing message of a hook's JSON answer ('' when it said nothing)."""
    if not out.strip():
        return ""
    data = json.loads(out)
    return str(data.get("systemMessage") or data.get("reason") or "")


def agent_of(s: Session) -> str:
    """SR-266: what the stop queued for the agent's channel (cards, judge counts), taken once."""
    from host.fakes import agent_notes

    return agent_notes(s.repo, s.session_id)


def own_cards(s: Session) -> list[dict[str, Any]]:
    path = s.repo / ".plumb" / "session" / s.session_id / "cards.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def deny(s: Session, rel: str = "src/feature.py") -> bool:
    """Whether the edit guard refuses an edit of ``rel`` right now."""
    out = s.hook("pre-tool", hook_event_name="PreToolUse", tool_name="Edit",
                 tool_input={"file_path": str(s.repo / rel)})
    return bool(out.strip()) and json.loads(out)["hookSpecificOutput"][
        "permissionDecision"] == "deny"


def show(s: Session, ids: list[str]) -> None:
    """The previous reply showed these records (what the stop hook records as stated)."""
    core = open_core(s.repo)
    index = core.index()
    core.paths.stated.parent.mkdir(parents=True, exist_ok=True)
    core.paths.stated.write_text(json.dumps({
        "at": "2026-10-10T09:00:00Z", "session": s.session_id, "reply_after_prompt": None,
        "records": [{"id": i, "hash": index[i].hash, "shown": True} for i in ids]}),
        encoding="utf-8")


def at_owner_level(*texts: str, quoted: tuple[str, ...] = ()) -> None:
    """Both owner-text scanners pass; the owner's own words, quoted back, are theirs to say."""
    for text in texts:
        for words in quoted:
            text = text.replace(words, "")
        assert owner_level(text) == [], text


# ---- (1) a request with gaps ----------------------------------------------------------------


def test_flow_1_request_with_gaps_one_card_one_answer(repo: Path) -> None:
    s = Session(repo)
    model(s, clarify=GAPS)
    s.start()
    said = s.say("/plumb clarify let users export their data")
    assert "Waiting for your answer before building" in said     # the gate closed at once
    assert deny(s)                                                # an edit is refused
    assert s.worker_idle(30)

    done = plumb(s, "clarify", "--wait", "--json", "--root", str(repo), "--timeout", "30")
    card = json.loads(done.stdout)
    assert card["state"] == "card" and card["card"]
    at_owner_level(*card["lines"])
    assert deny(s)                                                # still closed: unanswered
    (open_card,) = [c for c in own_cards(s) if c["status"] == "open" and c["kind"] == "choice"]
    question = f'{open_card["id"]}/{open_card["questions"][0]["id"]}'

    # the owner answers in one message; the read job applies before the clarify job runs
    model(s, clarify=NOTHING, read={"entries": [{
        "id": question, "hash": "", "answer": "accepted", "change": "csv",
        "evidence": "csv please", "confidence": 0.95}]})
    s.say("csv please, for everything")
    assert s.worker_idle(30)
    jobs = [files.job_from_json(json.loads(p.read_text(encoding="utf-8")))
            for p in (repo / ".plumb" / "session" / SID / "jobs").glob("*.json")]
    (read_job,) = [j for j in jobs if j.kind == "read"]
    assert [j for j in jobs if j.kind == "clarify" and j.needs] == []   # SR-171: no second check

    assert not deny(s)                                            # the gate opened
    cards = [c for c in own_cards(s) if c["kind"] == "choice"]
    assert [c["status"] for c in cards] == ["answered"]           # no second choice card
    assert cards[0]["answers"][0]["answer"] == "accepted"
    again = json.loads(plumb(s, "clarify", "--wait", "--json", "--root", str(repo),
                             "--timeout", "30").stdout)
    assert again["state"] == "ready"
    at_owner_level(*again["lines"])
    assert len(calls(s, "clarify")) == 1                          # only the command runs a check


# ---- (2) a mixed answer ---------------------------------------------------------------------


def test_flow_2_mixed_answer_one_job_confirm_and_change(repo: Path, write_record) -> None:
    write_record(repo, int_text(8, "Internal features"))
    write_record(repo, record_text(88, "Plain words UX"))
    index = open_core(repo).index()
    s = Session(repo)
    show(s, ["INT-008", "SR-088"])
    message = ("INT-008 ok, I am not sure I agree with SR-088. In terms of UX, some features "
               "might have to remain internal to plumb.")
    entries = [
        {"id": "INT-008", "hash": index["INT-008"].hash, "answer": "accepted",
         "evidence": "INT-008 ok", "confidence": 0.97},
        {"id": "SR-088", "hash": index["SR-088"].hash, "answer": "change",
         "change": "some features stay internal", "confidence": 0.9,
         "evidence": "I am not sure I agree with SR-088"}]
    s.script_path.write_text(json.dumps({
        "$delay": 10, "clarify": NOTHING, "read": {"entries": entries},
        "judge": judge_clear("INT-008", SR_088=["some features stay internal"])}),
        encoding="utf-8")
    s.start()
    # SR-298: session start queues the waiting records from a process of its own; the answer
    # is sent once that backlog is judged, so the reading below is the message's own
    from plumb.understand import jobs as queued_jobs

    until = time.monotonic() + 60
    while time.monotonic() < until and not (
            (backlog := [j for j in queued_jobs.queued(repo, s.session_id)
                         if j.inputs.get("pass") == "backlog"])
            and not [j for j in queued_jobs.pending(repo, s.session_id) if j in backlog]):
        time.sleep(0.2)
    assert s.worker_idle(40)
    s.say(message)
    lines: list[str] = []
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline and owner_text.STEP_READING not in (
            line := s.status_line()):
        time.sleep(0.2)
    lines.append(line)
    assert owner_text.STEP_READING in line                       # "reading your answer"
    assert events(repo, "approval") == []                        # nothing confirmed meanwhile
    assert s.worker_idle(40)

    # the reading keeps the message as a pre-intent; the judge approves with the words
    (kept,) = events(repo, "pre-intent")
    assert kept.payload["text"] == message
    assert set(judge_approvals(repo)) == {"INT-008"} and owner_words_approvals(repo) == {}
    assert judge_approvals(repo)["INT-008"]["answers"] == [kept.digest]
    status = open_core(repo).status()
    assert status["INT-008"].confirmation == "confirmed"
    assert status["SR-088"].confirmation != "confirmed"           # sent back to be reworded
    assert not [c for c in own_cards(s) if c["id"].startswith("change:")]
    assert len(calls(s, "read")) == 1                             # one read job for the message
    said = text_of(s.stop())
    assert owner_text.JUDGE_APPROVED not in said                  # SR-265 EX-7: the agent's
    assert owner_text.JUDGE_APPROVED in agent_of(s)
    lines.append(said)
    lines.append(s.status_line())
    at_owner_level(*[ln for ln in lines if ln],
                   quoted=("INT-008 ok", "I am not sure I agree with SR-088"))


# ---- (3) capture, trial, calibration -------------------------------------------


def _capture_doc() -> dict[str, Any]:
    requirements = [{"title": f"Operation {n}", "statement": f"The calculator does operation {n}",
                     "examples": [{"given": f"input {n}", "when": "it runs",
                                   "then": f"output {n}"}]} for n in range(1, 7)]
    return {"intent": {"quote": "Build a small calculator", "readback": "A small calculator",
                       "will": ["do six operations"], "wont": ["nothing else"]},
            "requirements": requirements}


def test_flow_3_capture_asks_through_the_question_tool_and_draws_no_trial(repo: Path) -> None:
    """SR-248 EX-3, SR-252 EX-6: after a capture the judge model's question waits for the
    question tool (``clarify --wait`` answers ``ask``); the turn end draws no trial or read-back
    card and nothing is approved without a question round."""
    (repo / ".plumb" / "config.yaml").write_text(ROOMY, encoding="utf-8")
    s = Session(repo)
    s.start()
    model(s, clarify=CLEAR)
    s.say("Build a small calculator: it adds, subtracts, multiplies, divides, takes powers "
          "and takes roots of whole numbers.")
    assert s.worker_idle(30)

    # one capture: one judge job for the intent and the six requirements, one question for all
    ids = ["INT-001", *(f"SR-00{n}" for n in range(1, 7))]
    asked = {"question": "Should the calculator work on whole numbers only?",
             "header": "Numbers", "records": ids,
             "options": [{"label": "Whole numbers", "consequence": "As you said; no decimals."},
                         {"label": "Decimals too", "consequence": "Wider; more to build."}],
             "recommended_reason": "you said whole numbers",
             "request": {"words": "takes roots of whole numbers", "date": "16 Oct"}}
    model(s, judge={"verdicts": [{"id": rid, "verdict": "supported", "confidence": 0.9}
                                 for rid in ids], "questions": [asked]})
    (repo / "capture.json").write_text(json.dumps(_capture_doc()), encoding="utf-8")
    done = plumb(s, "capture", "--file", str(repo / "capture.json"), "--prompt",
                 short(last_digest(repo)))
    assert done.returncode == 0, done.stderr
    assert s.worker_idle(30)
    assert len(calls(s, "judge")) == 1

    waited = plumb(s, "clarify", "--wait", "--json")
    assert waited.returncode == 0, waited.stderr
    shown = json.loads(waited.stdout)
    assert shown["state"] == "ask"
    (question,) = shown["questions"]
    assert question["options"][0]["label"] == "Whole numbers (Recommended)"
    assert "takes roots of whole numbers" in question["question"]
    at_owner_level(question["question"], *(o["description"] for o in question["options"]))

    s.stop()
    assert not [c for c in own_cards(s) if c["kind"] in ("trial", "clarify")]
    assert not events(repo, "approval")                  # no approval without a question round


# ---- (5) every failure of spec 9.1 ------------------------------------------------------------


def _accept_int8(index: Any, evidence: str = "INT-008 ok") -> dict[str, Any]:
    return {"entries": [{"id": "INT-008", "hash": index["INT-008"].hash, "answer": "accepted",
                         "evidence": evidence, "confidence": 0.97}]}


def test_flow_5_failures_confirm_nothing_and_retry_next_turn(repo: Path, write_record) -> None:
    write_record(repo, int_text(8, "Internal features"))
    index = open_core(repo).index()
    s = Session(repo)
    show(s, ["INT-008"])
    s.start()

    # no model at all: "INT-008 ok" would pass the word rules, but nothing is confirmed
    s.script_path.unlink()
    s.say("INT-008 ok")
    assert s.worker_idle(30)
    assert owner_words_approvals(repo) == {}
    assert events(repo, "approval") == []
    assert text_of(s.stop()) == ""                    # SR-265, SR-363: no question count
    couldnt = agent_of(s)                                        # SR-266: the card is the agent's
    assert "did not finish" in couldnt.lower()
    at_owner_level(couldnt, quoted=("INT-008 ok",))

    # the model is back: the next turn retries the failed job and the judge approves
    model(s, read=_accept_int8(index), judge=judge_clear("INT-008"))
    s.say("what is left to do?")
    assert s.worker_idle(30)
    assert set(judge_approvals(repo)) == {"INT-008"}
    s.stop()
    assert owner_text.JUDGE_APPROVED in agent_of(s)


def test_flow_5_schema_failure_and_a_record_edited_after_it_was_shown(
        repo: Path, write_record) -> None:
    write_record(repo, int_text(8, "Internal features"))
    index = open_core(repo).index()
    s = Session(repo)
    show(s, ["INT-008"])
    model(s, read={"entries": "not a list of entries"})            # fails the schema
    s.start()
    s.say("INT-008 ok")
    assert s.worker_idle(30)
    assert owner_words_approvals(repo) == {}
    failed = json.loads(next((repo / ".plumb" / "session" / SID / "results").glob(
        "read-*.json")).read_text(encoding="utf-8"))
    assert failed["status"] == "error" and failed["error"]["step"] == "schema"

    # the record is edited after the owner saw it: an answer about the old version confirms
    # nothing, whatever the model says
    path = repo / ".plumb" / "intents" / "INT-008.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Internal features",
                                                              "Internal features, reworded"),
                    encoding="utf-8")
    model(s, read=_accept_int8(index))
    s.say("INT-008 ok, really")
    assert s.worker_idle(30)
    assert owner_words_approvals(repo) == {}
    assert open_core(repo).status()["INT-008"].confirmation != "confirmed"


def test_flow_5_three_failures_show_in_the_status_line_and_clear_on_success(
        repo: Path, write_record) -> None:
    write_record(repo, int_text(8, "Internal features"))
    index = open_core(repo).index()
    s = Session(repo)
    show(s, ["INT-008"])
    model(s, **{"$fail_when": {"contains": ""}})                    # every call fails
    s.start()
    for n in range(3):
        s.say(f"INT-008 ok {n}")
        assert s.worker_idle(30)
    line = s.status_line()
    failed = re.search(r"failed (\d+) times in a row", line)
    assert failed and int(failed.group(1)) >= 3, line
    at_owner_level(line)
    model(s, read=_accept_int8(index, "INT-008 ok"))
    s.say("INT-008 ok")
    assert s.worker_idle(30)
    assert "in a row" not in s.status_line()


def test_flow_5_a_job_not_finished_at_the_turns_end_is_collected_next_turn(
        repo: Path, write_record) -> None:
    write_record(repo, int_text(8, "Internal features"))
    index = open_core(repo).index()
    s = Session(repo)
    show(s, ["INT-008"])
    s.script_path.write_text(json.dumps({"$delay": 3, "clarify": NOTHING,
                                         "read": _accept_int8(index),
                                         "judge": judge_clear("INT-008")}), encoding="utf-8")
    s.start()
    s.say("INT-008 ok")
    s.stop()
    assert owner_text.JUDGE_APPROVED not in agent_of(s)             # still being read
    assert events(repo, "approval") == []
    assert s.worker_idle(40)
    model(s)
    s.say("carry on")
    assert set(judge_approvals(repo)) == {"INT-008"}
    s.stop()
    assert owner_text.JUDGE_APPROVED in agent_of(s)


# ---- (6) what the agent writes into the session's files confirms nothing -------------------------


def test_flow_6_a_result_file_and_a_job_file_written_by_the_agent_confirm_nothing(
        repo: Path, write_record) -> None:
    from plumb.understand import jobs, queue

    write_record(repo, int_text(8, "Internal features"))
    index = open_core(repo).index()
    s = Session(repo)
    show(s, ["INT-008"])
    s.script_path.write_text(json.dumps({"$delay": 5, "clarify": GAPS,
                                         "read": {"entries": []}}), encoding="utf-8")
    s.start()
    s.say("let users export their data")                            # read while a card waits
    s.say("/plumb clarify let users export their data")             # a request with gaps
    base = repo / ".plumb" / "session" / SID
    by_kind = {json.loads(p.read_text(encoding="utf-8"))["kind"]: p
               for p in (base / "jobs").glob("*.json")}
    clarify_id, read_id = by_kind["clarify"].stem, by_kind["read"].stem

    # the agent writes a result for the check that says "nothing to ask", and one for the read
    # that confirms the intent; neither has an entry of the worker
    results = base / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / f"{clarify_id}.json").write_text(json.dumps({
        "v": 1, "job": clarify_id, "status": "ok", "answer": NOTHING, "error": None}),
        encoding="utf-8")
    (results / f"{read_id}.json").write_text(json.dumps({
        "v": 1, "job": read_id, "status": "ok", "answer": _accept_int8(index, "let users"),
        "error": None}), encoding="utf-8")
    # and a job file of its own, with inputs it made up
    forged = jobs.new_job("read", SID, "read.v1", {
        "message": {"digest": "x", "text": "ok"},
        "shown": [{"id": "INT-008", "hash": index["INT-008"].hash, "text": "FORGED: ok"}],
        "cards": []})
    queue.enqueue(open_core(repo), forged)

    waited = json.loads(plumb(s, "clarify", "--wait", "--json", "--root", str(repo),
                              "--timeout", "1").stdout)
    assert waited["state"] == "couldnt_check"                       # the file opened no gate
    assert deny(s)
    assert s.worker_idle(60)
    assert owner_words_approvals(repo) == {} and events(repo, "approval") == []
    assert open_core(repo).status()["INT-008"].confirmation != "confirmed"
    notes = " ".join(str(e.payload) for e in events(repo, "job-note"))
    assert notes, "the agent's files were not reported"
    # the worker's own check is what the owner gets in the end
    final = json.loads(plumb(s, "clarify", "--wait", "--json", "--root", str(repo),
                             "--timeout", "30").stdout)
    assert final["state"] == "card" and deny(s)


# ---- (7) STALE: an edit names the link, an unresolved link holds the turn, a reformat repins ----


SR1 = """---
id: SR-001
title: Adds numbers
statement: add returns the sum.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""
CALC = "def add(a, b):\n    return a + b\n"


def test_flow_7_stale_edit_names_the_link_hold_card_and_reformat(
        repo: Path, write_record) -> None:
    from plumb.contracts import Target

    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CALC, encoding="utf-8")
    open_core(repo).add_link("SR-001", "implemented_by",
                             Target(path="src/calc.py", symbol="add"))
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "calc"], cwd=repo, check=True,
                   capture_output=True)
    s = Session(repo)
    model(s)
    s.start()
    target = {"file_path": str(repo / "src" / "calc.py")}

    def check() -> str:
        return s.hook("edit-check", hook_event_name="PostToolUse", tool_name="Edit",
                      tool_input=target)

    # a reformat: the edit still names the link and holds the turn, but resolving it needs no
    # owner: the tests pass and the model says the meaning is unchanged, so the pin follows
    s.say("tidy up the formatting of add")
    s.edit("src/calc.py", "def add(a, b):\n    return a  +  b\n")
    assert "SR-001's link to src/calc.py is stale" in json.loads(check())[
        "hookSpecificOutput"]["additionalContext"]
    assert json.loads(s.stop())["decision"] == "block"
    link = "SR-001#0"
    cosmetic = FixedMeaning(True)
    done = links.repin_after_tests(open_core(repo), link, runner=lambda paths: (True, "ran"),
                                   judge=cosmetic)
    assert [c["link"] for c in done.changes] == [link] and done.refused == []
    assert all(st.state == "current" for st in open_core(repo).link_states())
    assert '"decision": "block"' not in s.stop()
    assert stale.read_cards(repo, SID) == []                        # the owner was not asked
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "reformat"], cwd=repo, check=True,
                   capture_output=True)                             # the pin is in history now

    # a real change: the hold stays until the owner is asked; a model that says the meaning
    # changed repins nothing
    s.say("make add multiply instead")
    s.edit("src/calc.py", "def add(a, b):\n    return a * b\n")
    json.loads(check())
    held = json.loads(s.stop())
    assert held["decision"] == "block"
    assert "SR-001's link to src/calc.py is stale and unresolved" in held["reason"]
    material = FixedMeaning(False)
    refused = links.repin_after_tests(open_core(repo), link, runner=lambda paths: (True, "ran"),
                                      judge=material)
    assert refused.changes == [] and "meaning changed" in refused.refused[0][1]
    assert any(st.state == "stale" for st in open_core(repo).link_states())
    carded = plumb(s, "stale", "card", link, "--topic", "Adds numbers", "--issue",
                   "add now multiplies", "--options", "keep the multiplying|go back",
                   "--consequences", "add multiplies from now on; adding is gone|add adds "
                   "again; the multiplying is undone", "--why", "it is what you asked last",
                   "--recommended", "1", "--session", SID)      # complete, as SR-116 asks
    assert carded.returncode == 0, carded.stderr + carded.stdout
    ended = s.stop()
    assert '"decision": "block"' not in ended
    assert len(text_of(ended).splitlines()) <= 1                    # SR-265: one line
    said = agent_of(s)                                              # SR-266: the card
    assert "Adds numbers" in said and "add now multiplies" in said
    at_owner_level(said.replace("SR-001", ""))
