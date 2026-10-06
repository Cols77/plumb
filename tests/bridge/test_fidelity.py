"""BRIDGE B3: fidelity packets for the host agent, ``plumb judge`` and ``unjudged`` (8.3)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from plumb import cli
from plumb.api import open_core
from plumb.contracts import NodeEvidence
from plumb.judgment.fidelity import MAX_END_CHARS, build_packet, judge, unjudged

pytestmark = pytest.mark.sr("SR-022")

SR_001 = """---
id: SR-001
title: Adds one
statement: f adds one to its argument.
examples:
- id: EX-1
  given: x is 1
  when: f(x) is called
  then: it returns 2
links:
- kind: implemented_by
  path: src/mod.py
- kind: verified_by
  path: tests/test_mod.py
---
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True, encoding="utf-8").stdout


@pytest.fixture
def fid(repo: Path, write_record) -> Path:
    write_record(repo, SR_001)
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_mod.py").write_text(
        "from mod import f\n\ndef test_f():\n    assert f(1) == 2\n", encoding="utf-8")
    return repo


class _Verify:
    def tests_for(self, refs):
        return {r: ("tests/test_mod.py::test_f",) for r in refs}

    def evidence(self, nodes):
        return {n: NodeEvidence(node_id=n, state="fresh-pass") for n in nodes}


def test_packet_contains_statement_examples_ends_evidence(fid: Path) -> None:
    core = open_core(fid)
    packet = build_packet(core, _Verify(), "SR-001")
    record = core.index()["SR-001"]
    assert packet.requirement == "SR-001"
    assert packet.requirement_hash == record.hash
    assert packet.statement == "f adds one to its argument."
    assert [e.id for e in packet.examples] == ["EX-1"]
    kinds = {e["kind"]: e for e in packet.ends}
    assert kinds["implemented_by"]["path"] == "src/mod.py"
    assert "return x + 1" in kinds["implemented_by"]["content"]
    assert kinds["implemented_by"]["hash"].startswith("sha256:")
    assert kinds["implemented_by"]["truncated"] is False
    assert list(packet.evidence) == [{"node_id": "tests/test_mod.py::test_f",
                                      "state": "fresh-pass"}]
    assert packet.fingerprint.startswith("sha256:")
    assert build_packet(core, None, "SR-001").evidence == ()


def test_packet_truncates_deterministically(fid: Path) -> None:
    (fid / "src" / "mod.py").write_text("x = 1\n" * 2000, encoding="utf-8")
    core = open_core(fid)
    a = build_packet(core, None, "SR-001")
    b = build_packet(open_core(fid), None, "SR-001")
    end = next(e for e in a.ends if e["kind"] == "implemented_by")
    assert end["truncated"] is True
    assert len(end["content"]) == MAX_END_CHARS
    assert a == b


def test_packet_rejects_non_requirement(fid: Path) -> None:
    with pytest.raises(KeyError):
        build_packet(open_core(fid), None, "SR-404")


def test_judge_appends_event_with_hashes(fid: Path) -> None:
    core = open_core(fid)
    entry = judge(core, "SR-001", "fits", "matches EX-1")
    payload = entry.payload
    assert entry.kind == "judgment"
    assert payload["subject"] == "SR-001"
    assert payload["action"] == "fidelity"
    assert payload["verdict"] == "fits"
    assert payload["backend"] == "host-agent"
    assert payload["requirement_hash"] == core.index()["SR-001"].hash
    assert set(payload["end_hashes"]) == {"SR-001#0", "SR-001#1"}
    assert payload["note"] == "matches EX-1"
    with pytest.raises(ValueError):
        judge(core, "SR-001", "great", "")


def test_unjudged_after_end_change(fid: Path) -> None:
    core = open_core(fid)
    assert unjudged(core) == ("SR-001",)
    judge(core, "SR-001", "fits", "ok")
    assert unjudged(open_core(fid)) == ()
    (fid / "src" / "mod.py").write_text("def f(x):\n    return x + 2\n", encoding="utf-8")
    assert unjudged(open_core(fid)) == ("SR-001",)
    judge(open_core(fid), "SR-001", "drifts", "returns x + 2")
    assert unjudged(open_core(fid), ["SR-001"]) == ("SR-001",)  # drifts stays a signal
    judge(open_core(fid), "SR-001", "unsure", "unclear")
    assert unjudged(open_core(fid), ["SR-001"]) == ("SR-001",)
    assert unjudged(open_core(fid), ["INT-001"]) == ()


def test_judgment_never_confirms_or_freshens(fid: Path) -> None:
    core = open_core(fid)
    before = core.status(["SR-001"])["SR-001"].confirmation
    judge(core, "SR-001", "fits", "ok")
    core = open_core(fid)
    assert core.status(["SR-001"])["SR-001"].confirmation == before == "proposed"
    assert list(core.log_read("evidence")) == []
    kinds = [e.kind for e in core.log_read("events")]
    assert kinds == ["judgment"]


def test_merge_lists_unjudged_fidelity(fid: Path, capsys) -> None:
    _git(fid, "add", "-A")
    _git(fid, "commit", "-q", "-m", "base")
    base = _git(fid, "rev-parse", "HEAD").strip()
    (fid / "src" / "mod.py").write_text("def f(x):\n    return x + 1  # same\n",
                                        encoding="utf-8")
    # 5: the test file has no full run yet, so the verification hold comes first (sp3 5);
    # the fidelity list is advisory and never changes the exit
    assert cli.main(["validate", "--merge", base, "--root", str(fid)]) == 5
    out = capsys.readouterr().out
    assert "plumb fidelity SR-001" in out


def test_fidelity_and_judge_cli(fid: Path, capsys) -> None:
    assert cli.main(["fidelity", "SR-001", "--root", str(fid)]) == 0
    out = capsys.readouterr().out
    assert "f adds one to its argument." in out
    assert "src/mod.py" in out
    assert "plumb judge SR-001 --verdict fits|drifts|unsure" in out
    assert cli.main(["fidelity", "SR-001", "--json", "--root", str(fid)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["requirement"] == "SR-001"
    assert cli.main(["judge", "SR-001", "--verdict", "fits", "--note", "ok",
                     "--root", str(fid)]) == 0
    assert "confirms nothing" in capsys.readouterr().out
    assert cli.main(["judge", "SR-001", "--verdict", "bad", "--note", "x",
                     "--root", str(fid)]) == 2
    assert cli.main(["fidelity", "SR-404", "--root", str(fid)]) == 1
