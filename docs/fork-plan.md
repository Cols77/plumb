# pi-agent-factory to iaso: fork plan

This plan answers two owner decisions recorded in the intent brief (2026-10-05):

- D9: "consider stopping developments on pi-agent-factory if it takes too much RAM". The
  brief records the outcome: pi-agent-factory goes into maintenance mode after the current
  integration batch lands, new feature work moves to iaso, and "A fork plan is required."
- D10: "... and then also plan for the work needed for dogfooding and the kind of
  pi-agent-factory fork that is about to happen."

It also serves D3 ("I guess the CLI / lib can be re-used from pi-agent-factory?": reuse by
extraction, not forking), D4 (a simpler record model with an importer; "be careful about
loosing some important features, for example the hash is important for staleness
detection"), D7 (reuse the existing SR and FEAT artifacts) and D8 (JEV as an optional
judgment backend: "I think it might be usefull to integrate it in this new version too?").

The dogfooding work is planned in `docs/plans/sp1-plan.md`. This document plans the fork.
It replaces the draft that was at `docs/plans/fork-plan.md`. The owner does not review it
(D11); verifier agents check it against the brief, rulings R1 to R7, `docs/concept.md`
sections 10 and 11, and `docs/specs/sp1-grounding-loop.md` sections 8, 13 and 15.

Facts in this document were read on 2026-10-06 from `C:/coding/pi-agent-factory` and its
worktree `.worktrees/nc-t120`, read-only (files, `git log`, `git show`, `git ls-tree` and
`git archive` only). Nothing was written there.

## Contents

1. What "fork" means here
2. Rules that hold in every phase
3. pi-agent-factory maintenance mode
4. Extraction: what was extracted, and what remains
5. The importer: usage, and reading pi-agent-factory's register today
6. JEV (FEAT-022) and the intent-confirmed fast track (FEAT-023) in iaso
7. Migration steps and their order
8. Risks
9. Owner decisions this plan needs
10. State at handoff

## 1. What "fork" means here

The fork is a split of development, not a git fork (concept 10, D3):

- iaso copies selected pi-agent-factory modules with their tests and simplifies them. It
  never imports `factory.*`, `coherence.*` or `substrate.*`, and has no runtime dependency on
  pi-agent-factory.
- pi-agent-factory's records (SR, FEAT, NC, bundles, claims) reach iaso through a read-only
  importer that never manufactures a confirmation (R2).
- pi-agent-factory takes fixes only once the current integration batch has landed. New
  feature work happens in iaso.
- The per-turn admission and coordination weight is not carried over, nor anything on the
  brief's DROP list: "the planning run state machine, consent phrases, manifests and handoff
  hashes, review swarms, and governed execution as the default".

## 2. Rules that hold in every phase

- No iaso session writes inside `C:/coding/pi-agent-factory` or its worktrees, creates
  worktrees of it, or runs its `coherence` or `factory` commands, until phase F4, and in F4
  only on the owner's explicit go-ahead. Reading files and read-only git commands are allowed.
- pi-agent-factory's own guarded integration process owns every change to that repository
  before F4. iaso does not touch an integration in progress there.
- Every imported record arrives `proposed`. Only the owner confirms (R2). A `by: import`
  approval is allowed only where an upstream owner approval or consent pins the record's
  current content (concept 10); sub-project 1 accepts none (followups, CORE lane).
- pi-agent-factory's register is never imported into iaso's own repository. Both number
  their requirements from SR-001, so the IDs collide (the importer would skip them). The
  import target is a scratch copy (F3) or pi-agent-factory itself (F4).
- Each phase has a gate. The next phase starts only when its gate passes.

## 3. pi-agent-factory maintenance mode

### 3.1 The batch that must land first (phase F0)

The batch in flight on 2026-10-06, as named by pi-agent-factory's plans in
`docs/coherence/plans/`:

| Plan | Tasks | NCs | On `main` (341e2a08) |
|---|---|---|---|
| `2026-10-04-validation-runtime-and-evidence.md` | T-115, T-116, T-117 | NC-0021, NC-0022 | T-115, T-116 |
| `2026-10-04-safe-integration.md` | T-117 to T-120 | NC-0020, NC-0021 | T-118, T-119, T-120 (in part) |
| `2026-10-04-unit-suite-runtime.md` | T-121, T-122 | | T-121, T-122 |
| `2026-10-04-claim-correction.md` | T-123 | NC-0021, NC-0022 | T-123 |

The worktree `.worktrees/nc-t120` is one commit ahead of `main` (a4d721b6, the T-120
publication step, branch `fix/publish-config-eol`). No commit names T-117 on either.
NC-0021 and NC-0022 are still `open`; NC-0020 is `corrected`.

The batch is finished by pi-agent-factory's own guarded process, not by iaso agents. This
plan adds no work to it.

**Gate F0.** The batch's branches are merged on pi-agent-factory's `main` through its own
integration, its `full` gate is green there, and the owner says the batch has landed.

### 3.2 What continues

After gate F0, pi-agent-factory accepts:

- bug fixes, nonconformance corrections (NC-0021 and NC-0022 if still open, and any new
  NC), security fixes, and dependency updates needed to keep the tool running;
- the completion of runs that other sessions depend on, each only to its next stopping
  point, under the owner's standing authority already recorded for that repository:
  - the T-120 publication (`fix/publish-config-eol`) and whatever else closes the batch;
  - the COHERENCE-ARTIFACT-LOCATION run: the rest of T-110 and T-111, which close NC-0003.
    These are corrections, not features, so they may finish. The FEAT-023 refresh inside
    T-110 is not needed once FEAT-023 moves to iaso (section 6.3); the owner decides
    whether to skip it;
- reading: its register, plans and evidence stay the reference for the importer and for
  sub-projects 2 and 5;
- the Pi extensions (`pi-ext/factory-watch`, `pi-ext/scope-guard`) stay usable until iaso's
  Pi adapter exists (sub-project 4).

### 3.3 What stops

- new FEAT and SR records, new planning runs and new features. A new feature request becomes
  an `INT` record in the iaso repository instead;
- long governed executions and dispatches started by default. This is the RAM concern of D9;
- the held feature runs do not resume there. JEV T-077 to T-088 (FEAT-022) and the
  intent-confirmed fast track T-089 to T-104 (FEAT-023) were both on hold on 2026-10-04
  (T-077 and IFT-T-090 by the owner; IFT-T-089 had failed its retries). Their intent moves to
  iaso as mapped in section 6. Their branches (`dispatch/IFT-T-089-*`, `dispatch/IFT-T-090-*`,
  `plan/intent-confirmed-fast-track`) are left as they are; the owner may delete them later.

### 3.4 The maintenance notice (phase F1)

After gate F0, the owner, or a pi-agent-factory session the owner starts, adds a short notice
to pi-agent-factory's `AGENTS.md` and `README.md` stating sections 3.2 and 3.3. A iaso
session does not write it.

**Gate F1.** The notice is on pi-agent-factory's `main`, and the owner has seen it.

## 4. Extraction: what was extracted, and what remains

### 4.1 Extracted in sub-project 1

Source: `C:/coding/pi-agent-factory/.worktrees/nc-t120/src`, branch `fix/publish-config-eol`
(HEAD a4d721b6 on 2026-10-06; the lanes copied from the same branch during the night). Every
row of spec 13 was built:

| iaso module | Extracted from | iaso SR |
|---|---|---|
| `model.py`, `store.py` | `coherence/register/register.py` | SR-001 |
| `claims.py` (+ `trailers.py`) | `coherence/register/claims.py` | SR-007 |
| `links.py` | `coherence/register/relations.py` | SR-003 |
| `normalize.py`, `hashing.py` | `substrate/freshness/fingerprint.py` | SR-002 |
| `verify/imports.py` | `substrate/codemap/imports.py` | SR-016 |
| `verify/markers.py` | `coherence/register/markers.py` | SR-016 |
| `verify/select.py`, `verify/policy.py` | `coherence/integration/failure_policy.py` | SR-017, SR-019 |
| `verify/pytest_plugin.py` | `coherence/execution/pytest_evidence_plugin.py` | SR-018 |
| `verify/envid.py` | `coherence/integration/evidence.py` (content identity) | SR-018 |
| `judgment/model.py`, `tiers.py`, `state.py` | `substrate/judgment/{model,tiers,config,state}.py` | SR-021 |
| `importer/pi_factory.py` | `coherence/register/register.py` (`parse_requirement`, `content_checksum`) | SR-023 |

Written new rather than extracted: the approvals, relay and confirmation guard
(`approvals.py`, `confirm.py`), the hash-chained log (`log.py`), the merge boundary
(`merge.py`), the Claude Code adapter (`hosts/claude_code/*`), the test map, runner and
evidence store (`verify/testmap.py`, `runner.py`, `evidence.py`), the live JEV client
(`judgment/jev.py`; pi-agent-factory had only disabled and fake clients), the heuristic
backend, the host-agent cascade and fidelity packets (`judgment/heuristic.py`, `cascade.py`,
`fidelity.py`).

### 4.2 Resync after the batch lands (phase F2)

The source worktree was a batch in progress, so the copies can lag what finally lands:

1. Record the pi-agent-factory `main` commit that closes the batch as the extraction
   baseline (section 10).
2. For each row of 4.1, diff the source module at a4d721b6 against the same module at the
   baseline. Port each behavioural change test first, or record in `docs/followups.md` why it
   does not apply to iaso (for example a change to admission or coordination code). Known
   candidates: the claim-correction overlay in `coherence/register/claims.py` (iaso uses an
   NC-backed baseline instead) and the evidence and failure-policy code under
   `coherence/integration/`.

**Gate F2.** Every row of 4.1 is resynced to the baseline or has a followup entry. iaso's
whole suite and `ruff` are green, and `iaso validate` reports no errors on iaso's records.

### 4.3 Remaining extraction candidates

Extracted only when the sub-project named needs them, from the baseline of 4.2, never from
the older worktree:

| Candidate (source under `src/`) | What iaso would use it for | Sub-project |
|---|---|---|
| `substrate/codemap/sigs.py`, `model.py` | symbol-level link ends (`path::name`, KS4), so an edit elsewhere in a file no longer stales a link; also relinks the 148 `symbol-narrowed` import findings | 1 (rest) |
| `coherence/register/claims.py` `check_commit` message exemptions | accept `git revert`, `merge` and `--fixup` messages whose paths are all exempt (BRIDGE followup B1) | 1 (rest) |
| `coherence/planning/intent.py` (teach-back, revision) | `iaso intent`: read-back revision and supersession of INT records | 2 |
| `coherence/register/overlap.py`, `substrate/codemap/imports.py` overlap functions | candidate owning requirements for an undeclared changed path (JEV T-088, NC-0011) | 2 |
| `coherence/trace/suspect.py`, `propose.py` | proposed (never asserted) links for drift signals | 2 |
| `coherence/register/fidelity_packet.py`, `fidelity_findings.py` | feature-level (bundle) fidelity packets (JEV T-086) | 2 |
| `coherence/execution/flaky_registry.py`, `suite_plan.py`, `pytest_suite.py` | the merge-boundary full run that satisfies `full verification pending` | 3 |
| `coherence/integration/evidence.py` (promotion), `closure.py` | evidence promotion and claims audit over a range | 3 |
| `coherence/register/ingest.py` | `evidence/runs/ingest-*.json` `commits[]` into the claims checkpoint | 5 |
| `coherence/mirrors/generate.py`, `render.py` | keep FEAT documents' derived "Related requirements" blocks readable after import | 5 |
| `coherence/navigate/*` (brief, matrix, scope) | only if `iaso brief`, `why` and `show` need more than they have; prefer iaso's own queries | 5 or never |

