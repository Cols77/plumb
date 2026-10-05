# pi-agent-factory fork plan

This plan answers two owner decisions recorded in the intent brief (2026-10-05):

- D9: "consider stopping developments on pi-agent-factory if it takes too much RAM". The
  brief records the outcome: pi-agent-factory goes into maintenance mode after the current
  integration batch lands, new feature work moves to plumb, and "A fork plan is required."
- D10: "... and then also plan for the work needed for dogfooding and the kind of
  pi-agent-factory fork that is about to happen."

The dogfooding work is planned in `docs/plans/sp1-plan.md`. This document plans the fork. The
owner does not review it; verifier agents check it against the brief, rulings R1 to R7,
`docs/concept.md` section 10 and `docs/specs/sp1-grounding-loop.md` section 13.

## 1. What "fork" means here

The fork is a split of development, not a git fork. The concept fixes how it is done
(concept 10 and 12, decision D3: "Reuse pi-agent-factory code by EXTRACTION, not forking"):

- plumb copies selected pi-agent-factory modules with their tests and simplifies them. It
  never imports `factory.*`, `coherence.*` or `substrate.*`, and has no runtime dependency on
  pi-agent-factory.
- pi-agent-factory's records (SR, FEAT, NC, bundles, claims) move to plumb through a
  read-only importer that never manufactures a confirmation.
- pi-agent-factory itself takes fixes only once the current integration batch has landed,
  and new feature work happens in plumb.
- The per-turn admission and coordination weight, the planning run state machine, consent
  phrases, manifests, handoff hashes, review swarms and governed execution as the default are
  not carried over (brief, decision 4 DROP list).

## 2. Rules that hold in every phase

- No plumb session writes inside `C:/coding/pi-agent-factory` or its worktrees, creates
  worktrees of it, or runs its `coherence` or `factory` commands until phase F4, and in F4
  only on the owner's explicit go-ahead (section 7). Reading files is allowed.
- pi-agent-factory's own guarded integration process owns everything that changes that
  repository before F4. plumb does not touch an integration in progress there.
- Every imported record arrives `proposed`, unless an upstream owner approval or consent pins
  its current content (concept 10). Only the owner confirms (R2).
- Each phase has a gate. The next phase starts only when the gate passes.

## 3. Phase F0: the current integration batch lands (pi-agent-factory, unchanged process)

The batch in flight when this plan was written (2026-10-06), as named by pi-agent-factory's
own plans in `docs/coherence/plans/`:

- safe integration, T-117 to T-120 (`2026-10-04-safe-integration.md`, NC-0021);
- unit suite runtime, T-121 and T-122 (`2026-10-04-unit-suite-runtime.md`);
- the claim correction, T-123 (`2026-10-04-claim-correction.md`), with NC-0022.

The batch is finished by pi-agent-factory's existing guarded process, not by plumb agents.
This plan adds no work to it.

**Gate F0.** The batch's branches are merged on pi-agent-factory's `main` through its own
integration, that repository's `full` gate is green there, and the owner says the batch has
landed. This is the first owner decision the morning handoff asks for.

## 4. Phase F1: maintenance mode

Starts once gate F0 passes. The owner, or a pi-agent-factory session the owner starts, adds a
short maintenance notice to pi-agent-factory's `AGENTS.md` and `README.md`. A plumb session
does not write it. The notice states:

- accepted changes: bug fixes, nonconformance corrections, security fixes and dependency
  updates needed to keep the tool running;
- not accepted: new FEAT or SR records, and new features. A new feature request becomes an
  `INT` record in the plumb repository instead;
- long governed workflows are no longer started there by default, which is the RAM concern
  of D9;
- the Pi extensions (`pi-ext/factory-watch`, `pi-ext/scope-guard`) stay usable in
  maintenance until plumb's Pi adapter exists (concept roadmap, sub-project 4).

**Gate F1.** The notice is on pi-agent-factory's `main`, and the owner has seen it in the
handoff or in a session.

## 5. Phase F2: extraction (sub-project 1, then a resync)

Sub-project 1 copies the modules listed in spec 13, from the read-only source
`C:/coding/pi-agent-factory/.worktrees/nc-t120/src`. The source is a worktree of a batch that
was still in progress, so the copies can lag behind what finally lands.

Steps after gate F0:

1. Record the pi-agent-factory `main` commit that closes the batch as the extraction
   baseline, in section 9 of this document.
2. For each row of spec 13 that plumb built, diff the source module at the extraction source
   commit against the same module at the baseline. Every behavioural change the batch made is
   either ported into plumb, test first, or recorded in `docs/followups.md` with the reason it
   does not apply to plumb (for example, a change to admission or coordination code that plumb
   does not carry). Known candidates: the claim-correction overlay in
   `coherence/register/claims.py` (plumb drops claim corrections, spec 13) and the evidence
   and failure-policy code under `coherence/integration/`.
