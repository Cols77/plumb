# plumb concept spec

Status: reference document. Written 2026-10-05 from the owner intent brief of the same day.
The owner does not review this document; independent verifier agents check it, and every
plumb artifact, against the owner's words quoted below. When this document and the owner's
quoted words disagree, the quotes win and this document is corrected.

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

The owner's decisions that shape plumb:

| # | Decision | Owner's words |
|---|---|---|
| D1 | Standalone tool for any repository, designed so pi-agent-factory can migrate onto it. | "A / B" |
| D2 | Incremental intent capture by default; large, risky or cross-cutting work escalates to an up-front spec the owner approves; same artifacts in both modes; plumb suggests when to escalate. | "C" |
| D3 | Host-neutral core (CLI and library) with thin adapters, Claude Code first. Reuse pi-agent-factory code by extraction, without its per-turn admission and coordination weight. | "B. I guess the CLI / lib can be re-used from pi-agent-factory?" |
| D4 | A new, simpler record model with an importer, keeping familiar IDs and the KEEP list (section 4). | "B. can be the way to go but be careful about loosing some important features, for example the hash is important for staleness detection." / "Keep list looks fine" |
| D5 | Mostly in the background: status line, short end-of-turn summary, questions only on a real intent change, an unconfirmed decision that matters, or a regression. | "A" |
| D6 | First scope is core, grounding loop and covering-test verification, dogfooded on plumb itself. | "Would be nice to dogfood the version to itself as soon as possible and build with it." |
| D7 | Reuse existing artifacts: SR, FEAT and NC formats and IDs stay compatible. | "think of re-using the existing artifacts no? SRs FEATs..? It's up to you." |
| D8 | JEV is an optional judgment backend with an LLM cascade; plumb works without it. | "I think it might be usefull to integrate it in this new version too?" |
| D9 | pi-agent-factory goes into maintenance mode after the current integration batch lands; a fork plan is required. | "consider stopping developments on pi-agent-factory if it takes too much RAM" |
| D10 | The name is plumb, because "coherence is a bit confusing because it's a usefull word to use." | |

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
   work merges.
4. **Inspectable artifacts.** All committed state is Markdown with YAML frontmatter, or JSON, in
   git. Caches and session state are plain JSON too, are gitignored, and can be deleted at any
   time without losing information. Nothing hides in a database or a service.
5. **Trust from evidence.** Claims of alignment rest on content hashes, approvals pinned to
   exact content, test evidence pinned to code and environment identity, and append-only logs.
   When identity is unknown, plumb assumes nothing: evidence is not reused and the state is
   reported as unknown.
6. **Few, meaningful interruptions.** Three triggers can interrupt the owner (section 6.6).
   Everything else is logged and readable on demand.

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
  log/<kind>/<UTC-stamp>-<uuid8>.json   # append-only, committed
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
- **confirmed:** an approval pins the current hash;
- **covered:** confirmed, and every example has at least one `verified_by` link to an
  existing test;
- **verified:** covered, and every covering test has passing evidence for its current
  identity;
- **stale:** an approval or link pin no longer matches.

Work never waits for a record to leave the proposed state. The agent builds on proposed
records; the end-of-turn summary and the status line show how many records are still awaiting
confirmation, and the passive confirmation path (section 6.6) moves them to confirmed.

### 4.3 IDs

IDs are kind prefix plus zero-padded number: `INT-###`, `SR-###`, `DEC-###`, `FEAT-###`,
`NC-####`. The next ID is the highest existing number plus one. Identity comes from the
frontmatter `id`, never from the filename. Two records with the same ID (for example after
parallel branches merge) are an error that `plumb check` reports. Examples are numbered
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
unconfirmed until approved again. There are no consent phrases. An approval comes from one of
two sources:

- the owner running `plumb approve SR-004`, or `plumb approve --proposed` to approve every
  record still proposed (the batch form; it lists the records and their hashes in the entry);
- the agent recording a confirmation the owner gave in conversation. Such an entry is marked
  `by: agent-for-owner` and carries the owner's words verbatim plus the digest of the prompt
  that contained them. The prompt hook recorded that digest when the prompt arrived, so the
  quote can be checked. The entry also records its `basis`: `explicit` (the owner affirmed,
  for example "ok", "yes", or "approve all proposed") or `no-objection` (the owner's next
  prompt did not object to a statement shown in the previous reply; section 6.6).

Silence never counts as confirmation: an `agent-for-owner` entry always cites a real owner
prompt by digest, and with no owner prompt there is no approval.

