"""A4: the brief, delta and status-card wording of overlaps (SR-078)."""

from __future__ import annotations

from pathlib import Path

import pytest

from awareness.gitrepo import add_worktree, commit_all, make_repo, requirement
from iaso import awareness
from iaso.api import open_core
from iaso.awareness import publish as pub
from iaso.present.render import status_card

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
        changed.append(f".iaso/requirements/SR-0{i:02d}.md")
    pub.publish(open_core(other), changed)
    pub.publish(open_core(main), changed)
    return main


def test_brief_cap_and_more_line(tmp_path: Path) -> None:
    main = _many(tmp_path, 5)
    lines = awareness.brief_lines(open_core(main))
    assert len(lines) == 4
    assert lines[:3] == [f'iaso: SR-0{i:02d} "thing {i}" is also being changed on branch '
                         "feat-x" for i in (1, 2, 3)]
    assert lines[3] == "iaso: +2 more also being changed elsewhere (/iaso status)"


def test_wording_matches_spec(tmp_path: Path) -> None:
    """sp6 9.4: iaso: SR-005 "relay checks" is also being changed on branch feat-x."""
    from iaso.awareness.lines import overlap_line
    from iaso.contracts import Overlap

    item = Overlap(record="SR-005", title="relay checks", branch="feat-x",
                   worktree="C:/wt/feat-x")
    assert overlap_line(item) == 'iaso: SR-005 "relay checks" is also being changed on ' \
                                 "branch feat-x"
    assert overlap_line(item, worktree=True).endswith("(worktree C:/wt/feat-x)")
    claimed = Overlap(record="SR-005", title="relay checks", branch="feat-x", how="claimed",
                      summary="pin the stated group")
    assert overlap_line(claimed).endswith('(intent in flight there: "pin the stated group")')


def test_snapshot_fields_and_status_card_text(tmp_path: Path) -> None:
    main = _many(tmp_path, 2)
    fields = awareness.snapshot_fields(open_core(main))
    assert fields == {"overlaps": 2, "overlap_labels": ("feat-x",)}
    from iaso.hosts.claude_code.snapshot import build_snapshot

    snapshot = build_snapshot(open_core(main), tests_summary=("ok", (), ()))
    assert snapshot.overlaps == 2 and snapshot.overlap_labels == ("feat-x",)
    assert status_card(snapshot).endswith("· 2 also changed on feat-x")
    assert status_card(snapshot, ascii=True).endswith("| overlap 2 (feat-x)")
    data = {"requirements_total": 1, "proposed": 0, "conflicts": 1, "overlaps": 0}
    assert status_card(data).endswith("· 1 conflict awaits you")
    assert "overlap" not in status_card({"requirements_total": 1})