3. The rows that sub-project 1 did not build (1b and stretch items that were cut, listed in
   `docs/followups.md`) are extracted from the baseline, not from the older worktree.

**Gate F2.** Every spec 13 row is marked built from the baseline, resynced to it, or
deferred with a followup entry. plumb's whole suite and `ruff` are green, and
`plumb validate` reports no errors on plumb's own records.

## 6. Phase F3: import (sub-projects 1 and 5)

Sub-project 1 may build a minimal importer as a stretch item (plan T10): every record
imported as `proposed`, dry run by default, read-only on the source. Sub-project 5 builds the
full importer of concept 10:

- `requirements/SR-*.md`: acceptance criteria kept as `AC-n`; `implemented_by` and
  `verified_by` become pinned links; legacy `checksum:` values are verified and reported;
- `docs/features/FEAT-*.md` plus `bundles/*.json`: the union becomes the feature membership,
  and every difference between the two is reported as a finding, never resolved silently;
- `docs/nonconformances/NC-*.md`: read leniently, with the original `corrected_by` strings
  kept;
- `.factory/trace-claims.yaml` becomes `.plumb/claims.yaml`, and the `commits[]` of
  `evidence/runs/ingest-*.json` become the claims checkpoint;
- a record receives a `by: import` approval only when an upstream owner approval or consent
  pins its current content; every other record arrives `proposed`.

Steps:

1. Dry run against the baseline commit of F2, from a plumb session, writing its output into
   a scratch directory only. The output is the list of findings (feature and bundle differences, checksum
   mismatches, dangling relations, unparsed NCs).
2. The findings are written to a plumb `docs/` report and listed in the next handoff. The
   owner decides each finding that changes meaning. Mechanical ones (formatting, a moved path)
   are fixed by the importer.
3. A second dry run shows no unexplained finding.

**Gate F3.** Two consecutive dry runs on the same baseline give identical output (the import
is deterministic), every finding is explained or decided, and nothing in pi-agent-factory
changed (its `git status` is clean and its `HEAD` is the baseline).

## 7. Phase F4: the switch (after sub-projects 4 and 5)

The switch moves pi-agent-factory's own development records onto plumb. It needs the full
importer (sub-project 5) and, for Pi users, plumb's Pi adapter (sub-project 4). It starts only
on the owner's explicit go-ahead, in the owner's words.

Steps, on a branch of pi-agent-factory:

1. `plumb init` and the import, using the importer of F3 against the branch itself.
2. `plumb hooks install` for the host the owner uses there. pi-agent-factory's per-turn
   coherence hooks are disabled on that branch, so that a turn never runs both.
3. pi-agent-factory's `SR:` trailers keep their IDs, so existing history keeps its meaning.
   `plumb claims check` must accept the branch's commits.
4. The modules that plumb now owns are retired in pi-agent-factory one at a time: each removal
   is a fix-only change that pi-agent-factory's own gate accepts, until only what plumb does
   not cover remains (governed execution, kept available for whoever still uses it).
5. Merge through pi-agent-factory's own process. The merge is an owner merge boundary: plumb's
   `validate --merge` must exit 0, so every touched imported requirement is confirmed by the
   owner (R1).

**Gate F4.** The branch merged with both gates green (pi-agent-factory's `full` gate and
plumb's `validate --merge`), and the owner works in pi-agent-factory through plumb's loop.

**Rollback.** Until F4 merges, pi-agent-factory's own records remain the source of truth, and
abandoning the branch undoes the switch. After F4, `plumb hooks uninstall` and a revert of the
switch merge restore the previous setup; the imported `.plumb/` stays as a read-only record.

## 8. Schedule

| Phase | When | Who |
|---|---|---|
| F0 | In progress on 2026-10-06; ends when the batch lands | pi-agent-factory's process |
| F1 | Right after gate F0 | the owner, or a session the owner starts there |
| F2 | Extraction during sub-project 1 (2026-10-06 night); resync right after gate F0 | plumb sessions |
| F3 | Dry run as soon as an importer exists (plan T10, or sub-project 5) | plumb sessions; owner decides findings |
| F4 | After sub-projects 4 and 5, on the owner's go-ahead | owner-started session |

Owner decisions this plan needs, in order: gate F0 (the batch has landed), the maintenance
notice of F1, the meaning-changing import findings of F3, and the go-ahead for F4. The
morning handoff lists the first one.

## 9. State at handoff

Updated by the sub-project 1 coordinator before the morning handoff (SP1 plan, task F0).

- Extraction source used by sub-project 1: `C:/coding/pi-agent-factory/.worktrees/nc-t120`
  (branch at the time of writing: `fix/publish-config-eol`). Commit: to be recorded.
- Spec 13 rows built: to be recorded.
- Importer (T10): to be recorded.
- Extraction baseline (F2 step 1): not yet known; gate F0 has not passed.
