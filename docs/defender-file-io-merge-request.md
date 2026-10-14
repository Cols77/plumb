# Reduce worker bookkeeping file activity and keep events fresh between jobs

Proposed merge: `fix/defender-file-io` into `main` (base `fd0e10f`). This is a local proposal: the repository has no configured Git remote.

## Problem and result

The backlog tests repeatedly reopened the same worker queue and lock for retained job files, while each verdict separately read and replaced the log head. Workers also appended events outside Core, leaving later jobs with stale cached verdicts. These file accesses were prominent in a Defender performance trace taken after Hermes had stopped.

This change keeps separate immutable log entries but writes them in batches of at most 32 per lock acquisition and head publication. Each chunk reads the head once and removes it before persistence, forcing recovery from actual entries if a write is interrupted. Requests are validated before any entry is written. Core invalidates cached events even when an append partially fails, and worker verdicts and notes use those APIs.

Identical running progress updates are coalesced within one second; changed counts, completion, and failures publish immediately. Full backlog test passes invoke the real worker once, retaining the existing 150/160-record fixtures and partial-pass behavior.

The Core protocol declares the batch API, and the read-only boundary facade explicitly suppresses it. A regression verifies that neither single nor batch calls through that facade persist entries in either stream.

## Measured file operations

Both instrumented tests passed before and after. Counts below cover the test call phase, using Python audit events for attempted opens and replacements. They are not Defender scan counts or CPU measurements. Source hashes were unchanged during each probe. Full counts and source hashes are in [the measurement artifact](defender-file-io-measurements.json).

| Operation | 150-record scenario, before → after | 160-record scenario, before → after |
| --- | ---: | ---: |
| Log-head read attempts | 302 → 31 | 320 → 8 |
| Log-head replacements | 151 → 31 | 160 → 8 |
| Log-lock creation attempts | 151 → 31 | 160 → 8 |
| Worker-lock creation attempts | 91 → 3 | 4 → 1 |
| Progress replacements | 93 → 62 | 12 → 11 |
| Event-cache read attempts | 35 → 35 | 6 → 6 |
| Event-cache replacements | 31 → 31 | 4 → 4 |

Crash safety adds one head-removal attempt per batch: 31 and 8 respectively. Progress totals may vary with heartbeat timing under load. Event-cache writes remain necessary to expose changed verdicts; this patch does not eliminate them. The 150-record scenario includes a repeated completed pass and one changed record.

## Validation

- Regression tests first reproduced duplicate head reads, redundant progress writes, stale verdict visibility, malformed-head recovery, and partial persistence caused by late serialization validation.
- 82 focused tests passed, including the unchanged large backlog scenarios. Both instrumented scenarios passed again after implementation.
- Affected suites (`tests/core tests/logs tests/understand`): **839 passed, 5 skipped, 4 failed**, 848 collected. This was not an all-green run; see the failure disposition below.
- Ruff and whitespace validation pass.
- Independent specification review passed. Code-quality follow-up found a batch-write bypass in the read-only Core facade; the regression reproduced it, the fix passed 13 targeted fidelity/conformance tests, and the reviewer accepted the correction with no remaining blockers. Additional deterministic interleaving between batch chunks was suggested as optional coverage.
- SR-153 records the proposed requirement and links its four examples to regression tests. The [work board](plans/2026-10-14-defender-file-io.md) records the workflow.

An initial compatibility run hit the existing two-second log-lock timeout in the two-process append test; its unchanged targeted retry passed. Lock timeouts and stale-lock policy remain unchanged. The operation reductions are measured; the resulting Defender CPU improvement still requires a comparable performance trace.

### Broader-run failures and follow-up

| Check | Observed result and disposition |
| --- | --- |
| `tests/logs/test_single_writer.py` | Its allowlist omits `guard.py` and `hosts/claude_code/pretool.py`. The same failure reproduces on unchanged base `fd0e10f`; those files and the test are unchanged here. This pre-existing failure remains. |
| `tests/logs/test_read_cost.py` | Warm-read timing exceeded the 60 ms limit (89.3 ms in the broad run; 65.0 ms on the first retry). A subsequent unchanged retry passed, as did the base test. The read path was not modified. |
| `test_flow_7_stale_edit_names_the_link_hold_card_and_reformat` | The existing 1,400 ms stop budget expired near the card draw gate, producing the title-only fallback instead of the complete card. It failed in the broad run and first retry; base passed once. A final unchanged branch retry after the broad run passed. This demonstrates timing sensitivity, not proof that a performance regression is impossible. |
| `test_gate_sh_lets_the_card_diagram_through_while_closed` | `sh` was absent from the process PATH. The test passed with installed Git Bash temporarily added to that subprocess's PATH. No machine-wide PATH changes were made. |

The final retry of the card and shell checks passed both tests. An independent root-agent run also passed all four new read-only facade cases. No assertions or deadlines were weakened. Rerun the timing-sensitive checks under representative load before merge if the target CI requires stable timing gates; do not describe the full suite as clean.

## Review and integration

Review the head invalidation/recovery sequence, per-chunk lock scope, partial-write cache invalidation, and immediate terminal progress publication. No log-format migration is required. Active work and tests in other worktrees were left running. Reconcile concurrent changes in the `followups` worktree before integrating there.

The original diagnosis and its evidence limits are preserved in [the handoff note](defender-file-activity-handoff.md).
