"""Run pytest on a selection (spec 7.3).

``sys.executable -m pytest -p plumb.verify.pytest_plugin -q <nodes>`` from the repository
root, with the report path in ``PLUMB_REPORT``. Never ``-n`` unless ``verify.workers`` is 1
or 2 and pytest-xdist is installed. On the hard wall-clock limit plumb terminates the pytest
process it started, and only that one. A run stopped at the hard limit keeps the tests that
finished before it (every phase through teardown, read from the plugin's phase stream); the
test that was running and the ones after it give no evidence. When a file of the selection's
import closure changes during the run, the run is discarded (``inputs changed``): it gives no
evidence.

A collection error (an import or syntax error in a test module) does not stop the session:
``--continue-on-collection-errors`` lets the other selected files run, and every known node of
a selected file that failed to collect counts as ``failed`` in phase ``collect``, so a test
that passed before and can no longer even be imported is a regression (R3), never ``stale``.
"""

from __future__ import annotations

import contextvars
import json
import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PLUGIN = "plumb.verify.pytest_plugin"
COV_PLUGIN = "plumb.verify.cov_plugin"  # SR-110: coverage contexts, one per test node
STREAM_SUFFIX = ".stream"  # the plugin's phase stream, next to its report
_FAIL_RANK = {"setup": 0, "call": 1, "teardown": 2}
# SR-108: what a run says it is doing, and how it says it ended
STEP_FULL = "running the full suite"
STEP_COVERING = "running the covering tests"
STEP_RECORDING = "recording which code each test runs"
END_BY_STEP = {STEP_FULL: "the full suite finished", STEP_COVERING: "the covering tests finished",
               STEP_RECORDING: "recording finished"}
STOPPED = "{step} stopped at the time limit"
# the reporter and step of the run in progress, set by ``run_selection`` (a context, not an
# argument: ``run_pytest`` keeps its signature for everything that calls or replaces it)
_PROGRESS: contextvars.ContextVar[tuple[Any, str] | None] = contextvars.ContextVar(
    "plumb_run_progress", default=None)


@dataclass
class RunResult:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    collected: list[str] = field(default_factory=list)
    collection_errors: list[str] = field(default_factory=list)
    exit_status: int | None = None
    timed_out: bool = False
    finished: bool = False
    output: str = ""
    elapsed_s: float = 0.0
    workers: int = 0                       # xdist workers the run used (0: serial)
    notes: list[str] = field(default_factory=list)  # lines the run says (never a silent change)
    cov_files: list[str] = field(default_factory=list)  # coverage data files it wrote


@dataclass(frozen=True)
class CovSpec:
    """Record coverage contexts during the run (SR-110): data files next to ``data_base``;
    nodes in ``skip`` are not measured (their record is fresh), or not run when ``deselect``."""

    data_base: str
    sources: tuple[str, ...] = ()
    skip: frozenset[str] = frozenset()
    deselect: bool = False


@dataclass
class RunOutcome:
    result: RunResult
    discarded: str | None = None
    inputs: dict[str, str] = field(default_factory=dict)


def xdist_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("xdist") is not None


def coverage_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("coverage") is not None


XDIST_MISSING = ("pytest-xdist is not installed: the tests run on one process "
                 "(verify.workers is {workers})")


def effective_workers(workers: int, xdist: bool | None = None) -> tuple[int, str | None]:
    """``(workers actually used, the line to say when that differs from the setting)``."""
    if workers not in (1, 2):
        return 0, None
    if xdist is None:
        xdist = xdist_available()
    if xdist:
        return workers, None
    return 0, XDIST_MISSING.format(workers=workers)


def build_command(args: Sequence[str], *, workers: int = 0, xdist: bool | None = None,
                  cov: bool = False) -> list[str]:
    cmd = [sys.executable, "-m", "pytest", "-p", PLUGIN, "-p", "no:cacheprovider", "-q",
           "--continue-on-collection-errors"]
    if cov:
        cmd += ["-p", COV_PLUGIN]
    if workers in (1, 2):
        if xdist is None:
            xdist = xdist_available()
        if xdist:
            cmd += ["-n", str(workers)]
    return cmd + list(args)


