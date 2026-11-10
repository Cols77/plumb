# Hook profile, 2026-10-26 (SR-375, DEC-394)

Phase 3 of `2026-10-26-review-resolution.md`, step 1: each hook run 10 times warm and 10
times cold on this repository (the `intent/int-114` worktree, after the stop hook's inline
work was cut to the next action), with `IASO_HOOK_PROFILE=1`. Cold means the hash and log
caches in `.iaso/cache/*.json` removed before the run. Worker processes were not started
(the hook's own inline work only). The in-process time runs from the hook's start
(`iaso hook` entry), the clock its soft budget and hard limit use; the wall time adds
Python's start. `pre-tool` runs outside `run_hook` (no budget), so its row is wall time.

Conditions: the logs are **not** compacted (243 MB under `.iaso/log`, a 33 MB events cache
and a 49 MB evidence cache), and other sessions kept the machine busy throughout (the test
suite's load guard reported 5 minutes of busy CPU in the same hour). Both inflate the cold
rows; SR-375 EX-1 assumes the logs compacted.

## Per hook (ms)

| hook | budget key | runs | p50 ms | p95 ms | warm p95 ms | cold p95 ms | wall p95 ms |
|---|---|---|---|---|---|---|---|
| session-start | session_start | 21 | 37000 | 93187 | 32344 | 93781 | 73078 |
| prompt | prompt | 20 | 16437 | 50390 | 16437 | 53329 | 53718 |
| edit-check | post_edit | 20 | 860 | 2719 | 860 | 2750 | 4531 |
| stop | stop | 20 | 32344 | 52141 | 32344 | 63734 | 54547 |
| pre-tool | - | 20 | 2125 | 3578 | 2547 | 3640 | 3578 |

## The stop hook's steps (ms)

| stop step | warm p50 ms | warm p95 ms | cold p50 ms | cold p95 ms |
|---|---|---|---|---|
| queue background | 688 | 19250 | 2344 | 3125 |
| record index | 235 | 485 | 3140 | 3297 |
| changed paths | 515 | 3078 | 47 | 578 |
| records | 2719 | 8250 | 24813 | 27234 |
| untraced | 0 | 15 | 0 | 62 |
| covering tests | 1625 | 3672 | 11625 | 30734 |
| awareness | 1328 | 2703 | 3485 | 4578 |
| next action | 641 | 1375 | 2093 | 2563 |

`records` is `records_for_paths`, the touched records' statuses, the stated set, the session
intent and the status line's turn fields; cold, it pays the log caches' rebuild. `queue
background` starts the worker process (its warm p95 is one 19 s outlier of process start
under load).

The run before the status line's record-wide counts moved to the worker (stop still called
`core.status()` on every record) gave, for the same steps:

| stop step | warm p50 ms | warm p95 ms | cold p50 ms | cold p95 ms |
|---|---|---|---|---|
| queue background | 1297 | 1984 | 1094 | 1828 |
| record index | 281 | 344 | 2016 | 2562 |
| changed paths | 891 | 1937 | 16 | 63 |
| records | 4875 | 7719 | 20797 | 28797 |
| untraced | 0 | 31 | 0 | 16 |
| covering tests | 1969 | 6766 | 7703 | 41063 |
| awareness | 1859 | 2265 | 1266 | 1859 |
| next action | 109 | 156 | 47 | 94 |

## Limits

The plan's rule (budget = p95 x 2, hard limit = largest p95 x 4, at least 10 s) applied to
this table gives:

DEFAULT_HOOK_BUDGET_MS = {"session_start": 186400, "prompt": 100800, "post_edit": 5500, "stop": 104300} ; HARD_LIMIT_S = 373

That is above today's 60 s budgets and 90 s hard limit, and above the host's 120 s timeouts,
because session-start and prompt (not changed in this phase) and the cold caches dominate.
The limits stay at 60 s / 90 s until the logs are compacted at INT-114's landing and the hooks
are profiled again, then they are set from that second profile (DEC-397, owner 2026-10-26).
