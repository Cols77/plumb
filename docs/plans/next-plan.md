# Next plan: sub-projects 2 to 5 and the importer completion, in five lanes

Implements `docs/specs/sp2-intent-capture.md` (lane CAPTURE), `docs/specs/sp3-merge-boundary.md`
(lane MERGE), `docs/specs/sp4-hosts-mcp.md` (lane HOSTS), `docs/specs/sp5-presentation.md`
(lane PRESENT) and the pi-agent-factory importer completion specified in section 9 of this
plan (lane IMPORT). The owner does not review this plan (D11); verifier agents check it
against the owner intent brief, rulings R1 to R12, `docs/concept.md` and the four specs.
"sp2 8.1" means section 8.1 of the sp2 spec.

Binding owner rules for every phase (from the work order and the brief):

1. **HIGH findings only, whole class.** Fix only HIGH findings, and fix the whole class:
   name the guarantee, enumerate every entry point, fix at one choke point, add one test per
   entry point. Medium and low findings go to `docs/followups.md`.
2. **Test economy.** No full suite except the single run in the Integrate phase. Iterate on
   the touched tests only. Before each commit, run the lane's focused set (section 3.4) once,
   in the foreground (timeout up to 600000 ms).
3. **Latency.** Per-turn hook latency stays in seconds, with fewer, meaningful
   interruptions. Every hook keeps the sp1 budgets (sp1 10).
4. **Process safety.** Never kill a process you did not start. The machine has 2 cores; at
   most `pytest -n 2`, and lanes run without `-n`.
5. **Dogfooding.** Every commit carries `SR: SR-###` trailers that claim its paths (the
   `commit-msg` hook enforces it). New requirements are plumb records, `proposed`, with
   examples and links, written with plumb's own commands. Run `plumb validate` and
   `plumb drift` before committing. **Agents never approve records**: no agent runs
   `plumb approve`, `plumb revoke`, `plumb triage --approve`, `plumb spec approve` or
   `plumb config auto-approve`, and no agent relays an approval without the owner's own
   affirming words (R2). Only the owner confirms. Every owner-only command writes through
   the one choke point `approvals.require_owner` (concept 4.6 check 4: refused under the
   marker and, on every host, outside an interactive terminal); no lane adds an owner-only
   write that bypasses it, and each new owner-only command gets a test that runs it with no
   marker and stdin a pipe holding "y" and asserts exit 3 with nothing written.
6. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## 1. Shape of the work

| Phase | What | Who | Agent time | Gate before the next phase | Drop rule |
|---|---|---|---|---|---|
| 0. Contracts | Every cross-lane signature, data class, route, config key and stub (3.2), so the five lanes start against real interfaces | coordinator, alone, on `main` | about 60 min | 3.3 | Never cut. If it overruns, the lanes start later; no lane starts on unfrozen contracts |
| 1. Lanes | CAPTURE, MERGE, HOSTS, PRESENT, IMPORT in parallel, each in its own worktree (sections 4 to 8 and 9) | five lane agents | MUST items about 120 min per lane; SHOULD items until the lane stop | lane gate (3.4) at each merge point | MUST items merge-ready by lane start + 2 h 30. SHOULD items dropped from the start of each lane's drop order. Lane stop at lane start + 3 h 15: the lane hands back what passes its gate and records every unfinished item in `docs/followups.md` |
| 2. Integrate | Merge the lanes, reinstall hooks, the ONE full-suite run (as `plumb merge-check`), dogfood checks (10) | coordinator, on `main` | about 45 min | 10.4 | Never cut: the merges that pass their gate, the single full run, the dogfood checks. Cut first: the hook benchmark repeat, then the conformance test extension |
| 3. Review | Intent verifiers on the merged result; HIGH fixes only, whole class (11) | review agents; coordinator fixes | about 45 min | no HIGH finding open | Shrinks to one intent verifier |

Orchestration uses the host's native mechanism: in Claude Code, the `Workflow` tool (phase 0
as one agent step with its gate; phase 1 as a `parallel()` of five lane pipelines, each a
sequence of segment agents with a merge-ready report per merge point; phases 2 and 3 as
gated steps). Starting it needs the owner's opt-in where Claude Code asks for it; this plan
does not grant it.

## 2. Conventions for every agent

- Repository `C:/coding/plumb`. Phase 0 runs on `main` after merging the branch that holds
  this plan (`work`) into it with `git merge --no-ff`. Lanes work in worktrees
  `C:/coding/plumb-wt/next-<lane>` on branches `next/<lane>`, created from `main` after the
  phase-0 gate (`git -C C:/coding/plumb worktree add C:/coding/plumb-wt/next-capture -b
  next/capture main`), then `uv sync` inside the worktree.
- `C:/coding/pi-agent-factory` is read-only reference material: never write there, never
  create worktrees of it, never run its `coherence` or `factory` commands. Reading files and
  read-only git commands (`git show`, `git archive`) are allowed. Its filesystem is slow on
  this machine: read single files, never grep it recursively.
- Each lane starts with `uv run plumb brief`, `uv run plumb status` and
  `uv run plumb show <its SRs>` and keeps the output as context.
- Test first: write the failing test, see it red, implement, see it green. Mark every new test
  `@pytest.mark.sr("SR-0xx")` with the SR it verifies, so plumb's test map covers it.
- Iterate with the touched test file only (`uv run pytest tests/capture/test_triage.py -q`).
  Before each commit: the lane's focused set once, in the foreground (3.4). No whole suite.
- `SR:` trailers: each commit names the SRs of the task table rows it implements, and claims
  only paths those SRs declare or will declare. Before committing a new module, link it:
  `uv run plumb link SR-0xx implemented_by <path>` and `verified_by <test file> --example
  EX-n` (lanes may run `plumb link` and `plumb repin` on their own SRs; those never confirm
  anything). Then `uv run plumb validate`, `uv run plumb drift` and
  `uv run plumb claims check --range main..HEAD`.
