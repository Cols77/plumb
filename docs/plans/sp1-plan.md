# Sub-project 1 implementation plan

Implements `docs/specs/sp1-grounding-loop.md` (the spec). The owner does not review this plan;
verifier agents check it against the owner intent brief, rulings R1 to R7 and the spec. Section
numbers such as "spec 5.6" refer to the spec.

The plan follows the build order of concept section 11, slice 1a: plumb is used on plumb as
early as possible. The owner asked to "dogfood the version to itself as soon as possible and
build with it" (D6) and to have the implementation "by tomorrow morning (in 9 hours)" (D11).
So dogfooding is not a last phase here. It starts while the lanes start, and it grows at a
checkpoint each time a lane's must items merge (section 4).

## 1. Shape of the work

| Phase | What | Who | Agent time | Gate before the next phase |
|---|---|---|---|---|
| 0. Contracts | Package skeleton, frozen contracts, shared primitives (including the hash-chained log), fakes, dispatcher | coordinator, on `main` | 55 min | `uv run pytest -q` and `uv run ruff check src tests` pass; contract tests green; committed with an `SR:` trailer |
| 1. Lanes and dogfood checkpoints | CORE, TRUST, VERIFY, HOST in parallel, each in its own worktree. Each lane hands over a merge-ready commit at each of its merge points; the coordinator merges it into `main` at once and runs every dogfood checkpoint (D0 to D3, section 4) that the merge unlocks | four lane agents; coordinator | 3 h per lane; must items 150 min or less | lane gate (3.3) on each merge point; whole suite and ruff green on `main` after each merge; each checkpoint's gate (4.3) |
| 2. Integration | Merge the lanes' remaining 1b and stretch work, end-to-end and conformance tests, hook benchmark | coordinator | 45 min | whole suite and ruff green on `main`; benchmark recorded |
| 3. Dogfood completion | Finish plumb's links to the code and tests that landed after D3, the first full run, the benchmark on plumb's own repository | coordinator | 30 min | dogfood checks (4.4) pass |
| 4. Review | One review agent per lane diff plus one intent verifier, all on the dogfooded `main` | review agents; fixes by coordinator | 30 min | no HIGH finding open; medium and low in `docs/followups.md` |

Wall-clock schedule (elapsed time from the start of phase 0):

| Time | Event |
|---|---|
| 0:00 to 0:55 | Phase 0. Its commit is the first to carry an `SR:` trailer (IDs from 4.2) |
| 0:55 | Lanes start |
| about 1:00 to 1:40 | D0: the coordinator writes plumb's own records by hand under `.plumb/` |
| about 2:40 | TRUST merge point T4 merged (trailer check, approvals with the guard, merge boundary) |
| about 3:15 | CORE C1 to C7 merged; D1 runs: `plumb init`, plumb's records validated and pinned, `commit-msg` check on |
| about 3:30 to 3:55 | CORE C8 and the HOST merge points merged; D2 installs each hook in plumb's repository as it lands |
| about 3:55 | VERIFY must items merged; D3 builds plumb's test map |
| 3:55 to 4:40 | Phase 2 |
| 4:40 to 5:10 | Phase 3 |
| 5:10 to 5:40 | Phase 4 |

That leaves about 3 h 20 min of slack inside the 9 hours. Section 12 says what the slack
protects and what is dropped first.

Orchestration uses the host's native mechanism: in Claude Code, the `Workflow` tool. Phase 0
is one `agent()` step. Phase 1 is a `parallel()` of four lane pipelines plus the D0 step;
each lane pipeline is a sequence of segment `agent()` calls, one per merge point, and after
each segment the script runs a merge step on `main`. Merge steps run one at a time (one
`main` checkout), and each ends by running the checkpoints its merge unlocks. Phases 2 to 4
follow, each carrying its gate. Starting that workflow needs the owner's opt-in where Claude
Code asks for it; this plan does not grant it.

## 2. Conventions for every agent

- Repository `C:/coding/plumb`. Lanes work in worktrees `C:/coding/plumb-wt/sp1-<lane>` on
  branches `sp1/<lane>`, created from `main` after phase 0
  (`git -C C:/coding/plumb worktree add C:/coding/plumb-wt/sp1-core -b sp1/core main`), then
  `uv sync` inside the worktree. Lanes: `core`, `trust`, `verify`, `host`.
- Never write inside `C:/coding/pi-agent-factory` or its worktrees, never create worktrees of
  it, never run its `coherence` or `factory` commands. Read its files only. Copying a source
  file's content into plumb is reading.
- Test first: write the failing test, run it red, implement, run it green. Run focused tests
  while iterating (`uv run pytest tests/core/test_links.py -q`) and the lane's whole set once
  before each commit. No `-n` above 2; plumb's suite needs none.
- Do not kill processes you did not start. `plumb tests run` terminates only the pytest
  process it started.
- Commit in small steps with clear messages (`core: pin both link ends`), each ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **`SR:` trailers from the first commit.** From phase 0 on, every commit carries an `SR:`
  trailer naming the plumb requirements it serves, taken from the `SR` column of the task
  tables and from the requirement table in 4.2 (`SR: SR-003, SR-004`). The IDs are fixed
  by this plan, so a trailer is valid before the record files exist. The `commit-msg` hook
  enforces it from checkpoint D1 on. The hook lives in the shared git directory, so it also
  runs in the lane worktrees: in a worktree whose branch has no `.plumb/` yet, it passes with
  a notice (spec 5.9), and every merge commit the coordinator makes on `main` is checked.
  After D1, each lane runs `git rebase main` at its next merge point (conflict-free: `.plumb/`,
  `.claude/` and `CLAUDE.md` change only on `main`), so its later commits are checked too.
