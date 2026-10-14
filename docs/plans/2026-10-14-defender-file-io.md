# Defender file activity implementation plan

Use the subagent-driven-development workflow for implementation, followed by independent specification and code-quality review. The user approved the diagnosis and requested an isolated worktree and merge request. Running tests in other checkouts must remain untouched.

Goal: reduce repeated file operations without changing verdicts, hash-chain safety, progress liveness, or completed-job semantics. Python, pytest, and Windows Defender remain enabled and unexcluded.

Architecture: keep immutable per-entry log files. Reuse the head document inside the log lock; add batched appends that hold the lock once and invalidate the persisted head before writing a batch so interruption cannot leave a trusted stale pointer. Publish the new head after successful writes; missing-head recovery reconstructs it. Keep batches bounded and prevalidate entries and worker authority. Coalesce identical running progress updates per reporter until its heartbeat interval. Run full test passes through one real worker pass with explicit event-cache invalidation between jobs.

Alternatives considered: duplicate-read elimination alone is smallest but retains most lock/head replacements; persistent global head caches risk cross-process stale state; bounded batches with existing missing-head recovery provide larger reductions without changing the log format.

## Work board

| Item | Status | Evidence |
| --- | --- | --- |
| Isolated worktree and environment | Done | fix/defender-file-io from main fd0e10f; uv sync --frozen --offline |
| Baseline tests and operation counts | Done | Focused tests and both instrumented tests pass; baseline source hashes stable |
| Log, progress, and worker regression tests | Done | Red tests reproduced duplicate head reads, progress writes, stale events, missing batch API |
| Implementation | Done | Bounded batches, cache invalidation, progress coalescing, and full worker passes |
| Specification review | Done | Independent reviewer: SPEC_COMPLIANT; no blockers |
| Code-quality review | Done | Batch-write bypass in read-only Core facade reproduced and fixed; reviewer accepted correction, no remaining blockers |
| Final tests and operation comparison | Done with caveats | 839 passed, 5 skipped, 4 failed in broad run; timing and PATH retries pass, writer-policy failure reproduces base. Both operation probes pass; see merge request. |
| Commit and merge request proposal | Done | Review branch and local merge request proposal prepared; no remote configured, no merge performed |

## Implementation task

Files: `src/plumb/log.py`, `src/plumb/api.py`, `src/plumb/progress.py`, `src/plumb/understand/worker.py`, `tests/core/test_log*.py`, `tests/understand/test_progress*.py`, `tests/understand/test_worker*.py`, `tests/understand/test_backlog.py`.

- [x] Add failing tests that spy on real file operations: one head read for a healthy append; bounded batched lock/head updates with all entries readable and chain-valid; partial-write recovery and mixed-stream preservation; worker-only approval checks apply to batch entries.
- [x] Implement head reuse and bounded batch append. Expected interface: `log.append_many(paths, stream, entries)` where entries contain kind and payload; validate before writing, keep separate immutable entries, use one lock and one head publication per chunk. Invalidate the saved head before the first persisted entry, retaining current state in memory; never retain a stale on-disk head after partial failure.
- [x] Add failing tests for repeated identical running progress, immediate changed/final/failed state, heartbeat refresh, and retry after a failed write. Implement per-reporter semantic signature plus monotonic successful-write time; retain liveness and atomic writes.
- [x] Add a failing real multi-job worker test that requires later jobs to see earlier verdicts and the final progress to reflect the whole pass. Route worker writes through a Core API that invalidates cached events even after partial persistence. Keep queues/results/ledger trust checks intact.
- [x] Change `run_pass` to invoke the real worker once for full passes; preserve partial-pass ordering/limits and completed-job/changed-record assertions. Retain 150/160-record fixtures.
- [x] Run the focused log/progress/worker/backlog tests, then the affected core and understand suites. Use isolated pytest temporary roots and no cache provider. Preserve and disclose broader-run failures and targeted follow-up results.
- [x] Repeat the diagnostic probe against this worktree; compare file-operation counts and retain machine-readable results. CPU improvement is not established by operation counts alone.

Verification command family: `rtk proxy .\.venv\Scripts\python.exe -m pytest <affected tests> -q -p no:cacheprovider`. Expected red tests fail only on missing behavior; final green tests preserve existing assertions and reduce actual operations.

## Merge request

Base: main. Branch: fix/defender-file-io. Prepare a local review description with the problem, resulting behavior, measured before/after operations, tests, and limitations. Do not merge into main or change the active followups checkout. No Git remote is configured, so publishing requires a destination later.
