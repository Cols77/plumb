"""Shared helpers of the CAPTURE tests (no fixtures here: conftest files are shared test
infrastructure)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from plumb.cli import main


def run(repo: Path, *argv: str) -> int:
    return main([*argv, "--root", str(repo)])


def log_prompt(repo: Path, text: str, *, at: str = "2026-10-06T10:00:00Z",
               session: str = "test-session", via: str | None = "hook") -> str:
    """Append ``text`` to the prompt log as the prompt hook does; returns its digest."""
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = repo / ".plumb" / "session" / "prompts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"digest": digest, "session": session, "at": at, "text": text}
    if via is not None:
        entry["via"] = via
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry) + "\n")
    return digest


def write_stated(repo: Path, records: list[tuple[str, str]], *, at: str = "2026-10-06T09:59:00Z",
                 groups: list[dict] | None = None) -> None:
    """The stated set of the reply before the owner's prompt (the stop hook writes it)."""
    data: dict = {"at": at, "records": [{"id": i, "hash": h, "shown": True}
                                        for i, h in records]}
    if groups is not None:
        data["groups"] = groups
    path = repo / ".plumb" / "session" / "stated.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def event_kinds(repo: Path) -> list[str]:
    path = repo / ".plumb" / "log" / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line)["kind"] for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def tree_bytes(repo: Path) -> dict[str, bytes]:
    """Every file under .plumb/ except session state and caches."""
    out = {}
    for path in sorted((repo / ".plumb").rglob("*")):
        rel = path.relative_to(repo).as_posix()
        if path.is_file() and "/session/" not in rel and "/cache/" not in rel:
            out[rel] = path.read_bytes()
    return out


def agent_shell_setup(monkeypatch) -> None:
    """No session marker, the real terminal check, and stdin a pipe holding "y": an agent's
    shell on a host whose adapter cannot set the marker (concept 4.6 check 4)."""
    import io

    from plumb import approvals

    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    monkeypatch.setattr(approvals, "owner_terminal_answer", REAL_TERMINAL_CHECK)
    monkeypatch.setattr("sys.stdin", io.StringIO("y\ny\ny\n"))


def record_text(record_id: str, title: str, **fields) -> str:
    """A record file's text with simple frontmatter (lists as YAML)."""
    import yaml

    data = {"id": record_id, "title": title, **fields}
    return "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n"


from plumb.approvals import owner_terminal_answer as REAL_TERMINAL_CHECK  # noqa: E402