An escalated plan (section 5.2) is approved as a set: one approval pins a set hash over the
sorted member hashes.

### 4.7 Append-only logs

Approvals, repins, test evidence promoted at merge boundaries, judgments, claim ingestions and
owner waivers are written as one JSON file per entry under `.plumb/log/<kind>/`. Each entry is
created with a no-replace link (`os.link` with a uuid suffix, so two writers in the same second
never collide) and is never edited. Each entry carries its own digest. Corrections are new
entries that reference the old one. At merge boundaries, plumb checks that no committed log
entry was modified or deleted.

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
   `INT` record with the owner's quote beside it, and becomes confirmed through the passive
   confirmation path (section 6.6).
2. **Requirements anchored in confirmed examples.** Each requirement carries concrete
   given/when/then examples, including edge cases. The agent states the examples in the same
   non-blocking way, records them as a proposed `SR`, and the owner confirms them through the
   passive confirmation path. Each example becomes an acceptance test linked by
   `verified_by`.
3. **Ambiguity as explicit decisions.** When two readings fit, the agent writes a `DEC`
   ("I assumed A; B also fits") instead of choosing silently.
4. **Traceable links.** Intent to requirement to examples and tests to code, each link pinned
   at both ends.
5. **A living record kept honest by drift signals.** Stale pins, unconfirmed edits and failing
   covering tests show up on the next turn, not at release time.

In this document, "the owner confirms" never means a blocking question. Confirmation always
rests on something the owner did (a command, or a prompt sent after the statement was shown),
never on silence, and it never interrupts the owner. Only the three triggers of section 6.6
can make the agent stop and ask.

### 5.2 Incremental and escalated planning

**Incremental mode is the default.** Intent is captured as work happens: a read-back, one or
a few requirements with examples, and decisions as they arise. Each piece is stated in the
agent's reply, recorded as proposed, and the agent proceeds on it without waiting. The owner
confirms it in the flow of conversation through the passive confirmation path (section 6.6),
never by answering a blocking question. No spec document is required.

**Escalated mode** is for large, risky or cross-cutting work. Before code is written, the agent
drafts the full set of intents, requirements, examples and decisions, plus a short Markdown
spec in `docs/specs/` that links them. The owner approves the set once (a set-hash approval).
Both modes use the same records, so escalated work simply produces more of them up front.

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

## 6. The grounding loop

The loop is four hooks plus a status line. Each hook is a single `plumb hook <event>` process
that starts with minimal imports, reads only `.plumb/` and the files named in records, uses
caches keyed by file fingerprints (size and mtime first, hash when those change), never runs
tests, never scans `site-packages`, and never starts one subprocess per file. If a hook cannot
finish within its budget, it reports "plumb: check skipped (budget)" and the turn continues.
plumb never blocks the owner's work because of its own failure.

### 6.1 Session brief (session start)

The session-start hook outputs a compact brief of at most about 60 lines:

- the active features;
- confirmed intents in one line each;
- open decisions that matter;
- stale links, unconfirmed edits, records still proposed, failing or missing evidence, and
  open NCs;
- the location of the test map (`plumb map`).

It is context, not procedure.

### 6.2 Per-prompt context and intent-change detection

On each prompt, the prompt hook:

1. records the prompt's digest (and, in gitignored session state, its text) so approvals can
   quote it;
2. selects the relevant records, either named by ID or matched by term overlap with titles,
   statements and examples, and injects them with their confirmed examples and the tests
   that cover them, in about 20 lines at most;
