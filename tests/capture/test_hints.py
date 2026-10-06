"""CAPTURE CS6: a bounded hidden-dependency scan, shown as hints only (R12.4; sp2 10.2,
SR-045)."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest
from capture_helpers import record_text

from plumb.api import open_core
from plumb.capture.hints import drift_hints
from plumb.judgment import FakeBackend

pytestmark = pytest.mark.sr("SR-045")

SR4 = ".plumb/requirements/SR-004.md"


def commit(root: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=root, check=True,
                   capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    from plumb.approvals import approve

    write_record(repo, record_text("SR-004", "Invoices round totals",
                                   statement="invoice totals are rounded to cents"))
    write_record(repo, record_text("SR-012", "Refunds reuse invoice totals",
                                   statement="a refund repays the invoice totals in cents"))
    write_record(repo, record_text("SR-013", "Login lockout",
                                   statement="three failed logins lock the account"))
    approve(open_core(repo), ["SR-004"])
    commit(repo)
    path = repo / SR4
    path.write_text(path.read_text(encoding="utf-8").replace(
        "rounded to cents", "rounded up to whole cents per invoice line"), encoding="utf-8")
    return repo


def test_changed_confirmed_record_hints_at_an_unlinked_dependent(project: Path) -> None:
    core = open_core(project)
    states_before = [(s.link.id, s.state) for s in core.link_states()]
    lines = drift_hints(core, [SR4])
    assert lines and lines[0].startswith(
        "plumb: hint: SR-012 may depend on the change to SR-004 (no link)")
    assert not any("SR-013" in line for line in lines)
    assert [(s.link.id, s.state) for s in open_core(project).link_states()] == states_before


def test_backend_no_drops_the_hint(project: Path) -> None:
    backend = FakeBackend({("dependency", "SR-012"): ("no", 0.9)})
    assert drift_hints(open_core(project), [SR4], backend=backend) == []


def test_scan_is_bounded(project: Path, write_record) -> None:
    for n in range(50):
        write_record(project, record_text(f"SR-{200 + n}", f"invoice rule {n}",
                                          statement="invoice totals in whole cents per line"))

    class Counting(FakeBackend):
        calls = 0

        def ask(self, question, context, *, subject, action):
            Counting.calls += 1
            return super().ask(question, context, subject=subject, action=action)

    started = time.monotonic()
    lines = drift_hints(open_core(project), [SR4], backend=Counting())
    assert Counting.calls <= 5 and len(lines) <= 5
    assert time.monotonic() - started < 1.5
