"""``plumb mcp serve``: a read-only MCP server, JSON-RPC 2.0 over stdio (sp4 6, SR-057).

Newline-delimited JSON-RPC with the standard library only (no MCP SDK: the runtime
dependencies stay the standard library and PyYAML). Methods: ``initialize``,
``notifications/initialized``, ``ping``, ``tools/list``, ``tools/call``; any other method
answers ``-32601``. One request at a time; every tool call opens the records afresh, so it
sees the current files.

Read-only guarantee: the six tools only read. Each one runs the same plumb command the CLI
runs (``brief``, ``show``, ``explain``, ``impact``, ``drift``) in-process and returns what it
prints, plus its ``--json`` data as ``structuredContent``; ``plumb_relevant`` reads the
records directly. There is no write tool (no capture, link, repin, approve, relay, revoke,
test run or waiver), so an MCP client cannot reach the approval paths of concept 4.6.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TextIO

from plumb import __version__

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
INTERNAL_ERROR = -32603
ANNOTATIONS = {"readOnlyHint": True, "idempotentHint": True, "destructiveHint": False,
               "openWorldHint": False}


def _schema(properties: Mapping[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties), "required": list(required),
            "additionalProperties": False}


TOOLS: tuple[dict[str, Any], ...] = (
    {"name": "plumb_brief",
     "description": "The owner's current intent in a few lines (plumb brief); full: the long "
                    "brief.",
     "inputSchema": _schema({"full": {"type": "boolean"}})},
    {"name": "plumb_relevant",
     "description": "Records relevant to some text, one line each: ID, state, title.",
     "inputSchema": _schema({"text": {"type": "string"},
                             "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                            ("text",))},
    {"name": "plumb_show",
     "description": "Records in full: read-back, examples, tests and state (plumb show).",
     "inputSchema": _schema({"ids": {"type": "array", "items": {"type": "string"},
                                     "minItems": 1}}, ("ids",))},
    {"name": "plumb_explain",
     "description": "Why a behaviour, file or record exists, in the owner's terms (plumb "
                    "explain): plain words, a path or an ID.",
     "inputSchema": _schema({"query": {"type": "string"}}, ("query",))},
    {"name": "plumb_impact",
     "description": "What a change to a record or path would reach: records and covering "
                    "tests with their evidence (plumb impact).",
     "inputSchema": _schema({"ref": {"type": "string"}}, ("ref",))},
    {"name": "plumb_drift",
     "description": "Drift signals: stale and dangling links, unconfirmed edits, uncovered "
                    "examples (plumb drift).",
     "inputSchema": _schema({})},
)
for _tool in TOOLS:
    _tool["annotations"] = dict(ANNOTATIONS)
TOOL_NAMES = tuple(t["name"] for t in TOOLS)


class ToolError(Exception):
    """A tool's input is wrong; answered as ``isError`` content."""


def run_cli(root: Path, args: list[str]) -> tuple[int, str]:
    """Run one plumb CLI command in-process; ``(exit code, stdout)``."""
    from plumb import cli

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main([*args, "--root", str(root)])
        except SystemExit as exc:  # argparse
            code = exc.code if isinstance(exc.code, int) else 2
    text = out.getvalue()
    if code not in (0, 1) and err.getvalue().strip():
        text = (text + "\n" + err.getvalue()).strip()
    return int(code or 0), text


def _command_tool(root: Path, args: list[str]) -> tuple[str, Any]:
    code, text = run_cli(root, args)
    if code not in (0, 1):
        raise ToolError(text.strip() or f"plumb {args[0]} failed (exit {code})")
    _, raw = run_cli(root, [*args, "--json"])
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    return text.rstrip("\n"), data


def _relevant(root: Path, text: str, limit: int) -> tuple[str, Any]:
    from plumb.api import open_core

    core = open_core(root)
    ranked = list(core.relevant(text, limit=limit))
    index = core.index()
    statuses = core.status([i for i, _ in ranked if i in index])
    records = [{"id": i, "state": statuses[i].confirmation if i in statuses else "?",
                "title": index[i].title, "score": round(float(score), 3)}
               for i, score in ranked if i in index]
    lines = [f"{r['id']} [{r['state']}] {r['title']}" for r in records]
    return "\n".join(lines) or "no relevant records", {"records": records}