- Lanes never edit another lane's files (3.1). A needed contract change stops that item; the
  lane asks the coordinator and moves to its next item.
- Medium and low findings, and unfinished items with their state, go under the lane's own
  heading at the end of `docs/followups.md` (`## Next lane CAPTURE (2026-10-..)`).

## 3. Files, contracts and gates

### 3.1 Ownership (disjoint)

| Owner | Paths |
|---|---|
| Coordinator (phases 0, 2, 3) | `src/plumb/contracts.py`, `config.py`, `cli.py`, `cliutil.py`, `api.py`, `paths.py`, `log.py`, `store.py`, `model.py`, `normalize.py`, `text.py`, `trailers.py`, `__init__.py`, `__main__.py`; `pyproject.toml`, `uv.lock`; `tests/conftest.py`, `tests/test_smoke.py`, `tests/integration/**`, `tests/core/test_cli_core.py`, `tests/core/test_conformance_core.py`, `tests/core/test_model.py`, `tests/core/test_store.py`, `tests/core/test_log.py`, `tests/core/test_primitives.py`; `.plumb/**`, `.claude/**`, `CLAUDE.md`, `README.md`, `scripts/**`, `docs/**` (lanes only append to `docs/followups.md`; HOSTS writes `docs/hosts.md`; IMPORT writes `docs/import-rehearsal.md`) |
| CAPTURE | `src/plumb/capture/**` (new), `src/plumb/commands.py` (after phase 0: `init`, `link`, `repin`, `approve`, `relay`, `revoke`, `validate`), `src/plumb/approvals.py`, `src/plumb/confirm.py`, `src/plumb/validate.py`, `src/plumb/judgment/**`, `src/plumb/hosts/claude_code/templates/skills/**`; `tests/capture/**` (new), `tests/core/test_approvals.py`, `tests/core/test_confirm.py`, `tests/core/test_validate.py`, `tests/bridge/test_heuristic.py`, `test_jev.py`, `test_tiers.py`, `test_cascade.py`, `test_precision.py`, `test_fidelity.py` |
| MERGE | `src/plumb/merge.py`, `src/plumb/boundary/**` (new), `src/plumb/claims.py`, `src/plumb/trace.py`, `src/plumb/verify/**`; `tests/merge/**` (new), `tests/verify/**`, `tests/core/test_merge.py`, `tests/core/test_trace.py`, `tests/bridge/test_claims.py`, `tests/bridge/test_trailers.py` |
| HOSTS | `src/plumb/hosts/cli.py` (new), `src/plumb/hosts/codex/**`, `src/plumb/hosts/pi/**`, `src/plumb/hosts/hermes/**`, `src/plumb/mcp/**` (all new); `tests/hosts/**`, `tests/mcp/**` (new); `docs/hosts.md` |
| PRESENT | `src/plumb/present/**` (new after phase 0), `src/plumb/view/**` (new), `src/plumb/align.py` (new), `src/plumb/explain.py`, `src/plumb/query.py`, `src/plumb/readback.py`, `src/plumb/hosts/neutral.py` (after phase 0), `src/plumb/hosts/claude_code/**` except `templates/skills/**`; `tests/present/**` (new), `tests/host/**`, `tests/core/test_explain.py`, `test_query.py`, `test_readback.py`, `test_drift.py` |
| IMPORT | `src/plumb/importer/**`, `src/plumb/hashing.py`, `src/plumb/links.py`; `tests/importer/**` (new), `tests/bridge/test_import_*.py`, `tests/bridge/fixtures/**`, `tests/bridge/pi_source_fixture.py`, `tests/core/test_hashing.py`, `tests/core/test_links.py`; `docs/import-rehearsal.md` |
| Any lane, append only | `docs/followups.md` (own heading) |

Data and session files have one writer each: `capture` writes the new event kinds of sp2 4
through `CoreAPI.log_append`; `boundary` writes `merge-evidence`; `present.delta` writes
`.plumb/session/<sid>/seen.json`; the stop hook (PRESENT) writes `stated.json`, now able to
hold a triage group (sp2 8.1).

### 3.2 Phase 0: what the coordinator writes before any lane starts

1. **`contracts.py`.** `ApprovalBy` adds `"auto-jev"`. `Judgment` adds
   `probability: float | None = None` and `confidence_label: Literal["low", "medium",
   "high"] | None = None`. `JudgmentAction` adds `"faithfulness"`, `"contradiction"`,
   `"ownership"`, `"alignment"`, `"dependency"`, `"ambiguity"`. `JudgmentBackend` adds
   `version`, `entailment`, `contradiction`, `choose`, `ask` (sp2 11.2). New frozen data
   classes with defaults for every field: `CaptureResult`, `IntentFlag`,
   `EscalationSuggestion`, `DiffStats`, `TriageItem`, `TriageView`, `IntentCardData`,
   `AutoApproveState`, `Proposal`, `ClarifyView` (sp2 11.1); `TurnEvent`, `TurnOutput`
   (sp4 3.1); `MergeReport` (sp3 9); `Resolution`, `CardMode` (sp5 9). `StatusSnapshot` adds
   `state`, `intent_summary`, `confirmed_by`, `auto_approve` with defaults.
2. **`config.py`.** New sections with the defaults of the specs: `capture`, `triage`
   (`low_risk_min: 0.8`), `auto_approve` (mirror, `enabled: false`), `calibration`
   (`min_items: 20`, `min_negatives: 5`, `max_false_accept: 0.0`), `clarify`
   (`answered_min`), `hints` (`hidden_deps_max: 5`, `authoritative_docs`), `present`
   (`card: compact`, `ascii: false`), `resolve` (`min_score`, `margin`), `merge`
   (`default_base: main`, `prepush_run_full: true`), `hooks.stop_tokens: 150`,
   `judgment.jev.credential_env: TYPESAFE_API_KEY`, `escalation.shared_globs`,
   `escalation.irreversible`. `plumb init`'s commented `config.yaml` lists them.
