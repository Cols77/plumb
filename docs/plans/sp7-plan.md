# SP7 plan: the owner surface in four lanes

Implements `docs/specs/sp7-owner-surface.md` (rulings R14, R15, R16, R18, R19 and two SP6
leftovers) in four lanes with disjoint files and frozen contracts: PLUGIN (spec 4), MOD
(spec 5), SURFACE (spec 6 and 7, and the text part of 8.7) and CAPTURE2 (spec 8.1 to 8.6).
The owner does not review this plan (D11); verifier agents check it against the owner intent
brief, rulings R1 to R19, `docs/concept.md` and the spec. "spec 5.7" means section 5.7 of the
sp7 spec. Records: `FEAT-007`, `INT-023`, `SR-082` to `SR-095`, `DEC-023` to `DEC-025`, all
proposed, written with plumb's own CLI; agents never approve them.

| Lane | Spec | SRs | Decisions |
|---|---|---|---|
| PLUGIN | 4 | SR-082, SR-083, SR-084 | DEC-023 |
| MOD | 5 | SR-085, SR-086, SR-087 | DEC-024, DEC-025 |
| SURFACE | 6, 7, 8.7 | SR-088, SR-089 | |
| CAPTURE2 | 8.1 to 8.6 | SR-090, SR-091, SR-092, SR-093, SR-094, SR-095 | |

**Every R14, R15, R16, R18 and R19 item is a MUST.** This plan has no SHOULD tier and no
drop order. A lane that overruns keeps going; the batch waits for it. Model routing (R19's
deferred list) is out of scope; no lane starts it.

Binding owner rules for every phase (from the work order and the brief):

1. **HIGH findings only, whole class.** Fix only HIGH findings, and fix the whole class:
   name the guarantee, enumerate every entry point, fix at one choke point, add one test per
   entry point. Medium and low findings go to `docs/followups.md`.
2. **Test economy.** No full suite except the single run in Integrate. Iterate on the
   touched tests only. Before each commit, run the lane's focused set (3.4) once, in the
   FOREGROUND (timeout up to 600000 ms).
3. **Latency.** Hook latency stays in seconds; spec 10's budgets hold (a repository not
   adopted starts no Python; `pre-tool` for a command not about plumb starts no Python; the
   mod adds no process to the prompt path).
4. **Process safety.** Never kill a process you did not start. The machine has 2 cores: at
   most `pytest -n 2`, and lanes run without `-n`.
5. **Dogfooding.** Every commit carries `SR: SR-###` trailers that claim its paths (the
   `commit-msg` hook enforces it). New requirements are proposed plumb records with
   examples, written through plumb's CLI. Run `plumb validate` and `plumb drift` before
   committing. Set `PYTHONUTF8=1` when running plumb from a shell. **Agents never approve
   records**: no agent runs `plumb approve`, `revoke`, `triage --approve`, `spec approve`,
   `config auto-approve`, `conflict choose`, `owner ...` or `mod press|hello|typed` without
   the owner's own logged words or press, and no agent relays an approval or a choice the
   owner did not give (R2). Each new owner-only path gets its refusal test (exit 3, nothing
   written).
6. **Owner-visible text** speaks at the owner's level (R18) and never tells the owner to run
   a shell command (R14): every new owner string lives in `plumb.present.owner_text` and
   passes `shell_commands` and `jargon`.
7. `C:/coding/pi-agent-factory` is out of scope: never read, write or run anything there.
8. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## 1. Shape of the work

| Phase | What | Who | Gate before the next phase |
|---|---|---|---|
| 0. Contracts | Every cross-lane data class, config key, route, stub, call site, owner-text scanner and the plugin skeleton (3.2), so the lanes start against real interfaces | coordinator, alone, on `main` | 3.3 |
| 1. Lanes | PLUGIN, MOD, SURFACE, CAPTURE2 in parallel, each in its own worktree (sections 4 to 7) | four lane agents | lane gate (3.4) at each merge point |
| 2. Integrate | Merge the lanes, build the plugin, the owner e2e, the jargon scan, `claude plugin validate/test`, the live smoke, the ONE full-suite run (as `plumb merge-check`), docs (8) | coordinator, on `main` | 8.5 |
| 3. Review | Intent verifiers on the merged result; HIGH fixes only, whole class (9) | review agents; coordinator fixes | no HIGH finding open |

Orchestration uses the host's native mechanism: in Claude Code, the `Workflow` tool (phase 0
as one agent step with its gate; phase 1 as a `parallel()` of four lane pipelines, each a
sequence of segment agents with a merge-ready report per merge point; phases 2 and 3 as gated
steps). Starting it needs the owner's opt-in where Claude Code asks for it; this plan does
not grant it.

