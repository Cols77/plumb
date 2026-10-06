# Sub-project 3 spec: the merge boundary (`plumb merge-check`)

Status: implementation spec, written 2026-10-06. The owner does not review it (D11); verifier
agents check it against the owner intent brief, rulings R1 to R12 and `docs/concept.md`
section 7.5. Quotes and rulings win, then the concept, then this spec. Lane MERGE of
`docs/plans/next-plan.md` builds it. Requirements: `FEAT-003`, `SR-047` to `SR-052`, all
proposed.

## 1. Outcome

A merge boundary is where work relies on its records, so it is where the heavy guarantees
are paid for, once (concept principle 3). Sub-project 1 built the report
(`plumb validate --merge <base>`, sp1 5.11). Sub-project 3 completes it as one command:

```
plumb merge-check [BASE] [--no-run] [--json] [--hook pre-push]
plumb merge-check --install-pre-push | --uninstall-pre-push
```

`plumb merge-check main` answers "may this change merge?" in one short report and one exit
code:

1. every requirement the change touches is confirmed at its current hash, with its intents
   and the decisions that matter (R1, SR-047);
2. the approvals made in the range that the owner did not type in their own terminal
   (`agent-relayed`, and `auto-jev` from sub-project 2) are listed for the owner's glance
   (R2, R8 B, SR-047);
3. `full verification pending` is cleared by exactly ONE full-suite run, whose evidence is
   pinned to the code and environment identity and recorded as the merge's evidence (R5,
   SR-048);
4. claims (`SR:` trailers against declared paths) hold, no touched record has a stale or
   dangling link, and no confirmed example's acceptance test fails (KEEP list, SR-049);
5. the `plumb fidelity` packets of the touched requirements are listed, advisory only (R4,
   SR-050);
6. an optional git `pre-push` hook runs it (SR-051);
7. it stays lightweight: one process in the working tree, no transaction machinery
   (SR-052).

## 2. Owner intent served

| Owner decision or ruling | Where |
|---|---|
| Quality bar: "A full test suite runs only at merge boundaries." | One full run per merge-check, never in a turn (4) |
| KEEP: "test evidence pinned to the code and environment identity, plus the failure policy" | Full-run evidence keyed by tree and environment identity; flaky rerun on the same tree; owner waiver; full rerun only for infrastructure changes (4) |
| KEEP: "`SR:` commit trailers and claims checks (claimed vs declared paths)", "relation validation (no dangling links)" | Claims and link gates (5) |
| KEEP: "advisory fidelity judging, scoped to changed requirements" | Fidelity list (6) |
| R1: "At the merge boundary, every requirement touched by the change MUST be confirmed." | 3.1 |
| R2: "The merge boundary lists agent-relayed approvals for a quick owner glance." | 3.2 |
| R4: `plumb fidelity <SR>` "listed at the merge boundary, and always advisory" | 6 |
| R5: "`full verification pending`, which is satisfied at the next merge boundary" | 4 |
| R8 B: auto-approvals "listed at the merge boundary for a quick owner glance" | 3.2 |
| Pi-agent-factory lesson: "they seem pretty heavy ... blackboxed workflows" | No transaction machinery (7) |
| R10.5 (SP6): `plumb check --merge` on the merge result as a pre-merge or pre-push hook | Same entry point; SP6 adds intent conflicts (9) |

## 3. Confirmation and the glance

### 3.1 Every touched requirement is confirmed (SR-047)

Unchanged from sp1 5.11 item 1, now computed by `merge_report` (8): a requirement is touched
when its record, or an `implemented_by` or `verified_by` end, changed in `BASE..HEAD` plus
uncommitted changes, or a commit in the range claims it in an `SR:` trailer. Every touched
requirement, the `INT` records it derives from and each `DEC` with `matters: true` that
decides it must be confirmed at its current hash. Proposed records, unconfirmed edits,
requirements extended by a new owning link, acceptance tests changed since the approval,
untraced changes and `trace.exempt` globs added in the range go into one trigger-2 question,
and the command exits 4. An escalated set (sp2 6.2) whose member is touched counts as
confirmed only when an approval pins every member's current hash.

