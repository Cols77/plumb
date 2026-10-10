"""The agent definitions of the job kinds (ENGINE's loader): ``agents/<kind>.md`` is the system
prompt of the kind's model call (the file is its lane's)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

AGENTS_DIR = Path(__file__).resolve().parent
DEFAULT = "Answer only with the JSON the schema asks for, from the inputs given, nothing else."


def load(kind: str) -> str:
    """The system prompt of ``kind`` (a plain default when its file does not exist yet)."""
    try:
        text = (AGENTS_DIR / f"{kind}.md").read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT
    return text or DEFAULT


def name(kind: str) -> str:
    return f"plumb-{kind}"


def definition(kind: str, system: str | None = None) -> dict[str, Any]:
    """The ``--agents`` object for ``kind``: one agent, no tools."""
    return {name(kind): {"description": f"plumb {kind} job",
                         "prompt": load(kind) if system is None else system}}
