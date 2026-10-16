"""SR-182: calibration from the log takes only JEV's verdicts. A judge model's confidence never
sets JEV's threshold, and an old verdict with no marker is not taken as JEV's (the owner's
choice, 2026-10-15: "JEV's only")."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from capture_helpers import JevStub, use_jev
from jev_fixtures import owner_decisions

from plumb.api import open_core
from plumb.capture.calibrate import calibrate, labelled_set, logged_scores

pytestmark = pytest.mark.sr("SR-242")


def log_verdict(core: Any, record: str, digest: str, score: float, **marks: Any) -> None:
    core.log_append("events", "verdict", {"id": record, "hash": digest, "verdict": "supported",
                                          "score": score, "model": "haiku", **marks})


def one_labelled(repo: Path, write_record, monkeypatch) -> tuple[JevStub, Any, Any]:
    stub = JevStub()
    use_jev(repo, stub, monkeypatch)
    owner_decisions(repo, write_record)
    core = open_core(repo)
    item = next(i for i in labelled_set(core) if not i.source.startswith("gen"))
    return stub, core, item


def test_a_judge_models_logged_confidence_never_calibrates_jev(
        repo: Path, write_record, monkeypatch) -> None:
    stub, core, item = one_labelled(repo, write_record, monkeypatch)
    log_verdict(core, item.record, item.hash, 0.99)                        # no marker: old
    log_verdict(core, item.record, item.hash, 0.99, by="model", judge="claude:haiku")
    assert logged_scores(core) == ({}, "")
    entry, _ = calibrate(open_core(repo))                                  # scored through JEV
    assert entry.payload["backend"] == "jev" and entry.payload.get("source") != "logged"
    stub.close()


def test_jevs_logged_probabilities_calibrate_without_a_call(
        repo: Path, write_record, monkeypatch) -> None:
    stub, core, item = one_labelled(repo, write_record, monkeypatch)
    log_verdict(core, item.record, item.hash, 0.9, by="jev", judge="jev:typesafe/jev-1",
                model="typesafe/jev-1")
    assert logged_scores(core) == ({(item.record, item.hash): 0.9}, "typesafe/jev-1")
    asked = len(stub.requests)
    entry, _ = calibrate(open_core(repo))
    assert entry.payload["source"] == "logged"
    assert entry.payload["backend"] == "jev"
    assert entry.payload["model_version"] == "typesafe/jev-1"
    assert len(stub.requests) == asked                                     # JEV was not called
    stub.close()
