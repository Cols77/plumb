"""One host-neutral turn API: the same session gives the same output on every host
(sp4 5, SR-053 EX-1)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from hosts_helpers import QuietVerify, make_project, scripted_judge

from plumb.contracts import TurnEvent
from plumb.hosts.neutral import HOSTS, SELF_RECORDING_HOSTS, handle_event

pytestmark = pytest.mark.sr("SR-282")


def _session(root: Path, host: str) -> list[tuple]:
    verify = QuietVerify()

    def event(kind: str, **fields) -> tuple:
        out = handle_event(TurnEvent(kind=kind, root=root, session_id="s1", host=host,
                                     **fields), verify=verify, backend=None, unjudged=None)
        return (out.agent_context, out.owner_lines, out.block)

    steps = [event("session-start", source="startup"),
             event("prompt", text="make SR-001 accept integers only")]
    (root / "src" / "calc.py").write_text("def add(a, b):\n    return int(a) + int(b)\n",
                                          "utf-8")
    steps.append(event("edit", path="src/calc.py"))
    steps.append(event("stop"))
    steps.append(event("stop", stop_active=True))
    return steps


def test_same_output_for_every_host(repo: Path, write_record, tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    make_project(repo, write_record)
    scripted_judge(monkeypatch, tmp_path)
    results = {}
    for host in HOSTS:
        copy = tmp_path / f"copy-{host}"
        shutil.copytree(repo, copy)
        results[host] = _session(copy, host)
    first = results[HOSTS[0]]
    assert any("SR-001" in line for line in first[1][0])  # the delta reached the agent
    assert first[3][2] and "stale" in first[3][2]         # the stale-link hold blocked once
    assert first[4][2] is None                            # never while continuing
    for host in HOSTS[1:]:
        got = results[host]
        if host in SELF_RECORDING_HOSTS:
            # SR-173: plumb turn end is the agent's channel, so the note the released hold
            # queues for the next prompt reaches the agent at the stop itself
            assert any("held the turn open" in line for line in got[4][0]), host
            got = [*got[:4], (first[4][0], *got[4][1:])]
        assert got == first, host


def test_no_adapter_imports_another_adapter() -> None:
    """sp4 8.5: adapters share only plumb.hosts.common and plumb.hosts.neutral."""
    import re

    import plumb.hosts as hosts

    base = Path(hosts.__file__).parent
    for adapter in ("codex", "pi", "hermes"):
        for path in (base / adapter).rglob("*.py"):
            text = path.read_text("utf-8")
            others = {"codex", "pi", "hermes", "claude_code"} - {adapter}
            for other in others:
                assert not re.search(rf"plumb\.hosts\.{other}\b", text), (path, other)