- **No agent writes an approval.** No agent runs `plumb approve`, `plumb revoke` or
  `plumb relay` on plumb's own records in sub-project 1: no owner prompt in these sessions
  affirmed them (R2). Every plumb record stays proposed for the owner's morning confirmation.
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
| Phase 0 (frozen after) | `pyproject.toml`, `uv.lock`, `src/plumb/__init__.py`, `src/plumb/__main__.py`, `src/plumb/cli.py`, `src/plumb/cliutil.py`, `src/plumb/contracts.py`, `src/plumb/paths.py`, `src/plumb/normalize.py`, `src/plumb/config.py`, `src/plumb/text.py`, `src/plumb/log.py`, `tests/conftest.py`, `tests/fakes.py`, `tests/contracts/**`, `tests/test_smoke.py` |
| CORE | `src/plumb/model.py`, `store.py`, `hashing.py`, `links.py`, `confirm.py` (derived confirmation and covered state), `validate.py`, `query.py` (relevant, brief, why), `api.py`, `commands.py`; `tests/core/**` |
| TRUST | `src/plumb/claims.py` (trailers, `commit-msg` hook installer, claims check), `approvals.py`, `merge.py`, `trust_cli.py`; `src/plumb/judgment/**` (`__init__.py`, `model.py`, `heuristic.py`, `tiers.py`, `cascade.py`, `fidelity.py`, `jev.py`, `state.py`, `cli.py`); `src/plumb/importer/**` (`__init__.py`, `pi_factory.py`, `cli.py`); `tests/trust/**` including `tests/trust/fixtures/pi_factory/**` |
| VERIFY | `src/plumb/verify/**` (`__init__.py`, `imports.py`, `markers.py`, `testmap.py`, `select.py`, `pytest_plugin.py`, `runner.py`, `evidence.py`, `policy.py`, `envid.py`, `cli.py`); `tests/verify/**` |
| HOST | `src/plumb/hosts/__init__.py`, `src/plumb/hosts/claude_code/**` (`__init__.py`, `cli.py`, `hookio.py`, `session_start.py`, `prompt.py`, `post_edit.py`, `stop.py`, `snapshot.py`, `statusline.py`, `install.py`, `templates/SKILL.md`, `templates/plumb-command.md`, `templates/claude-md-block.md`); `tests/host/**` |
| Dogfood (coordinator, D0 to D3 and phase 3) | `.plumb/**`, `.claude/**`, `CLAUDE.md`, `README.md` (usage section); the untracked `.git/hooks/commit-msg` |
| Phase 2 | `tests/integration/**`, `scripts/bench_hooks.py` |
| Any lane, append only | `docs/followups.md` (own heading) |

`src/plumb/hosts/claude_code/templates/*` are package data; phase 0 makes `uv_build` include
them (they sit inside the package).

### 3.2 Contracts

Spec section 12 is the contract: `contracts.py` (12.1), the factory functions (12.2), the
dispatcher (12.3), the shared primitives including `log.py` (12.4) and the file formats
(12.5). A lane needing a contract change stops that item, asks the coordinator, and works on
its next item. The coordinator changes the contract on `main`, updates spec section 12 in the
same commit, and tells every lane to rebase.

Lanes never import each other's modules in unit tests. They use `tests/fakes.py` and the
phase-0 primitives. Calls across lanes at run time go only through the factory functions of
spec 12.2, imported inside the function that needs them, so a missing lane degrades instead
of failing at import.

### 3.3 Lane gate

Run inside the lane worktree at each merge point and before handing back:

```
uv run pytest tests/<lane> tests/contracts tests/test_smoke.py -q
uv run ruff check src tests
git diff --name-only main...HEAD   # every path must be in the lane's row of 3.1, or docs/followups.md
```

The lane then reports `merge-ready <lane> <merge point> <commit sha>` and goes on with its
next item. The coordinator merges that commit (`git merge --no-ff <sha>`, message with the
`SR:` trailer of the merged items), runs `uv run pytest -q` and `uv run ruff check src tests`
on `main`, and runs the checkpoints the merge unlocks (4.1).

## 4. Dogfooding: checkpoints from the first hour

### 4.1 Checkpoints

| Checkpoint | Runs when | Steps (coordinator, on `main`) |
|---|---|---|
| D0. Own records | Right after phase 0, in parallel with the lanes (needs no lane) | Write plumb's records of 4.2 by hand as Markdown with frontmatter (spec 5.2) under `.plumb/intents/`, `requirements/`, `decisions/`, `features/`: quotes verbatim from the brief, read-backs in the owner's terms, requirements with given/when/then examples, `derives_from` and `decides` links without pins. Commit `dogfood: plumb's own intent records` with `SR: SR-001` |
| D1. Records checked, trailers enforced | CORE merge point C7 and TRUST merge point T4 are both on `main` (concept 11, 1a steps 1 to 4) | `uv run plumb init` (idempotent; adds `config.yaml`, `claims.yaml`, `.gitignore`, `.gitattributes`, empty logs around the D0 records); set `verify.infra_globs` to add `src/plumb/verify/pytest_plugin.py`; `uv run plumb repin <ID>` on every record to pin its links; add `implemented_by` and `verified_by` links (whole files) for the modules and test files already on `main`; `uv run plumb validate` (no errors); `uv run plumb trailers install-hook`; set `require_trailer: true` in `.plumb/claims.yaml`; `uv run plumb validate --merge <phase-0 commit>` (exits 4, listing the records awaiting the owner); commit with `SR: SR-001, SR-003, SR-007` through the new hook |
| D2. Hooks installed as they land | Each HOST merge point (H6, H7, H8), once D1 and CORE merge point C8 are on `main` | `uv run plumb hooks install --launcher venv` after each merge: the installer registers only the hooks whose modules are present (section 10, H6), so session start, edit tracking and the status line are installed at H6, the prompt hook at H7 and the stop hook at H8. Add the links for the new modules and tests; `uv run plumb validate`; commit with `SR: SR-015` plus the hook's SR |
| D3. Map and covering tests | VERIFY merge point V8 is on `main` | `uv run plumb tests map`; add the `verified_by` links still missing for files on `main`; `uv run plumb tests select --changed` as a sanity run; commit with `SR: SR-016, SR-017` |

From D1 on, plumb's `commit-msg` hook checks every commit and merge on `main`. From D2 on,
the Claude Code sessions opened on `C:/coding/plumb` run plumb's own hooks, so the
integration, dogfood completion and review fixes are made with plumb in the loop. If a hook
misbehaves before `plumb hooks uninstall` lands (HOST 1b), `git revert` of the install commit
removes it; the failure is recorded in `docs/followups.md`.

A checkpoint whose condition is not met by the 3-hour lane mark waits for the morning-minimum
rule of section 12; it is never skipped.

### 4.2 Records

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
`derives_from` link, and `implemented_by` and `verified_by` links added at the checkpoint
where the files reach `main`):

