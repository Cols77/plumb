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

pytestmark = pytest.mark.sr("SR-225")


@pytest.fixture(autouse=True)
def _without_the_understanding_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests are about the records the hook injects. The understanding layer closes its
    gate on every owner message and says so (tests/understand covers that line)."""
    from plumb.hosts.claude_code import prompt

    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])

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


def test_new_turn_clears_touched_list(records: Path, hook_input) -> None:
    touched = records / ".plumb" / "session" / "s1" / "touched.txt"
    touched.parent.mkdir(parents=True, exist_ok=True)
    touched.write_text("src/old.py\n", encoding="utf-8")
    _run(records, hook_input, "next request")
    assert not touched.exists()


def test_injects_named_records_first(records: Path, hook_input) -> None:
    out = _run(records, hook_input, "the status line counts look wrong; also check SR-004")
    record_lines = [line for line in out.splitlines() if line[:3] in ("SR-", "INT", "DEC")]
    assert record_lines[0].startswith("SR-004 [proposed] Approvals pin exact content")
    assert any(line.startswith("SR-009") for line in record_lines)


@pytest.mark.sr("SR-277")
def test_injects_one_line_per_record_within_the_budget(records: Path, hook_input,
                                                       write_record) -> None:
    """R9: one line per relevant record (ID, state, title); examples and tests stay behind
    plumb show; the token budget bounds the delta."""
    for i in range(10, 40):
        write_record(records, f"---\nid: SR-0{i}\ntitle: Stale link rule {i}\n"
                     "statement: stale links pins hashes\nexamples:\n"
                     "- id: EX-1\n  given: stale link\n  when: pins\n  then: stale\n---\n")
    out = _run(records, hook_input, "SR-003 stale links pins hashes")
    lines = out.splitlines()
    assert lines[0].startswith("plumb: relevant records, new or changed this session")
    assert lines[1] == "SR-003 [proposed] Links pin both ends"
    assert not any("EX-1" in line or "tests:" in line for line in lines)
    records_shown = [line for line in lines if line.startswith("SR-")]
    assert 1 < len(records_shown) <= 5
    assert all(" [proposed] " in line for line in records_shown)
    assert len(out) <= 200 * 4 + 200  # hooks.prompt_tokens, plus the escalation hint


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


def test_backend_unavailable_degrades(records: Path, hook_input) -> None:
    _confirm(records, "SR-004")
    out = _run(records, hook_input, "SR-004 should now change", backend=None)
    assert "plumb: intent check unavailable" in out
    assert "plumb: compare this request" in out


@pytest.mark.sr("SR-245")
def test_unreachable_judge_is_one_line_once_per_session_and_never_blocks(
        records: Path, hook_input) -> None:
    """SR-021 EX-1: a jev judge with no key. The hook says so in one line, once per session,
    judges nothing by rules, and still lets the prompt through (exit 0)."""
    _confirm(records, "SR-004")
    (records / ".plumb" / "config.yaml").write_text("judgment:\n  backend: jev\n",
                                                   encoding="utf-8")
    text = "approvals should now stay after an edit, SR-004"
    first = _run(records, hook_input, text, backend=prompt.LAZY)
    unavailable = [ln for ln in first.splitlines() if "judging unavailable" in ln]
    assert len(unavailable) == 1
    assert "JEV" in unavailable[0] and "TYPESAFE_API_KEY" in unavailable[0]
    assert "this may change" not in first  # no rule-based flag in its place
    assert "plumb: compare this request" in first  # the prompt still gets its records
    second = _run(records, hook_input, text, backend=prompt.LAZY)
    assert "judging unavailable" not in second  # once per session


@pytest.mark.sr("SR-243")
def test_jev_without_its_key_says_so_once_and_judges_nothing_by_rules(
        records: Path, hook_input) -> None:
    """SR-039 EX-1: judgment.backend jev and the key variable unset (conftest clears it).
    Two prompts in one session: the first names JEV and the variable in exactly one line,
    the second says nothing, and no rule-based judgment is made in either."""
    _confirm(records, "SR-004")
    (records / ".plumb" / "config.yaml").write_text("judgment:\n  backend: jev\n",
                                                   encoding="utf-8")
    text = "approvals should now stay after an edit, SR-004"
    first = _run(records, hook_input, text, backend=prompt.LAZY)
    second = _run(records, hook_input, text, backend=prompt.LAZY)
    [line] = [ln for ln in first.splitlines() if "judging unavailable" in ln]
    assert "JEV" in line and "TYPESAFE_API_KEY" in line
    assert "judging unavailable" not in second
    assert "this may change" not in first + second
    assert not (records / ".plumb" / "session" / "intent_flags.jsonl").exists()


@pytest.mark.sr("SR-245")
def test_no_judge_configured_names_the_setting(records: Path, hook_input) -> None:
    _confirm(records, "SR-004")
    out = _run(records, hook_input, "SR-004 should now change", backend=prompt.LAZY)
    [line] = [ln for ln in out.splitlines() if "judging unavailable" in ln]
    assert "judgment.backend" in line


def test_needs_no_verification(records: Path, hook_input) -> None:
    """Covering tests are pulled on demand (plumb show), so the hook never asks VERIFY."""
    out = _run(records, hook_input, "SR-003 stale links", verify=None)
    assert out.splitlines()[1].startswith("SR-003")
    assert "verification unavailable" not in out


def test_nothing_relevant_prints_nothing(records: Path, hook_input) -> None:
    assert _run(records, hook_input, "zzz qqq") == ""


# --- SHOULD items -----------------------------------------------------------------------


@pytest.mark.sr("SR-242")
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


# --- the intent lines survive a budget cut (spec 10) ---------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def __getattr__(self, name: str):
        import time

        return getattr(time, name)


class _SlowBackend(FakeBackend):
    """An intent check that finishes after the prompt hook's soft budget has passed."""

    clock: _Clock | None = None

    def intent_change(self, prompt_text, records):
        assert self.clock is not None
        self.clock.now += 5.0
        return super().intent_change(prompt_text, records)


