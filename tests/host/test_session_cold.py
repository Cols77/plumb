"""SR-014: session start inside its budget on plumb's own records, cold and warm, and the
work it leaves out of the hook when the state is cold."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-275")

REPO = Path(__file__).resolve().parents[2]
BUDGET_MS = 1400.0
WARM_TARGET_MS = 900.0
STEPS = ("imports", "core_open", "index", "brief", "tests_summary", "snapshot", "tree_scan",
         "awareness")

_HARNESS = """
import io, json, sys, time
start = time.monotonic()
from plumb.hosts.claude_code import session_start
out = io.StringIO()
session_start.main(stdin=io.StringIO(sys.argv[2]), stdout=out, root=sys.argv[1],
                   watchdog=False, start=start)
print(json.dumps({"ms": (time.monotonic() - start) * 1000, "out": out.getvalue()}))
"""
PAYLOAD = {"session_id": "cold", "transcript_path": "", "hook_event_name": "SessionStart"}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True,
                          encoding="utf-8").stdout


@pytest.fixture(scope="module")
def own_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A clone of this repository's committed state with the test map built once."""
    root = tmp_path_factory.mktemp("cold") / "plumb"
    try:
        _git(REPO, "rev-parse", "--git-dir")
        _git(root.parent, "clone", "-q", "--local", "-c", "core.autocrlf=false", str(REPO),
             str(root))
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    if not (root / ".plumb" / "requirements").is_dir():
        pytest.skip("no plumb records in this checkout")
    from plumb.verify.testmap import build_map

    build_map(open_core(root))
    return root


def _call(root: Path, env: dict[str, str] | None = None) -> tuple[str, float]:
    import os

    payload = json.dumps({**PAYLOAD, "cwd": str(root)})
    result = subprocess.run([sys.executable, "-c", _HARNESS, str(root), payload],
                            capture_output=True, text=True, encoding="utf-8", check=False,
                            timeout=60, env={**os.environ, **(env or {})})
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout)
    return found["out"], found["ms"]


def _wipe_cache(root: Path) -> None:
    shutil.rmtree(root / ".plumb" / "cache", ignore_errors=True)


_COLD: dict[str, tuple[float, str]] = {}


def _cold_best(own_copy: Path) -> tuple[float, str]:
    """The best of four cold runs (``.plumb/cache`` wiped before each) and its output."""
    key = str(own_copy)
    if key not in _COLD:
        runs = []
        for _ in range(4):
            _wipe_cache(own_copy)
            out, ms = _call(own_copy)
            runs.append((ms, out))
        _COLD[key] = min(runs)
    return _COLD[key]


def test_cold_start_over_budget_today(own_copy: Path) -> None:
    """The plan's target: the best of four cold runs at most 0.9 of the budget."""
    best, _ = _cold_best(own_copy)
    assert best <= BUDGET_MS * 0.9, f"cold session start {best:.0f} ms against {BUDGET_MS:.0f}"


def test_cold_best_of_four_inside_90_percent_of_budget(own_copy: Path) -> None:
    best, _ = _cold_best(own_copy)
    assert best <= BUDGET_MS * 0.9, f"cold session start {best:.0f} ms against {BUDGET_MS:.0f}"


def test_cold_has_no_check_skipped_line(own_copy: Path) -> None:
    _, out = _cold_best(own_copy)
    assert "check skipped" not in out, out
    assert out.splitlines()[0].startswith("plumb brief")


def test_warm_start_inside_target(own_copy: Path) -> None:
    """Best of four warm runs at most 900 ms, on plumb's own records."""
    _call(own_copy)  # fills the caches
    best = min(_call(own_copy)[1] for _ in range(4))
    assert best <= WARM_TARGET_MS, f"warm session start {best:.0f} ms against {WARM_TARGET_MS:.0f}"


def test_timing_file_names_every_step(own_copy: Path) -> None:
    _call(own_copy, {"PLUMB_HOOK_TIMING": "1"})
    data = json.loads((own_copy / ".plumb" / "session" / "cold" / "timing.json")
                      .read_text("utf-8"))
    assert set(STEPS) <= set(data["steps"])
    assert all(isinstance(v, (int, float)) and v >= 0 for v in data["steps"].values())


