"""SR-254 EX-22: a repin waits while a covering test needed the automatic retry (report-9bfacadd)."""
from types import SimpleNamespace

import pytest

from iaso import links


def _verify(report):
    return lambda core: SimpleNamespace(run=lambda **kw: report)


def _report(**kw):
    base = dict(run_id="r1", ok=True, flaky=[], failed=[], timed_out=False, aborted=None,
                discarded=None, collection_errors=[])
    return SimpleNamespace(**{**base, **kw})


@pytest.mark.sr("SR-254")
def test_ex22_a_retry_pass_stops_the_repin_and_names_the_test(monkeypatch) -> None:
    monkeypatch.setattr("iaso.verify.open_verify", _verify(_report(flaky=["tests/a.py::test_x"])))
    ok, detail = links.default_runner(None)(["src/iaso/a.py"])
    assert not ok and "tests/a.py::test_x" in detail and "retry" in detail


@pytest.mark.sr("SR-254")
def test_ex22_a_clean_pass_still_goes_through(monkeypatch) -> None:
    monkeypatch.setattr("iaso.verify.open_verify", _verify(_report()))
    assert links.default_runner(None)(["src/iaso/a.py"]) == (True, "passed")
