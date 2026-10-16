"""SR-186: understand.judge_model is the model for verdicts and for what measures or guards them
(the evaluation run, the calibration fingerprint that suspends settling); understand.model stays
the model that reads the owner's words. The dispatcher is a stub that records the model asked for."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from understand.test_judge_cascade import calibrate_to, configure, world  # noqa: F401

from plumb.api import open_core
from plumb.contracts import DispatchError

pytestmark = pytest.mark.sr("SR-242")

SETTINGS = "understand:\n  model: haiku\n  judge_model: sonnet\n  dispatch: claude-code\n"


class Recorder:
    def __init__(self, model: str | None) -> None:
        self.model = model

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise DispatchError("model", "stub")


def test_ex1_the_evaluation_run_is_judged_by_the_judge_model_and_logs_it(
        world: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # noqa: F811
    configure(world, SETTINGS)
    asked: dict[str, str | None] = {}
    seen: list[str | None] = []

    def configured(core: Any, *, model: str | None = None) -> Recorder:
        seen.append(model)
        return Recorder(model)

    monkeypatch.setattr("plumb.understand.dispatch.configured", configured)
    from plumb.understand import evalrun

    assert evalrun.run("eval", ["--root", str(world)]) == 0
    (run,) = [e for e in open_core(world).events() if e.kind == "eval-run"]
    assert run.payload["model"] == "sonnet"
    assert seen.count("sonnet") == 1 and seen.count(None) == len(seen) - 1 and asked == {}


def test_ex2_a_logged_calibration_fingerprint_names_the_judge_model(world: Path) -> None:  # noqa: F811
    from plumb.capture.calibrate import fingerprint

    assert fingerprint(configure(world, SETTINGS))["model"] == "sonnet"


def test_ex3_clarify_and_read_jobs_keep_the_understand_model(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    core = configure(world, SETTINGS)
    monkeypatch.delenv("PLUMB_FAKE_DISPATCH", raising=False)
    from plumb.understand import dispatch

    assert dispatch.configured(core).model == "haiku"       # what the worker asks for a clarify or read job
    assert dispatch.configured(core, model=core.config.understand.judge_model).model == "sonnet"
