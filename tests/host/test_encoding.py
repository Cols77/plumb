"""Hooks and the status line talk UTF-8 with Claude Code, whatever the locale code page.

Claude Code sends UTF-8 JSON on stdin and reads UTF-8 on stdout. On Windows Python's
default stdio encoding is the locale code page (cp1252), so the hooks must not rely on it.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from plumb.hosts.claude_code import hookio

pytestmark = pytest.mark.sr("SR-310")


def _locale_env() -> dict[str, str]:
    """The environment without any UTF-8 override, as a plain host process sees it."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONUTF8"] = "0"
    if os.name != "nt":  # make the locale code page non-UTF-8 elsewhere too
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
    return env


def _call(root: Path, *args: str, payload: dict | None = None) -> bytes:
    raw = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    result = subprocess.run([sys.executable, "-m", "plumb", *args, "--root", str(root)],
                            input=raw, capture_output=True, check=False, timeout=30,
                            env=_locale_env())
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout


def _payload(root: Path, event: str, **fields: object) -> dict:
    return {"session_id": "enc-session", "transcript_path": "", "cwd": str(root),
            "hook_event_name": event, **fields}


def test_prompt_hook_logs_non_ascii_prompt_verbatim(repo: Path) -> None:
    prompt = "ok, très bien “go ahead” → go"
    _call(repo, "hook", "prompt", payload=_payload(repo, "UserPromptSubmit", prompt=prompt))
    log = repo / ".plumb" / "session" / "prompts.jsonl"
    entries = [json.loads(line) for line in log.read_text("utf-8").splitlines() if line]
    assert entries and entries[-1]["text"] == prompt
    errors = repo / ".plumb" / "session" / "errors.log"
    assert not errors.exists(), errors.read_text("utf-8")


def test_prompt_hook_prints_non_ascii_record_text(repo: Path, write_record) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: links pin hashes → staleness, naïve\n"
                 "statement: pinned links go stale\n---\n")
    out = _call(repo, "hook", "prompt",
                payload=_payload(repo, "UserPromptSubmit", prompt="fix SR-001 links"))
    text = out.decode("utf-8")
    assert "links pin hashes → staleness, naïve" in text
    errors = repo / ".plumb" / "session" / "errors.log"
    assert not errors.exists(), errors.read_text("utf-8")


def test_statusline_reads_utf8_input(repo: Path) -> None:
    out = _call(repo, "statusline", payload={"cwd": str(repo), "model": {"name": "é→"}})
    assert out.decode("utf-8").startswith("plumb |")


def test_failed_write_still_prints_the_skip_notice(repo: Path, hook_input) -> None:
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="cp1252", newline="\n")
    hookio.run_hook("test", lambda ctx: hookio.HookOutput(text="arrow → here"),
                    stdin=io.StringIO(hook_input("Stop")), stdout=out, root=repo,
                    budget_ms=500)
    out.flush()
    assert raw.getvalue().decode("cp1252").strip() == hookio.SKIP_ERROR
    log = (repo / ".plumb" / "session" / "errors.log").read_text("utf-8")
    assert "UnicodeEncodeError" in log
