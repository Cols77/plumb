"""R13 Q4: a chat "ok" confirms on a host without a prompt hook, and every confirmation
resting on a message the agent recorded itself (``iaso turn start``) is labelled
"self-recorded message" in iaso show, the merge-boundary glance and the host status
(sp4 3.2, SR-053). One flag written by the prose relay, which no longer exists (SR-101 EX-9);
entries it wrote stay in the log and every surface reads the flag. The tests write such an
entry with ``logutil.legacy_relay``."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest
from hosts_helpers import make_project
from logutil import legacy_relay

from iaso import approvals
from iaso.api import open_core
from iaso.cli import main
from iaso.confirm import SELF_RECORDED
from iaso.merge import merge_check

pytestmark = pytest.mark.sr("SR-282")

OK = "ok SR-001"


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> tuple[Path, str]:
    make_project(repo, write_record, decision=False)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                         text=True, check=True).stdout.strip()
    monkeypatch.chdir(repo)
    return repo, sha


def _logged(repo: Path) -> dict:
    path = repo / ".iaso" / "session" / "prompts.jsonl"
    return json.loads(path.read_text("utf-8").splitlines()[-1])


def _relay_turn_prompt(repo: Path, monkeypatch, capsys) -> None:
    """The agent records the owner's "ok" itself (iaso turn start), then relays it."""
    monkeypatch.setattr("sys.stdin", io.StringIO(OK))
    assert main(["turn", "start", "--session", "s1"]) == 0
    capsys.readouterr()
    entry = _logged(repo)
    assert entry["via"] == "turn"
    legacy_relay(repo, ["SR-001"], entry["digest"], OK, self_recorded=True)


def _relay_hook_prompt(repo: Path) -> None:
    """The host's prompt hook logged the owner's "ok"; the agent relays it."""
    path = repo / ".iaso" / "session" / "prompts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = approvals.prompt_digest(OK)
    path.write_text(json.dumps({"digest": digest, "session": "s1", "at": "t", "text": OK,
                                "via": "hook"}) + "\n", encoding="utf-8")
    legacy_relay(repo, ["SR-001"], digest, OK)


def test_relay_marks_an_approval_resting_on_a_turn_prompt(project, monkeypatch,
                                                         capsys) -> None:
    repo, _ = project
    _relay_turn_prompt(repo, monkeypatch, capsys)
    [entry] = open_core(repo).log_read("events", ["approval"])
    assert entry.payload["by"] == "agent-relayed" and entry.payload["self_recorded"] is True
    assert open_core(repo).status(["SR-001"])["SR-001"].self_recorded


def test_hook_prompt_is_not_labelled(project, capsys) -> None:
    repo, _ = project
    _relay_hook_prompt(repo)
    [entry] = open_core(repo).log_read("events", ["approval"])
    assert entry.payload["self_recorded"] is False
    assert main(["show", "SR-001"]) == 0
    assert SELF_RECORDED not in capsys.readouterr().out


def test_show_labels_self_recorded_confirmation(project, monkeypatch, capsys) -> None:
    repo, _ = project
    _relay_turn_prompt(repo, monkeypatch, capsys)
    assert main(["show", "SR-001"]) == 0
    header = capsys.readouterr().out.splitlines()[0]
    assert "confirmed" in header and SELF_RECORDED in header


def test_explain_labels_self_recorded_confirmation(project, monkeypatch, capsys) -> None:
    repo, _ = project
    _relay_turn_prompt(repo, monkeypatch, capsys)
    assert main(["explain", "SR-001"]) == 0
    assert f"(relayed), {SELF_RECORDED}" in capsys.readouterr().out


def test_merge_glance_labels_self_recorded_confirmation(project, monkeypatch,
                                                        capsys) -> None:
    repo, sha = project
    _relay_turn_prompt(repo, monkeypatch, capsys)
    merge_check(open_core(repo), sha, as_json=False)
    out = capsys.readouterr().out
    [row] = [line for line in out[out.index("approvals in range"):].splitlines()
             if "SR-001" in line and "AGENT-RELAYED" in line]
    assert SELF_RECORDED in row  # the merge boundary's glance (iaso.boundary, sp3 3.2)
    merge_check(open_core(repo), sha, as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert [a["self_recorded"] for a in data["glance"]] == [True]


@pytest.mark.parametrize("host", ["codex", "hermes"])
def test_hosts_status_counts_self_recorded_confirmations(project, monkeypatch, capsys,
                                                         host: str) -> None:
    repo, _ = project
    _relay_turn_prompt(repo, monkeypatch, capsys)
    assert main(["hosts", "status", host]) == 0
    assert f"confirmations resting on a {SELF_RECORDED}: 1" in capsys.readouterr().out
