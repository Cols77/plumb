"""SR-380 EX-2, EX-3: a frozen part (the Codex and Hermes adapters, the benchmark) counts in no
drift, brief or merge hold while Claude Code is the agent; it wakes when its host is."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from merge.merge_helpers import commit, project, write

from plumb import cli
from plumb.api import open_core
from plumb.commands import status_data

pytestmark = pytest.mark.sr("SR-380")

FREEZE = "freeze:\n  - src/hosts/codex\n  - tests/hosts/test_codex.py\n"
SR = """---
id: SR-001
title: The Codex adapter shows the brief
statement: The Codex adapter shows the brief.
examples:
- {id: EX-1, given: a session, when: it starts, then: the brief shows}
---
"""
INT = "---\nid: INT-001\ntitle: Hosts\nquote: q\nreadback: Hosts.\n---\n"


def _adapter(repo: Path) -> None:
    write(repo, ".plumb/intents/INT-001.md", INT)
    write(repo, ".plumb/requirements/SR-001.md", SR)
    write(repo, "src/hosts/codex/adapter.py", "def brief():\n    return 1\n")
    write(repo, "tests/hosts/test_codex.py", "def test_brief():\n    assert True\n")
    write(repo, ".plumb/config.yaml", FREEZE)
    root = ["--root", str(repo)]
    assert cli.main(["link", "SR-001", "derives_from", "INT-001", *root]) == 0
    assert cli.main(["link", "SR-001", "implemented_by", "src/hosts/codex/adapter.py",
                     *root]) == 0
    assert cli.main(["link", "SR-001", "verified_by", "tests/hosts/test_codex.py",
                     "--example", "EX-1", *root]) == 0
    write(repo, "src/hosts/codex/adapter.py", "def brief():\n    return 2\n")   # the edit


def _drift(repo: Path, capsys) -> dict:
    capsys.readouterr()
    cli.main(["drift", "--json", "--root", str(repo)])
    return json.loads(capsys.readouterr().out)


def test_ex2_a_sleeping_part_counts_no_stale_link_in_drift_or_brief(
        repo: Path, write_record, capsys) -> None:
    _adapter(repo)
    assert _drift(repo, capsys)["stale"] == []
    capsys.readouterr()
    assert cli.main(["brief", "--root", str(repo)]) == 0
    assert "drift: stale 0 |" in capsys.readouterr().out


def test_ex2_a_sleeping_part_holds_no_merge_and_owes_no_evidence(repo: Path, capsys) -> None:
    project(repo)
    write(repo, ".plumb/config.yaml", "verify:\n  flaky_rerun: false\n"
          "freeze:\n  - src/pkg/mod.py\n  - tests/test_mod.py\n")
    sha = commit(repo, "project")
    write(repo, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    capsys.readouterr()
    cli.main(["merge-check", sha, "--no-run", "--json", "--root", str(repo)])
    report = json.loads(capsys.readouterr().out)
    assert report["stale_links"] == [] and report["untested_links"] == []
    from plumb.verify import open_verify

    assert open_verify(open_core(repo)).unverified_acceptance(["SR-001"]) == {}


def test_ex2_a_frozen_record_waits_on_no_judge(repo: Path, write_record) -> None:
    write_record(repo, SR.replace("id: SR-001", "id: SR-001\nfrozen: true"))
    write_record(repo, SR.replace("SR-001", "SR-002"))
    data = status_data(open_core(repo))
    assert data["awaiting"] == ["SR-002"] and data["records"]["requirement"] == 1


def test_ex3_the_host_working_on_plumb_wakes_its_part(
        repo: Path, write_record, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    _adapter(repo)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "codex")
    assert [d["target"] for d in _drift(repo, capsys)["stale"]] == [
        "src/hosts/codex/adapter.py"]
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "hermes")      # another host's marker: still asleep
    assert _drift(repo, capsys)["stale"] == []


@pytest.mark.sr("SR-254")
def test_dec_404_a_failing_frozen_test_makes_no_full_run_red(repo: Path) -> None:
    """DEC-404, SR-380: a test in a frozen part counts in no merge hold, so a full run whose
    only failure is in a sleeping part is a pass, and the failure is not listed."""
    from types import SimpleNamespace

    from plumb.boundary import fullrun

    write(repo, ".plumb/config.yaml", "freeze:\n  - tests/hosts/test_codex.py\n")
    core = open_core(repo)
    frozen_id, live_id = "tests/hosts/test_codex.py::test_brief", "tests/test_mod.py::test_add"
    nodes = [{"id": frozen_id, "outcome": "failed"}, {"id": live_id, "outcome": "passed"}]
    payload = {"nodes": nodes, "exit_status": 1, "full": True}
    assert fullrun.clean_pass(payload, core) and not fullrun.completed_red(payload, core)
    nodes[1]["outcome"] = "failed"          # a live failure still makes it red
    assert fullrun.completed_red(payload, core) and not fullrun.clean_pass(payload, core)
    result = SimpleNamespace(failed=[frozen_id], run_id="r1")
    assert fullrun.verdict_of(result, core) == "passed"
    result.failed.append(live_id)
    assert fullrun.verdict_of(result, core) == "failed"
    assert fullrun.live_failures([frozen_id, live_id], core) == [live_id]
