"""Run pytest on a selection (spec 7.3).

``sys.executable -m pytest -p iaso.verify.pytest_plugin -q <nodes>`` from the repository
root, with the report path in ``IASO_REPORT``. Never ``-n`` unless ``verify.workers`` is 1
or 2 and pytest-xdist is installed. On the hard wall-clock limit iaso terminates the pytest
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
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from iaso.verify.envid import test_interpreter  # noqa: F401 - lives in envid, so session start skips this module

PLUGIN = "iaso.verify.pytest_plugin"
COV_PLUGIN = "iaso.verify.cov_plugin"  # SR-110: coverage contexts, one per test node
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
    "iaso_run_progress", default=None)


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
PYTEST_MISSING = ("pytest is not installed for {python}: install it there, or name the "
                  "interpreter that has it in verify.python")
_PROBED: dict[str, tuple[str | None, bool]] = {}


def _probe(interpreter: str) -> tuple[str | None, bool]:
    """``(why pytest cannot run there, whether iaso's own package must be put on its path)``
    for ``interpreter``, asked once per process: the pytest plugin the run loads is iaso's."""
    if interpreter in _PROBED:
        return _PROBED[interpreter]
    if interpreter == sys.executable:
        found = (None if _find("pytest") else PYTEST_MISSING.format(python=interpreter), False)
    else:
        code = ("import importlib.util as u; print(int(u.find_spec('pytest') is None), "
                "int(u.find_spec('iaso') is None))")
        try:
            out = subprocess.run([interpreter, "-c", code], capture_output=True, text=True,
                                 timeout=30, check=False).stdout.split()
        except (OSError, subprocess.SubprocessError):
            out = []
        no_pytest, no_iaso = (out + ["1", "1"])[:2]
        found = (PYTEST_MISSING.format(python=interpreter) if no_pytest == "1" else None,
                 no_iaso == "1")
    _PROBED[interpreter] = found
    return found


def _find(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


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
                  cov: bool = False, interpreter: str | None = None) -> list[str]:
    cmd = [interpreter or sys.executable, "-m", "pytest", "-p", PLUGIN, "-p", "no:cacheprovider",
           "-q", "--continue-on-collection-errors"]
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
    from iaso.verify.markers import strip_param

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
               step: str | None = None, interpreter: str | None = None) -> RunResult:
    """Run pytest once in ``root`` and read the plugin's report. With ``cov`` the coverage
    plugin writes one data file per process (``result.cov_files``). With ``progress`` (a
    ``progress.Reporter``) the run says ``step``, how many tests have finished of the total and
    the test file it is in; nothing it decides changes."""
    import glob
    import time

    root = Path(root)
    fd, report_path = tempfile.mkstemp(prefix="iaso-report-", suffix=".json")
    os.close(fd)
    os.remove(report_path)
    # Without the git hook variables: the pre-push hook runs the suite inside the hook process,
    # and an inherited GIT_DIR would point every fixture's `git init` at the host repository
    # and rewrite its shared config (report-2680054f).
    from iaso.background import child_env

    env = child_env()
    env["IASO_REPORT"] = report_path
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = RunResult()
    interpreter = interpreter or sys.executable
    missing, needs_iaso = _probe(interpreter)
    if missing:   # no run at all: the lane says why instead of failing every test
        result.notes.append(missing)
        result.output = missing
        result.exit_status = 1
        return result
    if needs_iaso:
        import iaso

        env["PYTHONPATH"] = os.pathsep.join(
            [str(Path(iaso.__file__).resolve().parent.parent)]
            + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    used, note = effective_workers(workers)
    result.workers = used
    if note:
        result.notes.append(note)
    skip_file = None
    if cov is not None:
        env["IASO_COV_DATA"] = cov.data_base
        env["IASO_COV_SOURCES"] = os.pathsep.join(cov.sources)
        if cov.deselect:
            env["IASO_COV_DESELECT"] = "1"
        if cov.skip:
            skip_file = cov.data_base + ".skip"
            Path(skip_file).write_text(chr(10).join(sorted(cov.skip)), encoding="utf-8")
            env["IASO_COV_SKIP"] = skip_file
    env["PYTHONDONTWRITEBYTECODE"] = "1"   # a file edited within the second of a run is read afresh
    cmd = build_command(args, workers=workers, cov=cov is not None, interpreter=interpreter)
    # Each run's tmp_path folders live under a base of its own, removed when the run ends:
    # pytest's keep-3 cleanup of /tmp/pytest-of-<user> did not keep up with many sessions'
    # runs and used up /tmp's inodes (and, on tmpfs, its memory).
    basetemp = tempfile.mkdtemp(prefix="iaso-pytest-")
    cmd.append(f"--basetemp={basetemp}")
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
        proc.terminate()  # only the process iaso started
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    if watch is not None:
        watch.finish()
    shutil.rmtree(basetemp, ignore_errors=True)
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
    from iaso.normalize import file_digest

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
    from iaso import progress as progress_module
    from iaso.verify.testmap import build_map

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
                            workers=workers, cov=cov, interpreter=test_interpreter(
                                root, str(getattr(core.config.verify, "python", "") or "")))
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