3. **Stubs with the final signatures.** `plumb/capture/__init__.py`, `capture/api.py` (every
   function of sp2 11.1 returning its empty value); `plumb/boundary/__init__.py`
   (`merge_report` wrapping today's `merge.merge_check` data, `render`, `exit_code`,
   `install_pre_push_hook` raising `NotImplementedError`); `plumb/present/__init__.py`,
   `present/api.py` (delegating to today's `query`, `explain`, `readback`, `verify impact`,
   `drift_data`), `present/render.py` (`status_card` from today's `statusline.render`,
   `intent_card` from `readback.record_lines`), `present/delta.py` (`emit` passing lines
   through); `plumb/hosts/neutral.py` (`handle_event` calling today's Claude Code
   `handle` functions with a `HookContext` built from the `TurnEvent`, and mapping their
   `HookOutput` to `TurnOutput`). Heuristic and disabled backends get `version`,
   `entailment`, `contradiction`, `choose`, `ask` returning `unsure` with confidence 0.
   `plumb/importer/recheck.py` (`recheck_import_approvals(core) -> list[str]`, returning
   `[]`), which `validate.py` calls lazily, so IMPORT adds its `by: import` re-check
   (9.3) without touching CAPTURE's `validate.py`.
4. **Command routing.** The handlers `status`, `brief`, `drift`, `show`, `explain` (`why`)
   move unchanged from `commands.py` to `present/report.py`. `cli.ROUTES` adds
   `capture`, `new`, `intent`, `example`, `decide`, `escalate`, `spec`, `triage`, `config`,
   `jev`, `clarify` -> `plumb.capture.cli`; `merge-check` -> `plumb.boundary.cli`; `hosts`,
   `turn` -> `plumb.hosts.cli`; `mcp` -> `plumb.mcp.cli`; `resolve`, `review`, `confirm`,
   `align`, `view` and the moved verbs -> `plumb.present.cli`. `plumb --help` is generated
   from `ROUTES`, listing a verb only when its module is importable (SR-068).
   `plumb validate --merge BASE` calls `plumb.boundary.merge_report(run_full=False)`,
   `render` and `exit_code`, so MERGE changes the boundary without touching `commands.py`.
   `.plumb/session/stated.json` gains `groups: [{group, records: [{id, hash}]}]` (written by
   the stop hook, read by `plumb relay --group`).
5. **Installer.** `install.py` installs every `templates/skills/<name>/SKILL.md` it finds
   (the existing skill moves to `templates/skills/plumb/SKILL.md`, since DEC-036
   `templates/skills/plumb-records/`), and adds deny rules for
   `plumb triage --approve`, `plumb spec approve` and `plumb config auto-approve`, in the
   three launcher forms. `plumb hook <event>` accepts `--host` and `--format` and routes
   through `hosts.neutral`. `.plumb/.gitignore` adds `view/`.
6. **Tests and markers.** New test directories with `__init__`-free layout like the others;
   the `jev_live` marker registered in `pyproject.toml`; `tests/integration/test_contracts.py`
   checks that every stub matches its protocol or signature.
7. **Records.** FEAT-002 to FEAT-005, SR-034 to SR-068, INT-017 to INT-020 and DEC-014 to
   DEC-019 already exist (written with this plan). Phase 0 links nothing new.

### 3.3 Phase-0 gate

```
uv run pytest tests/core tests/host tests/integration/test_contracts.py tests/test_smoke.py -q
uv run ruff check src tests
uv run plumb validate && uv run plumb drift
uv run plumb --help        # lists only importable verbs
```

Then the five worktrees are created from that `main`.

### 3.4 Lane gate (each merge point and before handing back)

```
uv run pytest <the lane's focused set> -q      # foreground, once, timeout 600000 ms
uv run ruff check src tests
uv run plumb validate && uv run plumb drift     # no errors
uv run plumb claims check --range main..HEAD    # no undeclared path
git diff --name-only main...HEAD               # every path in the lane's row of 3.1
```

Focused sets: CAPTURE `tests/capture tests/core/test_approvals.py tests/core/test_confirm.py
tests/core/test_validate.py tests/bridge/test_heuristic.py tests/bridge/test_jev.py
tests/bridge/test_tiers.py tests/bridge/test_precision.py`; MERGE `tests/merge
tests/core/test_merge.py tests/core/test_trace.py tests/bridge/test_claims.py
tests/bridge/test_trailers.py` plus the `tests/verify` files it touched; HOSTS `tests/hosts
tests/mcp`; PRESENT `tests/present tests/host tests/core/test_explain.py
tests/core/test_query.py tests/core/test_readback.py tests/core/test_drift.py`; IMPORT
`tests/importer tests/bridge/test_import_*.py tests/core/test_hashing.py
tests/core/test_links.py`.

