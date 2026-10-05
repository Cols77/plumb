# Sub-project 1 implementation plan

Implements `docs/specs/sp1-grounding-loop.md` (the spec). The owner does not review this plan;
verifier agents check it against the owner intent brief, rulings R1 to R7 and the spec. Section
numbers such as "spec 5.6" refer to the spec.

This revision applies five binding coordinator rulings (2026-10-06, about 01:00 local):

1. **Dogfood early.** Build order: the CORE lane alone first (minimal); then a dogfood
   bootstrap (`plumb init` in `C:/coding/plumb`, plumb's own `INT` records, `SR-001` onward
   with examples, and `FEAT-001`, all from `docs/concept.md`; an `SR:` trailer on every commit
   from then on); then VERIFY, HOST and BRIDGE in parallel on top of that core; then
   integration, with plumb's hooks installed into `C:/coding/plumb/.claude/settings.json` as
   soon as HOST lands.
2. **Time box.** Each lane's MUST list fits about 75 minutes of agent work. CORE's MUST list is
   fixed by the ruling. Everything else is SHOULD, with an explicit drop order, and every phase
   has a drop rule.
3. **R3 exactly.** Only a NEW test that starts red is exempt. An existing test that previously
   passed with recorded evidence and now fails IS a regression, even if its source changed.
4. **Fork plan.** The fork plan is `docs/fork-plan.md`, written by a later workflow phase. It
   is part of the definition of done.
5. **Known limitation.** The build agents of this overnight run do not run under plumb's own
   hooks. Full interactive dogfooding starts when the owner opens Claude Code in
   `C:/coding/plumb` (section 4.5).

The owner asked to "dogfood the version to itself as soon as possible and build with it" (D6)
and to have the implementation "by tomorrow morning (in 9 hours)" (D11). This plan therefore
puts plumb's own records on `main` right after the smallest useful core, and every later lane
starts from a repository that already holds them.

## 1. Shape of the work

| Phase | What | Who | Agent time | Gate before the next phase | Drop rule |
|---|---|---|---|---|---|
| 1. CORE | The CORE lane alone: package skeleton, frozen contracts and primitives, records, hashes, links, log, approvals, validate with `--merge`, brief, status (section 5) | one CORE agent in worktree `sp1-core`; coordinator merges | 75 min of MUST items, about 80 min with the gate | CORE lane gate (3.3); merged into `main`; `uv run pytest -q` and `uv run ruff check src tests` green on `main` | CORE builds no SHOULD item in this phase. At **03:15** CORE hands over what passes its gate; any unfinished MUST item continues in phase 3 as a fourth lane, `core-rest`, ahead of every SHOULD item, and is named in `docs/followups.md` |
| 2. Dogfood bootstrap | `plumb init` in `C:/coding/plumb`; plumb's own records from `docs/concept.md`; links pinned; `plumb validate` clean (section 4.1) | coordinator, on `main` | 25 min | bootstrap gate (4.3) | At **03:40** the bootstrap stops. Its MUST part (init, `INT`, `SR` with examples, `FEAT-001`, pinned `derives_from` links, `validate` with no errors) is never cut; `DEC` records with `matters: false` and code or test links move to phase 4 |
| 3. Lanes | VERIFY, HOST and BRIDGE in parallel, each in its own worktree on top of the bootstrapped `main` (sections 6 to 8). Each lane hands over a merge-ready commit at each merge point; the coordinator merges it at once and runs the landing steps it unlocks (4.4) | three lane agents; coordinator | 75 min of MUST items per lane; SHOULD items until the lane stop | lane gate (3.3) at each merge point; whole suite and ruff green on `main` after each merge; landing-step gates (4.4) | MUST merges are due by **05:30**. SHOULD items are dropped from the end of each lane's drop order first. Lane stop at **05:45**: the lane hands back what passes its gate (last merge by 06:00) and records each unfinished item in `docs/followups.md` |
| 4. Integration | Remaining links, conformance suite, end-to-end integration tests, hook benchmark, first full run on plumb's own repository (section 9) | coordinator, on `main` | 45 min | whole suite and ruff green on `main`; benchmark recorded; dogfood checks (4.6) | Cut in the order of section 11; the hook install, the `commit-msg` hook install, the driven loop check and the two never-dropped integration tests are never cut |
| 5. Review | One intent verifier on the merged result, plus one reviewer per lane diff if time allows; HIGH fixes only (section 10) | review agents; coordinator fixes | 30 min | no HIGH finding open; medium and low in `docs/followups.md` | Shrinks to the single intent verifier first. At the **07:15** clock rule review stops whatever its state; any open HIGH finding is named at the top of the handoff |

**The deadline is an absolute time.** The owner set the box on the evening of 2026-10-05: "I
want to have the implementation available by tomorrow morning (in 9 hours)." The owner's clock
started at about 23:00 local on 2026-10-05, so the deadline is about **08:00 local on
2026-10-06**. Every cutoff in this plan is an absolute local time on 2026-10-06, never an
elapsed time:

| Local time | Rule |
|---|---|
| 03:15 | CORE hands over (phase 1 drop rule) |
| 03:40 | Bootstrap stops (phase 2 drop rule) |
| 05:30 | Latest merge of any lane's MUST items |
| 05:45 | Lane stop: SHOULD work ends; last lane merge by 06:00 |
| 07:15 | **Clock rule** (section 11): review and all SHOULD work stop; only gated merges and the handoff remain |
| 07:45 | Handoff and `docs/followups.md` committed on `main` |
| 08:00 | The owner's deadline |

Planned schedule. It assumes phase 1 starts at 01:30 local; the coordinator writes the real
start time in the first CORE merge message. The cutoffs above never move: a late start only
shrinks the slack, and the drop rules apply earlier.

| Local time (planned) | Event |
|---|---|
| 01:30 to 02:50 | Phase 1: CORE MUST items K1 to K7, lane gate, merge into `main` |
| 02:50 to 03:15 | Phase 2: dogfood bootstrap; its commit is the first with an `SR:` trailer checked against real records |
| 03:15 | Worktrees `sp1-verify`, `sp1-host`, `sp1-bridge` created from the bootstrapped `main`; lanes start |
| about 03:35 | BRIDGE merge point B1 (trailers); landing step L-B installs the `commit-msg` hook |
| about 04:10 | HOST merge point H5 (installer, session start, edit tracking, status line); landing step L-H installs those hooks |
| about 04:40 | HOST merge point H7, VERIFY merge point V6, BRIDGE merge point B4 (all MUST items); landing steps L-H (prompt and stop hooks, driven loop check) and L-V (test map, first evidence) |
| 04:40 to 05:45 | SHOULD items in each lane's drop order |
| 05:45 to 06:35 | Phase 4: integration |
| 06:35 to 07:05 | Phase 5: review and HIGH fixes |
| 07:05 to 07:15 | Slack (10 min) |
| 07:15 to 07:45 | Handoff |

The nominal MUST work ends about 04:40, which leaves 50 min before the 05:30 MUST cutoff; that
is the real slack for the morning minimum. The SHOULD window (04:40 to 05:45) and review absorb
any later overrun, in the order of section 11.

Orchestration uses the host's native mechanism: in Claude Code, the `Workflow` tool. Phase 1 is
one `agent()` pipeline followed by a merge step; phase 2 is one coordinator step; phase 3 is a
`parallel()` of three lane pipelines, each a sequence of segment `agent()` calls (one per merge
point) with a merge step on `main` after each segment; merge steps run one at a time (one
`main` checkout) and each ends with the landing steps its merge unlocks. Phases 4 and 5
follow, each carrying its gate. Starting that workflow needs the owner's opt-in where Claude
Code asks for it; this plan does not grant it.

## 2. Conventions for every agent

- Repository `C:/coding/plumb`. Lanes work in worktrees `C:/coding/plumb-wt/sp1-<lane>` on
  branches `sp1/<lane>` (`git -C C:/coding/plumb worktree add C:/coding/plumb-wt/sp1-core -b
  sp1/core main`), then `uv sync` inside the worktree. CORE's worktree is created from the
  initial `main`; VERIFY, HOST and BRIDGE worktrees are created from `main` after the
  bootstrap, so they contain `.plumb/` with plumb's own records.
