"""The read-only MCP server on stdio (sp4 6, SR-057)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from plumb.mcp.server import TOOL_NAMES, run_cli, serve

pytestmark = pytest.mark.sr("SR-285")

SR1 = """---
id: SR-001
title: Adds numbers
statement: add returns the sum.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""
CALLS = {
    "plumb_brief": {},
    "plumb_relevant": {"text": "adds numbers"},
    "plumb_show": {"ids": ["SR-001"]},
    "plumb_explain": {"query": "adding numbers"},
    "plumb_impact": {"ref": "SR-001"},
    "plumb_drift": {},
}
CLI_VIEW = {"plumb_brief": ["brief"], "plumb_show": ["show", "SR-001"],
            "plumb_explain": ["explain", "adding numbers"], "plumb_impact": ["impact", "SR-001"],
            "plumb_drift": ["drift"]}


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    from plumb.api import open_core
    from plumb.contracts import Target

    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    return repo


def session(root: Path, messages: list[dict]) -> list[dict]:
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    stdout = io.StringIO()
    assert serve(root, stdin, stdout) == 0
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def request(n: int, method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": n, "method": method, "params": params or {}}


def call(n: int, name: str) -> dict:
    return request(n, "tools/call", {"name": name, "arguments": CALLS[name]})


def test_initialize_and_tools_list(project: Path) -> None:
    replies = session(project, [
        request(1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                  "clientInfo": {"name": "test", "version": "0"}}),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        request(2, "tools/list"),
        request(3, "ping"),
    ])
    assert [r["id"] for r in replies] == [1, 2, 3]  # no answer to the notification
    init = replies[0]["result"]
    assert init["protocolVersion"] == "2025-03-26"
    assert init["serverInfo"]["name"] == "plumb" and init["capabilities"] == {"tools": {}}
    tools = replies[1]["result"]["tools"]
    assert [t["name"] for t in tools] == list(CALLS)
    assert all(t["annotations"]["readOnlyHint"] is True for t in tools)
    assert replies[2]["result"] == {}


def test_each_tool_matches_cli_view(project: Path) -> None:
    replies = session(project, [call(i, name) for i, name in enumerate(CALLS)])
    by_name = dict(zip(CALLS, replies, strict=True))
    for name, reply in by_name.items():
        result = reply["result"]
        assert result["isError"] is False, (name, result)
        text = result["content"][0]["text"]
        if name in CLI_VIEW:
            assert text == run_cli(project, CLI_VIEW[name])[1].rstrip("\n"), name
            assert "structuredContent" in result, name
    relevant = by_name["plumb_relevant"]["result"]
    assert relevant["content"][0]["text"].startswith("SR-001 [proposed] Adds numbers")
    assert relevant["structuredContent"]["records"][0]["id"] == "SR-001"
    assert "SR-001/EX-1: given 1 and 2" in by_name["plumb_show"]["result"]["content"][0]["text"]


def test_unknown_method_error(project: Path) -> None:
    replies = session(project, [request(7, "resources/list"),
                                request(8, "tools/call", {"name": "plumb_approve"})])
    assert replies[0]["error"]["code"] == -32601
    assert replies[1]["error"]["code"] == -32602


def test_bad_input_is_a_tool_error_and_bad_json_a_parse_error(project: Path) -> None:
    stdin = io.StringIO("{not json\n" + json.dumps(request(
        2, "tools/call", {"name": "plumb_show", "arguments": {"ids": []}})) + "\n")
    stdout = io.StringIO()
    serve(project, stdin, stdout)
    first, second = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert first["error"]["code"] == -32700
    assert second["result"]["isError"] is True


def _plumb_files(root: Path) -> dict[str, bytes]:
    base = root / ".plumb"
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*"))
            if p.is_file() and p.relative_to(base).parts[0] != "cache"}


def test_tools_are_read_only_plumb_unchanged(project: Path) -> None:
    before = _plumb_files(project)
    replies = session(project, [call(i, name) for i, name in enumerate(CALLS)])
    assert all(r["result"]["isError"] is False for r in replies)
    assert _plumb_files(project) == before


def test_no_write_tool_listed(project: Path) -> None:
    [reply] = session(project, [request(1, "tools/list")])
    names = {t["name"] for t in reply["result"]["tools"]}
    assert names == set(TOOL_NAMES) == set(CALLS)
    for verb in ("capture", "link", "repin", "approve", "relay", "revoke", "run", "waive",
                 "triage", "config", "write", "set"):
        assert not any(verb in name for name in names), verb


def test_serve_over_a_real_pipe(project: Path) -> None:
    """``plumb mcp serve`` as a host starts it: a subprocess on stdio."""
    messages = [request(1, "initialize", {"protocolVersion": "2025-06-18"}),
                request(2, "tools/call", {"name": "plumb_relevant",
                                          "arguments": {"text": "adds numbers"}})]
    result = subprocess.run([sys.executable, "-m", "plumb", "mcp", "serve", "--root",
                             str(project)],
                            input="".join(json.dumps(m) + "\n" for m in messages),
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert replies[1]["result"]["content"][0]["text"].startswith("SR-001")
