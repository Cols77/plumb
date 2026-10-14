# plumb concept spec

Confirmation today (INT-036, INT-037, INT-041): a card is a read-back of a request, a choice
(one question at a time, the recommended option first, optionally with a block diagram) or a
trial. A record is confirmed by the owner's answer on a card, by the owner's own typed command
(`/plumb approve ...`), or by the judge when the owner has turned auto-approve on. Context
alone never confirms. There is no settle on/off, triage offer, `plumb relay`, `/plumb confirm`
or agent-run conflict relay; passages below that name them are history.

Status: reference document. Written 2026-10-05 from the owner intent brief of the same day.
The owner does not review this document; independent verifier agents check it, and every
plumb artifact, against the owner's words quoted below. When this document and the owner's
quoted words disagree, the quotes win and this document is corrected. The brief's
owner-proxy rulings R1 to R7 are binding and are applied here: R1 in sections 4.2, 5 and 6.6,
R2 in 4.6 and 4.7, R3 in 6.6, R4 in 6.4 and 8, R5 in 7.2, R6 in section 1 and 11, and R1, R2,
R4 and R5 together at the merge boundary (7.5). R7 governs how verifiers grade this document.
The owner's decisions of 2026-10-06, rulings R8 to R12, are newer than the first version of
this document and supersede it where they differ: R8 (JEV-assisted confirmation and its
commands) in 4.2, 4.6, 6.5, 8 and 12; R9 (presentation and context economy) in D13, 6.1,
6.2 and 6.5; R10 (parallel work) in section 11, item 6; R11 (brainstorming-grade
clarification) in 5.2 and 9; R12 (the JEV pieces ported from pi-agent-factory) in 8. R13,
the owner's direct answers to five checkpoint questions of 2026-10-06 (D18), is applied in
4.6 (the triage offer, auto-approval eligibility, the "self-recorded message" label), 8
(calibration and the offer line) and 9 (hosts without a prompt hook).

A plumb line hangs straight under its own weight and shows whether a wall is true. plumb does
the same for a codebase. It shows, cheaply and on every turn, whether the system being built
still matches what its owner intends.

## 1. Owner intent

Purpose, in the owner's words:

> "the goal of coherence tooling is to ensure the alignment between user's intent and
> understanding of what he wants to build and the current state of the system being built."

> "I find that the main issue with current coding agents is that we either have to micro manage
> them or 'vibe code / Spec driven develop' the thing. I'd like coherence to make vibe coding
> grounded on the projects artifacts in an efficient, reliable and trustable manner."

On the governed workflows of pi-agent-factory:

> "they seem pretty heavy, and also quite orthogonal to the developments claude and other coding
> agents are doing ... whether that really makes sense to have those heavy blackboxed workflows
> in the first place. isnt there a more elegant way of doing things nowadays? ... a lighter,
> more elegant and interactive way to leverage coherence."

On planning:

> "Don't you think that we'd need planning features still? how do you ensure that people defining
> their system will have their intent succesfully translated?"

The owner's decisions that shape plumb. The numbers follow the owner intent brief (decisions
1 to 12); D13 to D17 are the owner's rulings R9, R8, R10, R11 and R12 of 2026-10-06, and
D18 is the owner's checkpoint answers R13 of the same day:

| # | Decision | Owner's words |
|---|---|---|
| D1 | Standalone tool for any repository, designed so pi-agent-factory can migrate onto it. | "A / B" |
| D2 | Incremental intent capture by default; large, risky or cross-cutting work escalates to an up-front spec the owner approves; same artifacts in both modes; plumb suggests when to escalate. | "C" |
| D3 | Host-neutral core (CLI and library) with thin adapters, Claude Code first. Reuse pi-agent-factory code by extraction, without its per-turn admission and coordination weight. | "B. I guess the CLI / lib can be re-used from pi-agent-factory?" |
| D4 | A new, simpler record model with an importer, keeping familiar IDs and the KEEP list (section 4). | "B. can be the way to go but be careful about loosing some important features, for example the hash is important for staleness detection." / "Keep list looks fine" |
| D5 | Mostly in the background: status line, short end-of-turn summary, questions only on a real intent change, an unconfirmed decision that matters, or a regression (section 6.6). | "A" |
| D6 | First scope is core, grounding loop and covering-test verification, dogfooded on plumb itself. | "Would be nice to dogfood the version to itself as soon as possible and build with it." |
| D7 | Reuse existing artifacts: SR, FEAT and NC formats and IDs stay compatible. | "think of re-using the existing artifacts no? SRs FEATs..? It's up to you." |
| D8 | JEV is an optional judgment backend with an LLM cascade; plumb works without it. | "I think it might be usefull to integrate it in this new version too?" |
| D9 | pi-agent-factory goes into maintenance mode after the current integration batch lands; a fork plan is required. | "consider stopping developments on pi-agent-factory if it takes too much RAM" |
| D10 | Spawn a workflow that captures the intent in this concept spec as the future reference, then plans the dogfooding work and the pi-agent-factory fork. | "Consider spawning a workflow ... to capture this intent in a concept spec that we will then be able to refer to in the future, and then also plan for the work needed for dogfooding and the kind of pi-agent-factory fork that is about to happen." |
| D11 | Owner does not review; agents verify: the owner reviews neither this spec nor any plan, and independent verifier agents check every artifact against the owner's words. Implementation available by tomorrow morning (9 hours): sub-project 1 has a time-boxed slice that must be dogfoodable by then (section 11). | "I wont review the concept spec or any plan. use agents that verify that my intent based on that conversation is respected. I want to have the implementation available by tomorrow morning (in 9 hours)." |
| D12 | The repository and CLI are named plumb (a plumb line checks true alignment). | "coherence is a bit confusing because it's a usefull word to use." |
| D13 | Presentation and context economy (ruling R9). Hooks inject a compact, deduplicated delta: one line per record (ID, title, state), only when it is newly relevant in the session or changed, within a per-turn token budget, nothing when nothing is new; details by `plumb show`; a session brief of a few lines and a pointer. The owner sees a one-line status card by default and the full intent card only when it matters, configurable `full`, `compact` or `off`. Owner commands take plain language and answer in the owner's terms (`/plumb explain <anything>` replaces `plumb why <file\|ID>`). `plumb view` writes a generated Obsidian vault of the records for deep review; editing it never approves. | "isnt there a smarter way to do this? Isnt the risk to bloat the context way too fast with redundant tokens?" / "a proper way to present the relevant information to the user, but only when it is important. Otherwise it should only be small card ... collapsible or configured to be disabled." / "the user don't necessarily know the code ... All the commands should be designed to handle this properly" / "use obsidian as the frontend perhaps?" |
| D14 | JEV-assisted confirmation (ruling R8). A: triage, always available: the judgment backend rates each proposed record's faithfulness to the owner's words and groups the low-risk ones, which the owner confirms in one line with explicit words; it never approves by itself. B: a narrow auto-approval, opt-in and off by default, only for records derived directly from the owner's own words, only with JEV and a passing calibration (D17), recorded `by: auto-jev`, labelled everywhere, revocable and listed at the merge boundary; never for a decision that matters, an escalated spec set or an edit of an owner-confirmed record. Commands `plumb triage`, `plumb config auto-approve on\|off`, `plumb config show`, `plumb jev status`, `plumb jev setup` (sections 4.6 and 8). | "Ok for A+B" / "there should be a command for that" |
| D15 | Parallel work by awareness instead of locks: git is the coordinator and plumb holds no shared mutable runtime state; collision-free IDs, logs that never conflict, a frontmatter-aware merge driver, cross-worktree awareness, and `plumb check --merge` on the merge result (ruling R10; sub-project 6, section 11). | "yes" |
| D16 | Brainstorming-grade intent clarification: a `plumb-clarify` skill, written for plumb, that scales its depth to the request (trivial, incremental, escalated), asks only the questions whose answer changes what gets built, one per message, multiple choice with a recommendation, each recorded as a `DEC` that matters (ruling R11; sections 5.2 and 9). | "during the intent clarification, claude code should use some kind of brainstorming skill to improve intent capture capability" |
| D17 | Port the missing JEV pieces from pi-agent-factory: calibration on the owner's own confirmed and revoked records, a prerequisite for D14 B; edge alignment (`plumb align`); ownership proposals for untraced changes; a hidden-dependency scan as drift hints. All work in a degraded form with the heuristic, all are logged and advisory (ruling R12; section 8). | "Ok adopt the missing pieces you're mentionning" |
| D18 | Checkpoint answers (ruling R13, given directly by the owner). Q1 calibration (DEC-018): mixed evidence, per record kind at least 20 of the owner's past decisions and at least 5 "no" examples, up to half of them generated variations, none wrongly accepted; the real/generated split shown in `plumb jev status` and the calibration entry. Q2 grouped ok (DEC-017): the offer line names up to about 5 records by title, then "+N more (see plumb triage)"; the owner's "ok" approves exactly the pinned list (hashes), which `plumb triage` shows in full. Q3 auto-approval: a requirement qualifies only when JEV judges that the owner's logged words support its wording and every one of its examples. Q4 hosts without a prompt hook: a chat "ok" may confirm, labelled "self-recorded message" in `plumb show`, the merge-boundary glance and the host status. Q5 scope: everything in R8, R11 and R12 is a must (sections 4.6, 8 and 9). | Q1 "MIXED EVIDENCE" / Q2 "TOP 5 + MORE" / Q3 "WORDING + EXAMPLES" / Q4 "YES, LABELLED" / Q5 "EVERYTHING" |

## 2. Problem

Coding agents fail their owners in two opposite ways. Micro-management keeps the agent aligned
but costs the owner all their attention. Vibe coding saves attention but lets the code drift
from what the owner meant, and nothing notices until something breaks. Heavy spec-driven
frameworks, including pi-agent-factory's governed execution, buy alignment with long, opaque
pipelines: state machines, consent phrases, review swarms, admission control. They cost
minutes per step and hide their state.

