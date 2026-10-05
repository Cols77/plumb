# Sub-project 1 implementation plan

Implements `docs/specs/sp1-grounding-loop.md` (the spec). The owner does not review this plan;
verifier agents check it against the owner intent brief, rulings R1 to R7 and the spec. Section
numbers such as "spec 5.6" refer to the spec.

## 1. Shape of the work

| Phase | What | Who | Agent time | Gate before the next phase |
|---|---|---|---|---|
| 0. Contracts | Package skeleton, frozen contracts, shared primitives, fakes, dispatcher | coordinator, on `main` | 35 min | `uv run pytest -q` and `uv run ruff check src tests` pass; contract tests green; committed |
| 1. Lanes | CORE, VERIFY, HOST, BRIDGE in parallel, each in its own worktree | four lane agents | 3 h each, in parallel | lane gate (section 3.3) green on the lane branch |
| 2. Integration | Merge the lanes, end-to-end and conformance tests, hook benchmark | coordinator | 45 min | whole suite and ruff green on `main`; benchmark recorded |
| 3. Review | One review agent per lane diff against the spec and brief, plus one intent verifier | review agents; fixes by coordinator | 30 min | no HIGH finding open; medium and low in `docs/followups.md` |
| 4. Dogfood | plumb records its own intent, installs its own hooks, commits with `SR:` trailers | coordinator | 60 min | dogfood checks (section 8.4) pass |

Total about 5 h 50 min of wall time, about 6 h of agent time on the critical path.

Orchestration uses the host's native mechanism: in Claude Code, the `Workflow` tool, with
phase 0, a `parallel()` of four lane `agent()` calls, then phases 2 to 4, each phase carrying
its gate. Starting that workflow needs the owner's opt-in where Claude Code asks for it; this
plan does not grant it.

## 2. Conventions for every agent

- Repository `C:/coding/plumb`. Lanes work in worktrees `C:/coding/plumb-wt/sp1-<lane>` on
  branches `sp1/<lane>`, created from `main` after phase 0
  (`git -C C:/coding/plumb worktree add C:/coding/plumb-wt/sp1-core -b sp1/core main`), then
  `uv sync` inside the worktree.
- Never write inside `C:/coding/pi-agent-factory` or its worktrees, never create worktrees of
  it, never run its `coherence` or `factory` commands. Read its files only. Copying a source
  file's content into plumb is reading.
- Test first: write the failing test, run it red, implement, run it green. Run focused tests
  while iterating (`uv run pytest tests/core/test_links.py -q`) and the lane's whole set once
  before each commit. No `-n` above 2; plumb's suite needs none.
- Do not kill processes you did not start. `plumb tests run` terminates only the pytest
  process it started.
- Commit in small steps with clear messages (`core: pin both link ends`), each ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. `SR:` trailers start at the
  dogfood commit (phase 4); from then on every commit carries one.
- Fix only HIGH review findings. Each lane appends its medium and low findings, and any
  unfinished item with its state, under its own heading at the end of `docs/followups.md`
  (`## SP1 lane CORE (2026-10-06)`); the coordinator keeps both sides of the append-only
  conflicts at merge.
- Hooks must stay well under 2 s per turn: follow spec section 10 (lazy imports, JSON caches,
  one `git status`, no tests in hooks).
- Dependencies: standard library and PyYAML at runtime; pytest and ruff for development.
  Nothing else.

## 3. Files and ownership

### 3.1 Ownership table (disjoint)

| Owner | Paths |
|---|---|
| Phase 0 (frozen after) | `pyproject.toml`, `uv.lock`, `src/plumb/__init__.py`, `src/plumb/__main__.py`, `src/plumb/cli.py`, `src/plumb/cliutil.py`, `src/plumb/contracts.py`, `src/plumb/paths.py`, `src/plumb/normalize.py`, `src/plumb/config.py`, `src/plumb/text.py`, `tests/conftest.py`, `tests/fakes.py`, `tests/contracts/**`, `tests/test_smoke.py` |
| CORE | `src/plumb/model.py`, `store.py`, `hashing.py`, `links.py`, `log.py`, `approvals.py`, `validate.py`, `merge.py`, `claims.py`, `query.py` (relevant, brief, why), `api.py`, `commands.py`; `tests/core/**` |
| VERIFY | `src/plumb/verify/**` (`__init__.py`, `imports.py`, `markers.py`, `testmap.py`, `select.py`, `pytest_plugin.py`, `runner.py`, `evidence.py`, `policy.py`, `envid.py`, `cli.py`); `tests/verify/**` |
| HOST | `src/plumb/hosts/__init__.py`, `src/plumb/hosts/claude_code/**` (`__init__.py`, `cli.py`, `hookio.py`, `session_start.py`, `prompt.py`, `post_edit.py`, `stop.py`, `snapshot.py`, `statusline.py`, `install.py`, `templates/SKILL.md`, `templates/plumb-command.md`, `templates/claude-md-block.md`, `templates/commit-msg`); `tests/host/**` |
| BRIDGE | `src/plumb/importer/**` (`__init__.py`, `pi_factory.py`, `cli.py`); `src/plumb/judgment/**` (`__init__.py`, `model.py`, `heuristic.py`, `tiers.py`, `jev.py`, `state.py`, `cascade.py`, `fidelity.py`, `cli.py`); `tests/bridge/**` including `tests/bridge/fixtures/pi_factory/**` |
| Phase 2 | `tests/integration/**`, `scripts/bench_hooks.py` |
| Phase 4 | `.plumb/**`, `.claude/**`, `CLAUDE.md`, `README.md` (usage section) |
| Any lane, append only | `docs/followups.md` (own heading) |