Lanes create no new records (every SP7 record exists; a lane that needs one stops that item
and asks the coordinator). Lanes append to the logs only through plumb's commands (`plumb
link`, `plumb repin`, `plumb verify`), which write one file per entry and never conflict.

## 2. Conventions for every agent

- Repository `C:/coding/plumb`. Phase 0 runs on `main`. Lanes work in worktrees
  `C:/coding/plumb-wt/sp7-<lane>` on branches `sp7/<lane>` (`plugin`, `mod`, `surface`,
  `capture2`), created from `main` after the phase-0 gate, then `uv sync` inside the
  worktree. `main` may hold staged work of another session when a lane starts; lanes never
  touch it, and the coordinator commits phase 0 with path-limited commits.
- Each lane starts with `uv run plumb brief`, `uv run plumb status` and `uv run plumb show
  <its SRs>` and keeps the output as context.
- Test first: write the failing test, see it red, implement, see it green. Mark every new
  Python test `@pytest.mark.sr("SR-0xx")`; name the SR in each TypeScript test's title
  (`test("SR-086 EX-1: Confirm presses ...")`).
- Iterate with the touched test file only. Before each commit: the lane's focused set once,
  in the foreground (3.4). No whole suite.
- Tests that need git use a temporary repository (`tests/gitrepo.py`), never the plumb
  repository. Tests that need the user's home (`PLUMB_HOME`, `CLAUDE_PLUGIN_DATA`,
  `CLAUDE_ENV_FILE`) point them into `tmp_path`; no test writes to the real home.
- `SR:` trailers: each commit names the SRs of the task rows it implements, and claims only
  paths those SRs declare. Before committing a new module, link it: `uv run plumb link
  SR-0xx implemented_by <path>` and `verified_by <test file> --example EX-n` (lanes may run
  `plumb link` and `plumb repin` on their own SRs; those never confirm anything). Then
  `uv run plumb validate`, `uv run plumb drift` and `uv run plumb claims check --range
  main..HEAD`.
- Lanes never edit another lane's files (3.1). A needed contract change stops that item; the
  lane asks the coordinator and moves to its next item.
- Medium and low findings, and anything unfinished with its state, go under the lane's own
  heading at the end of `docs/followups.md` (`## SP7 lane PLUGIN (2026-10-..)`).

## 3. Files, contracts and gates

### 3.1 Ownership (disjoint)

| Owner | Paths |
|---|---|
| Coordinator (phases 0, 2, 3) | `src/plumb/contracts.py`, `config.py`, `cli.py`, `cliutil.py`, `api.py`, `store.py`, `model.py` (the `agent_notes` hash exclusion only), `confirm.py`; the phase-0 stub files' API names; `plugin/` skeleton files until the lanes take them (below); `tests/integration/**` (`test_answer_choke_point.py` new), `tests/owner/**` (new: the e2e harness and scenarios), the one-line `cliutil.answer` call in each command module of an `owner` form (spec 6.6; phase 0 only, the lanes keep their modules otherwise), `tests/present/test_owner_text.py`, `tests/test_smoke.py`, `tests/gitrepo.py`; `.plumb/**`, `.claude/**`, `CLAUDE.md`, `docs/concept.md`, `docs/plans/**`, `docs/specs/**` |
| PLUGIN | `.claude-plugin/marketplace.json`; `plugin/.claude-plugin/**`, `plugin/bin/**`, `plugin/hooks/hooks.json`, `plugin/commands/**`, `plugin/skills/**`, `plugin/vendor/**` (GENERATED or built: only the build script writes `commands/`, `skills/`, `vendor/`, `hooks/*.gen.ts`); `scripts/build_plugin.py`; `src/plumb/plugin/**` (new), `src/plumb/launcher.py` (new), `src/plumb/guard.py` (new), `src/plumb/commands.py` (`init` only), `src/plumb/hosts/claude_code/install.py`, `session_start.py`, `hookio.py`, `hosts/claude_code/cli.py` (the `hook pre-tool` event), `templates/claude-md-block.md`; `tests/plugin/**` (new), `tests/host/test_install.py`, `tests/host/test_session_start.py` |
| MOD | `plugin/hooks/*.tsx` and `*.ts` except `*.gen.ts`, `plugin/types/**`, `plugin/tsconfig.json`; `src/plumb/mod/**` (new, keeps the phase-0 API names, `handshake.py` included); `tests/mod/**` (new) |
| SURFACE | `src/plumb/present/**`, `src/plumb/view/**`, `src/plumb/owner_actions.py` (new), `src/plumb/owner_cli.py` (new), `src/plumb/hosts/claude_code/stop.py`, `prompt.py`, `statusline.py`, `snapshot.py`, `templates/plumb-command.md`, `templates/skills/plumb/SKILL.md`; `src/plumb/boundary/**`; `src/plumb/validate.py`, `src/plumb/claims.py` and `src/plumb/trailers.py` (owner text only), `src/plumb/explain.py`, `src/plumb/capture/jevcmd.py` (status rendering only); `README.md`, `docs/owner-matrix.md` (new), `docs/hosts.md`; `tests/surface/**` (new), `tests/present/**` except `test_owner_text.py` and `test_align.py`, `tests/merge/**`, `tests/host/test_stop.py`, `tests/host/test_prompt.py`, `tests/host/test_statusline.py` |
| CAPTURE2 | `src/plumb/approvals.py`, `src/plumb/capture/**` except `jevcmd.py`, `src/plumb/align.py`, `src/plumb/mergedriver/**` (`holds.py` new; `gitconfig.py` keeps the phase-0 launcher call), `src/plumb/awareness/answer.py` (only if the early-conflict answer reads `owner_scope` differently), `templates/skills/plumb-clarify/SKILL.md`; `tests/capture2/**` (new), `tests/capture/**`, `tests/mergedriver/**` (SP6's `test_owner_text.py` there stays SURFACE's), `tests/present/test_align.py`, `tests/core/test_approvals.py` |
| Any lane, append only | `docs/followups.md` (own heading) |

Data files have one writer each: `.plumb/session/<id>/mod.json`, `offers/` and `present.json`
are written by `plumb.mod` (the stop hook writes `present.json` through
`mod.handshake.deliver`); `brief.json` by `session_start.py`; `PLUMB_HOME/**` by
`plumb.plugin` and the launcher; the `shown` log kind by `capture.assent.record_shown`; the
`prompt` log kind by the prompt hook and `plumb.mod.typed` (both through
`approvals`-owned writers, unchanged).

### 3.2 Phase 0: what the coordinator writes before any lane starts

