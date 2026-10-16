"""Where plumb keeps its files (spec 4.2, 12.4)."""

from __future__ import annotations

from pathlib import Path


def holds_records(candidate: Path) -> bool:
    """Whether ``candidate/.plumb`` is a repository's records folder. plumb's own home
    (``~/.plumb``: the plugin's environments under ``env/`` and ``current.json``) never is,
    whatever else was left in it, so a folder under the user's home is never taken for an
    adopted repository."""
    plumb = Path(candidate) / ".plumb"
    if not plumb.is_dir():
        return False
    return not ((plumb / "env").is_dir() or (plumb / "current.json").is_file())


def find_root(start: Path) -> Path:
    """The first directory upward holding ``.plumb/``, else ``.git``, else ``start``."""
    start = start.resolve()
    chain = [start, *start.parents]
    for candidate in chain:
        if holds_records(candidate):
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

    @property
    def prompt_logs(self) -> list[Path]:
        """The prompt logs to read, oldest source first: a worktree's ``.git`` file names
        ``<main>/.git/worktrees/<name>``, and the hook logs in the main checkout (SR-189)."""
        logs = [self.prompts]
        try:
            gitdir = Path((self.root / ".git").read_text(encoding="utf-8").split(":", 1)[1].strip())
        except (OSError, IndexError):  # not a worktree: ``.git`` is a folder, or absent
            return logs
        if gitdir.parent.name == "worktrees":
            main = gitdir.parent.parent.parent / ".plumb" / "session" / "prompts.jsonl"
            if main.resolve() != self.prompts.resolve():
                logs.insert(0, main)
        return logs

    def prompt_lines(self) -> list[str]:
        """Every line of the prompt logs, the checkout's own last so its entries win."""
        lines: list[str] = []
        for log in self.prompt_logs:
            try:
                lines.extend(log.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeDecodeError):
                pass
        return lines

    def session_dir(self, session_id: str) -> Path:
        return self.session / session_id

    # SP6 6.1: one file per entry under .plumb/log/<kind>/ (SR-073); the head pointer and
    # the per-stream pack caches are gitignored and rebuilt by a scan when missing.
    def log_kind_dir(self, kind: str) -> Path:
        return self.log_dir / kind

    @property
    def log_head(self) -> Path:
        return self.cache / "log-head.json"

    def log_pack(self, stream: str) -> Path:
        if stream not in ("events", "evidence"):
            raise ValueError(f"unknown log stream: {stream}")
        return self.cache / f"log-{stream}.json"

    def log_path(self, stream: str) -> Path:
        """The legacy JSONL file of a stream (read during the transition, SR-074)."""
        if stream == "events":
            return self.log_events
        if stream == "evidence":
            return self.log_evidence
        raise ValueError(f"unknown log stream: {stream}")
