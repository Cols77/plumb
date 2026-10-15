# Browser workspace verification

Implementation branch: `feat/browser-issue-workspace`.
All decision tests use isolated temporary repositories, not the owner's project records.

## Backend review

Task 1 passed independent specification and code-quality reviews. Review fixes are in
`e3a6d68` and `701f460`:

- Browser offers bind the displayed explanation and reject earlier registration keys.
- Duplicate requests reserve their identity durably without duplicate follow-ups.
- Intervening card actions allow a later legitimate answer, including across questions.
- Background notifications do not consume the next-user-turn handoff.
- Separate actions with identical wording retain separate delivery identities.
- Queued actions retain their original order.

Measured checks (overlapping runs; counts must not be added):

| Check | Result |
| --- | --- |
| Root regression: browser, all mod, prompt/hook I/O, host conformance, guard (`701f460`) | 505 passed, 3 platform skips, 448.71 seconds |
| Browser, prompt-hook and mod-press regression run | 85 passed, 1 platform skip |
| Final specification regressions, sequential | 9 passed |
| Final quality-fix regressions, sequential | 6 passed |
| Independent quality-review reproduction tests | 3 passed |
| Changed Python files: Ruff; Git whitespace check | Passed |

An earlier broader run of browser, all mod, prompt/hook I/O, host conformance and guard
tests exited successfully with three platform skips. Its double-quiet output did not
give a final count, so no count is claimed. A later parallel worker startup failed on
Windows; the affected focused checks were rerun sequentially and passed.

## Frontend review

Task 2 passed independent specification and code-quality reviews and was committed as
`f754e57`. Final implementation checks: 29 unit tests passed; Svelte check reported zero
errors and warnings; production build succeeded; a fresh dependency installation and
audit reported zero known vulnerabilities. The quality reviewer independently reran
all 15 App tests, including the deferred-refresh selection regression.

A preliminary real Chrome render against the Python demo server displayed the issue,
diagram and evidence without page errors. The launch fragment was removed and selection
appeared in the URL. This is a rendering smoke check, not the final interaction proof.

## Independent integration exploration

The integration tester exercised 58 HTTP action scenarios across all 12 content kinds,
plus an accepted combined-conflict proposal. It verified action journals and press
events, retry deduplication, preserved mod credentials, trial approval/rejection
evidence, conflict file changes, and resulting card states. Two initial client timeouts
passed targeted retries with a longer client timeout.

Separate lifecycle checks passed for multiple questions, stale records, changed
presentation, matching-session full prompt delivery, notification and other-session
exclusion, one-time delivery, restart receipts, and correction text remaining outside
owner-prompt logs.

Four defects remain queued for the integration fix pass:

1. Stale-link/drift action state is not persisted to its separate store.
2. An invalid button index leaves an intent that becomes a false recovery handoff.
3. A left-open turn-built card's fresh offer fails presentation validation.
4. Requesting a custom combination for an unresolved conflict reports it done.

These explorations are not claimed as an all-passing matrix. Regression results and
the final browser matrix will be recorded after fixes.

## Remaining verification

Frontend checks, real-server browser interaction coverage, packaging verification and
the visible browser demonstration are still pending. This report is updated as those
checks complete.

## Meaning of the evidence

An owner answer is separate from a verified repair. A delivered follow-up means retained
in the matching session's prompt-hook output; it does not mean an agent was started or
completed work. The server serializes its browser requests. Independent existing mod
and worker processes retain the repository's original write/concurrency semantics.
