"""Where plumb keeps its files (spec 4.2, 12.4)."""

from __future__ import annotations

from pathlib import Path


def find_root(start: Path) -> Path:
    """The first directory upward holding ``.plumb/``, else ``.git``, else ``start``."""
    start = start.resolve()
    chain = [start, *start.parents]
    for candidate in chain:
        if (candidate / ".plumb").is_dir():
            return candidate
    for candidate in chain:
        if (candidate / ".git").exists():
            return candidate
    return start


class PlumbPaths:
    """Every path plumb reads or writes under ``<root>/.plumb``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        p = self.root / ".plumb"
        self.plumb = p
        self.config = p / "config.yaml"
        self.claims = p / "claims.yaml"
        self.log_dir = p / "log"
        self.log_events = p / "log" / "events.jsonl"
        self.log_evidence = p / "log" / "evidence.jsonl"
        self.cache = p / "cache"
        self.session = p / "session"
        self.test_map_txt = p / "test_map.txt"
        self.test_map_json = self.cache / "test_map.json"
        self.index_cache = self.cache / "index.json"
        self.hash_cache = self.cache / "hashes.json"
        self.evidence_index = self.cache / "evidence_index.json"
        self.env_identity = self.cache / "env_identity.json"
        self.config_cache = self.cache / "config.json"
        self.lock = self.cache / "log.lock"
        self.prompts = self.session / "prompts.jsonl"
        self.status = self.session / "status.json"
        self.stated = self.session / "stated.json"
        self.escalations = self.session / "escalations.jsonl"
        self.errors = self.session / "errors.log"

    def session_dir(self, session_id: str) -> Path:
        return self.session / session_id

    def log_path(self, stream: str) -> Path:
        if stream == "events":
            return self.log_events
        if stream == "evidence":
            return self.log_evidence
        raise ValueError(f"unknown log stream: {stream}")
