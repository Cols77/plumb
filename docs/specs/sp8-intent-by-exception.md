# Sub-project 8 spec: intent by exception (understood by models, confirmed only when uncertain)

Status: proposed, 2026-10-09; updated 2026-10-10 with the owner's answers of 10 Oct (section 2,
second table) and the design review from the owner's other session (section 3, principles 6
and 7). Order of work (`DEC-031`, 3A): the hooks fix first, then SP8, then the everyday loop's
requirements confirmed and verified, then SP7 resumes; SP7's panel later draws SP8's cards
(section 10). Written from a brainstorming session with the owner (answers quoted in
section 2). Records: `INT-028` (approval understood from meaning or a button),
`INT-029` (models, not fixed rules, wherever plumb interprets words; both reworded by this
spec, section 10, so that neither promises a fallback), `DEC-027` (which model
reads the owner), `SR-096` and `SR-097` (rejections and short answers, kept), `SR-012`
(the summary shows what awaits the owner as an answerable card), `DEC-029` (the backlog in one
pass, one card per feature), `DEC-030` (settling switches on by itself for derived records),
`DEC-031` (the order of work), `INT-030`, `SR-108` and `DEC-028` (long executions show their
current step and progress). When this spec and the owner's quoted words disagree, the words win.

## 1. Outcome

The owner states intent the way they would talk to a colleague. plumb records it faithfully,
asks up front only about gaps that change what gets built, and from then on asks the owner
only about what it cannot establish with confidence. Everything it can establish is settled
without the owner, shown in one short line per turn, and can be undone. Whatever needs the
owner arrives as a card that names the topic, the issue and suggested resolutions.

Success, measured on plumb's own repository:

- every owner message that carries intent ends in a record that quotes the whole message;
- the owner never retypes record numbers or fixed words to confirm (no "INT-008 ok" alone);
- no record is confirmed or settled that the owner did not mean (the evaluation set of 9.3
  passes, and no settled item is undone as "not what I said" in the first two weeks of use);
- the proposed backlog trends to zero instead of growing (it stood at about 150 on 9 Oct);
- the clarifier's false-gap rate (questions it asks that change nothing about what gets built)
  is measured on the evaluation set of 9.3 and reported with the calibration results;
- while a model job runs, the owner can see in plain words what plumb is doing and how far it
  is (section 4.4).

## 2. The owner's decisions (brainstorming, 9 Oct)

| Question | Owner's answer |
|---|---|
| What does the owner personally confirm? | "Agreed with A, but only partly. Only uncertain intent should need confirmation. Same for requirements, decisions and detailed examples derived from it. When resolution can't be fast-forwarded, cards that expose the topic and the issue are provided by the agent and suggest resolutions." |
| When may plumb settle without asking? | A: an independent, calibrated model finds the record faithful to the owner's words and to what they already confirmed |
| How does the owner see what was settled? | A: one short line per turn, titles only, each with Undo; the full list at the merge |
| When a request has gaps? | B: clarify up front, before building |
| How are up-front questions asked? | C: one card, at most three questions with suggested answers; smaller gaps become assumptions on the same card; more than three real questions escalate to a short spec session |
| Until the model has proven itself? | A: a trial in which every judged item comes as "plumb would settle these; right?", and the answers both settle and calibrate |
| The ~150 proposed records? | A: fed into the trial in small batches; flagged ones come as issue cards (the batches are superseded on 10 Oct, see below) |
| Architecture | 1: background judging started by the hooks |
| Worker | "That worker should be integrateable in claude and hermes agents using the expected technics that allow to dispatch work to an agent in the context of that coding harness." |
| Fallback | "No labelled falback. If a model is unreachable, throw an error" |
| Principle | "most of the time the system shouldn't rely on deterministic tooling to understand intent or process text, unless we're sure the deterministic solution can handle any type of situation" (INT-029) |

The owner's answers of 10 Oct (records `DEC-029` to `DEC-031`, `INT-030`), which change the rows
above where they overlap:

| Question | Owner's answer |
|---|---|
| How is the ~150-record backlog worked through? (`DEC-029`, 1A) | Judge the whole backlog in one background pass, then show one card per feature ("these 18 about the merge check would be settled; right?"). This replaces batches of five (section 8). |
| Who switches settling on once calibration passes? (`DEC-030`, 2B) | Settling switches on by itself, once calibrated, for records the agent derives (requirements and their examples). The owner still switches it on for intents and still answers decisions that matter (section 7). |
| In what order does work go? (`DEC-031`, 3A) | The hooks fix first, then SP8, then the requirements of the everyday loop confirmed and verified, then SP7 resumes; SP7's panel later draws SP8's cards (section 10). |
| What does the owner see while plumb works? (`INT-030`, `DEC-028`) | "There should be a progress bar indicating the progress of long executions with a message indicating what's going on": the current step in plain words and how far along, in the status line and as a bar (terminal) or plain lines (agent shell) (4.4, 8). |

