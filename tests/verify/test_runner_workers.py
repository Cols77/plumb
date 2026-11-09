"""HB5: selected tests run on verify.workers pytest-xdist workers (SR-110, EX-3)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from verify_helpers import make_project, write

from iaso.api import open_core
from iaso.verify import open_verify, runner
from iaso.verify.cli import report_lines

WORKER_TESTS = "".join(
    f"\n\ndef test_w{i}():\n    time.sleep(0.4)\n    with open(SEEN, 'a') as f:\n"
    "        f.write(os.environ.get('PYTEST_XDIST_WORKER', 'main') + '\\n')\n" for i in range(6))


def _project(repo: Path, workers: int, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in list(os.environ):  # the outer run may itself be an xdist worker
        if name.startswith("PYTEST_XDIST"):
            monkeypatch.delenv(name)
    make_project(repo)
    write(repo, ".iaso/config.yaml", f"verify:\n  flaky_rerun: false\n  workers: {workers}\n")
    write(repo, "tests/test_workers.py",
          "import os\nimport time\n\nSEEN = os.path.join(os.path.dirname(__file__), 'seen.txt')\n"
          + WORKER_TESTS)
    return repo


def _seen(root: Path) -> set[str]:
    return set((root / "tests" / "seen.txt").read_text(encoding="utf-8").split())


@pytest.mark.sr("SR-255")
def test_ex3_two_workers_with_xdist(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(repo, 2, monkeypatch)
    verify = open_verify(open_core(root), hook=False)
    report = verify.run(nodes=["tests/test_workers.py"])
    assert report.ok, str(report.as_dict())[:1500]
    assert report.workers == 2
    assert _seen(root) == {"gw0", "gw1"}
    assert not any("xdist" in line for line in report_lines(report))


@pytest.mark.sr("SR-255")
def test_xdist_missing_runs_serial_and_says_so(repo: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "xdist_available", lambda: False)
    root = _project(repo, 2, monkeypatch)
    result = runner.run_pytest(root, ["tests/test_workers.py::test_w0"], workers=2)
    assert result.workers == 0
    assert any("pytest-xdist is not installed" in note for note in result.notes)
    verify = open_verify(open_core(root), hook=False)
    report = verify.run(nodes=["tests/test_workers.py::test_w1"])
    assert report.ok, str(report.as_dict())[:1500]
    assert report.workers == 0
    assert any("pytest-xdist is not installed" in line for line in report_lines(report))
    assert _seen(root) == {"main"}


@pytest.mark.sr("SR-255")
def test_run_selection_passes_workers(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(repo, 2, monkeypatch)
    seen: list[int] = []

    def fake(root_: Path, args, *, timeout_s=None, workers=0, cov=None, interpreter=None):
        seen.append(workers)
        return runner.RunResult()

    monkeypatch.setattr(runner, "run_pytest", fake)
    core = open_core(root)
    runner.run_selection(core, ["tests/test_workers.py"])
    runner.run_selection(core, [], full=True)
    assert seen == [2, 2]
    # `--paths`, `--changed` and the stop hook's run all come through Verify.run
    verify = open_verify(core, hook=False)
    verify.run(changed=["src/pkg/mod.py"])
    verify.run(changed=None)
    assert set(seen) == {2}
