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
        generated = "/session/" in rel or "/cache/" in rel or rel.endswith("test_map.txt")
        if path.is_file() and not generated:
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

# --------------------------------------------------------------------------- a JEV stub

KEY = "ts-test-key-abcdefghij"


class JevStub:
    """A local ``/v1/systemone`` stub (no network). ``noul(state) -> p`` answers each Noul
    question; ``model`` is the resolved version it reports."""

    def __init__(self, noul=None, model: str = "jev-1.13.0") -> None:
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.noul = noul or (lambda state: 0.95)
        self.model = model
        self.requests: list[dict] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                stub.requests.append(body)
                answers = {}
                for name, q in body["questions"].items():
                    if q["type"] == "noul":
                        answers[name] = {"type": "noul", "noul": stub.noul(body["state"])}
                    else:
                        label = next(iter(q["criteria"]))
                        answers[name] = {"type": "choice", "choice": label,
                                         "probabilities": {label: 0.9}, "confidence": 0.9}
                data = json.dumps({"model": stub.model, "answers": answers}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def use_jev(repo: Path, stub: JevStub, monkeypatch, *, extra: str = "") -> None:
    """Configure ``repo`` for JEV against ``stub``, with the credential in the environment
    and no user store."""
    from plumb.judgment import jev as jev_mod

    (repo / ".plumb" / "config.yaml").write_text(
        "judgment:\n  backend: jev\n  hook_timeout_ms: 2000\n"
        f"  jev: {{base_url: '{stub.url}'}}\n" + extra, encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", KEY)
    monkeypatch.setattr(jev_mod, "user_store_path", lambda: repo.parent / "home" / "jev")
