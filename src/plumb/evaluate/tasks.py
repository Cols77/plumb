"""The benchmark tasks (SR-349): a brief for the agent, a hidden picture for the scripted owner,
the owner's requests in order, and hidden checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

NAMES = ("simple", "complex")
TASKS_DIR = Path(__file__).resolve().parent / "tasks"


@dataclass(frozen=True)
class Task:
    name: str
    agent_brief: str
    owner_brief: str
    requests: list[str]
    checks: Path


def load(name: str) -> Task:
    if name not in NAMES:
        raise ValueError(f"unknown task {name!r}; one of {', '.join(NAMES)}")
    here = TASKS_DIR / name
    read = lambda f: (here / f).read_text(encoding="utf-8").strip()  # noqa: E731
    return Task(name, read("agent.md"), read("owner.md"),
                json.loads(read("requests.json")), here / "checks")


def load_case(folder: Path | str) -> Task:
    """SR-397 EX-8: an evaluation case written by an evaluator, shaped like a benchmark task:
    ``requests.json`` (required), ``agent.md`` and ``owner.md`` ("" when absent), ``checks/``."""
    here = Path(folder)
    read = lambda f: (here / f).read_text(encoding="utf-8").strip() if (here / f).is_file() else ""  # noqa: E731
    requests = json.loads(read("requests.json") or "null")
    if not isinstance(requests, list) or not all(isinstance(r, str) for r in requests):
        raise ValueError(f"{here / 'requests.json'} must be a JSON list of strings")
    return Task(here.name, read("agent.md"), read("owner.md"), requests, here / "checks")
