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
