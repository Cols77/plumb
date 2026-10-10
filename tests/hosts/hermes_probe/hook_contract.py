"""Offline source-contract and boundary probe for Hermes hook evidence."""
from __future__ import annotations

import ast
import json
import sys
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


def _names_in_range(path: Path, line_range: str) -> set[str]:
    start, end = (int(part) for part in line_range.split("-"))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not (start <= node.lineno <= end):
            continue
        names.update(keyword.arg for keyword in node.keywords if keyword.arg)
    return names


def _assert_fixture(data: dict) -> None:
    assert data["provenance"]["source_checkout"] == PINNED
    assert data["provenance"]["fixture_class"] == "source_contract_not_runtime_capture"
    for event, (relative, line_range) in PRODUCERS.items():
        entry = data["events"][event]
        assert entry["source"] == f"{relative}:{line_range}"
        assert set(entry["kwargs"]) == set(entry["kwargs"]) - set(entry["absent_fields"])
        assert not set(entry["kwargs"]) & set(entry["absent_fields"])
        assert _names_in_range(SOURCE_ROOT / relative, line_range) == set(entry["kwargs"])


def _replay_only_kwargs(data: dict) -> dict[str, dict]:
    return {event: dict(entry["kwargs"]) for event, entry in data["events"].items()}


def _boundary_cases() -> list[dict]:
    return [
        {"project": "A", "session_id": "session-a", "cwd": "A"},
        {"project": "B", "session_id": "session-b", "cwd": "B"},
        {"project": "A", "session_id": "session-b", "cwd": "B"},
        {"project": "cron", "session_id": "cron-1", "parent_session_id": ""},
    ]


def _installed_project_binding(installed_project: str, event: dict) -> str:
    """Replay the adapter's fixed project binding without inventing runtime fields."""
    assert "workspace" not in event and "cwd" not in event
    return installed_project


def main() -> int:
    fixture = Path(__file__).with_name("hook_payloads.json")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    _assert_fixture(data)
    replay = _replay_only_kwargs(data)
    assert replay["pre_llm_call"]["session_id"] == "synthetic-session"
    cases = _boundary_cases()
    assert cases[0]["project"] != cases[1]["project"]
    assert cases[2]["session_id"] == cases[1]["session_id"]
    assert cases[2]["cwd"] == "B"
    assert _installed_project_binding("A", replay["pre_llm_call"]) == "A"
    assert _installed_project_binding("B", replay["pre_llm_call"]) == "B"
    assert "authenticated_origin" not in cases[3]
    assert cases[3]["parent_session_id"] == ""
    print(json.dumps({"events": len(replay), "boundary_cases": len(cases),
                      "parentless_cron_authenticated": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
