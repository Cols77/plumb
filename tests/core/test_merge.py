"""K6: the merge boundary, ``plumb validate --merge <base>`` (spec 5.11, R1, R2)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from plumb import approvals, cli
from plumb.api import open_core
from plumb.contracts import Target
from plumb.merge import merge_check

pytestmark = pytest.mark.sr("SR-008")

INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\nreadback: Ground the work.\n---\n"
SR1 = """---
id: SR-001
title: Links pin both ends
statement: Both ends are pinned.
examples:
  - {id: EX-1, given: a link, when: an end moves, then: it is stale}
---
"""
SR2 = "---\nid: SR-002\ntitle: Other\nstatement: Something else.\n---\n"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout


def _commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


@pytest.fixture
def base(repo: Path, write_record) -> tuple[Path, str]:
    for text in (INT, SR1, SR2):
        write_record(repo, text)
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    return repo, _commit(repo, "base")


def _check(root: Path, sha: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = merge_check(open_core(root), sha, as_json=False)
    return code, capsys.readouterr().out


def test_merge_refuses_unconfirmed_touched_requirement(base, capsys) -> None:
    root, sha = base
    path = root / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Both ends", "Each end"),
                    encoding="utf-8")
    _commit(root, "edit SR-001")
    code, out = _check(root, sha, capsys)
    assert code == 4
    assert "SR-001" in out and "INT-001" in out and "SR-002" not in out
    assert "plumb approve SR-001 INT-001" in out
    assert "given a link" in out


def test_merge_touch_via_implemented_by_end(base, capsys) -> None:
    root, sha = base
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")  # uncommitted
    code, out = _check(root, sha, capsys)
    assert code == 4
    assert "touched requirements: SR-001" in out


def test_merge_touch_via_sr_trailer(base, capsys) -> None:
    root, sha = base
    (root / "notes.txt").write_text("n\n", encoding="utf-8")
    _commit(root, "notes\n\nSR: SR-002")
    code, out = _check(root, sha, capsys)
    assert code == 4
    assert "touched requirements: SR-002" in out


def test_merge_passes_after_approval(base, capsys) -> None:
    root, sha = base
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    approvals.approve(open_core(root), ["SR-001", "INT-001"])
    code, out = _check(root, sha, capsys)
    assert code == 0, out
    assert cli.main(["validate", "--merge", sha, "--root", str(root)]) == 0
    assert cli.main(["validate", "--merge", "no-such-ref", "--root", str(root)]) == 2


def test_merge_with_nothing_touched_passes(base, capsys) -> None:
    root, sha = base
    code, out = _check(root, sha, capsys)
    assert code == 0
    assert "touched requirements: none" in out


def test_merge_lists_approvals_in_range_with_relayed_marked(base, capsys) -> None:
    root, sha = base
    approvals.approve(open_core(root), ["INT-001"])
    prompts = root / ".plumb" / "session" / "prompts.jsonl"
    prompts.parent.mkdir(parents=True, exist_ok=True)
    text = "SR-001 looks good, approved"
    digest = approvals.prompt_digest(text)
    prompts.write_text(json.dumps({"digest": digest, "session": "s", "at": "t",
                                   "text": text}) + "\n", encoding="utf-8")
    approvals.relay(open_core(root), ["SR-001"], prompt=digest, quote="SR-001 looks good, "
                    "approved")
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    code, out = _check(root, sha, capsys)
    assert code == 0, out
    section = out[out.index("approvals in range"):]
    assert "owner" in section and "INT-001" in section
    assert "agent-relayed" in section and digest[:19] in section
    assert "SR-001 looks good, approved" in section
    data_code = merge_check(open_core(root), sha, as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert data_code == 0
    assert [a["by"] for a in data["approvals"]] == ["owner", "agent-relayed"]


def test_merge_requires_deciding_matters_dec(base, capsys, write_record) -> None:
    root, sha = base
    write_record(root, "---\nid: DEC-001\ntitle: Deny rules\nquestion: q\nchosen: a\n"
                 "matters: true\n---\n")
    open_core(root).add_link("DEC-001", "decides", Target(record="SR-001"))
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    approvals.approve(open_core(root), ["SR-001", "INT-001"])
    code, out = _check(root, sha, capsys)
    assert code == 4 and "DEC-001" in out
    approvals.approve(open_core(root), ["DEC-001"])
    assert _check(root, sha, capsys)[0] == 0


def test_merge_detects_rewritten_log_line(base, capsys) -> None:
    root, _ = base
    approvals.approve(open_core(root), ["INT-001"])
    sha = _commit(root, "approval")
    events = root / ".plumb" / "log" / "events.jsonl"
    events.write_text(events.read_text(encoding="utf-8").replace("INT-001", "SR-002"),
                      encoding="utf-8")
    code, out = _check(root, sha, capsys)
    assert code == 1
    assert "log integrity" in out and "events.jsonl" in out


def test_merge_reports_fidelity_and_verification_unavailable(base, capsys, monkeypatch) -> None:
    root, sha = base
    monkeypatch.setitem(sys.modules, "plumb.judgment.fidelity", None)
    monkeypatch.setitem(sys.modules, "plumb.verify", None)
    _, out = _check(root, sha, capsys)
    assert "fidelity: unavailable" in out
    assert "verification: unavailable" in out


def test_validate_merge_json_is_one_document(base, capsys) -> None:
    root, sha = base
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    assert cli.main(["validate", "--merge", sha, "--json", "--root", str(root)]) == 4
    data = json.loads(capsys.readouterr().out)
    assert data["merge"]["awaiting"][0]["id"] == "SR-001"
    assert data["validate"]["errors"] == []


def test_merge_log_integrity_reads_merge_base_not_base_tip(base, capsys) -> None:
    root, _ = base
    git(root, "branch", "trunk")
    git(root, "checkout", "-q", "-b", "feat")
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    _commit(root, "feat change")
    git(root, "checkout", "-q", "trunk")
    approvals.approve(open_core(root), ["SR-002"])  # main receives a log entry meanwhile
    _commit(root, "approval on trunk")
    git(root, "checkout", "-q", "feat")
    code, out = _check(root, "trunk", capsys)
    assert "log integrity: ok" in out, out
    assert code == 4  # SR-001 touched and unconfirmed, but no false tamper alarm
    assert "SR-002" not in out[out.index("approvals in range"):]


def test_merge_log_integrity_still_catches_edit_of_merge_base_line(base, capsys) -> None:
    root, _ = base
    approvals.approve(open_core(root), ["INT-001"])
    _commit(root, "approval")
    git(root, "branch", "trunk")
    git(root, "checkout", "-q", "-b", "feat")
    events = root / ".plumb" / "log" / "events.jsonl"
    events.write_text(events.read_text(encoding="utf-8").replace("INT-001", "SR-002"),
                      encoding="utf-8")
    _commit(root, "tamper")
    git(root, "checkout", "-q", "trunk")
    (root / "notes.txt").write_text("n\n", encoding="utf-8")
    _commit(root, "trunk moves on")
    git(root, "checkout", "-q", "feat")
    code, out = _check(root, "trunk", capsys)
    assert code == 1
    assert "log integrity: FAILED" in out