plumb takes a third path. The owner's intent lives in small plain-text records in the
repository. Those records are linked to the tests and code that realize them, with content
hashes on every record and every link. A few cheap hooks keep the agent looking at those
records on every turn and report drift the moment it appears. The owner is asked something
only when the answer really changes what gets built.

## 3. Principles

1. **Grounding, not orchestration.** plumb never drives the agent through phases. The agent
   works as it normally does; plumb supplies the relevant records as context and reports
   drift. There is no run state machine.
2. **Context over procedure.** Telling an agent *which* requirements and *which* tests apply
   works better than telling it *how* to work. The TDAD study found that a grep-able test map
   with a short skill cut regressions by about 70%, while procedural TDD instructions that did
   not name the tests made regressions worse. plumb's per-turn output names records and tests;
   it never carries long procedures.
3. **Cheap checks every turn, heavy guarantees only at merge boundaries.** Per-turn hooks are
   deterministic, read files plumb already knows, and finish well under 2 seconds (target:
   p95 under 500 ms). The full test suite, claims audit and log-integrity audit run only when
   work merges. No per-turn path ever selects or requests the full suite: the tests the agent
   is asked to run in a turn are a targeted set, capped by a time budget of seconds
   (section 7.2), and anything that needs a full run sets `full verification pending`, which
   the next merge boundary satisfies.
4. **Inspectable artifacts.** All committed state is Markdown with YAML frontmatter, or JSON, in
   git. Caches and session state are plain JSON too, are gitignored, and can be deleted at any
   time without losing information. Nothing hides in a database or a service.
5. **Trust from evidence.** Claims of alignment rest on content hashes, approvals pinned to
   exact content, test evidence pinned to code and environment identity, and hash-chained
   append-only logs. When identity is unknown, plumb assumes nothing: evidence is not reused
   and the state is reported as unknown. The trust model is stated honestly: the record is
   tamper-evident, not tamper-proof against a malicious agent (section 4.6).
6. **Few, meaningful interruptions.** Three triggers can interrupt the owner (section 6.6).
   Everything else is logged and readable on demand. Read-backs and examples never block
   work in progress; the owner confirms them in one line whenever they choose, and a merge
   requires every requirement it touches to be confirmed.

## 4. Record model

### 4.1 Layout

Everything plumb owns lives under `.plumb/` at the repository root:

```
.plumb/
  config.yaml              # optional settings (source dirs, thresholds, judgment backend)
  claims.yaml              # SR trailer policy: epoch, exempt globs, NC-backed baseline
  intents/INT-001.md
  requirements/SR-001.md
  decisions/DEC-001.md
  features/FEAT-001.md
  ncs/NC-0001.md
  log/<kind>/<UTC-stamp>-<uuid8>.json   # append-only, committed (approval, prompt, judgment, ...)
  cache/                   # gitignored, derivable (import map, evidence reuse, env identity)
  session/                 # gitignored, per-session turn state for the hooks
```

Dependencies: Python 3.12 standard library plus PyYAML. Frontmatter is parsed by a small
helper (split on the first two `---` lines, `yaml` safe loader, C loader when available).

### 4.2 Record kinds

Every record is a Markdown file whose frontmatter carries an `id`, a `title` and kind-specific
fields, followed by a free Markdown body. Body wikilinks (`[[SR-004]]`, `[[SR-004|title]]`)
are allowed and are checked like links.

| Kind | ID | Purpose | Key fields |
|---|---|---|---|
| Intent | `INT-###` | What the owner wants, in the owner's words. | `quote` (verbatim owner words), `readback` (restatement in the owner's terms), `will`, `wont`, `assumptions` (each labelled), `mode: incremental \| escalated` |
| Requirement | `SR-###` | A testable statement of required behavior. | `statement`, `feature`, `examples` (given/when/then cases, ids `EX-n`), `links` |
| Decision | `DEC-###` | An ambiguity made explicit. | `question`, `chosen`, `alternatives`, `rationale`, `matters: true \| false` |
| Feature | `FEAT-###` | Groups requirements (replaces bundles). | `description`, `requirements` |
| Nonconformance | `NC-####` | A known defect against a requirement, first-class. | `status: open \| corrected \| waived`, `detected_by`, `corrected_by`, `external_ref` |

A requirement in plumb's own repository looks like this:

```yaml
---
id: SR-004
title: Links pin both ends
feature: FEAT-001
statement: Every link records the content hash of both of its ends, and plumb reports the
  link as stale when either end's current hash differs from its pin.
examples:
  - id: EX-1
    given: SR-004 links to a test whose pins are current
    when: the test function's body changes
    then: plumb check reports the link stale and names the test end
  - id: EX-2
    given: the same link with current pins
    when: the test file is re-saved with CRLF line endings and no other change
    then: the link stays current
links:
  - {kind: derives_from, to: INT-001, pin: {from: "sha256:...", to: "sha256:..."}}
  - {kind: verified_by, path: tests/test_links.py, test: "tests/test_links.py::test_pin_drift",
     example: EX-1, pin: {from: "sha256:...", to: "sha256:..."}}
---
```

Decisions are immutable once confirmed: changing one means writing a new `DEC` with a
`supersedes` link. Other records may be edited at any time, and editing a confirmed record
is exactly the drift signal the approval pin is there to catch.

Requirement states are derived and never stored:

- **proposed:** no approval pins the current hash;
- **confirmed:** an approval pins the current hash. Only the owner's explicit words create
  such an approval: `plumb approve` in the owner's terminal (`by: owner`), or the owner's own
  affirming words in a prompt, recorded by the agent and quote-checked (`by: agent-relayed`,
  section 4.6). There is no "no-objection" approval. The one exception is the owner's own
  choice (D14 B): when the owner has turned auto-approval on, a record derived directly from
  the owner's words may be confirmed `by: auto-jev` under the conditions of section 8; it is
  labelled "confirmed by JEV" everywhere, so the owner always tells it from "confirmed by
  you";
- **covered:** confirmed, and every example has at least one `verified_by` link to an
  existing test;
- **verified:** covered, and every covering test has passing evidence for its current
  identity;
- **stale:** an approval or link pin no longer matches.

Work in progress never waits for a record to leave the proposed state (only a merge, or an
escalated spec, waits for confirmation). The agent builds on proposed records; the end-of-turn summary shows each newly proposed read-back and example with
status `proposed`, and the status line and session brief count the records still awaiting
confirmation. They move to confirmed only when the owner affirms them, in one line, in
conversation or by command, whenever the owner chooses (the in-flow confirmation path,
section 6.6). A proposed record becomes a question only under trigger 2 of section 6.6: when
work relies on it at a merge boundary, when it belongs to an escalated spec, or when a
contradiction involves it. At the merge boundary, every requirement touched by the change
must be confirmed (section 7.5). Trigger 1, which protects confirmed intent, rests only on
intent the owner actually affirmed.

### 4.3 IDs

IDs are kind prefix plus zero-padded number: `INT-###`, `SR-###`, `DEC-###`, `FEAT-###`,
`NC-####`. The next ID is reserved through the shared ref `refs/plumb/ids` with git's
compare-and-swap (`update-ref` with the old value), so the worktrees of one clone never get
the same ID; outside git it is the highest existing number plus one (SP6, SR-070). Identity
comes from the frontmatter `id`, never from the filename. Two records with the same ID (two
clones that numbered independently) are an error that `plumb check` and the merge boundary
report; `plumb merge-fix` renumbers the incoming record and every reference its side added,
never rewriting history (SR-071). Examples are numbered
inside their requirement (`SR-004/EX-2`). Imported acceptance criteria keep their `AC-n` IDs.

### 4.4 Content hashing and normalization

Every record has a content hash, `sha256:<hex>`, computed on read and never stored in the
record. The hash covers the record's meaning and ignores its formatting:

- all frontmatter fields **except `links`** (so pinning a link never changes the record's own
  hash), serialized as canonical JSON (sorted keys, UTF-8, no insignificant whitespace), so
  YAML style and key order do not matter;
- the body, with CRLF and lone CR converted to LF, trailing whitespace stripped from each line,
  trailing blank lines dropped, Unicode normalized to NFC, and generated blocks
  (`<!-- derived -->` ... `<!-- end derived -->`) removed.

Link ends that are not records are hashed as follows:

- a Python symbol (`path` plus `symbol: module:name`): the normalized source segment of that
  definition, found with `ast` in that one file, so edits elsewhere in the file do not make the
  link stale;
- a test node (`path` plus `test: path::name`): the normalized source of the test function
  (parameter ids are dropped);
- any other file: its normalized text, or its raw bytes for binary files.

Directories and globs cannot be link ends. Line numbers are never used as identity.

### 4.5 Links, pins and staleness

A link lives in the frontmatter of its source record. It names a `kind`, a target (a record
`to:`, or `path` with an optional `symbol` or `test`), and a `pin` holding the hash of both
ends at the moment the link was last confirmed. Link kinds:

| Kind | From to | Meaning |
|---|---|---|
| `derives_from` | SR, DEC, FEAT to INT | the requirement exists because of this intent |
| `decides` | DEC to INT, SR | this decision resolves an ambiguity in that record |
| `upstream`, `relates_to` | SR to SR | dependency, association |
| `implemented_by` | SR to code | this code realizes the requirement |
| `verified_by` | SR (optionally an `EX-n`) to test | this test checks the requirement or example |
| `corrects` | NC to SR or code | the nonconformance is against this target |
| `supersedes` | any to same kind | replaces an older record |

A link is **current** when both pins equal both current hashes, **stale** when either differs
(the report names which end moved), and **dangling** when its target does not exist. Dangling
links are errors. Stale links are drift signals: they appear in the end-of-turn summary and
the status line. They are cleared by `plumb repin <link>`, which records the new pins in the
source record and appends a `repin` entry to the log. Repinning a link whose record end
changed does not confirm the record; only an approval does that.

