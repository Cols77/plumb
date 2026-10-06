"""P1: every hook output is a deduplicated delta within a token budget (sp5 3, SR-063)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from present_helpers import FEAT1, FEAT2, SR1, SR2, SR3, run_prompt, write_all

from plumb import approvals
from plumb.api import open_core
from plumb.hosts.claude_code.hookio import Deadline, HookContext
from plumb.present import delta

pytestmark = pytest.mark.sr("SR-063")


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    return write_all(repo, write_record, SR1, SR2, SR3, FEAT1, FEAT2)


def _ctx(repo: Path, session: str = "s1") -> HookContext:
    return HookContext(name="prompt", data={}, root=repo, session_id=session,
                       deadline=Deadline(10_000))


def _record_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line[:3] in ("SR-", "INT", "DEC", "FEA")]


def test_ten_prompts_three_records_once_each(records: Path, hook_input) -> None:
    """EX-1: ten prompts about the same three unchanged records inject each line once, and
    the total stays under the budget times the turns that had something new."""
    outputs = [run_prompt(records, hook_input, "SR-001 SR-002 SR-003 numbers and invoices")
               for _ in range(10)]
    lines = [line for out in outputs for line in _record_lines(out)]
    for record_id in ("SR-001", "SR-002", "SR-003"):
        assert sum(line.startswith(record_id) for line in lines) == 1
    budget = open_core(records).config.hooks.prompt_tokens * delta.CHARS_PER_TOKEN
    turns_with_news = sum(bool(out.strip()) for out in outputs)
    assert turns_with_news == 1
    assert sum(len(out) for out in outputs) <= budget * turns_with_news


def test_changed_record_reappears_once(records: Path, hook_input) -> None:
    """EX-3: a record changed after its line was injected comes once more, new state."""
    run_prompt(records, hook_input, "SR-002 divide")
    approvals.approve(open_core(records), ["SR-002"])
    second = run_prompt(records, hook_input, "SR-002 divide")
    third = run_prompt(records, hook_input, "SR-002 divide")
    assert [line for line in _record_lines(second) if line.startswith("SR-002")] == [
        "SR-002 [confirmed] divide returns the quotient"]
    assert not [line for line in _record_lines(third) if line.startswith("SR-002")]


def test_instructions_deduplicated(records: Path, hook_input) -> None:
    """EX-2: an untraced-change instruction already given is not repeated while the path
    stays untraced; nor is the compare line of a confirmed record."""
    approvals.approve(open_core(records), ["SR-001"])
    note = records / ".plumb" / "session" / "s1" / "untraced.json"
    (records / "src" / "app").mkdir(parents=True)
    (records / "src" / "app" / "mul.py").write_text("def mul(a, b):\n    return a * b\n",
                                                   encoding="utf-8")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(json.dumps({"paths": ["src/app/mul.py"]}), encoding="utf-8")
    first = run_prompt(records, hook_input, "SR-001 add numbers")
    assert "src/app/mul.py" in first
    assert "compare this request with the confirmed examples of SR-001" in first
    note.write_text(json.dumps({"paths": ["src/app/mul.py"]}), encoding="utf-8")
    second = run_prompt(records, hook_input, "SR-001 add numbers again")
    assert "src/app/mul.py" not in second
    assert "compare this request" not in second


def test_budget_cut_named_not_marked_seen(repo: Path, write_record) -> None:
    """A line cut by the budget is named with plumb show and is not marked seen, so a later
    emission brings it."""
    lines = [delta.Line(f"SR-00{i} [proposed] " + "x" * 120, subject=f"record:SR-00{i}",
                        state="h|proposed", record=f"SR-00{i}", group="records")
             for i in range(1, 6)]
    ctx = _ctx(repo)
    out = delta.emit(ctx, lines, "prompt", budget_tokens=80,
                     headers={"records": "plumb: relevant records"})
    shown = [line for line in out if line.startswith("SR-")]
    assert 1 <= len(shown) < 5
    cut = [f"SR-00{i}" for i in range(len(shown) + 1, 6)]
    assert out[-1].startswith("plumb: +") and all(i in out[-1] for i in cut)
    assert "plumb show" in out[-1]
    again = delta.emit(ctx, lines, "prompt", budget_tokens=10_000,
                       headers={"records": "plumb: relevant records"})
    assert [line[:6] for line in again if line.startswith("SR-")] == cut


def test_nothing_new_emits_nothing(repo: Path) -> None:
    ctx = _ctx(repo)
    lines = [delta.Line("plumb: hint once")]
    assert delta.emit(ctx, lines, "stop") == ["plumb: hint once"]
    assert delta.emit(ctx, lines, "stop") == []


def test_must_lines_are_never_cut_and_sessions_are_separate(repo: Path) -> None:
    must = delta.Line("plumb: awaiting confirmation " + "y" * 900, must=True)
    out = delta.emit(_ctx(repo), [must, delta.Line("plumb: optional")], "prompt",
                     budget_tokens=10)
    assert out[0] == must.text
    assert delta.emit(_ctx(repo, "s2"), [delta.Line("plumb: hint once")], "stop") == [
        "plumb: hint once"]


def test_session_start_and_stop_route_through_the_emitter(records: Path, hook_input,
                                                          monkeypatch) -> None:
    """Every agent-facing line goes through ``present.delta`` (the one choke point)."""
    import io

    from present_helpers import FakeVerify

    from plumb.hosts.claude_code import session_start

    calls: list[str] = []
    real = delta.Emitter.add

    def spy(self, lines, **kwargs):
        calls.append(self.kind)
        return real(self, lines, **kwargs)

    monkeypatch.setattr(delta.Emitter, "add", spy)
    out = io.StringIO()
    payload = hook_input("SessionStart", session_id="s9", source="startup")
    session_start.main(stdin=io.StringIO(payload), stdout=out, root=records,
                       verify=FakeVerify())
    first = out.getvalue()
    assert "session-start" in calls and first.strip()
    out = io.StringIO()
    session_start.main(stdin=io.StringIO(hook_input("SessionStart", session_id="s9",
                                                    source="resume")),
                       stdout=out, root=records, verify=FakeVerify())
    assert out.getvalue().strip() == ""  # the resumed session already has the brief
    run_prompt(records, hook_input, "SR-001", session="s9")
    assert "prompt" in calls


# --- a one-shot line is never lost to the budget (its source is consumed on read) ----------


def _tight(repo: Path, **budgets: int) -> None:
    text = "hooks:\n" + "".join(f"  {k}: {v}\n" for k, v in budgets.items())
    (repo / ".plumb" / "config.yaml").write_text(text, encoding="utf-8")


def _untraced(repo: Path, session: str = "s1") -> Path:
    (repo / "src" / "app").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "app" / "mul.py").write_text("def mul(a, b):\n    return a * b\n",
                                                 encoding="utf-8")
    return repo / ".plumb" / "session" / session / "untraced.json"


def test_oneshot_lines_are_never_cut(repo: Path) -> None:
    """The emitter keeps a ``oneshot`` line through the budget, like a ``must`` line."""
    lines = [delta.Line("plumb: optional " + "x" * 200),
             delta.Line("plumb: queued once " + "y" * 200, oneshot=True)]
    out = delta.emit(_ctx(repo), lines, "prompt", budget_tokens=10)
    assert out == [line.text for line in lines]


def test_prompt_untraced_instruction_survives_the_budget(records: Path, hook_input) -> None:
    """Entry point 1: the prompt hook's queued untraced-change instruction (untraced.json is
    removed when read) reaches the agent even when records and the compare line fill the
    budget."""
    approvals.approve(open_core(records), ["SR-001"])
    _tight(records, prompt_tokens=10)
    note = _untraced(records)
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(json.dumps({"paths": ["src/app/mul.py"]}), encoding="utf-8")
    out = run_prompt(records, hook_input, "SR-001 SR-002 SR-003 numbers and invoices")
    assert "compare this request" in out  # the budget is already used up
    assert "src/app/mul.py" in out
    assert not note.exists()


def test_prompt_queued_escalations_survive_the_budget(records: Path, hook_input) -> None:
    """Entry point 2: every queued escalation reaches the agent (the queue offset moved
    past them on read), however tight the budget."""
    _tight(records, prompt_tokens=10)
    queue = records / ".plumb" / "session" / "escalations.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text("".join(json.dumps({"subject": f"SR-00{i}",
                                         "instruction": f"judge SR-00{i} with plumb fidelity"})
                             + "\n" for i in (1, 2, 3)), encoding="utf-8")
    out = run_prompt(records, hook_input, "SR-001 SR-002 numbers")
    for i in (1, 2, 3):
        assert f"plumb: escalation SR-00{i}: judge SR-00{i}" in out


def test_blocked_stop_untraced_instruction_survives_the_budget(records: Path,
                                                               hook_input) -> None:
    """Entry point 3: the blocked stop removes untraced.json and tells the agent itself;
    the instruction is in the block whatever ``hooks.stop_tokens`` allows."""
    from present_helpers import FakeVerify, run_stop, touch

    _tight(records, stop_tokens=5)
    run_prompt(records, hook_input, "multiply")
    note = _untraced(records)
    touch(records, "src/app/mul.py")
    out = run_stop(records, hook_input, verify=FakeVerify(nodes=("tests/test_x.py::t",)))
    assert "plumb tests run" in out["reason"]
    assert "src/app/mul.py" in out["reason"]
    assert not note.exists()


# --- a per-turn line reaches the agent once in every turn, whatever its words (SR-063 EX-5) ---


def test_per_turn_line_is_once_per_turn_not_once_per_session(repo: Path) -> None:
    """The choke point: a ``per_turn`` line's key carries the emitter's turn, so the same
    text is dropped within a turn and emitted again in the next one."""
    path = delta.seen_path(repo / ".plumb" / "session", "s1")
    line = delta.Line("plumb: run the covering tests", subject="tests", must=True,
                      per_turn=True)
    first = delta.Emitter(path, "stop", None, turn="t1")
    assert first.add([line, line]) == [line.text]
    first.close()
    assert delta.Emitter(path, "stop", None, turn="t1").add([line]) == []
    assert delta.Emitter(path, "stop", None, turn="t2").add([line]) == [line.text]


def test_stop_blocks_every_turn_with_unrun_covering_tests(records: Path, hook_input) -> None:
    """Entry point 1, the stop hook: the owner types "continue" twice; each turn edits code
    whose covering tests have no fresh evidence, and each turn's stop blocks once."""
    from present_helpers import FakeVerify, run_stop, touch

    verify = FakeVerify(nodes=("tests/test_calc.py::test_add",))
    reasons = []
    for _ in range(2):
        run_prompt(records, hook_input, "continue")
        touch(records, "src/app/calc.py")
        out = run_stop(records, hook_input, verify=verify)
        reasons.append(out.get("reason") if out.get("decision") == "block" else None)
    assert all(r and "plumb tests run --paths src/app/calc.py" in r for r in reasons), reasons


def test_relay_line_reaches_every_affirming_prompt(records: Path, hook_input) -> None:
    """Entry point 2, the prompt hook: SR-001 is stated as shown and the owner types "ok"
    twice (the first relay did not land); both prompts carry the relay instruction."""
    stated = records / ".plumb" / "session" / "stated.json"
    stated.parent.mkdir(parents=True, exist_ok=True)
    stated.write_text(json.dumps({"records": [{"id": "SR-001", "shown": True}]}),
                      encoding="utf-8")
    outputs = [run_prompt(records, hook_input, "ok") for _ in range(2)]
    for out in outputs:
        assert "plumb: awaiting confirmation: SR-001" in out
        assert "run plumb relay SR-001 --prompt" in out
