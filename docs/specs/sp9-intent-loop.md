# The intent loop and the version 2 record set

Date: 2026-10-16. Records: INT-073, SR-193 to SR-197, DEC-079 to DEC-086 (all proposed).
Owner's note: the four-stage workflow pasted on 2026-10-16 (clarification, integration,
artifact update, execution with a proof of intent) and the question-tool answers of the same day.

## 1. Outcome

The owner opens an intent with `/plumb intent <words>`. plumb asks every blocking question
through the question tool, checks each answer against what is already confirmed, writes the
intent and its requirements once they are coherent, judges them, and only then plans and
builds. The build is done when the proof the owner stated has been shown. Ordinary messages
run no loop: the background grounding loop keeps doing what it does today.

The record set shrinks to one requirement per durable behaviour, derived from principles the
owner states once. The owner confirms about thirty records instead of answering a hundred and
thirty-two cards. The three sessions land what is done on the owner's word, drop what is
superseded, and the rewrite runs as one workflow on one branch.

## 2. The owner's decisions (2026-10-16)

| Decision | Chosen | Record |
|---|---|---|
| Orchestration or grounding | On command: the loop opens on `/plumb intent`; ordinary work keeps grounding. Concept principle 1 is narrowed, not dropped. | DEC-079 |
| Entry command | `/plumb intent` | DEC-080 |
| Stages I and II | One loop with one judge gate | DEC-081 (assumed; the note said "we can discuss") |
| Stage gates | The next stage's command refuses to run without the previous stage's passed gate; hooks only close the edit gate on an intent change and hold the merge | DEC-082 (assumed; the owner said "maybe it's not through a hook? idk") |
| Record set | Rebuild version 2 in place | DEC-083 |
| What a requirement is | One durable, observable behaviour with examples and a proof; fixes go under it; one intent per principle | DEC-084 |
| Landing the done work | On the owner's word; holds bypassed and logged; v2 reconfirms | DEC-085 |
| Superseded branches | Integrate fix/proof-findings and verdict-cascade's logs; drop sp7/plan and the SR-117 leftover | DEC-086 |

## 3. The intent loop (`/plumb intent`)

Three stages. Each stage ends in a gate; the next stage's command refuses to run until that
gate passed (SR-194). Every stage is interactive: questions come through the question tool,
trade-offs with full context come as cards (SR-157), and the owner can stop at any gate.

### 3.1 Stage A: clarify and integrate (the note's I and II, merged)

Input: the owner's words. Output: a clear intent, its requirements and decisions, proposed,
with the records they change named and the proof the owner stated.

1. **Intent candidates.** The clarifier (SR-103, now SR-193) reads the words and drafts the
   candidates: what will be done, what won't, assumptions labelled.
2. **Check against what is confirmed.** Each candidate is compared with the confirmed
   examples (the intent-change flag, SR-038), with intent in flight on other branches
   (SR-081, `plumb inflight`) and with the requirements it would change (SR-165). A
   contradiction or an extension becomes a question, not a silent choice.
3. **Questions.** All blocking questions, specific ones, through the question tool (DEC-072),
   invariants first (SR-172): the principle that settles several gaps is asked once and the
   gaps are derived from it. A question with a recommendable answer is an assumption, not a
   question (DEC-039). A complex trade-off is a card with its full context (SR-157).
4. **Loop** until no blocking gap is left. The owner states the proof: how they will see the
   intent working (SR-197).
5. **Judge gate.** The candidates go through the verdict cascade (SR-182: JEV first, the
   judge model below its threshold) and a review for coherence (contradiction with each
   other or with confirmed records, missing edge cases, two readings of one statement).
   Findings are high, medium or low. High and medium are fixed and judged again; the gate
   passes when only low findings remain. The judge never confirms a record here: records stay
   proposed until the owner confirms (SR-112).
6. **Write.** `plumb capture` writes INT, SRs with examples and the proof plan, DECs; the
   superseded records are named with a `supersedes` link (SR-195). The gate is recorded.

Why I and II merge: checking the candidates against the records is what tells which questions
matter, so it belongs inside the loop; a separate integration stage would re-ask them.

### 3.2 Stage B: update records and plans (the note's III)

Input: the passed clarify gate. Output: a reviewed implementation plan.

1. **Apply the plan of record updates:** retire or reword the superseded records, relink,
   repin what the tests still cover (`plumb repin --after-tests`), card what they do not
   (`plumb stale card`).