The lane reports `merge-ready <lane> <merge point> <sha>`. The coordinator merges with
`git merge --no-ff` (message with the merged rows' `SR:` trailers) and runs the merged
lane's focused set once on `main`; it does not run the whole suite until phase 2.

### 3.5 Interface contracts between lanes

| Provider | Interface | Consumers | Degraded form when missing |
|---|---|---|---|
| CAPTURE | `plumb.capture.api` (sp2 11.1) | PRESENT (hooks, cards, review, drift), MERGE (`diff_serves` in `trailers check-msg`), HOSTS (through PRESENT only) | empty result; PRESENT prints `plumb: <part> unavailable` once per session |
| CAPTURE | `JudgmentBackend` additions (sp2 11.2) | PRESENT (`align`), MERGE (fidelity scoring) | `unsure`, confidence 0, "no judgments available" |
| MERGE | `plumb.boundary` (sp3 9) | PRESENT (`/plumb review`) | `merge state: unavailable` |
| PRESENT | `plumb.present.api`, `plumb.present.render` (sp5 9) | HOSTS (MCP tools, adapters), CAPTURE (`plumb capture` prints the intent card) | phase-0 delegations stay valid |
| PRESENT | `plumb.hosts.neutral.handle_event` (sp4 3.1) | HOSTS (every adapter, `plumb turn`) | phase-0 delegation |
| IMPORT | `import_pi_factory(core, source, *, dry_run, only, diff)`, `plan_import(...)` (9.4) | none at run time (CLI only) | n/a |
| IMPORT | symbol and test-node link ends in `hashing.py` and `links.py` (9.2) | every lane through `CoreAPI` (link states, hashes) | whole-file hashing, as today |
| Coordinator | the data classes, routes and config keys of 3.2 | all | frozen; changes only through the coordinator |

Unit tests never import another lane's new modules; they use the phase-0 stubs or local
fakes. Run-time calls between lanes go through the interfaces above, imported inside the
function that needs them.

## 4. Lane CAPTURE (sp2)

Goal: the agent records the owner's intent in one call; escalation and set approval;
contradiction-aware intent flags; triage; the skills. Then the R8 B, R11 and R12 extras.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| C1 | `capture/records.py` and `capture/cli.py`: `plumb new`, `intent`, `example`, `decide` (incl. `--supersede`, `--recommend`, `--matters`), IDs only through `Store.next_id`, links through `add_link` | MUST | SR-035 | 15 min |
| C2 | `capture/capture.py`: `plumb capture` (sp2 5.1): quote check against the logged prompt, records and links, `updates`, intent card via `present.render.intent_card`, `CaptureResult` | MUST | SR-034 | 20 min |
| C3 | `judgment/heuristic.py` `contradiction` and `capture.api.intent_flags`: contradicts, extends, benign against confirmed examples; fixture of at least 30 labelled prompts | MUST | SR-038 | 20 min |
| C4 | `capture/escalation.py`: the six triggers, `escalate decline` (the owner's form through `approvals.require_owner`), `escalation-declined` event, no repeat per intent | MUST | SR-036 | 15 min |
| C5 | Set approval: `INT` `members`, `spec show`, `spec approve` (owner; through `approvals.require_owner`), `relay --set` in `commands.py`/`approvals.py`, member state in `confirm.py` | MUST | SR-037 | 20 min |
| C6 | `capture/triage.py`: heuristic `entailment`, groups and exclusions, `plumb triage`, `--approve low-risk` (owner; through `approvals.require_owner`), `relay --group`, `triage` event; `capture.api.triage`, `card_data`, `confirmation_counts`, `next_question` | MUST | SR-040 | 20 min |
| C7 | Skills: `templates/skills/plumb/SKILL.md` names `capture`, `decide`, `clarify`, `triage` and the relay forms (about 25 lines); `templates/skills/plumb-clarify/SKILL.md` (sp2 9.1) | MUST | SR-046, SR-043 | 10 min |
| CS1 | `plumb clarify` and `capture.api.clarify`; `tests/capture/test_clarify_e2e.py` (sp2 9.3) | SHOULD | SR-043 | 25 min |
| CS2 | JEV protocol methods in `jev.py`; `plumb jev status`, `plumb jev setup` (name only), `jev_live` tests skipped without the credential | SHOULD | SR-039 | 20 min |
| CS3 | `plumb jev calibrate` (sp2 8.3), `calibration` event | SHOULD | SR-042 | 25 min |
| CS4 | `plumb config auto-approve on\|off` (through `approvals.require_owner`), `config show`, `config card`; the gate in `capture`; `by: auto-jev` approvals; `validate` re-check | SHOULD | SR-041 | 30 min |
| CS5 | `ownership_proposals`, test-node proposals, `diff_serves` (sp2 10.1) | SHOULD | SR-044 | 25 min |
| CS6 | `drift_hints`: hidden-dependency scan (sp2 10.2) | SHOULD | SR-045 | 15 min |

MUST total: 120 min. Merge points: after C2, after C7 (MUST), at the end. **Drop order**
(first dropped to last): CS6, CS5, CS4, CS3, CS2, CS1. CS4 needs CS3: when CS3 is dropped,
CS4 is dropped too, and auto-approval stays unavailable (it is off by default anyway).

Tests (`tests/capture/` unless named), each marked with its SR:

- C1 `test_records.py`: `test_new_uses_next_id_and_is_proposed`, `test_example_appends_ex_n`,
  `test_decide_writes_alternatives_and_matters`, `test_supersede_never_edits_confirmed_dec`
- C2 `test_capture.py`: `test_capture_writes_int_sr_dec_linked_and_proposed`,
  `test_quote_must_be_verbatim_in_prompt`, `test_update_of_confirmed_record_says_unconfirmed`,
  `test_dry_run_writes_nothing`, `test_prints_intent_card`
- C3 `test_intent_flags.py`: `test_contradiction_flagged`, `test_extension_flagged`,
  `test_benign_mention_not_flagged`, `test_proposed_record_never_flagged`,
  `test_precision_fixture_all_contradictions_no_benign`
- C4 `test_escalation.py`: one test per trigger (six), `test_declined_not_repeated`,
  `test_owner_decline_refused_without_terminal`
- C5 `test_set_approval.py`: `test_set_hash_over_sorted_members`,
  `test_spec_approve_refused_under_marker`, `test_spec_approve_refused_without_terminal`,
  `test_relay_set_checks_r2`,
  `test_member_edit_unconfirms_member_and_set`
- C6 `test_triage.py`: `test_groups_low_risk_first`, `test_exclusions_shown_individually`,
  `test_approve_low_risk_exact_hashes_owner_only`,
  `test_approve_low_risk_refused_without_terminal`, `test_relay_group_needs_group_in_stated_set`,
  `test_no_backend_reports_no_judgments`
- C7 `test_skills.py`: `test_plumb_skill_names_capture_helpers`,
  `test_clarify_skill_states_depths_and_discipline`
- CS1 `test_clarify.py`, `test_clarify_e2e.py`; CS2 `tests/bridge/test_jev.py` additions,
  `test_jev_cli.py`; CS3 `test_calibrate.py`; CS4 `test_auto_approve.py` (one test per
  "never" case of sp2 8.2, plus `test_config_on_refused_without_calibration`,
  `test_config_on_off_refused_without_terminal`,
  `test_yaml_without_owner_event_is_off`, `test_validate_rechecks_auto_jev`); CS5
  `test_ownership.py`; CS6 `test_hints.py`

Definition of done: sp2 13 for the items built; every unbuilt SHOULD item in
`docs/followups.md`.

## 5. Lane MERGE (sp3)

Goal: `plumb merge-check`, with exactly one full run, the claims and link gates, the glance,
and the pre-push hook. Lightweight.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| M1 | `boundary/report.py`: `merge_report` (data) from today's `merge_check`, `render`, `exit_code`, replacing the phase-0 stub that `validate --merge` already calls | MUST | SR-047 | 25 min |
| M2 | Glance groups (agent-relayed, auto-jev, owner, import, with revoke forms); `repinned without a judgment`; fidelity list (advisory, exit unchanged) | MUST | SR-047, SR-050 | 15 min |
| M3 | `boundary/fullrun.py`: need decision, reuse on identical identity, one in-process full run with the same-tree flaky rerun, never a second; `merge-evidence` event on green | MUST | SR-048 | 30 min |
| M4 | Claims gate (`claims check --range FORK..HEAD`), stale and dangling links of touched records, log integrity: exit 1 with fixes | MUST | SR-049 | 20 min |
| M5 | `boundary/cli.py`: `plumb merge-check [BASE] [--no-run] [--json]`, report caps, no writes except `merge-evidence` | MUST | SR-052 | 15 min |
| M6 | `--install-pre-push`, `--uninstall-pre-push`, `--hook pre-push` (stdin refs, base selection), foreign hook untouched | MUST | SR-051 | 15 min |
| MS1 | JEV pre-scoring of up to five fidelity packets within 5 s | SHOULD | SR-050 | 15 min |
| MS2 | `trailers check-msg` calls `capture.api.diff_serves` for the non-blocking warning (sp2 10.1) | SHOULD | SR-044 | 10 min |
| MS3 | Claims: accept revert, merge and fixup messages whose paths are all exempt (followups, BRIDGE B1) | SHOULD | SR-049 | 15 min |

MUST total: 120 min. Merge points: after M3, after M6, at the end. **Drop order**: MS3, MS2,
MS1.

Tests (`tests/merge/`): M1 `test_report.py`: `test_validate_merge_and_merge_check_agree`,
`test_touched_unconfirmed_exits_4`, `test_set_member_counts_only_with_full_set_approval`; M2
`test_glance.py`: `test_lists_agent_relayed_with_quote`, `test_lists_auto_jev_with_score`,
`test_repinned_unjudged_listed_not_held`, `test_fidelity_never_changes_exit`; M3
`test_fullrun.py` (a fake runner counting calls): `test_pending_cleared_by_one_green_run`,
`test_red_run_not_repeated_and_holds_5`, `test_identical_identity_reuses`,
`test_no_run_flag_runs_nothing`, `test_merge_evidence_only_on_green`; M4 `test_gates.py`:
`test_undeclared_path_exits_1`, `test_stale_link_on_touched_record_exits_1`,
`test_dangling_link_exits_1`, `test_exit_precedence_1_5_4`; M5 `test_cli.py`:
`test_report_caps_lists`, `test_writes_nothing_but_merge_evidence`; M6 `test_prepush.py`:
`test_installs_and_leaves_foreign_hook`, `test_hook_blocks_push_on_nonzero` (temporary repo
with a bare remote), `test_uninstall_removes_only_plumb_hook`.

Definition of done: sp3 10.

## 6. Lane HOSTS (sp4)

Goal: thin adapters for Codex, Pi and Hermes over `hosts.neutral`, the CLI-only fallback,
and the read-only MCP server.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| H1 | `docs/hosts.md`: each host's event surface from the installed version's docs or `--help` (read-only), as capability tables; rows without a mechanism marked fallback | MUST | SR-053 | 10 min |
| H2 | `hosts/cli.py`: `plumb hosts install\|uninstall\|status <host>`, `plumb turn start\|end`, shared install helpers (idempotent block and file writes, foreign entries kept); conformance test across host values | MUST | SR-053 | 25 min |
| H3 | `hosts/codex/`: `AGENTS.md` block, hooks where available, `notify` entry, marker where supported; `hosts status codex` prints the sp4 3.2 line when the marker is unavailable | MUST | SR-054 | 20 min |
| H4 | `hosts/pi/`: rendered `.pi/extensions/plumb/index.ts` mapping session start, input, tool result, agent end, the footer status and the `/plumb` command; marker where the extension API sets it, else the sp4 3.2 status line | MUST | SR-055 | 20 min |
| H5 | `hosts/hermes/`: rendered plugin (`plugin.yaml`, `plugin.py` with `register(ctx)`); marker where the plugin sets it, else the sp4 3.2 status line | MUST | SR-056 | 15 min |
| H6 | `mcp/server.py`, `mcp/cli.py`: JSON-RPC over stdio, the six read-only tools over `present.api`, read-only test | MUST | SR-057 | 30 min |
| HS1 | `plumb mcp install\|uninstall claude-code\|codex\|hermes` | SHOULD | SR-057 | 15 min |
| HS2 | Type-check the rendered Pi extension with `node` when available (skipped otherwise) | SHOULD | SR-055 | 10 min |

MUST total: 120 min. Merge points: after H2, after H6, at the end. **Drop order**: HS2, HS1.

Tests: `tests/hosts/test_turn.py` (`test_turn_start_logs_digest_and_prints_delta`,
`test_turn_end_prints_summary_and_block_exit_0`), `test_conformance.py`
(`test_same_output_for_every_host`), `test_codex.py`, `test_pi.py`, `test_hermes.py` (each:
`test_install_idempotent_preserves_foreign`, `test_uninstall_removes_only_plumb`,
`test_dry_run_writes_nothing`, `test_owner_only_refused_in_agent_shell` and
`test_status_names_missing_marker` (sp4 3.4 and 8.6), plus
`test_pi_extension_names_events_and_commands` and
`test_hermes_register_drives_callbacks` with a fake `ctx`); `tests/mcp/test_server.py`
(`test_initialize_and_tools_list`, `test_each_tool_matches_cli_view`,
`test_unknown_method_error`, `test_tools_are_read_only_plumb_unchanged`,
`test_no_write_tool_listed`).

Definition of done: sp4 8.

## 7. Lane PRESENT (sp5)

Goal: the deduplicated delta everywhere, the cards, plain-language owner commands, and the
Claude Code hook output; then the vault and alignment.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| P1 | `present/delta.py` emitter; prompt, stop and session-start hooks and `hosts.neutral` emit agent lines only through it; `hooks.stop_tokens` | MUST | SR-063 | 25 min |
| P2 | Status card (`present/render.status_card`, glyph and ASCII), snapshot fields, status line, "(N by JEV)", first summary line | MUST | SR-061 | 20 min |
| P3 | Intent card (`intent_card`), when-it-matters rules, `full\|compact\|off`, stated-set "shown" through the card, triage offer line, escalated-set question card | MUST | SR-062 | 25 min |
| P4 | `present/resolve.py`, `plumb resolve`; plain words for `explain`, `impact`, `show` | MUST | SR-064 | 15 min |
| P5 | `plumb status --card`, `plumb review`, `plumb confirm`; `.claude/commands/plumb.md` template with the six verbs | MUST | SR-064, SR-065 | 25 min |
| P6 | Routing regression test for every advertised verb and `why` | MUST | SR-068 | 10 min |
| PS1 | `view/`: `plumb view` vault, index notes, Canvas, idempotent, never read back | SHOULD | SR-066 | 40 min |
| PS2 | `align.py`: `plumb align [scope]`, gaps, edge questions, badges for the vault and review | SHOULD | SR-067 | 30 min |

MUST total: 120 min. Merge points: after P3, after P6, at the end. **Drop order**: PS2, then
PS1 (the vault is dropped last; if it is dropped, it is the first item of the next batch and
named at the top of the handoff).

Tests (`tests/present/`): P1 `test_delta.py` (`test_ten_prompts_three_records_once_each`,
`test_changed_record_reappears_once`, `test_instructions_deduplicated`,
`test_budget_cut_named_not_marked_seen`); P2 `test_status_card.py` (one per state,
`test_ascii_fallback`, `test_jev_count_only_with_auto_approvals`); P3 `test_intent_card.py`
(`test_format_four_lines`, `test_shown_only_when_it_matters`, `test_off_still_shows_trigger`,
`test_card_marks_record_shown_in_stated_set`); P4 `test_resolve.py`
(`test_ids_and_paths_first`, `test_ambiguous_lists_candidates`); P5 `test_review.py`,
`test_confirm.py` (`test_confirm_writes_no_approval`,
`test_plain_words_put_records_in_stated_set_shown`, `test_ids_with_confirm_relay_directly`);
P6 `test_routes.py`; PS1 `test_view.py` (`test_idempotent_bytes`,
`test_note_edit_changes_no_state`, `test_canvas_valid`); PS2 `test_align.py`
(`test_collection_fingerprint_deterministic`, `test_gaps_named`,
`test_judgments_never_change_edges`). Existing `tests/host/*` stay green or are updated
for the new output.

Definition of done: sp5 11.

## 8. Lane IMPORT (the importer completion)

Goal: the full pi-agent-factory register import of concept 10, idempotent with a dry-run diff,
specified in section 9.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| I1 | `importer/plan.py`: `plan_import` -> `ImportPlan` (create, update, unchanged, skip per record, with the field-level diff); `--dry-run` prints the diff | MUST | SR-060 | 20 min |
| I2 | Idempotent apply: records carry `source: {repo, path, upstream_hash}`; a second run on the same source changes nothing; a changed source updates the record and re-pins its links | MUST | SR-060 | 20 min |
| I3 | Symbol and test-node link ends in `hashing.py` and `links.py` (sp1 KS4: `path::Qual.name`, `path::test_name`, AST segment hashing, parametrize ids dropped) | MUST | SR-058 | 30 min |
| I4 | Relations: structured bindings to `implemented_by` symbol ends and `verified_by` test nodes, `upstream`, `relates_to`, `spec:` relations as `relates_to` path links when the document exists; bundles to features (union, differences as findings); NCs with `corrects` links | MUST | SR-058 | 20 min |
| I5 | Provenance: `by: import` approvals from upstream human consent pinning the current content (9.3); everything else proposed; `importer/recheck.py` fills the phase-0 stub `validate` calls | MUST | SR-059 | 25 min |
| IS1 | `.factory/trace-claims.yaml` to `.plumb/claims.yaml`; `evidence/runs/ingest-*.json` `commits[]` to a `claims-ingest` event | SHOULD | SR-058 | 20 min |
| IS2 | Rehearsal on an exported copy (`git archive`, fork plan F3), twice, recorded in `docs/import-rehearsal.md` | SHOULD | SR-060 | 15 min |
| IS3 | One-pass pinning to bring the 2 min 14 s import down (fork plan K4) | SHOULD | SR-060 | 15 min |

MUST total: 115 min. Merge points: after I3, after I5, at the end. **Drop order**: IS3, IS2,
IS1.

Tests (`tests/importer/`): I1 `test_plan.py` (`test_dry_run_diff_lists_create_update_skip`,
`test_dry_run_writes_nothing`); I2 `test_idempotent.py` (`test_second_run_no_change`,
`test_changed_source_updates_and_repins`, `test_never_writes_source_tree`); I3
`tests/core/test_hashing.py` and `test_links.py` additions (`test_symbol_end_ignores_edits_elsewhere`,
`test_test_node_drops_parametrize_ids`, `test_missing_symbol_dangles`); I4
`test_relations.py` (`test_bindings_become_symbol_and_node_links`,
`test_spec_relation_becomes_relates_to_path`, `test_feature_union_and_differences`,
`test_nc_corrects_link`); I5 `test_provenance.py` (`test_consent_pinning_current_content_gives_by_import`,
`test_consent_for_older_content_stays_proposed`, `test_non_human_or_wrong_phrase_ignored`,
`test_by_import_cites_consent_file_and_digest`, `test_validate_rechecks_by_import`).
Fixtures: copies of real consent files and SR files read once from
`C:/coding/pi-agent-factory` into `tests/bridge/fixtures/pi_factory/`.

Definition of done: 9.5.

## 9. The importer completion (specification)

Concept 10 and the fork plan (sections 5 and 7) set the goal; sub-project 1 built the minimal
importer (sp1 8.1, SR-023). This completes it. Requirements: `SR-058` to `SR-060` under
`FEAT-004`.

### 9.1 Scope

`plumb import pi-agent-factory <source> [--dry-run] [--diff] [--only SR,FEAT,NC,CLAIMS]
[--json] [--root <target>]` reads the source read-only (files opened read-only, `HEAD` read
from `.git` files, no git command in the source) and maps:

- `requirements/SR-*.md`: as sp1 8.1, plus each structured `implemented_by` and
  `verified_by` binding as a symbol or test-node end when it names one (I3), and each
  acceptance criterion's `verification.ref` as a `verified_by` link naming that `AC-n`;
- `upstream` and `relates_to` to records; `spec:` relations to `relates_to` path links when
  the document exists in the target, otherwise a `relation-skipped` finding;
- `docs/features/FEAT-*.md` plus `bundles/*.json`: membership is the union; each difference
  is a `membership-difference` finding, never resolved silently;
- `docs/nonconformances/NC-*.md`: read leniently, `corrected_by` kept verbatim, a `corrects`
  link to each SR the NC names;
- (SHOULD) `.factory/trace-claims.yaml` and the ingest checkpoint.

### 9.2 Link ends

Symbol ends hash the normalized AST source segment of the definition (decorators included);
test-node ends hash the test function's source with parametrize ids dropped (concept 4.4).
A missing symbol or node makes the link dangling. Directories, globs and line numbers are
never ends.

### 9.3 Approval provenance (`by: import`)

pi-agent-factory records human consent per SR in
`.factory/planning/<run_id>/consent/SR-###.json` with `decision: "approve"`,
`reviewer: "human"`, the fixed consent phrase, a `reason` and `requirement_sha256`, the
SHA-256 of the SR file's LF form (`coherence/planning/digest.py`; its CRLF form is accepted
too). For each imported SR:

- if a consent record exists whose `decision`, `reviewer` and `phrase` are exactly those, and
  whose `requirement_sha256` is in the accepted digests of the source SR file's current
  bytes, the importer writes one approval `by: import` pinning the imported record's plumb
  hash, with `{upstream: {repo_head, consent_path, consent_digest, requirement_sha256,
  run_id}}`;
- otherwise the record is `proposed`. Importing never manufactures a confirmation the owner
  did not give (concept 10, R2).

`plumb validate` re-checks every `by: import` approval: it cites a consent path and digest,
pins the record's hash at import, and was written with no session marker or by the importer
command (`import` event before it). The merge boundary lists `by: import` approvals in the
glance (sp3 3.2).

### 9.4 Idempotence and the dry-run diff

`plan_import` computes, for each source record, `create`, `update` (with the changed fields
and links), `unchanged` or `skip` (ID collision with a record of another origin, a finding).
`--dry-run` prints that plan as a diff and writes nothing; `--diff` prints it before applying.
Applying the same source twice changes no file and appends no event the second time (an
`import` event is appended only when something changed). Imported records carry
`source: {repo: "pi-agent-factory", path, upstream_hash}`; an update keeps the plumb ID,
rewrites the fields, re-pins the links whose ends exist, and leaves the record proposed
unless 9.3 gives a fresh `by: import` approval for the new content.

### 9.5 Definition of done

1. A dry run of `C:/coding/pi-agent-factory` into a scratch target prints the diff and leaves
   the source unchanged (git status and file hashes compared).
2. Two consecutive imports of the same source into a scratch copy produce identical trees.
3. Every `by: import` approval cites a consent record pinning current content; tests cover
   current, older and malformed consent.
4. Symbol and test-node ends are hashed and checked in `plumb validate` and `plumb drift`.
5. Findings report counts by kind; pi-agent-factory's register is never imported into
   plumb's own repository (fork plan 2: the SR IDs collide).

## 10. Phase 2: Integrate (coordinator, on `main`)

1. Merge each lane's final branch with `git merge --no-ff next/<lane>` and the `SR:` trailers
   of its merged rows, in this order: IMPORT (link ends are below everything), CAPTURE,
   MERGE, PRESENT, HOSTS. Only `docs/followups.md` may conflict (keep both sections). After
   each merge, run that lane's focused set once.
2. `uv run plumb hooks install` (new skills, deny rules, command file); `uv run plumb hosts
   status`; `uv run plumb mcp serve` smoke via `tests/integration/test_mcp_smoke.py`.
3. Plumb's own records: link every new module and test file to its SR (`plumb link`),
   `plumb repin` only for the coordinator's own link changes, `plumb tests map`.
4. **The single full-suite run:** `uv run plumb merge-check main` (it runs the suite once
   when full verification is pending, records the evidence pinned to identity, and reports).
   If MERGE's M3 did not land, `uv run plumb tests run --full` once instead. No other full
   run happens in this batch. Expected exit: 4, because plumb's records await the owner (no
   agent approves them); 1 or 5 are failures to fix (HIGH) before phase 3.