1. **`contracts.py`.** The frozen data classes of spec 9 with defaults on every field:
   `ModHello`, `ModSnapshot`, `ModCard`, `ModOffer`, `ModButton`, `ModToast`, `PaneTree`,
   `PaneNode`, `OwnerActionResult`, `StructureReport`, `Gap`, `InReplyTo`, `ShownItem`,
   `MigrationResult`; `ClarifyView` gains `challenges` and `uncovered` (tuples, default
   empty).
2. **`config.py`.** Sections `mod` (`enabled: true`, `summary_line: true`, `toasts: true`)
   and `plugin` (`hint: true`); `plumb init`'s commented `config.yaml` lists them.
3. **Stubs with the final signatures (spec 9)**, each keeping today's behaviour:
   - `plumb/launcher.py`: `git_hook_line` and `driver_command` return today's interpreter
     forms (moved out of `boundary/premerge.py`, `boundary/prepush.py`,
     `mergedriver/gitconfig.py` and the commit-msg installer); `plumb_home` returns
     `~/.plumb`.
   - `plumb/guard.py`: `DENIED` holds today's deny-rule table moved out of `install.py`;
     `denied` matches it; `install.py` generates its rules from it (no behaviour change).
   - `plumb/plugin/__init__.py`, `plumb/plugin/cli.py`: `migrate`, `ignore` raise
     `NotImplementedError`; `legacy_install` reads `.claude/settings.json` (real, small); the
     CLI prints "not available in this build" (exit 2).
   - `plumb/mod/__init__.py`, `plumb/mod/cli.py`: `hello`, `snapshot`, `pane`, `press`,
     `typed` raise `NotImplementedError`; CLI exit 2. `plumb/mod/handshake.py`: `active`
     returns False, `deliver` returns the output unchanged, `background_owned` returns
     False.
   - `plumb/owner_actions.py`: `perform` raises `Refused("not available in this build")`;
     `parse_command` returns None. `plumb/owner_cli.py`: exit 2.
   - `plumb/capture/assent.py`: `is_bare_assent` returns False, `record_shown` does
     nothing, `check` does nothing, `validate_refs` returns `[]`. `capture/spec.py` gains `structure` (returns a clean
     report), `offerable` (True), `repair_note` (None). `plumb/mergedriver/holds.py`:
     `held_by_conflict` returns `{}`, `split` returns `(states, [])`.
4. **Call sites, wired once, so lanes edit only their own modules.**
   - `session_start.py` asks `mod.handshake.background_owned` before injecting the brief and
     writes `brief.json`; `stop.py` passes its output through `mod.handshake.deliver`, calls
     `capture.assent.record_shown` with the cards, questions and offers it shows, asks
     `capture.spec.offerable` before any set offer and adds `capture.spec.repair_note` to
     its block reasons.
   - Every list of stale links goes through `mergedriver.holds.split`: `boundary/gates.py`
     (links gate), `validate.py`, `present/report.py` (drift and status), `snapshot.py`
     (drift count), `stop.py` (drift lines), `present/review.py`, `view` badges.
   - `approvals.relay(..., set_anchor=...)` asks `capture.spec.offerable`.
   - `boundary/premerge.py`, `boundary/prepush.py`, `mergedriver/gitconfig.py` and the
     commit-msg installer call `plumb.launcher`.
   - `present/cards.py` draws `in_reply_to` ("you said ... to: ...") and `done_when` ("Done
     when: ...") when present (minimal lines; SURFACE finishes the wording).
   - `capture/records.py` accepts and stores `in_reply_to`, `done_when` and `serves` (the
     fields only; CAPTURE2 adds the checks).
   - `validate.py` reports the findings of `capture.assent.validate_refs(core)` (stub: none),
     so CAPTURE2 adds the `in_reply_to` check without editing `validate.py`.
   - `store.write_record` gains `text_check="refuse"|"report"` and calls
     `present.owner_text.record_gaps` (stub: `[]`), raising `RecordTextGaps` (exit 2 in the
     CLI) in `refuse` mode; `model.record_hash` leaves out `agent_notes` like `links`
     (spec 6.5); `validate.py` lists `record_gaps` of existing records as agent-facing
     `owner-text` warnings.
   - **Route answers (spec 6.6).** `cliutil.add_common` gains `--agent` and `--details`,
     and `cliutil.answer(args, form, payload, agent_text)` prints `--json` as the payload,
     `--agent` as today's text, `--details` as `present.answers.render(form, payload,
     details=True)` and the default as `present.answers.render(form, payload)`, falling
     back to today's text when the renderer returns `None`. Every command of an
     `owner` form of spec 6.6 emits through it (`--json` added where it was missing), so
     the default output is still today's text; the forms SP7 adds (`plugin ignore`,
     `plugin migrate`, the success line of `owner <action>`) call it from their first
     version, and their lane adds the same sentinel check in its own tests
     (`tests/plugin/test_answers.py`, `tests/surface/test_answers_text.py`). `present/answers.py` holds `FORMS` complete
     (every CLI form of spec 6.1 with its class) and the `render` stub (`None`). Tests that
     assert today's default text of an `owner` form switch to `--agent` now, while the
     change is a no-op; the `/plumb` template, the `plumb` skill, the prompt hook's delta
     pointer and the brief's pointer name `--agent` or `--json` for the agent's own reads.
   - Approval and event entries carry `via` and `resolved_from`; `plumb check` re-checks
     `via: command` entries by the parse check instead of the affirmation term (spec 7.2;
     stub parse: accept), and keeps "a `by: owner` entry under a marker is an error"
     unchanged.
5. **Routes.** `cli.ROUTES` adds `owner` -> `plumb.owner_cli`, `mod` -> `plumb.mod.cli`,
   `plugin` -> `plumb.plugin.cli`; the `hook` route accepts `pre-tool` (stub: allow); `spec`
   accepts `check` (stub: clean). `plumb --help` lists a verb only when its module is
   importable (SR-068).
6. **Owner text (spec 6.3).** `present/owner_text.py` gains `shell_commands`, `jargon`,
   `JARGON`, `CONCEPTS`, `explain`, and the constants of spec 9 with first wordings.
   `tests/present/test_owner_text.py` gains `test_shell_commands_flags` (`uv run plumb
   approve`, `python -m plumb`, `git push --no-verify`, `` `plumb repin SR-001#3` ``),
   `test_slash_and_plugin_commands_pass` (`/plumb confirm the reminders`, `/plugin install
   plumb@plumb`), `test_jargon_flags` (each `JARGON` term, an ID without its title, a
   `.plumb/` path), `test_title_beside_id_passes`, `test_concept_explained_first_passes`,
   `test_every_constant_passes` (both scanners).