2. **Staleness** is computed (`plumb stale`, `plumb drift`): which code and tests the new
   and reworded requirements leave uncovered.
3. **Plan.** The writing-plans skill writes the implementation plan from the requirements,
   their examples (each example gets its acceptance test), the stale links, and the code the
   proof needs. A big intent is an escalated spec first (SR-036, SR-037).
4. **Review gate.** The plan is reviewed against the intent, the requirements, staleness and
   feasibility (the plan-review step of the superpowers skills plus the judge model), fixed
   until only low findings remain, then recorded as passed.

### 3.3 Stage C: build and prove (the note's IV)

Input: the passed plan gate. Output: the proof of intent.

1. Build through the normal development workflow (executing-plans or subagent-driven
   development, in a worktree), with drift caught at the edit (SR-111) and covering tests at
   the end of each turn (SR-017).
2. Show the proof the owner stated and record its evidence (`plumb proof SR-### --evidence`).
3. `plumb intent done` refuses while a proof is missing or a requirement the change touches is
   unconfirmed; the merge boundary holds the same (SR-047, SR-049).

### 3.4 State, commands and the workflow

- State lives in `.plumb/session/<id>/intent/<INT-id>.json`: the stage, each gate
  (`open`, `passed`, with the findings that remained), the proof plan, the records written.
  It is session state, carries no authority, and confirms nothing (concept section 5.3).
- Commands (agent side, driven by the plumb-intent skill): `plumb intent open <words>`
  (reads the words, drafts the candidates, opens the state), `plumb intent gate clarify
  --findings <file>` and `plumb intent gate plan --findings <file>` (record a gate; refuse
  when a finding above low remains), `plumb intent done` (refuse without the proof's
  evidence), `plumb intent status` (which gate is open, for the owner's card and the status
  line). `plumb clarify` stays as the inner check `intent open` calls; the owner command
  `/plumb clarify` is replaced by `/plumb intent` (SR-171 is superseded by SR-193).
- The skill runs the stages as phases of a Claude Code workflow (the Workflow tool) where
  the owner has it; each phase ends by calling the gate command, so a phase cannot proceed
  on a gate that did not pass. On a host without workflows the skill runs the same commands
  in sequence; the gate commands enforce the order either way.
- The question tool's answers are logged as the owner's words (SR-156) and feed the next
  question; they confirm no record. Confirmation stays a card press or `/plumb approve`.

### 3.5 What the hooks do (SR-196)

The hook events do not change (session-start, prompt, pre-tool, post-edit, edit-check,
question-answer, stop, subagent-stop, the git hooks). What changes:

- The prompt hook computes the intent-change flag (SR-038) for a message that is a request;
  when it flags a contradiction or an extension of a confirmed record and no loop has run
  for that request, it closes the edit gate and says which record and example. The gate
  opens when a loop reaches a clear intent for the request, or when the owner releases it
  (`/plumb go`). A request that touches nothing confirmed never closes the gate and runs
  nothing else.
- The pre-tool hook keeps refusing edits while the gate is closed (SR-121).
- Edit-check keeps catching drift at the edit (SR-111); the stop hook keeps the turn open
  while a link this turn made stale is unresolved, and asks for the covering tests.
- The git hooks hold the merge on unconfirmed, stale or unproven requirements, as now.
- No stage gate is a hook: a hook cannot know which stage an agent is in, and the stage
  commands can (DEC-082).

## 4. The version 2 record set (SR-195)

### 4.1 Definitions

- **INT**: one principle the owner holds, with their words as the quote. One per principle,
  not one per message. About twelve.
- **SR**: one durable, observable behaviour of plumb, with given/when/then examples (edge
  cases included), a proof plan and a feature. A fix of a behaviour an SR already states
  is a commit claiming that SR, or an NC when it was broken; never a new SR. About thirty.
- **DEC**: a fork that mattered and still holds. Decisions about removed mechanics are
  retired by the record that removed them. About twenty.
- **FEAT**: the areas. Today's eight sub-projects stay as the grouping unless the rewrite
  shows a cleaner cut (records and links; the intent loop; confirmation; cards and the owner
  surface; judging; verification and the merge boundary; parallel work; hosts and the
  browser).
- **NC**: kept as they are.

### 4.2 Why the set grew