def test_intent_lines_survive_a_budget_cut(records: Path, hook_input, monkeypatch) -> None:
    """Records, the intent-change flag, the compare line and the relay line are printed even
    when the intent check is slow; nothing asks for the covering tests."""
    from plumb.hosts.claude_code import hookio

    clock = _Clock()
    monkeypatch.setattr(hookio, "time", clock)
    _confirm(records, "SR-003")
    index = open_core(records).index()
    (records / ".plumb" / "session").mkdir(parents=True, exist_ok=True)
    (records / ".plumb" / "session" / "stated.json").write_text(json.dumps(
        {"records": [{"id": "SR-009", "hash": index["SR-009"].hash, "shown": True}]}), "utf-8")
    backend = _SlowBackend()
    backend.clock = clock
    verify = FakeVerify(tests={"SR-003": ("tests/test_links.py::test_pin",)})
    calls: list[tuple] = []
    real_tests_for = verify.tests_for
    monkeypatch.setattr(verify, "tests_for", lambda refs: calls.append(tuple(refs))
                        or real_tests_for(refs))
    out = _run(records, hook_input, "SR-003 should now stop pinning both ends",
               backend=backend, verify=verify)
    lines = out.splitlines()
    assert lines[0].startswith("plumb: relevant records, new or changed this session")
    assert lines[1].startswith("SR-003 [confirmed]")
    assert "plumb: this may change SR-003 (confirmed)." in out
    assert "plumb: compare this request with the confirmed examples of SR-003" in out
    assert "plumb relay" not in out and "awaiting confirmation" not in out
    assert not any("covering tests" in line for line in lines)
    assert calls == []


# -- untraced changes queued by the stop hook (spec 6.2, 6.4) ----------------------------


def _queue_untraced(repo: Path, paths: list[str], session: str = "s1") -> Path:
    note = repo / ".plumb" / "session" / session / "untraced.json"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(json.dumps({"paths": paths}), "utf-8")
    return note


@pytest.mark.sr("SR-200")
def test_next_prompt_tells_the_agent_to_trace_the_untraced_change(records: Path,
                                                                  hook_input) -> None:
    (records / "src").mkdir()
    (records / "src" / "mul.py").write_text("x = 1\n", "utf-8")
    note = _queue_untraced(records, ["src/mul.py"])
    out = _run(records, hook_input, "thanks, now add division")
    assert ("plumb: untraced change: src/mul.py changed with no requirement owning it. "
            "Read the change back to the owner") in out
    assert "record it as a proposed SR" in out
    assert not note.exists()  # delivered once; the merge boundary still lists it
    assert "untraced change" not in _run(records, hook_input, "and modulo")


