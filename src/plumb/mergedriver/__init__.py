"""The record merge driver and intent conflicts (sp6 7, 8, 10; SR-075 to SR-077).

- ``merge_texts``: one record file merged field by field against the merge base (pure);
- ``install``, ``uninstall``, ``status``: the ``.plumb/.gitattributes`` lines and the git
  config keys that make git call ``plumb merge-driver`` for record files;
- ``open_conflicts``, ``conflict_card``, ``stated_entries``: the intent conflicts the driver wrote into record
  files, as the owner's cards.

Import-light: the submodules load only when called (the driver runs inside ``git merge``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plumb.contracts import DriverResult, IntentConflict

__all__ = ["conflict_card", "install", "merge_texts", "open_conflicts", "stated_entries", "status",
           "uninstall"]


def merge_texts(base: str, ours: str, theirs: str, *, labels: tuple[str, str],
                reserve_ic: Callable[[], str]) -> DriverResult:
    from plumb.mergedriver.merge import merge_texts as _merge

    return _merge(base, ours, theirs, labels=labels, reserve_ic=reserve_ic)


def open_conflicts(core: Any) -> tuple[IntentConflict, ...]:
    from plumb.mergedriver.conflicts import open_conflicts as _open

    return _open(core)


def conflict_card(core: Any, conflict: IntentConflict, *, backend: Any = None) -> list[str]:
    from plumb.mergedriver.conflicts import conflict_card as _card

    return _card(core, conflict, backend=backend)


def stated_entries(core: Any, shown: Iterable[str]) -> list[dict[str, Any]]:
    from plumb.mergedriver.conflicts import stated_entries as _stated

    return _stated(core, shown)


def install(root: Path, launcher: str, *, dry_run: bool = False) -> list[str]:
    from plumb.mergedriver.gitconfig import install as _install

    return _install(root, launcher, dry_run=dry_run)


def uninstall(root: Path, *, dry_run: bool = False) -> list[str]:
    from plumb.mergedriver.gitconfig import uninstall as _uninstall

    return _uninstall(root, dry_run=dry_run)


def status(root: Path) -> str:
    from plumb.mergedriver.gitconfig import status as _status

    return _status(root)