New in this sub-project: a confirmed requirement whose `implemented_by` end changed in the
range and was repinned with no fidelity judgment for the new hashes is listed under
`repinned without a judgment` (followups round 4). It is a glance item, not a wait: R4 keeps
fidelity advisory.

### 3.2 Approvals for the owner's glance

Every `approval` and `revocation` event added in the range, grouped:

- `by: agent-relayed`, with the owner's quote and the prompt digest (R2);
- `by: auto-jev`, with the score, confidence label, model version and prompt digest (R8 B);
- `by: owner` (triage groups and set approvals named as such) and `by: import`, one line each.

Each line ends with the revoke command (`plumb revoke SR-034`). The section is a glance,
never a question: the owner revokes what they did not mean.

## 4. Exactly one full-suite run (SR-048)

`plumb merge-check` decides whether a full run is needed before anything runs:

- needed when `full verification pending` holds (sp1 7.2: infrastructure changed since the
  latest full run, no full run on record, or an unknown-coverage file changed), or when
  touched acceptance tests are unverified or deferred and no owner waiver pins this exact
  change (`plumb tests waive --merge BASE`, sp1 7.5);
- not needed when the latest full `test-run` entry has the same tree identity
  (`head_tree` plus the dirty digest) and the same environment key and identity as now and
  passed: that evidence is reused, and the report says `full run reused (run <id>)`.

When needed, it runs `plumb tests run --full` exactly once, in-process, with the failure
policy: a failed node is rerun once on the same tree (flaky) and nothing else is rerun. It
never starts a second full run, whatever the result; a failure stays a failure and holds the
merge (exit 5) until a later merge-check (a new invocation by the agent or owner) runs again.
`--no-run` skips the run and reports what would hold, so the agent can check cheaply first.

A full run counts only when it collected cleanly, ran tests, and every test it failed has
passed since (sp1 5.11 item 4). It satisfies `full verification pending` by recording the
infrastructure hashes, as today.

When the report is green, merge-check appends one `merge-evidence` event:
`{base, fork, head, head_tree, dirty, full_run: <run_id>, reused: bool, env: {env_key,
identity}, touched, confirmed: [{id, hash}], verdict: "green"}`. This is the evidence
promotion of concept 7.5: the per-run entries are already committed in `evidence.jsonl`
(sp1 F5); the merge evidence pins which run vouched for this merge. A red or waiting report
writes nothing.

## 5. Claims, links and confirmed examples (SR-049)

- **Claims.** `plumb claims check --range FORK..HEAD` (sp1 5.9) runs inside merge-check.
  Undeclared paths (changed by a commit that claims SRs, declared by none of them, not exempt,
  not in the NC-backed baseline) hold the merge with exit 1 and the fix: declare the path on
  the right SR (`plumb link SR-### implemented_by <path>`) or add an NC-backed baseline entry.
  A range with no `SR:` trailer at all while `require_trailer: true` is also exit 1.
- **Links.** Every link of a touched record must be current: a dangling link is exit 1 (as in
  `plumb validate`); a stale link is exit 1 with the moved end and `plumb repin <link>`; a
  repin never confirms (sp1 5.5), and a repinned confirmed requirement is listed in 3.1.
- **Confirmed examples.** A failing or unverified acceptance test of a touched requirement,
  or of a confirmed requirement whose tests cover a changed path, holds the merge with exit 5
  (sp1 5.11 item 4, SR-027, SR-031), after the full run of 4 has had its chance to pass them.
- **Log integrity** against `BASE` (sp1 5.7): exit 1.