- Never write inside `C:/coding/pi-agent-factory` or its worktrees, never create worktrees of
  it, never run its `coherence` or `factory` commands. Read its files only. Copying a source
  file's content into plumb is reading.
- Test first: write the failing test, run it red, implement, run it green. Run focused tests
  while iterating (`uv run pytest tests/core/test_links.py -q`) and the lane's whole set once
  before each commit. No `-n` above 2; plumb's suite needs none.
- Do not kill processes you did not start. `plumb tests run` terminates only the pytest
  process it started. The machine has 2 cores and other work running: at most two lanes run
  their whole lane suite at the same moment; focused tests are fine at any time.
- Commit in small steps with clear messages (`core: pin both link ends`), each ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **`SR:` trailers.** From the bootstrap commit on, every commit carries an `SR:` trailer naming
  the plumb requirements it serves, taken from the `SR` column of the task tables and from the
  requirement table in 4.2 (`SR: SR-003, SR-004`). CORE's phase-1 commits should already carry
  them (the IDs are fixed by this plan), but before the bootstrap nothing checks them. The
  `commit-msg` hook enforces trailers from landing step L-B on; it lives in the shared git
  directory, so it also runs in the lane worktrees.
- **Lanes use plumb while they build.** Each phase-3 lane agent starts by running `uv run
  plumb brief` and `uv run plumb status` in its worktree and keeps that output as context; it
  marks every new test with `@pytest.mark.sr("SR-0xx")` (the marker is registered in phase
  1), so plumb's test map covers it without the lane editing `.plumb/`; and it runs `uv run
  plumb validate` before each merge-ready report. Lanes never edit `.plumb/`; the coordinator
  owns it.
- **No agent writes an approval.** No agent runs `plumb approve`, `plumb revoke` or
  `plumb relay` on plumb's own records in sub-project 1: no owner prompt in these sessions
  affirmed them (R2). Every plumb record stays proposed for the owner's morning confirmation.
- **Internal merges are not merge boundaries.** Lane-to-`main` merges are internal integration
  and use `git merge --no-ff`. Sub-project 1's merge boundary in R1's sense is the owner's
  morning `plumb validate --merge <base>`, which exits 4 until the owner confirms (4.6). The
  coordinator still runs `validate --merge` in report-only mode after each merge and logs its
  exit code in the merge commit message.
- Fix only HIGH review findings. Each lane appends its medium and low findings, and any
  unfinished item with its state, under its own heading at the end of `docs/followups.md`
  (`## SP1 lane CORE (2026-10-06)`); the coordinator keeps both sides of append-only conflicts.
- Hooks must stay well under 2 s per turn: follow spec section 10 (lazy imports, JSON caches,
  one `git status`, no tests in hooks).
- Dependencies: standard library and PyYAML at runtime; pytest and ruff for development.
  Nothing else.

## 3. Files and ownership

### 3.1 Ownership table (disjoint)

| Owner | Paths |
|---|---|
| CORE (phase 1; the first group is frozen after the CORE merge) | Frozen: `pyproject.toml`, `uv.lock`, `src/plumb/__init__.py`, `__main__.py`, `cli.py`, `cliutil.py`, `contracts.py`, `paths.py`, `normalize.py`, `config.py`, `text.py`, `log.py`, `tests/conftest.py`, `tests/test_smoke.py`. CORE modules: `src/plumb/model.py`, `store.py`, `hashing.py`, `links.py`, `confirm.py`, `approvals.py`, `trailers.py` (trailer parsing only), `merge.py`, `validate.py`, `query.py`, `api.py`, `commands.py`; `tests/core/**` |
| VERIFY | `src/plumb/verify/**` (`__init__.py`, `imports.py`, `markers.py`, `testmap.py`, `select.py`, `pytest_plugin.py`, `runner.py`, `evidence.py`, `policy.py`, `envid.py`, `cli.py`); `tests/verify/**` |
| HOST | `src/plumb/hosts/__init__.py`, `src/plumb/hosts/claude_code/**` (`__init__.py`, `cli.py`, `hookio.py`, `session_start.py`, `prompt.py`, `post_edit.py`, `stop.py`, `snapshot.py`, `statusline.py`, `install.py`, `templates/SKILL.md`, `templates/plumb-command.md`, `templates/claude-md-block.md`); `tests/host/**` (including `tests/host/fakes.py`) |
| BRIDGE | `src/plumb/claims.py` (`trailers check-msg`, `trailers install-hook`, `claims check`); `src/plumb/judgment/**` (`__init__.py`, `model.py`, `tiers.py`, `heuristic.py`, `fidelity.py`, `cascade.py`, `jev.py`, `state.py`, `cli.py`); `src/plumb/importer/**` (`__init__.py`, `pi_factory.py`, `cli.py`); `tests/bridge/**` including `tests/bridge/fixtures/pi_factory/**` |
| `core-rest` (only if the phase-1 drop rule fires, then CORE SHOULD items) | CORE's module files and `tests/core/**`, never the frozen group |
| Coordinator (bootstrap, landing steps, integration) | `.plumb/**`, `.claude/**`, `CLAUDE.md`, `README.md` (usage section), `tests/integration/**`, `scripts/bench_hooks.py`, `docs/sp1-handoff.md`; the untracked `.git/hooks/commit-msg` |
| Any lane, append only | `docs/followups.md` (own heading) |

`src/plumb/hosts/claude_code/templates/*` are package data; phase 1 makes `uv_build` include
them (they sit inside the package).

### 3.2 Contracts

Spec section 12 is the contract: `contracts.py` (12.1), the factory functions (12.2), the
dispatcher with every lane's routes (12.3), the shared primitives including `log.py` (12.4) and
the file formats (12.5). CORE writes all of them in phase 1, so they exist before any other
lane starts. A lane needing a contract change stops that item, asks the coordinator, and works
on its next item. The coordinator changes the contract on `main`, updates spec section 12 in
the same commit, and tells every lane to rebase.

VERIFY, HOST and BRIDGE build on the real, merged core: they may import CORE modules directly
(`plumb.api.open_core`, `plumb.model`, `plumb.log`). They never import each other's modules in
unit tests: HOST uses fakes of `VerifyAPI`, `JudgmentBackend` and `LLMCascade` in its own
`tests/host/fakes.py`, and BRIDGE passes `verify=None` or a small local fake. Calls between
these three lanes at run time go only through the factory functions of spec 12.2, imported
inside the function that needs them, so a missing lane degrades instead of failing at import.

### 3.3 Lane gate

Run inside the lane worktree at each merge point and before handing back:

```
uv run pytest tests/<lane> tests/core tests/test_smoke.py -q
uv run ruff check src tests
uv run plumb validate          # phase-3 lanes only: no errors
git diff --name-only main...HEAD   # every path must be in the lane's row of 3.1, or docs/followups.md
```

The lane then reports `merge-ready <lane> <merge point> <commit sha>` and goes on with its next
item. The coordinator merges that commit (`git merge --no-ff <sha>`, message with the `SR:`
trailer of the merged items), runs `uv run pytest -q` and `uv run ruff check src tests` on
`main` (from landing step L-V on, through `uv run plumb tests run --full`, 4.4), and runs the
landing steps the merge unlocks.

## 4. Dogfooding: bootstrap, landing steps and the known limitation

### 4.1 Phase 2: the dogfood bootstrap (coordinator, on `main`)

Runs right after the CORE merge, before the other lanes start, so they start from a repository
that already holds plumb's own records.

1. `uv run plumb init` in `C:/coding/plumb` (idempotent; adds `config.yaml`, `claims.yaml`,
   `.gitignore`, `.gitattributes` and empty logs under `.plumb/`). Set `verify.infra_globs` in
   `.plumb/config.yaml` to add `src/plumb/verify/pytest_plugin.py`.
2. Write plumb's records of 4.2 as Markdown with frontmatter (spec 5.2), from `docs/concept.md`
   and the owner intent brief: `INT` records with verbatim quotes and read-backs in the owner's
   terms; `FEAT-001`; `SR-001` onward, each with a statement, at least one given/when/then
   example, `feature: FEAT-001` and a `derives_from` link; and the three `DEC` records whose
   `matters` is true (F2, F4, F6 of spec section 3). Records are written with `plumb new` if
   CORE's SHOULD item built it, otherwise by hand.
