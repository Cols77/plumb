# Sub-project 8 spec: intent by exception (understood by models, confirmed only when uncertain)

Status: proposed, 2026-10-09, written from a brainstorming session with the owner (answers
quoted in section 2). Records: `INT-028` (approval understood from meaning or a button),
`INT-029` (models, not fixed rules, wherever plumb interprets words), `DEC-027` (which model
reads the owner), `SR-096` and `SR-097` (rejections and short answers, kept), `SR-012`
(the summary shows what awaits the owner as an answerable card). When this spec and the
owner's quoted words disagree, the words win.

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
- the proposed backlog trends to zero instead of growing (it stood at about 150 on 9 Oct).

## 2. The owner's decisions (brainstorming, 9 Oct)

| Question | Owner's answer |
|---|---|
| What does the owner personally confirm? | "Agreed with A, but only partly. Only uncertain intent should need confirmation. Same for requirements, decisions and detailed examples derived from it. When resolution can't be fast-forwarded, cards that expose the topic and the issue are provided by the agent and suggest resolutions." |
| When may plumb settle without asking? | A: an independent, calibrated model finds the record faithful to the owner's words and to what they already confirmed |
| How does the owner see what was settled? | A: one short line per turn, titles only, each with Undo; the full list at the merge |
| When a request has gaps? | B: clarify up front, before building |
| How are up-front questions asked? | C: one card, at most three questions with suggested answers; smaller gaps become assumptions on the same card; more than three real questions escalate to a short spec session |
| Until the model has proven itself? | A: a trial in which every judged item comes as "plumb would settle these; right?", and the answers both settle and calibrate |
| The ~150 proposed records? | A: fed into the trial in small batches; flagged ones come as issue cards |
| Architecture | 1: background judging started by the hooks |
| Worker | "That worker should be integrateable in claude and hermes agents using the expected technics that allow to dispatch work to an agent in the context of that coding harness." |
| Fallback | "No labelled falback. If a model is unreachable, throw an error" |
| Principle | "most of the time the system shouldn't rely on deterministic tooling to understand intent or process text, unless we're sure the deterministic solution can handle any type of situation" (INT-029) |

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
   and against what the owner confirmed.

## 4. The pieces

All four live in a new package `plumb.understand` (host-neutral core), with one adapter per
host for dispatch (section 5).

### 4.1 Reader: what the owner answered

Input: the owner's logged message (text and digest); the stated set of the reply before it
(the records shown, each at its hash, with the text that was shown); the open cards (their
questions and suggested answers). Output, one entry per shown record or card question:

```json
{"id": "INT-008", "hash": "sha256:...", "answer": "accepted|rejected|change|open",
 "rejection": "misread|intent-changed|null", "change": "what the owner asked to change, or null",
 "evidence": "the owner's words that carry this answer", "confidence": "high|medium|low"}
```

