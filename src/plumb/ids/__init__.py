"""Collision-free record IDs (sp6 4, 5, 12; SR-070 to SR-072).

- ``reserve``, ``peek``, ``observe``, ``state``, ``sync``: the one allocation function and
  its companions over the shared ref ``refs/plumb/ids`` (compare-and-swap, every worktree);
- ``collisions``: two records with one ID, for the merge report and ``plumb merge-fix``;
- ``merge_fix``: renumber the incoming record of a clone collision and rewrite every
  reference the incoming side introduced, never history;
- ``approval_aliases``, ``trailer_aliases``, ``carried``: what a ``renumber`` entry maps.

Import-light: the submodules load only when called.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from plumb.ids.ref import REF

if TYPE_CHECKING:
    from plumb.contracts import Collision, IdState, MergeFixResult
    from plumb.paths import PlumbPaths

__all__ = ["REF", "IdBusy", "approval_aliases", "carried", "collisions", "merge_fix",
           "observe", "peek", "renumber_problems", "reserve", "state", "sync",
           "trailer_aliases"]


def __getattr__(name: str) -> Any:
    if name == "IdBusy":
        from plumb.ids.reservation import IdBusy

        return IdBusy
    raise AttributeError(name)


def reserve(paths: PlumbPaths, kind: str, count: int = 1, *,
            local: Iterable[str] | None = None) -> list[str]:
    from plumb.ids.reservation import reserve as _reserve

    return _reserve(paths, kind, count, local=local)


def peek(paths: PlumbPaths, kind: str, *, local: Iterable[str] | None = None) -> str:
    from plumb.ids.reservation import peek as _peek

    return _peek(paths, kind, local=local)


def observe(paths: PlumbPaths, ids: Iterable[str]) -> None:
    from plumb.ids.reservation import observe as _observe

    _observe(paths, ids)


def state(paths: PlumbPaths) -> IdState:
    from plumb.ids.reservation import state as _state

    return _state(paths)


def sync(paths: PlumbPaths) -> IdState:
    from plumb.ids.reservation import sync as _sync

    return _sync(paths)


def collisions(core: Any, base: str | None = None) -> tuple[Collision, ...]:
    from plumb.ids.collision import collisions as _collisions

    return _collisions(core, base)


def approval_aliases(core: Any) -> Mapping[tuple[str, str], tuple[str, str]]:
    from plumb.ids.aliases import approval_aliases as _aliases

    return _aliases(core)


def trailer_aliases(core: Any) -> Mapping[tuple[str, str], str]:
    from plumb.ids.aliases import trailer_aliases as _aliases

    return _aliases(core)


def carried(core: Any) -> Mapping[str, tuple[str, str]]:
    from plumb.ids.aliases import carried as _carried

    return _carried(core)


def renumber_problems(core: Any) -> list[str]:
    from plumb.ids.aliases import renumber_problems as _problems

    return _problems(core)


def merge_fix(core: Any, *, dry_run: bool = False,
              from_ref: str | None = None) -> MergeFixResult:
    from plumb.ids.mergefix import merge_fix as _merge_fix

    return _merge_fix(core, dry_run=dry_run, from_ref=from_ref)