5. Dogfood checks: `plumb validate` (no errors), `plumb drift`, `plumb claims check --range
   <phase-0 base>..HEAD` (no undeclared path), `scripts/bench_hooks.py` on plumb's repository
   (each hook within the sp1 budgets; misses recorded), `scripts/drive_session.py` (the
   driven loop through the reinstalled hooks shows the status card and, for a proposed
   intent, the intent card).
6. README: the new commands and slash commands; `docs/followups.md` collects every lane's
   unfinished items.

Gate (10.4): steps 1 to 5 done; the full run collected cleanly and its failures are fixed or
recorded; no hook over budget without a followup entry.

## 11. Phase 3: Review

- One intent verifier reads the merged result against the brief, R1 to R12 and the four
  specs; more verifiers (one per lane diff) if time allows. Severity follows R7: HIGH only
  for a genuine contradiction or omission of the owner's explicit words or decisions or the
  rulings, or a broken guarantee (a path that confirms without the owner's words or outside
  R8 B, a hook that can block or exceed its budget, a second full run per merge-check, an
  MCP write path, an import that manufactures a confirmation).
- Each HIGH finding is fixed for its whole class: the guarantee named, every entry point
  enumerated, one choke point fixed, one test per entry point, the touched tests run (no
  second full suite), committed with `SR:` trailers. Medium and low findings go to
  `docs/followups.md` under `## Next batch review (date)`.