| ID | Feature | Statement (short) | Derives from | Verified by (lane tests) |
|---|---|---|---|---|
| SR-001 | FEAT-001 | Records are Markdown with frontmatter under `.plumb/`, identified by frontmatter ID | INT-006, INT-010 | `tests/core/test_model.py`, `test_store.py` |
| SR-002 | FEAT-001 | Record hashes ignore formatting and change with meaning | INT-006 | `tests/core/test_hashing.py`, `tests/contracts/test_normalize.py` |
| SR-003 | FEAT-001 | Links pin both ends; either end moving makes the link stale; dangling links are errors | INT-006 | `tests/core/test_links.py`, `test_validate.py` |
| SR-004 | FEAT-001 | Approvals pin exact content; an edit leaves the record unconfirmed | INT-006 | `tests/core/test_confirmation.py`, `tests/trust/test_approvals.py` |
| SR-005 | FEAT-001 | Only the owner's explicit words confirm: owner command or quote-checked relay; the marker refuses self-approval | INT-004, INT-006 | `tests/trust/test_approvals.py`, `tests/host/test_install.py` |
| SR-006 | FEAT-001 | Logs are append-only and hash-chained; tampering is reported | INT-006 | `tests/contracts/test_log.py`, `tests/core/test_validate.py` |
| SR-007 | FEAT-001 | `SR:` trailers are checked at commit and claims compare claimed with declared paths | INT-006, INT-010 | `tests/trust/test_claims.py` |
| SR-008 | FEAT-001 | The merge boundary refuses unconfirmed touched requirements and lists approvals in the range | INT-004 | `tests/trust/test_merge.py` |
| SR-009 | FEAT-002 | The session brief is about 30 lines of context, not procedure | INT-002, INT-008 | `tests/core/test_query.py`, `tests/host/test_session_start.py` |
| SR-010 | FEAT-002 | Each prompt receives the relevant records, their tests and an intent-change flag | INT-002, INT-004 | `tests/host/test_prompt.py`, `tests/trust/test_heuristic.py` |
| SR-011 | FEAT-002 | Edits are tracked without blocking | INT-003 | `tests/host/test_post_edit.py` |
| SR-012 | FEAT-002 | The end-of-turn summary is short, shows proposed records, and asks only on the three triggers | INT-008 | `tests/host/test_stop.py` |
| SR-013 | FEAT-002 | The status line reads state and recomputes nothing | INT-008 | `tests/host/test_statusline.py` |
| SR-014 | FEAT-002 | Hooks stay within their budgets and never block work on plumb's own failure | INT-002, INT-003 | `tests/host/test_hookio.py`, `test_latency.py`, `tests/integration/test_latency_subprocess.py` |
| SR-015 | FEAT-002 | The installer writes hooks, status line, marker, deny rules, skill, slash command and commit hook, idempotently | INT-007, INT-009 | `tests/host/test_install.py`, `tests/trust/test_claims.py` |
| SR-016 | FEAT-003 | The test map is grep-able text built from links, markers, imports and naming | INT-002 | `tests/verify/test_testmap.py` |
| SR-017 | FEAT-003 | Covering-test selection: docs select nothing, infrastructure sets full pending, unknown coverage samples, a budget caps the turn | INT-002, INT-003 | `tests/verify/test_select.py` |
| SR-018 | FEAT-003 | Evidence is pinned to tree, closure, test source and environment identity, and reused only on an exact match | INT-006 | `tests/verify/test_evidence.py`, `test_envid.py`, `test_runner.py` |
| SR-019 | FEAT-003 | A failure that passes on a same-tree rerun is recorded as flaky with both attempts | INT-006 | `tests/verify/test_policy.py` |
| SR-020 | FEAT-003 | A regression is a previously passing test with unchanged source that now fails; a new red test never interrupts | INT-008 | `tests/verify/test_policy.py`, `tests/host/test_stop.py` |
| SR-021 | FEAT-004 | Judgment is optional: heuristic by default, JEV when a key exists, fallback on failure, advisory only | INT-011 | `tests/trust/test_heuristic.py`, `test_jev.py`, `test_tiers.py` |
| SR-022 | FEAT-004 | Fidelity packets let the host agent judge a requirement without JEV | INT-011, INT-004 | `tests/trust/test_fidelity.py` |
| SR-023 | FEAT-004 | The importer reads pi-agent-factory records read-only and never manufactures a confirmation | INT-005, INT-010 | `tests/trust/test_import_*.py` |
| SR-024 | FEAT-004 | The cascade hands low-confidence judgments to the host agent through an interface | INT-011 | `tests/trust/test_cascade.py` |