def _str(arguments: Mapping[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"'{key}' must be a non-empty string")
    return value


@contextlib.contextmanager
def no_derived_writes() -> Any:
    """The one choke point of the read-only guarantee for derived files: the commands the
    tools run may build the code-to-test map, which the CLI also writes to
    ``.plumb/test_map.txt``; inside a tool call the map is built in memory only, so
    ``.plumb/`` outside ``cache/`` stays byte-identical (sp4 6.3)."""
    try:
        from plumb.verify import testmap
    except ImportError:
        yield
        return
    original = testmap.build_map

    def build_map(core: Any, *, rebuild: bool = False, write_text: bool = True) -> Any:
        return original(core, rebuild=rebuild, write_text=False)

    testmap.build_map = build_map
    try:
        yield
    finally:
        testmap.build_map = original


def call_tool(root: Path, name: str, arguments: Mapping[str, Any]) -> tuple[str, Any]:
    """``(text, structured data)`` of one read-only tool."""
    with no_derived_writes():
        return _call_tool(root, name, arguments)


def _call_tool(root: Path, name: str, arguments: Mapping[str, Any]) -> tuple[str, Any]:
    if name == "plumb_brief":
        return _command_tool(root, ["brief", *(["--all"] if arguments.get("full") else [])])
    if name == "plumb_relevant":
        limit = arguments.get("limit", 5)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise ToolError("'limit' must be an integer from 1 to 50")
        return _relevant(root, _str(arguments, "text"), limit)
    if name == "plumb_show":
        ids = arguments.get("ids")
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
            raise ToolError("'ids' must be a non-empty list of record IDs")
        return _command_tool(root, ["show", *ids])
    if name == "plumb_explain":
        return _command_tool(root, ["explain", _str(arguments, "query")])
    if name == "plumb_impact":
        return _command_tool(root, ["impact", _resolve(root, _str(arguments, "ref"))])
    if name == "plumb_drift":
        return _command_tool(root, ["drift"])
    raise KeyError(name)


def _resolve(root: Path, ref: str) -> str:
    """Plain words resolved to a record or path first (sp5 5) when PRESENT's resolver is in
    this build; otherwise the reference as given."""
    try:
        from plumb.present.api import resolve  # type: ignore[import-not-found]
    except ImportError:
        return ref
    try:
        from plumb.api import open_core

        result = resolve(open_core(root), ref)
        best = getattr(result, "best", None) or getattr(result, "ref", None)
        return str(best) if best else ref
    except Exception:  # noqa: BLE001 - a resolver failure keeps the given reference
        return ref


class Server:
    """One MCP session over newline-delimited JSON-RPC."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.handlers: dict[str, Callable[[Mapping[str, Any]], Any]] = {
            "initialize": self._initialize, "ping": lambda _p: {},
            "tools/list": lambda _p: {"tools": [dict(t) for t in TOOLS]},
            "tools/call": self._call,
        }

    def _initialize(self, params: Mapping[str, Any]) -> dict[str, Any]:
        asked = params.get("protocolVersion")
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {"protocolVersion": version, "capabilities": {"tools": {}},
                "serverInfo": {"name": "plumb", "version": __version__},
                "instructions": "Read-only plumb records: the owner's intent, requirements "
                                "with examples, tests and drift. Nothing here writes or "
                                "approves."}

    def _call(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOL_NAMES:
            raise _RpcError(INVALID_PARAMS, f"unknown tool: {name}")
        if not isinstance(arguments, Mapping):
            raise _RpcError(INVALID_PARAMS, "arguments must be an object")
        try:
            text, data = call_tool(self.root, str(name), arguments)
        except ToolError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        result: dict[str, Any] = {"content": [{"type": "text", "text": text}],
                                  "isError": False}
        if isinstance(data, Mapping):
            result["structuredContent"] = dict(data)
        elif data is not None:
            result["structuredContent"] = {"result": data}
        return result

    def handle(self, message: Any) -> dict[str, Any] | None:
        """The response to one message, or None for a notification."""
        if not isinstance(message, Mapping) or message.get("jsonrpc") != "2.0" \
                or not isinstance(message.get("method"), str):
            return _error(message.get("id") if isinstance(message, Mapping) else None,
                          INVALID_REQUEST, "invalid request")
        is_notification = "id" not in message
        method = message["method"]
        handler = self.handlers.get(method)
        if is_notification:
            return None  # notifications/initialized and others need no answer
        if handler is None:
            return _error(message["id"], METHOD_NOT_FOUND, f"method not found: {method}")
        params = message.get("params") or {}
        if not isinstance(params, Mapping):
            return _error(message["id"], INVALID_PARAMS, "params must be an object")
        try:
            result = handler(params)
        except _RpcError as exc:
            return _error(message["id"], exc.code, str(exc))
        except Exception as exc:  # noqa: BLE001 - a broken tool never ends the session
            return _error(message["id"], INTERNAL_ERROR, f"internal error: {exc}")
        return {"jsonrpc": "2.0", "id": message["id"], "result": result}


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(root: Path, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    """Answer requests until stdin closes."""
    if stdin is None or stdout is None:
        from plumb.hosts.claude_code.hookio import use_utf8_stdio

        use_utf8_stdio()
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    server = Server(root)
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response: dict[str, Any] | None = _error(None, PARSE_ERROR, "parse error")
        else:
            response = server.handle(message)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0
