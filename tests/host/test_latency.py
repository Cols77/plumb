"""HS3: each hook stays within its budget in process (spec 10); the CLI routes work."""

from __future__ import annotations

import io
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest
from loadbound import assert_within

from plumb.api import open_core
from plumb.contracts import Target
from plumb.hosts.claude_code import post_edit, prompt, session_start, stop

pytestmark = pytest.mark.sr("SR-310")

BUDGET_MS = {"session-start": 900, "prompt": 600, "stop": 800, "post-edit": 300}


@pytest.fixture
def busy_repo(repo: Path, write_record) -> Path:
    """About plumb's own size: 15 intents, 25 requirements with examples, 13 decisions."""
    (repo / "src").mkdir()
    for i in range(1, 16):
        write_record(repo, f"---\nid: INT-{i:03d}\ntitle: Intent {i}\nquote: owner words {i}\n"
                     "---\n")
    for i in range(1, 26):
        (repo / "src" / f"mod{i}.py").write_text(f"X = {i}\n", "utf-8")
        write_record(repo, f"---\nid: SR-{i:03d}\ntitle: Requirement {i} about links\n"
                     f"feature: FEAT-001\nstatement: statement {i} on stale links\nexamples:\n"
                     f"- id: EX-1\n  given: g{i}\n  when: w{i}\n  then: t{i}\n---\n")
    for i in range(1, 14):
        write_record(repo, f"---\nid: DEC-{i:03d}\ntitle: Decision {i}\nchosen: a\n"
                     f"alternatives: [b]\nmatters: {str(i < 4).lower()}\n---\n")
    core = open_core(repo)
    for i in range(1, 26):
        core.add_link(f"SR-{i:03d}", "derives_from", Target(record=f"INT-{(i % 15) + 1:03d}"))
        core.add_link(f"SR-{i:03d}", "implemented_by", Target(path=f"src/mod{i}.py"))
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "records"], cwd=repo, check=True,
                   capture_output=True)
    return repo