`src/plumb/hosts/claude_code/templates/*` are package data; phase 0 makes `uv_build` include
them (they sit inside the package).

### 3.2 Contracts

Spec section 12 is the contract: `contracts.py` (12.1), the factory functions (12.2), the
dispatcher (12.3), the shared primitives (12.4) and the file formats (12.5). A lane needing a
contract change stops that item, asks the coordinator, and works on its next item. The
coordinator changes the contract on `main`, updates spec section 12 in the same commit, and
tells every lane to rebase.

Lanes never import each other's modules in unit tests. They use `tests/fakes.py`. Calls across
lanes at run time go only through the factory functions of spec 12.2, imported inside the
function that needs them, so a missing lane degrades instead of failing at import.

### 3.3 Lane gate

Run inside the lane worktree before handing back:

```
uv run pytest tests/<lane> tests/contracts tests/test_smoke.py -q
uv run ruff check src tests
git diff --name-only main...HEAD   # every path must be in the lane's row of 3.1, or docs/followups.md
```

## 4. Phase 0: contracts (coordinator, on `main`)

| # | Task | Tests (written first) |
|---|---|---|
| P0.1 | `pyproject.toml`: add `pyyaml>=6` to dependencies; register the `sr` marker (`markers = ["sr(id): links a test to a plumb requirement"]`); `uv lock`; `uv sync` | `tests/test_smoke.py` still green |
| P0.2 | `src/plumb/contracts.py` exactly as spec 12.1 | `tests/contracts/test_shapes.py`: `test_dataclasses_are_frozen`, `test_link_id_format`, `test_id_regex_accepts_and_rejects`, `test_kind_tables_cover_every_kind` |
| P0.3 | `src/plumb/normalize.py` (spec 12.4) | `tests/contracts/test_normalize.py`: `test_crlf_and_lone_cr_become_lf`, `test_trailing_whitespace_and_blank_lines_dropped`, `test_nfc_normalization`, `test_derived_blocks_removed`, `test_canonical_json_sorted_compact_utf8`, `test_file_digest_binary_uses_raw_bytes` |
| P0.4 | `src/plumb/paths.py`, `src/plumb/config.py`, `src/plumb/text.py` (spec 12.4, 11) | `tests/contracts/test_primitives.py`: `test_find_root_prefers_plumb_dir`, `test_config_defaults_without_file`, `test_config_reads_yaml_and_caches_json`, `test_config_cache_invalidated_on_change`, `test_terms_and_overlap` |
| P0.5 | `src/plumb/cli.py` dispatcher and `cliutil.py` (spec 12.3); keep `--version` and help; help lists every routed command | `tests/contracts/test_dispatcher.py`: `test_every_route_names_a_module_path`, `test_unknown_command_exits_2`, `test_missing_module_reports_not_available`, `test_hook_route_does_not_import_argparse_commands_of_other_lanes` |
| P0.6 | `tests/fakes.py` and `tests/conftest.py` (spec 12.4) | `tests/contracts/test_conformance.py`: protocol conformance suite parametrized over available implementations (fakes now): `test_core_index_and_status_shapes`, `test_core_log_append_read_round_trip`, `test_core_write_record_and_add_link`, `test_verify_select_and_evidence_shapes`, `test_backend_returns_judgments` |
| P0.7 | Add the spec and plan links to `README.md`; `.gitignore` unchanged (plumb's own `.plumb/.gitignore` comes from `plumb init`) | none |
| P0.8 | Commit `chore: freeze SP1 contracts, primitives and dispatcher`; create the four worktrees | gate of section 1 |

## 5. Lane CORE

Goal: the record model, hashing, links and staleness, the logs, approvals with the guard,
validation and the merge boundary, `SR:` trailers and claims, the CORE commands, and
`plumb.api.open_core`. Extraction sources: spec 13 (`register.py`, `claims.py`,
`relations.py`, `fingerprint.py`).

Tasks in build order. **M** = must (morning minimum), **S** = stretch (dropped from the end
first; recorded in `docs/followups.md` if unfinished).

| # | Task | M/S | Est. |
|---|---|---|---|
| C1 | `model.py`: frontmatter split and parse into `Record` (all five kinds, examples, AC examples, links, wikilinks); ID validation | M | 20 min |
| C2 | `hashing.py`: record hash (spec 5.4); file end hash with `(size, mtime_ns)` cache | M | 15 min |
| C3 | `store.py`: index load with `.plumb/cache/index.json`; next ID; `write_record` (YAML dump with stable key order); duplicate detection | M | 20 min |
| C4 | `links.py`: target parsing (`ID`, `path`, `path::Qual.name`, `path::test`), allowed-kind matrix, `add_link` with pins, `link_states`, `repin` | M | 25 min |
| C5 | `log.py`: JSONL append with lock, `prev` and `digest`, `log_read` from an offset, chain verification | M | 20 min |
| C6 | `approvals.py`: derived confirmation, `approve` (marker refusal), `--proposed`, `revoke`, `relay` with the four checks, `prompt` event copy, covered state | M | 30 min |
| C7 | `validate.py`: errors and warnings of spec 5.10; approval re-checks; `drift` | M | 20 min |
| C8 | `query.py`: `relevant`, `brief_lines` (30-line cap), `why`; `api.py` `open_core` (CoreAPI) | M | 20 min |
| C9 | `commands.py`: `init`, `new`, `show`, `link`, `repin`, `approve`, `relay`, `revoke`, `validate`/`check`, `status`, `drift`, `brief`, `why`, `log`, `trailers check-msg` | M | 25 min |
| C10 | `merge.py`: `validate --merge <base>` (spec 5.11), log integrity against git | M | 20 min |
| C11 | `hashing.py`: symbol and test-node end hashes with `ast` | S | 15 min |
| C12 | `claims.py`: `claims check` over a range, `claims.yaml`, exempt globs, baseline | S | 20 min |

Tests (`tests/core/`), each written red first:

- `test_model.py`: `test_parses_each_kind_from_frontmatter`,
  `test_identity_comes_from_frontmatter_not_filename`, `test_rejects_malformed_id`,
  `test_requirement_examples_parsed_with_ids`, `test_imported_acceptance_examples_keep_ac_ids`,
  `test_wikilinks_extracted_from_body`
- `test_hashing.py`: `test_record_hash_ignores_yaml_style_and_key_order`,
  `test_record_hash_ignores_links_field`,
  `test_record_hash_ignores_crlf_trailing_space_and_derived_blocks`,
  `test_record_hash_changes_on_statement_edit`, `test_file_end_hash_ignores_crlf`,
  `test_hash_cache_reuses_unchanged_files`; stretch C11: `test_symbol_end_ignores_edits_elsewhere`,
  `test_test_end_drops_parametrize_ids`, `test_missing_symbol_is_dangling`
- `test_store.py`: `test_new_assigns_next_id_per_kind`, `test_nc_ids_have_four_digits`,
  `test_write_record_round_trips`, `test_index_cache_reparses_only_changed_files`,
  `test_duplicate_ids_reported`
- `test_links.py`: `test_add_link_pins_both_ends`, `test_pin_drift`, `test_crlf_is_not_drift`,
  `test_source_edit_marks_source_moved`, `test_dangling_record_and_path`,
  `test_unpinned_link_warns`, `test_link_kind_allowed_matrix`,
  `test_repin_refreshes_pins_and_logs_event`, `test_repin_does_not_confirm`
- `test_log.py`: `test_append_chains_prev_digest`, `test_digest_detects_modified_line`,
  `test_missing_prev_detected`, `test_union_merged_fork_accepted`,
  `test_concurrent_appends_do_not_interleave`, `test_read_since_offset`,
  `test_marker_recorded`
- `test_approvals.py`: `test_proposed_until_approved`, `test_approval_pins_current_hash`,
  `test_edit_after_approval_is_unconfirmed_edit`, `test_revocation_returns_to_proposed`,
  `test_approve_refused_under_marker`, `test_approve_proposed_pins_all_listed`,
  `test_relay_accepts_affirming_quote_from_logged_prompt`,
  `test_relay_rejects_quote_not_in_prompt`, `test_relay_rejects_quote_without_affirmation`,
  `test_relay_rejects_record_outside_stated_set_unless_named`,
  `test_relay_writes_prompt_event_before_approval`, `test_relay_accepts_unique_digest_prefix`,
  `test_no_approval_from_non_affirming_prompt`, `test_covered_requires_verified_by_per_example`
- `test_validate.py`: `test_clean_repo_passes`, `test_errors_exit_one`,
  `test_warnings_for_stale_unconfirmed_uncovered`, `test_sr_without_derives_from_warns`,
  `test_untranslated_intent_items_warn`, `test_matters_false_deciding_confirmed_record_warns`,
  `test_owner_approval_under_marker_is_error`, `test_relayed_approval_without_prompt_event_is_error`
- `test_merge.py`: `test_merge_refuses_unconfirmed_touched_requirement`,
  `test_merge_touch_via_implemented_by_end`, `test_merge_touch_via_sr_trailer`,
  `test_merge_passes_after_approval`, `test_merge_lists_approvals_in_range`,
  `test_merge_requires_deciding_matters_dec`, `test_merge_detects_rewritten_log_line`,
  `test_merge_lists_unjudged_fidelity`, `test_merge_reports_verification_unavailable_without_verify`
- `test_claims.py`: `test_parse_sr_trailer_variants`, `test_check_msg_rejects_unknown_id`,
  `test_check_msg_requires_trailer_when_configured`; stretch C12:
  `test_claims_reports_undeclared_paths`, `test_claims_default_exempt_globs`,
  `test_claims_baseline_entries`
- `test_cli_core.py`: `test_init_is_idempotent_and_writes_ignore_and_attributes`,
  `test_new_show_round_trip_json`, `test_link_cli_target_forms`, `test_status_json_counts`,
  `test_drift_lists_moved_end`, `test_brief_respects_line_cap`, `test_why_walks_to_intent_quotes`,
  `test_log_reads_streams`, `test_relevant_ranks_named_ids_first`,
  `test_superseded_records_excluded_from_brief_and_relevant`

## 6. Lane VERIFY

Goal: the test map, covering-test selection, the pytest runner with identity-pinned
evidence, the failure policy, `plumb tests`, `plumb impact` and `plumb.verify.open_verify`.
Extraction sources: spec 13 (`imports.py`, `markers.py`, `failure_policy.py`,
`pytest_evidence_plugin.py`, `evidence.py`). The lane uses `FakeCore` for records, links and
the log; its runner tests use small temporary pytest projects.

| # | Task | M/S | Est. |
|---|---|---|---|
| V1 | `imports.py`: import edges and transitive closure over `source_dirs` (extracted) | M | 20 min |
| V2 | `markers.py`: `sr` marker collection (extracted) | M | 10 min |
| V3 | `testmap.py`: map from `verified_by`, markers, closure and naming; fingerprint cache; `test_map.txt` writer | M | 25 min |
| V4 | `select.py`: priority order, doc-only, infra globs, unknown-coverage sample, budget and deferral, derived `full_pending` | M | 30 min |
| V5 | `pytest_plugin.py`: per-phase outcomes, collection errors, exit status, JSON report to `PLUMB_REPORT` (extracted) | M | 15 min |
| V6 | `envid.py`: cheap `env_key`; content identity (extracted) cached under `env_key` | M | 20 min |
| V7 | `runner.py` and `evidence.py`: run selection, hard limit, inputs-changed discard, `test-run` entry, freshness and reuse index by offset | M | 30 min |
| V8 | `policy.py`: same-tree flaky rerun, regression rule (R3, spec F10) | M | 15 min |
| V9 | `__init__.py` `open_verify`; `cli.py`: `tests map|select|run`, aliases `map` and `verify`, `impact` | M | 20 min |
| V10 | `tests waive` (owner only, marker refusal, `waiver` event) | S | 10 min |

Tests (`tests/verify/`):

- `test_imports.py`: `test_import_edges_absolute_and_relative`, `test_transitive_closure`,
  `test_unresolvable_imports_ignored`
- `test_markers.py`: `test_collects_sr_markers_on_functions_and_classes`
- `test_testmap.py`: `test_map_from_verified_by_links`, `test_map_from_sr_markers`,
  `test_map_from_import_closure`, `test_map_from_naming`, `test_map_text_is_grepable`,
  `test_map_cache_reparses_only_changed_files`
- `test_select.py`: `test_doc_only_selects_nothing`,
  `test_priority_order_verified_by_literal_import_naming`,
  `test_infra_change_sets_full_pending_and_adds_nothing`,
  `test_unknown_coverage_samples_nearest_bounded`, `test_budget_defers_overflow`,
  `test_unknown_duration_counts_one_second`, `test_full_pending_cleared_by_full_run_evidence`,
  `test_selection_never_contains_whole_suite_marker`
- `test_plugin.py`: `test_plugin_reports_phases_and_exit_status`,
  `test_setup_failure_outranks_pass`, `test_collection_error_reported`
- `test_envid.py`: `test_env_key_changes_with_lock_and_python`,
  `test_identity_none_without_pyvenv`, `test_identity_cached_under_env_key`
- `test_runner.py`: `test_run_appends_test_run_entry_with_tree_and_env`,
  `test_run_never_passes_n_by_default`, `test_hard_limit_terminates_own_child`,
  `test_run_discarded_when_inputs_change`
- `test_evidence.py`: `test_fresh_pass_requires_matching_closure_test_and_env`,
  `test_reuse_miss_names_differing_part`, `test_unknown_identity_never_reused`,
  `test_index_rebuilt_from_log_after_cache_delete`
- `test_policy.py`: `test_flaky_rerun_same_tree_records_both_attempts`,
  `test_no_rerun_when_tree_changed`, `test_regression_requires_prior_pass_and_same_test_hash`,
  `test_new_red_test_is_not_regression`, `test_run_prints_regression_instruction`; stretch V10:
  `test_waiver_refused_under_marker`, `test_waiver_event_pinned_to_diff_digest`
- `test_cli_verify.py`: `test_tests_map_select_run_commands`, `test_aliases_map_and_verify`,
  `test_impact_lists_records_and_tests`

Runner tests start real pytest subprocesses; keep each temporary project to two or three tiny
tests so the lane suite stays under about 60 s.

## 7. Lane HOST

Goal: the Claude Code adapter: the four hooks, the status line, the skill, the slash command,
the CLAUDE.md block and the installer. Uses `FakeCore`, `FakeVerify`, `FakeBackend` and
`FakeCascade`; hook tests feed stdin JSON built by the `hook_input` fixture.

| # | Task | M/S | Est. |
|---|---|---|---|
| H1 | `hookio.py`: read stdin JSON, deadline, catch-all (exit 0, `check skipped` line, `errors.log`), output helpers (plain text, `systemMessage`, `decision: block`) | M | 15 min |
| H2 | `post_edit.py`: stdlib-only fast path appending to `touched.txt` | M | 10 min |
| H3 | `snapshot.py`: build `StatusSnapshot` from CoreAPI and VerifyAPI; write `status.json` | M | 15 min |
| H4 | `session_start.py`: brief (about 30 lines, cap 40) plus evidence lines; writes the snapshot | M | 15 min |
| H5 | `prompt.py`: prompt log, relevant records with examples and tests (20 lines), intent-change flag and compare line, awaiting-confirmation line, queued escalations | M | 30 min |
| H6 | `stop.py`: changed paths, records and links, selection and evidence, `stated.json`, one block per turn (tests, trigger 2, trigger 3), summary with capped `proposed` lines | M | 35 min |
| H7 | `statusline.py` | M | 10 min |
| H8 | `install.py`: settings merge (hooks, async post-edit, statusLine, env marker, deny rules), launcher selection, uninstall, status; skill, slash command, CLAUDE.md block, `commit-msg` hook; `cli.py` routes `hook`, `hooks`, `install`, `statusline` | M | 35 min |
| H9 | Escalation hint in the prompt hook (spec 6.2 step 5) | S | 10 min |

Tests (`tests/host/`):

- `test_hookio.py`: `test_internal_error_exits_zero_with_notice`,
  `test_deadline_skips_with_budget_notice`, `test_block_output_shape`
- `test_post_edit.py`: `test_appends_repo_relative_path`, `test_ignores_paths_outside_repo`,
  `test_fast_path_imports_no_yaml` (subprocess, checks `sys.modules`)
- `test_session_start.py`: `test_brief_about_30_lines_with_cap`,
  `test_brief_lists_awaiting_confirmation_and_drift`, `test_writes_status_snapshot`
- `test_prompt.py`: `test_logs_prompt_digest_and_text_to_session`,
  `test_injects_named_records_first`, `test_injects_examples_and_tests_within_20_lines`,
  `test_intent_change_flag_on_confirmed_record_with_change_words`,
  `test_no_flag_on_proposed_record`, `test_compare_line_when_confirmed_records_injected`,
  `test_awaiting_confirmation_lists_stated_set_with_digest`,
  `test_prints_queued_escalations`; stretch H9: `test_escalation_hint_on_many_features`
- `test_stop.py`: `test_blocks_once_when_covering_tests_not_fresh`,
  `test_no_block_when_stop_hook_active`, `test_summary_when_evidence_fresh`,
  `test_summary_caps_proposed_lines`, `test_regression_blocks_with_owner_instruction`,
  `test_matters_dec_asked_once_per_hash`, `test_new_red_test_never_asks`,
  `test_doc_only_turn_prints_at_most_one_line`, `test_writes_stated_set`,
  `test_no_change_turn_prints_nothing`, `test_verify_unavailable_degrades`
- `test_statusline.py`: `test_renders_line_from_snapshot`,
  `test_full_pending_shown_only_when_pending`, `test_missing_snapshot`
- `test_install.py`: `test_install_writes_hooks_statusline_env_and_deny_rules`,
  `test_install_preserves_foreign_settings_and_is_idempotent`,
  `test_uninstall_removes_only_plumb_entries`, `test_post_edit_registered_async`,
  `test_skill_about_20_lines_names_test_map_and_relay`, `test_slash_command_brief_why_impact`,
  `test_claude_md_block_idempotent`, `test_commit_msg_hook_written_and_foreign_hook_kept`,
  `test_launcher_selection`
- `test_latency.py`: `test_hooks_within_in_process_budget` (50 records, warm caches, fakes
  replaced by in-memory data; asserts each hook function under half its spec 10 budget, which
  leaves room for interpreter start)

## 8. Lane BRIDGE

Goal: the read-only importer, the judgment backends with the cascade interface, the JEV
adapter and fidelity packets. Extraction sources: spec 13 (`substrate/judgment/*`,
`register.py`). Fixtures: copies of `requirements/SR-077.md` (structured bindings,
acceptance), one SR with a `checksum:` field, `docs/features/FEAT-001.md`,
`bundles/FEAT-001.json` and `docs/nonconformances/NC-0002-*.md` from
`C:/coding/pi-agent-factory`, read once and saved under `tests/bridge/fixtures/pi_factory/`.

| # | Task | M/S | Est. |
|---|---|---|---|
| B1 | `judgment/model.py`, `tiers.py`: questions, answers, sealed records, fingerprint, `route` with version drift (extracted) | M | 20 min |
| B2 | `judgment/heuristic.py`, `get_backend` with `heuristic`, `disabled`, `fake` | M | 25 min |
| B3 | `judgment/cascade.py`: `LLMCascade` default `HostAgentCascade` (queues to `escalations.jsonl`), `get_cascade` | M | 10 min |
| B4 | `judgment/fidelity.py` and `cli.py`: `build_packet`, `plumb fidelity`, `plumb judge`, `plumb judgment status`, unjudged detection | M | 25 min |
| B5 | `importer/pi_factory.py`: SR, FEAT plus bundle, NC mapping, findings, dry run, `import` event; `importer/cli.py` | M | 40 min |
| B6 | `judgment/state.py`, `jev.py`: tracked-files state with secret exclusion and truncation (extracted); `urllib` client with the pinned wire shapes, timeouts, fallback with one notice | M | 35 min |
| B7 | Precision fixture for the intent-change heuristic (20 labelled prompts), result recorded in `docs/followups.md` | S | 15 min |

Tests (`tests/bridge/`):

- `test_tiers.py`: `test_route_thresholds`, `test_version_drift_suspends_accept`,
  `test_record_digest_detects_mutation`
- `test_heuristic.py`: `test_intent_change_flags_change_words_on_confirmed_match`,
  `test_no_flag_without_overlap`, `test_drift_triage_cosmetic_for_comment_only_change`,
  `test_drift_triage_material_for_logic_change`, `test_fidelity_is_unsure_escalate_llm`,
  `test_disabled_backend_is_unsure`; stretch B7: `test_intent_change_precision_fixture`
- `test_cascade.py`: `test_host_agent_cascade_queues_instruction`,
  `test_escalate_human_only_with_trigger`
- `test_fidelity.py`: `test_packet_contains_statement_examples_ends_evidence`,
  `test_packet_truncates_deterministically`, `test_judge_appends_event_with_hashes`,
  `test_unjudged_after_end_change`, `test_judgment_never_confirms_or_freshens`
- `test_import_sr.py`: `test_imports_sr_fields_and_ac_examples`,
  `test_structured_bindings_become_links_pinned_when_ends_exist`,
  `test_missing_ends_reported_as_findings`, `test_legacy_checksum_verified_and_reported`,
  `test_all_imported_records_are_proposed`
- `test_import_feat_nc.py`: `test_feature_membership_is_union_of_feat_and_bundle`,
  `test_membership_differences_reported`, `test_nc_read_leniently_keeps_corrected_by`,
  `test_id_collision_skipped_with_finding`
- `test_import_readonly.py`: `test_source_tree_unchanged_after_import`,
  `test_dry_run_writes_nothing`, `test_import_event_logged`
- `test_jev.py` (local stub `http.server` on 127.0.0.1, no network):
  `test_request_shape_matches_pinned_wire_format`, `test_parses_noul_choice_score_answers`,
  `test_timeout_falls_back_to_heuristic_with_one_notice`, `test_missing_key_uses_heuristic`,
  `test_key_never_read_from_repository`, `test_state_excludes_secret_paths_and_truncates`,
  `test_judgment_event_logged_with_fingerprint`
- `test_cli_bridge.py`: `test_import_cli_dry_run_report`, `test_fidelity_and_judge_cli`,
  `test_judgment_status_never_prints_key`

## 9. Phase 2: integration (coordinator)

1. Merge into `main` in this order, each with `git merge --no-ff sp1/<lane>`: CORE, VERIFY,
   BRIDGE, HOST. Only `docs/followups.md` may conflict (keep both sections). Run the whole
   suite after each merge.
2. The conformance suite in `tests/contracts/test_conformance.py` now also runs against
   `open_core`, `open_verify` and `get_backend`; fix any mismatch in the implementing lane's
   files.
3. Write `tests/integration/`:
   - `test_loop.py::test_loop_end_to_end`: temp repository with a small package and tests;
     `plumb init`, `new` INT and SR with an example, `link` derives_from and verified_by,
     `hooks install`; then `hook session-start`, `hook prompt` (names the SR), `hook
     post-edit` on a source file, `hook stop` (expects one block asking for `plumb tests run
     --changed`), `tests run --changed` (expects a `test-run` entry), `hook stop` with
     `stop_hook_active` (expects a summary, no block), `statusline`.
   - `test_loop.py::test_in_flow_confirmation`: stop writes the stated set, prompt "ok, go on"
     is logged, `relay` with that digest and quote confirms the SR; a neutral prompt confirms
     nothing.
   - `test_merge_boundary.py::test_merge_refused_then_allowed`: `validate --merge` exits 4,
     then 0 after `approve` run without the marker.
   - `test_regression.py::test_regression_detected_and_reported`: a passing test breaks after a
     source edit; `tests run` prints the regression instruction; the next stop summary shows
     `questions: regression`.
   - `test_dispatch.py::test_every_command_routes_and_helps`: `plumb <cmd> --help` exits 0 for
     every command of spec 9.
   - `test_latency_subprocess.py::test_hooks_end_to_end_under_two_seconds` (real subprocesses
     on the temp repository; asserts each hook under 2 s, records timings).
4. `scripts/bench_hooks.py`: runs each hook 20 times as subprocesses against a repository
   (default: the current one), prints p50 and p95 per hook and the prompt + stop sum. Run it
   on the temp repository now and on plumb's own repository in phase 4.
5. Gate: `uv run pytest -q` and `uv run ruff check src tests` green on `main`.

## 10. Phase 3: review

- Four review agents, one per lane diff (`git diff <phase-0 commit>..sp1/<lane>`), each
  checking the diff against the spec sections its lane implements, the brief and rulings R1
  to R7, and spec 10 latency rules. Severity follows R7: HIGH only for a contradiction or
  omission of the owner's words, decisions or rulings, or a defect that breaks a spec
  guarantee (for example a path that confirms a record without the owner's words, or a hook
  that can block or exceed 2 s).
- One intent verifier reads the merged result against the brief.
- The coordinator fixes HIGH findings test first, re-runs the whole suite, and appends medium
  and low findings to `docs/followups.md` under `## SP1 review (2026-10-06)`.

## 11. Phase 4: dogfood (coordinator, on `main`)

### 11.1 Steps

1. `uv run plumb init`; set `verify.infra_globs` to add `src/plumb/verify/pytest_plugin.py`.
2. Create the records below with `uv run plumb new ...` and link them with `uv run plumb link
   ...`. Quotes are copied verbatim from the brief; read-backs are in the owner's terms.
3. Add `@pytest.mark.sr("SR-0xx")` markers to the tests that verify each example, or
   `verified_by` links naming them; `uv run plumb tests map`.
4. `uv run plumb tests run --full` once, so `full verification pending` starts satisfied
   (this is the owner's merge boundary for sub-project 1, not a per-turn run).
5. `uv run plumb hooks install --launcher venv`; set `require_trailer: true` in
   `.plumb/claims.yaml`.
6. `uv run plumb validate` (no errors; proposed-record warnings expected),
   `uv run plumb validate --merge <phase-0 commit>` (exits 4 and lists every record awaiting
   the owner's confirmation, which is the expected morning question),
   `uv run python scripts/bench_hooks.py` (record the numbers in `docs/followups.md` if a
   budget is missed).
7. Commit `dogfood: plumb records its own intent and installs its hooks` with the trailer
   `SR: SR-001, SR-002, ...` (every requirement the commit serves), then
   `uv run plumb claims check --range <phase-0 commit>..HEAD`.
8. No approval is written by any agent. The handoff note tells the owner the one line that
   confirms everything they agree with: `plumb approve --proposed` in their own terminal, or
   "ok" in a session (relayed with the quote check).

### 11.2 Records to create

Intents (`INT`, `quote` verbatim from the brief, `source: owner intent brief 2026-10-05`):

| ID | Owner words (abridged here; full quote in the record) |
|---|---|
| INT-001 | "the goal of coherence tooling is to ensure the alignment between user's intent ... and the current state of the system being built." |
| INT-002 | "make vibe coding grounded on the projects artifacts in an efficient, reliable and trustable manner." |
| INT-003 | "a lighter, more elegant and interactive way to leverage coherence." |
| INT-004 | "how do you ensure that people defining their system will have their intent succesfully translated?" with decision 2 "C" |
| INT-005 | Decision 1 "A / B" (standalone; pi-agent-factory can migrate) |
| INT-006 | Decision 4 "be careful about loosing some important features, for example the hash is important for staleness detection." and "Keep list looks fine" |
| INT-007 | Decision 3 "I guess the CLI / lib can be re-used from pi-agent-factory?" |
| INT-008 | Decision 5 "A" (background; three triggers) |
| INT-009 | Decision 6 "dogfood the version to itself as soon as possible and build with it." |
| INT-010 | Decision 7 "think of re-using the existing artifacts no? SRs FEATs..?" |
| INT-011 | Decision 8 "I think it might be usefull to integrate it in this new version too?" |
| INT-012 | Decision 11 "I wont review the concept spec or any plan ... I want to have the implementation available by tomorrow morning (in 9 hours)." |

Features: FEAT-001 records and integrity, FEAT-002 grounding loop, FEAT-003 covering-test
verification, FEAT-004 judgment and import bridge.

Requirements (each with given/when/then examples drawn from the named tests, a
`derives_from` link, `implemented_by` links and `verified_by` links or markers):

| ID | Feature | Statement (short) | Derives from | Verified by (lane tests) |
|---|---|---|---|---|
| SR-001 | FEAT-001 | Records are Markdown with frontmatter under `.plumb/`, identified by frontmatter ID | INT-006, INT-010 | `tests/core/test_model.py`, `test_store.py` |
| SR-002 | FEAT-001 | Record hashes ignore formatting and change with meaning | INT-006 | `tests/core/test_hashing.py` |
| SR-003 | FEAT-001 | Links pin both ends; either end moving makes the link stale; dangling links are errors | INT-006 | `tests/core/test_links.py` |
| SR-004 | FEAT-001 | Approvals pin exact content; an edit leaves the record unconfirmed | INT-006 | `tests/core/test_approvals.py` |
| SR-005 | FEAT-001 | Only the owner's explicit words confirm: owner command or quote-checked relay; the marker refuses self-approval | INT-004, INT-006 | `tests/core/test_approvals.py`, `tests/host/test_install.py` |
| SR-006 | FEAT-001 | Logs are append-only and hash-chained; tampering is reported | INT-006 | `tests/core/test_log.py` |
| SR-007 | FEAT-001 | `SR:` trailers are checked at commit and claims compare claimed with declared paths | INT-006, INT-010 | `tests/core/test_claims.py` |
| SR-008 | FEAT-001 | The merge boundary refuses unconfirmed touched requirements and lists approvals in the range | INT-004 | `tests/core/test_merge.py` |
| SR-009 | FEAT-002 | The session brief is about 30 lines of context, not procedure | INT-002, INT-008 | `tests/host/test_session_start.py` |
| SR-010 | FEAT-002 | Each prompt receives the relevant records, their tests and an intent-change flag | INT-002, INT-004 | `tests/host/test_prompt.py` |
| SR-011 | FEAT-002 | Edits are tracked without blocking | INT-003 | `tests/host/test_post_edit.py` |
| SR-012 | FEAT-002 | The end-of-turn summary is short, shows proposed records, and asks only on the three triggers | INT-008 | `tests/host/test_stop.py` |
| SR-013 | FEAT-002 | The status line reads state and recomputes nothing | INT-008 | `tests/host/test_statusline.py` |
| SR-014 | FEAT-002 | Hooks stay within their budgets and never block work on plumb's own failure | INT-002, INT-003 | `tests/host/test_hookio.py`, `test_latency.py`, `tests/integration/test_latency_subprocess.py` |
| SR-015 | FEAT-002 | The installer writes hooks, status line, marker, deny rules, skill, slash command and commit hook, idempotently | INT-007, INT-009 | `tests/host/test_install.py` |
| SR-016 | FEAT-003 | The test map is grep-able text built from links, markers, imports and naming | INT-002 | `tests/verify/test_testmap.py` |
| SR-017 | FEAT-003 | Covering-test selection: docs select nothing, infrastructure sets full pending, unknown coverage samples, a budget caps the turn | INT-002, INT-003 | `tests/verify/test_select.py` |
| SR-018 | FEAT-003 | Evidence is pinned to tree, closure, test source and environment identity, and reused only on an exact match | INT-006 | `tests/verify/test_evidence.py`, `test_envid.py`, `test_runner.py` |
| SR-019 | FEAT-003 | A failure that passes on a same-tree rerun is recorded as flaky with both attempts | INT-006 | `tests/verify/test_policy.py` |
| SR-020 | FEAT-003 | A regression is a previously passing test with unchanged source that now fails; a new red test never interrupts | INT-008 | `tests/verify/test_policy.py`, `tests/host/test_stop.py` |
| SR-021 | FEAT-004 | Judgment is optional: heuristic by default, JEV when a key exists, fallback on failure, advisory only | INT-011 | `tests/bridge/test_heuristic.py`, `test_jev.py`, `test_tiers.py` |
| SR-022 | FEAT-004 | Fidelity packets let the host agent judge a requirement without JEV | INT-011, INT-004 | `tests/bridge/test_fidelity.py` |
| SR-023 | FEAT-004 | The importer reads pi-agent-factory records read-only and never manufactures a confirmation | INT-005, INT-010 | `tests/bridge/test_import_*.py` |
| SR-024 | FEAT-004 | The cascade hands low-confidence judgments to the host agent through an interface | INT-011 | `tests/bridge/test_cascade.py` |

Decisions: `DEC-001` to `DEC-012` for spec refinements F1 to F12, each with `question`,
`chosen`, `alternatives` (the concept's mechanism), `rationale`, a `decides` link to the SR it
shapes, and `matters: true` for F2 (guard by deny rules), F4 (prompt digests committed when
cited) and F6 (tests run in the agent's turn), `matters: false` for the others.

### 11.3 Dogfood checks (gate)

- `plumb validate`: no errors.
- `plumb tests map` lists every `SR-0xx` with at least one test.
- `.claude/settings.json` holds the four hooks, the status line, the marker and the deny rules;
  `.claude/skills/plumb/SKILL.md` and `.claude/commands/plumb.md` exist; the `commit-msg`
  hook rejects a message with an unknown SR ID (try it with `plumb trailers check-msg`).
- The dogfood commit carries an `SR:` trailer and `plumb claims check` reports no undeclared
  path (or records each one in `docs/followups.md`).
- `scripts/bench_hooks.py` on plumb's own repository: prompt + stop p95 under 1.5 s.

## 12. Drop order and the morning minimum

If a lane reaches its 3-hour mark, it stops, records each unfinished item in
`docs/followups.md` with its state, and hands back what passes its gate. Items are dropped from
the end of each lane's table first (stretch items, then the last must items).

The morning minimum, which phase 2 must not ship without, is: CORE C1 to C10, VERIFY V1 to
V9, HOST H1 to H8, BRIDGE B1 to B5. That is records, hashes, links, logs, approvals with the
guard, validation with the merge boundary, trailers, the four hooks, the status line, the
installer, the map, selection and runs with evidence, the failure policy, the judgment
interface with its heuristic default and fidelity packets, and the importer. If the JEV
adapter (B6) is unfinished, `judgment.backend: jev` falls back to the heuristic with a notice,
which the spec already requires.

## 13. Definition of done

Spec section 14.2, checked by the coordinator after phase 4 and reported in the handoff:

- [ ] whole suite and ruff green on `main`;
- [ ] every command of spec 9 exists, has a test, and appears in `plumb --help`;
- [ ] the end-to-end loop, in-flow confirmation, merge-boundary and regression integration
      tests pass;
- [ ] guard tests pass and the installer writes the deny rules and marker;
- [ ] `validate --merge` exits 4 then 0;
- [ ] hook benchmark within budget on plumb's own repository (or each miss recorded);
- [ ] read-only dry-run import of `C:/coding/pi-agent-factory` reports findings and changes
      nothing there;
- [ ] `plumb judgment status` reports `heuristic`; JEV tests pass on the local stub;
- [ ] dogfood checks of 11.3 pass; later commits carry `SR:` trailers;
- [ ] unfinished items, medium and low findings in `docs/followups.md`; no HIGH finding open.

## 14. Risks

| Risk | Mitigation |
|---|---|
| CORE is the largest lane | Phase 0 takes the shared primitives off it; symbol hashing and claims are its stretch items; other lanes do not wait on it (fakes) |
| Contract gaps found mid-lane | One coordinator owns contract changes; lanes move to their next item meanwhile |
| Interpreter start (about 225 ms here) eats the hook budget | Async post-edit hook, deny rules instead of a per-call guard hook, JSON caches, lazy imports, benchmark in phases 2 and 4 |
| Runner tests are slow on 2 cores | Tiny temporary projects; no xdist; lane suites run one at a time per lane |
| Host feature uncertainty (`async` hooks, wildcard deny rules) | Fallbacks stated in spec 6.3 and 5.6; the guard's primary layer is the CLI marker check |
| Union merges of JSONL logs | Chain forks accepted by design (spec 5.7); validated by `test_union_merged_fork_accepted` |
