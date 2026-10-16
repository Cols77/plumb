"""A selection whose real time exceeds its estimate still yields evidence and adapts (7.3).

Regression for the dogfooding finding: the selector filled the whole budget, the run hit the
hard limit, and the runner dropped every result, so each turn waited for the limit, recorded
nothing and never corrected its estimate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import commit_all, make_project, write

from plumb.api import open_core
from plumb.verify import open_verify
from plumb.verify.cli import report_lines

pytestmark = pytest.mark.sr("SR-255")

SLOW_TESTS = 16
# pytest plus coverage start-up takes 10-20 s on a cold Windows box and counts against the hard
# limit, so the limit (budget 16 x factor 2) leaves room for it and the tests still overrun it.


@pytest.fixture
def project(repo: Path) -> Path:
    make_project(repo)
    body = "import time\n\nimport pkg.mod\n"
    for i in range(SLOW_TESTS):
        body += f"\n\ndef test_slow_{i:02d}():\n    time.sleep(2.0)\n"
    write(repo, "tests/test_slow.py", body)
    # every estimate is far too low: unknown tests count 0.05 s
    write(repo, ".plumb/config.yaml", "verify:\n  flaky_rerun: false\n  default_test_s: 0.05\n"
          "  hard_limit_factor: 2\n")
    commit_all(repo)
    return repo


def test_overrun_records_finished_tests_and_learns_its_pace(project: Path) -> None:
    verify = open_verify(open_core(project))
    first = verify.select(["src/pkg/mod.py"], budget_s=16)
    assert "tests/test_slow.py" in first.nodes  # 0.05 s each: everything fits

    report = verify.run(changed=["src/pkg/mod.py"], budget_s=16)
    assert report.timed_out is True
    passed = sorted(n for n, o in report.outcomes.items() if o == "passed")
    assert passed, "tests that finished before the hard limit are kept"
    lines = report_lines(report)
    assert any("timeout after 32 s" in line and f"{len(report.outcomes)} finished" in line
               for line in lines), lines

    again = open_verify(open_core(project))
    evidence = again.evidence(passed)
    assert all(e.state == "fresh-pass" for e in evidence.values())
    assert again.index()["scale"] > 1.0
    # the next selection of the same change no longer schedules the slow file
    second = again.select(["src/pkg/mod.py"], budget_s=16)
    assert "tests/test_slow.py" not in second.nodes
    assert "tests/test_slow.py" in second.deferred
