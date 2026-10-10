"""plumb's coverage-context pytest plugin (SR-110), loaded with ``-p plumb.verify.cov_plugin``.

Measures the source directories with ``coverage`` and switches the coverage context to the
test's node id for the whole of one test (setup, call and teardown), so the data says which
lines each test executed. Each process (the single one, or each pytest-xdist worker) writes its
own data file, ``<PLUMB_COV_DATA>.<worker id>``; the caller combines them.

Environment:

- ``PLUMB_COV_DATA``: base path of the data files (the plugin does nothing without it).
- ``PLUMB_COV_SOURCES``: the directories to measure, joined by ``os.pathsep``.
- ``PLUMB_COV_SKIP``: a file listing node ids (one per line) whose record is fresh; they are
  not measured.
- ``PLUMB_COV_DESELECT=1``: the skipped nodes are not run at all (a recording-only run).

Coverage starts at the first measured test, never at collection, so a process that measures
nothing costs nothing. Standard library, pytest and coverage only.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

_state: dict[str, Any] = {"cov": None, "base": None, "sources": [], "skip": set(),
                          "deselect": False, "worker": "main", "started": False}


def pytest_configure(config: Any) -> None:
    base = os.environ.get("PLUMB_COV_DATA")
    _state["base"] = base
    _state["cov"] = None
    _state["started"] = False
    _state["worker"] = getattr(config, "workerinput", {}).get("workerid", "main")
    _state["sources"] = [s for s in os.environ.get("PLUMB_COV_SOURCES", "").split(os.pathsep)
                         if s]
    _state["deselect"] = os.environ.get("PLUMB_COV_DESELECT") == "1"
    skip: set[str] = set()
    listing = os.environ.get("PLUMB_COV_SKIP")
    if listing:
        try:
            with open(listing, encoding="utf-8") as handle:
                skip = {line.rstrip("\n") for line in handle if line.strip()}
        except OSError:
            skip = set()
    _state["skip"] = skip


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    if not _state["base"] or not _state["deselect"] or not _state["skip"]:
        return
    keep = [i for i in items if i.nodeid not in _state["skip"]]
    gone = [i for i in items if i.nodeid in _state["skip"]]
    if gone:
        items[:] = keep
        config.hook.pytest_deselected(items=gone)


def _coverage() -> Any:
    if _state["cov"] is None:
        import coverage

        _state["cov"] = coverage.Coverage(
            data_file=f"{_state['base']}.{_state['worker']}", source=_state["sources"] or None,
            config_file=False, branch=False)
    return _state["cov"]


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: Any, nextitem: Any):  # type: ignore[no-untyped-def]
    if not _state["base"] or item.nodeid in _state["skip"]:
        return (yield)
    cov = _coverage()
    cov.start()
    _state["started"] = True
    cov.switch_context(item.nodeid)
    try:
        return (yield)
    finally:
        cov.stop()


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    cov = _state["cov"]
    if cov is None:
        return
    try:
        cov.save()
    except Exception:  # noqa: BLE001 - no data never breaks the run
        pass