def _node_outcomes(phases: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """One outcome per node: any failed phase fails it (setup or teardown outrank a pass)."""
    nodes: dict[str, dict[str, Any]] = {}
    for phase in phases:
        node = nodes.setdefault(str(phase["nodeid"]), {"outcome": "passed", "duration_s": 0.0,
                                                       "_seen": set()})
        node["duration_s"] = round(node["duration_s"] + float(phase.get("duration") or 0), 6)
        when = str(phase.get("when"))
        node["_seen"].add(when)
        outcome = phase.get("outcome")
        if outcome == "failed":
            if node["outcome"] != "failed":
                node["outcome"] = "failed"
                node["failed_phase"] = when
        elif outcome == "skipped" and node["outcome"] == "passed":
            node["outcome"] = "xfailed" if phase.get("xfail") else "skipped"
    for node in nodes.values():
        node.pop("_seen", None)
    return nodes


def _collect_error_hits(errors: Sequence[str], test_file: str) -> bool:
    """Whether a collection error id (a module, or a directory above it) covers the file."""
    for err in errors:
        err = err.split("::", 1)[0].rstrip("/")
        if err in ("", ".") or test_file == err or test_file.startswith(err + "/"):
            return True
    return False


def mark_collection_failures(result: RunResult, targets: Sequence[str],
                             known: Mapping[str, Iterable[str]], *,
                             everything: bool = False) -> list[str]:
    """Record the known nodes of every target that failed to collect as ``failed``.

    ``targets`` are the selection's arguments (test files or node ids); ``known`` maps a test
    file to its known node ids (recorded ids and the ids its source defines). A node id target
    marks only its own nodes. Nodes the run reported stay as they are. ``everything`` (an
    aborted session) treats every target as failed to collect. Returns the marked ids.
    """
    from plumb.verify.markers import strip_param

    if not result.collection_errors and not everything:
        return []
    marked: list[str] = []
    for target in targets:
        test_file, _, rest = target.partition("::")
        if not everything and not _collect_error_hits(result.collection_errors, test_file):
            continue
        for node in known.get(test_file, ()):
            if rest and not (node == target or strip_param(node) == target
                             or node.startswith(target + "::")):
                continue
            if node in result.nodes or node in marked:
                continue
            result.nodes[node] = {"outcome": "failed", "failed_phase": "collect",
                                  "duration_s": 0.0}
            marked.append(node)
    return marked


def _read_stream(path: str) -> list[dict[str, Any]]:
    """The streamed phases of a run (a torn last line is dropped)."""
    phases: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    phase = json.loads(line)
                except ValueError:
                    continue
                if isinstance(phase, dict) and phase.get("nodeid") and phase.get("when"):
                    phases.append(phase)
    except OSError:
        pass
    return phases


def finished_nodes(phases: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Outcomes of the nodes whose teardown was reported: a node cut off by the hard limit
    mid-setup or mid-call is left out, never counted as passed."""
    done = {str(p["nodeid"]) for p in phases if p.get("when") == "teardown"}
    return _node_outcomes([p for p in phases if str(p["nodeid"]) in done])


class StreamWatch:
    """Follows the plugin's phase stream while pytest runs: tests finished (a teardown) of the
    total the plugin announced once, and the file the latest test belongs to (SR-108)."""

    def __init__(self, path: str, reporter: Any, step: str, interval_s: float = 0.2) -> None:
        self.path, self.reporter, self.step = path, reporter, step
        self.interval_s = interval_s
        self.offset = 0
        self.pending = b""
        self.done: set[str] = set()
        self.total = 0
        self.current = ""
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def poll(self) -> None:
        try:
            with open(self.path, "rb") as handle:
                handle.seek(self.offset)
                chunk = handle.read()
        except OSError:
            chunk = b""
        self.offset += len(chunk)
        *lines, self.pending = (self.pending + chunk).split(b"\n")
        for raw in lines:
            try:
                phase = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            if not isinstance(phase, dict):
                continue
            if isinstance(phase.get("total"), int):
                self.total = max(self.total, phase["total"])
            node = str(phase.get("nodeid") or "")
            if node:
                self.current = node.split("::", 1)[0]
                if phase.get("when") == "teardown":
                    self.done.add(node)
        self.reporter.update(self.step, len(self.done), self.total, item=self.current)

    def start(self) -> None:
        def run() -> None:
            while not self.stop.wait(self.interval_s):
                try:
                    self.poll()
                except Exception:  # noqa: BLE001 - progress never stops a run
                    return

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def finish(self) -> None:
        self.stop.set()
        if self.thread is not None:
            self.thread.join(2)
        try:
            self.poll()
        except Exception:  # noqa: BLE001
            pass


def run_pytest(root: Path, args: Sequence[str], *, timeout_s: float | None = None,
               workers: int = 0, cov: CovSpec | None = None, progress: Any = None,
               step: str | None = None) -> RunResult:
    """Run pytest once in ``root`` and read the plugin's report. With ``cov`` the coverage
    plugin writes one data file per process (``result.cov_files``). With ``progress`` (a
    ``progress.Reporter``) the run says ``step``, how many tests have finished of the total and
    the test file it is in; nothing it decides changes."""
    import glob
    import time

    root = Path(root)
    fd, report_path = tempfile.mkstemp(prefix="plumb-report-", suffix=".json")
    os.close(fd)
    os.remove(report_path)
    env = dict(os.environ)
    env["PLUMB_REPORT"] = report_path
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = RunResult()
    used, note = effective_workers(workers)
    result.workers = used
    if note:
        result.notes.append(note)
    skip_file = None
    if cov is not None:
        env["PLUMB_COV_DATA"] = cov.data_base
        env["PLUMB_COV_SOURCES"] = os.pathsep.join(cov.sources)
        if cov.deselect:
            env["PLUMB_COV_DESELECT"] = "1"
        if cov.skip:
            skip_file = cov.data_base + ".skip"
            Path(skip_file).write_text(chr(10).join(sorted(cov.skip)), encoding="utf-8")
            env["PLUMB_COV_SKIP"] = skip_file
    cmd = build_command(args, workers=workers, cov=cov is not None)
    start = time.monotonic()
    if progress is None and _PROGRESS.get() is not None:
        progress, step = _PROGRESS.get()
    step = step or STEP_FULL
    watch = StreamWatch(report_path + STREAM_SUFFIX, progress, step) if progress else None
    if progress is not None:
        progress.update(step)
    proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    if watch is not None:
        watch.start()
    try:
        out, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        result.timed_out = True
        proc.terminate()  # only the process plumb started
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    if watch is not None:
        watch.finish()
    result.elapsed_s = round(time.monotonic() - start, 3)
    if cov is not None:
        result.cov_files = sorted(f for f in glob.glob(glob.escape(cov.data_base) + ".*")
                                  if not f.endswith((".skip", "-journal")))
    result.output = (out or b"").decode("utf-8", errors="replace")[-4000:]
    stream_path = report_path + STREAM_SUFFIX
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    finally:
        try:
            os.remove(report_path)
        except OSError:
            pass
    if result.timed_out:
        result.nodes = finished_nodes(_read_stream(stream_path))
    try:
        os.remove(stream_path)
    except OSError:
        pass
    if report and not result.timed_out:
        result.finished = bool(report.get("finished"))
        result.collected = list(report.get("collected") or [])
        result.collection_errors = list(report.get("collection_errors") or [])
        result.nodes = _node_outcomes(report.get("phases") or [])
        status = report.get("exitstatus")
        result.exit_status = int(status) if status is not None else proc.returncode
    else:
        result.exit_status = None if result.timed_out else proc.returncode
    return result


def input_hashes(root: Path, paths: Iterable[str]) -> dict[str, str]:
    """Current normalized hashes of ``paths`` (``missing`` for a file that is gone)."""
    from plumb.normalize import file_digest

    out: dict[str, str] = {}
    for rel in sorted(set(paths)):
        try:
            out[rel] = file_digest(Path(root) / rel)
        except OSError:
            out[rel] = "missing"
    return out


def closure_inputs(tmap: Any, test_files: Iterable[str]) -> set[str]:
    files: set[str] = set()
    for test in test_files:
        files |= set(tmap.closures.get(test, {test: 0}))
    return files


def _end_line(step: str, result: RunResult) -> str:
    passed = sum(1 for d in result.nodes.values() if d.get("outcome") == "passed")
    failed = sum(1 for d in result.nodes.values() if d.get("outcome") == "failed")
    counts = f"{passed} passed" + (f", {failed} failed" if failed else "")
    return f"{END_BY_STEP.get(step, step)}: {counts}"


def run_selection(core: Any, nodes: Sequence[str], *, full: bool = False,
                  timeout_s: float | None = None, tmap: Any = None,
                  cov: CovSpec | None = None) -> RunOutcome:
    """Run ``nodes`` (or the whole suite when ``full``) and check the inputs did not move.
    The run reports its progress (SR-108) on the reporter of the enclosing execution, or its
    own."""
    from plumb import progress as progress_module
    from plumb.verify.testmap import build_map

    root = Path(core.root)
    tmap = tmap or build_map(core, write_text=False)
    test_files = tmap.test_files if full else [n.split("::", 1)[0] for n in nodes]
    watched = closure_inputs(tmap, test_files)
    before = input_hashes(root, watched)
    workers = int(getattr(core.config.verify, "workers", 0) or 0)
    step = STEP_RECORDING if cov is not None else STEP_FULL if full else STEP_COVERING
    reporter, owned = progress_module.acquire(root, "tests")
    token = _PROGRESS.set((reporter, step))
    try:
        result = run_pytest(root, [] if full else list(nodes), timeout_s=timeout_s,
                            workers=workers, cov=cov)
    except BaseException:
        if owned:
            reporter.failed(f"{step} stopped")
        raise
    finally:
        _PROGRESS.reset(token)
    if owned:
        if result.timed_out:
            reporter.failed(STOPPED.format(step=step))
        else:
            reporter.done(_end_line(step, result))
    after = input_hashes(root, watched)
    discarded = "inputs changed" if after != before else None
    return RunOutcome(result=result, discarded=discarded, inputs=before)