## 12. Protection order and cuts

Never cut: phase 0; every lane's R2 guard items (the owner-terminal guard
`approvals.require_owner` with its test per owner-only command in C4, C5, C6 and CS4, and the
per-host guard tests of H3 to H5; C5 and C6 relay checks, the deny rules of 3.2, CS4's "never" cases if CS4 is built, M2's glance, I5's
provenance rule, the MCP read-only test); the single full run and the dogfood checks of
phase 2; the HIGH-fix rule.

Order of protection (highest first): phase 0; each lane's MUST items; phase 2; phase 3
(down to one verifier); SHOULD items, each lane in its own drop order. A lane whose MUST item
is unfinished at lane start + 2 h 30 hands back what passes its gate; the missing item is
recorded in `docs/followups.md` and named at the top of the handoff.

## 13. Definition of done (the batch)

- [ ] phase-0 gate passed; contracts frozen in `contracts.py` and listed in 3.5;
- [ ] each lane's MUST items merged, each with its tests marked by SR, its lane gate passed,
      and its spec's definition of done met for the built items;
- [ ] the single full-suite run done in phase 2, through `plumb merge-check` when built,
      evidence recorded; no other full run in the batch;
- [ ] `plumb validate` without errors, `plumb drift` reviewed, `plumb claims check` clean
      over the batch range;
