"""SR-287: the landing's compaction moves the entries older than the records they served into
one archive segment per kind; validate checks the chain through the segments, hooks and
session start never open one, every other reader reads through them."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from mergedriver.mdhelpers import ex, record, run_git
from plumb import log
from plumb.api import open_core
from plumb.boundary import landing
from plumb.normalize import canonical_json
from plumb.validate import validate

pytestmark = pytest.mark.sr("SR-287")

OLD, LATER = "2026-10-01T10:00:00Z", "2026-10-20T00:00:00Z"
_N = itertools.count(1)


def put(root: Path, kind: str, payload: dict[str, Any], *, at: str = OLD,
        prev: str | None = None) -> dict[str, Any]:
    """Write one entry file as ``log.append`` would, at a chosen time."""
    entry: dict[str, Any] = {"v": 1, "kind": kind, "at": at, "marker": "none",
                             "payload": payload, "prev": prev}
    entry["digest"] = log.entry_digest(entry)
    stamp = at.replace("-", "").replace(":", "").rstrip("Z")
    folder = root / ".plumb" / "log" / kind
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stamp}.{next(_N):06d}Z-{entry['digest'][7:15]}.json").write_bytes(
        canonical_json(entry) + b"\n")
    return entry


def superseding(root: Path, write_record) -> None:
    """SR-001 superseded by SR-002."""
    write_record(root, record("SR-001", "old rule", statement="s", examples=[ex(1)]))
    write_record(root, record("SR-002", "new rule", statement="s", examples=[ex(1)],
                              links=[{"kind": "supersedes", "to": "SR-001"}]))


def compact(root: Path, since: str = LATER) -> list[str]:
    core = open_core(root)
    names = {e.name for s in log.STREAMS for e in core.log_read(s) if ":" not in e.name}
    return log.archive(core.paths, landing.compaction(core, since, names))


def live(root: Path, kind: str) -> list[str]:
    return sorted(p.name for p in (root / ".plumb" / "log" / kind).glob("*.json"))


def segment(root: Path, kind: str) -> list[dict[str, Any]]:
    path = root / ".plumb" / "log" / kind / log.SEGMENT
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def errors(root: Path) -> list[str]:
    return [f.line() for f in validate(open_core(root)) if f.severity == "error"]


def test_ex1_judgments_of_superseded_records_go_to_the_segment(repo: Path, write_record) -> None:
    superseding(repo, write_record)
    for n in range(30):
        put(repo, "judgment", {"subject": "SR-001", "n": n})
    for n in range(5):
        put(repo, "judgment", {"subject": "SR-002", "n": n})
    compact(repo)
    # SR-376, INT-114 (newer than SR-287's old words, DEC-400): judgment is telemetry, so every
    # entry older than the landing moves, current records or not; EX-11 holds for the other kinds
    # SR-376: judgment is telemetry, every entry older than the landing moves
    assert len(segment(repo, "judgment")) == 35
    assert len(live(repo, "judgment")) == 0
    assert errors(repo) == []


def test_ex2_a_prev_resolves_in_the_segment(repo: Path, write_record) -> None:
    superseding(repo, write_record)
    first = put(repo, "judgment", {"subject": "SR-001"})
    put(repo, "judgment", {"subject": "SR-002"}, prev=first["digest"],
        at="2026-10-25T10:00:00Z")      # newer than the landing: stays live (SR-376)
    compact(repo)
    assert len(segment(repo, "judgment")) == 1
    assert log.verify_chain(open_core(repo).paths, "events") == []


def test_ex3_an_edited_segment_entry_is_reported(repo: Path, write_record) -> None:
    superseding(repo, write_record)
    put(repo, "judgment", {"subject": "SR-001", "verdict": "yes"})
    compact(repo)
    path = repo / ".plumb" / "log" / "judgment" / log.SEGMENT
    path.write_bytes(path.read_bytes().replace(b'"yes"', b'"no"'))
    problems = log.verify_chain(open_core(repo).paths, "events")
    assert len(problems) == 1
    assert problems[0].startswith(f"judgment/{log.SEGMENT} line 1: digest sha256:")
    assert "modified entry" in problems[0]


def test_ex4_a_hook_reads_live_entry_files_only(repo: Path, write_record,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from plumb.hosts.claude_code.hookio import run_hook

    superseding(repo, write_record)
    put(repo, "judgment", {"subject": "SR-001"})
    put(repo, "judgment", {"subject": "SR-002"}, at="2026-10-25T10:00:00Z")
    compact(repo)
    opened: list[str] = []
    real = log.segment_lines
    monkeypatch.setattr(log, "segment_lines", lambda *a: opened.append("x") or real(*a))
    seen: list[int] = []

    def session_start(ctx: Any) -> None:
        core = open_core(ctx.root)
        core.brief_lines()
        seen.append(sum(e.kind == "judgment" for e in core.events()))

    stdin = io.StringIO(json.dumps({"session_id": "s1", "cwd": str(repo)}))
    run_hook("SessionStart", session_start, stdin=stdin, stdout=io.StringIO(), root=repo)
    assert seen == [1] and opened == []
    assert sum(e.kind == "judgment" for e in open_core(repo).events()) == 2  # reads through


def _run(node: str, run_id: str, outcome: str = "passed") -> dict[str, Any]:
    return {"run_id": run_id, "full": False, "env": {"env_key": "k"},
            "nodes": [{"id": node, "outcome": outcome, "closure": "c", "test_hash": "t"}]}


def test_ex5_evidence_that_keeps_a_test_fresh_stays_live(repo: Path) -> None:
    from plumb.verify.evidence import load_index

    put(repo, "test-run", _run("tests/test_a.py::test_a", "r1"))
    compact(repo)
    assert len(live(repo, "test-run")) == 1 and segment(repo, "test-run") == []
    monkey_live = log.LIVE_ONLY
    log.LIVE_ONLY = True
    try:
        index = load_index(open_core(repo))
    finally:
        log.LIVE_ONLY = monkey_live
    assert index["nodes"]["tests/test_a.py::test_a"]["last"]["run_id"] == "r1"


def test_ex6_a_branch_chained_onto_archived_entries_merges_cleanly(repo: Path,
                                                                    write_record) -> None:
    superseding(repo, write_record)
    first = put(repo, "waiver", {"subject": "SR-001"})
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "--no-verify", "-m", "records")
    run_git(repo, "checkout", "-q", "-b", "inflight")
    put(repo, "waiver", {"subject": "SR-002"}, at="2026-10-02T10:00:00Z",
        prev=first["digest"])
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "--no-verify", "-m", "branch work")
    run_git(repo, "checkout", "-q", "main")
    compact(repo)
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "--no-verify", "-m", "compaction")
    merged = run_git(repo, "merge", "-q", "--no-ff", "--no-verify", "-m", "m", "inflight",
                     check=False)
    assert merged.returncode == 0, merged.stdout + merged.stderr
    assert errors(repo) == []


def test_ex7_a_retired_records_entries_are_read_through_the_segment(repo: Path) -> None:
    put(repo, "card-settled", {"record": "SR-009", "reason": "retired: replaced"})
    compact(repo)
    assert len(segment(repo, "card-settled")) == 1 and live(repo, "card-settled") == []
    events = open_core(repo).events()
    assert [e.payload["reason"] for e in events if e.kind == "card-settled"] == \
        ["retired: replaced"]


def test_ex8_compacting_again_changes_nothing(repo: Path, write_record) -> None:
    superseding(repo, write_record)
    put(repo, "judgment", {"subject": "SR-001"})
    put(repo, "judgment", {"subject": "SR-002"}, at="2026-10-25T10:00:00Z")
    assert compact(repo)
    before = (repo / ".plumb" / "log" / "judgment" / log.SEGMENT).read_bytes()
    assert compact(repo) == []
    assert (repo / ".plumb" / "log" / "judgment" / log.SEGMENT).read_bytes() == before
    assert len(live(repo, "judgment")) == 1


def test_ex9_replaced_test_run_evidence_moves(repo: Path) -> None:
    older = put(repo, "test-run", _run("tests/test_a.py::test_a", "r1"))
    newer = put(repo, "test-run", _run("tests/test_a.py::test_a", "r2"),
                at="2026-10-02T10:00:00Z")
    compact(repo)
    assert [e["digest"] for e in segment(repo, "test-run")] == [older["digest"]]
    assert len(live(repo, "test-run")) == 1
    assert newer["digest"] in {e.digest for e in open_core(repo).log_read("evidence")}


def test_ex10_old_merge_evidence_naming_no_record_moves(repo: Path) -> None:
    put(repo, "merge-evidence", {"branch": "feat-x", "head": "abc"})
    put(repo, "merge-evidence", {"branch": "feat-y", "head": "def"}, at="2026-10-25T00:00:00Z")
    compact(repo)
    assert [e["payload"]["branch"] for e in segment(repo, "merge-evidence")] == ["feat-x"]
    assert len(live(repo, "merge-evidence")) == 1


def test_ex11_a_current_approval_and_the_prompt_it_rests_on_stay_live(
        repo: Path, write_record) -> None:
    superseding(repo, write_record)
    prompt = put(repo, "prompt", {"digest": "sha256:" + "a" * 64, "session": "s1"})
    pre = put(repo, "pre-intent", {"source": prompt["payload"]["digest"], "text": "t"})
    put(repo, "approval", {"by": "auto-model", "records": [{"id": "SR-002", "hash": "h"}],
                           "answers": [pre["digest"]]})
    assert compact(repo) == []
    assert len(live(repo, "prompt")) == len(live(repo, "pre-intent")) == 1
    assert len(live(repo, "approval")) == 1


def test_ex12_an_approval_of_a_superseded_record_moves_and_explain_still_names_it(
        repo: Path, write_record) -> None:
    from logutil import legacy_relay
    from plumb.explain import record_chain

    write_record(repo, record("SR-001", "old rule", statement="s", examples=[ex(1)]))
    legacy_relay(repo, ["SR-001"], "sha256:" + "b" * 64, "yes, that")
    write_record(repo, record("SR-002", "new rule", statement="s", examples=[ex(1)],
                              links=[{"kind": "supersedes", "to": "SR-001"}]))
    core = open_core(repo)
    said = record_chain(core, "SR-001", core.status())
    assert "confirmed by" in said[0]
    compact(repo, since=OLD)
    assert len(segment(repo, "approval")) == 1 and live(repo, "approval") == []
    core = open_core(repo)
    assert record_chain(core, "SR-001", core.status()) == said
    approval = [e for e in core.events() if e.kind == "approval"]
    assert approval and approval[0].at and approval[0].payload["by"] == "agent-relayed"


def test_ex13_calibration_counts_the_same_labelled_set_before_and_after(
        repo: Path, write_record) -> None:
    from plumb.capture.calibrate import labelled_set

    superseding(repo, write_record)
    for record_id, n in (("SR-001", 1), ("SR-001", 2), ("SR-002", 3)):
        put(repo, "rejection", {"reason": "capture-error", "by": "owner", "records": [
            {"id": record_id, "hash": f"sha256:{n}", "kind": "example-restatement",
             "premise": "the owner's words", "hypotheses": [f"will: rule {n}"]}]})

    def counted() -> tuple[int, int]:
        items = labelled_set(open_core(repo))
        return len(items), sum(i.label == "no" for i in items)

    first = counted()
    assert first[1] == 3
    compact(repo)
    assert len(segment(repo, "rejection")) == 2
    assert counted() == first
