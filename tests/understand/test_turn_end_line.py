"""Slice 4 (INT-090): the end-of-turn text goes. The owner gets at most one plumb line, or
nothing (SR-265); every card, stale link, untraced file and warning goes to the agent's
channel as text (SR-266); what only the owner can settle is tagged for the agent to ask with
the question tool (SR-295)."""

from __future__ import annotations

import io
import json
import re
import subprocess
import time
from pathlib import Path

import pytest
from host.fakes import FakeVerify
from mergedriver.mdhelpers import conflicted
from mod.helpers import SESSION, sample_card
from understand.test_read_job import make_core, open_card, record_text

from plumb import approvals
from plumb.api import open_core
from plumb.config import CARD_RETIRED
from plumb.contracts import NodeEvidence, Target, TurnEvent
from plumb.hosts import neutral
from plumb.hosts.claude_code import stop
from plumb.present.owner_text import JUDGE_APPROVED
from plumb.understand import summary

IDS = re.compile(r"\b(IC|SR|INT|DEC|FEAT)-\d+")
FEAT = "---\nid: FEAT-001\ntitle: deadline reminders\n---\n"


def _start_turn(root: Path) -> None:
    path = root / ".plumb" / "session" / SESSION / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}), "utf-8")


def _edit(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, "utf-8")
    with (root / ".plumb" / "session" / SESSION / "touched.txt").open("a", encoding="utf-8") as f:
        f.write(rel + "\n")


def _stop(root: Path, hook_input, verify=None, active: bool = False) -> dict:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=SESSION, stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=root,
                     verify=verify if verify is not None else FakeVerify(), unjudged=None) == 0
    return json.loads(out.getvalue()) if out.getvalue().strip() else {}


def _owner(data: dict) -> str:
    assert data.get("decision") != "block", data
    return str(data.get("systemMessage") or "")


def _agent(root: Path) -> str:
    """The agent's channel: what the stop queued for the next prompt, taken once."""
    path = root / ".plumb" / "session" / SESSION / "agent_notes.json"
    if not path.exists():
        return ""
    notes = json.loads(path.read_text("utf-8"))
    path.unlink()
    return "\n".join(notes)


@pytest.fixture
def carded(repo: Path, write_record):
    """A project with one card waiting for the owner (a question the turn raised)."""
    core = make_core(repo, write_record, [FEAT, record_text(1), record_text(2)])
    open_card(core, sample_card(core, "SR-001"))
    return core


@pytest.fixture
def confirmed(repo: Path, write_record) -> Path:
    """A confirmed requirement of the deadline reminders, its code committed."""
    make_core(repo, write_record, [FEAT, record_text(1, "Reminders before a deadline")])
    (repo / "src").mkdir()
    (repo / "src" / "remind.py").write_text("def remind():\n    return 1\n", "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/remind.py"))
    approvals.approve(open_core(repo), ["SR-001"])
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "setup"], cwd=repo, check=True,
                   capture_output=True)
    return repo


# --------------------------------------------------------------------------- SR-265


@pytest.mark.sr("SR-265")
def test_sr265_ex4_a_turn_where_nothing_changed_for_the_owner_prints_nothing(
        carded, hook_input) -> None:
    """SR-265 EX-4: the same card still waiting is no change: nothing is printed."""
    _start_turn(carded.root)
    _stop(carded.root, hook_input)
    assert _stop(carded.root, hook_input) == {}


@pytest.mark.sr("SR-265")
def test_sr265_ex6_an_ordinary_turn_shows_no_note(confirmed: Path, hook_input) -> None:
    """SR-265 EX-6: an ordinary turn with nothing that matters: no note at all."""
    _start_turn(confirmed)
    _edit(confirmed, "docs/notes.md", "notes\n")
    assert _stop(confirmed, hook_input) == {}


@pytest.mark.sr("SR-265")
def test_sr265_ex7_a_judge_approval_gets_no_line_and_no_question(
        repo: Path, write_record, hook_input, monkeypatch) -> None:
    """SR-265 EX-7: a requirement the judge approved, nothing confirmed touched: no line."""
    make_core(repo, write_record, [FEAT])
    monkeypatch.setattr(summary, "_confirmations",
                        lambda *a, **k: (f"1 {JUDGE_APPROVED}",))
    _start_turn(repo)
    _edit(repo, ".plumb/requirements/SR-009.md", record_text(9))
    assert _stop(repo, hook_input) == {}
    summary.after_stop(open_core(repo), SESSION)   # SR-375: the worker tells the agent
    assert JUDGE_APPROVED in _agent(repo)


# --------------------------------------------------------------------------- SR-266


@pytest.mark.sr("SR-266")
def test_sr266_ex2_stale_links_untraced_files_and_warnings_go_to_the_agent(
        confirmed: Path, hook_input, monkeypatch) -> None:
    """SR-266 EX-2: the agent's channel names them; the owner's text is at most one line."""
    from plumb.awareness import turn as awareness
    from plumb.present.delta import Line

    warning = "plumb: SR-001 is also being changed on branch feat-x"
    stale_note = "plumb: SR-001's link to src/remind.py is stale"
    monkeypatch.setattr(awareness, "at_stop", lambda *a, **k: [Line(warning)])
    monkeypatch.setattr(stop, "stale_hold", lambda *a, **k: ([], [stale_note]))
    _start_turn(confirmed)
    _edit(confirmed, "src/other.py", "x = 1\n")
    owner = _owner(_stop(confirmed, hook_input))
    assert len(owner.splitlines()) <= 1 and "feat-x" not in owner and "stale" not in owner
    agent = _agent(confirmed)
    # SR-373: one next action; the untraced file comes before the links it moved
    assert warning in agent and stale_note not in agent
    untraced = json.loads((confirmed / ".plumb" / "session" / SESSION /
                           "untraced.json").read_text("utf-8"))
    assert untraced["paths"] == ["src/other.py"]          # the next prompt names it


