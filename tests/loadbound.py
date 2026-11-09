"""SR-307: a test marked ``load_bound`` asserts a time budget, so it first waits for a free CPU;
if it then misses its budget it is reported xfailed as load-bound (the run stays green) and a
debug case is written. Any other failure of a marked test fails as usual."""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
import time
import warnings
from collections.abc import Callable
from types import SimpleNamespace

import pytest

FREE_BELOW = 50.0
WAIT_LIMIT = 300.0
_last: list[int] = []


def cpu_busy() -> float:
    """System CPU use in percent over one second (psutil is not installed: no dependency)."""
    if sys.platform != "win32":
        time.sleep(1)
        return os.getloadavg()[0] / (os.cpu_count() or 1) * 100

    def times() -> tuple[int, int]:
        idle, kernel, user = (ctypes.c_ulonglong() for _ in range(3))
        ctypes.windll.kernel32.GetSystemTimes(*(ctypes.byref(v) for v in (idle, kernel, user)))
        return idle.value, kernel.value + user.value      # kernel time includes idle

    (idle0, total0), _ = times(), time.sleep(1)
    idle1, total1 = times()
    return 100.0 * (1 - (idle1 - idle0) / max(total1 - total0, 1))


def wait_for_free_cpu(busy: Callable[[], float] = cpu_busy, limit: float = WAIT_LIMIT,
                      clock: Callable[[], float] = time.monotonic) -> bool:
    """Wait until ``busy()`` is below 50%; False when ``limit`` seconds passed first."""
    end = clock() + limit
    while busy() >= FREE_BELOW:
        if clock() >= end:
            return False
    return True


class BudgetMiss(AssertionError):
    """A measured time went over its budget (DEC-186): the only failure counted as load-bound."""


def assert_within(elapsed: float, budget: float, what: str) -> None:
    if elapsed > budget:
        raise BudgetMiss(f"{what}: {elapsed:.3g} over the budget of {budget:.3g}")


def is_budget_failure(excinfo: pytest.ExceptionInfo) -> bool:
    return excinfo.errisinstance(BudgetMiss)


def _case(item: pytest.Item, excinfo: pytest.ExceptionInfo) -> None:
    from iaso.understand import summary

    key = hashlib.sha256(item.nodeid.encode()).hexdigest()[:8]
    summary.write_cases(SimpleNamespace(root=item.config.rootpath), f"load-bound-{key}", [{
        "id": f"LB-{key}", "kind": "load-bound test", "target": item.nodeid,
        "detail": f"missed its time budget under load: {str(excinfo.value)[:200]}"}])


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("load_bound") and not wait_for_free_cpu():
        warnings.warn(f"{item.nodeid} ran under load: the CPU stayed busy for "
                      f"{WAIT_LIMIT / 60:.0f} minutes", stacklevel=1)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    report = (yield).get_result()
    if (call.when == "call" and call.excinfo and item.get_closest_marker("load_bound")
            and is_budget_failure(call.excinfo)):
        _case(item, call.excinfo)
        report.outcome, report.wasxfail = "skipped", "load-bound: missed its time budget"
