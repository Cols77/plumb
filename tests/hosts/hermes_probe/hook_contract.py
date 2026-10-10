"""Offline source-contract and boundary probe for Hermes hook evidence."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import tempfile
from types import SimpleNamespace
from pathlib import Path


PINNED = "b20cc5f787ea816ea8645603b7b2ac8234dcb8b4"
SOURCE_ROOT = Path("C:/Users/33630/AppData/Local/hermes/hermes-agent")
PRODUCERS = {
    "on_session_start": ("agent/conversation_loop.py", "1107-1117"),
    "pre_llm_call": ("agent/turn_context.py", "1389-1405"),
    "post_tool_call": ("model_tools.py", "1184-1235"),
    "pre_verify": ("hermes_cli/plugins.py", "6871-6917"),
    "transform_llm_output": ("agent/turn_finalizer.py", "607-628"),
    "post_llm_call": ("agent/turn_finalizer.py", "630-649"),
}


def _names_in_range(path: Path, line_range: str, event: str) -> set[str]:
    start, end = (int(part) for part in line_range.split("-"))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not (start <= node.lineno <= end):
            continue
        if not (isinstance(node.func, ast.Name)
                and node.func.id in {"invoke_hook", "_invoke_hook"}):
            continue
        if (not node.args or not isinstance(node.args[0], ast.Constant)
                or node.args[0].value != event):
            continue
        names.update(keyword.arg for keyword in node.keywords if keyword.arg)
    return names


def _assert_fixture(data: dict) -> None:
    assert _source_checkout() == PINNED
    assert data["provenance"]["source_checkout"] == PINNED
    assert data["provenance"]["fixture_class"] == "source_contract_not_runtime_capture"
    for event, (relative, line_range) in PRODUCERS.items():
        entry = data["events"][event]
        assert entry["source"] == f"{relative}:{line_range}"
        assert set(entry["kwargs"]) & set(entry["absent_fields"]) == set(), (
            f"{event}: absent_fields overlap kwargs")
        assert set(entry["absent_fields"]) <= _known_absent_fields(event, entry), (
            f"{event}: absent_fields contains an unverified field")
        assert (_names_in_range(SOURCE_ROOT / relative, line_range, event)
                == set(entry["kwargs"]))


def _source_checkout() -> str:
    result = subprocess.run(["git", "-C", str(SOURCE_ROOT), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _known_absent_fields(event: str, entry: dict) -> set[str]:
    """Return the fields absent from this producer's inspected call site."""
    known = {"parent_session_id", "sender_id", "session_key", "cwd", "workspace",
             "authenticated_origin", "delivery_receipt"}
    return known - set(entry["kwargs"])


def _load_plugin(root: Path, name: str):
    path = root / ".hermes" / "plugins" / "plumb" / "plugin.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Context:
    def __init__(self) -> None:
        self.hooks: dict[str, object] = {}

    def register_hook(self, event: str, callback) -> None:
        self.hooks[event] = callback

    def register_skill(self, *_args, **_kwargs) -> None:
        pass

    def register_command(self, *_args, **_kwargs) -> None:
        pass


class _DispatchCapture:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, _argv, *, input=None, cwd=None, **_kwargs):
        self.calls.append({"kind": "run", "payload": json.loads(input), "cwd": cwd})
        return SimpleNamespace(stdout=json.dumps({"agent_context": [], "owner_lines": [],
                                                  "block": None, "status_line": ""}))

    def popen(self, _argv, *, stdin=None, cwd=None, **_kwargs):
        capture = self

        class _Child:
            def __init__(self) -> None:
                self.stdin = self

            def write(self, text: str) -> None:
                capture.calls.append({"kind": "popen", "payload": json.loads(text),
                                      "cwd": cwd})

            def close(self) -> None:
                pass

        return _Child()


def _replay_callbacks(data: dict) -> dict:
    from plumb.hosts.hermes import install as hermes_install

    with tempfile.TemporaryDirectory(prefix="plumb-hermes-hook-") as temporary:
        root_a, root_b = (Path(temporary) / "A", Path(temporary) / "B")
        for root in (root_a, root_b):
            (root / ".plumb").mkdir(parents=True)
            hermes_install.install(root, launcher="path")
        plugin_a = _load_plugin(root_a, "plumb_plugin_a")
        plugin_b = _load_plugin(root_b, "plumb_plugin_b")
        ctx_a, ctx_b = _Context(), _Context()
        plugin_a.register(ctx_a)
        plugin_b.register(ctx_b)
        capture = _DispatchCapture()
        plugin_a.subprocess.run = capture.run
        plugin_a.subprocess.Popen = capture.popen
        plugin_b.subprocess.run = capture.run
        plugin_b.subprocess.Popen = capture.popen

        replay = {event: dict(entry["kwargs"]) for event, entry in data["events"].items()}
        cwd_before = Path.cwd()
        try:
            for module, context, root, session in (
                (plugin_a, ctx_a, root_a, "session-a"),
                (plugin_b, ctx_b, root_b, "session-b"),
            ):
                for event in ("on_session_start", "pre_llm_call", "post_tool_call",
                              "pre_verify", "transform_llm_output", "post_llm_call"):
                    kwargs = dict(replay[event])
                    kwargs["session_id"] = session
                    if event == "post_tool_call":
                        kwargs["tool_name"] = "write_file"
                    if event == "pre_verify":
                        kwargs["attempt"] = 0
                    if event == "transform_llm_output":
                        kwargs["response_text"] = "synthetic response"
                    if event == "post_llm_call":
                        kwargs["assistant_response"] = "synthetic response"
                    assert "source" not in kwargs and "absent_fields" not in kwargs
                    os.chdir(root_b if root == root_a else root_a)
                    context.hooks[event](**kwargs)

            # This is a separately labelled synthetic extra-field boundary: the
            # supplied parent metadata must exclude a child before dispatch.
            child = dict(replay["pre_llm_call"])
            child["session_id"] = "child-a"
            child["parent_session_id"] = "parent-a"
            before_child = len(capture.calls)
            ctx_a.hooks["pre_llm_call"](**child)
            explicit_parent_child_excluded = len(capture.calls) == before_child

            # A parentless supplied cron-shaped event still dispatches; no origin
            # field is supplied, so this is a counterexample, not authentication.
            cron = dict(replay["post_llm_call"])
            cron["session_id"] = "cron-1"
            ctx_a.hooks["post_llm_call"](**cron)
        finally:
            os.chdir(cwd_before)

        for call in capture.calls:
            assert "absent_fields" not in call["payload"]
            assert call["payload"]["cwd"] == call["cwd"]
        a_calls = [call for call in capture.calls if call["cwd"] == str(root_a)]
        b_calls = [call for call in capture.calls if call["cwd"] == str(root_b)]
        assert a_calls and b_calls
        assert all(call["payload"]["cwd"] == str(root_a) for call in a_calls)
        assert all(call["payload"]["cwd"] == str(root_b) for call in b_calls)
        return {"dispatches": len(capture.calls),
                "explicit_parent_child_excluded": explicit_parent_child_excluded,
                "parentless_cron_dispatched": any(
                    call["payload"].get("session_id") == "cron-1"
                    for call in capture.calls)}


def main() -> int:
    fixture = Path(__file__).with_name("hook_payloads.json")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    _assert_fixture(data)
    evidence = _replay_callbacks(data)
    print(json.dumps({"events": len(data["events"]), "boundary_cases": 4,
                      "parentless_cron_authenticated": False, **evidence}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