@pytest.mark.sr("SR-200")
def test_queued_path_linked_since_is_not_repeated(records: Path, hook_input) -> None:
    from plumb.contracts import Target

    (records / "src").mkdir()
    (records / "src" / "mul.py").write_text("x = 1\n", "utf-8")
    open_core(records).add_link("SR-009", "implemented_by", Target(path="src/mul.py"))
    _queue_untraced(records, ["src/mul.py"])
    assert "untraced change" not in _run(records, hook_input, "thanks")


# -- R9 context economy: a deduplicated delta per session (SR-032) ----------------------------


@pytest.mark.sr("SR-277")
def test_second_prompt_naming_an_unchanged_record_injects_nothing(records: Path,
                                                                   hook_input) -> None:
    first = _run(records, hook_input, "SR-003 stale links")
    assert "SR-003 [proposed] Links pin both ends" in first
    assert _run(records, hook_input, "again SR-003 stale links") == ""
    # another session has not seen it
    assert "SR-003 [proposed]" in _run(records, hook_input, "SR-003 stale links", session="s2")


@pytest.mark.sr("SR-277")
def test_changed_record_is_injected_again_as_one_line(records: Path, hook_input) -> None:
    _run(records, hook_input, "SR-003 and SR-004")
    path = records / ".plumb" / "requirements" / "SR-003.md"
    path.write_text(path.read_text("utf-8").replace("a moved end", "any moved end"), "utf-8")
    lines = _run(records, hook_input, "SR-003 and SR-004").splitlines()
    assert [line for line in lines if line.startswith("SR-")] == [
        "SR-003 [proposed] Links pin both ends"]


@pytest.mark.sr("SR-277")
def test_confirmation_change_is_injected_again(records: Path, hook_input) -> None:
    _run(records, hook_input, "SR-004 approvals")
    _confirm(records, "SR-004")
    out = _run(records, hook_input, "SR-004 approvals")
    assert "SR-004 [confirmed] Approvals pin exact content" in out
    assert "plumb: compare this request with the confirmed examples of SR-004" in out
    # the compare line comes with the record, not on every prompt
    assert "compare this request" not in _run(records, hook_input, "SR-004 approvals")


@pytest.mark.sr("SR-277")
def test_records_cut_by_the_budget_come_on_a_later_prompt(records: Path, hook_input,
                                                          write_record) -> None:
    (records / ".plumb" / "config.yaml").write_text("hooks:\n  prompt_tokens: 10\n", "utf-8")
    first = _run(records, hook_input, "SR-003 SR-004")
    assert "SR-003 [proposed]" in first and "SR-004" not in first.splitlines()[1]
    assert "more relevant: plumb show SR-004" in first
    second = _run(records, hook_input, "SR-003 SR-004")
    assert "SR-004 [proposed]" in second and "SR-003 [proposed]" not in second


@pytest.mark.sr("SR-277")
def test_session_clear_resets_what_the_agent_has_seen(records: Path, hook_input) -> None:
    from plumb.hosts.claude_code import session_start

    _run(records, hook_input, "SR-003 stale links")
    payload = hook_input("SessionStart", session_id="s1", source="clear")
    assert session_start.main(stdin=io.StringIO(payload), stdout=io.StringIO(), root=records,
                              verify=FakeVerify()) == 0
    assert "SR-003 [proposed]" in _run(records, hook_input, "SR-003 stale links")


# -- trigger 1 is about each request, not each record (decision 5) -------------------------

CHANGE_1 = "approvals should now stay after an edit, SR-004"
CHANGE_2 = "approvals should now also expire after a week"


def _flag(record_id: str) -> str:
    return f"plumb: this may change {record_id} (confirmed)."


