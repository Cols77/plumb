"""A4: the brief, delta and status-card wording of overlaps (SR-078)."""

from __future__ import annotations

from pathlib import Path

import pytest

from awareness.gitrepo import add_worktree, commit_all, make_repo, requirement
from plumb import awareness
from plumb.api import open_core
from plumb.awareness import publish as pub
from plumb.present.render import status_card

pytestmark = pytest.mark.sr("SR-258")


def _many(tmp_path: Path, n: int) -> Path:
    main = make_repo(tmp_path / "main")
    for i in range(1, n + 1):
        requirement(main, f"SR-0{i:02d}", f"thing {i}")
    commit_all(main, "records")
    other = add_worktree(main, tmp_path / "wt-x", "feat-x")
    changed = []
    for i in range(1, n + 1):
        for root in (main, other):
            requirement(root, f"SR-0{i:02d}", f"thing {i}", f"{root.name} version")
        changed.append(f".plumb/requirements/SR-0{i:02d}.md")
    pub.publish(open_core(other), changed)
    pub.publish(open_core(main), changed)
    return main


def test_brief_cap_and_more_line(tmp_path: Path) -> None:
    main = _many(tmp_path, 5)
    lines = awareness.brief_lines(open_core(main))
    assert len(lines) == 4
    assert lines[:3] == [f'plumb: SR-0{i:02d} "thing {i}" is also being changed on branch '
                         "feat-x" for i in (1, 2, 3)]
    assert lines[3] == "plumb: +2 more also being changed elsewhere (/plumb status)"


def test_wording_matches_spec(tmp_path: Path) -> None:
    """sp6 9.4: plumb: SR-005 "relay checks" is also being changed on branch feat-x."""
    from plumb.awareness.lines import overlap_line
    from plumb.contracts import Overlap

    item = Overlap(record="SR-005", title="relay checks", branch="feat-x",
                   worktree="C:/wt/feat-x")
    assert overlap_line(item) == 'plumb: SR-005 "relay checks" is also being changed on ' \
                                 "branch feat-x"
    assert overlap_line(item, worktree=True).endswith("(worktree C:/wt/feat-x)")
    claimed = Overlap(record="SR-005", title="relay checks", branch="feat-x", how="claimed",
                      summary="pin the stated group")
    assert overlap_line(claimed).endswith('(intent in flight there: "pin the stated group")')


def test_snapshot_fields_and_status_card_text(tmp_path: Path) -> None:
    main = _many(tmp_path, 2)
    fields = awareness.snapshot_fields(open_core(main))
    assert fields == {"overlaps": 2, "overlap_labels": ("feat-x",)}
    from plumb.hosts.claude_code.snapshot import build_snapshot

    snapshot = build_snapshot(open_core(main), tests_summary=("ok", (), ()))
    assert snapshot.overlaps == 2 and snapshot.overlap_labels == ("feat-x",)
    assert status_card(snapshot).endswith("· 2 also changed on feat-x")
    assert status_card(snapshot, ascii=True).endswith("| overlap 2 (feat-x)")
    data = {"requirements_total": 1, "proposed": 0, "conflicts": 1, "overlaps": 0}
    assert status_card(data).endswith("· 1 conflict awaits you")
    assert "overlap" not in status_card({"requirements_total": 1})


def test_many_branches_on_one_record_are_one_line() -> None:
    """54 old branches each carrying the same records once made a prompt 508 lines."""
    from plumb.awareness.lines import grouped_lines
    from plumb.contracts import Overlap

    found = [Overlap(record="SR-267", title="A question stands alone", branch=f"debug/b{n}",
                     other_hash=f"h{n}") for n in range(25)]
    found.append(Overlap(record="SR-300", title="Debug cases", branch="feat/x"))
    lines = grouped_lines(found)
    assert [line.text for line in lines] == [
        'plumb: SR-267 "A question stands alone" is also being changed on 25 branches: '
        "debug/b0, debug/b1, debug/b2 and 22 more (/plumb status)",
        'plumb: SR-300 "Debug cases" is also being changed on branch feat/x']
    assert lines[0].subject == "overlap:SR-267" and lines[1].subject == "overlap:SR-300:feat/x"


def test_a_prompt_names_ten_records_then_more(monkeypatch) -> None:
    from types import SimpleNamespace

    from plumb.awareness import lines as mod
    from plumb.contracts import Overlap

    found = [Overlap(record=f"SR-{n}", title="t", branch="b") for n in range(14)]
    monkeypatch.setattr(mod, "overlaps", lambda core, ids: found)
    monkeypatch.setattr(mod, "raised_lines", lambda core: [])
    monkeypatch.setattr(mod, "superseded_lines", lambda core: [])
    core = SimpleNamespace(config=SimpleNamespace(awareness=None))
    texts = [line.text for line in mod.delta_lines(core, [])]
    assert len(texts) == 11 and texts[-1] == ("plumb: +4 more also being changed elsewhere "
                                              "(/plumb status)")