7. **Plugin skeleton.** `.claude-plugin/marketplace.json` (with a description),
   `plugin/.claude-plugin/plugin.json`, `plugin/hooks/hooks.json` (the module and the five
   command hooks of spec 4.3), `plugin/bin/plumb-hook` and `plugin/bin/plumb` (exec the
   development `.venv` when `PLUMB_DEV_PYTHON` is set, for tests), `plugin/hooks/register.tsx`
   (an empty `register`), `plugin/types/index.d.ts` (`PluginState['plumb']` of spec 5.6),
   `plugin/tsconfig.json`. `claude plugin validate plugin` and `claude plugin validate .`
   pass.
8. **Test helpers.** `tests/gitrepo.py` gains `bare_remote(tmp_path)`; `tests/owner/
   harness.py` (new): `OwnerSession(root)` with `slash(text)`, `say(text)`, `press(label,
   card=...)`, `agent(route_args)` (runs only CLI forms parsed from the generated
   `plugin/commands/plumb.md`, failing on any other or on a form `present.answers.FORMS`
   does not classify, and returns its stdout), `show(output)` (what the scripted agent
   relays to the owner; it fails on the output of an `agent` form or an `--agent` text), `outputs()` (every
   owner-visible text captured, including the stdout of every `owner` form the agent
   ran), the hook calls through `plugin/bin/plumb-hook` with Claude Code's JSON payloads,
   and a simulated mod (`hello`, `snapshot`, `press`, `typed` with its key).
   `tests/integration/test_contracts.py` checks every stub against its signature.
9. **Records.** FEAT-007, INT-023, SR-082 to SR-095 and DEC-023 to DEC-025 exist (written
   with this plan). Phase 0 links each stub module `implemented_by` its SR.

### 3.3 Phase-0 gate

