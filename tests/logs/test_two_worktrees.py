"""SP6 6.2: appends in two worktrees merge without a conflict (SR-073 EX-1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from logutil import entries

from logs.gitrepo import add_worktree, commit_all, make_repo, run_git
from plumb import approvals, log
from plumb.api import open_core
from plumb.validate import validate

pytestmark = pytest.mark.sr("SR-232")

SR = ("---\nid: SR-00{n}\ntitle: Requirement {n}\nstatement: s{n}\nexamples:\n"
      "  - {{id: EX-1, given: g, when: w, then: t}}\n---\n")


def _activity(root: Path, side: str, record: str) -> None:
    core = open_core(root)
    core.log_append("events", "calibration", {"digest": f"sha256:{side}", "side": side})
    approvals.approve(open_core(root), [record])
    core.log_append("evidence", "test-run", {
        "run_id": f"run-{side}", "env": {"env_key": "E"},
        "nodes": [{"id": f"tests/test_{side}.py::t", "outcome": "passed", "closure": "C",
                   "test_hash": "T"}]})


def test_appends_in_two_worktrees_merge_without_conflict(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    main = make_repo(tmp_path / "main")
    for n in (1, 2):
        path = main / ".plumb" / "requirements" / f"SR-00{n}.md"
        path.write_text(SR.format(n=n), encoding="utf-8")
    open_core(main).log_append("events", "repin", {"note": "base"})
    commit_all(main, "records")
    feat = add_worktree(main, tmp_path / "feat", "feat-x")

    _activity(main, "main", "SR-001")
    _activity(feat, "feat", "SR-002")
    commit_all(main, "main appends")
    commit_all(feat, "feat appends")

    merged = run_git(main, "merge", "--no-edit", "feat-x", check=False)
    assert merged.returncode == 0, merged.stdout + merged.stderr
    assert run_git(main, "ls-files", "-u").stdout == ""  # nothing unmerged anywhere

    core = open_core(main)
    for stream in ("events", "evidence"):
        assert log.verify_chain(core.paths, stream) == []
    errors = [f for f in validate(core) if f.severity == "error"]
    assert errors == [], errors
    prompts = {e["payload"]["side"] for e in entries(main, "events") if e["kind"] == "calibration"}
    assert prompts == {"main", "feat"}
    runs = {e["payload"]["run_id"] for e in entries(main, "evidence")}
    assert runs == {"run-main", "run-feat"}
    status = core.status(["SR-001", "SR-002"])
    assert status["SR-001"].confirmation == status["SR-002"].confirmation == "confirmed"
    # the chain forked at the merge and the next entry still chains to a real entry
    after = core.log_append("events", "repin", {"note": "after"})
    assert after.prev in {e["digest"] for e in entries(main, "events")}