3. `uv run plumb repin <ID>` on every record, so every link is pinned.
4. `uv run plumb validate` (no errors; warnings for proposed records and uncovered examples are
   expected).
5. `uv run plumb validate --merge <first commit of main>`: exits 4 and lists every record
   awaiting the owner's confirmation, which is the expected morning question.
6. Commit `dogfood: plumb's own intent records` with `SR: SR-001, SR-003, SR-025`.

Then, with time left before 03:40 (SHOULD, in this order): `implemented_by` and `verified_by`
links (whole files) for CORE's modules and tests; the `DEC` records with `matters: false` for
the other refinements of spec section 3. Whatever is left moves to phase 4.

### 4.2 plumb's own records

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

Feature: `FEAT-001` "Sub-project 1: core, grounding loop and covering-test verification"
(concept section 11, item 1), whose `requirements` list every SR below. Splitting it into
finer features is left to the owner.

Requirements. Each has given/when/then examples drawn from the named tests and a
`derives_from` link; `implemented_by` and `verified_by` links are added when the files reach
`main` (bootstrap SHOULD step, landing steps, phase 4). Lane tests also carry
`@pytest.mark.sr` markers naming these IDs.

| ID | Lane | Tier | Statement (short) | Derives from | Verified by |
|---|---|---|---|---|---|
| SR-001 | CORE | MUST | Records are Markdown with frontmatter under `.plumb/`, identified by frontmatter ID | INT-006, INT-010 | `tests/core/test_model.py`, `test_store.py` |
| SR-002 | CORE | MUST | Record hashes ignore formatting and change with meaning | INT-006 | `tests/core/test_hashing.py`, `test_primitives.py` |
| SR-003 | CORE | MUST | Links pin both ends; either end moving makes the link stale; dangling links are errors | INT-006 | `tests/core/test_links.py`, `test_validate.py` |
| SR-004 | CORE | MUST | Approvals pin exact content; an edit leaves the record unconfirmed | INT-006 | `tests/core/test_confirm.py`, `test_approvals.py` |
| SR-005 | CORE, HOST | MUST | Only the owner's explicit words confirm: owner command or an agent-relayed approval carrying the owner's verbatim quote and the prompt digest; the session marker refuses self-approval | INT-004, INT-006 | `tests/core/test_approvals.py`, `tests/host/test_install.py` |
| SR-006 | CORE | MUST | Logs are append-only and hash-chained; tampering is reported | INT-006 | `tests/core/test_log.py`, `test_validate.py` |
| SR-007 | BRIDGE | MUST | `SR:` trailers are checked at commit, and the claims check compares claimed with declared paths | INT-006, INT-010 | `tests/bridge/test_trailers.py`, `test_claims.py` |
| SR-008 | CORE | MUST | The merge boundary refuses unconfirmed touched requirements and lists the approvals of the range, agent-relayed ones included | INT-004 | `tests/core/test_merge.py` |
| SR-009 | CORE, HOST | MUST | The session brief is about 30 lines of context, not procedure | INT-002, INT-008 | `tests/core/test_query.py`, `tests/host/test_session_start.py` |
| SR-010 | HOST, BRIDGE | MUST | Each prompt receives the relevant records, their tests and an intent-change flag | INT-002, INT-004 | `tests/host/test_prompt.py`, `tests/bridge/test_heuristic.py` |
| SR-011 | HOST | MUST | Edits are tracked without blocking | INT-003 | `tests/host/test_post_edit.py` |
| SR-012 | HOST | MUST | The end-of-turn summary is short, shows proposed records, and asks only on the three triggers | INT-008 | `tests/host/test_stop.py` |
| SR-013 | HOST | MUST | The status line reads state and recomputes nothing | INT-008 | `tests/host/test_statusline.py` |
| SR-014 | HOST | MUST | Hooks stay within their budgets and never block work on plumb's own failure | INT-002, INT-003 | `tests/host/test_hookio.py`, `tests/integration/test_latency_subprocess.py` |
| SR-015 | HOST, BRIDGE | MUST | The installer writes hooks, status line, marker, deny rules, skill, CLAUDE.md block and the commit hook, idempotently | INT-007, INT-009 | `tests/host/test_install.py`, `tests/bridge/test_trailers.py` |
| SR-016 | VERIFY | MUST | The test map is grep-able text built from links, markers and imports | INT-002 | `tests/verify/test_testmap.py` |
| SR-017 | VERIFY | MUST | Covering-test selection: docs select nothing, infrastructure sets full pending, unknown coverage samples, a budget caps the turn | INT-002, INT-003 | `tests/verify/test_select.py` |
| SR-018 | VERIFY | MUST | Evidence is pinned to the tree, the import closure, the test source and the environment key, and reused only on an exact match | INT-006 | `tests/verify/test_evidence.py`, `test_runner.py` |
| SR-019 | VERIFY | SHOULD | A failure that passes on a same-tree rerun is recorded as flaky with both attempts | INT-006 | `tests/verify/test_policy.py` |
| SR-020 | VERIFY, HOST | MUST | A regression is an existing test node that previously passed with recorded evidence and now fails, even if its source changed since; only a new test that starts red is exempt and never interrupts | INT-008 | `tests/verify/test_policy.py`, `tests/host/test_stop.py` |
| SR-021 | BRIDGE | MUST | Judgment is optional: heuristic by default, advisory only, JEV only when a key exists, fallback on failure | INT-011 | `tests/bridge/test_heuristic.py`, `test_tiers.py` |
| SR-022 | BRIDGE | MUST | Fidelity packets let the host agent judge a requirement without JEV | INT-011, INT-004 | `tests/bridge/test_fidelity.py` |
| SR-023 | BRIDGE | SHOULD | The importer reads pi-agent-factory records read-only and never manufactures a confirmation | INT-005, INT-010 | `tests/bridge/test_import_*.py` |
| SR-024 | BRIDGE | SHOULD | The cascade hands low-confidence judgments to the host agent through an interface | INT-011 | `tests/bridge/test_cascade.py` |
| SR-025 | CORE | MUST | `plumb init` adopts any repository in one idempotent command | INT-005 | `tests/core/test_cli_core.py` |

