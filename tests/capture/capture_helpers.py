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
    from logutil import kinds

    return kinds(repo, "events")


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
                    elif "benign" in q["criteria"]:     # SR-372: the approval question
                        p = stub.noul(body["state"])
                        label = "benign" if p >= 0.5 else "contradicts"
                        answers[name] = {"type": "choice", "choice": label,
                                         "probabilities": {"benign": p, "contradicts": 1 - p},
                                         "confidence": 0.9}
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


class CoverageJudge:
    """A test double for the configured judge: it rates how much of a restatement the owner's
    words cover, by term overlap. It stands in for JEV in tests that need a judgment; plumb
    itself has no rule-based judge (INT-029)."""

    name = "double"
    version = "double-1"

    def entailment(self, premise: str, hypothesis: str, *, subject: str, claim_kind: str,
                   quote_only: str | None = None):
        from plumb.contracts import Judgment
        from plumb.judgment.textjudge import _LABEL, stems

        supported = stems(premise)
        wanted: set[str] = set()
        penalty = 0.0
        for line in hypothesis.splitlines():
            label = _LABEL.match(line)
            terms = stems(line[label.end():] if label else line)
            wanted |= terms
            if label and label.group(1).lower() != "will" and terms and not terms & supported:
                penalty += 0.15
        score = 0.0 if not supported or not wanted else max(
            0.0, round(len(wanted & supported) / len(wanted) - penalty, 4))
        verdict = "entailed" if score >= 0.8 else ("not-entailed" if score < 0.5 else "unsure")
        probability = score if verdict == "entailed" else 1.0 - score
        return Judgment(action="faithfulness", subject=subject, verdict=verdict,
                        confidence=0.5, tier="escalate-llm", backend=self.name,
                        fingerprint="sha256:" + "0" * 64, probability=probability,
                        confidence_label="low")


def use_coverage_judge(monkeypatch) -> CoverageJudge:
    """``get_backend`` answers with the double unless the repository configures a judge."""
    import plumb.judgment as judgment

    real = judgment.get_backend
    double = CoverageJudge()

    def pick(core, hook):
        return real(core, hook=hook) if core.config.judgment.backend else double

    monkeypatch.setattr(judgment, "get_backend", pick)
    return double


def approve_set(core, anchor: str) -> None:
    """A set approval as the judge worker writes it (the owner-terminal command is gone)."""
    from plumb.capture.spec import set_payload

    records, digest = set_payload(core, anchor)
    core.log_append("events", "approval", {
        "records": records, "set": digest, "by": "owner", "prompt_digest": None, "quote": None,
        "quote_digest": None, "affirmation": None, "stated_set": None, "note": ""})