def test_timing_off_writes_nothing(repo: Path, hook_input,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    from fakes import FakeVerify

    from plumb.hosts.claude_code import session_start

    monkeypatch.delenv("PLUMB_HOOK_TIMING", raising=False)
    session_start.main(stdin=io.StringIO(hook_input("SessionStart")), stdout=io.StringIO(),
                       root=repo, verify=FakeVerify())
    assert not list((repo / ".plumb" / "session").glob("*/timing.json"))


# -- HC2: what a session start imports ---------------------------------------------------

_MODULES = """
import io, json, sys
from plumb.hosts.claude_code import session_start
out = io.StringIO()
session_start.main(stdin=io.StringIO(sys.argv[2]), stdout=out, root=sys.argv[1], watchdog=False)
print(json.dumps(sorted(sys.modules)))
"""
# plumb.judgment.tiers stays: the status of a record rechecks auto-approvals with it
FORBIDDEN = ("plumb.judgment.jev", "plumb.judgment.model", "plumb.judgment.common",
             "plumb.judgment.textjudge", "plumb.judgment.fidelity", "plumb.capture.calibrate",
             "plumb.verify.runner", "plumb.verify.cov_plugin", "urllib.request", "yaml")


def test_hook_import_set_has_no_judgment_or_verify_runner(own_copy: Path) -> None:
    payload = json.dumps({**PAYLOAD, "cwd": str(own_copy)})
    for _ in range(2):  # the second run is warm: nothing builds a cache by importing
        result = subprocess.run([sys.executable, "-c", _MODULES, str(own_copy), payload],
                                capture_output=True, text=True, encoding="utf-8", check=False,
                                timeout=60)
        assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout)
    found = [m for m in loaded if any(m == bad or m.startswith(bad + ".") for bad in FORBIDDEN)]
    assert not found, f"session start imports {found}"


# -- HC3: cold-state work leaves the hook -------------------------------------------------

def _start(repo: Path, hook_input, **kwargs) -> list[str]:
    from plumb.hosts.claude_code import session_start

    out = io.StringIO()
    session_start.main(stdin=io.StringIO(hook_input("SessionStart", source="startup")),
                       stdout=out, root=repo, **kwargs)
    return out.getvalue().splitlines()


@pytest.fixture
def roomy(monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.hosts.claude_code import session_start

    monkeypatch.setattr(session_start, "hook_budget", lambda name: (lambda root: 60000.0))


def test_cold_start_spawns_map_build_does_not_wait(repo: Path, hook_input, write_record,
                                                   roomy, monkeypatch) -> None:
    import plumb.verify.api as verify_api

    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    (repo / "tests").mkdir()
    for n in range(verify_api.HOOK_PARSE_MAX + 5):  # more files than a hook may parse
        (repo / "tests" / f"test_{n}.py").write_text(f"def test_{n}():\n    pass\n", "utf-8")
    started: list[object] = []
    monkeypatch.setattr(verify_api, "spawn_map_build", lambda root: started.append(root))
    lines = _start(repo, hook_input)
    assert len(started) == 1
    assert "tests: not checked (checking in the background)" in lines
    assert not any("no mapped tests yet" in line for line in lines)
    # the line is not cached as an answer: once the map exists the next start reports it
    assert not list((repo / ".plumb" / "cache").glob("**/brief_tests*"))


def test_no_network_call_cold(repo: Path, hook_input, write_record, roomy,
                              monkeypatch) -> None:
    """A network judgment backend and no cached triage: the brief makes no judgment call."""
    import socket

    from fakes import FakeVerify

    import plumb.judgment as judgment

    (repo / ".plumb" / "config.yaml").write_text(
        "judgment:\n  backend: jev\n  jev:\n    provider: openrouter\n", "utf-8")
    write_record(repo, "---\nid: INT-001\ntitle: One\nquote: q\n---\n")
    calls: list[str] = []
    monkeypatch.setattr(judgment, "get_backend", lambda *a, **k: calls.append("backend"))
    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: calls.append("connect"))
    lines = _start(repo, hook_input, verify=FakeVerify())
    assert calls == []
    assert lines[0].startswith("plumb brief")
    assert not any("rated faithful" in line for line in lines)


def test_git_called_once(repo: Path, hook_input, roomy, monkeypatch) -> None:
    """One git status pass for the whole start, however many steps want the tree."""
    from fakes import FakeVerify

    real = subprocess.run
    seen: list[list[str]] = []

    def spy(args, *a, **k):
        if isinstance(args, list) and args[:1] == ["git"]:
            seen.append(args)
        return real(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", spy)
    _start(repo, hook_input, verify=FakeVerify())
    assert len([a for a in seen if a[1] == "status"]) == 1, seen


def test_brief_kept_when_cut(repo: Path, hook_input, write_record, monkeypatch) -> None:
    """The cut falls on the tests line: the records brief is printed whole."""
    from fakes import FakeVerify

    from plumb.hosts.claude_code import session_start

    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    monkeypatch.setattr(session_start, "hook_budget", lambda name: (lambda root: 0.001))
    lines = _start(repo, hook_input, verify=FakeVerify())
    assert lines[0].startswith("plumb brief")
    assert "waiting on a judge: 1 record" in lines
    assert "tests: not checked (budget)" in lines


def test_cold_branch_scan_is_bounded_and_continues_next_start(repo: Path, monkeypatch) -> None:
    import time

    from plumb.api import open_core
    from plumb.awareness import scan

    for n in range(8):
        _git(repo, "branch", f"topic-{n}")
    diffs: list[str] = []

    def slow(root, default, tip):
        diffs.append(tip)
        time.sleep(0.1)
        return ["README.md"]

    monkeypatch.setattr(scan, "_diff", slow)
    core = open_core(repo)
    first = scan.refresh_branches(core)
    assert 1 <= len(diffs) <= 3 and len(first["branches"]) == len(diffs)  # cut, not all 8
    scan.refresh_branches(core)
    assert len(diffs) > 3  # the next start goes on from the cache
