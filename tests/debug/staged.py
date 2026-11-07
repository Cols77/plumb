"""SR-388 helpers: scripted stages for ``selfdebug.fix``. Every stage takes the keywords of the
fixer (round, case, evidence, worktree, model, previous) and whatever else the stage is given
(``**kw``), and says in ``trail`` that it ran. ``ok_stages()`` is the one shared helper for the
tests that script only the fixer: a diagnosis that reads nothing and a review that says ok."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import debug.test_selffix as base

CAUSE = "add subtracts instead of adding"


class Stage:
    """Scripted diagnoser or reviewer: round n answers ``answers[n-1]`` (the last one after)."""

    def __init__(self, name: str, answers: list[Any], trail: list[tuple[str, int]],
                 effect: Callable[[Path], None] | None = None) -> None:
        self.name, self.answers, self.trail, self.effect = name, answers, trail, effect
        self.models: list[str] = []
        self.kws: list[dict[str, Any]] = []
        self.seen: list[str] = []            # what each call was given, as text

    def __call__(self, *, round: int, case: dict[str, Any], worktree: Path, model: str,
                 previous: list[str], **kw: Any) -> dict[str, Any]:
        self.trail.append((self.name, round))
        self.models.append(model)
        self.kws.append({"round": round, "case": case, "previous": list(previous),
                         "worktree": worktree, **kw})
        self.seen.append(json.dumps({"case": case, "previous": previous, **kw}, default=str))
        if self.effect:
            self.effect(worktree)
        a = self.answers[min(round, len(self.answers)) - 1]
        return dict(a)


def diagnosis(cause: str = CAUSE) -> dict[str, Any]:
    return {"cause": cause, "path": "src/plumb/calc.py"}


OK = {"ok": True, "findings": []}


def not_ok(finding: str) -> dict[str, Any]:
    return {"ok": False, "findings": [finding]}


class Fixer(base.Fixer):
    """The fixer of test_selffix, taking the diagnosis (and whatever else) as keywords too."""

    def __init__(self, trail: list[tuple[str, int]], *steps: Any) -> None:
        super().__init__(*steps)
        self.trail, self.seen = trail, []

    def __call__(self, *, round, case, evidence, worktree, model, previous, **kw):
        self.trail.append(("fix", round))
        self.seen.append(json.dumps({"previous": previous, **kw}, default=str))
        return super().__call__(round=round, case=case, evidence=evidence, worktree=worktree,
                                model=model, previous=previous)


def ok_stages() -> dict[str, Any]:
    """``selfdebug.fix(..., fixer=f, **ok_stages())``: a diagnosis, then a review that says ok."""
    trail: list = []
    return {"diagnoser": Stage("diagnosis", [diagnosis()], trail),
            "reviewer": Stage("review", [OK], trail)}
