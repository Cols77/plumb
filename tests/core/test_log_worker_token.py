"""SP8 3.2 item 3: owner-words approvals need the worker's token."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from iaso import log
from iaso.paths import IasoPaths

pytestmark = pytest.mark.sr("SR-232")

TOKEN = "a1" * 16


@pytest.fixture
def paths(tmp_path: Path) -> IasoPaths:
    p = IasoPaths(tmp_path)
    p.log_dir.mkdir(parents=True)
    lock = p.session_dir("s1") / "worker.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": 1, "heartbeat": 0, "token": TOKEN}), encoding="utf-8")
    return p


def _approval(by: str) -> dict:
    return {"by": by, "session": "s1", "records": [{"id": "SR-001", "hash": "sha256:0"}]}


def test_owner_words_refused_without_token(paths: IasoPaths,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IASO_WORKER", raising=False)
    with pytest.raises(log.LogError):
        log.append(paths, "events", "approval", _approval("owner-words"))
    assert log.worker_token_problem(paths.root, "s1", "owner-words")


def test_accepted_with_matching_token(paths: IasoPaths,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IASO_WORKER", TOKEN)
    assert log.worker_token_problem(paths.root, "s1", "owner-words") is None
    entry = log.append(paths, "events", "approval", _approval("owner-words"))
    assert entry.payload["by"] == "owner-words"


def test_other_by_values_unchanged(paths: IasoPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IASO_WORKER", raising=False)
    for by in ("owner", "agent-relayed", "import"):
        assert log.worker_token_problem(paths.root, "s1", by) is None
        log.append(paths, "events", "approval", _approval(by))
    log.append(paths, "events", "revocation", {"by": "undone", "records": []})
