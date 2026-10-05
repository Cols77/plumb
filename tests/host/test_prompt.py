"""H6: the UserPromptSubmit hook (spec 6.2)."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from fakes import FakeBackend, FakeVerify

from plumb import approvals
from plumb.api import open_core
from plumb.hosts.claude_code import prompt

pytestmark = pytest.mark.sr("SR-010")

SR3 = """---
id: SR-003
title: Links pin both ends
feature: FEAT-001
statement: Each link pins the hashes of both ends; a moved end makes the link stale.
examples:
- id: EX-1
  given: a link from SR-003 to src/links.py
  when: src/links.py changes
  then: the link is stale
- id: EX-2
  given: a stale link
  when: repin runs
  then: the link is current again
---
"""
SR4 = """---
id: SR-004
title: Approvals pin exact content
feature: FEAT-001
statement: An approval pins the record hash; an edit leaves the record unconfirmed.
examples:
- id: EX-1
  given: a confirmed record
  when: its statement is edited
  then: the record is an unconfirmed edit
---
"""
SR9 = """---
id: SR-009
title: Status line shows counts
feature: FEAT-002
statement: The status line shows confirmed requirement counts.
---
"""


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    for text in (SR3, SR4, SR9):
        write_record(repo, text)
    return repo


def _run(repo: Path, hook_input, text: str, session: str = "s1", **kwargs) -> str:
    kwargs.setdefault("verify", FakeVerify())
    kwargs.setdefault("backend", FakeBackend())
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=text, session_id=session)
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo, **kwargs) == 0
    return out.getvalue()


def _confirm(repo: Path, *ids: str) -> None:
    approvals.approve(open_core(repo), list(ids))


def test_logs_prompt_digest_and_text_to_session(records: Path, hook_input) -> None:
    text = "please fix the stale links, ok"
    _run(records, hook_input, text)
    lines = (records / ".plumb" / "session" / "prompts.jsonl").read_text("utf-8").splitlines()
    entry = json.loads(lines[-1])
    assert entry["text"] == text and entry["session"] == "s1"
    assert entry["digest"] == "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert entry["digest"] == approvals.prompt_digest(text)
    assert entry["at"].endswith("Z")
    turn = json.loads((records / ".plumb" / "session" / "s1" / "turn.json").read_text("utf-8"))
    assert turn["prompt_digest"] == entry["digest"] and turn["turn_start"] > 0
    assert turn["asked"] == {}


def test_turn_keeps_asked_decisions_of_the_session(records: Path, hook_input) -> None:
    turn = records / ".plumb" / "session" / "s1" / "turn.json"
    _run(records, hook_input, "first")
    data = json.loads(turn.read_text("utf-8"))
    data["asked"] = {"DEC-001": "sha256:abc"}
    turn.write_text(json.dumps(data), encoding="utf-8")
    _run(records, hook_input, "second")
    assert json.loads(turn.read_text("utf-8"))["asked"] == {"DEC-001": "sha256:abc"}


def test_injects_named_records_first(records: Path, hook_input) -> None:
    out = _run(records, hook_input, "the status line counts look wrong; also check SR-004")
    record_lines = [line for line in out.splitlines() if line[:3] in ("SR-", "INT", "DEC")]
    assert record_lines[0].startswith("SR-004 [proposed] Approvals pin exact content")
    assert any(line.startswith("SR-009") for line in record_lines)


def test_injects_examples_and_tests_within_20_lines(records: Path, hook_input,
                                                     write_record) -> None:
    for i in range(10, 16):
        write_record(records, f"---\nid: SR-0{i}\ntitle: Stale link rule {i}\n"
                     "statement: stale links pins hashes\nexamples:\n"
                     + "".join(f"- id: EX-{n}\n  given: stale link {n}\n  when: pins\n"
                               f"  then: stale {n} " + "x" * 120 + "\n" for n in range(1, 5))
                     + "---\n")
    verify = FakeVerify(tests={"SR-003": ("tests/test_links.py::test_pin_drift",
                                          "tests/test_links.py::test_repin")})
    out = _run(records, hook_input, "SR-003 stale links pins hashes", verify=verify)
    lines = out.splitlines()
    assert lines[1].startswith("SR-003")
    assert "  EX-1: given a link from SR-003 to src/links.py, when src/links.py changes, " \
           "then the link is stale" in lines
    assert ("  tests: tests/test_links.py::test_pin_drift, tests/test_links.py::test_repin"
            in lines)
    section = [line for line in lines if not line.startswith("plumb:")]
    assert len(section) + 1 <= 20
    assert all(len(line) <= 102 for line in lines if line.startswith("  EX-"))


def test_intent_change_flag_on_confirmed_record_with_change_words(records: Path,
                                                                   hook_input) -> None:
    _confirm(records, "SR-004")
    backend = FakeBackend()
    out = _run(records, hook_input, "approvals should now stay after an edit, SR-004",
               backend=backend)
    assert ("plumb: this may change SR-004 (confirmed). If it does, read back the change and "
            "ask before editing; if not, proceed.") in out
    assert backend.calls and backend.calls[0][1] == ("SR-004",)
    flags = (records / ".plumb" / "session" / "intent_flags.jsonl").read_text("utf-8")
    assert json.loads(flags.splitlines()[0])["subject"] == "SR-004"


def test_no_flag_on_proposed_record(records: Path, hook_input) -> None:
    backend = FakeBackend()
    out = _run(records, hook_input, "approvals should now stay after an edit, SR-004",
               backend=backend)
    assert "this may change" not in out
    assert backend.calls == []  # only confirmed records are judged


def test_compare_line_when_confirmed_records_injected(records: Path, hook_input) -> None:
    _confirm(records, "SR-003")
    out = _run(records, hook_input, "SR-003 links are fine as they are")
    assert ("plumb: compare this request with the confirmed examples of SR-003; if it "
            "contradicts or extends them, read back the change and ask before editing.") in out
    assert "this may change" not in out


def test_awaiting_confirmation_lists_stated_set_with_digest(records: Path,
                                                             hook_input) -> None:
    core = open_core(records)
    index = core.index()
    stated = {"at": "2026-10-06T03:00:00Z", "session": "s1", "reply_after_prompt": None,
              "records": [{"id": "SR-009", "hash": index["SR-009"].hash},
                          {"id": "SR-003", "hash": index["SR-003"].hash}]}
    _confirm(records, "SR-003")
    (records / ".plumb" / "session").mkdir(parents=True, exist_ok=True)
    (records / ".plumb" / "session" / "stated.json").write_text(json.dumps(stated), "utf-8")
    text = "ok, go on"
    out = _run(records, hook_input, text)
    short = approvals.prompt_digest(text).removeprefix("sha256:")[:12]
    assert (f"plumb: awaiting confirmation: SR-009 | prompt sha256:{short} | if this prompt "
            f"affirms them, run plumb relay SR-009 --prompt {short} --quote \"<owner's exact "
            "words>\"; otherwise leave them proposed.") in out


def test_backend_unavailable_degrades(records: Path, hook_input) -> None:
    _confirm(records, "SR-004")
    out = _run(records, hook_input, "SR-004 should now change", backend=None)
    assert "plumb: intent check unavailable" in out
    assert "plumb: compare this request" in out


def test_verify_unavailable_degrades(records: Path, hook_input) -> None:
    out = _run(records, hook_input, "SR-003 stale links", verify=None)
    assert out.splitlines()[1].startswith("SR-003")
    assert "plumb: verification unavailable" in out


def test_nothing_relevant_prints_nothing(records: Path, hook_input) -> None:
    assert _run(records, hook_input, "zzz qqq") == ""


# --- SHOULD items -----------------------------------------------------------------------


@pytest.mark.sr("SR-024")
def test_prints_queued_escalations(records: Path, hook_input) -> None:
    queue = records / ".plumb" / "session" / "escalations.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text(json.dumps({"at": "2026-10-06T03:00:00Z", "subject": "SR-003",
                                 "instruction": "judge SR-003 with plumb fidelity SR-003"})
                     + "\n", encoding="utf-8")
    out = _run(records, hook_input, "zzz")
    assert "plumb: escalation SR-003: judge SR-003 with plumb fidelity SR-003" in out
    assert "escalation" not in _run(records, hook_input, "zzz")  # printed once


def test_escalation_hint_on_many_features(records: Path, hook_input) -> None:
    out = _run(records, hook_input, "rework SR-003, SR-004 and SR-009 together")
    assert ("plumb: consider escalating to an up-front spec (2 features: FEAT-001, FEAT-002);"
            " the owner decides.") in out
    assert "consider escalating" not in _run(records, hook_input, "SR-003 stale links")
