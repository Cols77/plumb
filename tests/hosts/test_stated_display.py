"""The stated set marks a record ``shown`` only when the owner sees the stop's summary, on
every stop entry point (sp4 5, R2, R13 Q4): the stated set's one writer
(``stop.write_stated``) applies the ``display`` each entry point gives ``handle_event``.

Entry points: the CLI-only fallback ``iaso turn end`` and a host's Stop hook (``owner``:
the summary is shown), Codex's ``notify`` (``status``: a refresh the owner never sees, which
leaves the stated set alone) and ``iaso hook stop --unseen`` (the host could not show it).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from hosts_helpers import make_project

from iaso.api import open_core
from iaso.cli import main
from iaso.hosts.common import instruction_block

pytestmark = pytest.mark.sr("SR-282")


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    make_project(repo, write_record, decision=False)
    monkeypatch.chdir(repo)
    return repo


def _stated(repo: Path) -> dict:
    return json.loads((repo / ".iaso" / "session" / "stated.json").read_text("utf-8"))


def _edit_record(repo: Path) -> None:
    record = next((repo / ".iaso").rglob("SR-001.md"))
    record.write_text(record.read_text("utf-8").replace(
        "add returns the sum.", "add returns the sum of two numbers."), "utf-8")


def _hook(monkeypatch, capsys, args: list[str], data: dict) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    assert main(["hook", *args]) == 0
    capsys.readouterr()


def _last_prompt(repo: Path) -> dict:
    path = repo / ".iaso" / "session" / "prompts.jsonl"
    return json.loads(path.read_text("utf-8").splitlines()[-1])


@pytest.mark.sr("SR-283")
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
    from iaso.understand import read

    assert read.shown_items(open_core(project), _last_prompt(project)["at"]) == []


def test_fallback_block_tells_the_agent_to_show_the_summary() -> None:
    block = instruction_block(["iaso"], "codex", hooks=True)
    assert "Put the summary `turn end`" in block and "only what the owner saw" in block
