"""SP8 3.2 item 3: owner-words approvals need the worker's token."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import log
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-006")

TOKEN = "a1" * 16


@pytest.fixture
def paths(tmp_path: Path) -> PlumbPaths:
    p = PlumbPaths(tmp_path)
    p.log_dir.mkdir(parents=True)
    lock = p.session_dir("s1") / "worker.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": 1, "heartbeat": 0, "token": TOKEN}), encoding="utf-8")
    return p


def _approval(by: str) -> dict:
    return {"by": by, "session": "s1", "records": [{"id": "SR-001", "hash": "sha256:0"}]}


def test_owner_words_refused_without_token(paths: PlumbPaths,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUMB_WORKER", raising=False)
    with pytest.raises(log.LogError):
        log.append(paths, "events", "approval", _approval("owner-words"))
    assert log.worker_token_problem(paths.root, "s1", "owner-words")


def test_accepted_with_matching_token(paths: PlumbPaths,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUMB_WORKER", TOKEN)
    assert log.worker_token_problem(paths.root, "s1", "owner-words") is None
    entry = log.append(paths, "events", "approval", _approval("owner-words"))
    assert entry.payload["by"] == "owner-words"


def test_other_by_values_unchanged(paths: PlumbPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUMB_WORKER", raising=False)
    for by in ("owner", "agent-relayed", "import", "auto-jev"):
        assert log.worker_token_problem(paths.root, "s1", by) is None
        log.append(paths, "events", "approval", _approval(by))
    log.append(paths, "events", "revocation", {"by": "undone", "records": []})
