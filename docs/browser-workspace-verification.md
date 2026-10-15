# Browser workspace verification

Branch `feat/browser-issue-workspace`, worktree `C:/Users/33630/.codex/worktrees/1190/plumb`,
measured on 2026-10-15 after commit `632b051`. Everything below is from that one fresh run;
nothing is carried over from earlier reports.

## Commands and their result lines

| # | Command (run from the worktree root, `ui/` for npm) | Result line |
| --- | --- | --- |
| 1 | `PYTHONPATH=<worktree>/src python -m pytest tests/browser tests/mod tests/host -q -p no:cacheprovider -n 2` | No summary line is printed (`addopts = "-q"` plus `-q` is double quiet). Progress line counted: **313 passed, 7 failed, 1 skipped** (321). All 7 failures are in `tests/host` (below); `tests/browser` and `tests/mod` all passed. |
| 2a | `npm test` | `Test Files  5 passed (5)` / `Tests  29 passed (29)` |
| 2b | `npm run check` | `COMPLETED 395 FILES 0 ERRORS 0 WARNINGS 0 FILES_WITH_PROBLEMS` |
| 2c | `npm run build` | `✓ built in 14.14s` (output `src/plumb/browser/static`, unchanged against the committed assets) |
| 2d | `npm run test:e2e` | `40 passed (1.8m)` |
| 3 | `python -m ruff check src/plumb/browser src/plumb/mod tests/browser` | `All checks passed!` |
| 4 | `git status --short` | Clean apart from `.plumb/log` entries and the files this report changes |

`-n 2` was used because pytest-xdist 3.8.0 is installed (pytest 9.1.1).

### The seven `tests/host` failures

`tests/host/test_session_cold.py` (6) and `tests/host/test_hook_perf.py` (1): cold session
start 5734 ms against a 1400 ms budget, warm start 2297 ms against 900 ms, the "check
skipped (budget)" line, extra timing steps (`tests_summary`, `tree_scan`, `awareness`),
and `plumb.judgment.jev`, `plumb.judgment.model`, `plumb.capture.calibrate` imported at
session start. None of these tests touch the browser, mod press or follow-up code, and
the branch does not change `session_start`. See "Baseline" below for the same tests on
the merge-base commit.

An eighth failure in the first run, `tests/host/test_install_skills.py::
test_records_skill_runs_clarify_wait_first_and_names_the_guarded_commands`, was caused by
this branch: it added `ui` to the guard table (`src/plumb/guard.py`) without naming it in
the plumb-records skill. The skill template and its two rendered copies now list `ui`
among the owner-only commands; the test passed in the second full run.

## The four queued defects

All four were fixed in one commit, `aac8a1c` ("fix(browser): preserve decisions through
refresh and restart"), each guarded in `tests/browser/test_decision_lifecycle.py`:

| Defect | Regression test |
| --- | --- |
| Stale-link/drift action state was not persisted to its separate store | `test_stale_decisions_survive_redraw_restart_and_identical_evaluation`, `test_stale_changed_meaning_reopens_a_left_open_decision`, `test_stale_target_change_in_same_turn_has_a_fresh_answerable_offer` |
| An invalid button index left an intent that became a false recovery handoff | `test_invalid_button_never_recovers_a_handoff`, `test_disappeared_card_unknown_failure_never_recovers_a_handoff` |
| A left-open turn-built card's fresh offer failed presentation validation | `test_turn_card_leave_then_change_is_waiting_after_restart`, `test_turn_card_semantic_change_still_refuses_old_offer` |
| A custom combination for an unresolved conflict was reported done | `test_conflict_both_only_completes_when_combined_version_applies` |

## End-to-end coverage (Playwright against the real server)

40 tests, one worker, Chromium, server started by `ui/tests/e2e/server.py`:

| File | Tests | Covers |
| --- | --- | --- |
| `controls.spec.ts` | 21 | skip link, help notices, Processing filter, inbox and evidence splitters, composer Cancel, session back navigation, 15 s polling only while visible, resize between inbox and drawer, retry under the same request id, empty project, Retry diagram, zoom limits, evidence sections, conflict Split/Unified/Base/proposed, Only this issue, long diff folding, phone drawer shade/close/Tab wrap |
| `decisions.spec.ts` | 9 | double click records one answer; trial Leave open / Ask for a change / Yes / No / Fix it; choice Keep CSV / Use JSON; conflict Both / Keep this one / Keep the other; stale card and stale record refusal; multi-question card and missing-diagram fallback |
| `diagram.spec.ts` | 1 | zoom, reset, download, source |
| `navigation.spec.ts` | 7 | click and keyboard selection, filters/search/reset, browser back and forward, reload, refresh and help, empty session, tabs with records and activity |
| `resilience.spec.ts` | 2 | unreachable server then retry; phone width drawer |

Decision tests assert the approval log and the server's stored card state (fresh draw)
after each click, not only the page.

## Screenshots

From this e2e run, copied to `docs/screenshots/browser/`:

| File | Shows |
| --- | --- |
| `inbox.png` | the inbox with an issue selected |
| `issue-diagram.png` | an issue with its diagram zoomed to 125 % |
| `answered-followup.png` | an answered issue with its queued follow-up notice |
| `stale-refusal.png` | the stale-card refusal with "Refresh issue" |
| `narrow-issue.png` | the phone-width layout |
| `disconnected.png` | the disconnected state with retry |
| `demo-live.png` | the persistent demo server (library-started on isolated demo data, port 8765) opened in the installed browser after the run |

## Baseline

The two failing files were rerun on a clone of the merge-base commit `8ad488f` (without
this branch): `python -m pytest tests/host/test_session_cold.py tests/host/test_hook_perf.py
-p no:cacheprovider -rfs` gave `7 failed, 9 passed in 201.85s (0:03:21)` with the same
seven test names. These failures exist without the browser work; they are timing budgets
on this machine and a session-start import set, out of scope here and left untouched.

## Limitations

- "Delivered" means the follow-up was retained in the matching session's prompt-hook
  output; it does not mean an agent ran or that a repair was verified.
- The demonstration and the e2e suite run on isolated demo data seeded by
  `plumb.browser.demo.seed` in a temporary directory, never on the owner's records.
- `plumb ui` refuses under the agent session marker by design, so the e2e helper
  (`ui/tests/e2e/server.py`) starts the server through the library
  (`plumb.browser.server.make_server`), not the command.
- The visible demonstration ran afterwards from a scratch launcher that drops the agent
  marker in its own process only (as `ui/tests/e2e/server.py` does) and serves a fresh
  demo project; `plumb ui --demo --open` from the owner's terminal is the clean way.
- Not tested now: browser console errors are not captured by the e2e suite;
  no independent reviewer recheck or final spec/security code review is recorded here;
  Firefox and WebKit; packaging of the built assets into a wheel.
- The pytest command prints no summary line, so the counts above were derived from the
  progress line of the same run.
