"""DEC-116, DEC-232: a shared entry keeps the outcome; the owner's text is a local entry."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb import log, words
from plumb.api import open_core
from plumb.normalize import sha256_text

from .gitrepo import commit_all, make_repo, run_git

ROOT = Path(__file__).resolve().parents[2]

CASES = [
    ("approval", {"records": [{"id": "SR-001", "hash": "sha256:x"}], "by": "agent-relayed",
                  "prompt_digest": "sha256:p", "quote": "yes, that is right",
                  "note": "my note"}, ("quote", "note")),
    ("revocation", {"records": [{"id": "SR-001", "hash": "sha256:x"}], "by": "owner",
                    "quote": "no, undo it", "note": "wrong", "reason": "because"},
     ("quote", "note", "reason")),
    ("waiver", {"diff_digest": "sha256:d", "reason": "docs only", "by": "owner"},
     ("reason",)),
    ("conflict-resolution", {"ic": "IC-1", "take": "ours", "by": "agent-relayed",
                             "quote": "keep mine", "prompt": "sha256:p"},
     ("quote",)),
    ("escalation-declined", {"intent": "INT-021", "by": "agent-relayed",
                             "prompt_digest": "sha256:p", "quote": "no up-front spec for this"},
     ("quote",)),
    ("config", {"auto_approve": {"enabled": True}, "by": "owner", "via": "typed",
                "prompt_digest": "sha256:p", "quote": "/plumb auto-approve on"},
     ("quote",)),
]


def _scratch(tmp_path: Path) -> Path:
    root = make_repo(tmp_path / "r")
    (root / ".gitignore").write_text(
        (ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    commit_all(root, "ignore")
    return root


@pytest.mark.parametrize("kind,payload,fields", CASES)
def test_the_committed_entry_keeps_the_outcome_and_digests_only(
        tmp_path: Path, kind: str, payload: dict, fields: tuple[str, ...]) -> None:
    root = _scratch(tmp_path)
    core = open_core(root)
    entry = core.log_append("events", kind, payload)
    for field in fields:
        assert field not in entry.payload
        assert entry.payload[f"{field}_digest"]
    for key, value in payload.items():
        if key not in fields:
            assert entry.payload[key] == value
    on_disk = "\n".join(p.read_text(encoding="utf-8")
                        for p in (root / ".plumb" / "log" / kind).glob("*.json"))
    for field in fields:
        text = payload[field]
        if isinstance(text, str):
            assert text not in on_disk
    status = run_git(root, "status", "--porcelain", "-uall").stdout
    assert f".plumb/log/{kind}/" in status
    assert ".plumb/log/owner-words/" not in status


@pytest.mark.parametrize("kind,payload,fields", CASES)
def test_a_reader_joins_the_words_by_digest(
        tmp_path: Path, kind: str, payload: dict, fields: tuple[str, ...]) -> None:
    root = _scratch(tmp_path)
    core = open_core(root)
    entry = core.log_append("events", kind, payload)
    joined = words.joined(core, entry)
    for field in fields:
        assert joined[field] == payload[field]
    assert "owner-words" in log.OWNER_WORDS_KINDS and "owner-words" in log.LOCAL_KINDS


def test_a_clone_without_the_words_reads_the_outcome_and_asks_for_nothing(
        tmp_path: Path) -> None:
    root = _scratch(tmp_path)
    core = open_core(root)
    entry = core.log_append("events", "approval", {
        "records": [{"id": "SR-001", "hash": "sha256:x"}], "by": "agent-relayed",
        "prompt_digest": "sha256:p", "quote": "ok", "quote_digest": sha256_text("ok")})
    for p in (root / ".plumb" / "log" / "owner-words").glob("*.json"):
        p.unlink()
    again = open_core(root)
    (shared,) = [e for e in again.events() if e.kind == "approval"]
    assert shared.digest == entry.digest
    joined = words.joined(again, shared)
    assert "quote" not in joined and joined["quote_digest"] == sha256_text("ok")


def test_the_digest_of_a_quote_stays_the_digest_of_its_text(tmp_path: Path) -> None:
    core = open_core(_scratch(tmp_path))
    entry = core.log_append("events", "approval", {
        "records": [], "by": "agent-relayed", "prompt_digest": "sha256:p",
        "quote": "all good"})
    assert entry.payload["quote_digest"] == sha256_text("all good")
