"""K7: relevant records and the session brief (spec 6.1, 6.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb import approvals, cli
from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-278")


def _sr(n: int, title: str, statement: str, extra: str = "") -> str:
    return (f"---\nid: SR-{n:03d}\ntitle: {title}\nfeature: FEAT-001\nstatement: {statement}\n"
            f"{extra}---\n")


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    write_record(repo, "---\nid: INT-001\ntitle: Grounded vibe coding\nquote: make vibe coding "
                 "grounded on the projects artifacts\n---\n")
    write_record(repo, "---\nid: FEAT-001\ntitle: Records and integrity\nrequirements: "
                 "[SR-001, SR-002, SR-003]\n---\n")
    write_record(repo, _sr(1, "Links pin both ends", "Every link pins the hash of its ends."))
    write_record(repo, _sr(2, "Status line", "The status line reads a snapshot."))
    write_record(repo, _sr(3, "Old status line", "The status line recomputes state.",
                           "links:\n  - {kind: derives_from, to: INT-001}\n"))
    write_record(repo, "---\nid: SR-004\ntitle: New status line\nstatement: status line\n"
                 "links:\n  - {kind: supersedes, to: SR-003}\n---\n")
    write_record(repo, "---\nid: NC-0001\ntitle: Hook too slow\nstatus: open\n---\n")
    write_record(repo, "---\nid: DEC-001\ntitle: Deny rules instead of a guard hook\n"
                 "question: q\nchosen: deny rules\nmatters: true\n---\n")
    return repo


def test_relevant_ranks_named_ids_first(records: Path) -> None:
    ranked = open_core(records).relevant("fix the status line hash links, see SR-001", limit=5)
    ids = [i for i, _ in ranked]
    assert ids[0] == "SR-001"
    assert "SR-002" in ids
    assert len(ids) <= 5
    assert all(score > 0 for _, score in ranked)
    assert open_core(records).relevant("zzz qqq") == []


def test_superseded_records_excluded_from_brief_and_relevant(records: Path) -> None:
    core = open_core(records)
    ids = [i for i, _ in core.relevant("status line recomputes state", limit=10)]
    assert "SR-003" not in ids and "SR-004" in ids
    assert "SR-003" not in "\n".join(core.brief_lines(40))
    assert "SR-003" in [i for i, _ in core.relevant("SR-003 status", limit=10)]  # named


def test_brief_content(records: Path) -> None:
    open_core(records).add_link("SR-001", "derives_from", Target(record="INT-001"))
    approvals.approve(open_core(records), ["INT-001"])
    lines = open_core(records).brief_lines(30)
    text = "\n".join(lines)
    assert lines[0].startswith("plumb brief")
    assert "FEAT-001 Records and integrity (3 SR)" in text
    assert "INT-001" in text and "make vibe coding grounded" in text
    assert "waiting on a judge:" in text and "your confirmation" not in text
    assert "DEC-001" in text
    assert "drift:" in text
    assert "NC-0001" in text


def test_brief_respects_line_cap(repo: Path, write_record) -> None:
    for n in range(1, 61):
        write_record(repo, f"---\nid: INT-{n:03d}\ntitle: Intent number {n}\nquote: words {n}\n"
                     "---\n")
    for n in range(1, 31):
        write_record(repo, f"---\nid: NC-{n:04d}\ntitle: Problem {n}\nstatus: open\n---\n")
    core = open_core(repo)
    lines = core.brief_lines(30)
    assert len(lines) <= 30
    assert any("+" in line and "more (plumb brief --all)" in line for line in lines)
    assert len(core.brief_lines(100)) <= 40  # hard cap
    assert len(core.brief_lines(10)) <= 10


def test_brief_and_status_commands(records: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["brief", "--root", str(records)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("plumb brief") and len(out.splitlines()) <= 40
    assert cli.main(["brief", "--all", "--root", str(records)]) == 0
    assert cli.main(["status", "--root", str(records)]) == 0
    out = capsys.readouterr().out
    assert "requirements" in out and "awaiting" in out


def test_brief_intent_items_are_indented(records: Path) -> None:
    lines = open_core(records).brief_lines(30)
    assert any(line.startswith("  INT-001 Grounded vibe coding") for line in lines)
