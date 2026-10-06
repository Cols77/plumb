# Sub-project 2 spec: intent capture, escalation and JEV-assisted confirmation

Status: implementation spec, written 2026-10-06. The owner does not review it (decision D11:
"I wont review the concept spec or any plan. use agents that verify that my intent based on
that conversation is respected."); verifier agents check it against the owner intent brief,
its rulings R1 to R12 and `docs/concept.md`. When this spec, the concept and the owner's
quoted words disagree, the quotes and rulings win, then the concept, then this spec. Section
3 lists every place where this spec refines the concept, with the reason.

Companion documents: `docs/concept.md` (the reference), `docs/specs/sp3-merge-boundary.md`,
`docs/specs/sp4-hosts-mcp.md`, `docs/specs/sp5-presentation.md`, and the one combined plan for
all four sub-projects plus the importer completion, `docs/plans/next-plan.md` (lane CAPTURE
builds this spec). Requirements: `FEAT-002`, `SR-034` to `SR-046` in `.plumb/`, all proposed.

## 1. Outcome

At the end of sub-project 2, the agent turns what the owner says into plumb records as the
work happens, with a few commands, and the owner confirms them with as little effort as their
own words allow:

- `plumb capture` records a whole read-back in one call: the owner's verbatim words, the
  restatement, what will and won't be done, labelled assumptions, given/when/then examples
  (edge cases too) and the decisions taken ("I assumed A; B also fits"). Everything is
  `proposed`, linked and hash-pinned, and the command prints the intent card the agent puts
  in its reply (SR-034). Single-record helpers `plumb intent`, `plumb example` and
  `plumb decide` cover the smaller cases (SR-035);
- escalation is detected with the concept's triggers and suggested once; an escalated spec is
  a set of records the owner approves by one set-hash approval (SR-036, SR-037);
- intent-change and contradiction scoring go through the `JudgmentBackend`: the heuristic by
  default, the JEV live client only behind the protocol, with its credential read from the
  environment and every JEV test skipped when it is absent (SR-038, SR-039);
- `plumb triage` groups proposed records by how faithful they are to the owner's words and
  lets the owner confirm the low-risk group in one step (R8 A, SR-040); a narrow, opt-in,
  calibrated auto-approval for records restating the owner's own words exists and is off by
  default (R8 B, R12.1, SR-041, SR-042);
- the `plumb-clarify` skill scales the clarification to the request (R11, SR-043);
- ownership proposals for untraced changes and hidden-dependency hints are computed and
  handed to the presentation layer as proposals only (R12.3, R12.4, SR-044, SR-045);
- the `plumb` skill drives these helpers (SR-046).

Nothing in this sub-project lets a model or the agent confirm intent outside the two paths
the owner chose: the owner's explicit words (R2) and, only when the owner turns it on, the
calibrated JEV auto-approval of records derived directly from the owner's words (R8 B).

## 2. Owner intent served

| Owner decision or ruling | Where this spec serves it |
|---|---|
| D2 "C" and its five intent-translation mechanisms | `plumb capture` (5.1), decisions (5.3), escalation and set approval (6) |
| "how do you ensure that people defining their system will have their intent succesfully translated?" | read-back with will, won't and labelled assumptions; examples with edge cases; decisions with alternatives (5); clarification depth (9) |
| D5 "A": questions only on the three triggers | escalation is a suggestion, never a question (6.1); clarifying questions are trigger 2 only when intent starts or changes (9.3) |
| D8 "I think it might be usefull to integrate it in this new version too?" | `JudgmentBackend` with the heuristic default and the JEV client behind it (7) |
| R1: read-back and examples non-blocking | every record `proposed`; nothing waits except an escalated spec (5, 6.2) |
| R2: only the owner's explicit words; agent-relayed with quote and digest | triage group relay (8.1), set relay (6.2); no "no-objection" path anywhere |
| R8 A, triage ("Ok for A+B") | `plumb triage` (8.1) |
| R8 B, narrow auto-approval | `auto_approve` gated by an owner config event and by calibration (8.2, 8.3) |
| R8 commands ("there should be a command for that") | `plumb triage`, `plumb config auto-approve on\|off`, `plumb config show`, `plumb jev status`, `plumb jev setup` (8, 7.3) |
| R11 brainstorming-grade clarification | `plumb-clarify` skill and `plumb clarify` (9) |
| R12.1 calibration | `plumb jev calibrate` (8.3) |
| R12.3 ownership proposals | `ownership_proposals`, `diff_serves`, test-node proposals (10.1) |
| R12.4 hidden-dependency scan | `drift_hints` (10.2) |
| R10 (SP6, later) | no design here conflicts with it (12) |

## 3. Refinements of the concept, with reasons

| # | Concept text | This spec | Reason |
|---|---|---|---|
| C1 | Helpers `plumb intent`, `plumb example`, `plumb decide` (concept 11, item 2) | Those three, plus `plumb capture`, which writes a whole read-back (INT, SR with examples, DEC) from one JSON document in one call, and `plumb new <kind>` as the generic form | One call per turn keeps the agent's overhead to one interpreter start (about 225 ms here) instead of one per record; the single-record helpers stay for small edits |
| C2 | Set approval pins a set hash over the sorted member hashes (4.6) | The set is anchored on an `INT` with `mode: escalated` and a `members` list; `plumb spec approve INT-###` (owner) or `plumb relay --set INT-### --prompt --quote` (relayed) writes one approval with the set hash and every member's hash | Gives the set an identity the owner can name, inside the existing record model; no new record kind |
| C3 | "No model ... confirms intent" (concept 8 and 12) | Exception R8 B: `by: auto-jev` approvals, off by default, only for records derived directly from the owner's words, only after a passing calibration for the current model version, and only while the owner's own `plumb config auto-approve on` event stands | Owner decision 2026-10-06 ("Ok for A+B") and R12.1. The concept is updated in the same change (section 8 and 12) |
| C4 | `.plumb/config.yaml` holds settings (4.1) | `auto_approve` in `config.yaml` is a mirror. The effective state is the latest `config` event written by `plumb config auto-approve` in the owner's terminal (the owner-terminal guard, concept 4.6 check 4: no session marker and a y/N answered in an interactive terminal). A `config.yaml` that says on without that event is off, and `plumb validate` warns | The agent may edit `config.yaml` (the guard denies only `.plumb/log/**`); R8 says the command is "owner-terminal only, logged in the event log". The log event is what the agent cannot write on the normal path |
| C5 | R8 A: one line "approve the N records rated faithful to your words?" | The line names every record of the group by ID; the stated set records the group with its hashes; a relayed "ok" on the next prompt approves exactly that group (`plumb relay --group low-risk`), even though the records were not each shown in full | The owner chose the grouped one-line confirmation explicitly (R8 A). Naming every ID keeps the owner's words tied to an exact, inspectable set; the full records are one `plumb triage` away |
| C6 | Intent-change detection flags change words on a matched confirmed record (6.2) | Scored against the confirmed record's examples: a contradiction (the request negates or replaces a `then`), an extension (new behaviour next to a confirmed one), or benign (a mention, a tidy-up). Change words alone never flag | The heuristic flagged "also tidy the add docstring for SR-001" and missed "make add subtract" (followups, round 5): a false interruption and a missed trigger 1 |
| C7 | JEV key in `TYPESAFE_API_KEY` or the user store `~/.config/plumb/jev` (8) | `plumb jev setup` records only the NAME of the environment variable (`judgment.jev.credential_env`, default `TYPESAFE_API_KEY`); the user store remains a fallback read path; no secret is ever written by plumb | R8 commands: "records only the NAME of the environment variable that holds the credential; never stores the secret" |

## 4. Records and files

No new record kind. Fields added (all optional; old records stay valid):

| Kind | New field | Meaning |
|---|---|---|
| intent | `members` (list of IDs) | only with `mode: escalated`: the records of the up-front spec |
| intent | `prompt` (digest prefix) | the logged owner prompt the quote comes from (session state holds its text) |
| requirement example | `quote` | a verbatim span of the owner's words this example restates (R8 B eligibility) |
| decision | `recommended` | the option the agent recommends when it asks (R11) |
| decision | `asked` | `false` until the stop hook has asked it once at its current hash |

New event kinds in `events.jsonl` (written only through `CoreAPI.log_append`): `config`
(owner changes of `auto_approve`), `calibration` (12.1 results), `escalation-declined`,
`triage` (the groups shown, for later calibration), `jev-setup` (the credential variable's
name). New session files (gitignored): `.plumb/session/<sid>/clarify.json` (the depth
chosen for the current intent) and `.plumb/session/triage.json` (the last group offered).

## 5. Capture

### 5.1 `plumb capture` (SR-034)

```
plumb capture [--file doc.json | -] [--prompt <digest>] [--dry-run] [--json]
```

The document (JSON or YAML) carries the read-back the agent is about to state:

```json
{"intent": {"quote": "add multiply next to add", "readback": "...",
            "will": ["multiply(a, b) returns a * b"], "wont": ["no floats yet"],
            "assumptions": ["integers only, like add"], "mode": "incremental"},
 "requirements": [{"title": "multiply returns the product", "statement": "...",
                   "feature": "FEAT-001",
                   "examples": [{"given": "a = 2 and b = 3", "when": "multiply runs",
                                 "then": "it returns 6", "quote": "2 times 3 is 6"},
                                {"given": "a = 0", "when": "multiply runs", "then": "it returns 0"}],
                   "implemented_by": ["src/app/calc.py"]}],
 "decisions": [{"question": "floats?", "chosen": "integers only",
                "alternatives": ["floats too"], "matters": true, "recommended": "integers only"}],
 "updates": [{"id": "SR-004", "examples": [...]}]}
```

Rules:

- `intent.quote` is required and must be a verbatim substring (after body normalization) of
  the prompt named by `--prompt` when one is given; otherwise the command refuses (exit 2).
  The owner's words are never paraphrased into `quote`.
- Records are written through `CoreAPI.write_record`, which allocates IDs through the one
  choke point `Store.next_id` (R10 compatibility, 12). Links `derives_from` (SR and DEC to the
  INT), `decides` (DEC to the INT or SR) and `implemented_by` (each existing path) are added
  through `CoreAPI.add_link`, so they are pinned at once.
- `updates` edit an existing record's examples or statement. Editing a record that is
  confirmed makes it an unconfirmed edit, exactly as in sub-project 1; `plumb capture` says so
  in its output (`SR-004 was confirmed; this edit needs the owner again`).
- Every written record is `proposed`. The command then asks the auto-approval gate (8.2),
  which returns at once when auto-approval is off (the default).
- Output: the intent card text (`plumb.present.render.intent_card`, sp5) for the agent to put
  in its reply, then one line per written record (`INT-017 proposed`, `SR-034 proposed`).
  `--json` returns `CaptureResult` (11.1). `--dry-run` validates and prints, writing nothing.
- The records written are part of the turn's stated set through the stop hook's existing rule
  (every proposed record created or edited this turn), so the owner's "ok" on the next prompt
  can confirm them under R2.

Latency: one process, no network unless auto-approval is on (then one JEV call, 10 s limit on
the command line; it is not a hook).

### 5.2 Single-record helpers (SR-035)

- `plumb new <intent|requirement|decision|feature|nc> --title T [fields] [--derives-from ID]`
  writes one record with the next ID and prints its path (sp1 5.8, now built).
- `plumb intent --quote Q --readback R [--will W]... [--wont W]... [--assume A]...`
- `plumb example SR-### --given G --when W --then T [--quote Q]` appends `EX-n`.
- `plumb decide --question Q --chosen A --alt B [--alt C] [--matters] [--recommend A]
  [--decides ID]` writes a `DEC`; `plumb decide --supersede DEC-### ...` writes the new
  decision with a `supersedes` link (a confirmed decision is never edited in place).

### 5.3 Decisions with alternatives

A decision is how an ambiguity becomes explicit: "I assumed A; B also fits." The agent writes
one whenever two readings fit, instead of choosing silently. `matters: true` marks a decision
whose answer changes what gets built; those are the only ones the stop hook may ask about
(trigger 2), once per hash, and when several are open it asks only the highest-ranked one
per message (`next_question`, 11.1; R11 "ONE per message"). A decision with
`matters: false` is shown in the summary and never asked.

## 6. Escalation and the up-front spec mode

### 6.1 Detection (SR-036)

`capture.escalation(core, prompt=, matched=, diff=)` returns suggestions for the concept's
triggers (concept 5.2), each with its reason:

1. the request would add or change more than `escalation.max_requirements` (3) requirements,
   or touch more than `escalation.max_features` (1) feature (matched records, plus the
   records `plumb capture` is about to write);
2. it contradicts or removes a confirmed requirement or example (a `contradicts` flag of 7.1);
3. it touches shared surfaces: the record format (`.plumb/**` schemas, `contracts.py`), the
   claims policy (`.plumb/claims.yaml`), shared test infrastructure (`verify.infra_globs`), a
   public CLI or API (`cli.py`, routed command modules), a data schema or a migration
   (configurable globs `escalation.shared_globs`);
4. hard-to-undo effects: deleting records, changing persisted data, security or credential
   handling, publishing (configurable path globs and words `escalation.irreversible`);
5. two or more decisions with `matters: true` are still unconfirmed;
6. the diff passes `escalation.diff_lines` (400) changed lines or `escalation.diff_files`
   (10) files without a confirmed escalated set covering it (from `DiffStats`, given by the
   stop hook).

A suggestion is shown as one line by the prompt or stop hook
(`plumb: consider an up-front spec: touches 2 features (FEAT-001, FEAT-003); the owner
decides`). It is never a question by itself. `plumb escalate decline [--intent INT-###]`
(agent-relayed when the owner says no, or the owner's terminal through
`approvals.require_owner`) appends an
`escalation-declined` event; the same trigger for the same intent is not suggested again.

### 6.2 The escalated set and its approval (SR-037)

When the owner accepts the suggestion, the agent drafts the whole set before code: an `INT`
with `mode: escalated` and `members` (every SR, DEC and FEAT of the spec), the records
themselves, and a short Markdown spec in `docs/specs/` that links them by ID. It presents the
set for approval, which is a trigger-2 question the owner invited by accepting.

- `plumb spec show INT-###` prints every member in full (the read-back of each), the set
  hash and the approval command.
- `plumb spec approve INT-###` (owner's terminal, through `approvals.require_owner`: refused
  under the marker and outside an interactive terminal, exit 3) and
  `plumb relay --set INT-### --prompt D --quote Q` (the owner's affirming words in a prompt
  after the set was shown) write one `approval` event:
  `{"records": [{"id", "hash"}...], "set": {"anchor": "INT-###", "hash": "sha256:..."},
  "by": ...}` where the set hash is `sha256(canonical_json(sorted [id, hash] pairs))`.
- Every member is confirmed at its hash by that one event. An edit to any member afterwards
  makes that member an unconfirmed edit and the set `unconfirmed` (shown as such); code for
  the escalated work keeps waiting only until the first approval; later edits are ordinary
  drift that the merge boundary asks about (R1).
- Members are never eligible for auto-approval (R8 B).
- While the set is unapproved, the stop hook names it once per turn as the open trigger-2
  question; the agent is told not to write code for it (`plumb: INT-### (escalated) waits
  for the owner's approval of its set; do not write its code yet`).

## 7. Judgment: intent change, contradiction and the JEV client

### 7.1 Intent-change and contradiction scoring (SR-038)

`capture.intent_flags(core, prompt, matched)` returns `IntentFlag`s for confirmed records
only (a proposed record never feeds trigger 1, concept 4.2):

- `contradicts`: the request negates, replaces or reverses a confirmed example's `then` or
  the statement (heuristic: a confirmed example term set overlaps the prompt strongly and the
  prompt carries a replacement or negation pattern bound to those terms: "make X Y" where Y
  differs from the confirmed `then`, "instead", "no longer", "not ... anymore", "remove",
  "rename X to");
- `extends`: the request adds behaviour beside a confirmed record (strong overlap on the
  subject, new verbs or objects absent from every example: "add a multiply function next to
  add");
- benign: everything else, including a mention of the ID with tidy-up words ("docstring",
  "comment", "typo", "format", "rename variable") — no flag.

Each flag carries `confidence`, the example it is about and a one-line reason. The backend
decides: `JudgmentBackend.intent_change` (heuristic by default) gives the candidates, and
`contradiction(prompt, record)` (11.2) labels them. A flag reaches the agent as the existing
instruction ("this may change SR-004 (confirmed). If it does, read back the change and ask
before editing; if not, proceed."); the agent remains the cascade's LLM tier. A precision
fixture (`tests/capture/fixtures/intent_prompts.yaml`, at least 30 labelled prompts:
contradict, extend, benign) records precision and recall in the test output; the heuristic
must flag every `contradicts` prompt of the fixture and no `benign` one.

### 7.2 JEV live client behind the protocol (SR-039)

The client exists (`plumb/judgment/jev.py`, sub-project 1 BS3) and is reached only through
`get_backend` and the `JudgmentBackend` protocol. This sub-project:

- adds the methods of 11.2 (`entailment`, `choose`, `ask`) to `JevBackend`, `HeuristicBackend`
  and `DisabledBackend`;
- reads the credential from the environment variable named by `judgment.jev.credential_env`
  (default `TYPESAFE_API_KEY`), then the user store, never from the repository;
- keeps the hook timeout (`judgment.hook_timeout_ms`, 800 ms) and the fallback to the
  heuristic with one notice per session;
- tests: unit tests use the local stub HTTP server (no network); live tests are marked
  `@pytest.mark.jev_live` and skipped unless the credential variable is set, so the suite
  passes on any machine without a key.

### 7.3 `plumb jev status` and `plumb jev setup`

- `plumb jev status [--json]`: configured? (backend `jev` and a credential variable name),
  credential present? (yes/no, never the value), reachable? (one `GET`-equivalent probe with
  a 2 s limit, only when asked), backend and resolved model version, the version thresholds
  were calibrated against, and whether auto-approval is effective. `plumb judgment status`
  stays as an alias of the non-network part.
- `plumb jev setup [--env-var NAME] [--base-url URL]`: writes `judgment.backend: jev` and
  `judgment.jev.credential_env: NAME` to `config.yaml`, appends a `jev-setup` event with the
  name only, and prints how to set the variable in the owner's shell. It never reads, prints
  or stores the secret.

## 8. JEV-assisted confirmation (R8)

### 8.1 Triage, always available (SR-040)

`plumb triage [--json] [--approve low-risk]`:

1. Takes every `proposed` or unconfirmed-edit record.
2. Scores each for faithfulness to the owner's words with
   `JudgmentBackend.entailment(premise, hypothesis)`: the premise is the owner's words the
   record derives from (an INT's `quote`; for an SR, the `quote` of the INTs it derives from
   plus its examples' `quote` spans; for a DEC, its question and the INT quote), the
   hypothesis is the record's restatement (read-back, will, won't, assumptions; statement and
   examples; chosen option). With JEV this is a typed judgment; with the heuristic it is term
   coverage of the hypothesis by the premise, plus penalties for won't items or assumptions
   with no support in the premise.
3. Groups: **low-risk** when the score is at least `triage.low_risk_min` (0.8) and the record
   is not excluded (below); every other record is shown **individually** with its rating and
   reason. Excluded from the low-risk group, always shown individually: a `DEC` with
   `matters: true`, a member of an escalated set, an edit of a record the owner confirmed
   before, and any record whose premise is empty (no owner words to compare).
4. Prints the low-risk group first (one line per record: ID, title, rating), then the others.
5. `--approve low-risk`, in the owner's terminal only, lists the group with hashes, then
   writes through `approvals.require_owner` (refused under the marker and outside an
   interactive terminal, exit 3; its one `y/N`, which no flag skips, is the confirmation of
   the one step), and writes one `approval` event
   `by: owner` of exactly the listed hashes, with `"triage": {"group": "low-risk",
   "backend": ..., "scores": {...}}`. A record that changed between listing and writing is
   left out and named.

The end-of-turn summary and `plumb brief` carry one line when the group is not empty:
`plumb: approve the 4 records rated faithful to your words (INT-017, SR-034, SR-035, SR-036)?
say "ok" or see plumb triage`. The stop hook records the group in the stated set as
`{"group": "low-risk", "records": [{"id", "hash"}]}` (C5). On the owner's next prompt, an
affirming quote is relayed with `plumb relay --group low-risk --prompt D --quote Q`, which
checks the R2 rules (verbatim quote, affirmation, the group present in the stated set) and
approves exactly the group's hashes, `by: agent-relayed`. Triage never approves anything by
itself; with the heuristic it still groups (degraded), and without any backend it reports
"no judgments available" and shows every record individually.

### 8.2 Narrow auto-approval, opt-in and off by default (SR-041)

Configuration, mirrored in `config.yaml` (C4):

```yaml
auto_approve: {enabled: false, backend: jev, min_probability: 0.9, min_confidence: high}
```

`plumb config auto-approve on [--backend jev] [--min-probability 0.9] [--min-confidence
high]`, `plumb config auto-approve off` and `plumb config show` run in the owner's terminal
only (refused under the marker, exit 3; denied by the installed deny rules). `on` and `off`
write through `approvals.require_owner`, so they are also refused outside an interactive
terminal on every host (concept 4.6 check 4). `on` writes a
`config` event and the mirror, and refuses (exit 1, nothing written) when JEV is not
configured, the credential is absent, or no passing calibration exists for the current
resolved model version (8.3).

Auto-approval is **effective** only when all of these hold: the latest `config` event says
on and was written with no session marker through `approvals.require_owner`; JEV is configured and answered (the heuristic
never auto-approves); a passing `calibration` event exists for the resolved model version.
When the resolved version differs from the calibrated one, auto-approval is suspended and the
status line and brief say so (`auto-approve suspended: model changed, recalibrate`).

When effective, `plumb capture` and `plumb example` ask the gate for each record they wrote:

- **Eligible** only: an `INT` whose `quote` is a verbatim span of the logged prompt named by
  `--prompt`; an `SR` written in the same capture whose every example carries a `quote` that
  is a verbatim span of that prompt. The gate asks JEV whether the logged prompt text
  **entails** the record text (11.2 `entailment`).
- **Never** eligible: a `DEC` with `matters: true`; a member of an escalated set; an edit of a
  record that has ever had an owner, agent-relayed or import approval; a record of any kind
  when JEV is unavailable, timed out or errored; any record when no `--prompt` is given.
- An approval is written only when the answer's probability is at least `min_probability` and
  its confidence label at least `min_confidence`, and at least the calibrated threshold for
  that claim kind (8.3). It is one `approval` event `by: auto-jev` with `{score,
  confidence, prompt_digest, backend, model_version, calibration: <digest of the calibration
  event>, claim_kind}`, hash-pinned like any approval.

Auto-approvals are labelled everywhere: `confirmed by JEV` in `plumb show`, `status`, the
brief and the status line (`SR 12/14 ok (2 by JEV)`), and they are listed at the merge
boundary with the agent-relayed approvals for the owner's glance (sp3). `plumb revoke ID`
(owner) and `plumb relay --revoke` revoke them like any approval. `plumb validate` re-checks
each `auto-jev` approval: a preceding owner `config` on event without a later off, a
preceding passing `calibration` for the same model version, a cited prompt event, a score at
or above the recorded thresholds, an eligible record kind; any failure is an error.

### 8.3 Calibration (R12.1, SR-042)

`plumb jev calibrate [--json]` measures the backend on the owner's own decisions:

- The labelled set is built from the log: records the owner confirmed (`by: owner` or
  `agent-relayed`) and never revoked are positives; records the owner revoked, and records
  the owner edited right after an auto-approval, are negatives. To the negatives it adds
  deterministic perturbations of the positives (a will item moved to won't, a negated `then`,
  a swapped number), labelled `synthetic`, so a small project still has negatives.
- For each claim kind (`intent-readback`, `example-restatement`) it scores every item with
  `entailment` and finds the lowest threshold at which no negative would have been accepted.
- **Passing** means, per claim kind: at least `calibration.min_items` (20) labelled items of
  which at least `calibration.min_negatives` (5) are negatives (synthetic ones count up to
  half), a false-accept rate of at most `calibration.max_false_accept` (0.0) at the chosen
  threshold, and at least half of the positives accepted.
- It appends one `calibration` event `{model_version, backend, per_kind: {kind: {items,
  negatives, threshold, false_accept, recall, passing}}, labelled_set_digest}` and prints the
  table. The agent may run it; only the owner can turn auto-approval on.
- With the heuristic it reports "heuristic: no auto-approval, calibration not applicable";
  without any backend, "no judgments available".

## 9. Clarification depth: the `plumb-clarify` skill (R11, SR-043)

### 9.1 The skill

`src/plumb/hosts/claude_code/templates/skills/plumb-clarify/SKILL.md`, written for plumb
(not copied from other plugins), installed by `plumb hooks install` next to the `plumb`
skill. Its description makes the agent load it whenever a request creates or changes intent.
It scales its depth to the request:

- **TRIVIAL/CLEAR** (maps to confirmed intent, or a small unambiguous change): no questions;
  a compact read-back only (one line, "Doing X as in SR-004; nothing else changes").
- **INCREMENTAL** (new or partly specified intent): write back the understanding, separating
  "you said" from "I assume"; propose examples, including edge cases; ask ONLY the questions
  whose answer changes what gets built, ONE per message, as multiple choice with a
  recommended option; each question becomes a `DEC` with `matters: true` and `recommended`.
- **ESCALATED** (one of the triggers of 6.1): a short structured session: settle purpose and
  success first; then 2-3 approaches with trade-offs and a recommendation; then the set of
  records presented as an up-front spec for set-hash approval (6.2).

Discipline, stated in the skill: never ask what the repository, the records or sensible
defaults already answer; YAGNI, drop features the owner did not ask for; restate in the
owner's terms, never code terms (R9); stop asking once the owner says "go" or "ok": the
remaining unknowns become labelled assumptions (non-blocking under R1). Clarifying questions
are the "unconfirmed decision that matters" trigger, so they occur only when the owner starts
or changes intent, never mid-implementation unless a contradiction appears. Output: the
intent card (sp5) plus the records written with `plumb capture`, all proposed.

### 9.2 `plumb clarify`

`plumb clarify "<request>" [--questions q.json] [--json]` gives the skill its facts:

- `depth`: `trivial`, `incremental` or `escalated`. Escalated when a trigger of 6.1 fires;
  trivial when every matched record is confirmed, no flag of 7.1 fires and the backend's
  ambiguity rating (`ask`, "is this request ambiguous given these records?") is low;
  incremental otherwise. With no backend judgment, the heuristic rates ambiguity by unmatched
  content terms.
- `answered`: confirmed records (and config defaults) that already answer parts of the
  request, so the agent does not ask about them.
- With `--questions` (the agent's draft questions, each `{question, options, recommended}`):
  each question is dropped when a confirmed record answers it (term overlap above
  `clarify.answered_min` with its statement or an example, citing the record) or when all its
  options lead to the same will/won't items; the rest are ranked by the backend (`ask`:
  "does the answer change what gets built?") and returned in order. The agent asks the first,
  one per message.
- Writes `.plumb/session/<sid>/clarify.json` with the depth, so the stop hook can tell an
  escalated intent from an incremental one.

### 9.3 Measure

The end-to-end session test (`tests/capture/test_clarify_e2e.py`) drives one ambiguous
request ("let users export their data") through `plumb clarify` with four drafted questions:
one answered by a confirmed record, one whose options lead to the same build, two that
matter. It asserts that exactly the two questions that matter remain, that recording them
writes two `DEC` records with `matters: true`, and that the stop hook asks only the first in
the next message and the second after it is answered.

## 10. Proposals for presentation and the merge boundary (R12.3, R12.4)

### 10.1 Ownership proposals (SR-044)

- `ownership_proposals(core, paths)`: for each untraced changed path (sp1 5.11), candidate
  owning requirements are narrowed by the code map (requirements whose `implemented_by` or
  `verified_by` ends share the import closure or the package of the path; at most 5); the
  backend picks one (`choose`, a Choice over the candidates plus "none"). The result feeds the
  untraced-change instruction to the agent ("src/app/mul.py: SR-001 may own this (proposed);
  read it back and link it, or record a new SR"). It is a proposal only and never writes a
  link.
- `diff_serves(core, sr_ids, paths)`: at commit time, `plumb trailers check-msg` asks "does
  this diff serve its claimed SRs?" (`ask`, a Noul) for each claimed SR; a `no` with high
  confidence prints a one-line warning (`plumb: warning: SR-004 may not be served by
  src/app/report.py`). The hook never blocks on it, and the claims result is identical with
  and without judgments. The call has the hook timeout.
- Test-node proposals: a `verified_by` link to a bare test file gets a proposed node
  (`tests/test_calc.py::test_add_returns_sum`) chosen by name and docstring overlap with the
  example it verifies; shown as a drift hint, never written.

With the heuristic, candidates are ranked by overlap and only the top one is proposed when its
lead is clear; otherwise "no judgments available".

### 10.2 Hidden-dependency scan (SR-045)

When a confirmed record, or an authoritative document (`hints.authoritative_docs`, default
`docs/concept.md` and `docs/specs/**`), changes in the working tree or the range, a bounded
scan (at most `hints.hidden_deps_max` (5) candidates, at most 1 s) proposes records and
documents that may silently depend on it: candidates are records and documents with no link
to it whose text overlaps its changed terms; the backend confirms each with one `ask`
("does B depend on what changed in A?"). The results are drift hints only, returned by
`drift_hints(core, changed)` as ready lines for `plumb drift`, the brief and `/plumb review`
(`plumb: hint: SR-012 may depend on the change to SR-004 (no link)`). They are never
staleness marks or edges, and they never interrupt.

## 11. Interfaces provided to the other lanes

The coordinator writes these signatures, and stubs that return empty results, in the plan's
phase 0 (`docs/plans/next-plan.md` 3), so the PRESENT, MERGE and HOSTS lanes build against
them from the start. CAPTURE replaces the stubs; it never changes a signature without the
coordinator.

### 11.1 `plumb.capture.api`

```python
def capture(core, doc: Mapping[str, Any], *, prompt_digest: str | None = None,
            dry_run: bool = False) -> CaptureResult: ...
def intent_flags(core, prompt: str, matched: Sequence[str]) -> Sequence[IntentFlag]: ...
def escalation(core, *, prompt: str | None = None, matched: Sequence[str] = (),
               diff: DiffStats | None = None) -> Sequence[EscalationSuggestion]: ...
def next_question(core, touched: Sequence[str]) -> str | None: ...       # one DEC id or None
def triage(core, ids: Iterable[str] | None = None) -> TriageView: ...
def card_data(core, ids: Sequence[str]) -> Sequence[IntentCardData]: ...
def confirmation_counts(core) -> Mapping[str, int]: ...  # {"owner", "agent-relayed", "auto-jev", "import", "proposed"}
def auto_approve_state(core) -> AutoApproveState: ...
def ownership_proposals(core, paths: Sequence[str]) -> Mapping[str, Proposal]: ...
def diff_serves(core, sr_ids: Sequence[str], paths: Sequence[str]) -> Sequence[str]: ...
def drift_hints(core, changed: Sequence[str]) -> Sequence[str]: ...
def clarify(core, request: str, questions: Sequence[Mapping[str, Any]] = ()) -> ClarifyView: ...
```

The data classes (`CaptureResult`, `IntentFlag`, `EscalationSuggestion`, `DiffStats`,
`TriageView`, `TriageItem`, `IntentCardData`, `AutoApproveState`, `Proposal`, `ClarifyView`)
live in `plumb/contracts.py` (plan 3.2). Every function returns within 1 s with the heuristic
and degrades to an empty result on any error, so a hook that calls it never fails because of
it.

### 11.2 `JudgmentBackend` additions

```python
def entailment(self, premise: str, hypothesis: str, *, subject: str,
               claim_kind: str) -> Judgment: ...      # verdict entailed|not-entailed|unsure
def contradiction(self, prompt: str, record: Record) -> Judgment: ...  # contradicts|extends|benign
def choose(self, question: str, options: Sequence[str], *, subject: str,
           context: str = "") -> Judgment: ...        # verdict: the chosen option or "none"
def ask(self, question: str, context: str, *, subject: str,
        action: str) -> Judgment: ...                 # verdict yes|no|unsure (Noul)
version: str                                          # resolved model version, "heuristic" otherwise
```

`Judgment` gains optional `probability: float | None` and `confidence_label: "low" |
"medium" | "high" | None`. Every judgment stays advisory except the gated `entailment` of
8.2, and is logged as a `judgment` event with its request fingerprint when it comes from JEV.

## 12. R10 compatibility (parallel work, sub-project 6)

- IDs are allocated only through `Store.next_id`, the one choke point SP6 replaces with the
  `refs/plumb/ids` reservation.
- Every new log entry goes through `CoreAPI.log_append` with a new `kind`; nothing writes
  `events.jsonl` directly, so SP6's one-file-per-entry migration moves them all.
- Session files are per session directory; no new shared mutable state, lock or lease.
- Set approvals and triage approvals pin exact hashes, so an intent conflict from a merge
  (R10.3) shows as an unconfirmed edit, never as a silently kept approval.

## 13. Definition of done

1. `plumb capture`, `new`, `intent`, `example`, `decide`, `escalate decline`, `spec show`,
   `spec approve`, `triage`, `config auto-approve|show`, `jev status|setup|calibrate` and
   `clarify` exist, have tests marked with their SR, and appear in `plumb --help`.
2. The precision fixture of 7.1 passes: every `contradicts` prompt flagged, no `benign` one.
3. Guard tests: `spec approve`, `triage --approve`, `config auto-approve on|off` and the
   owner's `escalate decline` refuse under the marker, and refuse with no marker outside an
   interactive terminal (one test per command, stdin a pipe holding "y"); `relay --group` and `relay --set` enforce the R2 checks; auto-approval never fires
   with the heuristic, without an owner `config` event, without a passing calibration, for a
   `matters: true` DEC, for a set member or for an edit of an owner-confirmed record.
4. JEV unit tests pass on the local stub; live tests are skipped without the credential.
5. `tests/capture/test_clarify_e2e.py` passes (9.3).
6. The installed `plumb` skill names `plumb capture`, `plumb decide`, `plumb clarify`,
   `plumb triage` and the relay forms (SR-046); `plumb-clarify` is installed beside it.
7. `plumb validate` and `plumb drift` run clean of errors on plumb's own repository.

## 14. Out of scope

- Rendering of cards, the status line and `/plumb review` (sp5); CAPTURE provides their data.
- The merge-boundary listing of auto-approvals (sp3).
- `plumb align` (R12.2) and the Obsidian view (sp5).
- Parallel-work features (R10, sub-project 6).
- Any approval made by a model outside R8 B, and any "no-objection" approval.
