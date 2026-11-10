"""A panel started by a mid-session plugin reload takes over a silent registration (SR-350):
a hello replaces a registration whose heartbeat is older than a minute, keeping the older
digests as ``earlier``; while the heartbeat is fresh it is still refused."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from mod.helpers import DIGEST, OTHER_KEY, mod_json, run_mod
from iaso.mod import session as mod_session

pytestmark = pytest.mark.sr("SR-350")

NEW_DIGEST = mod_session.key_digest(OTHER_KEY)


def _hello(monkeypatch, capsys, root: Path, digest: str) -> int:
    return run_mod(monkeypatch, capsys, root, "hello", stdin={"key_digest": digest})[0]


def _age(root: Path, seconds: int) -> None:
    held = json.loads(mod_json(root).read_text(encoding="utf-8"))
    held["heartbeat"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds))
    mod_json(root).write_text(json.dumps(held), encoding="utf-8")


def test_a_silent_registration_is_replaced(repo: Path, monkeypatch, capsys) -> None:
    assert _hello(monkeypatch, capsys, repo, DIGEST) == 0
    _age(repo, 120)
    assert _hello(monkeypatch, capsys, repo, NEW_DIGEST) == 0
    held = json.loads(mod_json(repo).read_text(encoding="utf-8"))
    assert held["key_digest"] == NEW_DIGEST and held["earlier"] == [DIGEST]


def test_a_fresh_registration_is_still_refused(repo: Path, monkeypatch, capsys) -> None:
    assert _hello(monkeypatch, capsys, repo, DIGEST) == 0
    _age(repo, 30)
    assert _hello(monkeypatch, capsys, repo, NEW_DIGEST) == 3
