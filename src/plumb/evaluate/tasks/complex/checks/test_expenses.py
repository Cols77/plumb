"""Hidden checks of the complex task: run from the repository root, drive expenses.py."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("expenses.py").resolve()


@pytest.fixture
def run(tmp_path):
    """Run expenses.py from a private copy, so its CSV files start empty for each check."""
    script = shutil.copy(SCRIPT, tmp_path / "expenses.py")

    def go(*args: str) -> str:
        done = subprocess.run([sys.executable, script, *args], capture_output=True, text=True,
                              cwd=tmp_path, timeout=20)
        return done.stdout + done.stderr

    go.dir = tmp_path
    return go


# request: 1
def test_add_then_list(run):
    run("add", "2026-03-05", "food", "1250", "lunch")
    line = run("list").split()
    assert line[:3] == ["2026-03-05", "food", "1250"] and "lunch" in line


# request: 2
def test_report_one_month(run):
    run("add", "2026-03-05", "food", "1250")
    run("add", "2026-03-09", "food", "1750")
    run("add", "2026-03-10", "transport", "500")
    run("add", "2026-04-01", "food", "999")
    lines = [ln.split() for ln in run("report", "2026-03").splitlines() if ln.strip()]
    assert lines == [["food", "3000"], ["transport", "500"], ["total", "3500"]]


# request: 3
def test_over_budget_warning(run):
    run("budget", "food", "2000")
    assert "over budget" not in run("add", "2026-03-05", "food", "1500")
    assert "over budget: food" in run("add", "2026-03-06", "food", "600")


# request: 4
def test_float_refused(run):
    assert "invalid amount" in run("add", "2026-03-05", "food", "12.50")
    assert "food" not in run("list")


# request: 4
def test_cents_printed(run):
    run("add", "2026-03-05", "food", "1250")
    out = run("list")
    assert "1250" in out and "12.50" not in out


def bank_file(run) -> str:
    path = run.dir / "bank.csv"
    path.write_text("Description,Amount,Date\nCoffee,-350,05/03/2026\n"
                    "Salary,200000,01/03/2026\nBooks,-1200,07/03/2026\n", encoding="utf-8")
    return str(path)


# request: 5
def test_import_adds_spending_rows(run):
    run("import", bank_file(run))
    out = run("report", "2026-03").split()
    assert "bank" in out and "1550" in out


# request: 5
def test_import_skips_income(run):
    run("import", bank_file(run))
    out = run("list")
    assert len(out.splitlines()) == 2 and "200000" not in out