3. checks for a possible intent change. The heuristic default flags a prompt that matches a
   confirmed record and contains change language (instead, no longer, remove, rename, also,
   change, should now, don't). When the judgment backend is enabled, it filters these
   candidates first (section 8). A flagged candidate is injected as an instruction to the
   agent: "this may change SR-004 (confirmed). If it does, read back the change and ask
   before editing; if not, proceed." The agent, which is already running, acts as the
   cascade's LLM tier at no extra cost. Only a confirmed contradiction or extension reaches
   the owner.

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
- shows the owner a summary of at most five lines, for example:

```
plumb: touched SR-004, SR-007 | stale: SR-007 -> src/plumb/links.py:repin (code end)
plumb: covering tests 6 selected: 4 fresh pass, 1 not yet passing, 1 not yet run
plumb: proposed 2 (SR-009, INT-004) | confirmed SR-004 on your prompt "ok, go on"
plumb: questions: none
```

If the turn changed code whose covering tests have no fresh evidence, the hook asks the
*agent* (not the owner) once per turn to run `plumb verify`, which runs exactly those tests
and records evidence. Test execution belongs to the agent's turn and never to the hook's
latency budget.

### 6.5 Status line

`plumb status --line` reads `session/status.json` and recomputes nothing. It prints one
plain-ASCII line, for example `plumb | SR 12/14 ok | proposed 2 | stale 1 | tests ok | ask 0`.

### 6.6 Interruption triggers (exhaustive)

plumb asks the owner a question in exactly three cases:

1. **Real intent change.** A request contradicts or extends a confirmed intent, requirement
   or example. A deterministic backstop also counts here: a confirmed record whose hash
   changed this turn without a new approval.
2. **An unconfirmed decision that matters.** A `DEC` with `matters: true` that is not
   confirmed and is linked to a record or file touched this turn. Each decision is asked once
   per hash. The question is phrased "I assumed A; B also fits. Which one?"
3. **Regression.** A test that has passing evidence for an earlier identity now fails. This
   includes a covering test of a confirmed example that passed before and now fails. A test
   with no prior passing evidence is not a regression: during a test-first red step, a new
   test is expected to fail. It is shown as "not yet passing" in the summary and the status
   line and is never a question to the owner.

The agent asks in its reply, with a read-back. Nothing else interrupts. Stale links, proposed
records, not-yet-passing tests, escalation suggestions and skipped checks are logged and shown
in the summary, the status line, and `plumb status` / `plumb log`.

**Passive confirmation path.** New read-backs and examples are confirmed without a question:

1. The agent states the read-back and the proposed examples in its reply as a non-blocking
   statement ("Building X, not Y; assuming Z. Examples: EX-1 ..., EX-2 .... Say so if
   wrong.") and proceeds. The records are written as proposed and marked as stated in this
   turn in session state.
2. On the owner's next prompt, the prompt hook lists the records stated in the previous reply
   that are still proposed. The agent reads the prompt:
   - an explicit affirmation ("ok", "yes", "approve all proposed") is recorded as an
     `agent-for-owner` approval with `basis: explicit`, the owner's words and the prompt
     digest;
   - a prompt that does not object is recorded the same way with `basis: no-objection`;
   - an objection is not an approval: the agent revises the records, states them again, and
     asks only if the objection also meets one of the three triggers above.
3. Each approval made this way appears as one line in the end-of-turn summary (for example
   `plumb: confirmed SR-004 on your prompt "ok, go on"`), so the owner sees it and can revoke
   it, by saying so or with `plumb revoke SR-004` (a new log entry), without being
   interrupted.
4. Records stated in a reply that the owner never answered stay proposed: silence is not
   confirmation. The owner can confirm them at any time with `plumb approve SR-004` or
   `plumb approve --proposed`.

Only a decision with `matters: true` can block work, and only through trigger 2.

Escalated mode is the one case where the owner reviews up front, and only because the owner
accepted an escalation suggestion (section 5.2) and so asked for that review. Presenting the
set for its set-hash approval is then the work the owner requested, not an interruption.

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

Documentation-only changes select nothing. A change to shared test infrastructure selects
the full suite. The default infrastructure globs are `**/conftest.py`, plumb's pytest plugin,
`pyproject.toml`, `pytest.ini`, `tox.ini`, `setup.cfg` and `uv.lock`, and they are
configurable.

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

This is the owner's rule, carried over from pi-agent-factory:

- **Flaky rerun on the same tree.** When a test fails and then passes on a rerun with an
  identical tree and environment, it counts as a pass and is recorded as flaky with both
  attempts.
- **Owner-waiver targeted rerun.** An owner waiver lets a targeted rerun stand in for a full
  rerun. The waiver is an immutable log entry pinned to the diff digest it covers.
- **Full rerun only for shared test infrastructure.** A change to shared test infrastructure
  requires a full rerun. Any other change requires only the covering tests.

### 7.5 Merge-boundary verification (later)

At a merge boundary (sub-project 3), plumb runs the full suite, `plumb check` (no dangling
links, no duplicate IDs, no unconfirmed edits of confirmed records), the claims check, and the
log-integrity check. It then promotes the resulting evidence into the committed log. This is
the only place where heavy guarantees are paid for.

## 8. Optional judgment backend (JEV) and the heuristic default

Some loop decisions are classifications: does this prompt change that requirement, is this
diff cosmetic or material, does this code still fit its requirement. plumb answers them with a
deterministic **heuristic by default**, which needs no key, makes no network call and is
fully reproducible.

JEV (TypeSafe's typed-judgment model, which answers with `Choice`, `Score` or `Noul` in about
70 to 500 ms) can be enabled as an **optional** backend through `.plumb/config.yaml`, with the
key in `TYPESAFE_API_KEY` or the user store `~/.config/plumb/jev` (never inside the
repository). It is used for:

- intent-change detection on candidate prompts;
- drift triage (cosmetic or material) on stale links;
- a cheap advisory fidelity score scoped to the requirements changed in the turn.

The cascade is the one already validated in pi-agent-factory:

- confidence of 0.9 or more: accept;
- from 0.5 to 0.9: escalate to an LLM, which by default is the host agent through injected
  context;
- below 0.5: escalate to a human, but only when the item also meets an interruption trigger
  (section 6.6); otherwise it is logged.

When the resolved model version differs from the version the thresholds were validated
against, automatic acceptance is suspended. In the hook path, the call has a hard timeout of
about 800 ms; a timeout, missing key or error falls back to the heuristic with one logged
notice. State sent to the service is assembled only from tracked files, with secret-bearing
paths excluded and deterministic truncation. Every judgment is an append-only log entry with
its request fingerprint. Judgments are advisory: they order, filter and annotate, and they
never confirm a record or mark something fresh.

## 9. Host adapters

The core is a CLI with JSON output and a Python library. Hosts are thin adapters. **Claude
Code comes first**: `plumb install claude-code` writes four things.

- **Hooks** in `.claude/settings.json`: `SessionStart` (brief), `UserPromptSubmit` (context and
  intent check), `PostToolUse` on edit tools (tracking) and `Stop` (summary and verification
  nudge).
- **The status line command**.
- **A short `plumb` skill** of about 20 lines. It explains how to state a read-back and
  examples as non-blocking statements, how to record them and decisions, how to record an
  owner's confirmation (section 6.6), and when to run `plumb verify`.
- **A short CLAUDE.md block** naming `.plumb/` and `plumb map`.

It also installs the `commit-msg` hook for `SR:` trailers. Later adapters (Codex, Pi, Hermes,
and an MCP server exposing read-only record and map tools) reuse the same CLI commands.

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

  The register was owner-approved upstream, so imported records receive approvals marked
  `by: import`.
- **Maintenance mode.** Once the current integration batch lands, pi-agent-factory takes
  fixes only, and new feature work moves to plumb. The fork plan (a separate document)
  sequences the extraction, the import and the switch.

## 11. Roadmap

1. **Core, grounding loop and verification, dogfooded.** This covers:
   - the record model, hashing, links and pins, approvals (including the passive
     confirmation path of section 6.6), logs and `plumb check`;
   - `SR:` claims and the commit-msg hook;
   - the code-to-test map, covering-test selection, `plumb verify` with identity-pinned
     evidence, and the failure policy;
   - the four hooks, the status line and the Claude Code adapter;
   - the judgment interface with the heuristic, disabled and fake backends.

   Exit criteria: plumb's own requirements are `SR` records in `.plumb/`, its commits carry
   `SR:` trailers, plumb's hooks are installed in its own repository, and the hooks stay under
   budget.
2. **Intent capture and escalation.** This adds:
   - the read-back, example and decision helpers (`plumb intent`, `plumb example`,
     `plumb decide`);
   - the escalation triggers and set approvals;
   - the live JEV client (standard-library HTTP) and advisory fidelity scoring.
3. **Merge boundary.** This adds the full-suite run, evidence promotion, the claims audit over
   a range, log integrity, and a pre-merge or CI entry point.
4. **More adapters and MCP.** Codex, Pi, Hermes, and a read-only MCP server.
5. **Full importer and migration.** This covers:
   - a complete pi-agent-factory import with findings;
   - moving pi-agent-factory onto plumb;
   - retiring the duplicated modules there.

## 12. Non-goals

- No run state machine, no phases, no planning runs, no handoff hashes, no consent phrases, no
  review swarms, and no governed execution by default.
- No orchestration of agents. plumb informs and checks; the host agent does the work.
- No full test suite and no environment scan per turn.
- No hidden state: no database, no required service, and no network call on the default path.
- No model that decides freshness or confirms intent. Hashes decide staleness, and only the
  owner confirms: by a command, or by a prompt the agent records as an `agent-for-owner`
  approval (section 6.6). Silence never confirms.
- No forking of pi-agent-factory, and no runtime dependency on it.
- No dependencies beyond the standard library and PyYAML at runtime.
- No questions to the owner outside the three interruption triggers. Confirming a read-back
  or an example is never a question (section 6.6).
