"""SR-104: the job id and file format (plan 3.2 item 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.understand import files, jobs

pytestmark = pytest.mark.sr("SR-273")

INPUTS = {"message": {"digest": "sha256:a", "text": "yes please"}, "shown": []}


def test_id_is_stable_for_equal_inputs() -> None:
    a = jobs.new_job("read", "s1", "read.v1", INPUTS)
    b = jobs.new_job("read", "s2", "read.v1", {"shown": [], "message": dict(INPUTS["message"])})
    assert a.id == b.id and a.id.startswith("read-") and len(a.id) == len("read-") + 16
    assert a.inputs_digest == files.digest_of(INPUTS)
    assert jobs.new_job("read", "s1", "read.v1", {**INPUTS, "shown": [{"id": "SR-1"}]}).id != a.id
    assert jobs.new_job("judge", "s1", "read.v1", INPUTS).id != a.id


def test_needs_is_part_of_the_id() -> None:
    plain = jobs.new_job("clarify", "s1", "clarify.v1", INPUTS)
    after = jobs.new_job("clarify", "s1", "clarify.v1", INPUTS, needs="read-0123456789abcdef")
    other = jobs.new_job("clarify", "s1", "clarify.v1", INPUTS, needs="read-fedcba9876543210")
    assert plain.needs is None and after.needs == "read-0123456789abcdef"
    assert len({plain.id, after.id, other.id}) == 3


def test_job_file_round_trips_and_lists_in_created_order(tmp_path: Path) -> None:
    late = jobs.new_job("read", "s1", "read.v1", {"n": 1}, created="2026-01-02T00:00:00Z")
    early = jobs.new_job("read", "s1", "read.v1", {"n": 2}, created="2026-01-01T00:00:00Z")
    for job in (late, early):
        files.write_json_atomic(jobs.job_path(tmp_path, "s1", job.id), files.job_to_json(job))
    assert [j.id for j in jobs.queued(tmp_path, "s1")] == [early.id, late.id]
    assert jobs.load(tmp_path, "s1", late.id) == late
    assert jobs.load(tmp_path, "s1", "read-0000000000000000") is None
    assert jobs.queued(tmp_path, "nobody") == []


def test_a_result_counts_only_with_the_workers_ledger_entry(tmp_path: Path) -> None:
    from plumb.contracts import JobResult
    from plumb.understand import ledger

    job = jobs.new_job("read", "s1", "read.v1", {"n": 1})
    assert jobs.result(tmp_path, "s1", job.id) is None
    files.write_json_atomic(files.results_dir(tmp_path, "s1") / f"{job.id}.json",
                            files.result_to_json(JobResult(job=job.id, status="ok")))
    assert jobs.result(tmp_path, "s1", job.id) is None          # written by someone else
    assert jobs.result(tmp_path, "s1", job.id, trusted=False).status == "ok"
    ledger.record(tmp_path, "s1", job.id)
    assert jobs.result(tmp_path, "s1", job.id).status == "ok"
