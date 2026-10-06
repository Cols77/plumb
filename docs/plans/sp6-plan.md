# SP6 plan: parallel work in four lanes

Implements `docs/specs/sp6-parallel-work.md` (ruling R10, concept D15 and section 11 item 6)
in four lanes with disjoint files and frozen contracts: IDS (spec 4, 5 and the ID part of
10), LOGS (spec 6), MERGEDRIVER (spec 7, 8 and the intent-conflict part of 10) and AWARENESS
(spec 9). The owner does not review this plan (D11); verifier agents check it against the
owner intent brief, rulings R1 to R15, `docs/concept.md` and the spec. "spec 7.3" means
section 7.3 of the sp6 spec. Records: `FEAT-006`, `INT-022`, `SR-070` to `SR-079`,
`DEC-020` to `DEC-022`, all proposed, written with plumb's own CLI.

**Every R10 item is a MUST.** This plan has no SHOULD tier and no drop order. A lane that
overruns keeps going; the batch waits for it. Only the polish items named in the Integrate
row may be cut.

Binding owner rules for every phase (from the work order and the brief):

1. **HIGH findings only, whole class.** Fix only HIGH findings, and fix the whole class:
   name the guarantee, enumerate every entry point, fix at one choke point, add one test per
   entry point. Medium and low findings go to `docs/followups.md`.
2. **Test economy.** No full suite except the single run in the Integrate phase. Iterate on
   the touched tests only. Before each commit, run the lane's focused set (3.4) once, in the
   FOREGROUND (timeout up to 600000 ms).
3. **Latency.** Hook latency stays in seconds; awareness must stay cheap (spec 13: the
   overlap check at most 50 ms warm, no git process on the prompt path).
4. **Process safety.** Never kill a process you did not start. The machine has 2 cores: at
   most `pytest -n 2`, and lanes run without `-n`.
5. **Dogfooding.** Every commit carries `SR: SR-###` trailers that claim its paths (the
   `commit-msg` hook enforces it). New requirements are proposed plumb records with
   examples, written through plumb's CLI. Run `plumb validate` and `plumb drift` before
   committing. Set `PYTHONUTF8=1` when running plumb from a shell. **Agents never approve
   records**: no agent runs `plumb approve`, `revoke`, `triage --approve`, `spec approve`,
   `config auto-approve` or `conflict choose` without the owner's own logged words, and no
   agent relays an approval or a choice the owner did not give (R2). Every owner-only write
   goes through `approvals.require_owner` (or `approvals.owner_prompt` for a relay), and
   each new owner-only command gets a test that runs it with no marker and stdin a pipe
   holding "y" and asserts exit 3 with nothing written.
6. `C:/coding/pi-agent-factory` is out of scope: never read, write or run anything there for
   this batch.
7. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## 1. Shape of the work

| Phase | What | Who | Agent time | Gate before the next phase |
|---|---|---|---|---|
| 0. Contracts | Every cross-lane data class, config key, route, stub and call site (3.2), so the four lanes start against real interfaces | coordinator, alone, on `main` | about 60 min | 3.3 |
| 1. Lanes | IDS, LOGS, MERGEDRIVER, AWARENESS in parallel, each in its own worktree (sections 4 to 7) | four lane agents | about 150 min per lane, all MUST | lane gate (3.4) at each merge point |
| 2. Integrate | Merge the lanes (LOGS first), migrate plumb's own logs, reinstall hooks (driver included), the e2e scenarios, the ONE full-suite run (as `plumb merge-check`), dogfood checks (8) | coordinator, on `main` | about 60 min | 8.4 |
| 3. Review | Intent verifiers on the merged result; HIGH fixes only, whole class (9) | review agents; coordinator fixes | about 45 min | no HIGH finding open |

Orchestration uses the host's native mechanism: in Claude Code, the `Workflow` tool (phase 0
as one agent step with its gate; phase 1 as a `parallel()` of four lane pipelines, each a
sequence of segment agents with a merge-ready report per merge point; phases 2 and 3 as
gated steps). Starting it needs the owner's opt-in where Claude Code asks for it; this plan
does not grant it.

The lanes are themselves parallel work on plumb, before SP6 exists. To stay out of the
problems SP6 solves: **lanes create no new records** (every SP6 record exists; a lane that
needs one stops that item and asks the coordinator), and lanes append to the logs only
through plumb's commands (`plumb link`, `plumb repin`, `plumb verify`), which today's
`merge=union` keeps mergeable.

## 2. Conventions for every agent

- Repository `C:/coding/plumb`. Phase 0 runs on `main`. Lanes work in worktrees
  `C:/coding/plumb-wt/sp6-<lane>` on branches `sp6/<lane>`, created from `main` after the
  phase-0 gate (`git -C C:/coding/plumb worktree add C:/coding/plumb-wt/sp6-ids -b sp6/ids
  main`), then `uv sync` inside the worktree.
- Each lane starts with `uv run plumb brief`, `uv run plumb status` and
  `uv run plumb show <its SRs>` and keeps the output as context.
- Test first: write the failing test, see it red, implement, see it green. Mark every new test
  `@pytest.mark.sr("SR-0xx")` with the SR it verifies.
- Iterate with the touched test file only (`uv run pytest tests/ids/test_reserve.py -q`).
  Before each commit: the lane's focused set once, in the foreground (3.4). No whole suite.
- Tests that need git use a temporary repository (`tmp_path`, `git init -b main`, a local
  `user.name`/`user.email`), real `git worktree add` and, for clones, `git clone` of that
  repository; never the plumb repository itself. Helpers live in the lane's own
  `tests/<lane>/gitrepo.py` (phase 0 provides `tests/gitrepo.py` with `make_repo`,
  `add_worktree`, `commit_all`, `run_git`; lanes import it and never edit it).