Requirements SR-001 to SR-095 state one behaviour each under a feature. From SR-096 on,
almost every session's read-back became a requirement with no feature, including fixes and
one-off tasks, and the older statement of the same behaviour stayed live. The confirmation
rule is stated in about eighteen requirements, the card rules in about twenty, the judge
rules in about twenty-two, drift and links in about fifteen, the merge in about eleven. Each
newer one extends or contradicts the older, and that disagreement is the backlog of 132
records and 236 stale links.

### 4.3 The rewrite

One workflow on one branch, after the landing (section 5):

1. **Cluster.** Readers (a cheap model) group the 186 requirements, 70 intents and 75
   decisions by the behaviour they state, with each record's newest confirmed statement and
   every confirmed example that still holds.
2. **Principles.** From the clusters, the owner's principles are drafted (about twelve) with
   the quotes that carry them, and put to the owner through the question tool, one principle
   at a time; the answers are the INTs.
3. **Draft.** For each cluster, one requirement: statement, examples (every confirmed example
   that still holds is kept or named as dropped, with why), proof plan, feature, the
   `supersedes` list.
4. **Check.** An adversarial pass per draft: does it contradict a confirmed example it does
   not supersede, does it drop a behaviour the code still has, is it two behaviours in one.
   Fix until only low findings remain.
5. **Confirm.** The owner confirms per principle, by `/plumb approve <IDs>` grouped per
   principle or by the cards; nothing is auto-approved.
6. **Retire and relink.** Superseded records are retired with the trail; tests are relinked
   to the new requirements and repinned where they pass (the DEC-066 pattern); the test map
   is rebuilt; `plumb validate` is clean; the acceptance tests of retired examples are
   removed (DEC-065).
7. **Proof.** `plumb status` shows the short set, no proposed duplicate, every retired record
   pointing at its successor, and the covering tests passing.

The five requirements of this spec (SR-193 to SR-197) are the first version 2 records; the
capture already flagged the ones they change (SR-171, SR-127, SR-165, SR-134), which the
rewrite supersedes.

## 5. Sessions and branches

Freeze: no new feature branch until version 2 lands. Order: land, drop, prune, green, rewrite.

| Branch or worktree | Owner | Decision |
|---|---|---|
| merge/browser-issue-workspace (staged in main, MERGE_HEAD f82bc41a) | plumb-ac | Lands on the owner's "finish the merge" with holds bypassed (DEC-085); 72 built files exempted by a glob in .plumb/claims.yaml; worktree plumb-wt/browser removed after |
| feat/browser-issue-workspace, the .codex worktree | plumb-ac | Drop now (superseded by the merge branch, nothing uncommitted) |
| feat/open-items (2 ahead of main) | plumb-80 | Land on the owner's word |
| fix/proof-findings (3 fixes main lacks: SR-174, SR-170, SR-167) | plumb-80 | Integrate, then drop |
| feat/verdict-cascade (calibration logs only) | plumb-80 | Merge the logs as evidence, then drop |
| fix/budget-overrun | plumb-80 | Already in main (merged into open-items); drop |
| sp7/plan (one docs commit, 2026-10-07) | none | Drop |
| worktree-wf_5552c70c-97a-1 (SR-117, removed by DEC-040; 3 uncommitted edits) | none | Drop with its edits |
| 116 merged branches and their worktrees under .claude/worktrees and plumb-wt | none | Prune (only those with no uncommitted change; plumb-jevor, plumb-wt/defender-io and plumb-wt/sp7-contracts hold edits and wait for their owner's word) |
| design/intent-loop (this spec) | plumb-53 | Merge after the owner's review |

Then: main is made green (20 tests failed in the last full run, all pre-existing; those whose
examples the rewrite retires go with them), and the rewrite of section 4.3 runs.

## 6. Proof of this intent

- SR-193: open `/plumb intent` on a small idea in a scratch repository; the questions arrive
  through the question tool, the judge gate runs, records are written only after it passes.
- SR-194: run the stages out of order on a scratch intent; the refusal names the missing gate.
- SR-195: `plumb status` after the rewrite shows the short set, no proposed duplicate, and
  every retired record pointing at its successor.
- SR-196: in a scratch repository with one confirmed requirement, a contradicting request has
  its edit refused with the requirement named; after the loop, the edit goes through.
- SR-197: a proof stated on a scratch intent, the build finished without showing it, and
  `plumb intent done` refusing; then shown, and the evidence recorded.

## 7. Out of scope

The panel and browser views of the loop's state (one line on the status line is enough for
now); other hosts' adapters; the diagram mod; auto-approval by the judge, which stays as
DEC-073 left it. The concept document gets a version 2 section once the rewrite lands, not
before.
