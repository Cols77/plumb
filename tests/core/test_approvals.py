"""K5: owner approvals and the self-approval guard (spec 5.6). The agent-run prose relay is
gone (SR-101 EX-9; tests/understand/test_no_prose_relay.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import approvals, cli
from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-005")

SR1 = "---\nid: SR-001\ntitle: Links pin both ends\nstatement: s1\n---\n"
SR2 = "---\nid: SR-002\ntitle: Hashes ignore format\nstatement: s2\n---\n"
INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\n---\n"


@pytest.fixture
def setup(repo: Path, write_record) -> Path:
    for text in (SR1, SR2, INT):
        write_record(repo, text)
    return repo


def log_prompt(root: Path, text: str, at: str = "2026-10-06T03:00:00Z",
               session: str = "s1") -> str:
    digest = approvals.prompt_digest(text)
    prompts = root / ".plumb" / "session" / "prompts.jsonl"
    prompts.parent.mkdir(parents=True, exist_ok=True)
    with prompts.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"digest": digest, "session": session, "at": at,
                                 "text": text, "via": "hook"}) + "\n")
    return digest


def state_set(root: Path, ids: list[str], at: str = "2026-10-06T02:59:00Z") -> None:
    index = open_core(root).index()
    stated = root / ".plumb" / "session" / "stated.json"
    stated.parent.mkdir(parents=True, exist_ok=True)
    stated.write_text(json.dumps({"at": at, "session": "s1", "reply_after_prompt": None,
                                  "records": [{"id": i, "hash": index[i].hash} for i in ids]}),
                      encoding="utf-8")


def _confirmation(root: Path, record_id: str) -> str:
    return open_core(root).status([record_id])[record_id].confirmation


def test_approve_refused_under_marker(setup: Path, monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    with pytest.raises(approvals.Refused):
        approvals.approve(open_core(setup), ["SR-001"])
    with pytest.raises(approvals.Refused):
        approvals.revoke(open_core(setup), ["SR-001"])
    root = ["--root", str(setup)]
    assert cli.main(["approve", "SR-001", *root]) == 3
    assert cli.main(["approve", "--proposed", *root]) == 3
    assert cli.main(["revoke", "SR-001", *root]) == 3
    assert "refused" in capsys.readouterr().err
    assert list(open_core(setup).log_read("events")) == []


def test_approve_proposed_pins_all_listed(setup: Path,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    root = ["--root", str(setup)]
    assert cli.main(["approve", "--proposed", *root]) == 0  # y/N answered in the terminal
    out = capsys.readouterr().out
    assert "SR-001" in out and "INT-001" in out
    entries = list(open_core(setup).log_read("events", kinds=["approval"]))
    assert len(entries) == 1
    pinned = {r["id"]: r["hash"] for r in entries[0].payload["records"]}
    index = open_core(setup).index()
    assert pinned == {i: index[i].hash for i in ("INT-001", "SR-001", "SR-002")}
    assert entries[0].payload["by"] == "owner" and entries[0].marker == "none"
    assert all(_confirmation(setup, i) == "confirmed" for i in pinned)
    assert cli.main(["approve", "SR-404", *root]) == 1


@pytest.mark.sr("SR-028")
def test_approval_records_the_ends_a_requirement_owns(setup: Path) -> None:
    from plumb.contracts import Target

    (setup / "src").mkdir()
    (setup / "src" / "a.py").write_text("x = 1\n", "utf-8")
    open_core(setup).add_link("SR-001", "implemented_by", Target(path="src/a.py"))
    entry = approvals.approve(open_core(setup), ["SR-001", "INT-001"])
    items = {r["id"]: r for r in entry.payload["records"]}
    assert items["SR-001"]["ends"] == ["implemented_by src/a.py"]
    assert "ends" not in items["INT-001"]


# -- an ok confirms only what the owner's words affirm (R2; concept 6.6) --------------------

MIXED = "SR-001 is ok but INT-001 is wrong, use floats"

