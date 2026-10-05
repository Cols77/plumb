"""Run pytest on a selection (spec 7.3).

``sys.executable -m pytest -p plumb.verify.pytest_plugin -q <nodes>`` from the repository
root, with the report path in ``PLUMB_REPORT``. Never ``-n`` unless ``verify.workers`` is 1
or 2 and pytest-xdist is installed. On the hard wall-clock limit plumb terminates the pytest
process it started, and only that one. When a file of the selection's import closure
changes during the run, the run is discarded (``inputs changed``): it gives no evidence.

A collection error (an import or syntax error in a test module) does not stop the session:
``--continue-on-collection-errors`` lets the other selected files run, and every known node of
a selected file that failed to collect counts as ``failed`` in phase ``collect``, so a test
that passed before and can no longer even be imported is a regression (R3), never ``stale``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PLUGIN = "plumb.verify.pytest_plugin"
_FAIL_RANK = {"setup": 0, "call": 1, "teardown": 2}


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


@dataclass
class RunOutcome:
    result: RunResult
    discarded: str | None = None
    inputs: dict[str, str] = field(default_factory=dict)


def xdist_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("xdist") is not None


def build_command(args: Sequence[str], *, workers: int = 0,
                  xdist: bool | None = None) -> list[str]:
    cmd = [sys.executable, "-m", "pytest", "-p", PLUGIN, "-p", "no:cacheprovider", "-q",
           "--continue-on-collection-errors"]
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


def run_pytest(root: Path, args: Sequence[str], *, timeout_s: float | None = None,
               workers: int = 0) -> RunResult:
    """Run pytest once in ``root`` and read the plugin's report."""
    import time

    root = Path(root)
    fd, report_path = tempfile.mkstemp(prefix="plumb-report-", suffix=".json")
    os.close(fd)
    os.remove(report_path)
    env = dict(os.environ)
    env["PLUMB_REPORT"] = report_path
    env.setdefault("PYTHONIOENCODING", "utf-8")
    cmd = build_command(args, workers=workers)
    result = RunResult()
    start = time.monotonic()
    proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
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
    result.elapsed_s = round(time.monotonic() - start, 3)
    result.output = (out or b"").decode("utf-8", errors="replace")[-4000:]
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    finally:
        try:
            os.remove(report_path)
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


def run_selection(core: Any, nodes: Sequence[str], *, full: bool = False,
                  timeout_s: float | None = None, tmap: Any = None) -> RunOutcome:
    """Run ``nodes`` (or the whole suite when ``full``) and check the inputs did not move."""
    from plumb.verify.testmap import build_map

    root = Path(core.root)
    tmap = tmap or build_map(core, write_text=False)
    test_files = tmap.test_files if full else [n.split("::", 1)[0] for n in nodes]
    watched = closure_inputs(tmap, test_files)
    before = input_hashes(root, watched)
    workers = int(getattr(core.config.verify, "workers", 0) or 0)
    result = run_pytest(root, [] if full else list(nodes), timeout_s=timeout_s, workers=workers)
    after = input_hashes(root, watched)
    discarded = "inputs changed" if after != before else None
    return RunOutcome(result=result, discarded=discarded, inputs=before)