Decisions: `DEC-001` to `DEC-013` for spec refinements F1 to F13, each with `question`,
`chosen`, `alternatives` (the concept's mechanism), `rationale` and a `decides` link to the SR
it shapes. F2 (guard by deny rules), F4 (prompt digests committed when cited) and F6 (tests run
in the agent's turn) have `matters: true` and are written in the bootstrap's MUST part; the
others have `matters: false` and are SHOULD.

A requirement whose SHOULD item is not built (for example SR-023 without the importer) stays a
proposed record with no `implemented_by` link; `plumb validate` warns about it and the handoff
lists it.

### 4.3 Bootstrap gate

- `plumb validate` reports no errors on plumb's own records;
- every `INT` of 4.2 exists with its verbatim quote, `FEAT-001` exists, and every `SR` of 4.2
  exists with at least one example and a pinned `derives_from` link;
- `plumb validate --merge <first commit of main>` exits 4 and lists the records awaiting the
  owner;
- `plumb brief` prints the brief within 40 lines;
- the bootstrap commit carries an `SR:` trailer.

### 4.4 Landing steps (coordinator, on `main`, as each lane lands)

| Step | Runs when | Steps | Gate |
|---|---|---|---|
| L-B. Trailers enforced | BRIDGE merge point B1 is on `main` | `uv run plumb trailers install-hook`; set `require_trailer: true` in `.plumb/claims.yaml`; commit with `SR: SR-007, SR-015` through the new hook | `plumb trailers check-msg` rejects a message naming `SR-999` and accepts one naming `SR-001`; the commit passed the hook |
| L-H. Hooks installed | Each HOST merge point (H5, H7), at once | `uv run plumb hooks install --launcher venv` into `C:/coding/plumb/.claude/settings.json`; the installer registers only the hooks whose modules are present (H5: session start, edit tracking, status line, marker, deny rules, skill, CLAUDE.md block; H7: prompt and stop); then the driven loop check (4.5); commit with `SR: SR-015` plus the hook's SR | `.claude/settings.json` holds the hooks installed so far, the status line, the marker and the deny rules; each installed hook exits 0 on plumb's repository within its spec 10 budget; the driven loop check passes |
| L-V. Map and evidence | VERIFY merge point V6 is on `main` | `uv run plumb tests map`; add the `verified_by` links still missing for files on `main`; `uv run plumb tests run --full` once, so evidence starts; from now on every post-merge suite run on `main` is `uv run plumb tests run --full`, which records evidence, so R3 regressions between merges are detected on plumb's own tests; commit with `SR: SR-016, SR-017, SR-018` | `plumb tests map` lists every SR whose test files are on `main`; `.plumb/log/evidence.jsonl` has a full-run `test-run` entry |

A landing step whose lane has not landed waits; it is never skipped. If an installed hook
misbehaves before `plumb hooks uninstall` exists (HOST SHOULD item), `git revert` of the
install commit removes it and the failure is recorded in `docs/followups.md`.

### 4.5 Known limitation: the build runs outside plumb's hooks

Stated honestly, as the coordinator ruled. Hooks registered in
`C:/coding/plumb/.claude/settings.json` fire only for a Claude Code session whose project
directory is `C:/coding/plumb`. The coordinating session of this overnight run is rooted
elsewhere, and its lane and coordinator agents are subagents of that session: they do not
receive the `SessionStart`, `UserPromptSubmit`, `PostToolUse` or `Stop` events that drive
plumb's loop. Installing the hooks therefore does not put the build agents under them.

What plumb does for its own build tonight, without hooks:

- plumb's own records are on `main` from the bootstrap, before any other lane starts;
- every commit from the bootstrap on carries an `SR:` trailer, checked by plumb's
  `commit-msg` hook from L-B on (git hooks do fire for every agent's commits);
- every phase-3 lane agent reads `plumb brief` and `plumb status` before it starts, marks its
  tests with `sr` markers, and runs `plumb validate` before handing over;
- every merge on `main` runs `plumb validate` and, from L-V on, `plumb tests run --full`, which
  records evidence and reports regressions;
- at each L-H step, the **driven loop check** calls plumb's real hook entry points against
  plumb's own repository with the JSON Claude Code would send (`session_id` `sp1-driven-<n>`,
  `cwd` `C:/coding/plumb`, `PLUMB_AGENT_SESSION=1`): `plumb hook session-start`; once
  installed, `plumb hook prompt` with a short work item text; `plumb hook post-edit` for one
  file; `plumb hook stop` (if it blocks asking for the covering tests, `plumb tests run
  --changed`, then `plumb hook stop` with `stop_hook_active: true`); and `plumb statusline`.
  Its outputs and timings go in the merge commit message. It proves the hooks work on plumb's
  own repository; it is not an interactive session.

What does not happen tonight: no build agent sees plumb's session brief, per-prompt context,
intent-change flag, stop-hook covering-test request or end-of-turn summary as part of its own
turns. **Full interactive dogfooding starts when the owner opens Claude Code in
`C:/coding/plumb`**: from that session on, the installed hooks run on every prompt and every
turn. The handoff says this in its first section, not in a footnote.

### 4.6 Dogfood checks (phase 4 gate)

- `plumb validate`: no errors.
- `plumb tests map` lists every SR whose module was built with at least one test.
- `.claude/settings.json` holds the four hooks, the status line, the marker and the deny rules;
  `.claude/skills/plumb/SKILL.md` exists; the `commit-msg` hook rejects a message with an
  unknown SR ID (`plumb trailers check-msg`).
- Every commit since the bootstrap carries an `SR:` trailer, and `plumb claims check` over that
  range reports no undeclared path, or each one is recorded in `docs/followups.md`.
- `scripts/bench_hooks.py` on plumb's own repository: prompt + stop p95 under 1.5 s.
- `.plumb/log/evidence.jsonl` holds the `test-run` entries of the post-merge runs since L-V.
- `plumb validate --merge <first commit of main>` exits 4 and lists every record awaiting the
  owner's confirmation: the expected morning question. The handoff gives the one line that
  confirms everything the owner agrees with: `plumb approve --proposed` in their own terminal,
  or "ok" in a session (relayed with the quote check).

## 5. Phase 1: lane CORE (alone)

Goal: the smallest core that plumb's own records and every later lane can stand on. Extraction
sources: spec 13 (`register.py`, `relations.py`, `fingerprint.py`). The MUST list is the
coordinator's ruling: the record model with parse and write, normalized content hash,
hash-pinned links and staleness, pinned approvals including agent-relayed approvals with quote
and prompt digest, the append-only event log, validate including `--merge` (R1 at the merge
boundary), brief and status.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| K1 | Skeleton and frozen contracts: `pyproject.toml` (`pyyaml>=6`; `sr` marker registered: `markers = ["sr(id): links a test to a plumb requirement"]`; templates as package data), `uv lock`; `contracts.py` exactly as spec 12.1; `normalize.py`, `paths.py`, `config.py` (defaults plus YAML load), `text.py` (spec 12.4); `cli.py` dispatcher with every lane's route and `cliutil.py` (spec 12.3); `tests/conftest.py` (`repo`, `write_record`, `hook_input`); `plumb init` | MUST | SR-001, SR-025 | 10 min |
| K2 | `model.py`, `store.py`, `hashing.py`: frontmatter split and parse into `Record` (five kinds, examples, AC examples, links); ID validation; next ID; `write_record` (YAML dump with stable key order); duplicate detection; record hash (spec 5.4) and whole-file end hash | MUST | SR-001, SR-002 | 15 min |
| K3 | `log.py` (spec 5.7): JSONL append with lock, `prev` and `digest`, one `write`; read from an offset; chain verification | MUST | SR-006 | 10 min |
| K4 | `links.py`: target parsing (`ID`, `path`), allowed-kind matrix, `add_link` with pins, `link_states`, `repin` (also pins unpinned links, logs `repin`); commands `link`, `repin` | MUST | SR-003 | 10 min |
| K5 | `confirm.py`: derived confirmation from `approval` and `revocation` events against current hashes, covered state; `approvals.py`: `approve` (marker refusal, `--proposed`, `--yes`), `revoke`, `relay` with the four checks of spec 5.6 (prompt digest in `prompts.jsonl`, verbatim quote, affirmation term, stated set or named ID) and the `prompt` event before the approval; commands `approve`, `relay`, `revoke` | MUST | SR-004, SR-005 | 15 min |
| K6 | `validate.py`: errors and warnings of spec 5.10, approval re-checks, log chain check; `trailers.py` (`parse_sr_trailer`); `merge.py`: `merge_check` (spec 5.11): touched requirements confirmed (exit 4), approvals of the range listed with agent-relayed ones marked, log integrity against the base; fidelity and verification lines print `unavailable` until their providers exist; command `validate [--merge]` | MUST | SR-003, SR-006, SR-008 | 10 min |
| K7 | `query.py`: `relevant`, `brief_lines` (30-line cap); `api.py`: `open_core`; commands `brief`, `status` | MUST | SR-009 | 5 min |
| KS1 | Index and hash caches (`.plumb/cache/index.json`, `hashes.json`, keyed by `(size, mtime_ns)`); config JSON cache | SHOULD | SR-014 | 10 min |
| KS2 | Commands `new`, `show` | SHOULD | SR-001 | 10 min |
| KS3 | Commands `drift`, `why`, `log` | SHOULD | SR-003, SR-009 | 10 min |
| KS4 | Symbol and test-node end hashes with `ast` (`path::Qual.name`, `path::test`) | SHOULD | SR-002, SR-003 | 15 min |
| KS5 | Wikilink checks; intent-translation warnings (an `INT` `will` item or assumption with no deriving SR or deciding DEC) | SHOULD | SR-003, SR-004 | 10 min |

MUST total: 75 min. CORE builds only K1 to K7 in phase 1 and merges once, after K7. CORE's
SHOULD items run in phase 3 as a fourth lane, `core-rest` (after any MUST item the phase-1
drop rule moved there), at lower priority than the three lanes: its agent runs only focused
tests while two lane suites are running. If it does not run, the coordinator builds KS1 in
phase 4. **Drop order** (dropped first to last): KS5, KS4, KS3, KS2, KS1. KS1 is dropped last
because it serves hook latency; without it the hooks parse plumb's few dozen records on each
call, which the phase-4 benchmark measures.

Tests (`tests/core/`), each written red first and marked with its SR:

- `test_primitives.py` (K1): `test_crlf_and_lone_cr_become_lf`,
  `test_trailing_whitespace_and_blank_lines_dropped`, `test_nfc_normalization`,
  `test_derived_blocks_removed`, `test_canonical_json_sorted_compact_utf8`,
  `test_file_digest_binary_uses_raw_bytes`, `test_find_root_prefers_plumb_dir`,
  `test_config_defaults_without_file`, `test_dataclasses_are_frozen`,
  `test_unknown_command_exits_2`, `test_missing_module_reports_not_available`,
  `test_every_route_names_a_module_path`
- `test_model.py`, `test_store.py`, `test_hashing.py` (K2):
  `test_parses_each_kind_from_frontmatter`, `test_identity_comes_from_frontmatter_not_filename`,
  `test_rejects_malformed_id`, `test_requirement_examples_parsed_with_ids`,
  `test_new_id_per_kind_and_nc_four_digits`, `test_write_record_round_trips`,
  `test_duplicate_ids_reported`, `test_record_hash_ignores_yaml_style_and_key_order`,
  `test_record_hash_ignores_links_field`,
  `test_record_hash_ignores_crlf_trailing_space_and_derived_blocks`,
  `test_record_hash_changes_on_statement_edit`, `test_file_end_hash_ignores_crlf`
- `test_log.py` (K3): `test_append_chains_prev_digest`, `test_digest_detects_modified_line`,
  `test_missing_prev_detected`, `test_union_merged_fork_accepted`,
  `test_concurrent_appends_do_not_interleave`, `test_read_since_offset`, `test_marker_recorded`
- `test_links.py` (K4): `test_add_link_pins_both_ends`, `test_pin_drift`,
  `test_crlf_is_not_drift`, `test_source_edit_marks_source_moved`,
  `test_dangling_record_and_path`, `test_unpinned_link_warns`, `test_link_kind_allowed_matrix`,
  `test_repin_refreshes_pins_and_logs_event`, `test_repin_does_not_confirm`
- `test_confirm.py`, `test_approvals.py` (K5): `test_proposed_until_approved`,
  `test_approval_event_at_current_hash_confirms`,
  `test_edit_after_approval_is_unconfirmed_edit`, `test_revocation_returns_to_proposed`,
  `test_covered_requires_verified_by_per_example`, `test_approve_refused_under_marker`,
  `test_approve_proposed_pins_all_listed`, `test_relay_accepts_affirming_quote_from_logged_prompt`,
  `test_relay_records_quote_and_prompt_digest`, `test_relay_rejects_quote_not_in_prompt`,
  `test_relay_rejects_quote_without_affirmation`,
  `test_relay_rejects_record_outside_stated_set_unless_named`,
  `test_relay_writes_prompt_event_before_approval`, `test_no_approval_from_non_affirming_prompt`
- `test_validate.py`, `test_merge.py` (K6): `test_clean_repo_passes`, `test_errors_exit_one`,
  `test_warnings_for_stale_unconfirmed_uncovered`, `test_sr_without_derives_from_warns`,
  `test_owner_approval_under_marker_is_error`,
  `test_relayed_approval_without_prompt_event_is_error`, `test_tampered_log_line_is_error`,
  `test_parse_sr_trailer_variants`, `test_merge_refuses_unconfirmed_touched_requirement`,
  `test_merge_touch_via_implemented_by_end`, `test_merge_touch_via_sr_trailer`,
  `test_merge_passes_after_approval`, `test_merge_lists_approvals_in_range_with_relayed_marked`,
  `test_merge_requires_deciding_matters_dec`, `test_merge_detects_rewritten_log_line`,
  `test_merge_reports_fidelity_and_verification_unavailable`
- `test_query.py`, `test_cli_core.py` (K7 and K1): `test_relevant_ranks_named_ids_first`,
  `test_brief_respects_line_cap`, `test_superseded_records_excluded_from_brief_and_relevant`,
  `test_init_is_idempotent_and_writes_ignore_and_attributes`, `test_status_json_counts`,
  `test_link_cli_target_forms`
- SHOULD: `test_index_cache_reparses_only_changed_files`, `test_hash_cache_reuses_unchanged_files`
  (KS1); `test_new_show_round_trip_json` (KS2); `test_drift_lists_moved_end`,
  `test_why_walks_to_intent_quotes`, `test_log_reads_streams` (KS3);
  `test_symbol_end_ignores_edits_elsewhere`, `test_test_end_drops_parametrize_ids`,
  `test_missing_symbol_is_dangling` (KS4); `test_untranslated_intent_items_warn`,
  `test_dangling_wikilink_is_error` (KS5)

## 6. Lane VERIFY (phase 3)

Goal: the test map, covering-test selection under R5, the pytest runner with evidence pinned
to the code and the cheap environment key, the regression rule exactly as R3, `plumb tests` and
`plumb.verify.open_verify` (concept 11, 1a step 6). Extraction sources: spec 13 (`imports.py`,
`markers.py`, `failure_policy.py`, `pytest_evidence_plugin.py`, `evidence.py`). The lane uses
the real core (`open_core` on the `repo` fixture) and small temporary pytest projects.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| V1 | `imports.py` (import edges and transitive closure over `source_dirs`) and `markers.py` (`sr` marker collection), both extracted | MUST | SR-016 | 10 min |
| V2 | `testmap.py`: map from `verified_by` links, markers and the import closure; fingerprint cache; `test_map.txt` writer | MUST | SR-016 | 10 min |
| V3 | `select.py`: priority order, doc-only, infra globs, unknown-coverage sample, budget and deferral, derived `full_pending` (R5) | MUST | SR-017 | 20 min |
| V4 | `pytest_plugin.py` (extracted: per-phase outcomes, collection errors, exit status, JSON report to `PLUMB_REPORT`); `runner.py`: run a selection, hard limit terminating only its own child, inputs-changed discard | MUST | SR-018 | 15 min |
| V5 | `envid.py` cheap `env_key`; `evidence.py`: `test-run` entry, freshness on closure, test hash and `env_key` (spec 7.4), reuse index by offset | MUST | SR-018 | 10 min |
| V6 | `policy.py`: the regression rule exactly as R3 (spec 7.5); `__init__.py` `open_verify`; `cli.py`: `tests map|select|run`, aliases `map` and `verify` | MUST | SR-020, SR-016, SR-017 | 10 min |
| VS1 | `removed after passing`: a node that passed with recorded evidence and is no longer collected while its file exists is listed by `plumb tests run` and in `status` (never an interruption), so renaming a failing test cannot hide it | SHOULD | SR-020 | 10 min |
| VS2 | `policy.py`: same-tree flaky rerun | SHOULD | SR-019 | 15 min |
| VS3 | `envid.py`: content identity (extracted) cached under `env_key`; freshness then also requires it | SHOULD | SR-018 | 15 min |
| VS4 | `cli.py`: `impact` | SHOULD | SR-016 | 10 min |
| VS5 | `testmap.py`: naming source | SHOULD | SR-016 | 5 min |
| VS6 | `tests waive` (owner only, marker refusal, `waiver` event) | SHOULD | SR-019 | 10 min |

MUST total: 75 min. Merge points: after V6 (unlocks L-V), at the end. **Drop order** (first to
last): VS6, VS5, VS4, VS3, VS2, VS1.

**The regression rule (R3, exactly).** In `policy.py` and its tests: a failing node is a
regression when an earlier `test-run` entry recorded the same node id `passed` or `flaky`,
whatever happened to its source since; a changed `test_hash` adds the note `test source changed
since the pass` and never clears the flag. Only a new test that starts red, a node id with no
earlier passing evidence, is exempt: it is `not yet passing`, never a regression, and never
interrupts.

Tests (`tests/verify/`), marked with their SR:

- `test_imports.py`, `test_markers.py` (V1): `test_import_edges_absolute_and_relative`,
  `test_transitive_closure`, `test_unresolvable_imports_ignored`,
  `test_collects_sr_markers_on_functions_and_classes`
- `test_testmap.py` (V2): `test_map_from_verified_by_links`, `test_map_from_sr_markers`,
  `test_map_from_import_closure`, `test_map_text_is_grepable`,
  `test_map_cache_reparses_only_changed_files`
- `test_select.py` (V3): `test_doc_only_selects_nothing`,
  `test_priority_order_verified_by_literal_import`,
  `test_infra_change_sets_full_pending_and_adds_nothing`,
  `test_unknown_coverage_samples_nearest_bounded`, `test_budget_defers_overflow`,
  `test_unknown_duration_counts_one_second`, `test_full_pending_cleared_by_full_run_evidence`,
  `test_selection_never_contains_whole_suite_marker`
- `test_plugin.py`, `test_runner.py` (V4): `test_plugin_reports_phases_and_exit_status`,
  `test_setup_failure_outranks_pass`, `test_collection_error_reported`,
  `test_run_never_passes_n_by_default`, `test_hard_limit_terminates_own_child`,
  `test_run_discarded_when_inputs_change`
- `test_evidence.py` (V5): `test_run_appends_test_run_entry_with_tree_and_env`,
  `test_fresh_pass_requires_matching_closure_test_and_env_key`,
  `test_reuse_miss_names_differing_part`, `test_index_rebuilt_from_log_after_cache_delete`,
  `test_env_key_changes_with_lock_and_python`
- `test_policy.py`, `test_cli_verify.py` (V6): `test_regression_requires_prior_pass_of_same_node`,
  `test_edited_test_that_passed_then_fails_is_regression` (its `test_hash` differs from the
  pass and `regression` is still true), `test_regression_notes_test_source_changed`,
  `test_new_red_test_is_not_regression`, `test_never_passed_existing_node_is_not_regression`,
  `test_run_prints_regression_instruction`, `test_tests_map_select_run_commands`,
  `test_aliases_map_and_verify`
- SHOULD: `test_removed_after_passing_listed` (VS1);
  `test_flaky_rerun_same_tree_records_both_attempts`, `test_no_rerun_when_tree_changed` (VS2);
  `test_identity_none_without_pyvenv`, `test_identity_cached_under_env_key`,
  `test_unknown_identity_never_reused` (VS3); `test_impact_lists_records_and_tests` (VS4);
  `test_map_from_naming` (VS5); `test_waiver_refused_under_marker`,
  `test_waiver_event_pinned_to_diff_digest` (VS6)

Runner tests start real pytest subprocesses; keep each temporary project to two or three tiny
tests so the lane suite stays under about 60 s.

## 7. Lane HOST (phase 3)

Goal: the Claude Code adapter: the four hooks, the status line, the skill, the CLAUDE.md block
and the installer. The installer comes before the prompt and stop hooks, so the first hooks can
be installed in plumb's repository at merge point H5 (L-H). Uses the real core and the fakes in
`tests/host/fakes.py` (`FakeVerify`, `FakeBackend`, `FakeCascade`); hook tests feed stdin JSON
built by the `hook_input` fixture.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| H1 | `hookio.py`: read stdin JSON, deadline, catch-all (exit 0, `check skipped` line, `errors.log`), output helpers (plain text, `systemMessage`, `decision: block`); `tests/host/fakes.py` | MUST | SR-014 | 10 min |
| H2 | `post_edit.py`: stdlib-only fast path appending to `touched.txt` | MUST | SR-011 | 5 min |
| H3 | `snapshot.py` (build `StatusSnapshot` from CoreAPI and VerifyAPI, write `status.json`) and `statusline.py` | MUST | SR-013 | 10 min |
| H4 | `session_start.py`: brief (about 30 lines, cap 40) plus evidence lines; writes the snapshot | MUST | SR-009 | 5 min |
| H5 | `install.py`: settings merge (registers only the hooks whose modules are present; async post-edit, `statusLine`, env marker, deny rules), launcher selection; skill and CLAUDE.md block; the `commit-msg` hook through BRIDGE's `install_commit_msg_hook` (degrades with a notice when missing); `cli.py` routes `hook`, `hooks install`, `install`, `statusline` | MUST | SR-015, SR-005 | 15 min |
| H6 | `prompt.py`: prompt log, relevant records with examples and tests (20 lines), intent-change flag through `get_backend` (degrades to `plumb: intent check unavailable`) and compare line, awaiting-confirmation line | MUST | SR-010 | 15 min |
| H7 | `stop.py`: changed paths, records and links, selection and evidence, `stated.json`, one block per turn (tests, trigger 2, trigger 3), summary with capped `proposed` lines; a new red test never asks | MUST | SR-012, SR-020 | 15 min |
| HS1 | `install.py`: `hooks uninstall`, `hooks status` | SHOULD | SR-015 | 10 min |
| HS2 | Slash command `.claude/commands/plumb.md` | SHOULD | SR-015 | 5 min |
| HS3 | In-process latency test (`test_latency.py`) | SHOULD | SR-014 | 10 min |
| HS4 | Queued escalations printed by the prompt and stop hooks | SHOULD | SR-024 | 5 min |
| HS5 | Escalation hint in the prompt hook (spec 6.2 step 5) | SHOULD | SR-010 | 10 min |

MUST total: 75 min. Merge points: after H5 (unlocks L-H for session start, edit tracking, the
status line and the guard), after H7 (unlocks L-H for prompt and stop, and the driven loop
check), at the end. **Drop order** (first to last): HS5, HS4, HS3, HS2, HS1.

Tests (`tests/host/`), marked with their SR:

- `test_hookio.py` (H1): `test_internal_error_exits_zero_with_notice`,
  `test_deadline_skips_with_budget_notice`, `test_block_output_shape`
- `test_post_edit.py` (H2): `test_appends_repo_relative_path`,
  `test_ignores_paths_outside_repo`, `test_fast_path_imports_no_yaml` (subprocess, checks
  `sys.modules`)
- `test_statusline.py` (H3): `test_renders_line_from_snapshot`,
  `test_full_pending_shown_only_when_pending`, `test_missing_snapshot`
- `test_session_start.py` (H4): `test_brief_about_30_lines_with_cap`,
  `test_brief_lists_awaiting_confirmation_and_drift`, `test_writes_status_snapshot`
- `test_install.py` (H5): `test_install_writes_hooks_statusline_env_and_deny_rules`,
  `test_install_registers_only_available_hooks`,
  `test_install_preserves_foreign_settings_and_is_idempotent`, `test_post_edit_registered_async`,
  `test_skill_about_20_lines_names_test_map_and_relay`, `test_claude_md_block_idempotent`,
  `test_install_calls_commit_msg_installer_or_notes_missing`, `test_launcher_selection`
- `test_prompt.py` (H6): `test_logs_prompt_digest_and_text_to_session`,
  `test_injects_named_records_first`, `test_injects_examples_and_tests_within_20_lines`,
  `test_intent_change_flag_on_confirmed_record_with_change_words`,
  `test_no_flag_on_proposed_record`, `test_compare_line_when_confirmed_records_injected`,
  `test_awaiting_confirmation_lists_stated_set_with_digest`, `test_backend_unavailable_degrades`
- `test_stop.py` (H7): `test_blocks_once_when_covering_tests_not_fresh`,
  `test_no_block_when_stop_hook_active`, `test_summary_when_evidence_fresh`,
  `test_summary_caps_proposed_lines`, `test_regression_blocks_with_owner_instruction`,
  `test_edited_test_regression_still_blocks`, `test_matters_dec_asked_once_per_hash`,
  `test_new_red_test_never_asks`, `test_doc_only_turn_prints_at_most_one_line`,
  `test_writes_stated_set`, `test_no_change_turn_prints_nothing`,
  `test_verify_unavailable_degrades`
- SHOULD: `test_uninstall_removes_only_plumb_entries` (HS1);
  `test_slash_command_brief_why_impact` (HS2); `test_hooks_within_in_process_budget` (HS3);
  `test_prints_queued_escalations` (HS4); `test_escalation_hint_on_many_features` (HS5)

## 8. Lane BRIDGE (phase 3)

Goal, in this order: the `SR:` trailer check and its `commit-msg` hook (concept 1a step 3), the
judgment interface with its heuristic default (used by the prompt hook's intent-change flag),
fidelity packets for the host agent (R4), and the claims check (KEEP list); then, with time
left, the cascade, the read-only importer and the JEV adapter. Extraction sources: spec 13
(`claims.py`, `substrate/judgment/*`, `register.py`). Uses the real core.

| # | Task | Tier | SR | Est. |
|---|---|---|---|---|
| B1 | `claims.py`: `check_msg` (unknown or malformed ID rejected; `require_trailer`; passes with a notice without `.plumb/`), `install_commit_msg_hook` (spec 12.2; leaves a foreign hook untouched and reports it); commands `trailers check-msg`, `trailers install-hook` | MUST | SR-007, SR-015 | 15 min |
| B2 | `judgment/model.py`, `tiers.py` (extracted: questions, answers, sealed records, fingerprint, `route` with version drift); `heuristic.py`; `get_backend` with `heuristic`, `disabled`, `fake` | MUST | SR-021, SR-010 | 25 min |
| B3 | `judgment/fidelity.py` and `cli.py`: `build_packet`, `unjudged`, `plumb fidelity`, `plumb judge` | MUST | SR-022 | 20 min |
| B4 | `claims.py`: `claims check` over a range, `claims.yaml` exempt globs and baseline | MUST | SR-007 | 15 min |
| BS1 | `judgment/cascade.py`: `HostAgentCascade` (queues to `escalations.jsonl`), `get_cascade`; `plumb judgment status` | SHOULD | SR-024, SR-021 | 15 min |
| BS2 | `importer/pi_factory.py`: SR, FEAT plus bundle, NC mapping, findings, dry run, `import` event; `importer/cli.py` | SHOULD | SR-023 | 40 min |
| BS3 | `judgment/state.py`, `jev.py`: tracked-files state with secret exclusion and truncation (extracted); `urllib` client with the pinned wire shapes, timeouts, fallback with one notice | SHOULD | SR-021 | 35 min |
| BS4 | Precision fixture for the intent-change heuristic (20 labelled prompts), result recorded in `docs/followups.md` | SHOULD | SR-010 | 15 min |

MUST total: 75 min. Merge points: after B1 (unlocks L-B), after B4 (MUST), at the end. **Drop
order** (first to last): BS4, BS3, BS2, BS1. BS2 fixtures: copies of `requirements/SR-077.md`
(structured bindings, acceptance), one SR with a `checksum:` field,
`docs/features/FEAT-001.md`, `bundles/FEAT-001.json` and `docs/nonconformances/NC-0002-*.md`
from `C:/coding/pi-agent-factory`, read once and saved under `tests/bridge/fixtures/pi_factory/`.

Tests (`tests/bridge/`), marked with their SR:

- `test_trailers.py` (B1): `test_check_msg_rejects_unknown_id`,
  `test_check_msg_requires_trailer_when_configured`, `test_check_msg_passes_without_plumb_dir`,
  `test_install_hook_writes_and_leaves_foreign_hook`, `test_install_hook_uses_installing_interpreter`,
  `test_trailers_cli`
- `test_tiers.py`, `test_heuristic.py` (B2): `test_route_thresholds`,
  `test_version_drift_suspends_accept`, `test_record_digest_detects_mutation`,
  `test_intent_change_flags_change_words_on_confirmed_match`, `test_no_flag_without_overlap`,
  `test_drift_triage_cosmetic_for_comment_only_change`,
  `test_drift_triage_material_for_logic_change`, `test_fidelity_is_unsure_escalate_llm`,
  `test_disabled_backend_is_unsure`, `test_jev_without_adapter_falls_back_with_notice`
- `test_fidelity.py` (B3): `test_packet_contains_statement_examples_ends_evidence`,
  `test_packet_truncates_deterministically`, `test_judge_appends_event_with_hashes`,
  `test_unjudged_after_end_change`, `test_judgment_never_confirms_or_freshens`,
  `test_merge_lists_unjudged_fidelity`
- `test_claims.py` (B4): `test_claims_reports_undeclared_paths`,
  `test_claims_default_exempt_globs`, `test_claims_baseline_entries`
- SHOULD: `test_cascade.py` (BS1): `test_host_agent_cascade_queues_instruction`,
  `test_escalate_human_only_with_trigger`, `test_judgment_status_never_prints_key`;
  `test_import_sr.py`, `test_import_feat_nc.py`, `test_import_readonly.py` (BS2):
  `test_imports_sr_fields_and_ac_examples`,
  `test_structured_bindings_become_links_pinned_when_ends_exist`,
  `test_missing_ends_reported_as_findings`, `test_legacy_checksum_verified_and_reported`,
  `test_all_imported_records_are_proposed`, `test_feature_membership_is_union_of_feat_and_bundle`,
  `test_membership_differences_reported`, `test_nc_read_leniently_keeps_corrected_by`,
  `test_id_collision_skipped_with_finding`, `test_source_tree_unchanged_after_import`,
  `test_dry_run_writes_nothing`, `test_import_event_logged`; `test_jev.py` (BS3, local stub
  `http.server` on 127.0.0.1, no network): `test_request_shape_matches_pinned_wire_format`,
  `test_parses_noul_choice_score_answers`, `test_timeout_falls_back_to_heuristic_with_one_notice`,
  `test_missing_key_uses_heuristic`, `test_key_never_read_from_repository`,
  `test_state_excludes_secret_paths_and_truncates`, `test_judgment_event_logged_with_fingerprint`;
  `test_intent_change_precision_fixture` (BS4)

## 9. Phase 4: integration (coordinator, on `main`)

The landing steps of 4.4 already ran as each lane landed. Phase 4 completes the integration:

1. Merge each lane's final branch head into `main` (`git merge --no-ff sp1/<lane>`, with the
   `SR:` trailer of its items): VERIFY, HOST, BRIDGE, and `core-rest` if it ran. Only
   `docs/followups.md` may conflict (keep both sections). Run `uv run plumb tests run --full`
   and ruff after each merge. Re-run `plumb hooks install` if HOST's final merge added a hook
   entry.
2. Conformance: `tests/integration/test_conformance.py` checks `open_core`, `open_verify`,
   `get_backend` and `get_cascade` (when built) against the protocols of spec 12.1 and HOST's
   fakes against the same shapes; fix any mismatch in the implementing lane's files.
3. `tests/integration/` (with `sr` markers):
   - `test_loop.py::test_loop_end_to_end`: temp repository with a small package and tests;
     `plumb init`, an `INT` and an `SR` with an example, `link` derives_from and verified_by,
     `hooks install`; then `hook session-start`, `hook prompt` (names the SR), `hook
     post-edit` on a source file, `hook stop` (expects one block asking for `plumb tests run
     --changed`), `tests run --changed` (expects a `test-run` entry), `hook stop` with
     `stop_hook_active` (expects a summary, no block), `statusline`. **Never dropped.**
   - `test_merge_boundary.py::test_merge_refused_then_allowed`: `validate --merge` exits 4,
     then 0 after `approve` run without the marker. **Never dropped.**
   - `test_loop.py::test_in_flow_confirmation`: stop writes the stated set, prompt "ok, go on"
     is logged, `relay` with that digest and quote confirms the SR; a neutral prompt confirms
     nothing.
   - `test_regression.py::test_regression_detected_and_reported`: a passing test breaks after a
     source edit and after an edit of the test itself; both are regressions; a new red test is
     not; the next stop summary shows `questions: regression`.
   - `test_latency_subprocess.py::test_hooks_end_to_end_under_two_seconds` (real subprocesses
     on the temp repository; asserts each hook under 2 s, records timings).
   - `test_dispatch.py::test_every_command_routes_and_helps`: `plumb <cmd> --help` exits 0 for
     every command of spec 9 that was built.
4. `scripts/bench_hooks.py`: runs each hook 20 times as subprocesses against a repository
   (default: the current one), prints p50 and p95 per hook and the prompt + stop sum. Run it on
   plumb's own repository. **Never dropped.**
5. plumb's own records: add the `implemented_by` and `verified_by` links for every module and
   test file on `main`, the `DEC` records the bootstrap left, `plumb repin`, `plumb tests map`.
6. Gate: `uv run pytest -q` and `uv run ruff check src tests` green on `main`; the dogfood
   checks of 4.6 pass.

## 10. Phase 5: review (on the dogfooded `main`)

- One intent verifier reads the merged, dogfooded result against the brief, rulings R1 to R7
  and the coordinator rulings of this plan. **Never dropped** while time remains before 07:15.
- With time left, one review agent per lane diff (`git diff <CORE merge base>..sp1/<lane>`),
  each checking the diff against the spec sections its lane implements and spec 10 latency
  rules. Severity follows R7: HIGH only for a contradiction or omission of the owner's words,
  decisions or rulings, or a defect that breaks a spec guarantee (for example a path that
  confirms a record without the owner's words, a hook that can block or exceed 2 s, or a
  regression rule that differs from R3).
- The coordinator fixes each HIGH finding test first, re-runs `uv run plumb tests run --full`,
  commits through plumb's `commit-msg` hook with `SR:` trailers, and appends medium and low
  findings to `docs/followups.md` under `## SP1 review (2026-10-06)`.

## 11. Time box, drop order and the morning minimum

**The morning minimum** is: CORE K1 to K7; the bootstrap's MUST part; VERIFY V1 to V6; HOST H1
to H7; BRIDGE B1 to B4; landing steps L-B, L-H (with the driven loop check) and L-V;
`test_loop_end_to_end`, `test_merge_refused_then_allowed` and the hook benchmark; the handoff.
That is the concept's dogfoodable core (concept 11, 1a): records, hashes, links, logs,
approvals with the guard, validation with the merge-boundary confirmation rule, trailers, the
four hooks, the status line, the installer, and the map, selection and runs with evidence and
the R3 regression rule, all set up on plumb's own repository. Every lane's MUST items fit in
about 75 min.

**Never dropped**, whatever the clock says: the R1 merge-boundary confirmation rule (K6), the
approval guard (K5's marker refusal and relay checks, H5's deny rules and marker), the R3
regression rule (V6), the `SR:` trailer check (B1), the bootstrap's MUST part, the landing
steps, the honest statement of the known limitation (4.5), and the handoff with its link to
`docs/fork-plan.md`.

**Order of protection** (highest first):

1. the morning minimum;
2. the rest of phase 4 (conformance, the other integration tests, the full link set);
3. phase 5 review (it can shrink to the single intent verifier);
4. SHOULD items, each lane in its own drop order.

**Cutting when time runs short**, in this order: SHOULD items (from the start of each lane's
drop order: BS4, VS6, HS5, KS5 first); lane reviewers (the intent verifier last); the
non-essential integration tests (`test_dispatch.py`, then `test_latency_subprocess.py`, then
`test_in_flow_confirmation`; the benchmark still runs). Dogfooding is never cut to make room
for review or SHOULD work.

**Phase drop rules** are in the table of section 1: CORE hands over at 03:15, the bootstrap
stops at 03:40, MUST merges are due by 05:30, lanes stop at 05:45, and review stops at 07:15.
A lane whose MUST item is still unfinished at 05:30 hands back what passes its gate; the
missing item is recorded in `docs/followups.md` and named at the top of the handoff as a
missing part of the morning minimum.

**Clock rule.** At **07:15 local on 2026-10-06** (the owner's 08:00 deadline minus 45 min),
whatever the state: the coordinator stops review and all SHOULD work, merges only what passes
its gate, records the rest in `docs/followups.md`, and writes and commits the handoff
(`docs/sp1-handoff.md`) by **07:45**.

**The handoff** says, in this order: what is on `main` and how to try it; the known limitation
(4.5) and that full interactive dogfooding starts when the owner opens Claude Code in
`C:/coding/plumb`; the morning question (`plumb validate --merge` exits 4; `plumb approve
--proposed` or "ok" confirms); any missing part of the morning minimum; every KEEP-list item
that was not built (for example the flaky rerun VS2, the content identity VS3, the importer
BS2), named against the owner's KEEP list; the plans for the owner, with `docs/fork-plan.md`
and its first owner decision.

If the JEV adapter (BS3) is not built, `judgment.backend: jev` falls back to the heuristic with
a notice, which the spec already requires. If the importer (BS2) is not built, `plumb import`
reports `not available in this build` (spec 12.3) and SR-023 stays proposed without code.

## 12. Definition of done

Spec section 14.2, checked by the coordinator after phase 4 and reported in the handoff:

- [ ] whole suite and ruff green on `main`;
- [ ] every command of spec 9 that was built exists, has a test, and appears in `plumb --help`;
      unbuilt SHOULD commands are listed in `docs/followups.md`;
- [ ] the end-to-end loop and merge-boundary integration tests pass (and the in-flow
      confirmation and regression tests, if not cut);
- [ ] guard tests pass and the installer writes the deny rules and the marker;
- [ ] `validate --merge` exits 4 then 0 in the integration test, and exits 4 on plumb's own
      records with every record awaiting the owner listed;
- [ ] the regression tests show R3 exactly: an edited test that passed and now fails is a
      regression; only a new red test is exempt;
- [ ] the bootstrap gate (4.3) and landing steps L-B, L-H and L-V passed; every commit since
      the bootstrap carries an `SR:` trailer, and the `commit-msg` hook has checked every
      commit since L-B;
- [ ] plumb's hooks are installed in `C:/coding/plumb/.claude/settings.json` and the driven
      loop check passed on plumb's own repository;
- [ ] hook benchmark within budget on plumb's own repository (or each miss recorded);
- [ ] dogfood checks of 4.6 pass;
- [ ] if the importer (BS2) was built: a read-only dry-run import of `C:/coding/pi-agent-factory`
      reports findings and changes nothing there;
- [ ] `plumb judgment status` reports `heuristic` if BS1 was built; JEV tests pass on the local
      stub if BS3 was built;
- [ ] unfinished items, medium and low findings in `docs/followups.md`; no HIGH finding open;
- [ ] **`docs/fork-plan.md` exists on `main`** (D9, D10). A later workflow phase writes it,
      outside the lanes; the handoff links it and names its first owner decision. An earlier
      draft at `docs/plans/fork-plan.md` is input to that phase, which replaces it;
- [ ] the handoff states the known limitation of 4.5 honestly and is committed on `main` by
      07:45 local on 2026-10-06.

## 13. Risks

| Risk | Mitigation |
|---|---|
| CORE overruns and delays everything | CORE's MUST list is only the ruling's items (75 min); no SHOULD work in phase 1; at 03:15 unfinished MUST items move to `core-rest` in phase 3 and the bootstrap starts with what exists |
| Three lanes contend for 2 cores | At most two whole-lane suite runs at the same moment; focused tests while iterating; runner tests use tiny temporary projects; no xdist |
| A lane's MUST items overrun | SHOULD items absorb it first, in each lane's drop order; MUST merges are due by 05:30, 45 min after the nominal end |
| Contract gaps found mid-lane | One coordinator owns contract changes; lanes move to their next item meanwhile; lanes build on the real core, so fewer contracts exist than before |
| The build agents never run under plumb's hooks | Stated as a known limitation (4.5); the driven loop check proves the hooks on plumb's repository; lanes use plumb's CLI (brief, status, validate, markers) while they build; interactive dogfooding starts with the owner's first session in `C:/coding/plumb` |
| A plumb hook misbehaves on plumb's repository after L-H | Hooks always exit 0 and block at most once per turn; `git revert` of the install commit until `hooks uninstall` lands; the failure is recorded |
| The `commit-msg` hook blocks a lane commit | Lanes take trailers from their task tables; the check passes with a notice where a checkout has no `.plumb/` |
| Interpreter start (about 225 ms here) eats the hook budget | Async post-edit hook, deny rules instead of a per-call guard hook, lazy imports, index cache (KS1), benchmark in phase 4 |
| The deadline is passed while work is still going | Every cutoff is an absolute local time (section 1): CORE 03:15, bootstrap 03:40, MUST merges 05:30, lane stop 05:45, clock rule 07:15, handoff 07:45, deadline 08:00 |
| Union merges of JSONL logs | Chain forks accepted by design (spec 5.7); validated by `test_union_merged_fork_accepted` |
