"""sp6 11.1 (R14): every owner-visible awareness surface names a /plumb command or plain
words, never a shell command. One test per surface, each rendering it for real."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from awareness.gitrepo import add_worktree, commit_all, make_repo, requirement
from awareness.scenario import change, setup
from plumb import awareness
from plumb.api import open_core
from plumb.awareness import publish as pub
from plumb.present import owner_text
from plumb.present.owner_text import bare_cli_verbs


def _overlapping(tmp_path: Path, n: int = 5) -> Path:
    main = make_repo(tmp_path / "main")
    for i in range(1, n + 1):
        requirement(main, f"SR-0{i:02d}", f"thing {i}")
    commit_all(main, "records")
    other = add_worktree(main, tmp_path / "wt-x", "feat-x")
    paths = []
    for i in range(1, n + 1):
        for root in (main, other):
            requirement(root, f"SR-0{i:02d}", f"thing {i}", f"{root.name}")
        paths.append(f".plumb/requirements/SR-0{i:02d}.md")
    pub.publish(open_core(other), paths)
    pub.publish(open_core(main), paths)
    return main


@pytest.mark.sr("SR-258")
def test_brief_lines(tmp_path: Path) -> None:
    lines = awareness.brief_lines(open_core(_overlapping(tmp_path)))
    assert any("+2 more" in line and "/plumb status" in line for line in lines)
    assert bare_cli_verbs("\n".join(lines)) == []


@pytest.mark.sr("SR-258")
def test_delta_and_stop_lines(tmp_path: Path) -> None:
    lines = awareness.delta_lines(open_core(_overlapping(tmp_path)), ["SR-001", "SR-002"])
    assert len(lines) == 2
    assert bare_cli_verbs("\n".join(line.text for line in lines)) == []


@pytest.mark.sr("SR-258")
def test_status_card(tmp_path: Path) -> None:
    from plumb.hosts.claude_code.snapshot import build_snapshot
    from plumb.present.render import status_card

    snapshot = build_snapshot(open_core(_overlapping(tmp_path)), tests_summary=("ok", (), ()))
    for ascii_only in (False, True):
        card = status_card({**snapshot.__dict__, "conflicts": 2}, ascii=ascii_only)
        assert ("overlap 5 (feat-x)" if ascii_only else "5 also changed on feat-x") in card
        assert "2 conflicts await you" in card
        assert bare_cli_verbs(card) == []


@pytest.mark.sr("SR-258")
def test_status_section(tmp_path: Path) -> None:
    from plumb.cli import main as cli_main

    root = _overlapping(tmp_path, 2)
    out = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(out):
        cli_main(["status", "--root", str(root)])
    text = out.getvalue()
    assert "also being changed elsewhere" in text and "(worktree " in text
    section = text[text.index("also being changed elsewhere"):]
    assert bare_cli_verbs(section) == []
    with contextlib.redirect_stdout(io.StringIO()) as card_out:
        cli_main(["status", "--card", "--root", str(root)])
    card = card_out.getvalue()
    assert "also being changed elsewhere" in card
    assert bare_cli_verbs(card[card.index("also being changed elsewhere"):]) == []


@pytest.mark.sr("SR-259")
def test_early_conflict_card_and_lines(tmp_path: Path) -> None:
    """The early card, the recorded line and the known and settled lines (R17)."""
    from plumb import approvals
    from plumb.awareness import inflight

    main, other = setup(tmp_path)
    change(main, "main's version")
    raised = change(other, "feat-x's version")
    own = [line for line in raised.lines if "comes back at the end of this turn" in line or line.startswith("  ")
           or "asked once" in line]
    assert own and bare_cli_verbs("\n".join(own)) == []
    known = change(main, "main again")
    assert bare_cli_verbs("\n".join(known.lines)) == []
    dec = next(r for r in open_core(other).index().values() if r.kind == "decision")
    approvals.approve(open_core(other), [dec.id])
    inflight.sync_decisions(open_core(other))
    settled = awareness.brief_lines(open_core(main))
    assert any("settled it on branch feat-x" in line for line in settled)
    assert bare_cli_verbs("\n".join(settled)) == []


@pytest.mark.sr("SR-259")
def test_clarify_inflight_lines(tmp_path: Path) -> None:
    from plumb.capture.clarify import clarify, view_lines

    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    view = clarify(open_core(main), "change SR-005 again")
    assert view.inflight and bare_cli_verbs("\n".join(view.inflight)) == []
    assert bare_cli_verbs("\n".join(view_lines(view)[:6])) == []


def test_every_awareness_constant_passes() -> None:
    names = [n for n in dir(owner_text) if n.isupper() and isinstance(getattr(owner_text, n),
                                                                        str)]
    assert names
    for name in names:
        assert bare_cli_verbs(getattr(owner_text, name)) == [], name


def test_bare_cli_verbs_flags_plumb_verbs() -> None:
    assert bare_cli_verbs("run plumb inflight drop feat-x") == ["plumb inflight"]
    assert bare_cli_verbs("uv run plumb status") == ["plumb status"]
    assert bare_cli_verbs("/plumb status and plumb: SR-005 is changing") == []
    assert json.dumps(bare_cli_verbs("")) == "[]"