Exit precedence, unchanged: 1 (integrity, claims, links) before 5 (verification) before 4
(the owner's confirmation). 0 means all of 3 to 5 hold.

## 6. Fidelity, advisory (SR-050)

Touched requirements with no judgment for their current hashes, or whose latest judgment is
`drifts` or `unsure`, are listed with `plumb fidelity SR-###` for each. When JEV is
configured, merge-check scores up to five of them first (sp2 7.2), cheapest first, within
5 s, and shows the score beside each; a clear `fits` from JEV is shown as such, never
recorded as the host agent's judgment. The section never changes the exit code.

## 7. Lightweight by design (SR-052)

- One process, in the current working tree. No candidate checkouts, no integration
  transactions, no admission or coordination locks, no guarded publish, no manifests
  (contrast pi-agent-factory's T-120 transaction work). The only lock is the log lock
  every plumb write takes.
- No state between invocations except the committed log and the derived caches.
- The report fits one screen: at most 12 lines outside the lists, each list capped at 10 rows
  with `+N more (plumb merge-check --json)`.
- Cost: the checks without the full run finish in under 5 s on plumb's own repository; the
  full run costs what the suite costs, once.
- It never merges, pushes, commits or edits records. It reports and exits.

## 8. Pre-push hook (SR-051)

`plumb merge-check --install-pre-push` writes `pre-push` in the shared git hooks directory
(`git rev-parse --git-path hooks`) running
`<interpreter> -m plumb merge-check --hook pre-push`, with the interpreter that installed it.
In hook mode it reads git's stdin lines (`<local ref> <local sha> <remote ref> <remote sha>`),
uses the remote sha (or, for a new branch, the merge base with the configured
`merge.default_base`, default `main`) as BASE, and exits with the report's code, so git
refuses the push when it is not 0. `merge.prepush_run_full: false` makes the hook run with
`--no-run`. An existing non-plumb `pre-push` hook is left untouched and reported, as the
`commit-msg` installer does. `--uninstall-pre-push` removes only plumb's hook. The hook is
optional: `plumb hooks install` does not install it; the owner or the agent on the owner's
request does. `git push --no-verify` bypasses it, as with any git hook; the trust model is
unchanged (tamper-evident, not tamper-proof).

## 9. Interfaces and R10 compatibility

```python
# plumb.boundary (MERGE)
def merge_report(core, base: str, *, run_full: bool = True) -> MergeReport: ...
def render(report: MergeReport) -> list[str]: ...
def exit_code(report: MergeReport) -> int: ...
def install_pre_push_hook(root: Path, interpreter: str) -> Path: ...
```

`MergeReport` (in `contracts.py`, plan phase 0) holds the sections of 3 to 6 as data:
`touched`, `awaiting` (id, state, new ends), `untraced`, `new_exempt`, `glance` (approval rows
with `by`), `repinned_unjudged`, `full_run` (`{needed, ran, reused, run_id, verdict}`),
`claims`, `links`, `failing`, `unverified`, `regressions`, `fidelity`, `integrity`, `exit`.
`plumb validate --merge BASE` becomes `merge_report(run_full=False)` plus `render`, so the
two commands never disagree. PRESENT's `/plumb review` (sp5) calls `merge_report` with
`run_full=False`.

R10 compatibility: merge-check reads only committed files and the working tree, holds no
shared mutable runtime state, and its sections are a list SP6 extends with "intent
conflicts" (R10.3) when it runs on a merge result. It never renumbers or rewrites records.

## 10. Definition of done

1. `plumb merge-check` exists with tests per section, marked with their SR; `validate --merge`
   is its report-only form, and both give the same exit on the same tree.
2. A test shows exactly one full run per invocation (the runner is a fake counting calls):
   pending clears after one green run; a red run is not repeated; reuse on identical
   identity runs nothing.
3. Claims, stale-link and dangling-link holds have tests with exit 1; confirmed-example
   failures exit 5; unconfirmed touched requirements exit 4; the glance lists agent-relayed
   and auto-jev approvals with their quote or score.
4. The pre-push installer leaves a foreign hook untouched, and the hook mode blocks a push on
   a non-zero report in a temporary repository.
5. A `merge-evidence` event is written only on green.
6. On plumb's own repository, `plumb merge-check main --no-run` reports and exits 4 while
   plumb's records await the owner (expected: no agent approves them).

## 11. Out of scope

- Intent conflicts from a merge driver, cross-worktree awareness, collision-free IDs (R10,
  sub-project 6).
- CI service configuration; the command is CI-ready (exit codes, `--json`) but plumb ships
  no CI file.
- Any merge, push or publish action by plumb.