Not candidates (DROP list and non-goals): `coherence/planning/*` run state, `coherence/runs`,
`coherence/gate`, `coherence/policy` and `substrate/policy` (policy compiler), handoffs and
manifests, `coherence/execution/driver_factory.py` and the governed driver,
`coherence/audit` dispatch, `coherence/simulation`, `coherence/course`, `coherence/goals`,
the `factory.*` shims and the admission and coordination hooks. `coherence/measurement` is
not planned; it returns only if an owner decision asks for measured acceptance criteria.

## 5. The importer: usage, and reading pi-agent-factory's register today

### 5.1 Usage

```text
iaso import pi-agent-factory <source> [--dry-run] [--only SR,FEAT,NC] [--json] [--root <target>]
```

- `<source>` is a pi-agent-factory checkout. It is opened read-only; no git command runs in
  it (`HEAD` is read from `.git` files).
- The target is the repository that `--root` names (default: the current one), after
  `iaso init`. `--dry-run` writes nothing and prints the findings.
- Mapping (spec 8.1): `requirements/SR-*.md` become requirements, with `acceptance` as
  `AC-n` examples and `upstream`, `relates_to`, `implemented_by`, `verified_by` as links,
  pinned when their ends exist in the target; legacy `checksum:` values are verified;
  `docs/features/FEAT-*.md` plus `bundles/*.json` become features whose membership is the
  union of both; `docs/nonconformances/NC-*.md` become NCs, read leniently.
- Every imported record is `proposed`. One `import` event records the source path, its
  `HEAD`, the counts and a findings digest.