Decisions: `DEC-001` to `DEC-013` for spec refinements F1 to F13, each with `question`,
`chosen`, `alternatives` (the concept's mechanism), `rationale`, a `decides` link to the SR it
shapes, and `matters: true` for F2 (guard by deny rules), F4 (prompt digests committed when
cited) and F6 (tests run in the agent's turn), `matters: false` for the others.

A requirement whose module is a stretch item that is not built (for example SR-023 without
the importer) stays a proposed record with no `implemented_by` link; `plumb validate` warns
about it and the handoff lists it.

### 4.3 Checkpoint gates

- D0: every record file parses as YAML frontmatter with the fields of spec 5.2 (checked with
  a one-off `python -c` YAML load, since CORE is not merged yet); IDs match 4.2.
- D1: `plumb validate` reports no errors; `plumb trailers check-msg` rejects a message naming
  `SR-999` and accepts one naming `SR-001`; `validate --merge <phase-0 commit>` exits 4.
- D2: `.claude/settings.json` holds the hooks installed so far, the status line, the marker
  and the deny rules; one manual `uv run plumb hook session-start` (and, once installed,
  `hook prompt` and `hook stop`) on plumb's repository exits 0 within its budget.
- D3: `plumb tests map` lists every SR whose test files are on `main`.

### 4.4 Dogfood checks (phase 3 gate)

Phase 3 steps: add the links for the code and tests merged in phase 2; replace whole-file
`verified_by` links with test-node links if CORE's test-node hashing (C10) landed; `uv run
plumb tests map`; `uv run plumb tests run --full` once, so `full verification pending` starts
satisfied (this is the owner's merge boundary for sub-project 1, not a per-turn run);
`uv run python scripts/bench_hooks.py` on plumb's repository; commit with `SR:` trailers.

Checks:

- `plumb validate`: no errors.
- `plumb tests map` lists every `SR-0xx` whose module was built with at least one test.
- `.claude/settings.json` holds the four hooks, the status line, the marker and the deny rules;
  `.claude/skills/plumb/SKILL.md` and `.claude/commands/plumb.md` exist; the `commit-msg`
  hook rejects a message with an unknown SR ID (try it with `plumb trailers check-msg`).
- Every commit since phase 0 carries an `SR:` trailer, and `plumb claims check` reports no
  undeclared path (or records each one in `docs/followups.md`).
- `scripts/bench_hooks.py` on plumb's own repository: prompt + stop p95 under 1.5 s.
- `plumb validate --merge <phase-0 commit>` exits 4 and lists every record awaiting the owner's
  confirmation: the expected morning question. The handoff tells the owner the one line that
  confirms everything they agree with: `plumb approve --proposed` in their own terminal, or
  "ok" in a session (relayed with the quote check).

## 5. Phase 0: contracts (coordinator, on `main`)

| # | Task | SR | Tests (written first) |
|---|---|---|---|
| P0.1 | `pyproject.toml`: add `pyyaml>=6` to dependencies; register the `sr` marker (`markers = ["sr(id): links a test to a plumb requirement"]`); `uv lock`; `uv sync` | SR-001 | `tests/test_smoke.py` still green |
| P0.2 | `src/plumb/contracts.py` exactly as spec 12.1 | SR-001 | `tests/contracts/test_shapes.py`: `test_dataclasses_are_frozen`, `test_link_id_format`, `test_id_regex_accepts_and_rejects`, `test_kind_tables_cover_every_kind` |
| P0.3 | `src/plumb/normalize.py` (spec 12.4) | SR-002 | `tests/contracts/test_normalize.py`: `test_crlf_and_lone_cr_become_lf`, `test_trailing_whitespace_and_blank_lines_dropped`, `test_nfc_normalization`, `test_derived_blocks_removed`, `test_canonical_json_sorted_compact_utf8`, `test_file_digest_binary_uses_raw_bytes` |
| P0.4 | `src/plumb/paths.py`, `src/plumb/config.py`, `src/plumb/text.py` (spec 12.4, 11) | SR-001 | `tests/contracts/test_primitives.py`: `test_find_root_prefers_plumb_dir`, `test_config_defaults_without_file`, `test_config_reads_yaml_and_caches_json`, `test_config_cache_invalidated_on_change`, `test_terms_and_overlap` |
| P0.5 | `src/plumb/log.py` (spec 5.7, 12.4): JSONL append with lock, `prev` and `digest`, read from an offset, chain verification. It is a frozen primitive because every lane writes through it (CoreAPI `log_append` delegates to it) | SR-006 | `tests/contracts/test_log.py`: `test_append_chains_prev_digest`, `test_digest_detects_modified_line`, `test_missing_prev_detected`, `test_union_merged_fork_accepted`, `test_concurrent_appends_do_not_interleave`, `test_read_since_offset`, `test_marker_recorded` |
| P0.6 | `src/plumb/cli.py` dispatcher and `cliutil.py` (spec 12.3); keep `--version` and help; help lists every routed command | SR-014 | `tests/contracts/test_dispatcher.py`: `test_every_route_names_a_module_path`, `test_unknown_command_exits_2`, `test_missing_module_reports_not_available`, `test_hook_route_does_not_import_argparse_commands_of_other_lanes` |
| P0.7 | `tests/fakes.py` and `tests/conftest.py` (spec 12.4); `FakeCore` logs through the real `log.py` | SR-001 | `tests/contracts/test_conformance.py`: protocol conformance suite parametrized over available implementations (fakes now): `test_core_index_and_status_shapes`, `test_core_log_append_read_round_trip`, `test_core_write_record_and_add_link`, `test_verify_select_and_evidence_shapes`, `test_backend_returns_judgments` |
| P0.8 | Add the spec and plan links to `README.md`; `.gitignore` unchanged (plumb's own `.plumb/.gitignore` comes from `plumb init`) | none | none |
| P0.9 | Commit `chore: freeze SP1 contracts, primitives and dispatcher` with `SR: SR-001, SR-002, SR-006, SR-014`; create the four worktrees | | gate of section 1 |

## 6. Lane tiers and estimates

Each lane's tasks are in build order and carry a tier:

- **M** (must, 1a): the morning minimum. Each lane's M items add up to 150 min or less, which
  leaves at least 30 min of its 3 hours for red/green cycles and the lane gate. M items are
  never dropped (section 12).
- **1b**: the rest of sub-project 1 (concept 11, 1b), built after the lane's M items, dropped
  from the end of the list first.
- **S** (stretch): built only with time left, dropped before any 1b item.

| Lane | M | 1b | S | Merge points |
|---|---|---|---|---|
| CORE | 150 min (C1 to C8) | 30 min | none | after C7 (unlocks D1 with TRUST), after C8 (unlocks D2), at the end |
| TRUST | 130 min (T1 to T6) | 55 min | 90 min | after T4 (unlocks D1 with CORE), after T6, at the end |
| HOST | 150 min (H1 to H8) | 15 min | 10 min | after H6, after H7, after H8 (each unlocks D2 for the hooks it adds), at the end |
| VERIFY | 150 min (V1 to V8) | 45 min | 10 min | after V8 (unlocks D3), at the end |

## 7. Lane CORE

Goal: the record model, hashing, links and staleness, derived confirmation, validation, the
query functions the hooks use, the CORE commands and `plumb.api.open_core`. Extraction
sources: spec 13 (`register.py`, `relations.py`, `fingerprint.py`).

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| C1 | `model.py`: frontmatter split and parse into `Record` (all five kinds, examples, AC examples, links, wikilinks); ID validation | M | SR-001 | 20 min |
| C2 | `hashing.py`: record hash (spec 5.4); whole-file end hash with `(size, mtime_ns)` cache | M | SR-002 | 15 min |
| C3 | `store.py`: index load with `.plumb/cache/index.json`; next ID; `write_record` (YAML dump with stable key order); duplicate detection | M | SR-001 | 20 min |
| C4 | `links.py`: target parsing (`ID`, `path`, `path::Qual.name`, `path::test`), allowed-kind matrix, `add_link` with pins, `link_states`, `repin` (also pins unpinned links) | M | SR-003 | 25 min |
| C5 | `confirm.py`: derived confirmation from `approval` and `revocation` events against current hashes, covered state; `validate.py`: errors and warnings of spec 5.10, approval re-checks, log chain check through `log.py` | M | SR-003, SR-004, SR-006 | 25 min |
| C6 | `api.py`: `open_core` (CoreAPI: index, status, link_states, records_for_paths, hash_target for whole files, write_record, add_link, log_append and log_read through `log.py`) | M | SR-001 | 10 min |
| C7 | `commands.py`: `init`, `new`, `show`, `link`, `repin`, `validate` (`--merge` calls TRUST's `merge_check` lazily, else prints `merge boundary: unavailable` and exits 2), `status` | M | SR-001, SR-003 | 20 min |
| C8 | `query.py`: `relevant`, `brief_lines` (30-line cap); wired into `open_core` | M | SR-009, SR-010 | 15 min |
| C9 | `commands.py`: `drift`, `brief`, `why`, `log` | 1b | SR-003, SR-009 | 15 min |
| C10 | `hashing.py`: symbol and test-node end hashes with `ast` | 1b | SR-002, SR-003 | 15 min |

Merge points: after C7 (D1), after C8 (D2), at the end.

Tests (`tests/core/`), each written red first:

- `test_model.py`: `test_parses_each_kind_from_frontmatter`,
  `test_identity_comes_from_frontmatter_not_filename`, `test_rejects_malformed_id`,
  `test_requirement_examples_parsed_with_ids`, `test_imported_acceptance_examples_keep_ac_ids`,
  `test_wikilinks_extracted_from_body`
- `test_hashing.py`: `test_record_hash_ignores_yaml_style_and_key_order`,
  `test_record_hash_ignores_links_field`,
  `test_record_hash_ignores_crlf_trailing_space_and_derived_blocks`,
  `test_record_hash_changes_on_statement_edit`, `test_file_end_hash_ignores_crlf`,
  `test_hash_cache_reuses_unchanged_files`; 1b C10: `test_symbol_end_ignores_edits_elsewhere`,
  `test_test_end_drops_parametrize_ids`, `test_missing_symbol_is_dangling`
- `test_store.py`: `test_new_assigns_next_id_per_kind`, `test_nc_ids_have_four_digits`,
  `test_write_record_round_trips`, `test_index_cache_reparses_only_changed_files`,
  `test_duplicate_ids_reported`
- `test_links.py`: `test_add_link_pins_both_ends`, `test_pin_drift`, `test_crlf_is_not_drift`,
  `test_source_edit_marks_source_moved`, `test_dangling_record_and_path`,
  `test_unpinned_link_warns`, `test_link_kind_allowed_matrix`,
  `test_repin_refreshes_pins_and_logs_event`, `test_repin_pins_unpinned_links`,
  `test_repin_does_not_confirm`
- `test_confirmation.py`: `test_proposed_until_approved`,
  `test_approval_event_at_current_hash_confirms`, `test_edit_after_approval_is_unconfirmed_edit`,
  `test_revocation_returns_to_proposed`, `test_covered_requires_verified_by_per_example`
- `test_validate.py`: `test_clean_repo_passes`, `test_errors_exit_one`,
  `test_warnings_for_stale_unconfirmed_uncovered`, `test_sr_without_derives_from_warns`,
  `test_untranslated_intent_items_warn`, `test_matters_false_deciding_confirmed_record_warns`,
  `test_owner_approval_under_marker_is_error`, `test_relayed_approval_without_prompt_event_is_error`,
  `test_tampered_log_line_is_error`
- `test_query.py`: `test_relevant_ranks_named_ids_first`, `test_brief_respects_line_cap`,
  `test_superseded_records_excluded_from_brief_and_relevant`
- `test_cli_core.py`: `test_init_is_idempotent_and_writes_ignore_and_attributes`,
  `test_new_show_round_trip_json`, `test_link_cli_target_forms`, `test_status_json_counts`,
  `test_validate_merge_delegates_or_reports_unavailable`; 1b C9: `test_drift_lists_moved_end`,
  `test_brief_cli_respects_max_lines`, `test_why_walks_to_intent_quotes`, `test_log_reads_streams`

## 8. Lane TRUST

Goal, in this order: the `SR:` trailer check and its `commit-msg` hook, owner approvals and
agent-relayed approvals with the guard, the merge boundary (R1), the judgment interface with
its heuristic default; then fidelity packets, the claims check and the cascade; then, with
time left, the read-only importer and the JEV adapter. Extraction sources: spec 13
(`claims.py`, `substrate/judgment/*`, `register.py`). TRUST uses `FakeCore` for records,
hashes and status, and the real phase-0 `log.py` for events.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| T1 | `claims.py`: `parse_sr_trailer`, `check_msg` (unknown or malformed ID rejected; `require_trailer`; passes with a notice without `.plumb/`), `install_commit_msg_hook` (spec 12.2; leaves a foreign hook untouched and reports it); `trust_cli.py`: `trailers check-msg`, `trailers install-hook` | M | SR-007, SR-015 | 20 min |
| T2 | `approvals.py`: `approve` (marker refusal, `--proposed`, `--yes`), `revoke`, `relay` with the four checks, `prompt` event copy before the approval | M | SR-004, SR-005 | 30 min |
| T3 | `merge.py`: `merge_check` (spec 5.11): touched requirements must be confirmed (exit 4), approvals in the range, log integrity against the base; fidelity and verification lines print `unavailable` until their providers exist | M | SR-008 | 25 min |
| T4 | `trust_cli.py`: `approve`, `relay`, `revoke` | M | SR-005 | 10 min |
| T5 | `judgment/model.py`, `tiers.py`: questions, answers, sealed records, fingerprint, `route` with version drift (extracted) | M | SR-021 | 20 min |
| T6 | `judgment/heuristic.py`, `get_backend` with `heuristic`, `disabled`, `fake`; `judgment/cli.py`: `judgment status` | M | SR-010, SR-021 | 25 min |
| T7 | `judgment/fidelity.py` and `cli.py`: `build_packet`, `unjudged`, `plumb fidelity`, `plumb judge`; `merge_check` lists unjudged fidelity | 1b | SR-022 | 25 min |
| T8 | `claims.py`: `claims check` over a range, `claims.yaml` exempt globs and baseline | 1b | SR-007 | 20 min |
| T9 | `judgment/cascade.py`: `HostAgentCascade` (queues to `escalations.jsonl`), `get_cascade` | 1b | SR-024 | 10 min |
| T10 | `importer/pi_factory.py`: SR, FEAT plus bundle, NC mapping, findings, dry run, `import` event; `importer/cli.py` | S | SR-023 | 40 min |
| T11 | `judgment/state.py`, `jev.py`: tracked-files state with secret exclusion and truncation (extracted); `urllib` client with the pinned wire shapes, timeouts, fallback with one notice | S | SR-021 | 35 min |
| T12 | Precision fixture for the intent-change heuristic (20 labelled prompts), result recorded in `docs/followups.md` | S | SR-010 | 15 min |

Merge points: after T4 (D1), after T6, at the end. T10 fixtures: copies of
`requirements/SR-077.md` (structured bindings, acceptance), one SR with a `checksum:` field,
`docs/features/FEAT-001.md`, `bundles/FEAT-001.json` and `docs/nonconformances/NC-0002-*.md`
from `C:/coding/pi-agent-factory`, read once and saved under
`tests/trust/fixtures/pi_factory/`.

Tests (`tests/trust/`):

- `test_claims.py`: `test_parse_sr_trailer_variants`, `test_check_msg_rejects_unknown_id`,
  `test_check_msg_requires_trailer_when_configured`, `test_check_msg_passes_without_plumb_dir`,
  `test_install_hook_writes_and_leaves_foreign_hook`, `test_install_hook_uses_installing_interpreter`;
  1b T8: `test_claims_reports_undeclared_paths`, `test_claims_default_exempt_globs`,
  `test_claims_baseline_entries`
- `test_approvals.py`: `test_approve_refused_under_marker`, `test_approve_pins_current_hash`,
  `test_approve_proposed_pins_all_listed`, `test_revoke_writes_revocation`,
  `test_relay_accepts_affirming_quote_from_logged_prompt`,
  `test_relay_rejects_quote_not_in_prompt`, `test_relay_rejects_quote_without_affirmation`,
  `test_relay_rejects_record_outside_stated_set_unless_named`,
  `test_relay_writes_prompt_event_before_approval`, `test_relay_accepts_unique_digest_prefix`,
  `test_no_approval_from_non_affirming_prompt`
- `test_merge.py`: `test_merge_refuses_unconfirmed_touched_requirement`,
  `test_merge_touch_via_implemented_by_end`, `test_merge_touch_via_sr_trailer`,
  `test_merge_passes_after_approval`, `test_merge_lists_approvals_in_range`,
  `test_merge_requires_deciding_matters_dec`, `test_merge_detects_rewritten_log_line`,
  `test_merge_reports_fidelity_and_verification_unavailable`; 1b T7:
  `test_merge_lists_unjudged_fidelity`
- `test_cli_trust.py`: `test_approve_relay_revoke_exit_codes`,
  `test_trailers_check_msg_and_install_hook_cli`, `test_judgment_status_never_prints_key`
- `test_tiers.py`: `test_route_thresholds`, `test_version_drift_suspends_accept`,
  `test_record_digest_detects_mutation`
- `test_heuristic.py`: `test_intent_change_flags_change_words_on_confirmed_match`,
  `test_no_flag_without_overlap`, `test_drift_triage_cosmetic_for_comment_only_change`,
  `test_drift_triage_material_for_logic_change`, `test_fidelity_is_unsure_escalate_llm`,
  `test_disabled_backend_is_unsure`; stretch T12: `test_intent_change_precision_fixture`
- 1b T7 `test_fidelity.py`: `test_packet_contains_statement_examples_ends_evidence`,
  `test_packet_truncates_deterministically`, `test_judge_appends_event_with_hashes`,
  `test_unjudged_after_end_change`, `test_judgment_never_confirms_or_freshens`
- 1b T9 `test_cascade.py`: `test_host_agent_cascade_queues_instruction`,
  `test_escalate_human_only_with_trigger`
- stretch T10 `test_import_sr.py`: `test_imports_sr_fields_and_ac_examples`,
  `test_structured_bindings_become_links_pinned_when_ends_exist`,
  `test_missing_ends_reported_as_findings`, `test_legacy_checksum_verified_and_reported`,
  `test_all_imported_records_are_proposed`; `test_import_feat_nc.py`:
  `test_feature_membership_is_union_of_feat_and_bundle`, `test_membership_differences_reported`,
  `test_nc_read_leniently_keeps_corrected_by`, `test_id_collision_skipped_with_finding`;
  `test_import_readonly.py`: `test_source_tree_unchanged_after_import`,
  `test_dry_run_writes_nothing`, `test_import_event_logged`
- stretch T11 `test_jev.py` (local stub `http.server` on 127.0.0.1, no network):
  `test_request_shape_matches_pinned_wire_format`, `test_parses_noul_choice_score_answers`,
  `test_timeout_falls_back_to_heuristic_with_one_notice`, `test_missing_key_uses_heuristic`,
  `test_key_never_read_from_repository`, `test_state_excludes_secret_paths_and_truncates`,
  `test_judgment_event_logged_with_fingerprint`

## 9. Lane VERIFY

Goal: the test map, covering-test selection, the pytest runner with evidence pinned to the
code and the cheap environment key, the regression rule, `plumb tests` and
`plumb.verify.open_verify` (concept 11, 1a step 6); then the full environment identity, the
flaky rerun and `plumb impact` (1b). Extraction sources: spec 13 (`imports.py`, `markers.py`,
`failure_policy.py`, `pytest_evidence_plugin.py`, `evidence.py`). The lane uses `FakeCore` for
records and links and the real `log.py`; its runner tests use small temporary pytest projects.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| V1 | `imports.py`: import edges and transitive closure over `source_dirs` (extracted) | M | SR-016 | 20 min |
| V2 | `markers.py`: `sr` marker collection (extracted) | M | SR-016 | 10 min |
| V3 | `testmap.py`: map from `verified_by`, markers and the import closure; fingerprint cache; `test_map.txt` writer | M | SR-016 | 20 min |
| V4 | `select.py`: priority order, doc-only, infra globs, unknown-coverage sample, budget and deferral, derived `full_pending` | M | SR-017 | 30 min |
| V5 | `pytest_plugin.py`: per-phase outcomes, collection errors, exit status, JSON report to `PLUMB_REPORT` (extracted) | M | SR-018 | 15 min |
| V6 | `envid.py`: cheap `env_key` | M | SR-018 | 5 min |
| V7 | `runner.py`, `evidence.py`, `policy.py` (regression rule only): run selection, hard limit, inputs-changed discard, `test-run` entry, freshness on closure, test hash and `env_key` (spec 7.4), reuse index by offset, regression rule (R3, spec F10) | M | SR-018, SR-020 | 35 min |
| V8 | `__init__.py` `open_verify`; `cli.py`: `tests map|select|run`, aliases `map` and `verify` | M | SR-016, SR-017 | 15 min |
| V9 | `envid.py`: content identity (extracted) cached under `env_key`; freshness then also requires it (spec 7.4) | 1b | SR-018 | 15 min |
| V10 | `policy.py`: same-tree flaky rerun | 1b | SR-019 | 15 min |
| V11 | `cli.py`: `impact` | 1b | SR-016 | 10 min |
| V12 | `testmap.py`: naming source | 1b | SR-016 | 5 min |
| V13 | `tests waive` (owner only, marker refusal, `waiver` event) | S | SR-019 | 10 min |

Merge points: after V8 (D3), at the end.

Tests (`tests/verify/`):

- `test_imports.py`: `test_import_edges_absolute_and_relative`, `test_transitive_closure`,
  `test_unresolvable_imports_ignored`
- `test_markers.py`: `test_collects_sr_markers_on_functions_and_classes`
- `test_testmap.py`: `test_map_from_verified_by_links`, `test_map_from_sr_markers`,
  `test_map_from_import_closure`, `test_map_text_is_grepable`,
  `test_map_cache_reparses_only_changed_files`; 1b V12: `test_map_from_naming`
- `test_select.py`: `test_doc_only_selects_nothing`,
  `test_priority_order_verified_by_literal_import`,
  `test_infra_change_sets_full_pending_and_adds_nothing`,
  `test_unknown_coverage_samples_nearest_bounded`, `test_budget_defers_overflow`,
  `test_unknown_duration_counts_one_second`, `test_full_pending_cleared_by_full_run_evidence`,
  `test_selection_never_contains_whole_suite_marker`
- `test_plugin.py`: `test_plugin_reports_phases_and_exit_status`,
  `test_setup_failure_outranks_pass`, `test_collection_error_reported`
- `test_envid.py`: `test_env_key_changes_with_lock_and_python`; 1b V9:
  `test_identity_none_without_pyvenv`, `test_identity_cached_under_env_key`
- `test_runner.py`: `test_run_appends_test_run_entry_with_tree_and_env`,
  `test_run_never_passes_n_by_default`, `test_hard_limit_terminates_own_child`,
  `test_run_discarded_when_inputs_change`
- `test_evidence.py`: `test_fresh_pass_requires_matching_closure_test_and_env_key`,
  `test_reuse_miss_names_differing_part`, `test_index_rebuilt_from_log_after_cache_delete`;
  1b V9: `test_unknown_identity_never_reused`
- `test_policy.py`: `test_regression_requires_prior_pass_and_same_test_hash`,
  `test_new_red_test_is_not_regression`, `test_run_prints_regression_instruction`; 1b V10:
  `test_flaky_rerun_same_tree_records_both_attempts`, `test_no_rerun_when_tree_changed`;
  stretch V13: `test_waiver_refused_under_marker`, `test_waiver_event_pinned_to_diff_digest`
- `test_cli_verify.py`: `test_tests_map_select_run_commands`, `test_aliases_map_and_verify`;
  1b V11: `test_impact_lists_records_and_tests`

Runner tests start real pytest subprocesses; keep each temporary project to two or three tiny
tests so the lane suite stays under about 60 s.

## 10. Lane HOST

Goal: the Claude Code adapter: the four hooks, the status line, the skill, the slash command,
the CLAUDE.md block and the installer. The build order puts the installer before the prompt
and stop hooks, so each hook can be installed in plumb's repository as soon as it lands
(concept 11, 1a step 5; D2). Uses `FakeCore`, `FakeVerify`, `FakeBackend` and `FakeCascade`;
hook tests feed stdin JSON built by the `hook_input` fixture.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| H1 | `hookio.py`: read stdin JSON, deadline, catch-all (exit 0, `check skipped` line, `errors.log`), output helpers (plain text, `systemMessage`, `decision: block`) | M | SR-014 | 15 min |
| H2 | `post_edit.py`: stdlib-only fast path appending to `touched.txt` | M | SR-011 | 10 min |
| H3 | `snapshot.py`: build `StatusSnapshot` from CoreAPI and VerifyAPI; write `status.json` | M | SR-013 | 15 min |
| H4 | `statusline.py` | M | SR-013 | 10 min |
| H5 | `session_start.py`: brief (about 30 lines, cap 40) plus evidence lines; writes the snapshot | M | SR-009 | 15 min |
| H6 | `install.py`: settings merge (registers only the hooks whose modules are present; async post-edit, statusLine, env marker, deny rules), launcher selection; skill, slash command, CLAUDE.md block; the `commit-msg` hook through TRUST's `install_commit_msg_hook` (degrades with a notice when missing); `cli.py` routes `hook`, `hooks install`, `install`, `statusline` | M | SR-015, SR-005 | 30 min |
| H7 | `prompt.py`: prompt log, relevant records with examples and tests (20 lines), intent-change flag and compare line, awaiting-confirmation line | M | SR-010 | 25 min |
| H8 | `stop.py`: changed paths, records and links, selection and evidence, `stated.json`, one block per turn (tests, trigger 2, trigger 3), summary with capped `proposed` lines | M | SR-012, SR-020 | 30 min |
| H9 | `install.py`: `hooks uninstall`, `hooks status` | 1b | SR-015 | 10 min |
| H10 | Queued escalations printed by the prompt and stop hooks | 1b | SR-024 | 5 min |
| H11 | Escalation hint in the prompt hook (spec 6.2 step 5) | S | SR-010 | 10 min |

Merge points: after H6, after H7, after H8 (each unlocks D2 for the hooks it adds), at the end.

Tests (`tests/host/`):

- `test_hookio.py`: `test_internal_error_exits_zero_with_notice`,
  `test_deadline_skips_with_budget_notice`, `test_block_output_shape`
- `test_post_edit.py`: `test_appends_repo_relative_path`, `test_ignores_paths_outside_repo`,
  `test_fast_path_imports_no_yaml` (subprocess, checks `sys.modules`)
- `test_statusline.py`: `test_renders_line_from_snapshot`,
  `test_full_pending_shown_only_when_pending`, `test_missing_snapshot`
- `test_session_start.py`: `test_brief_about_30_lines_with_cap`,
  `test_brief_lists_awaiting_confirmation_and_drift`, `test_writes_status_snapshot`
- `test_install.py`: `test_install_writes_hooks_statusline_env_and_deny_rules`,
  `test_install_registers_only_available_hooks`,
  `test_install_preserves_foreign_settings_and_is_idempotent`, `test_post_edit_registered_async`,
  `test_skill_about_20_lines_names_test_map_and_relay`, `test_slash_command_brief_why_impact`,
  `test_claude_md_block_idempotent`, `test_install_calls_commit_msg_installer_or_notes_missing`,
  `test_launcher_selection`; 1b H9: `test_uninstall_removes_only_plumb_entries`
- `test_prompt.py`: `test_logs_prompt_digest_and_text_to_session`,
  `test_injects_named_records_first`, `test_injects_examples_and_tests_within_20_lines`,
  `test_intent_change_flag_on_confirmed_record_with_change_words`,
  `test_no_flag_on_proposed_record`, `test_compare_line_when_confirmed_records_injected`,
  `test_awaiting_confirmation_lists_stated_set_with_digest`; 1b H10:
  `test_prints_queued_escalations`; stretch H11: `test_escalation_hint_on_many_features`
- `test_stop.py`: `test_blocks_once_when_covering_tests_not_fresh`,
  `test_no_block_when_stop_hook_active`, `test_summary_when_evidence_fresh`,
  `test_summary_caps_proposed_lines`, `test_regression_blocks_with_owner_instruction`,
  `test_matters_dec_asked_once_per_hash`, `test_new_red_test_never_asks`,
  `test_doc_only_turn_prints_at_most_one_line`, `test_writes_stated_set`,
  `test_no_change_turn_prints_nothing`, `test_verify_unavailable_degrades`
- `test_latency.py`: `test_hooks_within_in_process_budget` (50 records, warm caches, fakes
  replaced by in-memory data; asserts each hook function under half its spec 10 budget, which
  leaves room for interpreter start)

## 11. Phases 2 to 4

### 11.1 Phase 2: integration (coordinator)

1. Merge each lane's final branch head into `main` (`git merge --no-ff sp1/<lane>`, with the
   `SR:` trailer of its items): CORE, TRUST, VERIFY, HOST. Only `docs/followups.md` may
   conflict (keep both sections). Run the whole suite after each merge.
2. The conformance suite in `tests/contracts/test_conformance.py` now also runs against
   `open_core`, `open_verify` and `get_backend`; fix any mismatch in the implementing lane's
   files.
3. Write `tests/integration/` (with `sr` markers naming the SRs they verify):
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
     every command of spec 9 that was built.
   - `test_latency_subprocess.py::test_hooks_end_to_end_under_two_seconds` (real subprocesses
     on the temp repository; asserts each hook under 2 s, records timings).
4. `scripts/bench_hooks.py`: runs each hook 20 times as subprocesses against a repository
   (default: the current one), prints p50 and p95 per hook and the prompt + stop sum. Run it
   on the temp repository now and on plumb's own repository in phase 3.
5. Gate: `uv run pytest -q` and `uv run ruff check src tests` green on `main`.

### 11.2 Phase 3: dogfood completion (coordinator, on `main`)

The steps and the gate are in 4.4. Most of the dogfooding is already done by D0 to D3; this
phase only completes the links, runs the first full suite and measures the hooks on plumb's
own repository.

### 11.3 Phase 4: review (on the dogfooded `main`)

- Four review agents, one per lane diff (`git diff <phase-0 commit>..sp1/<lane>`), each
  checking the diff against the spec sections its lane implements, the brief and rulings R1
  to R7, and spec 10 latency rules. Severity follows R7: HIGH only for a contradiction or
  omission of the owner's words, decisions or rulings, or a defect that breaks a spec
  guarantee (for example a path that confirms a record without the owner's words, or a hook
  that can block or exceed 2 s).
- One intent verifier reads the merged, dogfooded result against the brief.
- The coordinator fixes HIGH findings test first, re-runs the whole suite, commits through
  plumb's own hooks with `SR:` trailers, and appends medium and low findings to
  `docs/followups.md` under `## SP1 review (2026-10-06)`.

## 12. Time box, drop order and the morning minimum

**The morning minimum** is: phase 0; CORE C1 to C8; TRUST T1 to T6; VERIFY V1 to V8; HOST H1
to H8; checkpoints D0 to D3; and the phase 2 merges with `test_loop_end_to_end` and
`test_merge_refused_then_allowed`. That is the concept's dogfoodable core (concept 11, 1a):
records, hashes, links, logs, approvals with the guard, validation, the merge-boundary
confirmation rule, trailers, the four hooks, the status line, the installer, and the map,
selection and runs with evidence and the regression rule, all used on plumb itself. Every lane's
must items fit in 150 min of its 3 hours (section 6).

**Never dropped**, whatever the clock says: the R1 merge-boundary confirmation rule (T3), the
`SR:` trailer check (T1), the approval guard (T2's marker refusal and relay checks, H6's deny
rules and marker), and the dogfood checkpoints D0 to D3.

**Order of protection** (highest first):

1. the morning minimum, including D0 to D3;
2. phase 3, dogfood completion;
3. phase 4, review (it can shrink to the single intent verifier);
4. 1b items;
5. stretch items.

**Cutting when time runs short**, in this order: stretch items (from the end of each lane's
list); 1b items (from the end of each lane's list); review scope (lane reviewers first, the
intent verifier last); the non-essential integration tests (`test_dispatch.py`,
`test_latency_subprocess.py`; the benchmark script still runs). Dogfooding is never cut to
make room for review, 1b or stretch work.

**Lane stop rule.** At its 3-hour mark a lane stops 1b and stretch work, records each
unfinished item in `docs/followups.md` with its state, and hands back what passes its gate.
If a must item is still unfinished, the morning minimum outranks the 3-hour stop: the lane
continues on its remaining must items only, and the coordinator takes that time from items
3 to 5 above. The slack in the schedule (section 1) absorbs it.

**Clock rule.** At 8 hours elapsed, whatever is on `main` has passed every checkpoint it
unlocked; the coordinator stops review and 1b work, writes the handoff and records the rest
in `docs/followups.md`.

If the JEV adapter (T11) is not built, `judgment.backend: jev` falls back to the heuristic
with a notice, which the spec already requires. If the importer (T10) is not built,
`plumb import` reports `not available in this build` (spec 12.3) and SR-023 stays proposed
without code.

## 13. Definition of done

Spec section 14.2, checked by the coordinator after phase 3 and reported in the handoff:

- [ ] whole suite and ruff green on `main`;
- [ ] every command of spec 9 that was built exists, has a test, and appears in
      `plumb --help`; unbuilt 1b and stretch commands are listed in `docs/followups.md`;
- [ ] the end-to-end loop, in-flow confirmation, merge-boundary and regression integration
      tests pass;
- [ ] guard tests pass and the installer writes the deny rules and marker;
- [ ] `validate --merge` exits 4 then 0;
- [ ] checkpoints D0 to D3 passed; every commit since phase 0 carries an `SR:` trailer, and
      the `commit-msg` hook has checked every commit since D1;
- [ ] hook benchmark within budget on plumb's own repository (or each miss recorded);
- [ ] if the importer (T10) was built: a read-only dry-run import of
      `C:/coding/pi-agent-factory` reports findings and changes nothing there;
- [ ] `plumb judgment status` reports `heuristic`; if T11 was built, JEV tests pass on the
      local stub;
- [ ] dogfood checks of 4.4 pass;
- [ ] unfinished items, medium and low findings in `docs/followups.md`; no HIGH finding open.

## 14. Risks

| Risk | Mitigation |
|---|---|
| A lane's must items overrun | Must items are at most 150 min per lane; the lane stop rule keeps must work going and cuts 1b, stretch and review first (section 12) |
| CORE is on the critical path to D1 | Phase 0 takes the log and the shared primitives off it; approvals, the merge boundary and trailers moved to TRUST; other lanes do not wait on it (fakes) |
| Contract gaps found mid-lane | One coordinator owns contract changes; lanes move to their next item meanwhile |
| A plumb hook misbehaves on plumb's own sessions after D2 | Hooks always exit 0 and block at most once per turn; `git revert` of the install commit until `hooks uninstall` lands; the failure is recorded |
| The `commit-msg` hook blocks a lane commit | The check passes with a notice where the branch has no `.plumb/`; after rebasing, lanes take trailers from their task tables |
| Interpreter start (about 225 ms here) eats the hook budget | Async post-edit hook, deny rules instead of a per-call guard hook, JSON caches, lazy imports, benchmark in phases 2 and 3 |
| Runner tests are slow on 2 cores | Tiny temporary projects; no xdist; lane suites run one at a time per lane |
| Host feature uncertainty (`async` hooks, wildcard deny rules) | Fallbacks stated in spec 6.3 and 5.6; the guard's primary layer is the CLI marker check |
| Union merges of JSONL logs | Chain forks accepted by design (spec 5.7); validated by `test_union_merged_fork_accepted` |
