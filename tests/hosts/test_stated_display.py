"""The stated set marks a record ``shown`` only when the owner sees the stop's summary, on
every stop entry point (sp4 5, R2, R13 Q4): the stated set's one writer
(``stop.write_stated``) applies the ``display`` each entry point gives ``handle_event``.

Entry points: the CLI-only fallback ``plumb turn end`` and a host's Stop hook (``owner``:
the summary is shown), Codex's ``notify`` (``status``: a refresh the owner never sees, which
leaves the stated set alone) and ``plumb hook stop --unseen`` (the host could not show it).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from hosts_helpers import make_project

from plumb.api import open_core
from plumb.cli import main
from plumb.hosts.common import instruction_block

pytestmark = pytest.mark.sr("SR-053")


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    make_project(repo, write_record, decision=False)
    monkeypatch.chdir(repo)
    return repo


def _stated(repo: Path) -> dict:
    return json.loads((repo / ".plumb" / "session" / "stated.json").read_text("utf-8"))


def _edit_record(repo: Path) -> None:
    record = next((repo / ".plumb").rglob("SR-001.md"))
    record.write_text(record.read_text("utf-8").replace(
        "add returns the sum.", "add returns the sum of two numbers."), "utf-8")


def _hook(monkeypatch, capsys, args: list[str], data: dict) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    assert main(["hook", *args]) == 0
    capsys.readouterr()


def _last_prompt(repo: Path) -> dict:
    path = repo / ".plumb" / "session" / "prompts.jsonl"
    return json.loads(path.read_text("utf-8").splitlines()[-1])


def _turn_end_then_ok(repo: Path, monkeypatch, capsys, *, notify: bool) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("change add"))
    assert main(["turn", "start", "--session", "s1"]) == 0
    _edit_record(repo)
    assert main(["turn", "end", "--session", "s1"]) == 0
    before = _stated(repo)
    assert before["records"] == [{"id": "SR-001", "hash": before["records"][0]["hash"],
                                  "shown": True}]
    if notify:  # Codex's notify program: the turn's JSON as the last argument
        payload = json.dumps({"type": "agent-turn-complete", "thread-id": "codex-thread-1",
                              "cwd": str(repo)})
        assert main(["hook", "stop", "--host", "codex", "--format", "text", "--notify",
                     payload]) == 0
        assert _stated(repo) == before  # a status refresh never rewrites the stated set
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO("ok"))
    assert main(["turn", "start", "--session", "s1"]) == 0
    from plumb.understand import read

    last = _last_prompt(repo)
    assert last["via"] == "turn"  # R13 Q4: the fallback's message is labelled as such
    assert [i["id"] for i in read.shown_items(open_core(repo), last["at"])] == ["SR-001"]


def test_turn_end_marks_the_shown_summary(project: Path, monkeypatch, capsys) -> None:
    _turn_end_then_ok(project, monkeypatch, capsys, notify=False)


@pytest.mark.sr("SR-054")
def test_codex_notify_leaves_the_stated_set(project: Path, monkeypatch, capsys) -> None:
    """R13 Q4 on Codex's fallback: notify after `turn end` must not wipe what a chat "ok"
    confirms."""
    _turn_end_then_ok(project, monkeypatch, capsys, notify=True)


@pytest.mark.sr("SR-054")
def test_codex_stop_hook_marks_the_shown_summary(project: Path, monkeypatch,
                                                 capsys) -> None:
    _hook(monkeypatch, capsys, ["prompt", "--host", "codex", "--format", "claude"],
          {"session_id": "c1", "prompt": "change add", "cwd": str(project)})
    _edit_record(project)
    _hook(monkeypatch, capsys, ["stop", "--host", "codex", "--format", "claude"],
          {"session_id": "c1", "stop_hook_active": False, "cwd": str(project)})
    stated = _stated(project)
    assert stated["session"] == "c1"
    assert [(r["id"], r["shown"]) for r in stated["records"]] == [("SR-001", True)]


@pytest.mark.sr("SR-056")
def test_unseen_stop_marks_nothing_shown(project: Path, monkeypatch, capsys) -> None:
    """A host that could not show the summary (Hermes without it in the reply): a bare "ok"
    relays nothing it never saw."""
    _hook(monkeypatch, capsys, ["prompt", "--host", "hermes", "--format", "json"],
          {"session_id": "h1", "text": "change add", "cwd": str(project)})
    _edit_record(project)
    _hook(monkeypatch, capsys, ["stop", "--host", "hermes", "--format", "json", "--unseen"],
          {"session_id": "h1", "stop_active": True, "cwd": str(project)})
    assert [(r["id"], r["shown"]) for r in _stated(project)["records"]] == [("SR-001", False)]
    _hook(monkeypatch, capsys, ["prompt", "--host", "hermes", "--format", "json"],
          {"session_id": "h1", "text": "ok", "cwd": str(project)})
    from plumb.understand import read

    assert read.shown_items(open_core(project), _last_prompt(project)["at"]) == []


def test_fallback_block_tells_the_agent_to_show_the_summary() -> None:
    block = instruction_block(["plumb"], "codex", hooks=True)
    assert "Put the summary `turn end`" in block and "only what the owner saw" in block
