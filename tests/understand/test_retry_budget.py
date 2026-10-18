"""SR-325 EX-5, DEC-255: a judge job that failed is retried with a larger budget than the last
time, and only the third failure in a row is a debug case."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.understand import dispatch, files, worker

pytestmark = pytest.mark.sr("SR-325")


def test_each_retry_gets_a_larger_budget(repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "x")        # the claude-code dispatcher
    core = open_core(repo)
    base = core.config.understand.timeout_s
    assert dispatch.configured(core).timeout_s == base
    token = dispatch.budget_scale.set(3)
    try:
        assert dispatch.configured(core).timeout_s == 3 * base
    finally:
        dispatch.budget_scale.reset(token)
    assert dispatch.configured(core).timeout_s == base


def test_the_scale_follows_the_failures_in_a_row(repo: Path) -> None:
    assert worker.budget_scale_for(repo, "s1") == 1
    path = files.failures_path(repo, "s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"v": 1, "consecutive": 2, "last": {}}), encoding="utf-8")
    assert worker.budget_scale_for(repo, "s1") == 3
