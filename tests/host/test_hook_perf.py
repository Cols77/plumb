"""SR-014: the hooks finish well inside their budgets on plumb's own records, and the hook
modules stay cheap to import."""

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

pytestmark = pytest.mark.sr("SR-014")

REPO = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True,
                          encoding="utf-8").stdout


@pytest.fixture(scope="module")
def own_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A clone of this repository's committed state (its own .plumb records, source and
    tests), with the test map built once (a hook never builds it)."""
    root = tmp_path_factory.mktemp("own") / "plumb"
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


_HARNESS = """
import io, json, sys, time
start = time.monotonic()
import importlib
module = importlib.import_module("plumb.hosts.claude_code." + sys.argv[1])
out = io.StringIO()
module.main(stdin=io.StringIO(sys.argv[3]), stdout=out, root=sys.argv[2], watchdog=False,
            start=start)
print(json.dumps({"ms": (time.monotonic() - start) * 1000, "out": out.getvalue()}))
"""


def _call(root: Path, module: str, payload: dict[str, object]) -> tuple[str, float]:
    """One hook in its own process, timed as the hook times itself: from the moment the
    dispatcher hands over (the hook module's imports included) to the answer."""
    result = subprocess.run([sys.executable, "-c", _HARNESS, module, str(root),
                             json.dumps(payload)], capture_output=True, text=True,
                            encoding="utf-8", check=False, timeout=60)
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout)
    return found["out"], found["ms"]


def test_hooks_on_plumbs_own_records_finish_inside_their_budgets(own_copy: Path) -> None:
    from plumb.config import load_config

    budgets = load_config(own_copy).hooks.budget_ms
    base = {"session_id": "perf", "transcript_path": "", "cwd": str(own_copy)}
    edited = own_copy / "src" / "plumb" / "hashing.py"
    cases = {
        "session_start": {"hook_event_name": "SessionStart"},
        "prompt": {"hook_event_name": "UserPromptSubmit",
                   "prompt": "fix the stale links of SR-014"},
        "stop": {"hook_event_name": "Stop", "stop_hook_active": True},
    }
    _call(own_copy, "post_edit", {**base, "hook_event_name": "PostToolUse",
                                  "tool_name": "Edit", "tool_input": {"file_path": str(edited)}})
    for module, payload in cases.items():  # the first turn warms the caches
        _call(own_copy, module, {**base, **payload})
    (own_copy / ".plumb" / "session" / "errors.log").unlink(missing_ok=True)  # cold turn
    for module, payload in cases.items():
        runs = [_call(own_copy, module, {**base, **payload}) for _ in range(4)]
        out, best = min(runs, key=lambda run: run[1])  # a loaded machine slows single runs
        budget = float(budgets[module])
        assert best <= budget * 0.9, f"{module}: {best:.0f} ms against a {budget:.0f} ms budget"
        assert "check skipped" not in out, f"{module}: {out}"
    errors = own_copy / ".plumb" / "session" / "errors.log"
    assert not errors.exists(), errors.read_text("utf-8")


def test_hookio_imports_only_what_a_hook_always_needs() -> None:
    code = ("import json, sys, time\n"
            "start = time.perf_counter()\n"
            "import plumb.hosts.claude_code.hookio\n"
            "took = (time.perf_counter() - start) * 1000\n"
            "print(json.dumps({'ms': took, 'modules': sorted(sys.modules)}))\n")
    runs = [json.loads(subprocess.run([sys.executable, "-c", code], capture_output=True,
                                      text=True, check=True, timeout=60).stdout)
            for _ in range(5)]
    loaded = set(runs[0]["modules"])
    for heavy in ("dataclasses", "traceback", "yaml", "plumb.contracts", "plumb.hashing",
                  "plumb.api", "urllib.request"):
        assert heavy not in loaded, f"importing hookio also imports {heavy}"
    best = min(run["ms"] for run in runs)
    assert best < 350, f"hookio import took {best:.0f} ms"


def test_the_triage_offer_is_skipped_when_its_judgment_could_outlast_the_hook(
        repo: Path, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:
    """The offer may call the judgment service for up to the hook timeout: with less budget
    left than that, the brief ends without it rather than risk the watchdog."""
    from plumb.capture import api as capture_api
    from plumb.hosts.claude_code import session_start

    (repo / ".plumb" / "config.yaml").write_text("judgment:\n  backend: fake\n",
                                                encoding="utf-8")
    asked: list[int] = []

    def triage(core, ids):
        asked.append(1)
        raise RuntimeError("no offer")

    monkeypatch.setattr(capture_api, "triage", triage)
    from fakes import FakeVerify

    def run(budget_ms: float) -> None:
        monkeypatch.setattr(session_start, "hook_budget", lambda name: (lambda root: budget_ms))
        session_start.main(stdin=io.StringIO(hook_input("SessionStart")), stdout=io.StringIO(),
                           root=repo, verify=FakeVerify())

    run(300)  # the default judgment timeout is 800 ms
    assert not asked
    run(60000)
    assert asked


def test_a_warm_session_start_reads_no_record_file(
        own_copy: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The index cache keys on each record file's size and mtime: a warm load of plumb's own
    records opens none of them."""
    from plumb.paths import PlumbPaths
    from plumb.store import Store

    Store(PlumbPaths(own_copy)).index()
    Store(PlumbPaths(own_copy)).index()  # stamps the files that were too fresh to trust
    opened: list[str] = []
    real = Path.read_text

    def counted(self: Path, *args, **kwargs):
        opened.append(str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted)
    started = statistics.median(_time(lambda: Store(PlumbPaths(own_copy)).index())
                                for _ in range(3))
    assert not [p for p in opened if p.endswith(".md")]
    assert started < 500


def _time(fn) -> float:
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000


def test_plumbs_own_runs_use_two_xdist_workers() -> None:
    """The runner passes -n 2 for this repository (``verify.workers`` in its config)."""
    from plumb.config import load_config
    from plumb.verify.runner import build_command, xdist_available

    assert xdist_available(), "pytest-xdist is a dev dependency"
    workers = load_config(REPO).verify.workers
    assert workers == 2
    assert build_command(["tests/x.py"], workers=workers)[-3:] == ["-n", "2", "tests/x.py"]