## 3. Principles

1. **Models interpret; code checks what is exact.** Every step that interprets words (the
   owner's answers, a gap in a request, whether a record is faithful) is a model job. Code
   keeps only checks that are exact by nature: the message is in the prompt log, the record
   was shown at that version, hashes, IDs, links, test evidence, owner-only settings.
2. **No fallback.** A model that cannot be reached is an error the owner sees. Nothing is
   confirmed, settled or rejected on a guess, and no rule-based reading replaces the model.
3. **Independence.** The coding agent never decides that the owner approved something. The
   reader and the judge run in a separate context that sees only the job's inputs.
4. **Confirmation by exception.** The owner is asked only about what is uncertain; the rest
   is settled, visible and undoable.
5. **The owner's words are the anchor.** Every intent quotes the whole logged message (and
   the question it answered, for a short answer); every judgment compares against those words
   and against what the owner confirmed. The message is committed to the repository log (text
   and digest) the moment it becomes a record's premise, not only kept in the gitignored
   session log, so the premise outlives the session and a fresh clone can judge it (4.2).
6. **The model's own confidence is a signal, and the owner's answers set the thresholds.**
   Reader and judge report a confidence as the model gives it. No threshold is fixed in
   advance: the cut-off for acting on a confidence is learned from trial outcomes (section 7),
   with a cautious starting value until there are enough answers.
7. **Few model starts.** Each `claude -p` start costs seconds, so jobs are batched: one read
   job per turn and one judge job per capture (4.4). Nothing waits on a job: while it runs the
   agent proceeds with nothing confirmed, and the status line says what is happening.

## 4. The pieces

All four live in a new package `plumb.understand` (host-neutral core), with one adapter per
host for dispatch (section 5).

### 4.1 Reader: what the owner answered

One read job per turn covers the whole message against everything the previous reply showed.
Input: the owner's logged message (text and digest); the stated set of the reply before it
(the records shown, each at its hash, with the text that was shown); the open cards (their
questions and suggested answers). Output, one entry per shown record or card question; the
confidence is the model's own, from 0 to 1:

```json
{"id": "INT-008", "hash": "sha256:...", "answer": "accepted|rejected|change|open",
 "rejection": "misread|intent-changed|null", "change": "what the owner asked to change, or null",
 "evidence": "the owner's words that carry this answer", "confidence": 0.0}
```

Card answers map onto these four answers; the schema has no other. For a card's resolutions:
keep = `accepted`, drop it = `rejected`, reword = `change` (the new words in `change`), pick a
version or combine = `change` with the chosen version, or the combination, in `change`; a
trial batch's yes = `accepted`, no = `rejected`; the Couldn't check card's "build anyway" =
`accepted`, "wait" = `rejected` (4.3). Each card kind has an SR-105 example.