plumb then applies only exact checks: the message is in the prompt log (via the hook); each
id was in that stated set at that hash; `evidence` occurs in the message. An `accepted`
entry with high confidence confirms the record as "you said: <evidence>" (`by:
owner-words`, with the digest and the reader's job id). A `rejected` entry is logged as an
SR-096 rejection (`misread` is the calibration "no"). A `change` entry becomes a recapture
task for the agent (read back at the next turn). `open`, or any confidence below high,
confirms nothing. Records named in the message but not shown are never confirmed: plumb
shows them as cards first (SR-088's rule, kept).

This replaces, as the way approvals are understood, the affirmation-term list, the
objection words, the clause splitting and the plain-words matching of `approvals.py`
(`owner_scope`, `change_clauses`, `_plain_named`, `affirmation_in`). They are removed, not
kept as a fallback (principle 2). `plumb relay` remains for the owner's own terminal and for
tests, with the reader's output as its input instead of a quote parse.

### 4.2 Judge: can this be settled?

Input: one record (an intent's read-back, will, won't; a requirement's statement and
examples; a decision's question and chosen option), its premise (the owner's whole logged
message or messages it derives from, plus the stored question for a short answer, plus the
parent intent when the owner confirmed it), and the owner's confirmed or settled records it
relates to. Labelled assumptions are shown but are not part of what is judged.

Output:

```json
{"verdict": "supported|beyond|contradicts", "beyond": ["what the record asserts that the owner's words do not"],
 "contradicts": ["what conflicts, with the record it conflicts with"], "confidence": 0.0}
```

`supported` means the owner's words support everything the record asserts as theirs, and
every addition is a labelled assumption that does not change what gets built. Only a
`supported` verdict at or above the calibrated threshold can settle a record, and only once
settling is on (section 7). `beyond` and `contradicts` produce an issue card (section 6).
The judge replaces the strict-entailment question of today's triage (`capture/triage.py
claim()`), which rated faithful elaborations as unfaithful.

### 4.3 Clarifier: is the request clear and complete?

Runs when the prompt hook flags a message as new or changed intent. Input: the message, the
confirmed and settled records it touches. Output: a draft read-back (will, won't, assumptions,
two or three concrete examples) and the gaps that change what gets built, ranked, each with
two or three suggested answers and a recommended one. plumb shows one card with at most
three questions (section 6); the remaining gaps become assumptions on the same card. More
than three questions that change what gets built escalate to a short structured session
ending in an up-front spec (INT-004). A request with no such gap produces no card: work
starts at once. The plumb-clarify skill tells the agent to present the card and wait for it
before building (the owner chose "clarify up front").

### 4.4 Worker and jobs

A job is a file `.plumb/session/<id>/jobs/<job-id>.json`: kind (`read`, `judge`,
`clarify`), inputs with their hashes, the answer schema, created-at. A result is
`.../results/<job-id>.json`: the validated answer, the model used, timings, or an error.
Jobs are idempotent: the same inputs give the same job id, so a retried hook never runs a
job twice. The prompt hook queues `read` (when the previous reply stated anything) and
`clarify` (when the message is flagged as intent); `plumb capture` queues `judge` for every
record it writes or changes. The worker is started detached by the hook that queued (the
hook returns within its budget); a running worker picks up new jobs; at most one worker per
session.

## 5. Dispatch through the host

The core defines the jobs; each host adapter runs them the way that harness dispatches work
to an agent. Exactly one dispatcher is configured (`understand.dispatch`); when it fails,
the job fails with an error (principle 2). There is no automatic second route.

| Host | Dispatcher | How |
|---|---|---|
| Claude Code | `claude-code` (default there) | `claude -p` with a plumb-shipped agent (`--agents` file, a prompt per job kind), `--model` from config (default `haiku`), `--tools ""` (no tools), `--json-schema` with the job's answer schema, `--output-format json`, `--no-session-persistence`. Run without `--bare`, so the owner's Claude login is used; plumb's own hooks see `PLUMB_JOB=<job-id>` in the environment and exit at once, so a job never queues jobs. With an API key configured the adapter may add `--bare`. |
| Hermes | `hermes` | A delegated child session (Hermes's own delegation, the same mechanism the Hermes adapter already excludes from plumb's hooks by `parent_session_id`), given the job prompt and schema, without tools. The exact call follows SR-099's assessment and the Hermes adapter plan (`.hermes/plans/2026-10-09_120026-plumb-hermes-spec-and-plan.md`). |
| Any | `openrouter` | A direct call through the credential plumb already reads for JEV, with the same schema. A configured choice, never a silent fallback. |

DEC-027 is revised to: "a small model through the host's own dispatch (Claude Code: Haiku via
`claude -p`), or OpenRouter when configured; the coding agent never reads its own approvals".

## 6. Cards

Every card carries a topic (in the owner's terms, no IDs alone, no internals), the issue,
the evidence (the owner's words and what conflicts with them), and two or three suggested
resolutions with the recommended one first. plumb builds the card's facts; the agent words the
suggested resolutions for the owner and presents the card in its reply (SR-012's new example:
never only as an ID or inside tool output). With SP7, the same card is drawn in the panel
with a button per resolution and Accept / Reject.

| Card | When | The owner's answer does |
|---|---|---|
| Clarify | 4.3 found gaps that change what gets built | answers become part of the read-back; assumptions not contradicted are settled with it |
| Trial batch | during the trial (section 7), up to five items the judge would settle | yes settles the item and labels it "yes" for calibration; no rejects it (`misread`) |
| Goes beyond your words | judge `beyond` | keep (the owner confirms the addition), drop it, or reword |
| Contradicts | judge `contradicts`, or an answer conflicting with a confirmed record | pick a version, or combine |
| Couldn't check | a job failed (model unreachable, malformed answer) | nothing to answer; says what was not done and that it will retry |

The end-of-turn summary shows, in this order: confirmations from the owner's words ("you
said ..."), the settled line ("Settled from your words: <title>; <title>", each with Undo),
the cards. Undo is plain words or a button; it reopens the item as a card.

## 7. Trial, calibration and settling

- **Trial (default when no passing calibration exists).** Every judged `supported` item is
  offered in a trial batch instead of being settled. The owner's yes and no are the labelled
  examples; `misread` rejections (SR-096) are real "no" examples. SR-042's thresholds apply
  per kind, with the judge's verdict as the score.
- **Calibration** reruns after each trial batch answered, cheaply, from logged judgments
  (no new model calls). When it passes for a kind, the summary says so once and offers to
  turn settling on for that kind; the owner turns it on with words or a button (an
  owner-only setting, SR-041).
- **Settling** marks a record `settled` (`by: plumb-judge`, with the job id, the model and
  the premise digest). A settled record counts as confirmed for the merge boundary, is listed
  separately at the merge, and returns to proposed if its text or its premise changes.
- **Model or prompt change** (a new model version, an edited job prompt) suspends settling
  until the evaluation set (9.3) passes again and calibration is rerun.

## 8. The backlog

The ~150 proposed records enter the trial as a background queue: `judge` jobs at a low rate
(a configurable number per turn, default 10), batches of up to five offered per turn
alongside any new work. Records the judge flags come as issue cards. Records whose premise is
a fragment get their premise rebuilt from the logged message when the prompt log holds it;
when it does not (records imported from the 5–7 Oct sessions), the issue card says the
original words are not on file and offers the records' own read-back for the owner to accept
or correct.

## 9. Failures, safety and tests

### 9.1 Failures

- Model unreachable or dispatcher missing: the job's result is an error; the summary shows a
  "couldn't check" line; nothing is confirmed, settled or rejected; the job is retried on the
  next turn; three consecutive failures show in the status line.
- An answer that fails the schema: an error for that job, never a reading.
- A job not finished at the end of the turn: collected at the next turn.
- A record edited after it was shown: an answer about the old version confirms nothing.

### 9.2 Safety (exact, deterministic)

Kept from today and checked in code: the owner's message is in the prompt log; a record is
confirmed only at the version shown; the agent cannot confirm, settle or turn settling on by
itself (the session marker and the guard); owner-only settings change only on the owner's
words read by the reader or a button; every confirmation and settlement records how it
happened and can be undone.

### 9.3 Tests

- Unit tests with a fake dispatcher returning scripted answers: each reader outcome, each
  judge verdict, the clarifier's three-question cap and escalation, the trial flow, settling,
  undo, and every failure of 9.1. No network.
- One end-to-end test per dispatcher (`claude-code`, `hermes`, `openrouter`), marked to run
  only where that host or credential is present.
- An evaluation set of real cases, run against the configured model before calibration and
  after any model or prompt change: the owner's "INT-008 ok, I am not sure I agree with
  SR-088. In terms of UX, some features might have to remain internal to plumb." (accepts
  INT-008, changes SR-088); INT-016's first read-back (beyond: one line per record, a token
  budget); INT-013's first read-back (beyond: maintenance mode); INT-004, INT-006, INT-007
  (supported); "A" for INT-008 with its stored question (supported); "Reject all G" for the
  ten generated variations (rejected); "Confirm SR-097, SR-098, INT-24" (accepts all three).

## 10. What changes in existing records and code

- `SR-005` (only the owner's explicit words confirm) is superseded by a requirement that
  states the reader's rule: the owner's logged words, as read by the reader, or a button.
- `SR-098` (mixed answer lists by clause rules) is superseded: the reader handles mixed
  answers; its examples become evaluation cases.
- `SR-040` and `SR-042` (triage and calibration) are reworded around the judge's verdicts.
- `SR-012` keeps its new example (answerable cards).
- New requirements: the reader (4.1), the judge (4.2), the clarifier (4.3), the worker and
  dispatch (4.4, 5), cards (6), trial and settling (7), the backlog (8).
- SP7's CAPTURE2 lane (approvals, `owner_scope`) is re-scoped: SP8 replaces the parsing it
  was going to extend; SP7's panel draws SP8's cards and buttons.

## 11. Out of scope

Choosing models per step for the coding agent itself; routing the coding agent's work
through JEV; any change to how tests are selected or run.

## 12. Open questions

1. Hermes delegation: the exact call and whether a delegated child can run without tools,
   from SR-099's assessment.
2. Whether a judge `supported` verdict should also require that the record's examples were
   generated from the owner's words rather than invented (measured on the evaluation set
   before deciding).
