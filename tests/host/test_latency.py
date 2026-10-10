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

from plumb.api import open_core
from plumb.contracts import Target
from plumb.hosts.claude_code import post_edit, prompt, session_start, stop

pytestmark = pytest.mark.sr("SR-014")

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


def _time_ms(fn) -> float:
    runs = []
    for _ in range(3):
        start = time.perf_counter()
        fn()
        runs.append((time.perf_counter() - start) * 1000)
    return statistics.median(runs)


def test_hooks_within_in_process_budget(busy_repo: Path, hook_input) -> None:
    root = busy_repo
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
    assert "plumb: touched SR-003" in json.loads(run(stop, stop_input, verify=verify,
                                                     unjudged=None))["systemMessage"]
    over = {k: round(v) for k, v in timings.items() if v > BUDGET_MS[k]}
    assert not over, f"over budget (ms): {over}; all: {timings}"
    errors = root / ".plumb" / "session" / "errors.log"
    assert not errors.exists(), errors.read_text("utf-8")


def test_cli_drives_the_hooks(busy_repo: Path, hook_input) -> None:
    """The real entry point, as Claude Code calls it (one subprocess per hook)."""
    root = str(busy_repo)

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
    stop_out = json.loads(call("hook", "stop", payload=hook_input("Stop")))
    assert "SR-002" in (stop_out.get("reason") or stop_out.get("systemMessage"))
    assert call("statusline").startswith("plumb ● awaits you")
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
    assert "awaiting your confirmation: 53 proposed" in brief
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
    message = json.loads(raw)["systemMessage"]
    assert "  statement two on stale links" in message.splitlines()  # SR-002's card
    assert wall < 6.0, f"stop hook took {wall:.1f} s under contention"