### 4.6 Pinned approvals

An approval is an append-only log entry: `{record, hash, by, at, evidence}`. A record is
confirmed exactly when its latest approval pins its current hash, so any later edit leaves it
unconfirmed until approved again. Links are outside that hash, so an approval of a requirement
also lists the code and test ends it owns at that moment; an end added later is put to the
owner at the merge boundary (section 7.5). There are no consent phrases. An approval comes
from one of two sources:

- the owner running `plumb approve SR-004`, or `plumb approve --proposed` to approve every
  record still proposed (the batch form; it lists the records and their hashes in the entry),
  in the owner's own terminal, outside any agent session (see the guard below). Such an entry
  is marked `by: owner`;
- the agent relaying an explicit confirmation the owner gave in conversation, with
  `plumb approve SR-004 --prompt <digest> --quote "<owner's words>"`. Such an entry is marked
  `by: agent-relayed` and carries the owner's affirming words verbatim plus the digest of
  the prompt that contained them, as logged by the prompt hook. The quote must itself affirm
  (for example "ok", "yes", "approve", "go ahead"); see check 3 below.

A confirmation requires the owner's explicit words. There is no "no-objection" approval:
silence, or a prompt that does not object to a stated record or is about something else,
leaves the record proposed. With no affirming words from the owner there is no approval.
Every merge boundary lists the `agent-relayed` approvals made since the merge base, each with
its quote, for a quick owner glance (section 7.5).

Two forms the owner chose on 2026-10-06 (D14) sit beside these:

- **Triage group (D14 A).** `plumb triage` groups proposed records by the judgment backend's
  faithfulness rating. The owner confirms the low-risk group in one step, either
  `plumb triage --approve low-risk` in the owner's terminal (`by: owner`, exactly the listed
  hashes). The offer line names up to about 5
  records of the group by title, then "+N more (see plumb triage)" (D18, R13 Q2); the stated
  set pins the whole group's hashes, `plumb triage` shows it in full, and the owner's "ok"
  approves exactly that pinned list, no more: a record changed since the offer is left out
  and named. An "ok" that objects to one of the group, or names records instead, does not
  confirm the group. The rating never approves anything by itself. A record joins the group
  only when its premise is the owner's verified words and nothing in it contradicts them,
  whatever the backend scored (one choke point, the low-risk admission of `plumb triage`):
  every quote it rests on must be verbatim in a prompt the host's prompt hook logged (a
  quote stored without `--prompt`, or resting on a self-recorded message, is shown
  individually as "quote not verified", and owner views call it "quoted, not checked
  against your logged prompt", never "your words"), and cheap checks find no changed number
  and no flipped will/won't or result against those words (the "no" cases of R13 Q1, the
  variations calibration generates); such a record is shown individually as "contradicts
  your words".
- **Auto-approval (D14 B).** Off by default. Only the owner turns it on, in the owner's
  terminal (`plumb config auto-approve on`, logged as an event; editing `config.yaml` alone
  does not turn it on), and only after a passing calibration for the current JEV model
  version (section 8). Then a record derived directly from the owner's own words (an `INT`
  read-back whose quote is verbatim in the logged prompt, an example restating the owner's
  given/when/then) that JEV judges entailed by that prompt is approved `by: auto-jev`. A
  requirement qualifies only when JEV judges that the owner's logged words support its
  wording AND every one of its examples; otherwise it waits for the owner (D18, R13 Q3). A
  prompt the agent recorded itself (no prompt hook) never supports one. It is approved with
  the score, confidence, prompt digest and backend version, hash-pinned like any approval.
  Never for a `DEC` with `matters: true`, an escalated spec set, an edit of a record the owner
  confirmed, or any record when JEV is unavailable; the heuristic never auto-approves. Such
  approvals are labelled everywhere, revocable with `plumb revoke`, and listed at the merge
  boundary beside the agent-relayed ones.

**Prompt-digest log.** On every owner prompt, the prompt hook appends a committed log entry
under `.plumb/log/prompt/` holding only `{digest, session, at}`: the `sha256` of the prompt
text, never the text itself. The text stays in gitignored session state for the rest of the
session, which is enough for the write-time check below.

**Guard against self-approval.** The agent has shell access, so without a guard it could run
`plumb approve` itself and produce an entry that looks like the owner's. plumb prevents this
with four cheap, deterministic checks, none of which calls a model:

1. **Session marker.** `plumb install claude-code` sets `PLUMB_AGENT_SESSION=claude-code` in
   the host's session environment (`.claude/settings.json` `env`). The variable reaches every
   shell command the agent runs, but not the owner's own terminal. When the marker is set,
   `plumb approve` and `plumb revoke` refuse to write a `by: owner` entry and accept only the
   `agent-relayed` form, which must cite `--prompt <digest>` and `--quote`.
2. **Tool guard.** A `PreToolUse` hook on the shell tool denies any command that runs
   `plumb approve` or `plumb revoke` without `--prompt`, or that unsets or overrides
   `PLUMB_AGENT_SESSION`. The same hook on the edit tools denies writes under `.plumb/log/`,
   so log entries can only be created through plumb. This is a string match on the command
   and the path, well within the hook budget.
3. **Write-time quote check.** `plumb approve --prompt <digest>` checks, before writing
   anything, that the digest exists in the prompt-digest log, that the prompt text held in
   session state hashes to that digest, and that the quote is a verbatim substring of that
   text (after the body normalization of section 4.4). It then checks that the quote
   affirms: it must contain, as a whole word or phrase, one of the configured affirmation
   terms (`approve.affirmations` in `config.yaml`; default ok, okay, yes, approve, approved,
   confirm, confirmed, agreed, lgtm, go ahead, sounds good). Finally it checks the targets:
   each approved record must have been stated in the agent reply just before that prompt
   (the stated set, section 6.6) and shown there in full, or be named by ID in the quote,
   so an "ok" about one thing cannot approve unrelated records or content the owner was
   never shown. The owner's words also decide which of those records the "ok" covers: when
   the clause the quote comes from (or the quote) names records, it confirms only those
   ("SR-001 is ok but DEC-001 is wrong" confirms SR-001 alone), and a record the prompt
   names next to objection or change words (wrong, not, instead, should, change, rewrite,
   except, ...) is never confirmed by it: an objection is not an approval. The owner names
   records in plain words as often as by ID (R9), so a record counts as named when the
   clause holds its ID or a distinctive word of its title, statement, examples or quote
   ("No, the pow example is wrong, it should return 9. Ok, carry on" objects to the records
   about pow); an objection that refers to "the example" or "the test" in general and names
   none objects to every record. A correction needs no objection word: a change clause is
   any clause that holds an objection word, opens with but, though, except, ..., holds a
   directive (make, accept, also, too, return, actually, ...) beside a word naming behaviour
   ("ok, and make cube accept floats too"), or says anything in plain words about a record
   the owner was shown, through its title, statement, examples, assumptions, won't list or a
   decision's alternatives, numbers included ("ok, please also accept floats" against a
   decision whose alternative is floats, "ok. Actually multiply by 0 gives 1" against an
   example saying 0); a clause naming no shown record still asks for a change when it holds
   a directive or a number ("ok, 3 minus 5 is 0 for us"). Only a clause repeating a
   decision's chosen option ("ok, orders only") or praising a record by its title ("ok, the
   multiply looks good") is not one. A change
   clause objects to the records it names; when none of the prompt's change clauses names a
   record by ID or in plain words among the records the owner was shown, it objects to every
   one: "ok, except 3 minus 5 should return 0" confirms nothing, since the correction may be
   about any of them. Beside an affirmation the burden is inverted, since no list of
   objection words is complete: the ok confirms only what the owner affirms without
   reservation. From the sentence holding the affirmation on, any clause that holds a word
   beyond the closed vocabulary of assent (affirmations, praise, carry-on words, function
   words, words for the shown records in general, record IDs) is a reservation: "yes, apart
   from the zero example", "lgtm, minus the zero example", "go ahead, skip the zero
   example", "ok, will check the examples tomorrow", "would that be ok if I sleep on it". A
   reservation holds back the records it names, by ID, in plain words or by kind ("the
   examples" are the requirements'), and every record shown when it names none. An ok
   scoped to one kind ("ok for the intent", "ok for the examples only") keeps only the whole
   records of that kind, none for the examples. When the prompt objects to something else, the quote must be the
   owner's whole statement ("Ok, carry on with the tests", never a bare "Ok" cut from it),
   the approval records `prompt_objects`, and the merge-boundary glance flags it and prints
   the owner's whole logged message beside the quote. The prompt hook's relay
   suggestion applies the same rule, so it lists every awaiting record only for a bare "ok".
   The same words sent twice ("ok" today and "ok" last week) share a digest; the check
   reads the latest logged prompt with that digest, the one the owner just sent, against
   the reply before it. An approval that fails any check is rejected with a
   non-zero exit and is not stored. The stored entry records the prompt digest, the quote,
   the digest of the quote, the matched affirmation term and the stated set, so the result
   of the check stays inspectable after the session state is deleted.
4. **Owner terminal, on every host.** Checks 1 and 2 need the host's help: an adapter that
   cannot set the marker or install a tool guard (section 9 and sp4) leaves the agent's shell
   looking like the owner's. So every owner-only command (`plumb approve`, `plumb revoke`,
   `plumb tests waive`, `plumb spec approve`, `plumb triage --approve`,
   `plumb config auto-approve`, and any later one) writes its `by: owner` entry through one
   choke point (`approvals.require_owner`) that, after the marker check, requires stdin and
   stdout to be interactive terminals and a `y`/`N` answered there. There is no flag that
   skips the question. An agent's shell tool runs without a terminal, so the command is
   refused (exit 3) whether or not the marker is set, and a piped `y` proves nothing. An
   agent that drives a pseudo-terminal could still answer the question; that is a deliberate
   bypass, covered by the trust model below, not the normal path.

