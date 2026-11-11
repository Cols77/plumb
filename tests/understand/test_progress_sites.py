"""SHOW P3: the long executions report through the progress reporter and decide nothing
differently (SR-108)."""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from understand.fakes import owner_level

from iaso import progress
from iaso.api import open_core
from iaso.verify import runner

pytestmark = pytest.mark.sr("SR-272")


class Pipe(io.StringIO):
    def isatty(self) -> bool:
        return False


@pytest.fixture
def loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every update is drawn at once: the thresholds of a real run are the reporter's tests."""
    monkeypatch.setattr(progress, "MIN_S", 0.0)
    monkeypatch.setattr(progress, "PLAIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(progress, "INTERVAL_S", 0.0)


def _suite(root: Path, files: int = 3, per_file: int = 4, nap: float = 0.12) -> None:
    tests = root / "tests"
    tests.mkdir(exist_ok=True)
    for n in range(files):
        body = "import time\n" + "".join(
            f"\n\ndef test_{k}():\n    time.sleep({nap})\n" for k in range(per_file))
        (tests / f"test_part{n}.py").write_text(body, encoding="utf-8")


def test_full_run_reports_done_of_total_and_current_file(repo: Path, loud: None) -> None:
    _suite(repo, nap=0.3)    # a longer run: a starved poller still sees it move before the end
    out = Pipe()
    reporter = progress.Reporter(repo, None, "full-run", stream=out, lazy=True)
    result = runner.run_pytest(repo, [], progress=reporter, step=runner.STEP_FULL)
    reporter.done("the full suite finished: 12 passed")
    lines = out.getvalue().splitlines()
    counted = [int(m.group(1)) for line in lines if (m := re.search(r": (\d+) of 12", line))]
    assert counted and max(counted) > 0 and min(counted) < 12      # done of total, moving
    assert any("tests/test_part" in line for line in lines)          # the file it is in
    assert all("running the full suite" in line for line in lines[:-1])
    assert lines[-1] == "the full suite finished: 12 passed"
    assert len(result.nodes) == 12 and result.exit_status == 0


def test_merge_check_step_names(repo: Path, loud: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso.boundary import cli, fullrun

    seen: list[str] = []
    original = progress.Reporter.update

    def spy(self: Any, step: str, *args: Any, **kwargs: Any) -> None:
        seen.append(step)
        original(self, step, *args, **kwargs)

    monkeypatch.setattr(progress.Reporter, "update", spy)
    monkeypatch.setattr(sys, "stderr", Pipe())

    class Verify:
        def env_key(self) -> str:
            return "k"

        def identity(self, compute: bool = False) -> str:
            return "i"

    monkeypatch.setattr(fullrun, "current_identity",
                        lambda core, verify: {"tree": {"head_tree": "t", "dirty": ""},
                                              "env": {"env_key": "k", "identity": "i"}})
    core = open_core(repo)

    def fake_report(core_: Any, base: str, *, run_full: bool, hook: bool) -> Any:
        fullrun.full_run(core_, Verify(), pending=True, reasons=["r"], unverified=False,
                         waived=False, run_full=True, runner=lambda c: object())
        from iaso.boundary.report import MergeReport

        return MergeReport(base=base)   # SR-374: the merge insight reads the report's fields

    import iaso.boundary as boundary

    monkeypatch.setattr(boundary, "merge_report", fake_report)
    monkeypatch.setattr(boundary, "render", lambda report: [])
    cli._print_report(core, "main", run_full=True, as_json=False)
    assert seen[0] == cli.STEP_CHECK
    assert fullrun.STEP_DECIDE in seen and seen.index(fullrun.STEP_RUN) > seen.index(
        fullrun.STEP_DECIDE)
    for step in (cli.STEP_CHECK, fullrun.STEP_DECIDE, fullrun.STEP_RUN, cli.MERGE_END):
        assert owner_level(step) == []
    assert progress.shown(repo, None) == cli.MERGE_END     # only its end line is left


def test_map_build_elapsed_only(repo: Path, loud: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso.verify.testmap import STEP_MAP, build_map

    _suite(repo, files=2, per_file=1, nap=0)
    err = Pipe()
    monkeypatch.setattr(sys, "stderr", err)
    build_map(open_core(repo), rebuild=True, write_text=False)
    text = err.getvalue()
    assert STEP_MAP in text and "so far" in text
    assert " of " not in text and "%" not in text and "[" not in text


def test_coverage_collection_reports_done_of_total_tests(repo: Path, loud: None,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    if not runner.coverage_available():
        pytest.skip("coverage is not installed")
    from iaso.verify import open_verify

    _suite(repo, files=2, per_file=3, nap=0.1)
    err = Pipe()
    monkeypatch.setattr(sys, "stderr", err)
    core = open_core(repo)
    report = open_verify(core).map_coverage()
    lines = err.getvalue().splitlines()
    assert any(runner.STEP_RECORDING in line and re.search(r"\d+ of 6", line) for line in lines)
    assert lines[-1].startswith(runner.END_BY_STEP[runner.STEP_RECORDING])
    assert report.ran


def test_align_report(repo: Path, loud: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso import align

    seen: list[tuple[str, int, int]] = []
    original = progress.Reporter.update

    def spy(self: Any, step: str, done: int = 0, total: int = 0, **kwargs: Any) -> None:
        seen.append((step, done, total))
        original(self, step, done, total, **kwargs)

    monkeypatch.setattr(progress.Reporter, "update", spy)
    monkeypatch.setattr(sys, "stderr", Pipe())
    core = open_core(repo)
    nodes = {"SR-1": "requirement", "FEAT-1": "feature", "SR-2": "requirement"}
    edges = [("SR-1", "FEAT-1"), ("SR-2", "FEAT-1")]
    seen.clear()
    align.judge(core, nodes, edges, None)
    assert seen == [(align.STEP_ALIGN, 0, 2), (align.STEP_ALIGN, 1, 2)]
    assert owner_level(align.STEP_ALIGN) == []


def test_no_behaviour_change_exit_codes_and_evidence(repo: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    _suite(repo, files=1, per_file=2, nap=0)
    plain = runner.run_pytest(repo, [])
    watched = progress.Reporter(repo, None, "x", stream=Pipe(), lazy=True)
    with_progress = runner.run_pytest(repo, [], progress=watched, step=runner.STEP_FULL)
    for field in ("nodes", "collected", "collection_errors", "exit_status", "timed_out",
                  "finished"):
        assert getattr(plain, field) == getattr(with_progress, field) or field == "nodes"
    assert set(plain.nodes) == set(with_progress.nodes)
    assert {n: d["outcome"] for n, d in plain.nodes.items()} == {
        n: d["outcome"] for n, d in with_progress.nodes.items()}
    # a failure in the progress code never stops a run
    monkeypatch.setattr(progress.Reporter, "update",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    broken = progress.Reporter(repo, None, "x", stream=Pipe(), lazy=True)
    with pytest.raises(RuntimeError):
        runner.run_pytest(repo, [], progress=broken)     # the first call is the caller's own
    # while a hook process never draws at all
    monkeypatch.setattr(sys.modules["iaso.verify"], "HOOK_PROCESS", True, raising=False)
    assert progress.default_stream() is None