- [ ] hooks within budget on plumb's repository (or each miss in `docs/followups.md`);
- [ ] no agent-written owner approval, triage approval, set approval or config event in the
      batch range (`plumb merge-check` glance shows none but relays the owner typed);
- [ ] `docs/concept.md` reflects R8 to R12 (done with this plan);
- [ ] every unfinished SHOULD item and every medium or low finding in `docs/followups.md`;
      no HIGH finding open;
- [ ] the handoff names what awaits the owner: the proposed records of FEAT-002 to FEAT-005
      (`plumb triage`, or "ok" in a session), and the owner-only switches
      (`plumb config auto-approve on`, `plumb merge-check --install-pre-push`).

## 14. Risks

| Risk | Mitigation |
|---|---|
| Five lanes on 2 cores | No `-n` in lanes; focused sets only, once per commit; the full suite only in phase 2 |
| A contract gap found mid-lane | Phase 0 writes every signature and stub; a change goes through the coordinator; the lane moves on meanwhile |
| PRESENT changes hook output that HOSTS mirrors | HOSTS renders `TurnOutput` only, never hook text; the conformance test compares hosts against the same handler |
| Auto-approval read as a model confirming intent | Off by default; owner-only switch backed by a log event; calibration gate; never for matters, sets or edits of owner-confirmed records; labelled everywhere and listed at the merge boundary (sp2 8.2) |
| The agent turns auto-approval on by editing `config.yaml` | The YAML is a mirror; the effective state is the owner's `config` event, written only without the session marker; `validate` warns on a mismatch (sp2 C4) |
| Host event names differ from the design | H1 records the installed host's surface first; rows without a mechanism use the CLI-only fallback |
| Symbol hashing changes link states repository-wide | IMPORT merges first in phase 2; whole-file ends keep hashing as before; only links naming `::` ends use symbol hashing |
| JEV unavailable | Every JEV path degrades to the heuristic or "no judgments available"; live tests are skipped without the credential |
| pi-agent-factory's slow filesystem stalls a lane | Read single files only, never recursive greps; fixtures copied once |