```
uv run pytest tests/core tests/host tests/merge tests/present/test_owner_text.py tests/integration/test_contracts.py tests/integration/test_answer_choke_point.py tests/test_smoke.py -q
uv run ruff check src tests
uv run plumb validate && uv run plumb drift
uv run plumb --help              # lists only importable verbs
claude plugin validate plugin && claude plugin validate .
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

Focused sets:

- PLUGIN: `tests/plugin tests/host/test_install.py tests/host/test_session_start.py
  tests/host/test_latency.py tests/core/test_cli_core.py`, plus `claude plugin validate
  plugin`, `claude plugin validate .` and `uv run python scripts/build_plugin.py --check`.
- MOD: `tests/mod`, plus `claude plugin test plugin`, `claude plugin validate plugin`, and
  `npx -p typescript@5 tsc -p plugin` when it is available offline (else noted in the
  merge-ready report).
- SURFACE: `tests/surface tests/present tests/merge tests/host/test_stop.py
  tests/host/test_prompt.py tests/host/test_statusline.py tests/mergedriver/test_owner_text.py`.
- CAPTURE2: `tests/capture2 tests/capture tests/mergedriver tests/core/test_approvals.py
  tests/present/test_align.py tests/awareness/test_early_answer.py`.

The lane reports `merge-ready <lane> <merge point> <sha>`. The coordinator merges with
`git merge --no-ff` (message with the merged rows' `SR:` trailers) and runs the merged lane's
focused set once on `main`; it does not run the whole suite until phase 2.

### 3.5 Interface contracts between lanes

| Provider | Interface | Consumers | Degraded form while missing |
|---|---|---|---|
| PLUGIN | `launcher.git_hook_line`, `driver_command`, `plumb_home`; `bin/plumb`, `bin/plumb-hook`, `PLUMB_HOME/current.json` (`{python, version, wheel_sha256, plugin_root}`) | SURFACE (hook texts), CAPTURE2 (driver), MOD (reads `current.json`) | today's interpreter path; tests set `PLUMB_DEV_PYTHON` |
| PLUGIN | `guard.DENIED`, `guard.denied`; `scripts/build_plugin.py` writes `hooks/guard.gen.ts`, `jargon.gen.ts`, `text.gen.ts` | MOD (`tool.call`, jargon test, labels), `install.py` | phase-0 table; MOD keeps a hand copy in its tests until the generator lands |
| MOD | `mod.handshake.active`, `deliver`, `background_owned`; `mod.press` calling `owner_actions.perform(..., via="button")`; `plumb mod` CLI JSON (`ModHello`, `ModSnapshot`, `PaneTree`) | SURFACE (`stop.py`, `session_start.py` via PLUGIN), the e2e harness | stubs: the hooks print as today |
| SURFACE | `owner_actions.perform` (with `show_first`), `parse_command`; `present.owner_text` (scanners, constants, `CONCEPTS`, `record_gaps`); the card and summary renderers MOD's snapshot calls (`present.cards.card_lines`, `present.render.summary_line`, `present.render.status_card`) | MOD, PLUGIN (hint and getting-ready lines), CAPTURE2 (gap and done-when lines) | the stub refuses; constants frozen at phase 0, wording changes through SURFACE only |
| CAPTURE2 | `capture.assent.is_bare_assent`, `record_shown`, `check`; `capture.spec.structure`, `offerable`, `repair_note`; `mergedriver.holds.held_by_conflict`, `split`; `approvals.owner_scope` (scoped) | SURFACE (`stop.py`, cards, merge report), MOD (offers for sets) | stubs: always offerable, nothing held, no assent check |
| Coordinator | data classes, routes, call sites, config keys, plugin skeleton, the e2e harness | all | frozen; changes only through the coordinator |

Unit tests never import another lane's new modules; they use the phase-0 stubs or local
fakes. MOD's TypeScript tests use fixtures (`tests/mod/fixtures/*.json`) its own Python tests
write from its own `plumb mod` code.

## 4. Lane PLUGIN (spec 4; SR-082, SR-083, SR-084)

| # | Task | Tests (first, red) | Merge point |
|---|---|---|---|
| P1 | Probe this Claude Code build once: does `$CLAUDE_ENV_FILE` reach the agent's shell for a plugin's SessionStart hook; is `${CLAUDE_PLUGIN_ROOT}` expanded in a plugin command's text; does `CLAUDE_PLUGIN_DATA` exist; does a plugin's PreToolUse `permissionDecision: deny` stop a Bash call. Record the answers in `docs/followups.md` (lane heading) for the coordinator's `docs/hosts.md` update; choose the forms of spec 4.3 accordingly | none (a probe in a scratch folder with `claude --plugin-dir`, no repository touched) | |
| P2 | `scripts/build_plugin.py`: build the wheel with `uv build --wheel`, write `vendor/MANIFEST.json` with `source_digest`, render the command and skills from the templates (`{plumb}` per P1), generate `hooks/guard.gen.ts`, `jargon.gen.ts`, `text.gen.ts` from Python; `--check` compares without writing | `test_bundle_fresh.py::test_check_passes_after_build`, `::test_check_fails_on_template_change`, `::test_check_fails_on_source_change`, `::test_version_matches_pyproject`, `::test_generated_ts_matches_python` | P-1 |
| P3 | `bin/plumb`, `bin/plumb.cmd`: bootstrap (lock, `uv venv` + `uv pip install` of the wheel, python fallback, `current.json`, user-level launcher, prune to two) and exec; never the repository's `.venv` | `test_env.py::test_bootstrap_builds_once`, `::test_bootstrap_lock`, `::test_stale_lock_taken_over`, `::test_hook_uses_bundled_env` (parametrized over the five hooks, a poisoned `.venv`), `::test_user_launcher_written`, `::test_needs_python_line` | P-1 |
| P4 | `bin/plumb-hook`: walk-up, the hint (startup and resume only, git work tree, not ignored), the legacy check, the `pre-tool` grep, the getting-ready line, exec | `test_unadopted.py::test_only_hint_at_startup`, `::test_silent_prompt`, `::test_silent_post_edit`, `::test_silent_stop`, `::test_silent_pre_tool`, `::test_no_python_started`, `::test_ignored_repo_silent`, `::test_hint_from_owner_text`, `::test_non_git_dir_silent` | P-1 |
| P5 | `plumb hook pre-tool` and `plumb.guard` (real matching for every launcher spelling); `install.py` rules from `guard.DENIED` | `test_guard.py` one case per denied form times spelling, `::test_status_allowed`, `::test_install_rules_from_same_table` | P-2 |
| P6 | Session start under the plugin: append the marker and PATH to `$CLAUDE_ENV_FILE` (per P1), the getting-ready path, `brief.json` per the handshake stub | `test_session_env.py::test_env_file_written`, `::test_env_file_absent_ok`; `tests/host/test_session_start.py` kept green | P-2 |
| P7 | `plumb init` under the plugin: `.plumb/`, the driver, commit-msg, pre-merge-commit, prepare-commit-msg, post-merge and pre-push through `launcher`, the not-set-up guard line in each hook, foreign hooks kept, nothing under `.claude/`; `launcher` real | `test_init.py::test_claude_dir_untouched`, `::test_git_hooks_written`, `::test_commit_msg_holds_missing_trailer`, `::test_merge_hold_runs_no_tests`, `::test_foreign_hook_kept`, `::test_hook_without_plugin_passes_with_line`, `::test_idempotent`; `test_env.py::test_git_hooks_use_user_launcher`, `::test_driver_uses_user_launcher` | P-2 |
| P8 | `plumb plugin migrate` and `plumb plugin ignore`; `known_templates.json` (digests of every released rendering, from git history of the templates) | `test_migrate.py::test_removes_only_plumb_entries`, `::test_edited_copy_kept`, `::test_claude_md_block_removed`, `::test_hooks_repointed`, `::test_legacy_repo_hooks_run_once`, `::test_without_plugin_legacy_unchanged`; `test_ignore.py` | P-3 |
| P9 | `claude plugin validate` on both manifests in the gate; `tests/plugin/test_validate.py` (skips without `claude`) | `test_validate.py::test_plugin_valid`, `::test_marketplace_valid` | P-3 |

Merge points: P-1 after P4, P-2 after P7, P-3 after P9.

## 5. Lane MOD (spec 5; SR-085, SR-086, SR-087)

| # | Task | Tests (first, red) | Merge point |
|---|---|---|---|
| M1 | Re-read the build's declarations (`claude-code.d.ts` beside the plugin-authoring skill, and `.claude-plugin/types/` once loaded) for `session.start`, `turn.start`, `turn.complete`, `prompt.compose`, `command.run`, `ui.render` (`AbovePrompt`, `Pane`, `CommandOutput`), `ui.press`, `tool.call`, `session.append`, `$.state`, `$.process.run`, `$.fs`, `$.ui.open`, `$.ui.toast`, `$.session`; note how `/plumb` resolves in `command.run` and whether the prompt hook runs for a typed slash command; adapt names, never behaviour | none | |
| M2 | `plumb mod hello` and `mod.json` (first wins), the heartbeat format; `handshake.active`, `deliver` (writes `present.json` from the stop hook's owner-facing parts, drops `systemMessage`, keeps a block), `background_owned` | `tests/mod/test_hello.py`, `test_handshake.py::test_stop_writes_present_no_message`, `::test_block_kept`, `::test_stale_heartbeat_prints`, `::test_background_owner_rule` | M-1 |
| M3 | `plumb mod snapshot` and `plumb mod pane` composing the SURFACE renderers (status card, summary line, cards, toasts chosen by the matters rules) and writing offers (`offerable` for sets) | `test_snapshot.py::test_offer_ids_stable`, `::test_no_set_offer_when_not_offerable`, `::test_toasts_only_for_what_matters`, `::test_snapshot_passes_scanners`, `::test_pane_tree_titles_only`, `::test_pane_details_shows_ids`; `test_fixtures.py` writes the shared fixtures | M-1 |
| M4 | `plumb mod press` (key check, offer check, hashes rechecked, `owner_actions.perform(via="button")`) and `plumb mod typed` | `test_press.py::test_confirm_pins_shown_hashes`, `::test_changed_target_left_out_and_named`, `::test_wrong_key_refused`, `::test_no_key_refused`, `::test_agent_shell_refused` (marker set, exit 3, nothing written), `::test_each_action` (approve, group, set, conflict, revoke, auto_approve, waive); `test_typed.py` | M-2 |
| M5 | `register.tsx`: `session.start` (root, `current.json`, key, hello, `$.state`), `turn.start` heartbeat, `turn.complete` summary line and snapshot refresh, `prompt.compose` background, `.catch` fallbacks | `fallback.test.tsx`, `summary.test.tsx`, `compose.test.tsx` | M-2 |
| M6 | The band (`AbovePrompt`): collapsed line, Hide/Show, expansion rules, compact and off, buttons; Show all | `band.test.tsx`, `buttons.test.tsx` | M-3 |
| M7 | The pane (`Pane`), `/plumb pane`, Open in Obsidian; `command.run` for `/plumb`, `/plumb status`, `/plumb confirm` and `CommandOutput` drawing, pass-through for the rest, the typed-command log | `pane.test.tsx`, `command.test.tsx` | M-3 |
| M8 | Toasts and notices (`$.ui.toast`, `$.session.append` system and user-meta rows), `$.state` dedupe; the `tool.call` guard from `guard.gen.ts` | `buttons.test.tsx` (notices), `guard.test.tsx`, `jargon.test.tsx` | M-3 |
| M9 | `claude plugin validate plugin` lists the hooks and `$` calls; `tsc -p plugin` where available; every test title names its SR | the gate | M-3 |

Merge points: M-1 after M3, M-2 after M5, M-3 after M9. M4's `owner_actions` call runs
against the phase-0 stub until SURFACE's S2 merges; `test_press.py` uses a local fake of
`perform` for the action cases and asserts the call's arguments.

## 6. Lane SURFACE (spec 6, 7 and 8.7; SR-088, SR-089)

| # | Task | Tests (first, red) | Merge point |
|---|---|---|---|
| S1 | `owner_text`: finish `JARGON`, `CONCEPTS`, the explain-first rule, the SP7 constants' wording; the agent/owner split of refusal and hook texts (`HookOutput` keeps the agent's part in its own field) | `tests/present/test_owner_text.py` (phase-0 cases stay green), `tests/surface/test_refusal_text.py` | S-1 |
| S2 | `plumb.owner_actions` (`perform`, `require_owner_action`, `parse_command`) and `plumb owner` CLI; route every terminal owner-only command through `perform(via="terminal")`; `auto_approve on` refuses without calibration in plain words; `set` asks `offerable` | `tests/surface/test_owner_actions.py`: per action, `command` accepted (hook-logged and mod-logged), self-recorded refused, no prompt refused (exit 3, nothing written), mismatched words refused; every `command` entry is `by: agent-relayed`, `via: command`, the whole typed command as its quote and the prompt digest, never `by: owner`; `::test_check_clean_after_typed_confirm` (`plumb check` has no error after `/plumb confirm SR-...` under the session marker; the glance lists it under "you typed"); `tests/surface/test_show_first.py`, one case per entry point (`/plumb confirm <words>`, `/plumb approve <decision words>`, `/plumb revoke <words>`, the group's words, the plan's words) against records not shown in the previous reply: nothing written, `show_first`, the cards shown as the stated set, then "ok" (relayed) or a press (`by: owner`) confirms exactly those hashes, a record edited in between left out and named; the same commands by ID, or naming only records shown in the previous reply, act at once (SR-088 EX-3, EX-7); "which one do you mean?" with nothing written on an ambiguous one (SR-088 EX-6); terminal cases with stdin a pipe holding "y" refused | S-1 |
| S3 | Stop hook, status card, session-start owner lines: titles instead of IDs, plain test states, decisions by their question, no paths; `in_reply_to` and `done_when` lines on cards; the structure gaps never shown to the owner. Route answers (spec 6.6): `present.answers.render` for every `owner` form of `FORMS` (the nine views, `drift` with each drift kind, `show`, `resolve`, `fidelity` without the packet header, `brief` without storage paths, `status --root`, `init`, `plugin ignore` and `migrate`, `import`, `merge-fix`, `ids sync`, `log migrate`, `escalate`, the success lines of `relay`, `owner` and `conflict relay`, and the rest of the list) | `test_summary_text.py` (each card kind), `test_status_text.py`, `test_session_text.py`, `test_answers_text.py` (`test_owner_answer` once per `owner` form: default, `--details` and `--agent`; `test_drift_kinds`, `test_fidelity_answer`, `test_show_awaiting`, `test_brief_no_paths`, `test_help`), `tests/host/test_stop.py` kept green | S-2 |
| S4 | Merge report, gates, pre-push, pre-merge-commit, prepare-commit-msg, post-merge, commit-msg outputs: no shell command, no `--no-verify` hint, `/plumb confirm <title>`, "say 'waive the full run'", titles not paths; `jev status` and `validate` warnings in plain words | `test_merge_text.py` (each report section), `test_prepush_text.py` (real push to a bare remote), `test_premerge_text.py`, `test_commit_text.py`, `test_jev_text.py`, `test_validate_text.py` | S-2 |
| S5 | `templates/plumb-command.md`: a route for every owner row of spec 6.1, the rules at the top, `allowed-tools` for every agent form (no owner-only form without `--prompt`); `templates/skills/plumb/SKILL.md`: the owner-level rule, the background, the routes | `test_command_routes.py::test_every_matrix_row_routed`, `::test_allowed_tools_cover_routes`, `::test_no_owner_only_form_without_prompt`, `::test_agent_forms_never_shown` (spec 6.6); `tests/surface/test_skill_text.py` (the plumb skill states the owner-level rule and the routes) | S-3 |
| S6 | `docs/owner-matrix.md` from spec 6.1; README split into "Using plumb" and "The agent's interface"; `docs/hosts.md` plugin and mod rows (with PLUGIN's P1 probe answers) | `test_matrix.py::test_every_route_listed`, `::test_every_route_form_classified` (spec 6.6), `test_docs_text.py` (README, matrix, hosts owner parts) | S-3 |
| S7 | `src/plumb/view/**`, the Obsidian vault at the owner's level (spec 6.3, vault row): every record note, `awaiting-you.md`, `by-feature.md`, `drift.md` and the Canvas labels lose the copyable CLI commands ("To confirm, type /plumb confirm <title> or say ok in a Claude Code session; editing this note confirms nothing"), wikilinks carry titles, stale or dangling wording becomes plain words, IDs and hashes stay in frontmatter and `## Details` only; the agent-relayed, typed-command and button labels of spec 7.2 in `plumb show` and the merge-boundary glance | `tests/surface/test_view_text.py` (both scanners on every generated note and Canvas label; frontmatter and `## Details` with `details=True`); `tests/merge/` glance cases for "you typed", "you said", "you pressed Confirm" | S-3 |
| S8 | `present.owner_text.record_gaps` (spec 6.5): the owner-facing fields per kind, the quote and `agent_notes` exemptions, `Gap.agent_line`; `validate`'s agent-facing `owner-text` warnings for old records | `tests/present/test_record_gaps.py` (each field per kind, the exemptions, unchanged fields not rescanned) | S-1 |

Merge points: S-1 after S2 and S8, S-2 after S4, S-3 after S7. S2 and S8 merge early
because MOD's press, CAPTURE2's record-text tests and the e2e depend on them.

## 7. Lane CAPTURE2 (spec 8.1 to 8.6; SR-090 to SR-095)

| # | Task | Tests (first, red) | Merge point |
|---|---|---|---|
| C1 | R16: `approvals._in_scope` inside `owner_scope`, `change_clauses` and the reservation rule (rules 1 to 3 of spec 8.1 for an ok naming IDs, a bare ok and a kind-scoped ok alike, T being what the ok answers; no "every change clause" fallback; the record-index document frequency for distinctive words, the repository-name exclusion) | `tests/capture2/test_relay_scope.py`, through each entry point (`relay` IDs, `relay` with a bare ok after cards, `--group`, `--set`, `conflict relay`, the early answer, `owner_actions` words via a local fake, the prompt hook's relay line, the `prompt_objects` flag): the R16 message against real copies of DEC-017 and DEC-018; an unrelated request plus a bare "ok" (in its own sentence, before and after) after the cards, group offer or set offer that entry point answers, confirming exactly that set (SR-090 EX-7); an out-of-sentence correction that refers back or uses a distinctive word of a shown record still refused (SR-090 EX-3, EX-5, EX-8); SR-090 EX-2 to EX-5 through each entry point that accepts them; `tests/capture/test_plain_objection.py`, `test_plain_change.py`, `test_relay_grounding.py` kept green | C-1 |
| C2 | Assent provenance: `capture.assent` (`is_bare_assent`, `record_shown` writing the `shown` log kind, `check`), the checks in `capture`, `intent`, `example`; `autoapprove.py` single-proposal rule; `validate_refs` (wired into `validate` in phase 0) | `test_assent.py`: one per SR-091 example and one per entry point | C-1 |
| C3 | Self-challenge: `ClarifyView.challenges` (absolutes, tradeoffs via the backend, unsupported claims, contradictions with confirmed records); the plumb-clarify SKILL.md step and the owner-level rule | `test_challenge.py`, `tests/capture/test_skills.py` (clarify part), `tests/capture/test_clarify_e2e.py` extended with the "instantly" request | C-2 |
| C4 | `done_when`: fields, numbering, hash, `ClarifyView.uncovered`, `align` gaps through `owner_text.DONE_WHEN_GAP` | `test_done_when.py` | C-2 |
| C5 | Structure check: `serves`, `W-n` numbering, `spec.structure`, `offerable`, `repair_note`, `plumb spec check`; `relay --set` refusal; the escalated-depth repair loop in plumb-clarify and the gap kinds | `test_structure.py` (each gap kind, the scripted repair loop, one intent gap one question, every offer entry point hides or refuses an unclean set) | C-3 |
| C6 | `mergedriver.holds` and the repin on the owner's choice (choose, conflict relay, the conflict button's `perform` path) | `test_conflict_holds.py` (one per entry point of spec 8.6, the repin after each way to choose) | C-3 |
| C7 | Record content at the owner's level (spec 6.5): every write entry point passes its mode to `store.write_record` (`refuse` for capture, intent, new, example, decide, conflict propose; `report` for import, the merge driver, merge-fix, the conflict choice); the plumb-clarify skill tells the agent to write record fields in the owner's words and put technical detail in `agent_notes` | `tests/capture2/test_record_text.py`, one case per entry point of spec 6.5 (against SURFACE's `record_gaps` once S-1 merged; a local fake before) | C-3 |

Merge points: C-1 after C2, C-2 after C4, C-3 after C7. C1 is first: it is the owner's
reported bug.

## 8. Phase 2: Integrate (coordinator, on `main`)

### 8.1 Merge order

CAPTURE2, SURFACE, PLUGIN, MOD (each `git merge --no-ff` with its rows' `SR:` trailers).
After each merge, that lane's focused set once. Cross-lane conflicts on generated files are
resolved by running `scripts/build_plugin.py`, never by hand.

### 8.2 Build and validate the plugin

`pyproject.toml` and `plugin.json` to `0.7.0`; `uv run python scripts/build_plugin.py`;
`--check` clean; `claude plugin validate plugin`; `claude plugin validate .`;
`claude plugin test plugin`; `tsc -p plugin` where available.

### 8.3 The owner e2e and the jargon scan

`tests/owner/test_owner_flows_e2e.py` (spec 12 item 2), on the harness of 3.2 item 8, one
scenario function per owner-facing row group of spec 6.1, every captured output through
`shell_commands` and `jargon`, including the stdout of every CLI call the scripted agent
makes on an `owner` form of spec 6.6 (drift, show, fidelity, brief, help, init, plugin
migrate, the import summary, merge-fix, ids sync, log migrate, status for another
repository, escalate and the rest); the harness fails when the scripted agent relays an
`agent` form's output or an `--agent` text. `tests/owner/test_inputs_are_owner_inputs.py` asserts the
harness never sends the owner anything but slash commands, prose and presses. The live smoke
(`claude -p --plugin-dir plugin "/plumb status"` in an adopted temporary repository) runs
once when `claude` is signed in; its output goes through both scanners.

### 8.4 Dogfood and the single full run

plumb's own repository keeps its per-repository install (spec 4.7); the coordinator checks
that the plugin, when loaded with `--plugin-dir` in the plumb repository, stays silent (no
double summary). `plumb init` there adds the missing commit-msg hook only if it is absent.
Then the ONE full-suite run, as `plumb merge-check` on the merged `main` (serial, foreground
or background with notification, never a second run; failures are triaged under the
failure policy: flaky rerun on the same tree, a real failure fixed with the lane's focused
set).

### 8.5 Integrate gate

```
uv run plumb merge-check                         # the single full run, passing
uv run python scripts/build_plugin.py --check
claude plugin validate plugin && claude plugin validate . && claude plugin test plugin
uv run plumb validate && uv run plumb drift && uv run plumb claims check --range <base>..HEAD
```

and `docs/concept.md` (4.2, 4.6, 5, 6, 9, 11), the README, `docs/hosts.md` and
`docs/owner-matrix.md` describe the shipped behaviour.

## 9. Phase 3: Review

Independent verifier agents read the brief (R1 to R19), the concept, the spec and the merged
code, and grade findings under R7 (HIGH only for a genuine contradiction or omission of the
owner's explicit words, decisions or rulings). They exercise, at least: a fresh repository
adopted only with `/plumb init` through the harness; the R16 message; a button press by the
simulated mod and the same press attempted from the agent's shell; the pre-push output of a
push carrying an unconfirmed requirement; the README read as the owner. HIGH findings are
fixed by the coordinator, whole class (guarantee, every entry point, one choke point, one
test per entry point); medium and low go to `docs/followups.md` under "SP7 review".

## 10. Definition of done (the batch)

1. Spec 12 items 1 to 8 hold.
2. Every lane's rows are merged; every SR of FEAT-007 has its linked code and tests
   (`plumb show SR-0xx` lists them), and `plumb validate`, `plumb drift` and `plumb claims
   check` are clean.
3. The owner installs and adopts with slash commands only: the README's "Using plumb" says
   `/plugin marketplace add`, `/plugin install plumb@plumb` and `/plumb init`, and nothing
   else.
4. The single full run passed (or its failures were triaged and fixed with focused runs, and
   the run is recorded as the batch's evidence).
5. Every SP7 record stays proposed: the owner confirms them himself, by "ok" or by pressing
   Confirm once the plugin is installed. Before they are offered, `record_gaps` finds
   nothing in their owner-facing fields (spec 6.5); they were reworded to the owner's level
   in the spec review of 2026-10-07.