- `SR:` trailers: each commit names the SRs of the task rows it implements, and claims only
  paths those SRs declare. Before committing a new module, link it:
  `uv run plumb link SR-0xx implemented_by <path>` and `verified_by <test file> --example
  EX-n` (lanes may run `plumb link` and `plumb repin` on their own SRs; those never confirm
  anything). Then `uv run plumb validate`, `uv run plumb drift` and
  `uv run plumb claims check --range main..HEAD`.
- Lanes never edit another lane's files (3.1). A needed contract change stops that item; the
  lane asks the coordinator and moves to its next item.
- Medium and low findings, and anything unfinished with its state, go under the lane's own
  heading at the end of `docs/followups.md` (`## SP6 lane IDS (2026-10-..)`).

## 3. Files, contracts and gates

### 3.1 Ownership (disjoint)

| Owner | Paths |
|---|---|
| Coordinator (phases 0, 2, 3) | `src/plumb/contracts.py`, `config.py`, `cli.py`, `api.py`, `store.py`, `confirm.py`, `claims.py`, `validate.py`, `importer/apply.py`, `boundary/report.py`, `boundary/cli.py`, `boundary/__init__.py`, `present/render.py`, `present/cli.py`, `present/report.py`, `present/owner_text.py` (new), `hosts/claude_code/session_start.py`, `prompt.py`, `stop.py`, `post_edit.py`, `snapshot.py`, `install.py`, `cli.py`, `hosts/claude_code/templates/**`, the stub packages' `__init__.py` API names; `tests/gitrepo.py`, `tests/logutil.py` (phase 0 only; then LOGS), `tests/present/test_owner_text.py` (new), `tests/integration/**`, `tests/test_smoke.py`; `.plumb/**`, `.claude/**`, `CLAUDE.md`, `README.md`, `docs/**` (lanes only append to `docs/followups.md`) |
| IDS | `src/plumb/ids/**` (new; keeps the phase-0 API names); `tests/ids/**` (new) |
| LOGS | `src/plumb/log.py`, `src/plumb/logcmd.py` (new), `src/plumb/paths.py`, `src/plumb/merge.py` (`log_integrity` and its helpers only), `src/plumb/verify/evidence.py` (`load_index` and its cursor only), `src/plumb/commands.py` (`init`'s log files and `GITATTRIBUTES_LINES` only); `tests/logs/**` (new), `tests/logutil.py` (after phase 0), `tests/core/test_log.py` |
| MERGEDRIVER | `src/plumb/mergedriver/**` (new; keeps the phase-0 API names), `src/plumb/boundary/premerge.py` (new); `tests/mergedriver/**` (new) |
| AWARENESS | `src/plumb/awareness/**` (new; keeps the phase-0 API names); `tests/awareness/**` (new) |
| Any lane, append only | `docs/followups.md` (own heading) |

Data files have one writer each: `log.append` writes `.plumb/log/**` (every lane's new kinds
go through `CoreAPI.log_append`: `renumber` from IDS, `conflict-resolution` and the
compatibility `judgment` from MERGEDRIVER); the stop and post-edit hooks write
`.plumb/cache/changing.json` through `awareness.publish` and `awareness.note_edit`;
`awareness` alone writes `.plumb/cache/awareness-branches.json`; `log` alone writes
`.plumb/cache/log-head.json` and `log-<stream>.json`; the merge driver writes only its
`OURS` file; `ids` alone moves `refs/plumb/ids`.

### 3.2 Phase 0: what the coordinator writes before any lane starts

1. **`contracts.py`.** Frozen data classes with defaults on every field: `IdState`,
   `Collision`, `MergeFixResult`, `MigrationReport`, `DriverResult`, `IntentConflict`,
   `Overlap` (spec 12). `LogEntry` adds `name: str = ""`. `StatusSnapshot` adds
   `overlaps: int = 0`, `overlap_labels: tuple[str, ...] = ()`, `conflicts: int = 0`.
   `MergeReport` adds `id_collisions`, `unmerged`, `intent_conflicts` (tuples, default
   empty) and `legacy_log_lines: int = 0`.
2. **`config.py`.** Sections `ids` (`retries: 50`, `retry_s: 3`) and `awareness`
   (`enabled: true`, `branches: true`, `remotes: false`, `max_age_days: 7`,
   `branch_max: 8`, `branch_scan_ms: 400`, `brief_lines: 3`); `merge.premerge_run_full:
   true`. `plumb init`'s commented `config.yaml` lists them.
3. **Stubs with the final signatures (spec 12).**
   - `plumb/ids/__init__.py`: `reserve` and `peek` return the highest local number plus one
     (today's `Store.next_id` logic, moved), `observe` does nothing, `state` reports
     `reserved: false`, `collisions` returns the duplicates `Store.problems()` reports,
     `approval_aliases` and `trailer_aliases` return `{}`, `merge_fix` returns an empty
     result.
   - `plumb/logcmd.py`: `run` prints "plumb log: not available in this build" (exit 2).
   - `plumb/mergedriver/__init__.py`: `open_conflicts` returns `()`, `conflict_card` and
     `stated_entries` return `[]`, `install`, `uninstall` return `[]`, `status` returns
     "merge driver: not available", `merge_texts` raises `NotImplementedError`.
   - `plumb/awareness/__init__.py`: `publish`, `note_edit` do nothing, `overlaps` returns
     `()`, `brief_lines`, `delta_lines` return `[]`, `snapshot_fields` returns `{}`.
4. **Call sites, wired once, so lanes edit only their own modules.**
   - `Store.next_id(kind)` calls `ids.reserve(paths, kind)`; `Store.peek_id(kind)` calls
     `ids.peek`; `plumb capture --dry-run` and every preview use `peek_id`.
   - `importer/apply.py` calls `ids.observe` with the IDs it wrote.
   - `confirm.confirmation_of` consults `ids.approval_aliases(core)` (empty in the stub).
   - `claims.py` (ingestion and `claims check`) reads trailers through
     `ids.trailer_aliases(core)`.
   - `boundary/report.merge_report` fills `id_collisions` from `ids.collisions`,
     `intent_conflicts` from `mergedriver.open_conflicts`, `unmerged` from one
     `git ls-files -u -- .plumb/` call, and `legacy_log_lines` from `log` (0 today);
     `exit_code` adds 1 for `id_collisions` and `unmerged`, 4 for `intent_conflicts`;
     `render` prints the three sections (the conflict section calls
     `mergedriver.conflict_card`).
   - `boundary/cli.py` accepts `--hook pre-merge-commit`, `--install-pre-merge-commit`,
     `--uninstall-pre-merge-commit`, routed to `plumb.boundary.premerge` (a stub module
     raising `NotImplementedError` until MERGEDRIVER replaces it).
   - Hooks: `session_start` appends `awareness.brief_lines` to the brief and counts
     `open_conflicts` in it; `prompt` passes `awareness.delta_lines(core, relevant ids)`
     through `present.delta.emit`; `stop` calls `awareness.publish(core, changed paths)`,
     emits `awareness.delta_lines` for touched records, shows `conflict_card` for a
     conflict new this turn and adds `mergedriver.stated_entries` to `stated.json` as
     `conflicts`; `post_edit` calls `awareness.note_edit`; `snapshot` merges
     `awareness.snapshot_fields` and the conflict count.
   - `present/render.status_card` renders `overlaps` (`· 1 also changed on feat-x`, ASCII
     `overlap 1 (feat-x)`) and `conflicts` (`· 1 conflict awaits you`); `plumb status`
     lists overlaps (`present/report.py`).
   - `hosts/claude_code/install.py`: `hooks install|uninstall|status` call
     `mergedriver.install|uninstall|status`; deny rules for `plumb conflict choose` without
     `--prompt`, in the three launcher forms.
5. **Routes.** `cli.ROUTES` adds `merge-fix`, `ids` -> `plumb.ids.cli`; `log` ->
   `plumb.logcmd`; `merge-driver`, `conflict`, `conflicts` -> `plumb.mergedriver.cli`. Each
   lane's `cli` module starts as a stub that prints "not available in this build" (exit 2);
   `plumb --help` lists a verb only when its module is importable (SR-068).
6. **The `/plumb` command template** names `/plumb merge-fix`, `/plumb conflicts`,
   `/plumb merge-check`, choosing a side in plain words, "migrate the logs", "finish the
   merge", "call plumb from my merge hook", the text-merge and modify/delete choices, and
   overlaps under `/plumb status` (spec 11), and the R14 feature matrix in `docs/` gains the
   SP6 rows.
7. **Test helpers.** `tests/gitrepo.py` (temporary repositories, worktrees, clones);
   `tests/logutil.py` with `entries(root, stream)`, `raw_entries(root, stream)` and
   `tamper(root, stream, index, mutate)`, written against today's JSONL; the ten test files
   that read `events.jsonl` or `evidence.jsonl` directly (`tests/capture/capture_helpers.py`,
   `tests/core/test_cli_core.py`, `test_merge.py`, `test_primitives.py`, `test_validate.py`,
   `tests/integration/test_session_e2e.py`, `tests/merge/test_gates.py`,
   `tests/verify/test_aborted.py`, `test_evidence.py`, and `tests/core/test_log.py`) switch
   to the helper, so LOGS changes the format by changing the helper only.
   `tests/integration/test_contracts.py` checks every stub against its signature.
8. **Records.** FEAT-006, INT-022, SR-070 to SR-079 and DEC-020 to DEC-022 exist (written
   with this plan). Phase 0 links each stub module `implemented_by` its SR.
9. **Owner text, the R14 choke point (spec 11.1).** `src/plumb/present/owner_text.py` holds
   every SP6 owner-visible string as a constant or format function (the list of spec 12) and
   `bare_cli_verbs(text)`, matched against `cli.ROUTES` keys. Lanes import these and never
   write owner wording inline; a wording change goes through the coordinator.
   `tests/present/test_owner_text.py`: `test_bare_cli_verbs_flags_plumb_verbs` (`plumb
   merge-fix`, `uv run plumb log migrate`), `test_slash_command_passes` (`/plumb merge-fix`,
   `/plumb status`), `test_plumb_colon_prefix_passes` ("plumb: SR-005 ..."),
   `test_every_constant_passes`.

### 3.3 Phase-0 gate

```
uv run pytest tests/core tests/host tests/merge tests/verify/test_evidence.py tests/verify/test_aborted.py tests/integration/test_contracts.py tests/present/test_owner_text.py tests/test_smoke.py -q
uv run ruff check src tests
uv run plumb validate && uv run plumb drift
uv run plumb --help        # lists only importable verbs
```

Then the four worktrees are created from that `main`.

### 3.4 Lane gate (each merge point and before handing back)

```
uv run pytest <the lane's focused set> -q      # foreground, once, timeout 600000 ms
uv run ruff check src tests
uv run plumb validate && uv run plumb drift     # no errors
uv run plumb claims check --range main..HEAD    # no undeclared path
git diff --name-only main...HEAD               # every path in the lane's row of 3.1
```

Focused sets: IDS `tests/ids tests/core/test_store.py tests/capture/test_records.py
tests/capture/test_capture.py`; LOGS `tests/logs tests/core/test_log.py
tests/core/test_validate.py tests/core/test_merge.py tests/core/test_primitives.py
tests/merge/test_gates.py tests/verify/test_evidence.py tests/verify/test_aborted.py`;
MERGEDRIVER `tests/mergedriver tests/merge tests/host/test_install.py`; AWARENESS
`tests/awareness tests/host/test_session_start.py tests/host/test_prompt.py
tests/host/test_stop.py tests/host/test_statusline.py tests/host/test_latency.py`.

The lane reports `merge-ready <lane> <merge point> <sha>`. The coordinator merges with
`git merge --no-ff` (message with the merged rows' `SR:` trailers) and runs the merged lane's
focused set once on `main`; it does not run the whole suite until phase 2.

### 3.5 Interface contracts between lanes

| Provider | Interface | Consumers | Degraded form while missing |
|---|---|---|---|
| IDS | `ids.reserve`, `peek`, `observe` | every record writer through `Store.next_id`; MERGEDRIVER (`IC` IDs, `reserve_ic`) | highest local number plus one (today's behaviour) |
| IDS | `ids.collisions`, `approval_aliases`, `trailer_aliases` | the merge report, `confirm`, `claims` | duplicates from `Store.problems()`; no aliases |
| LOGS | `log.append`, `read`, `verify_chain` (signatures kept, `since` added), `LogEntry.name` | every lane through `CoreAPI` | today's JSONL |
| MERGEDRIVER | `open_conflicts`, `conflict_card`, `stated_entries`, `install`, `uninstall`, `status`, `boundary.premerge` | the merge report, the hooks, `hooks install` | no conflicts; "merge driver: not available" |
| AWARENESS | `publish`, `note_edit`, `overlaps`, `brief_lines`, `delta_lines`, `snapshot_fields` | the hooks, the status card, `plumb status` | nothing shown |
| Coordinator | the data classes, routes, call sites and config keys of 3.2; `present.owner_text` (every owner-visible string, `bare_cli_verbs`) | all | frozen; changes only through the coordinator |

Unit tests never import another lane's new modules; they use the phase-0 stubs or local
fakes. MERGEDRIVER's `merge_texts` takes `reserve_ic` as a parameter, so its unit tests need
no git; its real-git tests run with the IDS stub (local numbering), which is enough for one
clone.

## 4. Lane IDS (spec 4, 5 and the ID part of 10)

Goal: no two worktrees ever get one ID; collisions from other clones are renumbered at merge
with every reference rewritten and nothing in history touched.

| # | Task | SR | Est. |
|---|---|---|---|
| I1 | `ids/ref.py`: read and write the ref blob (`rev-parse`, `cat-file`, `hash-object -w`, `update-ref` with the old oid or the zero oid), canonical JSON, `recent` capped at 50 | SR-070 | 20 min |
| I2 | `ids/reserve.py`: `reserve` (batch per prefix, compare-and-swap loop with jittered retry, 50 tries / 3 s, exit-2 message `owner_text.ID_BUSY`), `peek`, `observe`, `state`; the no-git fallback line `owner_text.ID_UNRESERVED`; `IC` prefix | SR-070 | 25 min |
| I3 | Seeding from this worktree and every local branch tip (`for-each-ref`, one `ls-tree` per branch, once per clone); `plumb ids` (status) and `plumb ids sync` in `ids/cli.py` | SR-070 | 15 min |
| I4 | `ids/collisions.py`: unmerged add/add record paths (stages 2 and 3), duplicate IDs at different paths, `--from <ref>` preview; `collisions(core, base)` for the merge report (exit 1, `owner_text.COLLISION`) | SR-071, SR-072 | 20 min |
| I5 | `ids/mergefix.py`: keep the first parent, reserve after `observe`, rewrite every reference the incoming side introduced (spec 5.3, each place), keep both when both sides introduced it, repin pure-renumber pins, rewrite `MERGE_MSG`/`SQUASH_MSG` trailers, `git add`, `--dry-run` with `peek`, idempotent | SR-071 | 35 min |
| I6 | The `renumber` event; `approval_aliases` (carried only while the content with the old ID hashes to the pin); `trailer_aliases`; the `plumb validate` re-check of `renumber` entries through the phase-0 call site | SR-071 | 25 min |
| I7 | `plumb merge-fix` CLI (`ids/cli.py`): output in the owner's terms (titles, `owner_text.RENUMBERED`), `--json`, exits 0/1/2 | SR-071 | 10 min |

Total: 150 min. Merge points: after I3, after I6, at the end.

Tests (`tests/ids/`), each marked with its SR:

- I1, I2 `test_reserve.py`: `test_first_reserve_creates_ref_and_returns_next`,
  `test_two_worktrees_never_get_the_same_id` (real `git worktree add`, interleaved
  reservations from both roots), `test_concurrent_processes_get_distinct_ids` (two
  subprocesses, ten reservations each, all distinct, `high` equals the last),
  `test_moved_ref_retries_and_never_reuses` (the ref moved between read and update by a
  monkeypatched hook), `test_busy_ref_gives_up_with_exit_2`,
  `test_batch_reserves_once_per_prefix`, `test_peek_does_not_move_the_ref`,
  `test_no_git_falls_back_and_says_not_reserved`, `test_ic_prefix_three_digits`,
  `test_nc_four_digits`
- I3 `test_seed.py`: `test_seed_from_an_unchecked_out_branch` (SR-070 EX-2),
  `test_seed_runs_once_per_clone`, `test_observe_raises_high_for_imported_ids`,
  `test_ids_sync_rescans`
- `test_entry_points.py` (spec 4.5, one test each): `plumb new` per kind, `plumb intent`,
  `plumb decide`, `plumb decide --supersede`, `plumb capture`, `plumb capture --dry-run`
  (no reservation), the importer (`observe`), `reserve(kind="conflict")`; plus
  `test_no_module_computes_record_numbers_outside_store_and_ids` (conformance scan of
  `src/plumb`)
- I4 `test_collisions.py`: `test_unmerged_add_add_is_a_collision`,
  `test_same_content_add_add_is_not`, `test_duplicate_ids_at_two_paths`,
  `test_from_ref_preview_writes_nothing`, `test_merge_report_exits_1_with_fix_line`
  (through `plumb check --merge` and `plumb merge-check`), `test_no_collision_after_fix`
- I5 `test_mergefix.py`: `test_clone_collision_renumbers_incoming` (a real `git clone`,
  both sides create the same SR, fetch, merge stops, `merge-fix` resolves; SR-071 EX-1),
  and one test per rewritten place of spec 5.3: `test_rewrites_links_to`,
  `test_rewrites_feature_and_requirements`, `test_rewrites_members_supersedes_decides`,
  `test_rewrites_example_references`, `test_rewrites_body_wikilinks`,
  `test_rewrites_incoming_test_markers_only`, `test_rewrites_claims_baseline_nc`,
  `test_rewrites_merge_msg_trailer`; plus `test_our_side_reference_untouched` (EX-4),
  `test_both_sides_reference_keeps_both`, `test_pure_renumber_pins_repinned_other_stale_kept`,
  `test_history_unchanged` (`git log` of the incoming commits byte-identical; EX-2),
  `test_stages_but_never_commits`, `test_dry_run_writes_and_reserves_nothing`,
  `test_second_run_is_a_no_op` (EX-5)
- I6 `test_aliases.py`: `test_approval_carried_for_pure_renumber` (EX-3),
  `test_approval_not_carried_after_an_edit`, `test_approval_of_other_content_not_carried`,
  `test_claims_reads_incoming_trailers_as_new_id`, `test_validate_rejects_forged_renumber`
- I7 `test_cli.py`: `test_output_names_titles_not_paths`, `test_json_shape`,
  `test_exit_codes`
- `test_owner_text.py` (spec 11.1, one test per surface, each asserting
  `bare_cli_verbs(output) == []`): `test_fallback_line` (SR-070), `test_busy_error`
  (SR-070), `test_merge_fix_output` (SR-071), `test_collision_section` (SR-072, through
  `plumb check --merge` and `plumb merge-check`)

Definition of done: spec 14 items 1 and 3 for SR-070 to SR-072.

## 5. Lane LOGS (spec 6)

Goal: one file per log entry; the JSONL logs migrated without changing a digest; readers that
accept both formats; integrity checks that still catch an edit or a deletion.

| # | Task | SR | Est. |
|---|---|---|---|
| L1 | `paths.py`: `log_kind_dir(kind)`, `log_head`, `log_pack(stream)`; `log.STREAM_OF_KIND`; entry file naming (new and migrated stamps and suffixes) and its parser | SR-073 | 15 min |
| L2 | `log.append`: per-worktree lock, head pointer (rebuilt by a scan), temporary file plus no-replace `os.link`, fsync, new suffix on a clash | SR-073 | 25 min |
| L3 | `log.read`: both formats, dedup by digest, order by `at` then chain then name, the pack cache, `LogEntry.name`, `since`; `verify_chain` over both formats with file names in the messages | SR-073, SR-074 | 30 min |
| L4 | `verify/evidence.load_index`: the name cursor and the rebuild when an entry arrives out of order; `merge.log_integrity`: one `git diff --name-status` for entry files, the legacy line check by digest | SR-073, SR-074 | 25 min |
| L5 | `logcmd.py`: `plumb log migrate [--dry-run] [--check] [--json]` (refuse on a bad line, skip existing names, truncate the legacy files only when complete, rebuild caches); `plumb validate` and the merge report's legacy-line warning (`owner_text.LEGACY_LOG`) through the phase-0 call; `plumb init` stops creating JSONL files | SR-074 | 30 min |
| L6 | `tests/logutil.py` moves to the per-entry format (reads both), so the ten rewired test files pass unchanged; `SR-006`'s statement and EX-2 updated to the per-entry layout through `plumb capture` `updates` (it stays proposed) | SR-073 | 15 min |
| L7 | Latency: a warm `read` of 2000 events under 60 ms with the pack cache, cold under 1 s, measured in `tests/logs/test_read_cost.py` | SR-073 | 10 min |

Total: 150 min. Merge points: after L3, after L5, at the end.

Tests (`tests/logs/`), each marked with its SR:

- L1, L2 `test_append.py`: `test_one_file_per_entry_under_kind`,
  `test_stream_of_kind_evidence_and_events`, `test_same_second_writers_never_replace`
  (SR-073 EX-2; two processes), `test_prev_is_stream_head`,
  `test_head_rebuilt_by_scan_when_deleted` (EX-4), `test_name_stamp_and_suffix_parse`
- L3 `test_read.py`: `test_order_at_then_chain_then_name`,
  `test_both_formats_deduplicated_by_digest`, `test_pack_cache_reads_only_new_files`,
  `test_pack_cache_drops_vanished_names`, `test_corrupt_pack_cache_rebuilt`,
  `test_since_skips_applied_names`
- `test_verify.py`: `test_edited_entry_reported_by_file` (EX-3),
  `test_deleted_entry_named_by_prev_reported`, `test_unparsable_file_reported`,
  `test_forked_chain_accepted`, `test_migrated_suffix_must_match_digest`
- `test_two_worktrees.py`: `test_appends_in_two_worktrees_merge_without_conflict`
  (real worktrees; approvals, prompts and test runs on both; `git merge` clean; validate
  clean; both sides' entries read; SR-073 EX-1)
- L4 `test_integrity.py`: `test_modified_entry_file_since_fork_reported`,
  `test_deleted_entry_file_since_fork_reported`,
  `test_legacy_lines_at_fork_satisfied_by_migrated_entries`;
  `test_evidence_index_rebuilds_on_out_of_order_entry`
- L5 `test_migrate.py`: `test_digests_and_prev_unchanged` (EX-1),
  `test_second_run_writes_nothing` (EX-2), `test_independent_migrations_merge_clean`
  (two branches migrate, merge, no conflict, no duplicate),
  `test_pre_migration_branch_merges_then_migrates` (EX-3: old branch appends to the JSONL
  after the migration on `main`; `merge=union` leaves the new lines; readers see them; the
  next migration moves them), `test_evidence_reuse_identical_before_after` (EX-4:
  `load_index` and the freshness of every node unchanged),
  `test_approvals_and_confirmations_unchanged`, `test_bad_line_refuses_and_writes_nothing`
  (EX-5), `test_check_exits_1_while_legacy_lines_remain`, `test_dry_run_writes_nothing`,
  `test_init_creates_no_jsonl`
- `test_single_writer.py`: `test_only_log_py_writes_under_plumb_log` (conformance scan)
- `test_owner_text.py` (spec 11.1): `test_validate_warning`, `test_merge_report_warning`
  (SR-074; each with legacy lines left and asserting `bare_cli_verbs(output) == []`)
- L7 `test_read_cost.py`

Definition of done: spec 14 items 1 and 4 for SR-073 and SR-074 (item 4's migration of
plumb's own logs happens in phase 2).

## 6. Lane MERGEDRIVER (spec 7, 8 and the intent-conflict part of 10)

Goal: record files merge field by field; a real content conflict becomes an intent conflict
the owner resolves; the merge boundary and a pre-merge-commit hook hold it.

| # | Task | SR | Est. |
|---|---|---|---|
| D1 | `mergedriver/merge.py`: `merge_texts` (pure): the field rules of spec 7.3 (links, string lists, examples with EX renumbering, scalars, body via `git merge-file -p`), stable key order, notes for stderr | SR-075 | 35 min |
| D2 | Add/add and fallbacks: same ID and different content -> ours, exit 1 with `owner_text.ADD_ADD`; equal content -> one, exit 0; unparsable side -> `git merge-file` on the whole text and its status (`owner_text.UNPARSABLE` in validate and the `unmerged` section) | SR-075 | 10 min |
| D3 | `mergedriver/driver.py` and `cli.py`: `plumb merge-driver %O %A %B %P %X %Y` (labels, older-git fallback from `HEAD`/`MERGE_HEAD`/`REBASE_HEAD`/`CHERRY_PICK_HEAD`), import-light, under 300 ms | SR-075 | 15 min |
| D4 | `mergedriver/install.py`: `.plumb/.gitattributes` lines and git config keys, idempotent, foreign lines kept, uninstall exact, status line; called from `hooks install` (phase-0 site) | SR-075 | 15 min |
| D5 | Intent conflict: the `conflict` block (spec 8.1) with `IC` from `reserve_ic`; `open_conflicts`; `plumb show IC-###`; `conflict_card` (spec 8.3) with the optional compatibility judgment (once per pair of hashes, logged, 5 s limit, "no judgment available" otherwise); `stated_entries` | SR-076 | 30 min |
| D6 | `plumb conflicts`, `plumb conflict propose`, `plumb conflict choose` (owner terminal through `approvals.require_owner`; relay through `approvals.owner_prompt` with the stated-set and choice-naming checks of spec 8.4; reservations and change clauses refused), the `conflict-resolution` event, re-confirmation by an existing approval of the chosen side | SR-076 | 25 min |
| D7 | `boundary/premerge.py`: install/uninstall of the pre-merge-commit hook (foreign hook left), `--hook pre-merge-commit` (base `HEAD`, staged result, claims `HEAD..MERGE_HEAD`, full run per `merge.premerge_run_full`) | SR-077 | 20 min |

Total: 150 min. Merge points: after D4, after D6, at the end.

Tests (`tests/mergedriver/`), each marked with its SR:

- D1 `test_fields.py` (pure, no git): `test_links_added_on_both_sides_union` (SR-075
  EX-1), `test_link_removed_on_one_side_removed`, `test_pin_divergence_keeps_ours_no_conflict`,
  `test_title_change_and_new_example_merge` (EX-2), `test_independent_fields_merge`,
  `test_string_lists_set_merge`, `test_same_item_rewritten_both_sides_conflicts`,
  `test_examples_added_both_sides_kept`, `test_same_new_ex_number_renumbered_with_links`
  (EX-3), `test_example_changed_both_sides_conflicts`,
  `test_example_removed_one_side_changed_other_conflicts`, `test_scalar_conflict_block`,
  `test_body_clean_merge`, `test_body_conflict`, `test_formatting_only_difference_clean`,
  `test_result_hash_matches_neither_side_on_conflict`
- D2 `test_add_add.py`: `test_same_id_different_content_exit_1_ours_kept`,
  `test_equal_content_exit_0`, `test_unparsable_side_falls_back_to_text_merge`
- D3, D4 `test_install.py`: `test_install_writes_attributes_and_config_once` (EX-4),
  `test_foreign_attributes_kept`, `test_uninstall_removes_exactly_plumb_lines`,
  `test_status_reports_attribute_without_driver`, `test_launcher_matches_commit_msg_hook`
- `test_git_merge.py` (real repository and two worktrees, driver installed):
  `test_non_overlapping_changes_merge_clean`, `test_content_conflict_becomes_ic`
  (SR-076 EX-1: labels `main` and `feat-x`, record unconfirmed, merge completed),
  `test_rebase_uses_the_same_driver`, `test_driver_under_300_ms`
- D5 `test_conflict_card.py`: `test_card_shows_both_versions_and_what_merged` (EX-2),
  `test_card_in_owner_terms_example_as_given_when_then`,
  `test_no_backend_says_no_judgment_available` (EX-5),
  `test_fake_jev_judgment_logged_once_per_pair`, `test_show_ic_and_show_record`
- D6 `test_choose.py`: `test_owner_terminal_choice_writes_resolution`,
  `test_choose_refused_without_terminal` (no marker, stdin a pipe with "y": exit 3,
  nothing written), `test_choose_refused_under_marker_without_prompt` (EX-4),
  `test_relay_needs_logged_prompt_and_card_in_stated_set`,
  `test_relay_quote_must_name_one_side`, `test_relay_with_reservation_refused`,
  `test_choosing_a_confirmed_side_reconfirms` (EX-3), `test_combined_stays_proposed`,
  `test_propose_never_applies`, `test_deny_rule_present_in_three_launcher_forms`
- D7 `test_premerge.py`: `test_merge_check_exits_4_with_card` (SR-077 EX-1, through
  `plumb check --merge` and `plumb merge-check`), `test_hook_refuses_merge_commit_on_ic`
  (EX-2, real `git merge` with the hook installed: no merge commit, `MERGE_HEAD` kept,
  output names `/plumb conflicts`), `test_commit_completes_after_choice`,
  `test_foreign_hook_untouched` (EX-3), `test_uninstall_removes_only_plumb_hook`
- `test_owner_text.py` (spec 11.1, one test per surface, each asserting
  `bare_cli_verbs(output) == []`): `test_driver_stderr` (merged, add/add and text fallback;
  SR-075), `test_driver_status` (SR-075), `test_unmerged_section` (modify/delete, unparsable
  side, no driver; SR-077), `test_conflict_card` (SR-076), `test_choose_messages`
  (refusal and result; SR-076), `test_premerge_hook_output` (refusal with `MERGE_HELD`, and
  the foreign-hook install text; SR-077)

Definition of done: spec 14 items 1, 2 (driver and conflict parts) and 6 for SR-075 to
SR-077.

## 7. Lane AWARENESS (spec 9)

Goal: every session hears, once, that another worktree or branch is changing the records it
works on, from cheap read-only reads.

| # | Task | SR | Est. |
|---|---|---|---|
| A1 | `awareness/gitfiles.py`: the common directory, worktrees (`worktrees/*/gitdir`, `HEAD`), branch tips (`refs/heads/**`, `packed-refs`) read as files; missing paths ignored | SR-079 | 20 min |
| A2 | `awareness/publish.py`: `publish` (changed records, `edited`/`new`/`ends`, the committed part recomputed only when `HEAD` moved), `note_edit` (append a path, no index), atomic write of `changing.json` | SR-079 | 25 min |
| A3 | `awareness/scan.py`: `overlaps` over worktrees (age limit, own worktree skipped, record mapping with the reader's index too, the other side's hash) and, at session start, branches without a worktree (tip cache, `branch_max`, `branch_scan_ms`, default branch skipped) | SR-078, SR-079 | 35 min |
| A4 | `awareness/lines.py`: `brief_lines` (cap and `owner_text.MORE_OVERLAPS`, "+N more (/plumb status)"), `delta_lines` keyed `(overlap, record, branch, other hash)` for `present.delta`, `snapshot_fields` (`overlaps`, `overlap_labels`); wording of spec 9.4 in the owner's terms | SR-078 | 25 min |
| A5 | Budget: the deadline passed by the hooks; "awareness skipped (budget)" to the error log; the 50 ms warm check with five worktrees and no git process on the prompt path | SR-079 | 20 min |
| A6 | `plumb status` overlap section data (`present/report.py` renders it through the phase-0 site) | SR-078 | 10 min |

Total: 135 min. Merge points: after A2, after A4, at the end.

Tests (`tests/awareness/`), each marked with its SR:

- A1 `test_gitfiles.py`: `test_finds_linked_and_main_worktrees_without_git`,
  `test_branch_tips_from_loose_and_packed_refs`, `test_removed_worktree_ignored`
  (SR-079 EX-4)
- A2 `test_publish.py`: `test_publishes_edited_new_and_ends`,
  `test_committed_part_recomputed_only_when_head_moved` (git call count),
  `test_note_edit_appends_path_without_index`, `test_write_is_atomic`
- A3 `test_two_worktrees.py` (real worktrees): `test_brief_names_record_and_branch`
  (SR-078 EX-1), `test_delta_line_once_then_again_after_other_side_changes` (EX-2),
  `test_no_overlap_no_line_and_no_status_field` (EX-4),
  `test_other_worktree_untouched` (EX-3: file listing and mtimes of the other worktree
  unchanged, no lock file created there), `test_stale_changing_json_ignored`,
  `test_reader_maps_paths_with_own_index`
- `test_branches.py`: `test_branch_without_worktree_reported_at_session_start` (EX-3 of
  SR-078), `test_unmoved_tip_runs_no_git` (SR-079 EX-2), `test_scan_capped_by_branch_max`,
  `test_scan_capped_by_deadline`, `test_default_branch_skipped`
- A4 `test_lines.py`: `test_brief_cap_and_more_line`, `test_wording_matches_spec`,
  `test_snapshot_fields_and_status_card_text` (Unicode and ASCII)
- A5 `test_budget.py`: `test_five_worktrees_under_50_ms_warm_no_git_process`
  (SR-079 EX-1; `subprocess.run` patched to fail the test),
  `test_budget_exhausted_skips_quietly`
- `test_owner_text.py` (spec 11.1, one test per surface, each asserting
  `bare_cli_verbs(output) == []`, SR-078): `test_brief_lines` (with the overflow line),
  `test_delta_and_stop_lines`, `test_status_card` (Unicode and ASCII),
  `test_status_section`

Definition of done: spec 14 items 1, 2 (awareness part) and 5 for SR-078 and SR-079.

## 8. Phase 2: Integrate (coordinator, on `main`)

### 8.1 Merge order

1. LOGS first (the format every later merge writes). After the merge, run
   `uv run plumb log migrate` on plumb's own repository and commit the result alone
   (`SR: SR-074`): 510+ events and 18+ evidence entries become files with unchanged digests,
   then `uv run plumb validate` (clean) and the evidence lines of `uv run plumb status --json`,
   captured before and after, are identical (the same tests fresh; spec 14 item 4).
2. IDS, MERGEDRIVER, AWARENESS, in the order they report ready. Each was branched before
   the migration and appended to `events.jsonl`: its merge must be clean (`merge=union` on
   the emptied file), and `uv run plumb log migrate` then moves its new lines (a live run of
   SR-074 EX-3). Run `uv run plumb log migrate --check` after each merge.
3. After each merge, the merged lane's focused set once.

### 8.2 Reinstall and dogfood

- `uv run plumb hooks install` (the record merge driver joins the commit-msg hook);
  `uv run plumb hooks status` shows the driver; `.plumb/.gitattributes` holds its lines.
- `uv run plumb ids sync` seeds `refs/plumb/ids` from `main` and the remaining local branches
  (`lane/*`, `work`, `feat/jev-openrouter`): `high` covers SR-079, DEC-022, INT-022,
  FEAT-006.
- `uv run plumb merge-check --install-pre-merge-commit` is NOT run on plumb's repository
  without the owner's request (it changes how the owner's merges behave); the README says
  how to ask for it.

### 8.3 The e2e scenarios and the single full run

- Write `tests/integration/test_parallel_e2e.py` (spec 14 items 2 and 3): the two-worktree
  scenario and the clone scenario, end to end through the CLI and the real hooks
  (session-start, prompt and stop driven as in `test_session_e2e.py`), each marked with every
  SR it covers; every hook output and merge report they capture passes
  `owner_text.bare_cli_verbs` (spec 11.1). Run it once in the foreground.
- Update `docs/concept.md` 4.3 (IDs reserved through `refs/plumb/ids`), 4.7 (the migration
  is done) and 7.5 (the three new sections), the README (parallel work, in the owner's
  terms, no shell commands for the owner) and the R14 feature matrix.
- The ONE full-suite run: `uv run plumb merge-check <phase-0 base>` (the `main` commit
  before phase 0), which
  runs the full suite once with evidence pinned to identity (sp3 4), with `-n 2` at most.
  Its report must show no ID collision, no intent conflict and no unmerged record path, and
  otherwise exit 4 only because plumb's records await the owner (no agent approves them).

### 8.4 Integrate gate

```
uv run plumb validate && uv run plumb drift
uv run plumb log migrate --check                   # exit 0: no legacy line left
uv run plumb claims check --range <phase-0 base>..HEAD
uv run plumb merge-check <phase-0 base>            # the single full run; exit 4 only for owner confirmations
uv run pytest tests/host/test_latency.py tests/awareness/test_budget.py -q   # budgets hold
```

Cut first if Integrate overruns (polish only, never a MUST): the README wording pass, then
the concept wording pass (both then go to `docs/followups.md` as open items).

## 9. Phase 3: Review

Independent intent verifiers read the brief (R10 and R14 in particular), the concept, this
spec and the merged code, and try the scenarios themselves in a temporary repository:

1. Two worktrees creating records at once never share an ID; a clone collision is renumbered
   with every reference rewritten and history untouched.
2. No log merge conflicts; the migration kept every digest and the evidence identities.
3. Non-overlapping record changes merge; a content conflict becomes an intent conflict with
   both versions, stays unconfirmed, and only the owner's explicit words choose (R2).
4. Awareness lines appear once, in the owner's terms, and cost no git process per prompt.
5. `plumb check --merge` holds collisions (1) and intent conflicts (4).
6. No owner-facing text names a shell command (R14): every surface of spec 11.1 has its
   passing test and draws its wording from `present.owner_text`.

Severity follows R7: HIGH only for a genuine contradiction or omission of the owner's
explicit words, decisions or rulings. HIGH findings are fixed by class (owner rule 1);
medium and low go to `docs/followups.md` under `## SP6 review (2026-10-..)`.

## 10. Definition of done (the batch)

1. Spec 14 items 1 to 7 hold on `main`.
2. Every lane's tests of sections 4 to 7 exist, marked with their SRs, and pass in the single
   full run.
3. FEAT-006's requirements are linked `implemented_by` their modules and `verified_by` their
   tests (`plumb validate` and `plumb drift` clean), and stay proposed: no agent approved
   any of them.
4. plumb's own logs are per-entry files; `refs/plumb/ids` exists; the record merge driver is
   installed in plumb's repository.
5. No HIGH finding is open; medium and low findings and anything unfinished are in
   `docs/followups.md`.
