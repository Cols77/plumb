"""A two-worktree repository with records for the intent-in-flight tests (R17)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from awareness.gitrepo import add_worktree, commit_all, make_repo, write_record
from iaso.api import open_core


def setup(tmp_path: Path) -> tuple[Path, Path]:
    """``main`` and worktree ``feat-x``, both holding FEAT-002, INT-001, SR-005 and SR-006
    (both in FEAT-002)."""
    main = make_repo(tmp_path / "main")
    write_record(main, "FEAT-002", "intent capture", description="capture")
    write_record(main, "INT-001", "relay intent", quote="relay", readback="relay")
    write_record(main, "SR-005", "relay checks", feature="FEAT-002",
                 statement="A relay pins every stated record.")
    write_record(main, "SR-006", "status card", feature="FEAT-002",
                 statement="The status card shows the state in one line.")
    commit_all(main, "records")
    other = add_worktree(main, tmp_path / "wt-x", "feat-x")
    return main, other


def capture(root: Path, doc: dict[str, Any], *, backend: Any = None,
            dry_run: bool = False) -> Any:
    from iaso.capture.capture import capture as run

    return run(open_core(root), doc, dry_run=dry_run, backend=backend)


def change(root: Path, statement: str, record: str = "SR-005", **kw: Any) -> Any:
    return capture(root, {"intent": "INT-001",
                          "updates": [{"id": record, "statement": statement}]}, **kw)


def new_requirement(root: Path, title: str, statement: str, *, backend: Any = None,
                    feature: str = "FEAT-002") -> Any:
    return capture(root, {"intent": "INT-001", "requirements": [
        {"title": title, "statement": statement, "feature": feature,
         "examples": [{"given": "g", "when": "w", "then": "t"}]}]}, backend=backend)
