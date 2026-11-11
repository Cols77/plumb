# Plan: resolve the critical and high findings of the 2026-10-26 review

Intent: INT-114. Requirements: SR-372 to SR-380 (each example below is an acceptance test).
Review: `docs/reviews/2026-10-26-iaso-design-review.md`. Decisions: DEC-385 to DEC-393 and
the eleven assumptions captured with INT-114.

Build order follows the review's verdict: the plugin version first (so every later fix
reaches the installed plugin), the logs (so the hooks become measurable), the hooks, then
the judge, the ablation, the gate, the insights table, the skills. Each phase is one
Workflow phase with the gate named at its end; the next phase starts only when the gate
passes. Stage C runs as a Workflow script once the owner opts in (CLAUDE.md); stage A ran in
the main session because it needed the question tool (DEC on INT-114).

Branch: `intent/int-114`, in its own worktree (`PYTHONPATH=<wt>/src` for pytest, memory
worktree-tests-need-src-on-path). One heavy job at a time (`.git/iaso-heavy.lock`). At
most two pytest runs at once, `-n 2`.

Every commit carries `SR: SR-###` naming what it serves. Tests of removed features are
deleted in the same commit as the feature, with `iaso unlink --note` on the retired
example first (DEC-065, as capture listed them).

---

## Phase 1: the plugin refreshes by itself (SR-377)

