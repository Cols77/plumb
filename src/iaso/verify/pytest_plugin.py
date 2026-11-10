"""iaso's pytest reporting plugin, loaded with ``-p iaso.verify.pytest_plugin``.

Extracted and simplified from pi-agent-factory's
``coherence/execution/pytest_evidence_plugin.py``: per-phase outcomes, collection errors and
the exit status, written as JSON to the path in ``IASO_REPORT``. Only the controlling
process publishes; xdist workers (at most ``-n 2``) report through it. Standard library and
pytest only, and nothing from the project under test.

Each phase is also streamed, one JSON line flushed as it completes, to ``IASO_REPORT`` +
``.stream``: a run stopped at the hard limit never reaches ``pytest_sessionfinish``, and the
runner still reads the tests that finished before it from the stream.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

_report: dict[str, Any] = {}
_worker_id: str | None = None
_stream: Any = None
_total_sent = False
STREAM_SUFFIX = ".stream"


def _empty() -> dict[str, Any]:
    return {"schema": 1, "collected": [], "collection_errors": [], "phases": [],
            "finished": False}


def _publish() -> None:
    target = os.environ.get("IASO_REPORT")
    if not target:
        return
    Path(target).write_text(json.dumps(_report, allow_nan=False), encoding="utf-8")


def pytest_configure(config: Any) -> None:
    global _report, _worker_id, _stream, _total_sent
    _report = _empty()
    _total_sent = False
    _worker_id = getattr(config, "workerinput", {}).get("workerid")
    target = os.environ.get("IASO_REPORT")
    if target and _worker_id is None:
        try:
            _stream = open(target + STREAM_SUFFIX, "a", encoding="utf-8")
        except OSError:
            _stream = None


def _stream_phase(phase: dict[str, Any]) -> None:
    global _stream
    if _stream is None:
        return
    try:
        _stream.write(json.dumps(phase, allow_nan=False) + "\n")
        _stream.flush()
    except (OSError, ValueError):
        _stream = None


def pytest_collection_finish(session: Any) -> None:
    _report["collected"] = [item.nodeid for item in session.items]
    _stream_total(len(session.items))


def _stream_total(count: int) -> None:
    """Say once how many tests the run has, for the runner's progress (done of total). A line
    with a ``total`` and no node id: the readers of the stream skip it."""
    global _total_sent
    if _total_sent or _worker_id is not None or count <= 0:
        return
    _total_sent = True
    _stream_phase({"total": count})


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node: Any, ids: Any) -> None:
    """With xdist the controller collects nothing itself: the first worker's list is the total."""
    _stream_total(len(ids))


def pytest_collectreport(report: Any) -> None:
    if report.failed and report.nodeid not in _report["collection_errors"]:
        _report["collection_errors"].append(report.nodeid)


def pytest_runtest_logreport(report: Any) -> None:
    if _worker_id is not None:
        return  # the controller receives the serialized phase reports
    duration = report.duration
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
        duration = 0.0
    phase = {"nodeid": report.nodeid, "when": report.when, "outcome": report.outcome,
             "xfail": hasattr(report, "wasxfail"), "duration": duration}
    _report["phases"].append(phase)
    _stream_phase(phase)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    if _worker_id is not None:
        return
    _report["exitstatus"] = int(exitstatus)
    _report["finished"] = True
    _publish()


def pytest_unconfigure(config: Any) -> None:
    global _stream
    if _stream is not None:
        try:
            _stream.close()
        except OSError:
            pass
        _stream = None