Finding kinds: `missing-end` (a binding's file does not exist in the target),
`symbol-narrowed` (a `path` + `symbol` binding linked as the whole file until KS4),
`relation-skipped` (a relation to a non-requirement, such as `spec:SPEC-*`),
`checksum-ok` or a checksum mismatch, `membership-difference` (FEAT document and bundle
disagree), and an ID already present in the target (skipped).

Not built yet (sub-project 5): `.factory/trace-claims.yaml` to `.iaso/claims.yaml`, the
ingest checkpoint, `by: import` approvals, and symbol ends.

### 5.2 Reading pi-agent-factory's register with iaso today

Two recipes, both read-only on pi-agent-factory. The paths are examples; use a scratch
directory.

**Findings only (no copy).** An empty target, so every binding is a `missing-end`:

```bash
mkdir -p "$SCRATCH/probe" && git -C "$SCRATCH/probe" init -q
uv run iaso init --root "$SCRATCH/probe"
uv run iaso import pi-agent-factory C:/coding/pi-agent-factory --dry-run --root "$SCRATCH/probe"
```

**The register with its code (exported copy).** `git archive` only reads the repository.
This gives iaso's view of pi-agent-factory as F4 would see it:

```bash
mkdir -p "$SCRATCH/paf" && git -C C:/coding/pi-agent-factory archive main | tar -x -C "$SCRATCH/paf"
git -C "$SCRATCH/paf" init -q && uv run iaso init --root "$SCRATCH/paf"
uv run iaso import pi-agent-factory C:/coding/pi-agent-factory --root "$SCRATCH/paf"
uv run iaso validate --root "$SCRATCH/paf"   # then: status, drift, brief, fidelity <SR>
```

Both commands are run from the iaso checkout. The source path is the main checkout; its
`HEAD` must equal the archived commit for the links to pin the same content.

Observed on 2026-10-06 (source `HEAD` 341e2a08, `main`):

| | Findings only | Exported copy |
|---|---|---|
| Records | 85 SR, 24 FEAT, 22 NC | same, written |
| Findings | 958: 789 `missing-end`, 148 `symbol-narrowed`, 8 `relation-skipped`, 7 `checksum-ok`, 6 `membership-difference` | 219: 50 `missing-end`, 148 `symbol-narrowed`, 8 `relation-skipped`, 7 `checksum-ok`, 6 `membership-difference` |
| Time | about 1 s | import 2 min 14 s; `validate` 1.2 s, `drift` 1.6 s, `status` and `brief` 5.9 s |
| `iaso validate` | | 0 errors, 86 warnings, 131 records proposed |
| Links | | 550 current, 0 stale, 0 dangling |

Reading the findings:

- the 50 `missing-end` in the copy are `verified_by` tests that requirements name before
  they exist (for example SR-077 and SR-078 name JEV tests not yet written, SR-091 names an
  artifact-location test). They are real gaps, not import errors;
- the 6 membership differences: FEAT-001 (SR-050, SR-057, SR-058, SR-064 only in the
  document), FEAT-002 (SR-059, SR-063), FEAT-010 (SR-056), and no bundle for FEAT-018,
  FEAT-019, FEAT-020. Each needs an owner decision in F3, because it changes meaning;
- the 8 skipped relations point at `spec:SPEC-*` documents, which iaso does not model as
  records. Sub-project 5 decides whether they become `relates_to` path links;
- the `status` and `brief` time at this scale exceeds the hook budget (risk K3, section 8).

## 6. JEV (FEAT-022) and the intent-confirmed fast track (FEAT-023) in iaso

### 6.1 Principles of the mapping

- JEV is optional (D8): iaso works without it, and every JEV-assisted path has a heuristic
  or host-agent path. A judgment only orders, filters, annotates and proposes. It never
  confirms a record, freshens evidence or passes the merge boundary (spec 8.2; tested by
  `tests/bridge/test_fidelity.py::test_judgment_never_confirms_or_freshens`). This is
  FEAT-022's own authority boundary.
- iaso has no planning runs, review points, review swarms or governed execution, so any
  task whose subject is one of those is dropped, and its intent is kept only where it serves
  the owner's interaction model (D5: background, questions only on the three triggers).
- Confirmation needs the owner's explicit words (R2) and every touched requirement must be
  confirmed at the merge boundary (R1). No fast track replaces that.
- New iaso requirements written for this work are iaso's own SRs (numbered in iaso). They
  cite the pi-agent-factory SR they come from in their body, since the two numberings
  overlap.

### 6.2 FEAT-022 (JEV-assisted review), tasks T-077 to T-088

T-075 (vendor contract, landed and deferred) and T-076 (judgment core, done 2026-10-03,
hardened 2026-10-04) are pi-agent-factory history; iaso extracted the core of T-076 (4.1)
and the wire shapes T-075 pinned.

| Task | Subject | In iaso | Sub-project |
|---|---|---|---|
| T-077 | TypeSafe client with hard fail-safe | Built: `judgment/jev.py`, 800 ms hook timeout, no retries in hooks, heuristic fallback (SR-021). Remaining: measure on the live service against the hook budget | 2 |
| T-078 | planning review triage annotation | No planning reviews. Kept as: JEV `drift_triage` orders drift signals (cosmetic or material) in the end-of-turn summary and `iaso drift` | 2 |
| T-079 | inbox, reviewer ordering, decision queue | Reviewer ordering dropped (no review swarms). Kept as: the merge boundary's "awaiting your confirmation" list ordered by judgment, never filtered | 3 |
| T-080 | benchmark and threshold validation | Partly built: the 20-prompt intent-change fixture (precision 1.0, recall 0.5 for the heuristic) and `judgment.jev.validated_against`. Remaining: measure JEV on real prompts from `.iaso/session/intent_flags.jsonl` | 2 |
| T-081 | host adapters (Claude Code, Hermes, Pi) | Claude Code built (hooks call the backend). Hermes and Pi with the other adapters | 4 |
| T-082 | judgment-first LLM offload, advisory cascade | Cascade built (`HostAgentCascade`, SR-024). Offload inside governed review workflows dropped | 1 (done) |
| T-083 | staleness triage | Built: heuristic `drift_triage` and the JEV question. Detection stays hash-based (D4) | 1 (done), ordering in 2 |
| T-084 | intent-capture challenges | Kept as: ambiguity surfaced as `DEC` records ("I assumed A; B also fits"), proposed by the heuristic or JEV on a captured read-back | 2 |
| T-085 | JEV as the SR-058 overlap judge | Kept as an advisory "possible duplicate requirement" note when a new SR is written | 2 (SHOULD) |
| T-086 | whole-bundle alignment review | Per-requirement fidelity packets built (SR-022). Feature-level packet over a FEAT's members | 2 |
| T-087 | authority boundary across integration points | Built as an invariant test; each new integration point adds its case | every sub-project |
| T-088 | ownership, justification and verification-reference proposals | Kept as: `iaso claims check` proposes the owning SR of an undeclared path from the import closure, and a covering test for an uncovered example. Proposals only | 2 or 3 |

### 6.3 FEAT-023 (intent-confirmed fast track), tasks T-089 to T-104

FEAT-023's premise, "the human confirms intent rather than approve artifacts", is iaso's
model: INT records carry the owner's quote, a read-back with will, won't and labelled
assumptions, and examples the owner confirms (D2). Its fast-track machinery assumed
pi-agent-factory's review points and automatic consent, which iaso does not have.

| Task | Subject | In iaso | Sub-project |
|---|---|---|---|
| T-089 | measure a local grounding specialist, OpenRouter findings | Not carried as a build task. Its records, if they land, inform the choice of a second judgment backend | none |
| T-090 | fast-track policy core and automatic decisions | Dropped: there are no review points to decide automatically; interaction A and R1 replace it | none |
| T-091 | calibration ledger, fixed-sequence bound, claim-kind registry | Kept in small form: judgments and owner decisions are already logged events; a calibration report compares them before a JEV threshold changes | 2 (SHOULD) |
| T-092 | label mapping, wrong-fast-track records, success report | Folded into the calibration report of T-091 | 2 (SHOULD) |
| T-093 | claim decomposition, cite-span check, bounded judge context | Kept as an advisory check: a requirement derived from an INT cites a verbatim span of its quote; the fidelity packet stays bounded (4,000 characters per end) | 2 |
| T-094 | local grounding specialist judge | Deferred: a possible additional backend behind the judgment interface | after 2 |
| T-095 | hosted OpenAI-compatible judge slot | Deferred, same reason. iaso's LLM is the host agent (R4) | after 2 |
| T-096 | judge ensemble, version drift, automatic disable | Version drift built (`validated_against` turns `accept` into `escalate-llm`). Ensemble deferred | 1 (part) |
| T-097 | teach-back at capture finalize | Built in shape: the INT read-back, shown `proposed` in the end-of-turn summary (R1). The helper command `iaso intent` | 2 |
| T-098 | intent revision, confirm-intent, supersession | Confirmation built (`iaso approve`, guarded `iaso relay`). Revision and supersession of INT records | 2 |
| T-099 | planning points A and B | Dropped (no planning review points). The merge boundary is the one point | none |
| T-100 | execution points C and D | Dropped (no governed execution review) | none |
| T-101 | consent point E, automatic consent for intent-entailed SRs | Dropped: it contradicts R2. An SR entailed by a confirmed INT is still confirmed by the owner, in one line, at the latest at the merge boundary | none |
| T-102 | standing delegation for merge and push | Not carried: iaso never merges or pushes. Revisit only if an adapter gains such an action | none |
| T-103 | cross-point proof and authority boundary | Folded into the authority invariant of T-087 | every sub-project |
| T-104 | shadow mode end to end, documentation, first labels | Folded into the T-091 calibration report, if built | 2 (SHOULD) |

The FEAT-022 and FEAT-023 records themselves (SR-077 to SR-090) stay in pi-agent-factory's
register. They arrive in iaso's form only through the F4 import of pi-agent-factory, as
`proposed` records of that repository.

### 6.4 Where they land in iaso's roadmap

Sub-project 2 of the concept ("intent capture and escalation") is the home of most of
sections 6.2 and 6.3: `iaso intent`, `iaso example`, `iaso decide`, the escalation
triggers and set approvals, the JEV live measurements, drift ordering, decision proposals,
cite-span checks and feature-level fidelity. Sub-project 3 takes the ordered confirmation
list and the claims proposals at the merge boundary; sub-project 4 the Hermes and Pi
adapters. Each item enters iaso as an `INT` read-back first, then SRs with examples, as the
concept requires for any work.

## 7. Migration steps and their order

| Phase | Steps | Gate | Who | When |
|---|---|---|---|---|
| F0 | The current batch lands (3.1) | F0 (3.1) | pi-agent-factory's process | in progress on 2026-10-06 |
| F1 | Maintenance notice (3.4); held runs stay held (3.3) | F1 (3.4) | the owner, or a session the owner starts there | right after F0 |
| F2 | Record the baseline; resync the extracted modules (4.2) | F2 (4.2) | iaso sessions | right after F0 |
| F3 | Import rehearsal on an exported copy of the baseline (below) | F3 | iaso sessions; the owner decides meaning-changing findings | after F2; repeat after sub-project 5 |
| F4 | The switch (below) | F4 | an owner-started session, on the owner's go-ahead | after sub-projects 4 and 5 |

Sub-projects 2 and 3 of iaso run in parallel with F1 to F3; they need nothing from
pi-agent-factory but its documents.

**F3, import rehearsal.** All in a scratch directory, with the recipe of 5.2 on the F2
baseline:

1. Dry run, then a real import into the exported copy. The output is the list of findings.
2. The findings go into a iaso `docs/` report and the next handoff. The owner decides each
   finding that changes meaning (the membership differences, the skipped `spec:` relations).
   Mechanical ones (formatting, a moved path) are fixed in the importer, test first.
3. Two consecutive imports of the same baseline give identical output (the import is
   deterministic), and pi-agent-factory's `HEAD` is still the baseline.

**Gate F3.** Two identical runs, every finding explained or decided, and the copy's
`iaso validate` shows 0 errors.

**F4, the switch.** It needs the full importer (sub-project 5: claims, ingest checkpoint,
`by: import` approvals, symbol ends) and, for Pi users, iaso's Pi adapter (sub-project 4).
It starts only on the owner's explicit go-ahead, in the owner's words. On a branch of
pi-agent-factory:

1. `iaso init` and the import, against the branch itself.
2. `iaso hooks install` for the host the owner uses there. pi-agent-factory's per-turn
   coherence hooks are disabled on that branch, so a turn never runs both.
3. `SR:` trailers keep their IDs, so history keeps its meaning. `iaso claims check` must
   accept the branch's commits, with an NC-backed baseline for any historical pair it cannot.
4. The modules iaso now owns are retired in pi-agent-factory one at a time, each a fix-only
   change its own gate accepts, until only what iaso does not cover remains (governed
   execution, kept for whoever still uses it).
5. Merge through pi-agent-factory's own process. This is an owner merge boundary: iaso's
   `validate --merge` must exit 0, so every touched imported requirement is confirmed by the
   owner (R1).

**Gate F4.** The branch merged with both gates green (pi-agent-factory's `full` gate and
iaso's `validate --merge`), and the owner works in pi-agent-factory through iaso's loop.

**Rollback.** Until F4 merges, pi-agent-factory's records remain the source of truth and
abandoning the branch undoes the switch. After F4, `iaso hooks uninstall` and a revert of
the switch merge restore the previous setup; the imported `.iaso/` stays as a read-only
record.

## 8. Risks

| ID | Risk | Mitigation |
|---|---|---|
| K1 | A iaso session writes into pi-agent-factory while its guarded integration runs, or another session merges there mid-run (NC-0021) | Section 2: read-only until F4; scratch copies via `git archive`; F4 only on the owner's go-ahead |
| K2 | The extracted copies lag the batch (a4d721b6 versus the final `main`) | F2 resync, row by row, before F3 |
| K3 | At pi-agent-factory's scale (131 records, 550 links) `iaso status` and `brief` take about 5.9 s, over the 2 s hook budget; `validate` 1.2 s | Before F4: the KS1 index and hash caches, then a measured hook benchmark on the exported copy. F4 is blocked until hooks are under budget there |
| K4 | The import takes 2 min 14 s on the exported copy | Acceptable for a one-off command; measured again in F3. Sub-project 5 pins links in one pass if it stays slow |
| K5 | Whole-file link ends (148 symbol-narrowed bindings) stale on any edit, which invites mass `repin` and weakens the staleness signal D4 protects | KS4 symbol ends before F4; `repin` stays per link and logged |
| K6 | Imported records look confirmed, or the agent confirms them in bulk | Every import is `proposed`; `by: import` only with a pinned upstream approval; the merge boundary lists agent-relayed approvals (R2) |
| K7 | Meaning-changing import findings are resolved silently | They are owner decisions in F3; the importer reports, never resolves |
| K8 | SR ID collision between iaso's own records and pi-agent-factory's | Never import into iaso's repository (section 2); new iaso SRs cite pi-agent-factory IDs in their body |
| K9 | Held runs (JEV T-077, IFT T-089 and T-090) are resumed in pi-agent-factory by a session unaware of maintenance mode, costing RAM and time | The F1 notice; the held-run list in 3.3; the owner decides each branch |
| K10 | Work dropped from FEAT-023 (automatic consent, standing delegation) was wanted by the owner | Dropped only where it contradicts R2 or has no subject in iaso; the owner can reopen any row of 6.3 with a new INT |
| K11 | JEV is unavailable, slow or changes version | Optional by design: heuristic fallback, 800 ms hook timeout, `validated_against` downgrades `accept` |
| K12 | Two development lines diverge: fixes land in pi-agent-factory modules iaso already copied | F2 diff on each fix touching a 4.1 row, until F4 retires the module there |
| K13 | Pi users lose their tools before iaso's Pi adapter exists | The Pi extensions stay in maintenance (3.2); F4 waits for sub-project 4 |

## 9. Owner decisions this plan needs

In order:

1. Gate F0: the batch has landed (and whether T-117 is still part of it).
2. Gate F1: the maintenance notice, and what happens to the held branches of 3.3.
3. Whether the FEAT-023 refresh inside pi-agent-factory's T-110 is skipped (3.2).
4. The meaning-changing findings of F3 (the six membership differences, the `spec:`
   relations).
5. The go-ahead for F4, in the owner's words.

## 10. State at handoff

- Extraction source used by sub-project 1: `C:/coding/pi-agent-factory/.worktrees/nc-t120`,
  branch `fix/publish-config-eol`, HEAD a4d721b6 on 2026-10-06.
- Spec 13 rows built: all eleven (section 4.1).
- Importer: built (spec 8.1, BRIDGE BS2); findings and timings in 5.2.
- JEV adapter: built (BS3); without a key, `iaso judgment status` reports `heuristic`.
- Extraction baseline (F2 step 1): not yet known; gate F0 has not passed.
- pi-agent-factory `main` on 2026-10-06: 341e2a08.