def test_each_request_that_may_change_a_confirmed_record_is_flagged(records: Path,
                                                                    hook_input) -> None:
    """Decision 5: a request that contradicts or extends a confirmed requirement asks first.
    A second, different changing request in the same session gets its own instruction; only
    the record line is deduplicated (R9)."""
    _confirm(records, "SR-004")
    first = _run(records, hook_input, CHANGE_1)
    assert _flag("SR-004") in first and "SR-004 [confirmed]" in first
    second = _run(records, hook_input, CHANGE_2 + " (SR-004)")
    assert _flag("SR-004") in second
    assert "SR-004 [confirmed]" not in second  # the record line stays deduplicated


def test_neutral_turn_api_flags_each_changing_request(records: Path) -> None:
    from plumb.contracts import TurnEvent
    from plumb.hosts.neutral import handle_event

    _confirm(records, "SR-004")
    outputs = []
    for text in (CHANGE_1, CHANGE_2 + " (SR-004)"):
        out = handle_event(TurnEvent(kind="prompt", root=records, session_id="s1",
                                     host="codex", text=text),
                           verify=FakeVerify(), backend=FakeBackend())
        outputs.append("\n".join(out.agent_context))
    assert all(_flag("SR-004") in out for out in outputs)


def test_turn_start_flags_each_changing_request(records: Path, monkeypatch,
                                                capsys) -> None:
    """The CLI-only fallback (``plumb turn start``) is the same prompt event."""
    from plumb.cli import main

    monkeypatch.setattr(prompt, "judgment_backend", lambda core, given=None: FakeBackend())
    _confirm(records, "SR-004")
    capsys.readouterr()
    outputs = []
    for text in (CHANGE_1, CHANGE_2 + " (SR-004)"):
        monkeypatch.setattr("sys.stdin", io.StringIO(text))
        assert main(["turn", "start", "--session", "s1", "--root", str(records)]) == 0
        outputs.append(capsys.readouterr().out)
    assert all(_flag("SR-004") in out for out in outputs)


def _logged(repo: Path) -> list[dict]:
    path = repo / ".plumb" / "session" / "prompts.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


@pytest.mark.sr("SR-209")
@pytest.mark.parametrize("note", [
    "<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>",
    "<system-reminder>\nthe task tools have not been used\n</system-reminder>",
    "[SYSTEM NOTIFICATION - NOT USER INPUT]\nbackground task finished",
])
def test_harness_notification_is_logged_as_such_and_queues_no_job(
        records: Path, hook_input, monkeypatch: pytest.MonkeyPatch, note: str) -> None:
    seen = []
    monkeypatch.setattr(prompt, "understand_lines",
                        lambda ctx, core, digest, text: seen.append(text) or [])
    out = _run(records, hook_input, note)
    assert [e["origin"] for e in _logged(records)] == ["notification"]
    assert seen == [] and out.strip() == ""
    assert not (records / ".plumb" / "session" / "s1" / "turn.json").exists()


@pytest.mark.sr("SR-209")
@pytest.mark.parametrize("note", [
    "<task-notification>\n<status>done</status>\n</task-notification>",
    "<system-reminder>\nnoise\n</system-reminder>",
    "[SYSTEM NOTIFICATION - NOT USER INPUT]\nbackground task finished",
])
def test_owner_text_with_appended_notification_logs_only_the_owner_text(
        records: Path, hook_input, monkeypatch: pytest.MonkeyPatch, note: str) -> None:
    seen = []
    monkeypatch.setattr(prompt, "understand_lines",
                        lambda ctx, core, digest, text: seen.append(text) or [])
    _run(records, hook_input, "please fix the stale links\n\n" + note)
    entries = _logged(records)
    assert [e["text"] for e in entries] == ["please fix the stale links"]
    assert entries[0]["digest"] == approvals.prompt_digest("please fix the stale links")
    assert seen == ["please fix the stale links"]


@pytest.mark.sr("SR-266")
def test_the_next_prompt_hands_the_agent_the_stop_hooks_queued_notes(
        records: Path, hook_input) -> None:
    notes = records / ".plumb" / "session" / "s1" / "agent_notes.json"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text(json.dumps(["plumb: SR-003 is also being changed on branch feat-x"]), "utf-8")
    assert "also being changed on branch feat-x" in _run(records, hook_input, "hello")
    assert not notes.exists()
    assert "feat-x" not in _run(records, hook_input, "hello again")