plumb then applies only exact checks: the message is in the prompt log (via the hook); each
id was in that stated set at that hash; `evidence` occurs in the message. An `accepted`
entry whose confidence is at or above the reader's threshold confirms the record as "you said:
<evidence>" (`by: owner-words`, with the digest and the reader's job id). The threshold is
learned from the owner's trial answers (section 7); until enough are on file it is 0.9. A `rejected` entry is logged as an
SR-096 rejection (`misread` is the calibration "no"). A `change` entry becomes a recapture
task for the agent (read back at the next turn). `open`, or any confidence below the threshold,
confirms nothing. While the read job runs the status line says "reading your answer" and the
agent goes on working with nothing confirmed; the confirmations are applied when the job
returns (4.4). Records named in free prose but not shown are never confirmed: plumb shows
them as cards first (SR-088's rule, kept for prose).

Two paths, not one. A typed `/plumb approve|confirm <ID...>` command is an exact owner action
(SR-088, SR-065): it names IDs, needs no reading, bypasses the reader and confirms at once,
recorded as passed on from the owner's typed command. The reader handles free prose only. An
ID named in prose but not shown becomes a card; the same ID in a typed command is confirmed.
Owner-only settings (switching settling on for intents, switching it off for any kind,
automatic confirmation) and Undo change only by a typed command (`/plumb settle on|off`,
`/plumb undo <ID>`) or a button, never by a model's reading of prose (the one automatic
switch-on, for derived records, is plumb's own act when calibration passes, section 7); a prose "turn settling on" or "undo that" has no effect, and plumb replies
with the command or button to use. The one prose-reachable release is the Couldn't check
card's "build anyway" question (4.3), which opens a guard and changes no setting.

This replaces, as the way approvals are understood, the affirmation-term list, the
objection words, the clause splitting and the plain-words matching of `approvals.py`
(`owner_scope`, `change_clauses`, `objection_clauses`, `affirmation_context_problem`,
`_plain_named`) and of `confirm.py` (`affirmation_in`). They are removed, not kept as a
fallback (principle 2). Every caller of a removed rule is listed in section 10.

**`plumb relay` for prose is removed.** Without the word rules, an agent-run relay would let
the agent confirm any logged prompt with any quote, including a message that says no, which
breaks principle 3. The only agent-run paths that reach a confirmation are the exact typed
command (parsed to exact IDs, SP7 7.2, `via: command`) and the worker (4.4). `plumb relay`
keeps a terminal-only form (an interactive y/N, as for `plumb approve`) for the owner's own
terminal and for tests; run from the agent's shell under the session marker it is refused.
Typed `/plumb confirm <words>` is not supported: `confirm` takes IDs only; words go to the
reader as prose, on the records the previous reply showed.

### 4.2 Judge: can this be settled?

The question put to the model is: **would the owner object to this record, given their
words?** For a short answer ("A", "yes") the words include the question it answered, which is
part of the premise, so that a bare answer is judged against what it was an answer to. One
judge job per capture covers every record the capture wrote or changed and returns one
verdict per record.

Input: one record per entry (an intent's read-back, will, won't; a requirement's statement and
examples; a decision's question and chosen option), its premise (the owner's whole logged
message or messages it derives from, plus the stored question for a short answer, plus the
parent intent when the owner confirmed it), and the owner's confirmed or settled records it
relates to. Labelled assumptions are shown but are not part of what is judged. The premise
message is read from the committed log: `plumb capture` writes the message's text and digest
there when the record first takes it as premise (principle 5), so a record keeps its premise
after the session log is gone. Records that predate this have the gap described in section 8.

Output:

```json
{"verdict": "supported|beyond|contradicts", "beyond": ["what the record asserts that the owner's words do not"],
 "contradicts": ["what conflicts, with the record it conflicts with"], "confidence": 0.0}
```

`supported` means the owner would not object: their words support everything the record
asserts as theirs, and every addition is a labelled assumption that does not change what gets
built. `beyond` and `contradicts` mean they would. The confidence is the model's own and is
logged with the verdict. Only a
`supported` verdict at or above the calibrated threshold can settle a record, and only once
settling is on (section 7). `beyond` and `contradicts` produce an issue card (section 6).
The judge replaces the strict-entailment question of today's triage (`capture/triage.py
claim()`), which rated faithful elaborations as unfaithful.

### 4.3 Clarifier: is the request clear and complete?

Runs on every owner message; the clarifier itself decides whether the message carries new or
changed intent and returns `no intent` when it does not (a question, an answer, a remark),
which produces no card. No hook, keyword or heuristic flags intent (principle 1). Input: the
message, the confirmed and settled records it touches. Output: `intent: yes|no`, then a draft
read-back (will, won't, assumptions,
two or three concrete examples) and the gaps that change what gets built, ranked, each with
two or three suggested answers and a recommended one. plumb shows one card with at most
three questions (section 6); the remaining gaps become assumptions on the same card. More
than three questions that change what gets built escalate to a short structured session
ending in an up-front spec (INT-004). A request with no such gap produces no card: work
starts at once. A question the owner would call pointless (it changes nothing about what gets
built) is a false gap; the false-gap rate is measured on the evaluation set (9.3) and reported
with the calibration results.

**The gate (clarify up front, before building).** The prompt hook closes the gate (it writes a
small state file `.plumb/session/<id>/gate` naming the latest owner message) and queues the
clarify job, idempotently, so it starts early; the hook does not wait. The first action the
plumb-clarify skill gives the agent is `plumb clarify --wait`, an agent-initiated, bounded
collection step outside any hook: it returns the clarify result, waiting for the job up to a
timeout (default 45 s), or runs the job itself when none was queued (same inputs, same job
id, so it never runs twice). Ordering: the clarify job for a message runs only after that
message's read job has been applied, and its input includes the open cards with the answers
the read job just mapped, so a card the owner has just answered is not asked again. Exactly
one of these opens the gate, each written by plumb and never by the agent: the clarify
result says `no intent` or has no gap; the result carries a card and all the card's
questions are mapped by the reader; the owner releases a failed check (below). Outcomes: `no
intent` or no gap, the guard opens and work starts at once; a card, the guard stays closed
until all its questions are mapped, and answering the card does not produce a second card for
the same questions; a job still running, `--wait` waits and edits stay refused; a late result
is collected by the next `--wait`, never after the build; a timeout or an error, a Couldn't
check card (section 6) and no build until the owner releases it.

**Release of a failed check.** The Couldn't check card carries one question, "Build without
the check?", with two resolutions, Build anyway and Wait. The owner answers by a button, by
the typed `/plumb go`, or in prose, which the reader maps (`accepted` at or above the reader's threshold
opens the guard, `rejected` keeps it closed). A failed clarify job blocks edits whatever the
message was, since the failed model is the one that would say whether it carried intent; this
is the cost of principle 2, and it lasts only until the release or until the next turn's
retry succeeds. This is the one place plumb blocks work: the owner's "clarify up front"
overrides INT-004's "block work on a proposed read-back (R1)" only for gaps that change what
gets built. INT-004 and INT-003 are otherwise unchanged: every other edit stays unblocked.

**What the gate runs on.** The refusal is a PreToolUse check, which today's install does not
have (its guard is static permissions). The gate therefore needs a pre-tool hook. SP8
builds the minimal one itself, because it comes before SP7's PLUGIN lane resumes (section 10),
and the gate is Claude Code only. The hook has one fast path: when the tool is
an edit (Edit, Write, NotebookEdit), read the one small state file and refuse while it says
closed, in shell with no Python, within the hook's 50 ms budget. Edits made through Bash
(redirects, `sed -i`) are out of scope: the gate refuses the edit tools only, and says so.
Other hosts (Hermes, Pi, Codex) have no pre-tool hook (Hermes's direct-tool defence is an
optional follow-on): they get the skill-level instruction to run `plumb clarify --wait` first
and the visible card, but no hard refusal. The state file is tamper-evident, not
tamper-proof (SP7 5.7).

### 4.4 Worker and jobs

A job is a file `.plumb/session/<id>/jobs/<job-id>.json`: kind (`read`, `judge`,
`clarify`), inputs with their hashes, the answer schema, created-at. A result is
`.../results/<job-id>.json`: the validated answer, the model used, timings, or an error.
Jobs are idempotent: the same inputs give the same job id, so a retried hook never runs a
job twice. Jobs are batched, because each `claude -p` start costs seconds: the prompt hook
queues one `read` job per turn (when the previous reply stated anything; it covers every
shown record and open card) and one `clarify` job (for every owner message); `plumb capture`
queues one `judge` job per capture, covering every record that capture wrote or changed. The worker is started detached by the hook that queued (the
hook returns within its budget); a running worker picks up new jobs; at most one worker per
session.

**What the owner sees while a job runs.** The worker writes its current step and progress to
the session state file (`.plumb/session/<id>/progress`) at least once per second, and the
Claude Code status line reads it as it reads status today (INT-030, SR-108, DEC-028). The
step is in plain words: "reading your answer" while a read job runs, "checking your request"
for a clarify job, "judging 7 records" for a judge job, "judging the backlog · 10/160" for the
backlog pass (section 8). Where the total is known the progress is done of total; where it is
not, the elapsed time, with no percentage. In a terminal (`plumb clarify --wait`, a backlog
pass started by hand) the same message shows as one bar redrawn in place; from the agent's
shell, as plain lines at a steady interval, bounded in number, ending with a line that says
what finished. A job that fails replaces the line with one naming the step that failed, and
the status line stops showing it as running. A job that finishes within two seconds shows
nothing. The agent never waits on a read or judge job: it proceeds with nothing confirmed and
the result is applied when the job returns.

**As shipped (progress and `go`).** The line is the `progress` file of the session. The worker
writes it every second while a model call is out and removes it when the job ends, except an end
line a job left itself (state done) and the count of a pass of many jobs (the backlog), which the
next job goes on from, so the status line reads "judging the backlog · 10/160" between jobs too
(a count older than two minutes is not the pass in progress). `plumb go --prompt DIGEST` is the
typed release of a failed check: it opens the gate only when the logged message with that digest,
written by the host's prompt hook, is exactly `/plumb go`; the agent's own attempt is refused (exit 3).

**Who writes a confirmation.** Only the hook-started worker applies reader and judge results,
and only the worker writes these entries. They are not new event kinds: `owner-words` and
`settled` are `by` values on the existing `approval` kind (and `undone` on `revocation`), so
one log reader, `confirm.py`, decides record status (section 10). The worker trusts no job
file. It recomputes every job's inputs from the logs: the prompt log (the message and its
digest), the shown set at its hash, the record at its hash, the premise from its logged
sources. It applies only what it computed itself, so a job file carries no authority and no
signature. A `judge` job queued by the agent (such as the one `plumb capture` queues for each
record it writes) is therefore safe, because its inputs are recomputed; and the model's
answer is applied in memory when the model returns, not by reading result files later. A
result file written by the agent confirms nothing and is reported. Each by value has its own
re-check at status and `validate` time: `owner-words` (the prompt digest is in the log, the
evidence occurs in the message, the record hash is the one shown); `settled` (the judgment is
logged with its job id, model and score, and the premise digest is unchanged); `undone` (the
owner's typed command or button). Independence is tamper-evident, not tamper-proof, as in SP7
5.7: the agent runs as the same OS user. This is how an owner-derived write happens without a
terminal, replacing SR-005's interactive y/N for reader confirmations (SR-005's terminal path
stays for typed commands).

## 5. Dispatch through the host

The core defines the jobs; each host adapter runs them the way that harness dispatches work
to an agent. Exactly one dispatcher is configured (`understand.dispatch`); when it fails,
the job fails with an error (principle 2). There is no automatic second route.

| Host | Dispatcher | How |
|---|---|---|
| Claude Code | `claude-code` (default there) | `claude -p` with a plumb-shipped agent defined by `--agents` and selected by `--agent <name>` (the prompt per job kind is its `--system-prompt`), `--model` from config (default `haiku`), `--tools ""` (no tools), `--json-schema` with the job's answer schema, `--output-format json`, `--no-session-persistence`, and isolation from the owner's setup: `--setting-sources ""`, `--strict-mcp-config` with no MCP config, `--disable-slash-commands`, and a neutral working directory (an empty temporary directory, never the repository), so the job sees only its inputs (principle 3). Run without `--bare`, so the owner's Claude login is used; plumb's own hooks see `PLUMB_JOB=<job-id>` in the environment and exit at once, so a job never queues jobs (other plugins' hooks are not plumb's to stop; `--setting-sources` keeps them out). With an API key configured the adapter may add `--bare`. A test asserts the job's context contains no CLAUDE.md text. |
| Hermes | `hermes` | A delegated child session (Hermes's own delegation, the same mechanism the Hermes adapter already excludes from plumb's hooks by `parent_session_id`), given the job prompt and schema, without tools. The exact call follows SR-099's assessment and the Hermes adapter plan (`.hermes/plans/2026-10-09_120026-plumb-hermes-spec-and-plan.md`). |
| Any | `openrouter` | A direct call through the credential plumb already reads for JEV, with the same schema. A configured choice, never a silent fallback. |

DEC-027 is revised to: "a small model through the host's own dispatch (Claude Code: Haiku via
`claude -p`), or OpenRouter when configured; the coding agent never reads its own approvals".

## 6. Cards

Every card carries a topic (in the owner's terms, no IDs alone, no internals), the issue,
the evidence (the owner's words and what conflicts with them), and two or three suggested
resolutions with the recommended one first. plumb builds the card's facts; the agent words the
suggested resolutions for the owner and presents the card in its reply (SR-012's new example:
never only as an ID or inside tool output). Until SP7 resumes there is no panel: the agent presents the card in its reply and the owner
answers in prose (read by the reader) or by a typed command. When SP7 resumes (DEC-031), its
panel draws these same cards, with a button per resolution and Accept / Reject.

| Card | When | The owner's answer does |
|---|---|---|
| Clarify | 4.3 found gaps that change what gets built | the answers the reader maps to the card's questions are confirmed; assumptions on the card stay labelled and proposed, and settle only through the judge and trial path, or by an owner yes the reader finds on them. Silence settles nothing (INT-028) |
| Trial batch | during the trial (section 7), up to five new items the judge would settle | yes settles the item and labels it "yes" for calibration; no rejects it (`misread`) |
| Backlog feature | the backlog pass (section 8) judged records of one feature `supported` | one yes confirms all of them ("these 18 about the merge check would be settled; right?"), each labelled "yes" for calibration; the owner can name exceptions in the same answer, which the reader maps per record; no rejects those named, or all |
| Goes beyond your words | judge `beyond` | keep (`accepted`: the owner confirms the addition), drop it (`rejected`), or reword (`change`) |
| Contradicts | judge `contradicts`, or an answer conflicting with a confirmed record | pick a version, or combine (`change`, carrying the chosen version) |
| Couldn't check | a job failed (model unreachable, malformed answer) | says what was not done and that it will retry; for a failed clarify job it asks "build without the check?" (4.3): Build anyway or Wait. Other failures need no answer |

The end-of-turn summary shows, in this order: confirmations from the owner's words ("you
said ..."), the settled line ("Settled from your words: <title>; <title>", each with Undo),
the cards. Undo is a button or the typed `/plumb undo <ID>` (owner-only, 4.1); it reopens the item as
a card.

## 7. Trial, calibration and settling

- **Trial (default when no passing calibration exists).** Every judged `supported` item is
  offered in a trial batch instead of being settled (the backlog is offered per feature
  instead, section 8). The owner's yes and no are the labelled
  examples; `misread` rejections (SR-096) are real "no" examples. SR-042's thresholds apply
  per kind. The judge's score is its own confidence for a `supported` verdict and 0 for any
  other, logged at judgment time so that recalibration is offline; the thresholds (the judge's
  per kind, and the reader's of 4.1) are whatever the trial outcomes support, never fixed
  numbers (principle 6). The labels are the owner's yes and
  no in a trial batch, `misread` rejections, and `by: owner-words` confirmations (a trial yes
  is recorded as an owner confirmation via the button, not as a plumb settlement); the
  `labelled_set` of `capture/calibrate.py` counts these as well as `owner` and
  `agent-relayed`. Because only supported items are offered, the threshold would be learned on
  a censored range: one item per batch is drawn from below the threshold ("plumb would not
  settle this; right?"), and the report states the remaining limit. Settle eligibility keeps
  SR-040's and SR-041's exclusions: a decision is never settled (decisions that matter are
  always individual, and `calibrate.KINDS` has no decision kind), nor a set member, an
  escalated set member, or an edit of an owner-confirmed record.
- **Calibration** reruns after each trial batch answered, cheaply, from logged judgments
  (no new model calls; `calibrate()` reads the logged score instead of rescoring through JEV). When it passes for a kind, who switches settling on depends on the kind
  (`DEC-030`, 2B):
  - **Records the agent derives (requirements, with their examples):** settling switches on
    by itself for that kind. The summary says so once, with how to switch it off. The switch-on
    is logged with the calibration result that allowed it. If the owner has switched the kind
    off, plumb does not switch it on again.
  - **Intents:** the summary says so once and offers to turn settling on; the owner turns it
    on with the typed `/plumb settle on intent` or a button (an owner-only setting, SR-041;
    prose cannot, 4.1).
  - **Decisions:** never settled. Decisions that matter are always asked individually.
  The owner switches settling off, for any kind, with the typed `/plumb settle off <kind>`
  or a button.
- **Settling** marks a record `settled` (`by: plumb-judge`, with the job id, the model and
  the premise digest). A settled record counts as confirmed for the merge boundary, is listed
  separately at the merge, and returns to proposed if its text or its premise changes.
- **One mechanism.** Settling replaces SR-041's automatic approval and
  `capture/autoapprove.py` (superseded; its revocation, undo and re-check parts are kept and
  move to settling; the owner-only on/off switch is kept). There is no second route.
- **Bare option answers.** The judge's premise for a short answer is the question it answered
  (the `in_reply_to` of SR-091, which is the "stored question" of SR-097: one thing). A
  `supported` verdict on a record whose premise is an option picked among several (SR-091 EX-3)
  is never settled; it goes to a trial or confirm card. A "yes" to one proposal shown whole
  (SR-091 EX-4) may settle like any other item.
- **Model or prompt change** (a new model version, an edited job prompt) suspends settling
  until the evaluation set (9.3) passes again and calibration is rerun. A kind that switched
  itself on switches itself back on then (unless the owner switched it off meanwhile); the
  owner's own switch for intents stays as they set it.

## 8. The backlog

The ~150 proposed records are judged in **one background pass** (`DEC-029`, 1A), started once
by the worker and not metered per turn, and then offered as **one card per feature** (section
6): "these 18 about the merge check would be settled; right?". The pass is a series of judge
jobs, each covering the records of one intent as a capture does (4.4); a job already done is
not run again unless its record changed (jobs are idempotent), so a pass interrupted by a
failure resumes on the next turn from where it stopped. Records without a feature are grouped
by the intent they derive from, and a feature card names the records it covers in the owner's
terms.

- The records the judge finds `supported` are on their feature's card. One yes confirms them
  all as the owner's (`by: owner-words`, labelled "yes" for calibration, section 7); a no, or
  exceptions named in prose ("all but SR-040"), are mapped per record by the reader. A card
  also carries one record drawn from below the threshold, asked as "plumb would not settle
  this; right?" (section 7).
- Records the judge flags (`beyond`, `contradicts`) are not on the feature card; each comes as
  an issue card.
- Records whose premise is a fragment get their premise rebuilt from the logged message when
  the prompt log holds it; when it does not (records imported from the 5-7 Oct sessions), the
  issue card says the original words are not on file and offers the record's own read-back
  for the owner to accept or correct.
- Cards are offered a few per turn alongside new work so the owner is not swamped; the
  features with the most records come first. This is the only metering, of what is shown and
  not of what is judged.
- While the pass runs, the status line says where it is in plain words, such as "judging the
  backlog · 10/160", and a bar or plain lines show the same wherever the pass is started
  (4.4, `SR-108`). When it ends, the line says how many records are judged and how many
  cards await.

## 9. Failures, safety and tests

### 9.1 Failures

- Model unreachable or dispatcher missing: the job's result is an error; the summary shows a
  "couldn't check" line; nothing is confirmed, settled or rejected; the job is retried on the
  next turn; three consecutive failures show in the status line.
- An answer that fails the schema: an error for that job, never a reading.
- A read or judge job not finished at the end of the turn: collected at the next turn. A
  clarify job is not left to the next turn: see the gate in 4.3.
- A record edited after it was shown: an answer about the old version confirms nothing.

### 9.2 Safety (exact, deterministic)

Kept from today and checked in code: the owner's message is in the prompt log; a record is
confirmed only at the version shown; the agent cannot confirm, settle or turn settling on by
itself (the session marker and the guard); owner-only settings and Undo change only by a typed
command or a button (the one automatic act, switching settling on for derived records, is
plumb's own and is logged with the calibration that allowed it); results are applied only by
the worker of 4.4, from inputs it recomputed from the logs; a premise message is in the
committed log before a record rests on it; every confirmation and settlement records how it
happened and can be undone.

### 9.3 Tests

- Unit tests with a fake dispatcher returning scripted answers: each reader outcome, each
  judge verdict, the clarifier's three-question cap and escalation, the trial flow, settling,
  undo, and every failure of 9.1. No network. Also: the word rules of
  `approvals.py` are not called when the dispatcher fails; a result file written by the agent
  confirms nothing; the clarify gate (pending job refuses edits, late result, timeout); a
  message that is not intent (a question) produces no card. Also: one read job per turn and one
  judge job per capture (batching); the status line reads "reading your answer" while the read
  job runs and nothing is confirmed until it returns; the judge question carries the question a
  short answer answered; a capture commits the message to the log; the backlog pass is one
  pass with one card per feature; a derived-record kind switches settling on by itself when
  calibration passes and an intent kind does not; progress is reported by the worker.
- One end-to-end test per dispatcher (`claude-code`, `hermes`, `openrouter`), marked to run
  only where that host or credential is present.
- An evaluation set of real cases, run against the configured model before calibration and
  after any model or prompt change: the owner's "INT-008 ok, I am not sure I agree with
  SR-088. In terms of UX, some features might have to remain internal to plumb." (accepts
  INT-008, changes SR-088); INT-016's first read-back (beyond: one line per record, a token
  budget); INT-013's first read-back (beyond: maintenance mode); INT-004, INT-006, INT-007
  (supported); "A" for INT-008 with its stored question (supported); "Reject all G" for the
  ten generated variations (rejected); "Confirm SR-097, SR-098, INT-24" (accepts all three);
  and messages that need no clarification, so that the clarifier's false-gap rate (questions
  asked that change nothing about what gets built) is measured and reported with the results.

## 10. What changes in existing records and code

The owner confirms every change below; the agent applies none by itself.

| Record or module | Fate | Note |
|---|---|---|
| `INT-028`, `INT-029` | reworded | Drop the labelled fallback (owner, 9 Oct: "No labelled falback. If a model is unreachable, throw an error"); an unreachable model is an error that confirms nothing. Recaptured with that answer as their source. |
| `SR-005` | superseded | By the reader's rule (4.1) and the worker's write path (4.4); the terminal y/N stays. Its EX-3, EX-4, EX-7 and EX-9 to EX-13 (the affirmation, objection, scope and reservation checks of an agent-run relay) are removed; an agent-run prose relay no longer exists (4.1). |
| `SR-088`, `SR-065` | narrowed | Kept for typed `/plumb` commands naming IDs; their plain-words matching (SR-088 EX-3, EX-6 and EX-7) is removed (INT-029); typed `/plumb confirm` takes IDs only (4.1). |
| `SR-098` | superseded | The reader handles mixed answers; its examples become evaluation cases. |
| `SR-090` | superseded | Its `owner_scope` sentence rule is what the reader replaces; dropped from CAPTURE2. `SR-091` is kept (EX-3 and EX-4 resolved in section 7). |
| `SR-041`, `capture/autoapprove.py` | superseded | By settling (section 7); SR-041's exclusions move to SR-106. |
| `SR-040`, `SR-042` | reworded | Around the judge's verdicts. |
| `SR-043` | narrowed | One question per message stays outside a card; a card question (SR-103, up to three) is a DEC that matters, recorded by plumb. |
| `SR-081` | kept, reworded | Early-conflict cards show before a read-back; the clarify card shows after them. Its answers (EX-6, EX-7, EX-9, EX-10) go through the reader instead of `relay_choice`'s word rules. |
| `SR-086` | kept | Its buttons are reused by 4.4 and 9.2 (its secret is not: the worker holds none, 4.4). The panel is built when SP7 resumes (`DEC-031`); until then the typed commands are the route. |
| `SR-014` | corrected | Its hook budgets (600 ms prompt, 800 ms stop) already differ from the code (1200, 1400); the record is brought to the code, and the settled line must fit the stop budget. |
| `SR-012` | kept | Keeps its new example (answerable cards). |
| `INT-004`, `INT-003` | unchanged | Except the one gate of 4.3. |
| `DEC-029`, `DEC-030`, `DEC-031`, `DEC-028`, `INT-030`, `SR-108` | recorded 10 Oct, proposed | They are the owner's answers of 10 Oct and the progress request; this spec follows them (sections 2, 7, 8, 10); `SR-104`, `SR-106`, `SR-107` carry the matching examples. |
| New | | The reader (4.1), the judge (4.2), the clarifier and its gate (4.3), the worker and dispatch (4.4, 5), cards (6), trial and settling (7), the backlog (8). |

Code. The word rules of `approvals.py` (`owner_scope`, `change_clauses`, `objection_clauses`,
`affirmation_context_problem`, `_plain_named`) and `confirm.affirmation_in` are removed. Every
caller of a removed rule, and what replaces it:

| Caller | Replacement |
|---|---|
| `hosts/claude_code/prompt.py` (`awaiting_line`, the relay line) | The relay line is removed; the line names the shown records and the typed command. A reader job reads the answer. |
| `boundary/glance._message` (the "message also objects" flag, from `change_clauses`) | Removed; the reader's `change` and `rejected` answers on a record are shown on its merge line. |
| `confirm.entry_problem` (`affirmation_in` re-check of each agent-relayed approval) | Removed with agent-run relay; existing agent-relayed entries stay valid by their other checks. New by values are re-checked as in 4.4. |
| `mergedriver/conflicts.relay_choice` (SR-081; `affirmation_in`, `objection_clauses`, `affirmation_context_problem`, `named_takes`) | A reader job maps the answer to the merge card's question; an exact typed pick (the branch's name) stays. |
| `awareness/answer.choice_named` and `answer.py` (`objection_clauses`) | A reader job on the card's question; an exact typed pick stays. |
| `capture/clarify.py` (`AMBIGUITY_TERMS`, the unmatched-term depth) | The clarifier model's gaps (4.3). |
| `capture/assent` (assent words) | Removed; the reader. |

`stop.py` changes (cards, settled line). `confirm.py` is the one reader of the log for record
status and changes with it: `entry_problem`, `checked_entries`, `remaining_entries`,
`carry_renumbers` and the api `status` accept the `by` values `owner-words` and `settled` on
`approval` and `undone` on `revocation`, each with its re-check (4.4). `capture/calibrate.py`
(`labelled_set`, `KINDS`, `calibrate`) changes as section 7 says. `log.py` accepts the new
`by` values; the model contracts gain the status `settled` (schema, `status` counts,
`owner_text`, `boundary/glance.py`, premerge and `validate`, which treat it as confirmed and
list it apart). SP7's CAPTURE2 lane (approvals, `owner_scope`) is re-scoped: SP8 replaces the
parsing it was going to extend; SP7's panel draws SP8's cards and buttons, and its pre-tool
hook carries the gate of 4.3. Because SP8 now comes before SP7 resumes (`DEC-031`), the gate's
PreToolUse fast path (4.3: read one state file, refuse edits while it says closed, in shell,
within 50 ms) is built with SP8 as a minimal hook of its own, and SP7's PLUGIN lane adopts it
when it resumes instead of building it again. The hooks fix that comes first (`DEC-031`) is its
prerequisite: the fast path needs hooks that run within their budget.

## 11. Out of scope

Choosing models per step for the coding agent itself; routing the coding agent's work
through JEV; any change to how tests are selected or run.

## 12. Open questions

1. Hermes delegation: the exact call and whether a delegated child can run without tools,
   from SR-099's assessment.
2. Whether a judge `supported` verdict should also require that the record's examples were
   generated from the owner's words rather than invented (measured on the evaluation set
   before deciding).
3. The clarifier's false-gap rate has no pass mark yet: it is measured and reported (9.3), and
   the owner chooses the acceptable rate once there is a number.
4. The reader's starting threshold of 0.9 (4.1) is plumb's own cautious choice, not the
   owner's; it applies only until the trial answers set the real one.