@pytest.mark.sr("SR-266")
def test_sr266_ex3_the_retired_card_setting_is_told_to_the_agent_once(carded) -> None:
    """SR-266 EX-3: full/compact/off has no effect and nothing is told about it."""
    (carded.root / ".plumb" / "config.yaml").write_text("present:\n  card: compact\n", "utf-8")

    def stop_cli():
        _start_turn(carded.root)
        return neutral.handle_event(TurnEvent(kind="stop", root=carded.root,
                                              session_id=SESSION, host="cli"),
                                    verify=FakeVerify(), unjudged=None)

    first = stop_cli()
    assert first.owner_lines == ()       # no effect on the owner
    assert not any(CARD_RETIRED in line for line in first.agent_context)


@pytest.mark.sr("SR-266")
def test_sr266_ex4_the_agent_keeps_the_conflict_id_the_owner_sees_none(
        repo: Path, hook_input, capsys) -> None:
    """SR-266 EX-4: `plumb conflicts` gives the agent the id; the owner's line has none."""
    from plumb import cli

    ic = conflicted(repo)
    _start_turn(repo)
    owner = _owner(_stop(repo, hook_input))
    assert "merge waits" in owner and not IDS.search(owner)   # SR-373: a merge that waits
    assert cli.main(["conflicts", "--root", str(repo)]) == 0
    assert ic in capsys.readouterr().out


@pytest.mark.sr("SR-266")
def test_sr266_ex6_a_test_that_passed_and_fails_now_reaches_the_agent_with_its_evidence(
        confirmed: Path, hook_input) -> None:
    """SR-266 EX-6: the evidence line (passed earlier, fails now) is given as text."""
    node = "tests/test_r.py::test_r"
    (confirmed / "tests").mkdir()
    (confirmed / "tests" / "test_r.py").write_text("def test_r():\n    assert 0\n", "utf-8")
    verify = FakeVerify(nodes=(node,), evidence_map={node: NodeEvidence(
        node, "fresh-fail", regression=True, last_run="run-2")})
    _start_turn(confirmed)
    _edit(confirmed, "src/remind.py", "def remind():\n    return 2\n")
    block = _stop(confirmed, hook_input, verify)
    assert block["decision"] == "block"
    assert f"{node} passed in an earlier run and now fails (last run run-2)" in block["reason"]
    owner = _owner(_stop(confirmed, hook_input, verify, active=True))
    assert len(owner.splitlines()) <= 1 and node not in owner
    assert node not in _agent(confirmed)   # SR-373 EX-7: the block told it; not repeated


# --------------------------------------------------------------------------- SR-295


@pytest.mark.sr("SR-295")
def test_sr295_ex1_an_open_conflict_is_handed_to_the_agent_to_ask(repo: Path,
                                                                   hook_input) -> None:
    """SR-295 EX-1: the owner's text carries no question count; the agent gets the
    conflict with the instruction to ask it with the question tool. The owner may see
    SR-373's one line that a merge waits, never a count of questions."""
    conflicted(repo)
    _start_turn(repo)
    assert "question" not in _owner(_stop(repo, hook_input))
    agent = _agent(repo)
    assert summary.ASK_OWNER in agent and "relay checks" in agent
    assert "question tool" in summary.ASK_OWNER


@pytest.mark.sr("SR-295")
def test_sr295_ex3_stale_links_and_untraced_files_alone_show_the_owner_nothing(
        confirmed: Path, hook_input, monkeypatch) -> None:
    """SR-295 EX-3: what the agent can fix is the agent's: the owner sees nothing."""
    stale_note = "plumb: SR-001's link to src/remind.py is stale"
    monkeypatch.setattr(stop, "stale_hold", lambda *a, **k: ([], [stale_note]))
    _start_turn(confirmed)
    # a traced file: an untraced one would be SR-373's next action before the stale link
    _edit(confirmed, "src/remind.py", "def remind():\n    return 2\n")
    assert _stop(confirmed, hook_input) == {}
    assert stale_note in _agent(confirmed)
    assert summary.ASK_OWNER not in stale_note


@pytest.mark.sr("SR-295")
def test_sr295_a_card_only_in_the_agents_channel_is_not_shown_to_the_owner(tmp_path: Path
                                                                           ) -> None:
    """A card the stop drew went to the agent alone: a bare 'ok' must not confirm it. Only
    plumb's panel, active this turn, puts the drawn card before the owner."""
    from types import SimpleNamespace

    session_dir = tmp_path / ".plumb" / "session" / SESSION
    session_dir.mkdir(parents=True)
    ctx = SimpleNamespace(root=tmp_path, session_id=SESSION, session_dir=session_dir,
                          extra={"display": "owner"})
    turn = {"turn_start": time.time() - 0.5, "prompt_digest": "sha256:" + "a" * 64}
    index = {"SR-001": SimpleNamespace(hash="sha256:1")}

    def stated() -> list:
        stop.write_stated(ctx, turn, index, ["SR-001"], {"SR-001": "sha256:1"})
        data = json.loads((session_dir / "stated.json").read_text("utf-8"))
        return [(r["id"], r["shown"]) for r in data["records"]]

    assert stated() == [("SR-001", False)]
    (session_dir / "mod.json").write_text(json.dumps({
        "active": True, "heartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}),
        "utf-8")
    assert stated() == [("SR-001", True)]

