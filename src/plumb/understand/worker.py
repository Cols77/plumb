"""The worker (ENGINE). Stub: no worker is started; ``run_once`` and ``run_loop`` have their
final signatures and run nothing (marked ``@stub``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plumb.understand import stub


def start_detached(root: Path, session: str) -> None:
    return None


@stub
def run_once(core: Any, session: str, job_id: str | None = None) -> list[str]:
    """Run the queued jobs of the session in the worker's order (or the one job given and
    its ``needs``); the ids run."""
    return []


@stub
def run_loop(core: Any, session: str) -> None:
    """Run jobs until none is left (the worker's loop)."""
    return None
