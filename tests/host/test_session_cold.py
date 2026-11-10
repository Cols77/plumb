"""SR-014: session start inside its budget on iaso's own records, cold and warm, and the
work it leaves out of the hook when the state is cold."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from loadbound import assert_within

from iaso.api import open_core

pytestmark = pytest.mark.sr("SR-310")

REPO = Path(__file__).resolve().parents[2]
BUDGET_MS = 1400.0
WARM_TARGET_MS = 900.0
STEPS = ("imports", "core_open", "index", "brief", "tests_summary", "snapshot", "tree_scan",
         "awareness")

_HARNESS = """
import io, json, sys, time
start = time.monotonic()
from iaso.hosts.claude_code import session_start
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
    root = tmp_path_factory.mktemp("cold") / "iaso"
    try:
        _git(REPO, "rev-parse", "--git-dir")
        _git(root.parent, "clone", "-q", "--local", "-c", "core.autocrlf=false", str(REPO),
             str(root))
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    if not (root / ".iaso" / "requirements").is_dir():
        pytest.skip("no iaso records in this checkout")
    from iaso.verify.testmap import build_map

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
    shutil.rmtree(root / ".iaso" / "cache", ignore_errors=True)


_COLD: dict[str, tuple[float, str]] = {}


def _cold_best(own_copy: Path) -> tuple[float, str]:
    """The best of four cold runs (``.iaso/cache`` wiped before each) and its output."""
    key = str(own_copy)
    if key not in _COLD:
        runs = []
        for _ in range(4):
            _wipe_cache(own_copy)
            out, ms = _call(own_copy)
            runs.append((ms, out))
        _COLD[key] = min(runs)
    return _COLD[key]


@pytest.mark.load_bound
def test_cold_start_over_budget_today(own_copy: Path) -> None:
    """The plan's target: the best of four cold runs at most 0.9 of the budget."""
    best, _ = _cold_best(own_copy)
    assert_within(best, BUDGET_MS * 0.9, "cold session start (ms)")


@pytest.mark.load_bound
def test_cold_best_of_four_inside_90_percent_of_budget(own_copy: Path) -> None:
    best, _ = _cold_best(own_copy)
    assert_within(best, BUDGET_MS * 0.9, "cold session start (ms)")


def test_cold_has_no_check_skipped_line(own_copy: Path) -> None:
    _, out = _cold_best(own_copy)
    assert "check skipped" not in out, out


@pytest.mark.load_bound
def test_warm_start_inside_target(own_copy: Path) -> None:
    """Best of four warm runs at most 900 ms, on iaso's own records."""
    _call(own_copy)  # fills the caches
    best = min(_call(own_copy)[1] for _ in range(4))
    assert_within(best, WARM_TARGET_MS, "warm session start (ms)")


def test_timing_file_names_every_step(own_copy: Path) -> None:
    _call(own_copy, {"IASO_HOOK_TIMING": "1"})
    data = json.loads((own_copy / ".iaso" / "session" / "cold" / "timing.json")
                      .read_text("utf-8"))
    assert set(STEPS) <= set(data["steps"])
    assert all(isinstance(v, (int, float)) and v >= 0 for v in data["steps"].values())


def test_timing_off_writes_nothing(repo: Path, hook_input,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    from fakes import FakeVerify

    from iaso.hosts.claude_code import session_start

    monkeypatch.delenv("IASO_HOOK_TIMING", raising=False)
    session_start.main(stdin=io.StringIO(hook_input("SessionStart")), stdout=io.StringIO(),
                       root=repo, verify=FakeVerify())
    assert not list((repo / ".iaso" / "session").glob("*/timing.json"))


# -- HC2: what a session start imports ---------------------------------------------------

_MODULES = """
import io, json, sys
from iaso.hosts.claude_code import session_start
out = io.StringIO()
session_start.main(stdin=io.StringIO(sys.argv[2]), stdout=out, root=sys.argv[1], watchdog=False)
print(json.dumps(sorted(sys.modules)))
"""
# iaso.judgment.tiers stays: the status of a record rechecks auto-approvals with it
FORBIDDEN = ("iaso.judgment.jev", "iaso.judgment.model", "iaso.judgment.common",
             "iaso.judgment.textjudge", "iaso.judgment.fidelity", "iaso.capture.calibrate",
             "iaso.verify.runner", "iaso.verify.cov_plugin", "urllib.request", "yaml")


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
    from iaso.hosts.claude_code import session_start

    out = io.StringIO()
    session_start.main(stdin=io.StringIO(hook_input("SessionStart", source="startup")),
                       stdout=out, root=repo, **kwargs)
    return out.getvalue().splitlines()


@pytest.fixture
def roomy(monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso.hosts.claude_code import session_start

    monkeypatch.setattr(session_start, "hook_budget", lambda name: (lambda root: 60000.0))


def test_cold_start_spawns_map_build_does_not_wait(repo: Path, hook_input, write_record,
                                                   roomy, monkeypatch) -> None:
    import iaso.verify.api as verify_api

    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    (repo / "tests").mkdir()
    for n in range(verify_api.HOOK_PARSE_MAX + 5):  # more files than a hook may parse
        (repo / "tests" / f"test_{n}.py").write_text(f"def test_{n}():\n    pass\n", "utf-8")
    started: list[object] = []
    monkeypatch.setattr(verify_api, "spawn_map_build", lambda root: started.append(root))
    lines = _start(repo, hook_input)
    assert len(started) == 1
    assert not any("tests" in line for line in lines)   # SR-374 EX-9: only what blocks
    # the line is not cached as an answer: once the map exists the next start reports it
    assert not list((repo / ".iaso" / "cache").glob("**/brief_tests*"))


def test_no_network_call_cold(repo: Path, hook_input, write_record, roomy,
                              monkeypatch) -> None:
    """A network judgment backend and no cached triage: the brief makes no judgment call."""
    import socket

    from fakes import FakeVerify

    import iaso.judgment as judgment

    (repo / ".iaso" / "config.yaml").write_text(
        "judgment:\n  backend: jev\n  jev:\n    provider: openrouter\n", "utf-8")
    write_record(repo, "---\nid: INT-001\ntitle: One\nquote: q\n---\n")
    calls: list[str] = []
    monkeypatch.setattr(judgment, "get_backend", lambda *a, **k: calls.append("backend"))
    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: calls.append("connect"))
    lines = _start(repo, hook_input, verify=FakeVerify())
    assert calls == []
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

    from iaso.hosts.claude_code import session_start

    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    monkeypatch.setattr(session_start, "hook_budget", lambda name: (lambda root: 0.001))
    (repo / ".iaso" / "session").mkdir(parents=True, exist_ok=True)
    (repo / ".iaso" / "session" / "brief_seen.json").write_text("{}", "utf-8")  # all changed
    lines = _start(repo, hook_input, verify=FakeVerify())
    assert lines[0].startswith("iaso: changed since you last looked: SR-001")
    assert lines[-1].startswith("iaso: check skipped (budget)")


def test_cold_branch_scan_is_bounded_and_continues_next_start(repo: Path, monkeypatch) -> None:
    import time

    from iaso.api import open_core
    from iaso.awareness import scan

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