def _scripted_judge(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """DEC-088: since DEC-060 / SR-174 the stale check waits without a judge, so the turn end
    gets a scripted one (``PLUMB_FAKE_DISPATCH``) that says the edit changed the meaning and
    brings it to the owner as a card."""
    script = root.parent / "judge.json"
    script.write_text(json.dumps({
        "repin": {"verdict": "changed", "reason": "the value changed", "confidence": 0.9},
        "diagnose": {"outcome": "owner", "explanation": "the value changed", "topic": "",
                     "options": ["keep the new value", "undo the edit"],
                     "consequences": ["the requirement follows", "the code goes back"],
                     "why": "the owner decides what the value is"}}), "utf-8")
    monkeypatch.setenv("PLUMB_FAKE_DISPATCH", str(script))


def _time_ms(fn) -> float:
    runs = []
    for _ in range(3):
        start = time.perf_counter()
        fn()
        runs.append((time.perf_counter() - start) * 1000)
    return statistics.median(runs)


@pytest.mark.load_bound
def test_hooks_within_in_process_budget(busy_repo: Path, hook_input,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    root = busy_repo
    _scripted_judge(monkeypatch, root)
    from fakes import FakeVerify

    verify = FakeVerify(nodes=("tests/test_x.py::test_x",))

    def run(module, payload: str, **kwargs) -> str:
        out = io.StringIO()
        module.main(stdin=io.StringIO(payload), stdout=out, root=root, **kwargs)
        return out.getvalue()

    timings = {
        "session-start": _time_ms(lambda: run(session_start, hook_input("SessionStart"),
                                              verify=verify)),
        "prompt": _time_ms(lambda: run(prompt, hook_input(
            "UserPromptSubmit", prompt="fix the stale links of SR-003 and SR-004"),
            verify=verify, backend=None)),
    }
    (root / "src" / "mod3.py").write_text("X = 33\n", "utf-8")
    edit = hook_input("PostToolUse", tool_name="Edit",
                      tool_input={"file_path": str(root / "src" / "mod3.py")})
    timings["post-edit"] = _time_ms(lambda: run(post_edit, edit))
    stop_input = hook_input("Stop", stop_hook_active=True)
    timings["stop"] = _time_ms(lambda: run(stop, stop_input, verify=verify, unjudged=None))
    # SR-266: the card the judged stale check filed for the edited requirement is the agent's
    run(stop, stop_input, verify=verify, unjudged=None)
    from fakes import agent_notes

    assert "Requirement 3 about links" in agent_notes(root, "test-session")
    for hook, took in timings.items():
        assert_within(took, BUDGET_MS[hook], f"{hook} hook (ms)")
    errors = root / ".plumb" / "session" / "errors.log"
    assert not errors.exists(), errors.read_text("utf-8")


def test_cli_drives_the_hooks(busy_repo: Path, hook_input,
                              monkeypatch: pytest.MonkeyPatch) -> None:
    """The real entry point, as Claude Code calls it (one subprocess per hook)."""
    root = str(busy_repo)
    _scripted_judge(monkeypatch, busy_repo)

    def call(*args: str, payload: str = "") -> str:
        result = subprocess.run([sys.executable, "-m", "plumb", *args, "--root", root],
                                input=payload, capture_output=True, text=True,
                                encoding="utf-8", check=False, timeout=30)
        assert result.returncode == 0, result.stderr
        return result.stdout

    assert call("hook", "session-start",
                payload=hook_input("SessionStart")).startswith("plumb brief")
    out = call("hook", "prompt", payload=hook_input("UserPromptSubmit",
                                                    prompt="SR-002 needs work"))
    assert "SR-002 [proposed]" in out
    (busy_repo / "src" / "mod2.py").write_text("X = 22\n", "utf-8")
    call("hook", "post-edit", payload=hook_input(
        "PostToolUse", tool_name="Edit", tool_input={"file_path": str(busy_repo / "src" /
                                                                       "mod2.py")}))
    stop_out = call("hook", "stop", payload=hook_input("Stop"))
    from fakes import agent_notes

    assert "SR-002" in stop_out + agent_notes(busy_repo, "test-session")
    assert "awaits you" not in call("statusline")   # records wait on a judge (SR-263 EX-6)
    assert call("hook", "--help").startswith("usage: plumb hook")


class _CpuContention:
    """One busy-loop process per core (simulated load); stops only its own processes."""

    def __enter__(self) -> _CpuContention:
        import os

        self.burners = [subprocess.Popen([sys.executable, "-c", "while True: pass"])
                        for _ in range(max(os.cpu_count() or 2, 2))]
        return self

    def __exit__(self, *exc: object) -> None:
        for proc in self.burners:
            proc.terminate()
        for proc in self.burners:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.mark.load_bound
def test_intent_lines_survive_cpu_contention(busy_repo: Path, hook_input) -> None:
    """Under full CPU contention the hooks may cut evidence detail, never the brief, the
    relevant records, the relay line or the proposed read-back (spec 10, R1). The caches are
    warm, as on every turn after the first (a cold first hook is in docs/followups.md)."""
    root = str(busy_repo)

    def call(*args: str, payload: str = "") -> tuple[str, float]:
        start = time.perf_counter()
        result = subprocess.run([sys.executable, "-m", "plumb", *args, "--root", root],
                                input=payload, capture_output=True, text=True,
                                encoding="utf-8", check=False, timeout=60)
        assert result.returncode == 0, result.stderr
        return result.stdout, time.perf_counter() - start

    call("hook", "session-start", payload=hook_input("SessionStart"))  # an earlier session
    with _CpuContention():
        _contended_turn(busy_repo, hook_input, call)


def _contended_turn(busy_repo: Path, hook_input, call) -> None:
    brief, _ = call("hook", "session-start", payload=hook_input("SessionStart"))
    assert brief.startswith("plumb brief")
    assert "waiting on a judge: 53 records" in brief
    index = open_core(busy_repo).index()
    stated = busy_repo / ".plumb" / "session" / "stated.json"
    stated.write_text(json.dumps({"records": [
        {"id": "SR-002", "hash": index["SR-002"].hash, "shown": True}]}), "utf-8")
    out, _ = call("hook", "prompt", payload=hook_input("UserPromptSubmit",
                                                       prompt="ok, confirm SR-002"))
    assert "SR-002 [proposed]" in out
    assert "plumb relay" not in out     # the agent is never told to confirm on its own reading
    record = busy_repo / ".plumb" / "requirements" / "SR-002.md"
    record.write_text(record.read_text("utf-8").replace("statement 2", "statement two"),
                      "utf-8")
    call("hook", "post-edit", payload=hook_input(  # the Edit tool's PostToolUse
        "PostToolUse", tool_name="Edit", tool_input={"file_path": str(record)}))
    raw, wall = call("hook", "stop", payload=hook_input("Stop", stop_hook_active=True))
    assert "decision" not in raw  # no decision is asked here (INT-037)
    assert_within(wall, 6.0, "stop hook under contention (s)")
