# Reduce worker bookkeeping file activity and keep events fresh between jobs

Merge: `fix/defender-file-io` at `eba17ec` into `main` (base `fd0e10f`). Integration is local; the repository has no configured Git remote.

**Owner-authorized integration, 14 October 2026.** The owner lifted the hold after all 238 records were confirmed and Plumb's quick merge check passed. This merge commit completes the pending non-fast-forward merge, including the approval history and the requested five-second hook-test allowance. Plumb's gates remain enabled. The known repository-state test failure and older traceability gaps below remain follow-up work.

## Owner-requested follow-up: confirmations and hook-test allowance

The owner subsequently requested confirmation of the original 32 proposals and an increased hook-test time allowance. The integration limit in `tests/integration/test_session_e2e.py` is now **5,000 ms instead of 2,000 ms**. Functional assertions and configured in-process hook deadlines are unchanged. An unused import in that test file was removed for lint. This is an intentionally relaxed integration-test threshold, not a measured runtime improvement or evidence that the original two-second target is met. The same test-file change is present in the isolated worktree and included in this merge.

Plumb recorded all three tests in that file passing in run `20261014T034950Z-469462ba`, with no timeout, discarded result, or regression. Ruff and whitespace checks passed. After that run, the owner confirmed the original 32 records through Plumb's interactive terminal. The owner then requested that everything be confirmed and completed a second native prompt for all 191 remaining records. **All 238 repository records are now confirmed, with zero pending**, freshly verified through Plumb's status API. The agent did not supply either terminal answer or bypass the approval guard.

A check after the first confirmation, run `20261014T035841Z-bcaf52d3`, found an existing repository-state assumption in `test_merge_check_on_plumb_reports_the_owners_pending_confirmations`: it requires SR-034, SR-047, SR-053, and SR-061 to appear as pending. All four are now confirmed. That test fails after the requested approvals, while the two hook-latency tests retain their passing evidence. Its hardcoded expectation needs a separate correction using controlled pending/confirmed records instead of the owner's live approval state. The whole integration file is therefore not currently green; the five-second change resolves the two latency failures specifically. No test assertions were changed as part of confirming the remaining records.

Changing the shared integration test expanded the merge's record scope to eight additional, older proposals: SR-010, SR-012, SR-014, SR-034, SR-043, SR-047, INT-018, and DEC-006. These are included in the completed repository-wide confirmation. The owner subsequently requested completion of the merge; confirming records does not waive test failures or settle the older traceability gaps.

After staging the approval log, the installed merge-hook interpreter's quick merge check exits **0**, with zero unconfirmed records, unstaged Plumb files, undeclared files, intent conflicts, ID collisions, or unreadable records. `plumb validate --json` also exits 0 with no errors and 740 repository-wide warnings; this does not establish passing tests or complete traceability. Hash checks verified that all 338 protected pre-existing local files remain unchanged. Approval and verification artifacts are in `all-confirmations-before.json`, `all-confirmations-after.json`, `all-approval-terminal-state.json`, `merge-plumb-final-quickcheck.json`, `merge-plumb-validate-final.json`, `merge-hook-budget-final-tests.json`, and `merge-confirmation-state-test.json` under the diagnostic folder named below.

Final focused verification through Plumb, run `20261014T042002Z-15053b70`, passed **all 53 selected tests**, with no failures or timeout. It covers log batching and recovery, progress updates, backlog workers, the read-only boundary, and both hook integration flows. The previously diagnosed repository-state assertion was not rerun in this focused selection. Results are retained in `merge-final-focused-tests.json` and Plumb's staged test-run log.

The later sections retain the earlier checkpoints and their limitations; the completed confirmations, passing quick merge check, owner-authorized integration, and final focused run above supersede those earlier statuses. The feature worktree and the owner's existing local configuration changes are preserved.

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

## Earlier Plumb follow-up while the merge was held

