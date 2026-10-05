"""plumb's pytest reporting plugin, loaded with ``-p plumb.verify.pytest_plugin``.

Extracted and simplified from pi-agent-factory's
``coherence/execution/pytest_evidence_plugin.py``: per-phase outcomes, collection errors and
the exit status, written as JSON to the path in ``PLUMB_REPORT``. Only the controlling
process publishes; xdist workers (at most ``-n 2``) report through it. Standard library and
pytest only, and nothing from the project under test.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

_report: dict[str, Any] = {}
_worker_id: str | None = None


def _empty() -> dict[str, Any]:
    return {"schema": 1, "collected": [], "collection_errors": [], "phases": [],
            "finished": False}


def _publish() -> None:
    target = os.environ.get("PLUMB_REPORT")
    if not target:
        return
    Path(target).write_text(json.dumps(_report, allow_nan=False), encoding="utf-8")


def pytest_configure(config: Any) -> None:
    global _report, _worker_id
    _report = _empty()
    _worker_id = getattr(config, "workerinput", {}).get("workerid")


def pytest_collection_finish(session: Any) -> None:
    _report["collected"] = [item.nodeid for item in session.items]


def pytest_collectreport(report: Any) -> None:
    if report.failed and report.nodeid not in _report["collection_errors"]:
        _report["collection_errors"].append(report.nodeid)


def pytest_runtest_logreport(report: Any) -> None:
    if _worker_id is not None:
        return  # the controller receives the serialized phase reports
    duration = report.duration
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
        duration = 0.0
    _report["phases"].append({"nodeid": report.nodeid, "when": report.when,
                              "outcome": report.outcome, "xfail": hasattr(report, "wasxfail"),
                              "duration": duration})


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    if _worker_id is not None:
        return
    _report["exitstatus"] = int(exitstatus)
    _report["finished"] = True
    _publish()