Files: `scripts/build_plugin.py`, `pyproject.toml`, `src/iaso/__init__.py`,
`plugin/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
`plugin/vendor/MANIFEST.json`, `tests/plugin/test_bundle_fresh.py`.

1. `build_plugin.py`: `version()` returns `0.1.<git rev-list --count HEAD>`; the build writes
   it to the five places (pyproject, `__init__`, plugin.json, marketplace.json, MANIFEST via
   the wheel); `--check` fails naming any place that disagrees.
2. Tests (one per example of SR-377):
   - `test_version_is_commit_count`: a scratch git repo with N commits builds `0.1.N`.
   - `test_new_commit_raises_version`: one more commit, the five places read `0.1.N+1`.
   - `test_check_names_disagreeing_places`: edit plugin.json's version; `--check` exits 1
     naming it.
   - EX-2 (update installs the new version) is the post-merge proof, not a test.
3. `plugin/bin/iaso` already keys the private environment on `<version>-<wheel sha>`; no
   change.

Gate: `python scripts/build_plugin.py --check` exits 0; `pytest tests/plugin/test_bundle_fresh.py`
passes.

## Phase 2: the logs stay small (SR-376)

Files: `src/iaso/log.py`, `src/iaso/understand/tidy.py`, `src/iaso/boundary/landing.py`,
`the records folder/.gitignore`, `src/iaso/contracts.py`, `src/iaso/stale.py`,
`src/iaso/understand/summary.py`, `tests/logs/`.

1. `log.py`: the kind table marks `judgment` as telemetry (compact whole at a landing: every
   entry older than the landing, record liveness not consulted) and local (not tracked);
   the `offer` kind is removed from the table, its writers (`mod/offers.py`, the browser
   service) stop writing it now (the files themselves go in phase 5).
2. `tidy.py` / `landing.py`: the landing's compaction applies the telemetry rule.
3. `the records folder/.gitignore`: `log/judgment/*.json` (the `archive.jsonl` segment stays tracked).
   One-off: `git rm -r --cached the-records-folder/log/judgment/*.json` and one compaction run on main,
   both in the landing commit (SR-329: judgment becomes a local kind, DEC-388).
4. Tests (`tests/logs/test_telemetry_kinds.py`):
   - `test_judgment_compacts_whole_at_landing` (EX-1).
   - `test_live_judgment_files_are_ignored_by_git` (EX-2).
   - `test_no_offer_kind` (EX-3: the kind is unknown to `log.py`; drawing a card logs nothing).
   - `test_validate_chains_through_segments` (EX-5).
   - `test_brief_under_three_seconds` marked `load_bound` (EX-4), on a fixture repository
     with 20,000 archived judgments.

Gate: `pytest tests/logs`; `iaso validate` exit 0 on this repository after the one-off
compaction; `iaso brief` timed under 3 s.

## Phase 3: no hook waits on work its reader does not need (SR-375, SR-373)

Files: `src/iaso/config.py`, `src/iaso/hosts/claude_code/hookio.py`,
`src/iaso/hosts/claude_code/stop.py`, `src/iaso/understand/worker.py`,
`src/iaso/understand/summary.py`, `src/iaso/present/delta.py`, `scripts/build_plugin.py`
(hook timeouts), `tests/host/`.

1. Profile first (owner, 2026-10-26, DEC-394 supersedes DEC-373): add step timing to
   `hookio` (each named step's duration, written to `the records folder/session/hook-timing.jsonl` when
   `IASO_HOOK_PROFILE=1`, off by default). After steps 3 and 4 below, run each hook 10 times
   on this repository (session-start, prompt, pre-tool, edit-check, stop; warm and cold
   cache) and write the table to `docs/plans/2026-10-26-hook-profile.md`. Then set
   `DEFAULT_HOOK_BUDGET_MS` per hook to the measured p95 times 2, `HARD_LIMIT_S` to the
   largest p95 times 4 (at least 10 s), and the `hooks.json` timeouts above the hard limit;
   the profile table is the reason in the commit. The old 60 s / 90 s stay until then.
2. `hookio.run_hook`: a watchdog cut calls `debug.hook_error` (one debug case) as an error
   does; the kept lines still print.
3. `stop.py`: inline work = changed paths, their records, the covering selection of this
   turn's files, the regression check, the one next action, `status.json`. Everything else
   (fidelity/unjudged, `understand_parts`, the summary, cards) is removed or queued for the
   background worker (`worker.start_detached`) and delivered through `queue_notes` at the
   next prompt. The next action is one line chosen in this order: regression > covering
   tests lacking a fresh run > untraced file > stale links > blocking judge questions.
4. `summary.py`: `stop_parts` and `owner_line` shrink to the owner's one line rule of SR-373
   (regression on confirmed behaviour, merge waiting, question); the card drawing goes in
   phase 5.
5. Tests (`tests/host/test_stop_next_action.py`, one per SR-373 example EX-1 to EX-8;
   `tests/host/test_hook_budgets.py` for SR-375 EX-1, EX-2, EX-4). SR-375 EX-3 (no cut over a
   day) is the proof.

Gate: `pytest tests/host -k "stop or budget or next_action"`; the profile table exists and
the configured limits match it; a stop hook on this repository answers within its profiled
soft budget.

## Phase 4: the judge approves what does not contradict the owner (SR-372)

Files: `src/iaso/judgment/jev.py`, `src/iaso/capture/autoapprove.py`,
`src/iaso/understand/judge.py`, `src/iaso/understand/verdict.py`,
`src/iaso/capture/calibrate.py`, `tests/understand/`.

1. `jev.py`: the record-approval action asks the contradiction form (labels `benign`,
   `extends`, `contradicts`, with "adds intent the owner did not give" as the `extends`
   reading) against the owner's logged words and answers; the entailment form is dropped
   for approval (kept for nothing).
2. `autoapprove.fast_track` / `_jev_auto`: approve when the verdict is `benign` (restatement
   or benign extension) and no part is `contradicts`; the approval payload names the verdict;
   `recheck` follows. The 0.9 floor applies to the confidence of `benign`, not to entailment.
3. `verdict.py` / `judge.py`: `contradicts` and `extends`-with-new-intent go to the judge
   model's one question; nothing else asks. Reversal by conversation already exists (reader
   `reversed`); add the test.
4. `calibrate.py`: calibration pairs the new verdicts with the owner's labels (SR-252 stays).
5. Tests (`tests/understand/test_no_contradiction_approval.py`): EX-1 restatement approved;
   EX-2 benign extension approved and marked; EX-3 reversal asks one question; EX-4 new
   intent asks; EX-6 conversation reverses. EX-5 (one pass over the 415) is the proof, run
   live in stage C with the heavy lock.

Gate: `pytest tests/understand -k "approval or fast_track or calibrat"`; then one judge pass
on this repository: `iaso status` shows the proposed count fall and only contradictions
waiting.

## Phase 5: the parts the owner uses stay; the rest goes or freezes (SR-380, SR-373 cards)

Files: delete `src/iaso/view/`, `src/iaso/importer/`, `src/iaso/mcp/`,
`src/iaso/hosts/pi/`, `src/iaso/mod/offers.py`, `src/iaso/mod/press.py`,
`src/iaso/understand/fullcard.py`, `cardcontent.py`, `recheck_button.py`,
`src/iaso/browser/{service,demo,followup,diagrams,session}.py`, the ui card components
(`DiffView`, `Evidence`, `diff.ts`, `decisions.spec`, `controls.spec`), the `triage` verb and
`spec approve`/`approve_set`; their tests: `tests/present/test_view.py`, `tests/importer/`,
`tests/bridge/test_import_*`, `tests/mcp/`, `tests/hosts/test_pi.py`, `tests/mod/test_press.py`,
`test_trial_press.py`, the nine card tests under `tests/understand/`, `tests/browser/` card
tests, `tests/capture/test_triage*.py`, `test_set_approval.py`. Edit `src/iaso/cli.py`
(routes and help), `src/iaso/hosts/cli.py` (no Pi), `src/iaso/stale.py` and
`src/iaso/present/*` (freeze filter), `pyproject.toml`, `src/iaso/study/video.py`,
`plugin/hooks/register.tsx` (`roomCard`), `src/iaso/mod/cli.py` (`room --card`),
`README.md`, `docs/hosts.md` (Pi section), `the records folder/config.yaml` (freeze list).

1. Before deleting: `iaso unlink <link> --note "retired with <part>"` for every link capture
   listed (SR-205, SR-238, SR-283 Pi examples, SR-285); `triage`'s `_Prompts`,
   `premise_problem`, `claim`, `_items` move beside `understand/premise.py`; `spec.py` keeps
   `escalated_ids`, `escalated_sets`, `set_ids`, `current_set_hash`; `confirm.py` keeps
   refusing `via: button` and `by: import` approvals with one line (trust boundary).
2. Freeze: `config.yaml` gains `freeze: [paths...]` (Codex and Hermes adapters and tests,
   `evaluate/` and `tests/evaluate`, `the records folder/eval`); `stale`, `drift`, the brief and the
   merge check skip frozen paths; the session marker `IASO_AGENT_SESSION=codex|hermes`
   wakes that host's paths (EX-3). The benchmark's records (INT-105, SR-344 to SR-349) are
   marked frozen in their frontmatter and excluded from "waiting on a judge".
3. `pyproject.toml`: `manim` moves to `[project.optional-dependencies] video`;
   `study/video.py` says "install iaso[video]" when `python -m manim` is missing.
4. Reword SR-282's host list (DEC-393) and `docs/hosts.md`.
5. Tests: `tests/core/test_frozen_parts.py` (EX-2, EX-3); `tests/plugin/test_bundle_fresh.py`
   gains `test_removed_verbs_are_unknown` (EX-1) and `test_wheel_requires_pyyaml_only`
   (EX-4); `tests/study/test_video.py` gains the missing-manim message; `tests/mod` and
   `tests/plugin/mod` lose the card half (EX-5 is checked by the remaining panel tests).

Gate: `python scripts/build_plugin.py --check`; `pytest tests/core tests/plugin tests/study
tests/mod tests/capture`; `iaso --help` lists none of `view import mcp triage`; the brief on
this repository counts no drift from frozen paths.

## Phase 6: an ordinary message never blocks the agent on the judge (SR-378)

Files: `src/iaso/understand/cmd_clarify.py`, `src/iaso/hosts/claude_code/ask_gate.py`,
`src/iaso/hosts/claude_code/pretool.py`, `src/iaso/understand/worker.py`, `tests/understand/`,
`tests/host/`.

1. `cmd_clarify._judged`: never `worker.run_once`; `worker.start_detached` and answer at once:
   `ask` with the questions already in the store (commanded messages included: this fixes
   debug case report-12a20a67), else `ready`.
2. `ask_gate.decide`: the refusal goes; `note_asked` bookkeeping stays for pacing (SR-334).
   `pretool.decide` denies only the guard and the closed gate whose reason is a contradiction
   with a confirmed record (SR-225).
3. Tests: `tests/understand/test_clarify_wait_background.py` (EX-1, under one second, no
   subprocess); `tests/host/test_ask_gate_gone.py` (EX-2); `tests/host/test_gate_contradiction.py`
   (EX-3, may already exist under SR-225: extend); `test_unreachable_judge_does_not_hold.py`
   (EX-4).

Gate: `pytest tests/understand -k clarify_wait` and `tests/host -k "gate"`; the debug case
report-12a20a67 reruns clean (`iaso debug`).

## Phase 7: one table of insights by condition (SR-374)

Files: new `src/iaso/present/insights.py`; `src/iaso/hosts/claude_code/session_start.py`,
`prompt.py`, `edit_check.py`, `stop.py`; `src/iaso/verify/runner.py` (failing-test line);
`src/iaso/debug.py` (known-issue symptom match reused by the prompt hook);
`src/iaso/boundary/cli.py` (merge-check prints holds only); `src/iaso/present/cli.py`
(`iaso context`); `src/iaso/present/brief.py` (deltas and blocks, no counts);
`src/iaso/trace.py` (default exempt `**/templates/**/vendor/**`); `src/iaso/verify/evidence.py`
and `funcmap.py` (freshness by covered files, DEC on INT-114); `tests/present/`, `tests/verify/`.

1. `insights.py`: the table as SR-374 states it: `condition -> builder(core, ctx) -> lines`,
   each line keyed for the once-per-session emitter (`present/delta.py`). Every hook asks the
   table for its condition and prints nothing else.
2. `iaso context <condition> [<path or id>]`: the same builders without the once-per-session
   filter, full text.
3. Brief: what changed since the agent last saw it (the `seen.json` mechanism) and what
   blocks now; counts move to `iaso status`.
4. Tests (`tests/present/test_insights.py`, one per SR-374 example, EX-1 to EX-11;
   `tests/verify/test_fresh_by_covered_files.py` for EX-11).

Gate: `pytest tests/present tests/verify tests/host -k "insight or brief or context or fresh"`.

## Phase 8: the skills are one rulebook (SR-379)

Files: `src/iaso/hosts/claude_code/templates/skills/*/SKILL.md`,
`templates/skills/iaso-records/references/glossary.md` (new), `templates/iaso-command.md`,
`scripts/build_plugin.py` (hook timeouts), `README.md`, `tests/capture/test_skills.py`,
`tests/plugin/test_bundle_fresh.py`, `tests/plugin/test_readme.py` (new).

1. iaso-records: the per-message loop, the question rules (once), the glossary pointer. The
   other skills and the command: "Questions to the owner: follow iaso-records." iaso-clarify's
   description triggers on intent change or an accepted spec session only; its state table
   moves to `references/clarify-states.md`. iaso-intent: stage A in the main session; B and
   C as workflow phases after the owner's opt-in. No record id in any skill. One sentence on
   pacing, pointing to the pacing rule.
2. Command: `allowed-tools` loses `git rm`, `git commit`, `git merge`, `git checkout --ours|--theirs`;
   `description` one line.
3. `hooks.json` timeouts: 10 s pre-tool and edit-check (built by `build_plugin.py`).
4. README: one page (what iaso is, install, `/iaso intent`, `/iaso status`, `/iaso go`);
   the command reference is `iaso --help`.
5. Tests: `test_skills.py::test_the_four_question_rules_are_in_each_skill` becomes
   `test_question_rules_live_in_iaso_records_and_others_point_to_it` (owner's answer of
   2026-10-26 on SR-328's proof); `test_clarify_triggers_on_intent_change_only`;
   `test_glossary_defines_every_iaso_term_used`; `test_no_record_ids_in_skills`;
   `test_command_grants_no_destructive_git`; `test_readme_is_one_page_and_names_no_retired_command`.

Gate: `python scripts/build_plugin.py --check`; `pytest tests/capture/test_skills.py tests/plugin`;
the plugin-dev validator and skill reviewer report no high finding (run as agents, output
kept with the proof).

## Phase 9: proofs, full run, landing

1. Record each proof: `iaso proof SR-37x --evidence <path> --summary "..." --passed`:
   SR-372 (status after the judge pass), SR-373 and SR-374 and SR-375 (a live session on this
   repository: a turn ends in seconds, the brief says what blocks, the intent line after
   compaction), SR-376 (counts and timing), SR-378 (clarify --wait timing with questions
   pending), SR-379 (validator and reviewer output), SR-380 (`iaso --help`, the wheel's
   metadata, the brief's counts). SR-377 is post-merge: the turn after the landing asks for it.
2. `iaso tests run --full` under the heavy lock; `iaso merge-check main`; `iaso intent done`.
3. Landing by the landing coordinator (memory): merge commit with the `SR:` trailer; the one-off
   log compaction and `git rm --cached` of judgment files land in the same merge; then the
   plugin build and `/plugin update` for SR-377's proof.

---

## Not in this plan

Question pacing (branch intent/pacing-choice, SR-334). The browser study room and the
escalation suggestion (kept as they are). The medium and low findings of the review.