At this earlier checkpoint, the installed merge-hook interpreter ran `plumb merge-check --hook pre-merge-commit` after staging validated Plumb records and audit entries. It exited **4 for 32 proposed records awaiting owner confirmation**. It reported zero unstaged Plumb files, undeclared files, intent conflicts, ID collisions, and unreadable records. Thirty of those proposals predate this fix; the new ones are SR-153 and INT-045. No owner approval was created or relayed by the agent.

Work completed through Plumb:

- `plumb intent` recorded this conversation's implementation request as proposed INT-045; `plumb link` connected SR-153 to it. The supplied quote is not represented as a hook-verified prompt.
- `plumb quotes recover` found exact historical source messages for INT-008 and INT-022. These are review aids, explicitly **found in a transcript, not verified**; recovery does not confirm records. It found no supporting source in the available transcripts for INT-011, INT-017, or INT-020. The narrower recovered message for INT-016 prompted a possible-overstatement finding; review the original brief and later owner wording before rewriting that intent or its token-budget requirement SR-063.
- `plumb tests run` recorded 13 passes and two failures in run `20261014T032031Z-54e91946`: all 11 selected cases covering this change passed, and two previously recorded failures also passed. The remaining failures are `test_session_through_installed_hooks` and `test_capture_flow_through_installed_hooks`. Diagnostic runs through Plumb confirmed that both reach their final hook-latency assertions after the functional assertions pass. Observed hooks take roughly 2.1-3.7 seconds against the unchanged 2-second limit. These failures remain open; the runs do not establish their cause or show that this branch caused them.
- A follow-up Plumb run, `20261014T033619Z-a9a6fbfb`, recorded 11 more passing cases for eight previously unrecorded test selectors. Plumb's final acceptance query reports **all 13 acceptance checks mapped to SR-153 passing on the current identity, no failing or unverified checks, and all SR-153 links current**. SR-153 remains proposed, awaiting owner confirmation.
- `plumb repin SR-022#4 --after-tests` ran all 12 fidelity tests successfully and refreshed that one stale link after Sonnet judged the change's meaning unchanged. The repin is logged; it grants no approval. The broader report still lists 140 stale/unpinned links and older unverified requirements. It also reports a full verification run pending because `tests/plugin/__init__.py` has no covering test. That repository-wide verification remains open.
- `plumb validate --json` exits 0 with no errors, including no log-integrity errors. It still reports 659 repository-wide warnings; this is not a clean whole-repository status. Hash checks verified that 338 pre-existing local files remain unchanged, including the user's Claude configuration and existing audit entries.
- `plumb view --scope SR-153 INT-045` generated [the fix's review vault](../.plumb/view/defender-fix/index.md), including an Obsidian Canvas. `plumb show` generated [the complete read-back of the 32 pending records](../.plumb/view/defender-merge-records.txt). These ignored local views are review aids and are not committed artifacts.

The two existing decisions needing owner review concern where long-running progress appears (DEC-028 proposes both terminal and status line) and how the old proposed-record backlog is reviewed (DEC-029 proposes one background pass, then cards grouped by feature). Plumb's scoped triage found no low-risk group eligible for a straightforward confirmation shortcut.

Resume by reviewing and resolving those proposals through Plumb's owner interface, investigating the hook-latency failures, and checking the remaining stale links. `plumb approve` requires the owner's own interactive terminal; the agent must not feed its confirmation prompt or bypass its session guard. After the records are settled, stage the resulting `.plumb` records and logs and rerun the quick merge check. The merge remains pending until the owner asks to finish it. Active tests in other checkouts were left running throughout.

Detailed diagnostic JSON and test output are retained locally under `C:/Users/33630/AppData/Local/Temp/defender-cpu-diagnostic/`, including `merge-plumb-final-quickcheck.json`, `merge-plumb-validate-final.json`, `merge-plumb-test-run-complete.json`, `merge-sr153-final-evidence.json`, `merge-sr153-remaining-tests.json`, `merge-hook-test-report.json`, `merge-capture-test-output.txt`, `merge-quote-recovery.json`, and `merge-repin-fidelity.json`.