`plumb check` re-checks every committed approval: each `agent-relayed` entry must cite a
prompt digest present in the prompt-digest log and recorded before the approval, and its
stored quote must contain an affirmation term and match its stored quote digest. Every
approval entry also records the session marker in force when it was written (or `none`), and
a `by: owner` entry written under a marker is reported as an error. The owner, inside an
agent session, confirms by saying so in a prompt (the in-flow path of section 6.6); in their
own terminal, they use `plumb approve`.

**Trust model, stated honestly.** The log is hash-chained and tamper-evident (section 4.7),
not tamper-proof against a malicious agent. The guard does not make the agent's shell a
sandbox: an agent determined to bypass it can forge an entry, or a prompt digest, before it
is committed. What plumb guarantees is that self-approval cannot happen by accident, is
refused on the normal path on every host (check 4 holds where a host cannot set the marker),
and that any edit, deletion or out-of-order insertion of a
committed entry shows up in `plumb check` and in git history. The merge-boundary list of
`agent-relayed` approvals with their quotes (section 7.5) is the owner's cheap backstop
against a relayed approval the owner never gave.

An escalated plan (section 5.2) is approved as a set: one approval pins a set hash over the
sorted member hashes. The set is anchored on an `INT` with `mode: escalated` and a `members`
list (`plumb spec approve INT-###` in the owner's terminal).

### 4.7 Append-only logs

Approvals, revocations, prompt digests, repins, test evidence promoted at merge boundaries,
judgments, claim ingestions and owner waivers are written as one JSON file per entry under
`.plumb/log/<kind>/`. Each entry is created with a no-replace link (`os.link` with a uuid
suffix, so two writers in the same second never collide) and is never edited. Each entry
carries its own digest and `prev`, the digest of the latest entry of the log when it was
written (read from a gitignored head pointer in `.plumb/cache/`, rebuilt by a scan when
missing), so the log is a hash chain. Branches that merge make the chain fork; that is
accepted as long as every `prev` resolves to an existing entry. Corrections are new entries
that reference the old one. `plumb check` verifies each entry's digest and its `prev` link,
so a modified entry, or a deleted entry that a later one points to, is reported; at merge
boundaries, plumb also checks against git that no committed entry was modified or deleted. The
earlier single-file logs (`events.jsonl`, `evidence.jsonl`) were migrated to entry files by
`plumb log migrate` with every digest and `prev` unchanged (SP6, SR-074); the emptied files
stay so that branches cut before the migration still merge.

### 4.8 Claims: `SR:` trailers

Commits declare the requirements they serve with an `SR: SR-004, SR-007` trailer, as in
pi-agent-factory. The `commit-msg` hook checks that each named ID exists. `plumb claims check`
compares claimed paths (files changed by commits that claim an SR) with declared paths (that
SR's `implemented_by` and `verified_by` ends) and reports changed but undeclared paths.
Exempt globs and an NC-backed baseline, which can only shrink, live in `.plumb/claims.yaml`.
Ingestion writes a small append-only record `{run_id, start, head, commits: [{sha, subject,
sr_ids, changed_files, exempted}]}` from a single `git log` call per range.

## 5. Intent translation

### 5.1 Mechanisms

These five mechanisms, agreed with the owner, turn what the owner says into records that can
be checked:

1. **Read-back in the owner's terms.** Before building, the agent restates the request in its
   reply: what will be done, what will not be done, and every assumption, labelled as an
   assumption. The read-back is a statement, not a question ("Building X, not Y; assuming Z.
   Say so if wrong."), and the agent goes on working. It is recorded at once as a proposed
   `INT` record with the owner's quote beside it, appears in the end-of-turn summary with
   status `proposed`, and becomes confirmed only when the owner affirms it (the in-flow
   confirmation path, section 6.6).
2. **Requirements anchored in confirmed examples.** Each requirement carries concrete
   given/when/then examples, including edge cases. The agent states the examples in the same
   non-blocking way and records them as a proposed `SR`, shown in the end-of-turn summary with
   status `proposed`; they become confirmed only when the owner affirms them, in one line, in
   conversation or by command. Each example becomes an acceptance test linked by
   `verified_by`. Every requirement a change touches must be confirmed before that change
   merges (section 7.5).
3. **Ambiguity as explicit decisions.** When two readings fit, the agent writes a `DEC`
   ("I assumed A; B also fits") instead of choosing silently.
4. **Traceable links.** Intent to requirement to examples and tests to code, each link pinned
   at both ends.
5. **A living record kept honest by drift signals.** Stale pins, unconfirmed edits and failing
   covering tests show up on the next turn, not at release time.

Confirmation always rests on the owner's explicit words (a command, or the owner's own
affirming words in a prompt), never on silence or on a prompt that merely does not object.
During work it is never a blocking question: the owner confirms in one line whenever they
choose. A read-back or example becomes a question only under trigger 2 of section 6.6 (an
unconfirmed decision that matters): when work relies on it at a merge boundary, when it
belongs to an escalated spec, or when a contradiction involves it. Only the three triggers of
section 6.6 can make the agent stop and ask.

### 5.2 Incremental and escalated planning

**Incremental mode is the default.** Intent is captured as work happens: a read-back, one or
a few requirements with examples, and decisions as they arise. Each piece is stated in the
agent's reply, recorded as proposed, and the agent proceeds on it without waiting. The owner
confirms it in one line, in conversation or by command, whenever they choose (the in-flow
confirmation path, section 6.6); the merge boundary asks for whatever the change touched and
is still unconfirmed (section 7.5). No spec document is required.

**Escalated mode** is for large, risky or cross-cutting work. Before code is written, the agent
drafts the full set of intents, requirements, examples and decisions, plus a short Markdown
spec in `docs/specs/` that links them. The owner approves the set once (a set-hash approval);
presenting the set for that approval is a trigger-2 question (section 6.6), and code for the
escalated work waits for it.
Both modes use the same records, so escalated work simply produces more of them up front.

**Clarification depth (D16).** Whenever a request creates or changes intent, the agent loads
the `plumb-clarify` skill, which scales the clarification to the request: a trivial or clear
request (it maps to confirmed intent, or is a small unambiguous change) gets no questions and
a compact read-back; an incremental one gets the read-back with "you said" apart from "I
assume", proposed examples with edge cases, and only the questions whose answer changes what
gets built, one per message, multiple choice with a recommended option, each recorded as a
`DEC` with `matters: true`; an escalated one gets a short structured session (purpose and
success first, then two or three approaches with trade-offs and a recommendation, then the
set of records presented for the set-hash approval). The skill never asks what the
repository, the records or sensible defaults already answer, drops what the owner did not ask
for, restates in the owner's terms, and stops asking once the owner says "go" or "ok": the
remaining unknowns become labelled assumptions. Clarifying questions are trigger 2 of section
6.6, so they occur only when the owner starts or changes intent, never mid-implementation
unless a contradiction appears. The agent records the result with `plumb capture`, which
writes the whole read-back (INT, SR with examples, DEC) in one call, all proposed.

plumb suggests escalation, and the owner decides. The prompt hook and `plumb status` raise
the suggestion when any of these triggers fires:

- the request would add or change more than 3 requirements, or touch more than one feature;
- it contradicts or removes a confirmed requirement or example;
- it touches shared surfaces: the record format, the claims policy, shared test
  infrastructure, a public CLI or API, a data schema or a migration;
- it has effects that are hard to undo: deleting records, changing persisted data,
  security or credential handling, publishing;
- two or more decisions marked `matters: true` are still unconfirmed;
- during the work, the diff passes 400 changed lines or 10 files without a confirmed plan
  covering it.

The thresholds are configurable. A declined suggestion is logged and is not repeated for
the same intent.

### 5.3 Understanding what the owner said (intent by exception)

Three model-backed readers sit between the owner's words and the records, so the owner
confirms by exception instead of one record at a time (`docs/specs/sp8-intent-by-exception.md`).
None of them is a keyword rule; each runs as a **job**, and the part that decides what counts
is exact code.

- **The reader** maps one owner message onto the records the previous reply showed and the
  cards that are open: accepted, rejected, change or open, with the owner's exact words as
  evidence. An accepted answer at or above the learned threshold, at the version shown, with
  its words found in the message, is written as an `approval` with `by: owner-words`. The
  typed commands (`/plumb approve ...`, `/plumb undo ...`, `/plumb go`) stay an exact grammar; prose never turns an owner-only setting on.
- **The judge** asks, for every record a capture wrote, whether the owner would object given
  their words. Until the trial teaches a threshold it only offers the supported records in
  batches of at most five (one drawn from below the line); an answered batch is the labelled
  set that `calibrate` reads, from the logged scores and with no model call. With
  auto-approve on (typed by the owner) the judge confirms what passes. The ~150 records proposed before this are judged in one background pass and
  offered as one card per feature (or per intent when there is no feature).
- **The clarifier** runs on every owner message and says whether it carries intent and which
  gaps change what gets built. A request with such a gap closes the **gate**: edits are
  refused (Claude Code only, the edit tools only) until `plumb clarify --wait` has returned the
  card and the owner has answered it, or has released a failed check (`/plumb go`).

Jobs are files under `.plumb/session/<id>/` and carry no authority. The prompt hook and
`plumb capture` queue them (one read job per turn, one clarify job per message, one judge job
per capture); one worker per session, started by the hook, recomputes each job's inputs from the
logs, asks the one configured dispatcher, checks the answer against the job's schema and
applies it. A result file or a job file written by anything else confirms nothing and is
reported. Every failure (no model, an unreadable answer, a timeout) confirms nothing, shows as
"couldn't check", and is retried on the next turn; three in a row show on the status line.
The end-of-turn summary lists, in order, what the owner's words confirmed (also for a read that
finished after its turn), the settled line, and the cards. While a job runs the status line
says so in plain words ("reading your answer", "checking your request", "judging the
backlog · 10/160").

## 6. The grounding loop

The loop is four hooks plus a status line, with one more hook that guards approvals
(section 4.6). Each hook is a single `plumb hook <event>` process
that starts with minimal imports, reads only `.plumb/` and the files named in records, uses
caches keyed by file fingerprints (size and mtime first, hash when those change), never runs
tests, never scans `site-packages`, and never starts one subprocess per file. If a hook cannot
finish within its budget, it reports "plumb: check skipped (budget)" and the turn continues.
plumb never blocks the owner's work because of its own failure.

### 6.1 Session brief (session start)

The session-start hook outputs a few lines and a pointer (D13): the record counts, what awaits
the owner, decisions that matter, drift, open NCs, one line of test evidence, and where the
rest is (`plumb show <ID>`, `plumb explain <anything>`, `plumb brief --all`). It never lists
every proposed record; records reach the agent one line at a time as they become relevant
(section 6.2). `hooks.session_brief: full` restores the longer brief (about 30 lines, hard cap
40): the active features, confirmed intents in one line each, open decisions that matter,
stale links, unconfirmed edits, records still proposed, failing or missing evidence, and open
NCs.

It is context, not procedure.

### 6.2 Per-prompt context and intent-change detection

On each prompt, the prompt hook:

1. appends the prompt's digest to the committed prompt-digest log and keeps its text in
   gitignored session state, so an approval can quote it and the quote can be checked
   (section 4.6);
2. selects the relevant records, either named by ID or matched by term overlap with titles,
   statements and examples, and injects a deduplicated delta (D13): one line per record (ID,
   state, title), only for a record that is newly relevant in this session or whose hash or
   confirmation state changed since it was injected (session state keeps what the agent has
   seen; a `/clear` or compaction resets it), within `hooks.prompt_lines` and the
   `hooks.prompt_tokens` budget. A record cut by the budget is named with `plumb show` and
   comes on a later prompt. Nothing is injected when nothing new is relevant. Examples and
   covering tests are pulled on demand with `plumb show <ID>`;
3. checks for a possible intent change. The heuristic default flags a prompt that matches a
   confirmed record and contains change language (instead, no longer, remove, rename, also,
   change, should now, don't). When the judgment backend is enabled, it filters these
   candidates first (section 8). A flagged candidate is injected as an instruction to the
   agent: "this may change SR-004 (confirmed). If it does, read back the change and ask
   before editing; if not, proceed." The flag is about the request, not the record: every
   prompt that may change a confirmed record gets its own instruction, also later in the
   same session (D5, trigger 1); only the record lines of step 2 are deduplicated. The
   agent, which is already running, acts as the cascade's LLM tier at no extra cost. Only a
   confirmed contradiction or extension reaches the owner: the flag is an instruction to the
   agent, and the stop hook shows the owner an intent-change card only when the turn shows
   the agent concluded there is a change (it edited the flagged record, or wrote or edited a
   record that supersedes, corrects, relates to, derives from or decides it), or when a
   backend other than the heuristic rated the flag `accept`. A heuristic flag alone never
   reaches the owner, on any host. The heuristic never reads a shared leading "add a ..."
   (or "function", "returning") as a subject in common: a new, unrelated feature is not an
   extension of a confirmed one.

### 6.3 Edit tracking

After each `Edit`, `Write`, `MultiEdit` or `NotebookEdit`, a hook appends the path to session
state. That is all it does. At the end of the turn, `git status --porcelain` (one call) catches
edits made through the shell.

### 6.4 End-of-turn alignment summary

The stop hook maps the turn's changed files to records through links and the test map, and
then:

- recomputes the hashes of the records and link ends involved;
- lists the covering tests (section 7.2) and their evidence state;
- writes `session/status.json`;
- shows the owner a summary of at most five lines, plus one short line per read-back or
  example newly proposed this turn, marked `proposed`, for example:

```
plumb: touched SR-004, SR-007 | stale: SR-007 -> src/plumb/links.py (code end)
plumb: covering tests 6 selected: 4 fresh pass, 1 not yet passing, 1 not yet run
plumb: full verification pending (tests/conftest.py changed) | 3 deferred (budget)
plumb: confirmed SR-004 on your prompt "ok, go on" | fidelity unjudged: SR-007
plumb: questions: none
plumb: proposed INT-004: build the status line, not the MCP server; assumes ASCII only
plumb: proposed SR-009/EX-1: given a stale link, when status runs, then it shows stale 1
```

The proposed lines repeat what the agent's reply stated, so the owner can confirm them in one
line ("ok", or "ok SR-009") now or later, or leave them for now; they become a question only
under trigger 2 (section 6.6).

If the turn changed code whose covering tests have no fresh evidence, the hook asks the
*agent* (not the owner) once per turn to run `plumb verify`, which runs the per-turn
selection of section 7.2 (covering tests, or a bounded sample when coverage is unknown,
within the per-turn time budget) and records evidence. Test execution belongs to the agent's
turn and never to the hook's latency budget, and the request never names the full suite.
When the turn changed shared test infrastructure, the hook does not ask for a full run: it
reports `full verification pending` in the summary and the status line (section 7.2), and
the next merge boundary satisfies it (section 7.5).

**Fidelity (advisory, no JEV needed).** The stop hook does not ask for fidelity judgments. It
only notes, as `fidelity unjudged`, each requirement whose `implemented_by` or `verified_by`
ends changed and which has no judgment for the current hashes. `plumb fidelity SR-004` builds
a scoped packet for the host agent to judge: the requirement's statement, its examples, the
linked code and tests at their current content, and their test evidence. The packet carries
no procedure. It runs on demand (the owner or the agent asks for it), and the merge boundary
lists every touched requirement still unjudged (section 7.5). The agent answers with
`plumb judge SR-004 --verdict fits|drifts|unsure --note "<one line>"`, which appends a
`judgment` log entry holding the verdict, `backend: host-agent`, the requirement's hash and
the hashes of the judged ends. Judgments are always advisory: `drifts` and `unsure` appear in
the summary and the status line as drift signals, never confirm or freshen anything, and
reach the owner only when they also meet an interruption trigger (section 6.6). When JEV is
enabled, it scores the same packets faster and more cheaply (section 8); it is never needed
for fidelity.

### 6.5 Status line

`plumb status --line` reads `session/status.json` and recomputes nothing. It prints one
plain-ASCII line, for example
`plumb | SR 12/14 ok | proposed 2 | stale 1 | tests ok | full pending | ask 0`. The
`full pending` field appears only while `full verification pending` holds (section 7.2).

With D13 the line becomes the owner's one-line status card: a state, a plain-language
summary of the intent being worked on, and the counts, for example
`plumb ✓ aligned · "add multiply next to add" · SR 12/14 ok (2 by JEV) · 1 awaits you`.
It distinguishes "confirmed by you" from "confirmed by JEV" (D14) and says
`auto-approve suspended` when a model change suspended it. The full intent card appears in
the end-of-turn summary only when it matters (a new or changed intent awaiting the owner, one
of the three triggers, a regression, or the owner's own request); the card's verbosity is
configurable, `full`, `compact` or `off` (`docs/specs/sp5-presentation.md`).

### 6.6 Interruption triggers (exhaustive)

plumb asks the owner a question in exactly three cases:

1. **Real intent change.** A request contradicts or extends a confirmed intent, requirement
   or example.
2. **An unconfirmed decision that matters.** Something work relies on that the owner has not
   confirmed, in one of these cases only:
   - a `DEC` with `matters: true` that is not confirmed and is linked to a record or file
     touched this turn, asked once per hash, phrased "I assumed A; B also fits. Which one?";
   - at a merge boundary, the requirements touched by the change that are still proposed,
     including read-backs and examples never confirmed and confirmed records edited since
     their approval (section 7.5);
   - an escalated spec, presented for its set-hash approval (section 5.2), which the owner
     invited by accepting the escalation;
   - a contradiction involving a proposed record: a request, or another record, that
     conflicts with a proposed read-back or example the work relies on.

   One question lists all the records concerned with their read-back and examples, and the
   owner answers in one line.
3. **Regression.** A test that previously passed, with recorded evidence, now fails. A new
   test that starts red (the test-first step) is never a regression and never interrupts: it
   is shown as "not yet passing" in the summary and the status line.

The agent asks in its reply, with a read-back. Nothing else interrupts, and proposed records
never block work outside trigger 2. Stale links, proposed records, unconfirmed edits,
not-yet-passing tests, unjudged or drifting fidelity, `full verification pending`, escalation
suggestions and skipped checks are logged and shown in the summary, the status line, and
`plumb status` / `plumb log`.

An edit to a confirmed record that no owner request asked for is not trigger 1: the record
loses its confirmation (its approval no longer pins its hash), it is shown as an "unconfirmed
edit" drift signal, and the merge boundary asks for it under trigger 2 unless the owner
confirms it earlier.

**In-flow confirmation path.** Read-backs and examples are confirmed without a question, but
only by the owner's own explicit words:

1. The agent states the read-back and the proposed examples in its reply as a non-blocking
   statement ("Building X, not Y; assuming Z. Examples: EX-1 ..., EX-2 .... Say so if
   wrong.") and proceeds. The records are written as proposed and appear in the end-of-turn
   summary with status `proposed`. The stop hook records the **stated set** in session
   state: every proposed record created or edited during the turn, plus every record listed
   in a trigger-2 question in that reply. This is deterministic; no model decides it. Each
   record is marked shown only when the summary displayed all of it (an INT's will, won't
   and labelled assumptions; every given/when/then of an SR); a record the summary had to
   cut is named with `plumb show <ID>` and is confirmed only when the owner's words name it.
2. On the owner's next prompt, the prompt hook lists the records of the stated set that are
   still proposed. The agent reads the prompt:
   - an explicit affirmation ("ok", "yes", "approve") is recorded as an `agent-relayed`
     approval with the owner's affirming words and the prompt digest, through
     `plumb approve --prompt <digest> --quote "..."`. Before writing, plumb checks that the
     quote is verbatim in the logged prompt, that it contains an affirmation term, and that
     every approved record is in the stated set or named by ID in the quote (section 4.6);
   - a prompt that neither affirms nor objects (for example one that moves on to other work)
     confirms nothing: the records stay proposed, and nothing is recorded;
   - an objection is not an approval: the agent revises the records, states them again, and
     asks only if the objection also meets one of the three triggers above.
3. Each approval made this way appears as one line in the end-of-turn summary (for example
   `plumb: confirmed SR-004 on your prompt "ok, go on"`), so the owner sees it and can revoke
   it, by saying so or with `plumb revoke SR-004` (a new log entry), without being
   interrupted.
4. Records the owner never affirmed stay proposed: neither silence nor a prompt that does not
   object is confirmation. They keep being counted as proposed in the status line and the
   session brief, and the owner can confirm them whenever they choose, in one line: a prompt
   naming them by ID ("ok SR-009, SR-010"), `plumb approve SR-009`, or
   `plumb approve --proposed`. A proposed record does not unlock the covered or verified
   states and does not feed trigger 1. Work goes on; the merge boundary is where every
   requirement the change touched must be confirmed.

## 7. Verification

### 7.1 Code-to-test map

`plumb map` builds the map from three sources:

- `verified_by` links;
- `@pytest.mark.sr("SR-###")` markers, found with an `ast` scan;
- the import closure of each test module, found by resolving `import` statements with `ast`
  over the configured source directories (default `src` and `tests`).

The map is cached in `.plumb/cache/` and keyed by file fingerprints, so only changed files are
re-parsed. It is printed as grep-able text: `path -> tests`, `SR -> tests`.

### 7.2 Covering-test selection

The covering tests for a set of changed files are the union of:

- tests whose import closure reaches a changed file;
- tests linked by `verified_by` to requirements whose `implemented_by` ends changed;
- tests that mention a changed path literally.

Documentation-only changes select nothing.

**Per-turn selection never includes the full suite.** Per-turn checks always run covering
tests within a time budget, and three rules keep them to seconds:

- **Shared test infrastructure sets `full verification pending`; it never triggers a full
  run in a turn.** The default infrastructure globs are `**/conftest.py`, plumb's pytest
  plugin, `pyproject.toml`, `pytest.ini`, `tox.ini`, `setup.cfg` and `uv.lock`, and they are
  configurable. A change to one of them adds nothing extra to the per-turn selection. Instead
  plumb sets **full verification pending**, which the next merge boundary satisfies with a
  full-suite run (section 7.5). The state is derived, not stored: it holds while the current
  hashes of the infrastructure files differ from the hashes recorded with the latest
  full-suite evidence, or when no full-suite evidence exists, or while the unknown-coverage
  rule below holds. It is shown in the end-of-turn summary (in the turn it first appears) and
  in the status line (while it holds). Until it is satisfied, the per-turn evidence for the
  affected tests is reported as resting on changed infrastructure, never as verified for the
  merge.
- **Unknown coverage gives a bounded sample plus the pending flag.** When a changed source
  file has no covering test in the map (for example a new module, or code reached only
  dynamically), `plumb verify` adds a bounded sample: the tests nearest to the file by path
  (same package, then its parent), in a deterministic order, at most `verify.sample_size`
  (10 by default) and inside the time budget. It also sets `full verification pending`,
  which holds while any such file differs from its hash recorded with the latest full-suite
  evidence. A hook never builds a test map inline that it cannot build within its budget
  (a fresh checkout, where `.plumb/cache/` is empty): the build starts outside the hook (a
  detached `plumb map`), and until it lands the turn gets the same bounded sample with
  `full verification pending` ("coverage unknown"), on every host. The regression check
  (trigger 3) reads the regressions this turn's runs recorded from the evidence index
  before any step a budget can cut, so it never waits for the map; when the budget cuts the
  selection itself, the agent is still asked to run the turn's covering tests.
- **A per-turn time budget caps the selection.** `plumb verify` in a turn runs the selected
  tests in priority order (tests linked by `verified_by` to the changed requirements, then
  tests that mention a changed path literally, then import-closure tests, nearest importers
  first) until their expected duration reaches the budget: `verify.turn_budget_s`, 30 s by
  default, configurable. Expected durations come from earlier evidence; a test with no
  recorded duration counts as 1 s. pytest runs with a hard wall-clock limit of twice the
  budget. Selected tests left out are reported as "deferred (budget)": they are not run, keep
  their previous evidence state, and are run at the merge boundary.

`plumb verify --full` runs the whole suite. It belongs to the merge boundary or to an
explicit request by the owner; no hook ever asks for it.

### 7.3 Identity-pinned evidence

`plumb verify` runs the selected tests with plain `pytest` (never more than `-n 2`) and
plumb's small pytest plugin. The plugin reports collection, per-phase outcomes and the exit
status; a fixture failure outranks a pass. Evidence is keyed per test node:

- `node_id`;
- `closure_digest`: the hashes of the files in the test's import closure;
- `env_key`: a cheap environment key, `sha256` of the LF-normalized `uv.lock`, the Python
  version, the platform and the `pyvenv.cfg` home.

The full content identity of the environment (installed distributions and the interpreter's
bytes), which took 1.1 s on pi-agent-factory, is computed only when evidence is recorded and
is cached under the cheap key. A passing result is reused only when its key matches exactly.
An unknown identity means no reuse. Each record carries a self-checksum. If the inputs change
while the tests run, the record is discarded. When reuse misses, plumb says which part of the
key differed.

### 7.4 Failure policy

This is the owner's rule, carried over from pi-agent-factory. It governs reruns after a
failure; it never moves a full run into a turn:

- **Flaky rerun on the same tree.** When a test fails and then passes on a rerun with an
  identical tree and environment, it counts as a pass and is recorded as flaky with both
  attempts. Within a turn this reruns only the failed tests.
- **Owner-waiver targeted rerun.** At the merge boundary, an owner waiver lets a targeted
  rerun stand in for a full rerun. The waiver is an immutable log entry pinned to the diff
  digest it covers (`plumb tests waive --merge <base>`, the owner's terminal only); any later
  edit voids it.
- **Full rerun only when shared test infrastructure changes, and only at the merge
  boundary.** A change to shared test infrastructure sets `full verification pending`
  (section 7.2). Within a turn it is reported, never run. At the merge boundary the full run
  is required unless an owner waiver covers it. After any other change, a rerun covers only
  the covering tests (plus the bounded sample when coverage is unknown).

### 7.5 Merge boundary

A merge boundary is where work relies on its records, so it is where the guarantees are
paid for. `plumb check --merge <base>` (sub-project 1a) gives the owner one short report over
the change from `<base>`:

- **Parallel work (SP6).** Three more sections hold the merge: ID collisions between clones
  (exit 1, fixed by `plumb merge-fix`), record paths git left unmerged (exit 1), and open
  intent conflicts that the record merge driver wrote when two branches changed the same
  words, each shown as one card with both versions (exit 4, the owner's choice). The quick
  form runs as git's pre-merge-commit hook without a test run; the one full run is at push.

- **Touched requirements must be confirmed.** A requirement is touched when its record, or
  one of its `implemented_by` or `verified_by` ends, changed in the range, or a commit in the
  range claims it in an `SR:` trailer. Every touched requirement, and the intents and
  decisions it derives from, must be confirmed at its current hash. Those still proposed
  (never confirmed, or edited since their approval) are put to the owner as one trigger-2
  question listing their read-back and examples (section 6.6); the owner answers in one line.
  The merge waits for that answer. A requirement that gained an `implemented_by` or
  `verified_by` end in the range (links are outside the record hash) is an extension of it
  and is put to the owner the same way, with its new ends, until an approval lists them; a
  `trace.exempt` glob added in the range is listed too and is not honoured until the owner
  confirms it. Changed source paths that no requirement owns (untraced
  changes: work that skipped the read-back) are listed in the same question; they need a
  requirement, recorded by the agent and confirmed by the owner, or the owner's explicit
  exemption.
- **Agent-relayed and auto-JEV approvals, for a glance.** Every `agent-relayed` approval
  made in the range is listed with its record and the owner's quote, and every `auto-jev`
  approval (D14 B) with its score, confidence and model version. This is not a question; the
  owner can revoke any of them. `plumb merge-check` (sub-project 3) is the command.
- **Fidelity, advisory.** Touched requirements with no judgment for their current hashes, or
  with a `drifts` or `unsure` verdict, are listed with the `plumb fidelity` command for each.
- **Verification state.** The merge is never green unless every acceptance test the change
  can affect has passing evidence on the current code. The acceptance tests checked are those
  of the touched requirements and of every confirmed requirement whose acceptance tests cover
  a changed path, so a change to one requirement's code that breaks another's is held too.
  A failing one (kept until a run passes the test body that passed before it, so a test
  rewritten to pass still fails), one with no passing evidence on the current code, or an
  unresolved regression holds the merge until a run passes it. `full verification pending`
  holds the merge until a full run satisfies it or an owner waiver pins this exact change
  (section 7.4); a full run that collected nothing, hit a collection error or failed a test
  that has not passed since never counts as full verification.
- **Confirmed acceptance tests.** An approval of a requirement pins the content of each
  `verified_by` end. A confirmed requirement whose acceptance test changed since is an
  unconfirmed edit, "acceptance test changed": it waits for the owner like any other
  unconfirmed requirement, shown with the example it verifies and the test's diff. A
  regression hidden by changing the test is a regression question in the stop hook (trigger
  3), never "questions: none".

Sub-project 3 completes the boundary: plumb runs the full suite (which satisfies
`full verification pending` by recording the current hashes of the shared test
infrastructure and runs every deferred test), `plumb check` (no dangling links, no duplicate
IDs, no unconfirmed edits of confirmed records, hash chain intact), the claims check, and the
log-integrity check against git, then promotes the resulting evidence into the committed log.
This is the only place where heavy guarantees are paid for.

## 8. Optional judgment backend (JEV) and the heuristic default

Some loop decisions are classifications: does this prompt change that requirement, is this
diff cosmetic or material, does this code still fit its requirement. plumb answers them with a
deterministic **heuristic by default**, which needs no key, makes no network call and is
fully reproducible.

JEV (TypeSafe's typed-judgment model, which answers with `Choice`, `Score` or `Noul` in about
70 to 500 ms) can be enabled as an **optional** backend through `.plumb/config.yaml`, reached
at TypeSafe (`provider: typesafe`, the default: `POST https://api.typesafe.ai/v1/systemone`)
or through OpenRouter (`provider: openrouter`: `POST
https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13`), the same Decisions
wire format; a preset supplies the endpoint, path, model, validated version and variable
name, and explicit `judgment.jev` values win. The key is read from the environment variable
named by `judgment.jev.credential_env` (default `TYPESAFE_API_KEY`, or `OPENROUTER_API_KEY`
with the OpenRouter preset): first the process environment, then the env file that the
user-level `~/.config/plumb/jev.json` names (read in place, never copied; refused inside the
repository), then the older user store `~/.config/plumb/jev`. The owner sets it up by saying
`/plumb jev setup openrouter` (the agent runs `plumb jev setup`, which records only the
provider, model and variable NAME, never the secret) and checks it with `/plumb jev status`.
The key never reaches a repository file, log entry, judgment record, notice or output. It is
used for:

- intent-change detection on candidate prompts;
- drift triage (cosmetic or material) on stale links;
- a cheap advisory fidelity score on the `plumb fidelity` packets of section 6.4, scoped to
  the requirements changed in the turn. Within the stop hook's budget, JEV scores a few of
  them in the background and answers the clear cases; low-confidence ones stay `fidelity
  unjudged` for the host agent, on demand or at the merge boundary. JEV only makes scoring
  faster and cheaper: without it, the host agent judges the same packets, and fidelity
  judging still happens.

The cascade is the one already validated in pi-agent-factory:

- confidence of 0.9 or more: accept;
- from 0.5 to 0.9: escalate to an LLM, which by default is the host agent through injected
  context;
- below 0.5: escalate to a human, but only when the item also meets an interruption trigger
  (section 6.6); otherwise it is logged.

When the resolved model version differs from the version the thresholds were validated
against, automatic acceptance is suspended. Versions are compared through one normalizer (no
vendor prefix, no leading `~`, no trailing `-YYYYMMDD` snapshot date, no zero patch), so
`jev-1.13.0` and OpenRouter's `typesafe/jev-1.13-20260917` are one version; `jev-1.14` is a
change. The same comparison serves tier routing, the logged `version_drift`, `plumb jev
status` and the calibration checks of auto-approval. In the hook path, the call has a hard timeout of
about 800 ms; a timeout, missing key or error falls back to the heuristic with one logged
notice. State sent to the service is assembled only from tracked files, with secret-bearing
paths excluded and deterministic truncation. Every judgment is an append-only log entry with
its request fingerprint. Judgments are advisory: they order, filter and annotate, and they
never mark something fresh. They never confirm a record, with one exception the owner chose
(D14 B, ruling R8): the narrow auto-approval of section 4.6, off by default, which only the
owner turns on, only with JEV (never the heuristic), and only while a passing calibration
(below) exists for the resolved model version.

**JEV-assisted confirmation (D14, ruling R8).**

- `plumb triage` scores each proposed record for faithfulness to the owner's words (JEV when
  configured, otherwise the heuristic) and groups the low-risk ones; the end-of-turn summary
  and `plumb brief` offer one line that names up to about 5 of them by title, then "+N more
  (see plumb triage)" (D18, R13 Q2), and that the owner confirms with explicit words; the
  "ok" approves exactly the pinned hashes, which `plumb triage` shows in full; riskier
  records are shown individually. `plumb triage --approve low-risk` confirms the group from the owner's
  terminal, recorded as an owner approval of exactly the listed hashes.
- `plumb config auto-approve on|off [--backend jev] [--min-probability 0.9]
  [--min-confidence high]` and `plumb config show` run in the owner's terminal only and are
  logged in the event log; `on` refuses when JEV is not configured or not calibrated.
- `plumb jev status` (configured? provider, endpoint, key source label, reachable?
  normalized resolved version) and `plumb jev setup`, which records only the provider, model
  and the NAME of the environment variable that holds the credential (with `--env-file`, the
  user-level `jev.json` that names where it is read) and never stores the secret. The owner
  reaches them, and calibration, through `/plumb jev status`, `/plumb jev setup openrouter`
  and `/plumb jev calibrate`. Setting a provider replaces the earlier provider's endpoint,
  path and validated version.

**Ported from pi-agent-factory's FEAT-022 (D17, ruling R12).** All four work with the
heuristic in a degraded form, or report "no judgments available"; with JEV they are cheaper
and sharper; all judgments are logged and advisory.

1. **Calibration.** `plumb jev calibrate` measures the backend's accuracy on the owner's own
   confirmed and revoked records (a labelled set built from the log) and records thresholds
   per claim kind with the resolved model version. The evidence is mixed (D18, R13 Q1): per
   record kind, at least 20 of the owner's past decisions and at least 5 "no" examples, of
   which up to half may be generated variations (a will flipped to a won't, a flipped
   result, a changed number); JEV must wrongly accept none of them. The split between real
   and generated examples is shown in `plumb jev status` and in the calibration log entry.
   The owner reaches it as `/plumb jev calibrate`; the agent runs it.
   `plumb config auto-approve on` refuses
   without a passing calibration for the current model version, and a version change
   suspends auto-approval until it is recalibrated.
2. **Edge alignment.** `plumb align [scope]` collects the scope deterministically (intent ->
   feature -> requirement -> example -> test -> code -> evidence) with a fingerprint, reports
   empty families as named gaps, and judges each edge with one question phrased for its edge
   class, weakest edge first. Whether an edge exists stays deterministic; judgments never
   create or remove edges. It is shown in `/plumb review` and in the Obsidian view.
3. **Ownership proposals.** For an untraced change, the backend proposes the owning
   requirement (a choice over candidates narrowed by the code map), and "does this diff serve
   its claimed SRs?" becomes a non-blocking commit-hook warning. A bare test-file reference
   gets a proposed test node. These feed the agent's read-back: every untraced-change
   instruction (the stop hook's, the next prompt's, `plumb turn end`'s) names the proposed
   owner of each shown path, bounded in paths and time, and `plumb review` lists them for
   uncommitted changes too. They never write links.
4. **Hidden-dependency scan.** When a confirmed record or an authoritative document changes,
   a bounded scan proposes records or documents that silently depend on it, shown as drift
   hints only, never as staleness marks or edges.

## 9. Host adapters

The core is a CLI with JSON output and a Python library. Hosts are thin adapters. **Claude
Code comes first**: `plumb install claude-code` writes four things.

- **Hooks** in `.claude/settings.json`: `SessionStart` (brief), `UserPromptSubmit` (prompt
  digest, context and intent check), `PostToolUse` on edit tools (tracking), `Stop` (summary
  with the `proposed` lines, verification nudge and the `fidelity unjudged` note), and
  `PreToolUse` on the shell and edit tools (the
  approval guard of section 4.6). The same file sets the `PLUMB_AGENT_SESSION` session
  marker in its `env`.
- **The status line command**.
- **A short `plumb` skill** (since DEC-036 the `plumb-records` skill) of about 20 lines. It explains how to state a read-back and
  examples as non-blocking statements, how to record them and decisions, how to relay an
  owner's explicit confirmation with the owner's affirming words (and that a prompt that does
  not object is not a confirmation, section 6.6), when to ask (only the three triggers), and
  when to run `plumb verify` and `plumb fidelity`.
- **A short CLAUDE.md block** naming `.plumb/` and `plumb map`.

It also installs the `commit-msg` hook for `SR:` trailers, and the `plumb-clarify` skill
(D16) beside the `plumb` skill. The owner-facing `/plumb` command takes plain-language
arguments (`/plumb explain`, `/plumb status`, `/plumb review`, `/plumb confirm`); the agent
resolves them to records, files and tests and answers in the owner's terms, while the raw CLI
stays the agent's interface (D13).

Later adapters (Codex, Pi, Hermes) are thin layers over one host-neutral turn API, mirroring
these hooks where the host supports them, with a CLI-only fallback (an instruction file plus
`plumb turn start` and `plumb turn end`) where it does not. `plumb turn start` logs the
owner's message and starts the turn before it prints the session brief of a session's first
turn, so a brief cut by the watchdog never drops the message. On such a host the owner's chat
"ok" may confirm, and each confirmation resting on a message the agent recorded itself is
labelled "self-recorded message" (D18, R13 Q4; section 4.6); a read-only MCP server on stdio
exposes the brief, the relevant records, why and impact, and drift
(`docs/specs/sp4-hosts-mcp.md`).

## 10. Relationship to pi-agent-factory

- **Extraction, not fork.** plumb copies selected pi-agent-factory modules together with their
  tests, then simplifies them:
  - the register parser and acceptance model, `SR:` trailer claims and the review of claimed
    against declared paths, test markers;
  - the trace model and gaps, trimmed to SR, FEAT and NC, and relation resolution;
  - freshness fingerprints and comparison;
  - the AST import-closure code;
  - the pytest evidence plugin and the snapshot model;
  - the failure policy and owner waivers;
  - the content-based environment identity;
  - the judgment package.

  It does not copy the per-turn admission, coordination, planning run state, gates,
  policy compiler, manifests or `factory.*` shims. No `factory.*` or `coherence.*` import
  exists in plumb.
- **Importer.** `plumb import pi-agent-factory <path>` reads that repository and never writes
  to it. It maps the following:
  - `requirements/SR-*.md`: acceptance criteria are kept as `AC-n`, structured
    `implemented_by` and `verified_by` entries become pinned links, and legacy `checksum:`
    values are verified and reported;
  - `docs/features/FEAT-*.md` plus `bundles/*.json`: the union of the two becomes the feature
    membership, and each difference between them is reported as a finding, never resolved
    silently;
  - `docs/nonconformances/NC-*.md`: read leniently, with original `corrected_by` strings kept;
  - `.factory/trace-claims.yaml` becomes `.plumb/claims.yaml`;
  - the `commits[]` of `evidence/runs/ingest-*.json` become the claims checkpoint.

  An imported record is confirmed only when the owner confirmed it upstream: a record that
  carries an upstream owner approval or consent pinning its current content receives an
  approval marked `by: import` that cites that upstream entry. Every other imported record
  arrives as proposed. Importing never manufactures a confirmation the owner did not give.
- **Maintenance mode.** Once the current integration batch lands, pi-agent-factory takes
  fixes only, and new feature work moves to plumb. The fork plan, `docs/fork-plan.md`,
  sequences the maintenance mode, the extraction, the import and the switch.

## 11. Roadmap

1. **Core, grounding loop and verification, dogfooded.** The owner wants the implementation
   usable within 9 hours of 2026-10-05 (decision D11). Sub-project 1 is therefore built in two
   parts, in this order.

   **1a. Time-boxed slice: must be dogfoodable within the 9 hours.** Built in the order listed,
   so that plumb is used on plumb as early as possible:
   1. the record model (INT, SR, DEC, FEAT, NC; IDs; frontmatter), content hashing and
      normalization with whole-file link ends, links, pins, staleness, `plumb repin`, and
      `plumb check` (dangling links, duplicate IDs, stale pins, unconfirmed edits);
   2. the hash-chained append-only log, pinned approvals (`plumb approve`, `plumb revoke`;
      `by: owner` and `by: agent-relayed`), the prompt-digest log, and the CLI side of the
      approval guard (session marker and write-time quote check, section 4.6);
   3. plumb's own requirements written as `SR` records in `.plumb/`, the `SR:` trailer and
      the commit-msg hook that checks it. From this step on, plumb's commits carry `SR:`
      trailers;
   4. `plumb check --merge <base>` with its first two parts (section 7.5): every touched
      requirement must be confirmed, and the `agent-relayed` approvals of the range are
      listed. Its fidelity and verification lines join it as those parts land;
   5. the session-start, prompt, edit-tracking and stop hooks (the summary shows read-backs
      and examples as `proposed`), the guard hook, the status line, the in-flow confirmation
      path (the owner's explicit words only), and `plumb install claude-code`. Each hook is
      installed in plumb's own repository as soon as it lands;
   6. `plumb map` (`verified_by` links, `sr` markers and the AST import closure), covering-test
      selection with the per-turn time budget, the unknown-coverage sample and the derived
      `full verification pending` state (an infrastructure change never triggers a full run
      in a turn, section 7.2), and `plumb verify` with evidence keyed by `node_id`,
      `closure_digest` and the cheap `env_key` only.

   **1b. Rest of sub-project 1**, built after 1a:
   - `plumb fidelity` packets and `plumb judge` (section 6.4);
   - the judgment interface with the heuristic, disabled and fake backends;
   - AST symbol-level hashing of link ends (1a hashes whole files);
   - the full environment identity of section 7.3;
   - the failure policy: flaky rerun of failed tests within a turn, and owner waivers for the
     merge-boundary full rerun;
   - `plumb claims check` (claimed against declared paths) and `.plumb/claims.yaml`.

   If time runs out, every item of 1a or 1b that is not finished is recorded in
   `docs/followups.md` with its state, and is built next in the order above. Items are dropped
   from the end of the list first, so the slice that exists in the morning is always the
   dogfoodable core: records, hashes, approvals, check (including the merge-boundary
   confirmation rule), trailers, hooks and status line.

   Exit criteria: plumb's own requirements are `SR` records in `.plumb/`, its commits carry
   `SR:` trailers, plumb's hooks are installed in its own repository, the hooks stay under
   budget, and `plumb check --merge` refuses a merge whose touched requirements are not all
   confirmed.
Sub-projects 2 to 5 and the importer completion are built as one batch of five parallel
lanes after a short contracts phase (`docs/plans/next-plan.md`); each has its spec.

2. **Intent capture and escalation** (`docs/specs/sp2-intent-capture.md`, lane CAPTURE).
   This adds:
   - `plumb capture`, which records a whole read-back in one call, and the helpers
     `plumb new`, `plumb intent`, `plumb example` and `plumb decide` (decisions with
     alternatives, "I assumed A; B also fits");
   - the escalation triggers and the up-front spec mode, a set of records approved by
     set-hash;
   - intent-change and contradiction scoring through the judgment backend, the heuristic by
     default and the live JEV client only behind the protocol, its credential read from the
     environment;
   - the R8 commands (D14): `plumb triage`, `plumb config auto-approve on|off`,
     `plumb config show`, `plumb jev status`, `plumb jev setup`; the narrow auto-approval,
     gated by calibration (`plumb jev calibrate`, D17 item 1);
   - the `plumb-clarify` skill and `plumb clarify` (D16), with the `plumb` skill (now
     `plumb-records`, DEC-036) updated to drive the capture helpers;
   - ownership proposals and the hidden-dependency scan as drift hints (D17 items 3 and 4).
3. **Merge boundary** (`docs/specs/sp3-merge-boundary.md`, lane MERGE). `plumb merge-check`
   completes section 7.5: every touched requirement confirmed; agent-relayed and auto-JEV
   approvals listed for a glance; `full verification pending` cleared by exactly one
   full-suite run with evidence pinned to identity; claims, stale and dangling links and
   failing confirmed-example tests hold the merge; fidelity packets listed (advisory); an
   optional git pre-push hook. No transaction machinery.
4. **More adapters and MCP** (`docs/specs/sp4-hosts-mcp.md`, lane HOSTS). Thin adapters for
   Codex, Pi and Hermes over one host-neutral turn API, with a CLI-only fallback, and a
   read-only MCP server on stdio.
5. **Presentation** (`docs/specs/sp5-presentation.md`, lane PRESENT). D13 beyond what
   sub-project 1 already ships (the per-session prompt delta, the compact session brief and
   `plumb explain`): one deduplicated delta for every hook output; the one-line status card
   and the full intent card only when it matters, configurable `full`, `compact` or `off`;
   plain-language owner slash commands executed through the agent (`/plumb explain`,
   `/plumb status`, `/plumb review`, `/plumb confirm`); the R8 commands as the owner sees
   them ("confirmed by you" or "by JEV"); `plumb align` (D17 item 2); and `plumb view`, a
   generated Obsidian vault of the records with a Canvas intent map, which never approves
   anything.
   **Importer completion** (lane IMPORT, specified in `docs/plans/next-plan.md` section 9):
   the full pi-agent-factory register import (SR relations to code and tests, bundles to
   features, NCs, `by: import` approvals only where an upstream human consent pins the
   current content), idempotent, with a dry-run diff. Moving pi-agent-factory onto plumb and
   retiring the duplicated modules there follow the fork plan (`docs/fork-plan.md`, F3 and F4).
6. **Parallel work** (D15, ruling R10), built after the batch above: collision-free IDs
   reserved through the shared ref `refs/plumb/ids` with git's compare-and-swap
   (`plumb merge-fix` renumbers collisions from other clones); one file per log entry under
   `.plumb/log/<kind>/` as section 4.7 says, with a migration of the current JSONL streams
   that keeps the hash chain; a frontmatter-aware git merge driver whose content conflicts
   become intent conflicts shown as one card with both versions; cross-worktree awareness in
   the brief and the status line, read-only, with no leases and no admission; and
   `plumb check --merge` on the merge result as a pre-merge or pre-push hook. The batch
   above avoids designs that conflict with it: IDs come from one allocation function, every
   log write goes through one append function, and no shared mutable runtime state is added.

## 12. Non-goals

- No run state machine, no phases, no planning runs, no handoff hashes, no consent phrases, no
  review swarms, and no governed execution by default.
- No orchestration of agents. plumb informs and checks; the host agent does the work.
- No full test suite and no environment scan per turn. A shared-infrastructure change sets
  `full verification pending`, which the next merge boundary satisfies; it never triggers a
  full run inside a turn, and the tests run in a turn stay within the per-turn time budget
  (section 7.2).
- No hidden state: no database, no required service, and no network call on the default path.
- No model that decides freshness, and no model that confirms intent except where the owner
  chose it. Hashes decide staleness, and only the owner confirms: by a command in the
  owner's own terminal, or by the owner's own affirming words in a prompt, which the agent
  records as a guarded `agent-relayed` approval that plumb checks deterministically (verbatim
  quote of a logged prompt, an affirmation term, targets limited to the records just stated,
  the triage group just offered, or records named by ID; sections 4.6 and 6.6). There is no
  "no-objection" approval: neither silence nor a prompt that merely does not object confirms
  anything, so the agent's reading of an unrelated or neutral prompt can never turn a record
  into confirmed intent. The single exception is the owner's own decision D14 B: the narrow
  JEV auto-approval, off by default, turned on only by the owner, gated by calibration,
  limited to records derived directly from the owner's words, labelled "confirmed by JEV"
  everywhere and listed at the merge boundary (sections 4.6 and 8).
- No forking of pi-agent-factory, and no runtime dependency on it.
- No dependencies beyond the standard library and PyYAML at runtime.
- No questions to the owner outside the three interruption triggers. Confirming a read-back
  or an example is never a question during work; it becomes one only under trigger 2, at a
  merge boundary, for an escalated spec or on a contradiction (section 6.6).
