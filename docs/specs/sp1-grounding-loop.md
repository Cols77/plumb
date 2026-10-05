# Sub-project 1 spec: core, grounding loop and covering-test verification

Status: implementation spec, written 2026-10-06. The owner does not review it (decision
D11: "I wont review the concept spec or any plan. use agents that verify that my intent based
on that conversation is respected."); independent verifier agents check it against the owner
intent brief and its rulings R1 to R7. When this spec, `docs/concept.md` and the owner's
quoted words disagree, the quotes and rulings win, then the concept, then this spec. Section
3 lists every place where this spec refines the concept, with the reason.

Revised about 01:00 local on 2026-10-06 for five binding coordinator rulings: the CORE lane is
built alone first, then a dogfood bootstrap, then VERIFY, HOST and BRIDGE in parallel; each
lane's MUST items fit about 75 minutes and everything else is SHOULD with a drop order; the
regression rule is R3 exactly; the fork plan is `docs/fork-plan.md`; and the build agents'
running outside plumb's hooks is stated as a known limitation (1, 3 F10 and F13, 7.5, 14).

Companion documents: `docs/concept.md` (the reference concept), `docs/plans/sp1-plan.md`
(lanes, tasks, tests, schedule), `docs/followups.md` (medium and low findings) and
`docs/fork-plan.md` (the pi-agent-factory fork plan, written by a later workflow phase).

## 1. Outcome

At the end of sub-project 1, plumb is a working tool that develops itself:

- plumb's own intent lives in `.plumb/` as `INT`, `SR`, `DEC` and `FEAT` records derived from
  `docs/concept.md`, each with a content hash, pinned links and a derived state, written in a
  dogfood bootstrap right after the core lands (14.1);
- every commit from that bootstrap on carries an `SR:` trailer, checked by a `commit-msg` hook
  as soon as the trailer check lands (14.1);
- Claude Code sessions on `C:/coding/plumb` run plumb's hooks: a short intent brief at session
  start, the relevant requirements and tests on every prompt with an intent-change flag, edit
  tracking, and an end-of-turn alignment summary that gets the covering tests run within a
  time budget and asks the owner only on the three agreed triggers;
- `plumb tests run` runs the covering tests of a change and appends identity-pinned evidence;
- `plumb validate --merge <base>` refuses a merge whose touched requirements are not all
  confirmed by the owner's own words;
- a judgment backend interface carries a heuristic default, and `plumb fidelity` builds the
  advisory packet for the host agent; with time left (plan SHOULD items), a read-only importer
  reads pi-agent-factory's SR, FEAT, bundle and NC records into plumb records and an optional
  JEV adapter plugs into the interface.

plumb is used on plumb as early as possible, following concept section 11, slice 1a. The CORE
lane is built alone first, with only the items the rest stands on; then a dogfood bootstrap
writes plumb's own records into `.plumb/` with `plumb init`, and every commit from then on
carries an `SR:` trailer; then the VERIFY, HOST and BRIDGE lanes build in parallel on top of
that core and of those records; and each part is set up in plumb's own repository as soon as
it lands: the `commit-msg` trailer check, the hooks in `C:/coding/plumb/.claude/settings.json`,
and the test map with recorded evidence (14.1). One limitation is stated honestly: the build
agents of the overnight run are subagents of a session rooted elsewhere, so they do not run
under plumb's own hooks. Full interactive dogfooding starts when the owner opens Claude Code in
`C:/coding/plumb` (14.1).

Each lane's MUST items fit in about 75 minutes of agent work; everything else is SHOULD, with
an explicit drop order (`docs/plans/sp1-plan.md`). The work is time-boxed to the owner's
deadline, an absolute time: about 2026-10-06 08:00 local, 9 hours after the owner's clock
started at about 23:00 local on 2026-10-05.

## 2. Owner intent served

| Owner decision or ruling | Where this spec serves it |
|---|---|
| Purpose: "make vibe coding grounded on the projects artifacts in an efficient, reliable and trustable manner" | Records (5), grounding loop (6), evidence (7), latency (10) |
| "a lighter, more elegant and interactive way to leverage coherence" | No run state machine, no phases; four hooks and a status line (6); non-goals (15) |
| D1 "A / B": standalone, pi-agent-factory can migrate | Installable in any repository (`plumb init`, `plumb hooks install`); importer (8.1, a plan SHOULD item) |
| D2 "C": incremental capture by default, escalation suggested | Records written as work happens (5.8); escalation hint in the prompt hook (6.2, a plan SHOULD item) |
| Intent translation: read-back, confirmed examples, explicit decisions, traceable links, drift signals | `INT` read-backs, `SR` examples, `DEC` records, pinned links, drift (5, 6) |
| D3 "B": host-neutral core, Claude Code first, reuse by extraction | CLI and library core; `plumb/hosts/claude_code` adapter (6); extraction table (13) |
| D4 "B" and the KEEP list ("Keep list looks fine") | Hashes and staleness (5.4, 5.5), pinned approvals (5.6), append-only logs (5.7), `SR:` trailers and claims (5.9), relation validation (5.10), NCs (5.2), features (5.2), identity-pinned evidence and failure policy (7.4, 7.5), advisory fidelity (8.3) |
| D5 "A": background, three triggers only | Stop hook summary and the exhaustive trigger list (6.4, 6.5) |
| D6: dogfood "as soon as possible and build with it" | CORE alone first, then the dogfood bootstrap (plumb's own records, `SR:` trailers on every commit from then on), then the other lanes on top of it, each part set up in plumb's repository as it lands (14.1); the lanes read `plumb brief` and run `plumb validate` while they build, and every merge runs `plumb tests run --full` once verification lands; the build agents do not run under plumb's hooks, stated as a known limitation, and full interactive dogfooding starts with the owner's first session in `C:/coding/plumb` (14.1; plan 4.5); dogfooding is never cut for review or SHOULD items (plan 11) |
| D7: reuse SR, FEAT, NC formats and IDs | Same ID formats and `SR:` trailers; importer (8.1, a plan SHOULD item) |
| D8: JEV optional, cascade, works without it | `JudgmentBackend` with heuristic default and JEV adapter (8.2) |
| D9: pi-agent-factory into maintenance mode, fork plan | Not built by sub-project 1's lanes: the fork plan is `docs/fork-plan.md`, written by a later workflow phase, required by the definition of done and linked from the morning handoff (14.2, 15; plan 12) |
| D10, D11: concept plus plans; owner does not review; implementation by the morning | This spec and the plan; verifier agents; a schedule anchored to the owner's absolute deadline (about 2026-10-06 08:00 local; clock rule at 07:15, handoff by 07:45), MUST items of about 75 min per lane, SHOULD items with an explicit drop order, and a drop rule for every phase (plan 1, 11) |
| D12: the name plumb | Package, CLI and `.plumb/` directory |
| R1: read-back and examples non-blocking; touched requirements confirmed at merge | `proposed` lines in the summary (6.4); `validate --merge` (5.11) |
| R2: no no-objection approval; `agent-relayed` with verbatim quote and prompt digest; honest trust model | `plumb relay` checks (5.6); merge-boundary approval list (5.11); trust model (5.6) |
| R3: regression = previously passed with recorded evidence | Regression rule (7.5) |
| R4: `plumb fidelity <SR>` packet for the host agent, JEV only accelerates | Fidelity (8.3) |
| R5: shared test infrastructure sets `full verification pending`; bounded sample on unknown coverage | Selection rules (7.2) |

## 3. Refinements of the concept, with reasons

Each refinement keeps the concept's guarantee and changes only its mechanism. Each becomes a
`DEC` record on plumb's own repository, so the owner sees it among the proposed records: F2,
F4 and F6 (`matters: true`) in the dogfood bootstrap, the others in the bootstrap if time
allows, otherwise in integration (plan 4.1, 9).

| # | Concept text | This spec | Reason |
|---|---|---|---|
| F1 | One JSON file per log entry under `.plumb/log/<kind>/` (4.7) | Two append-only JSONL streams, `.plumb/log/events.jsonl` and `.plumb/log/evidence.jsonl`, hash-chained per line, `merge=union` in git | One file read per hook instead of hundreds of small files on Windows; fewer files in git; same per-entry digest, `prev` chain and append-only check |
| F2 | `PreToolUse` hook on the shell tool denies `plumb approve` without `--prompt` (4.6 check 2) | Declarative `permissions.deny` rules in `.claude/settings.json`, plus the CLI session-marker check | A Python hook on every shell call costs about 250 ms of interpreter start per call on this machine; ten shell calls would break the 2-second per-turn budget. Deny rules cost nothing and are inspectable |
| F3 | `plumb approve SR-004 --prompt <digest> --quote "..."` for relayed approvals (4.6) | A separate command, `plumb relay SR-004 --prompt <digest> --quote "..."`; `plumb approve` is the owner's command only | Lets a deny rule block `plumb approve` and `plumb revoke` for the agent without blocking relays |
| F4 | The prompt hook writes each prompt digest to a committed log (4.6, 6.2) | The prompt hook writes `{digest, session, at, text}` to gitignored session state; `plumb relay` copies the cited `{digest, session, at}` into `events.jsonl` before the approval entry | Removes one committed file per prompt (followups round 4); the check "digest present in the log and recorded before the approval" still holds |
| F5 | Per-turn test evidence lives in the cache until the merge boundary (4.1, 7.3) | `plumb tests run` appends one compact entry per run to the committed `.plumb/log/evidence.jsonl`; the cache keeps only a derived reuse index | KEEP item "append-only evidence"; R3 regression detection must survive a cache deletion (followups rounds 2 to 4) |
| F6 | The stop hook asks the agent to run `plumb verify` (6.4) | Same mechanism, named `plumb tests run --changed`; the stop hook blocks once per turn with that instruction, the agent runs it inside its turn, and the hook never runs pytest itself | Hooks stay under 2 s while the covering tests still run every coding turn within `verify.turn_budget_s` |
| F7 | Commands `plumb check`, `plumb map`, `plumb verify`, `plumb install claude-code`, `plumb status --line` | `plumb validate`, `plumb tests map`, `plumb tests run`, `plumb hooks install`, `plumb statusline`; the concept names stay as aliases | The sub-project 1 command set given to the lanes; aliases keep the concept readable |
| F8 | Session brief of at most about 60 lines (6.1) | About 30 lines, hard cap 40 | Shorter context, same content; TDAD favours short context |
| F9 | `verify.turn_budget_s` 30 s, hard limit 2x (7.2) | 15 s, hard limit 1.5x | "Per-turn overhead is seconds, not minutes" (followups round 4) |
| F10 | Regression: a test that previously passed, with recorded evidence, now fails (6.6) | Same rule, applied exactly as R3 and keyed by the test's node id: an existing test node with an earlier `passed` or `flaky` `test-run` entry that now fails IS a regression, even if its source changed since that pass. When its `test_hash` differs from the one of that pass, the regression instruction adds the note `test source changed since the pass`; the note never suppresses the trigger. Only a NEW test that starts red is exempt: a node id with no recorded passing evidence is `not yet passing`, never a regression, and never interrupts | R3 exempts only a new test that starts red. Editing an existing test must not turn a regression into `not yet passing`, or an agent could edit a test until its failure stops counting; the note tells the owner that the test itself changed. A SHOULD item lists a previously passing node that is no longer collected (`removed after passing`, plan VS1), so renaming a test cannot hide it either |
| F11 | Imported records with an upstream approval get `by: import` (10) | The minimal importer imports every record as proposed; `by: import` approvals wait for the full importer (sub-project 5) | Never manufactures a confirmation; safe lower bound of the concept rule |
| F12 | Links live in their source record (4.5) | Unchanged; "link" is a first-class data type (`Link`, `LinkState`) and command (`plumb link`), not a separate file | A link file per link would double the files a hook reads and split a requirement from its evidence chain |
| F13 | Slice 1a is built in the listed order, one step after another; plumb's own `SR` records and `SR:` trailers start at step 3, and each hook is installed in plumb's repository as soon as it lands (11) | Slice 1a is built as: the CORE lane alone (concept steps 1, 2 and 4: records, hashes, links, the log, pinned approvals including agent-relayed ones, `validate` with `--merge`, plus brief and status); then the dogfood bootstrap (step 3's records: `plumb init`, plumb's own `INT`, `SR` with examples and `FEAT-001`; `SR:` trailers on every commit from then on); then VERIFY (step 6), HOST (step 5) and BRIDGE (step 3's `commit-msg` check, the judgment interface, fidelity and claims) in parallel on top of that core. Each part is set up in plumb's own repository as soon as it lands: the `commit-msg` hook when the trailer check lands, the hooks in `.claude/settings.json` when HOST lands, the test map and recorded evidence when VERIFY lands (14.1). The judgment interface with its heuristic backend, fidelity packets and the claims check move up from 1b into BRIDGE's MUST items, because the prompt hook's intent-change flag (trigger 1) uses the first and the other two are KEEP items. The JEV live client and the minimal importer are SHOULD items (the concept puts them in sub-projects 2 and 5); the AST symbol hashing, the flaky rerun, the full environment identity and the owner waiver (concept 1b) are SHOULD items with an explicit drop order. The build agents of the overnight run do not run under plumb's hooks (14.1) | The 9-hour box (D11) needs parallel lanes, and each lane's MUST list fits about 75 minutes. Building the core alone first keeps the critical path short and lets every later lane build on the real core and on plumb's own records instead of fakes, which is the earliest point at which plumb can hold its own intent ("as soon as possible and build with it", D6) |

### 3.1 Work-order wording reconciled with the rulings

The sub-project 1 work order (written by the coordinating workflow, not by the owner) asks
for two behaviours that the binding rulings settle differently. The rulings win:

- "Fallback to the whole suite on shared test infrastructure or unknown coverage." Under R5,
  neither ever runs the whole suite in a turn. Shared infrastructure sets
  `full verification pending`; unknown coverage runs a bounded sample and sets the same flag.
  The whole-suite fallback happens at the merge boundary, which satisfies the flag
  (`plumb tests run --full`, section 7.2).
- "Stop hook: runs the covering tests within a budget." The stop hook gets the covering tests
  run within the per-turn budget by asking the agent once per turn (F6); pytest itself runs in
  the agent's turn, so the hook stays within its own sub-second budget and the per-turn rule
  of 2 seconds.

## 4. Repository layout

### 4.1 Where plumb's records live

plumb keeps everything it owns under `.plumb/` at the repository root, as the concept does
(4.1). Reasons, against putting records under `docs/`:

1. One directory to scan: a hook fingerprints `.plumb/` with one `os.scandir` walk and never
   walks the rest of the repository.
2. Machine-checked records stay apart from prose. `docs/` keeps human documents (concept,
   specs, plans), which plumb links to but does not parse.
3. Adoption and removal are one directory, which matters for "installable in any repository"
   (D1) and for importing pi-agent-factory side by side with its own `requirements/`.
4. Everything stays inspectable: Markdown with YAML frontmatter and JSONL, all in git, except
   the derivable `cache/`, the per-session `session/` and the generated `test_map.txt`.

### 4.2 Tree

```
.plumb/
  config.yaml                  # optional settings (section 11); commented defaults from `plumb init`
  claims.yaml                  # SR trailer policy: exempt globs, NC-backed baseline
  .gitignore                   # cache/  session/  test_map.txt
  .gitattributes               # log/*.jsonl merge=union
  intents/INT-001.md
  requirements/SR-001.md
  decisions/DEC-001.md
  features/FEAT-001.md
  ncs/NC-0001.md
  log/events.jsonl             # approvals, revocations, cited prompts, repins, judgments, waivers, imports
  log/evidence.jsonl           # one entry per `plumb tests run`
  test_map.txt                 # generated, grep-able (TDAD style), gitignored
  cache/                       # gitignored, derivable: index.json, hashes.json, test_map.json,
                               #   evidence_index.json, env_identity.json, config.json, log.lock
  session/                     # gitignored: prompts.jsonl, status.json, stated.json,
                               #   <session_id>/touched.txt, <session_id>/turn.json, errors.log
```

Record files are named `<ID>.md`, optionally `<ID>-<slug>.md`; identity comes from the
frontmatter `id`, never from the filename.

Repository-level files written by `plumb hooks install` (Claude Code adapter): entries in
`.claude/settings.json`, `.claude/skills/plumb/SKILL.md`, `.claude/commands/plumb.md`, a
marked block in `CLAUDE.md`, and the git `commit-msg` hook.

## 5. Record model

### 5.1 Common shape

Every record is a Markdown file: a YAML frontmatter block between the first two `---` lines,
then a free Markdown body. Frontmatter is parsed with PyYAML's safe loader (C loader when
available). Required fields: `id`, `title`. Optional on every kind: `links`, `status_note`.
Body wikilinks (`[[SR-004]]`, `[[SR-004|title]]`) are checked like links (no dangling ID).

### 5.2 Kinds and fields

| Kind | ID | Fields (besides `id`, `title`, `links`) |
|---|---|---|
| intent | `INT-###` | `quote` (string or list: the owner's verbatim words), `readback` (restatement in the owner's terms), `will` (list of `{id: W-n, text}`), `wont` (list of strings), `assumptions` (list of `{id: A-n, text}`), `mode` (`incremental` or `escalated`, default `incremental`), `source` (where the quote came from) |
| requirement | `SR-###` | `statement`, `feature` (`FEAT-###`), `examples` (list of `{id: EX-n, given, when, then}`; imported records may carry `{id: AC-n, criterion}`), `domain` (optional, kept from imports) |
| decision | `DEC-###` | `question`, `chosen`, `alternatives` (list), `rationale`, `matters` (bool) |
| feature | `FEAT-###` | `description`, `requirements` (list of `SR-###`) |
| nc | `NC-####` | `status` (`open`, `corrected`, `waived`), `detected_by`, `corrected_by`, `external_ref` |

A requirement in plumb's own repository:

```yaml
---
id: SR-003
title: Links pin both ends
feature: FEAT-001
statement: Every link records the content hash of both of its ends, and plumb reports the
  link as stale when either end's current hash differs from its pin.
examples:
  - id: EX-1
    given: SR-003 links to a test whose pins are current
    when: the test function's body changes
    then: plumb drift reports the link stale and names the target end
  - id: EX-2
    given: the same link with current pins
    when: the test file is re-saved with CRLF line endings and no other change
    then: the link stays current
links:
  - {kind: derives_from, to: INT-006, pin: {from: "sha256:...", to: "sha256:..."}}
  - {kind: verified_by, test: "tests/core/test_links.py::test_pin_drift", example: EX-1,
     pin: {from: "sha256:...", to: "sha256:..."}}
  - {kind: implemented_by, path: src/plumb/links.py, symbol: "plumb.links:link_states",
     pin: {from: "sha256:...", to: "sha256:..."}}
---
```

Decisions are immutable once confirmed: a change is a new `DEC` with a `supersedes` link.
Superseded records are left out of the brief and of the prompt context.

### 5.3 IDs

Kind prefix plus zero-padded number: `INT-###`, `SR-###`, `DEC-###`, `FEAT-###` (three digits
or more) and `NC-####` (four digits or more). `plumb new` takes the highest existing number
plus one. Two records with the same ID are a `validate` error. Examples are numbered inside
their requirement (`SR-003/EX-2`); imported acceptance criteria keep `AC-n`; intent items are
`INT-004/W-1` and `INT-004/A-2`.

### 5.4 Content hash and normalization

Every record has a hash `sha256:<64 hex>` computed on read and never stored in the record:

- every frontmatter field except `links`, serialized as canonical JSON (sorted keys, UTF-8,
  separators `,` and `:`), so YAML style and key order do not matter, and pinning a link never
  changes the record's own hash;
- the body, normalized: CRLF and lone CR to LF, trailing whitespace stripped per line,
  trailing blank lines dropped, Unicode NFC, and `<!-- derived -->` ... `<!-- end derived -->`
  blocks removed.

The hash input is `canonical_json({"fields": ..., "body": ...})`.

Link ends that are not records:

| End | Hash input |
|---|---|
| `path` only | the file's normalized text (same rules as the body), or raw bytes if it is not UTF-8 text |
| `path` + `symbol: module:Qual.name` | the normalized source segment of that definition (decorators included), found with `ast` in that one file |
| `test: path::name` (or `path::Class::name`) | the normalized source of that test function; parametrize ids (`[...]`) are dropped |

Whole-file ends are a CORE MUST item; symbol and test ends are a SHOULD item (plan KS4).
Until it lands, `plumb link` rejects a `::` target with a usage error (exit 2), and
`verified_by` links name test files. Directories and globs cannot be link ends; line numbers
are never identity. A symbol or test
that no longer exists makes the link dangling. File hashes are cached in
`.plumb/cache/hashes.json` keyed by `(size, mtime_ns)`; symbol and test hashes are cached
under the file's key.

### 5.5 Links, pins and staleness

A link lives in its source record's `links` list. Its id is `<source>#<index>` (zero-based
position in that list). Fields: `kind`; a target (`to: <ID>`, or `path` with optional
`symbol`, or `test`); optional `example` (`EX-n` or `AC-n`, for `verified_by`); `pin`
`{from, to}` holding the source record's hash and the target's hash when the link was last
pinned.

| Kind | Allowed source to target |
|---|---|
| `derives_from` | SR, DEC, FEAT to INT |
| `decides` | DEC to INT or SR |
| `upstream`, `relates_to` | SR to SR |
| `implemented_by` | SR to code (`path`, optionally `symbol`) |
| `verified_by` | SR to test (`test`, or a test file `path`), optionally naming an example |
| `corrects` | NC to SR or code |
| `supersedes` | any record to a record of the same kind |

Link states: **current** (both pins equal both current hashes), **stale** (either differs;
the report says `source`, `target` or `both` moved), **dangling** (the target does not exist;
an error), **unpinned** (no pin yet; a warning). `plumb link` adds a link with fresh pins;
`plumb repin <link-id>|<record>|--all-stale` refreshes pins (and pins unpinned links) and
appends a `repin` event naming the old and new pins. Repinning never confirms a record. A
repin whose target end is code or a test marks that requirement `fidelity unjudged` until a
judgment exists for the new hashes (8.3).

### 5.6 Approvals and the self-approval guard

Requirement and record states are derived, never stored:

- **proposed:** no approval pins the record's current hash, and none ever did;
- **confirmed:** the latest approval (not revoked) pins the current hash;
- **unconfirmed edit:** an approval exists but pins an older hash (a drift signal; the merge
  boundary asks for it);
- **covered** (SR only): confirmed, and every example has at least one `verified_by` link to
  an existing test;
- **verified** (SR only): covered, and every covering test has fresh passing evidence (7.4).

An approval is an `events.jsonl` entry of kind `approval`:

```json
{"records": [{"id": "SR-003", "hash": "sha256:..."}], "by": "owner",
 "prompt_digest": null, "quote": null, "quote_digest": null, "affirmation": null,
 "stated_set": null, "note": ""}
```

Sources of approval, and only these:

1. **Owner.** `plumb approve SR-003 [SR-004 ...]` or `plumb approve --proposed` (lists every
   proposed or unconfirmed-edit record with its hash, asks `y/N` on a TTY unless `--yes`),
   run by the owner in their own terminal. `by: owner`. Refused (exit 3) when the session
   marker `PLUMB_AGENT_SESSION` is set.
2. **Agent-relayed.** `plumb relay SR-003 [...] --prompt <digest> --quote "<owner's words>"`.
   `by: agent-relayed`. Before writing anything, plumb checks:
   - the digest (full or a unique prefix of at least 12 hex digits) is in
     `.plumb/session/prompts.jsonl`, and that entry's text hashes to it;
   - the quote, after body normalization, is a verbatim substring of that prompt text;
   - the quote contains a configured affirmation term as a whole word or phrase
     (`approve.affirmations`; default ok, okay, yes, approve, approved, confirm, confirmed,
     agreed, lgtm, go ahead, sounds good), and that affirmation affirms where it stands in the
     prompt: its sentence (ended by `.`, `!`, `?` or `;` before whitespace, or a line break)
     does not end in `?`, and has no negation before it (no, not, never, wait, hold, stop,
     cannot, a `n't` word and the like; idioms such as "no objections" excepted). A question
     or an objection confirms nothing (R2);
   - every approved record is in the stated set (`.plumb/session/stated.json`, written by the
     stop hook of the reply just before that prompt) **and was shown there in full**
     (`shown: true`), or is named by ID in the quote. A record the summary cut (cap, a line
     too long) or a record of a blocked stop is `shown: false`: a bare "ok" never confirms
     content the owner was not shown.

   A failed check exits 3 and writes nothing. On success plumb appends a `prompt` event
   `{digest, session, at}` (if that digest is not yet in `events.jsonl`; `at` is the time
   the prompt hook recorded) and then the approval with `prompt_digest`, `quote`,
   `quote_digest`, `affirmation` and `stated_set`.

There is no other way to confirm. Silence, or a prompt that neither affirms nor objects,
confirms nothing (R2). `plumb revoke <ID>` (owner) and `plumb relay --revoke <ID> --prompt
--quote` (relayed; the quote need not affirm) append a `revocation` event
`{records: [{id, hash}], by, prompt_digest, quote, quote_digest, note}`; the record returns
to proposed or unconfirmed edit. Approvals, relays, revocations and the derivation of
confirmation from these events all live in CORE (`approvals.py`, `confirm.py`), so one module
writes and reads them.

The guard, three layers, none calling a model:

1. **Session marker.** `plumb hooks install` sets `PLUMB_AGENT_SESSION=claude-code` in the
   `env` of `.claude/settings.json`. Every agent shell command inherits it; the owner's own
   terminal does not. With the marker set, `plumb approve`, `plumb revoke` and
   `plumb tests waive` refuse. Every log entry records the marker in force (`marker`).
2. **Deny rules.** The installer adds `permissions.deny` entries: `Bash(plumb approve:*)`,
   `Bash(plumb revoke:*)`, `Bash(plumb tests waive:*)`, the same three behind `uv run ` and
   `python -m `, `Bash(*PLUMB_AGENT_SESSION*)`, and `Edit`, `Write` and `MultiEdit` on
   `.plumb/log/**`. If a host version reads `*` only as a prefix wildcard, the marker rule is
   inert; layer 1 and the trust model still hold.
3. **Write-time quote check** (above), whose result is stored in the entry, so it stays
   inspectable after session state is deleted.

`plumb validate` re-checks every committed approval: a relayed entry cites a `prompt` event
written earlier in the stream, its quote contains an affirmation term and matches its
`quote_digest`; an owner entry written under a marker is an error.

**Trust model, stated honestly (R2).** The logs are hash-chained and tamper-evident, not
tamper-proof against a malicious agent. An agent determined to bypass the guard can forge an
entry before it is committed. plumb guarantees that self-approval cannot happen by accident,
is refused on the normal path, and that any edit, deletion or reordering of a committed entry
shows in `plumb validate` and in git; the merge-boundary list of approvals (5.11) is the
owner's cheap backstop.

### 5.7 Append-only logs

Two streams, both committed: `.plumb/log/events.jsonl` and `.plumb/log/evidence.jsonl`. One
JSON object per line:

```json
{"v": 1, "kind": "approval", "at": "2026-10-06T03:12:45Z", "marker": "none",
 "payload": {...}, "prev": "sha256:<digest of the previous line's entry or null>",
 "digest": "sha256:<sha256 of canonical JSON of every other field>"}
```

Writing: take `.plumb/cache/log.lock` (created with `O_CREAT | O_EXCL`; retry for up to
2 s; a lock older than 10 s, which only plumb creates, is removed), read the last line by
seeking back from the end of the file, compute `prev` and `digest`, append one line with a
single `write` call, `fsync`, release. Entries are never edited; a correction is a new entry
that names the old digest.

`plumb validate` checks each line's digest and that each `prev` is null (first line) or the
digest of an existing line; branches merged with `merge=union` fork the chain, which is
accepted. `plumb validate --merge <base>` also checks that every line of the stream at
`<base>` is still present, unchanged, in the current file (one `git show` per stream).

Event kinds: `approval`, `revocation`, `prompt`, `repin`, `judgment`, `waiver`,
`claims-ingest`, `import`. Evidence kind: `test-run` (7.4).

### 5.8 Creating records

`plumb new <kind> --title "..." [kind fields]` writes a skeleton with the next ID and prints
its path; for example `plumb new requirement --title "Links pin both ends" --feature FEAT-001
--statement "..." --example "given|when|then"` and `plumb new intent --quote "..." --readback
"..." --will "..." --wont "..." --assume "..."`. `--derives-from INT-004` adds a pinned link.
New records are proposed. The agent records read-backs as `INT`, examples on `SR`, and
ambiguities as `DEC` ("I assumed A; B also fits") as work happens, without waiting (R1).

### 5.9 `SR:` trailers and claims

A commit declares the requirements it serves with a trailer line `SR: SR-003, SR-007`.

- `plumb trailers check-msg <file>` (run by the `commit-msg` hook) rejects a message whose
  `SR:` trailer names a malformed or unknown ID. A message without the trailer passes unless
  `claims.require_trailer: true` in `.plumb/claims.yaml` (plumb's own repository sets it as
  soon as the trailer check lands, 14.1). In a checkout with no `.plumb/` directory (a repository that has not
  adopted plumb, or a worktree whose branch predates `plumb init`), the check passes with the
  notice `plumb: not initialized here, trailer not checked`.
- `plumb trailers install-hook` writes the git `commit-msg` hook, which runs
  `<interpreter> -m plumb trailers check-msg "$1"` with the interpreter that installed it.
  The hook lives in the shared git directory, so it serves every worktree. An existing
  non-plumb `commit-msg` hook is left untouched and reported. `plumb hooks install` calls
  the same function (6.7).
- `plumb claims check [--range <base>..<head>] [--json]` reads the range with one
  `git log --format=... --name-only -z` call, takes each commit's `SR:` IDs and changed
  paths, and reports **undeclared** paths: changed by a commit that claims SRs, not a
  declared end (`implemented_by` or `verified_by` path, or the record file) of any claimed
  SR, and not exempt. Default exempt globs: `.plumb/**`, `docs/**`, `.claude/**`,
  `uv.lock`, `.gitignore`, `.gitattributes`. The NC-backed baseline in `claims.yaml`
  (`baseline: [{commit, path, nc}]`) may only shrink. Exit 1 when undeclared paths exist.

### 5.10 Validation

`plumb validate [--json]` reports, with severity:

- errors: duplicate IDs; malformed frontmatter or IDs; a link kind not allowed between its
  ends; dangling links and wikilinks; a log line whose digest or `prev` fails; an approval
  that fails its re-check (5.6);
- warnings: stale and unpinned links; unconfirmed edits; confirmed examples without a
  `verified_by` test; an `SR` without a `derives_from` link to an `INT`; an `INT` `will` item
  or assumption with no deriving `SR` or deciding `DEC`; a `DEC` with `matters: false` that
  decides a confirmed record (reported as mattering anyway).

The wikilink check (5.1) and the warning on untranslated `INT` items are a SHOULD item (plan
KS5); every other check above is a CORE MUST item. Exit 0 without errors, 1 with errors.
`plumb drift` (a SHOULD item, plan KS3) prints only the drift signals (stale and
dangling links with the moved end, unconfirmed edits, uncovered examples, unjudged fidelity).

### 5.11 Merge boundary (`plumb validate --merge <base>`)

Over the range `<base>..HEAD` plus uncommitted changes:

1. **Touched requirements must be confirmed.** A requirement is touched when its record file,
   or one of its `implemented_by` or `verified_by` ends, changed in the range, or a commit in
   the range claims it in an `SR:` trailer. Each touched requirement, the `INT` records it
   derives from, and each `DEC` with `matters: true` that decides it must be confirmed at its
   current hash. Otherwise the command prints one trigger-2 question listing those records
   with their read-back or statement and examples, and exits 4 ("merge waits for your
   confirmation: `plumb approve SR-003 SR-007`, or say ok in the session").
   **Untraced changes go in the same question.** A changed source path that no requirement
   owns (no `implemented_by` or `verified_by` end names it; `plumb.trace`) skipped the
   read-back: no statement, no example, nothing the owner could confirm. Such paths are listed
   as `untraced changes (no requirement owns them)` in the same trigger-2 question, and the
   merge waits (exit 4) until a requirement owns them (the agent records a proposed SR with
   examples and links it, then the owner confirms it) or the owner lists them under
   `trace.exempt` in `.plumb/config.yaml` and confirms that. Source paths are files under
   `source_dirs` outside `test_dirs`, minus shared test infrastructure, generated files
   (`__pycache__`, `*.pyc`, tool caches, build output) and `trace.exempt`; with a source
   directory of `.`, documentation and dot directories are left out too. When
   `.plumb/config.yaml` does not name `source_dirs`, a code file (by suffix) anywhere outside
   the test directories, `docs/` and dot directories is source as well, so a flat layout
   (`mypkg/`) or a root module is traced. The covering-test selection uses the same definition
   (`plumb.trace.is_code_path`).
   **Widening and exempting go in the same question.** Links are left out of a record's hash
   (4.4), so `plumb link` or a frontmatter edit could make a confirmed requirement own new code
   without unconfirming it. An approval therefore lists the requirement's owning ends
   (`implemented_by src/x.py`), and a requirement that gained an owning end in the range that
   no approval of it at its current hash lists is shown as `SR-001 (extended)` with
   `new link in this range: implemented_by src/z.py`, and the merge waits (exit 4) until the
   owner approves it again. A `trace.exempt` glob added in the range is listed
   (`trace.exempt src/**: added in this range`) and not honoured until the owner confirms it
   with `plumb approve --exempt` (or the agent relays an affirmation that names the exemption,
   `plumb relay --exempt`); a path that was source under the merge base's config stays
   source, so narrowing `source_dirs`, `test_dirs` or the infrastructure globs hides nothing.
2. **Approvals in the range, for a glance.** Every approval and revocation event added in the
   range, owner and agent-relayed, with its record and quote; agent-relayed entries are marked
   and also show the prompt digest they cite (R2).
3. **Fidelity, advisory.** Touched requirements with no judgment for their current hashes, or
   whose latest judgment is `drifts` or `unsure`, each with its `plumb fidelity` command
   (from BRIDGE's `unjudged`, 12.2; `fidelity: unavailable` without it).
4. **Verification state.** `full verification pending` with its reasons, tests deferred by
   the per-turn budget, touched requirements that are confirmed but not covered, and touched
   requirements whose acceptance tests (their `verified_by` ends, and the tests the map ties
   to them by marker) failed in their last recorded run, each with its example ids:
   `failing acceptance tests: SR-001 EX-1 tests/test_calc.py (regression)`. A failure is kept
   until a run passes the test, whatever changed since; one recorded on another identity reads
   `(failing, stale: not rerun since the change)`. Touched acceptance tests with no passing
   evidence on the current identity (never run, or stale since their last pass) are listed as
   `unverified acceptance tests`. While any touched acceptance test fails or is unverified, or
   any recorded regression (R3: a node that passed and has not passed since) is unresolved,
   the report exits 5 ("verification holds the merge"); a passing run of those tests resolves
   it. These lines appear only at the merge boundary, never per turn (R3). A full run
   satisfies `full verification pending` only when it collected cleanly, ran tests and every
   test it failed has passed since: pytest exit 5 (nothing collected), a collection error or
   an empty run never clears it, and exit 5 on a suite with known tests is an aborted run. If
   the verify lane is not importable, the line says `verification: unavailable`.
5. **Log integrity** against `<base>` (5.7).

Exit precedence: 1 (log integrity) before 5 (verification holds the merge: a failing or
unverified touched acceptance test, or an unresolved regression) before 4 (the merge waits for
the owner's confirmation). `plumb drift` lists the same failing acceptance tests
as drift signals (exit 1), and `plumb status` counts the failing requirements and names their
examples.

The full-suite run, evidence promotion and the claims audit as a gate belong to sub-project 3.

## 6. Grounding loop (Claude Code adapter)

Each hook is one process, `plumb hook <event>`, that reads the host's JSON on stdin, writes
its answer on stdout and always exits 0. On an internal error or an exhausted budget it prints
`plumb: check skipped (budget)` or `plumb: check skipped (error, see .plumb/session/errors.log)`
and the turn continues: plumb never blocks work because of its own failure.

### 6.1 SessionStart: the intent brief

Plain-text context, about 30 lines, hard cap 40, from `CoreAPI.brief_lines` plus
`VerifyAPI` state:

```
plumb brief (records in .plumb/, test map in .plumb/test_map.txt)
features: FEAT-001 records and integrity (8 SR), FEAT-002 grounding loop (7 SR), ...
intent (confirmed):
  INT-001 grounded vibe coding: "make vibe coding grounded on the projects artifacts ..."
  ...
awaiting your confirmation: 14 proposed (INT-002, SR-004, ...), 1 unconfirmed edit (SR-007)
decisions that matter, unconfirmed: DEC-002 permission deny rules instead of a guard hook
drift: stale 1 (SR-007#2 target moved) | dangling 0 | uncovered examples 3
tests: 2 failing (tests/core/test_links.py::test_pin_drift ...) | full verification pending (uv.lock)
open NCs: NC-0001 ...
```

Context, never procedure. Sections that would exceed the cap end with `+N more (plumb brief
--all)`. The hook also writes `.plumb/session/status.json` (6.6) so the status line has data
from the first turn.

### 6.2 UserPromptSubmit: relevant records, tests and the intent-change flag

1. Compute `digest = sha256(prompt text)`; append `{digest, session, at, text}` to
   `.plumb/session/prompts.jsonl`; record the turn start time in
   `.plumb/session/<session_id>/turn.json`.
2. Select relevant records: IDs named in the prompt first, then `CoreAPI.relevant(prompt)`
   (term overlap with titles, statements and examples; superseded records excluded), at
   most 5. Print each with its state, its confirmed examples (one line each, truncated to
   100 characters) and its covering tests from `VerifyAPI.tests_for`. At most 20 lines.
3. Intent-change flag: `JudgmentBackend.intent_change(prompt, confirmed matched records)`.
   The heuristic flags a confirmed record matched by ID or by strong overlap together with
   change language (instead, no longer, remove, rename, also, change, should now, don't,
   stop, replace). For each flag:
   `plumb: this may change SR-004 (confirmed). If it does, read back the change and ask before
   editing; if not, proceed.` Whenever confirmed records are injected, one more line tells the
   agent to compare the request with their examples, so a contradiction phrased without
   change words is still caught by the agent (the cascade's LLM tier, at no extra call).
   Every flag is logged to session state for later precision measurement.
4. Awaiting confirmation: the records of the previous reply's stated set that are still
   proposed, with the prompt digest prefix and the relay form:
   `plumb: awaiting confirmation: SR-009, INT-004 | prompt sha256:3f2a9c01b7de | if this
   prompt affirms them, run plumb relay <IDs> --prompt 3f2a9c01b7de --quote "<owner's exact
   words>"; otherwise leave them proposed.`
5. Untraced change: when the previous stop named a changed source path that no
   requirement owns (6.4), the agent is told, once and only while the path is still untraced:
   `plumb: untraced change: src/app/mul.py changed with no requirement owning it. Read the
   change back to the owner in their terms (what will and won't be done, assumptions
   labelled), record it as a proposed SR with given/when/then examples (edge cases too)
   deriving from an INT, and link it implemented_by those paths.` The Stop hook's own
   output reaches only the owner unless it blocks, so this prompt line is how a non-blocking
   instruction reaches the agent (R1).
6. Escalation hint (a SHOULD item, plan HS5): when the matched records span more than
   `escalation.max_features` features or more than `escalation.max_requirements`
   requirements, or a confirmed record is flagged in step 3, print
   `plumb: consider escalating to an up-front spec (reason); the owner decides.`

Output is plain text on stdout (added to the agent's context).

### 6.3 PostToolUse on Edit, Write, MultiEdit, NotebookEdit: edit tracking

Appends the tool input's file path, made repository-relative, to
`.plumb/session/<session_id>/touched.txt`. Standard library only, no YAML, no record index.
Registered with `"async": true` so it adds no blocking latency; on a host that ignores
`async`, the fast path still finishes in about 300 ms on this machine.

### 6.4 Stop: covering tests within the budget, then the alignment summary

1. Changed paths this turn: `touched.txt` plus every path in one
   `git status --porcelain -z --untracked-files=all` call whose mtime is at or after the turn
   start time.
2. Map them to records (`CoreAPI.records_for_paths`), recompute the hashes and link states of
   those records only, and get the covering selection (`VerifyAPI.select`) and its evidence
   state (`VerifyAPI.evidence`).
3. Write `.plumb/session/status.json` and `.plumb/session/stated.json` (every record created
   or edited this turn that is proposed or an unconfirmed edit, plus every record named in a
   trigger-2 instruction of this stop). Each record carries `shown`: true only when the
   summary displayed its whole read-back (`plumb.readback.record_lines`: an INT's read-back,
   will, won't and every labelled assumption; an SR's statement and every example; a DEC's
   chosen option and alternatives). The set is first written with `shown: false` and
   rewritten after the summary is composed, so a blocked stop or a hook cut short shows the
   owner nothing relayable.
4. Decide, at most one block per turn and never when the host says `stop_hook_active`:
   - **Covering tests not run.** If the selection has nodes without fresh evidence, answer
     `{"decision": "block", "reason": "plumb: run 'plumb tests run --changed' (covering
     tests, budget 15 s), then finish your reply."}`. The agent runs it inside its turn
     (F6); the run is capped by `verify.turn_budget_s` and never selects the full suite.
   - **Trigger 2 (a decision that matters).** A `DEC` with `matters: true`, unconfirmed,
     linked to a record or file touched this turn, not yet asked at this hash: block with
     `plumb: DEC-002 is unconfirmed and this work relies on it. Ask the owner: "I assumed A;
     B also fits. Which one?"`.
   - **Trigger 3 (regression).** Known at stop time from earlier evidence: block with
     `plumb: regression: <node> passed in run <id> and now fails. Tell the owner, with a
     read-back, and ask how to proceed.`, with ` (test source changed since the pass)`
     appended after `now fails` when the node's `test_changed_since_pass` is set (7.5). A
     regression found by the agent's own
     `plumb tests run` is printed by that command with the same instruction.
   - **Untraced change (never a block of its own, R1).** Changed source paths that no
     requirement owns (5.11) are named on the summary's first line,
     `| untraced: src/app/mul.py (read-back and a proposed SR requested)`. When the stop
     blocks anyway, the block reason carries the agent instruction of 6.2 step 5; otherwise
     it is queued in `.plumb/session/<session_id>/untraced.json` for the next prompt. The
     always-loaded CLAUDE.md block (6.7) tells the agent to read back each request and record
     it as proposed, so the hooks only catch what slipped through.
5. Otherwise answer `{"systemMessage": "<summary>"}`, at most five lines, then the full
   read-back of at most `hooks.summary_proposed_cap` (3) proposed **records** (the cap counts
   records, never lines: a shown record shows every one of its lines), then, when records
   were cut, one line naming them with the command that prints them:
   `plumb: +2 more not shown: SR-005, SR-006 (plumb show SR-005 SR-006); a confirmation must
   name them`. A record with a line over 400 characters is cut the same way:

```
plumb: touched SR-004, SR-007 | stale: SR-007#2 -> src/plumb/links.py (target moved)
plumb: covering tests 6: 4 fresh pass, 1 not yet passing, 1 deferred (budget)
plumb: full verification pending (tests/conftest.py changed)
plumb: confirmed SR-004 on your prompt "ok, go on" | fidelity unjudged: SR-007
plumb: questions: none
plumb: proposed INT-004: build the status line, not the MCP server; assumes ASCII only
plumb: proposed SR-009/EX-1: given a stale link, when status runs, then it shows stale 1
```

A documentation-only turn prints at most one line. A turn with no changes prints nothing.

### 6.5 Interruption triggers (exhaustive)

The agent asks the owner only on: (1) a real intent change, a request that contradicts or
extends a confirmed intent, requirement or example (flagged by 6.2, decided by the agent);
(2) an unconfirmed decision that matters: a `DEC` with `matters: true` touched this turn, the
touched requirements at a merge boundary (5.11), an escalated spec's set approval, or a
contradiction involving a proposed record the work relies on; (3) a regression (R3, 7.5).
Proposed records, stale links, unconfirmed edits, not-yet-passing tests, deferred tests,
`full verification pending`, unjudged fidelity, escalation hints and skipped checks are shown
in the summary, the status line and `plumb status`, and never interrupt.

### 6.6 Status line

`plumb statusline` reads `.plumb/session/status.json` and recomputes nothing:

```
plumb | SR 12/14 ok | proposed 2 | stale 1 | tests ok | full pending | ask 0
```

`SR a/b ok` counts confirmed over total requirements; `tests` is `ok`, `failing N`,
`regression N`, `not run` or `?`; `full pending` appears only while it holds; `ask` counts
open trigger questions. Missing or unreadable state prints `plumb | no status yet`.

### 6.7 Skill, slash command, CLAUDE.md block and installer

`plumb hooks install [--launcher path|venv|uv] [--dry-run]` (alias `plumb install
claude-code`) merges, idempotently and preserving every non-plumb entry:

- `.claude/settings.json`: hooks `SessionStart` (`plumb hook session-start`),
  `UserPromptSubmit` (`plumb hook prompt`), `PostToolUse` with matcher
  `Edit|Write|MultiEdit|NotebookEdit` and `"async": true` (`plumb hook post-edit`), `Stop`
  (`plumb hook stop`); `statusLine` (`plumb statusline`); `env.PLUMB_AGENT_SESSION`; the
  `permissions.deny` rules of 5.6. Only the hooks whose modules exist in the installed build
  are registered, so running install again after a new hook lands adds it (plumb's own
  repository runs it at each HOST landing, 14.1). The launcher prefix is `plumb` when it is on `PATH`,
  otherwise `"$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe" -m plumb` (POSIX
  `.venv/bin/python`), otherwise `uv run --no-sync plumb`. plumb entries are recognised by
  the ` plumb hook ` / ` plumb statusline` command suffix.
- `.claude/skills/plumb/SKILL.md`, about 20 lines, TDAD style (names where things are and
  which commands apply, no long procedure): records in `.plumb/`, the test map; state
  read-backs and examples as non-blocking statements and record them with `plumb new`; write
  a `DEC` when two readings fit; relay a confirmation only with the owner's affirming words via
  `plumb relay`, never `plumb approve`; a prompt that does not object is not a confirmation;
  ask only on the three triggers; run `plumb tests run --changed` when the stop hook asks;
  `plumb fidelity <SR>` when a requirement's code changed; grep `.plumb/test_map.txt` before
  editing a file. The skill and the slash command are rendered with the chosen launcher
  prefix, so the commands they name run as written.
- `.claude/commands/plumb.md` (a SHOULD item, plan HS2): `/plumb brief`, `/plumb why <ref>`, `/plumb impact <ref>`,
  running `plumb $ARGUMENTS` with `allowed-tools: Bash(plumb brief:*), Bash(plumb why:*),
  Bash(plumb impact:*)` and summarizing the output.
- A block between `<!-- plumb:begin -->` and `<!-- plumb:end -->` in `CLAUDE.md`: records live
  in `.plumb/`, the test map is `.plumb/test_map.txt`, `plumb brief` for the current intent.
- The git `commit-msg` hook (path from `git rev-parse --git-path hooks`) running
  `plumb trailers check-msg "$1"`, written by BRIDGE's `install_commit_msg_hook` (5.9, 12.2).
  An existing non-plumb hook is left untouched and reported.

`plumb hooks uninstall` removes exactly what install added. `plumb hooks status` reports what
is installed. Both are a SHOULD item (plan HS1).

## 7. Covering-test verification

### 7.1 Test map

`plumb tests map [--rebuild] [--json]` (alias `plumb map`) builds the code-to-test map from:

- `verified_by` links;
- `@pytest.mark.sr("SR-###")` markers, found with an `ast` scan of test files;
- the import closure of each test module: `import` and `from` statements resolved with `ast`
  over `source_dirs` (default `src`, `tests`), relative imports included, transitively;
- test naming: `tests/**/test_<name>.py` covers `src/**/<name>.py` when that file exists.

The map is cached in `.plumb/cache/test_map.json` keyed by file fingerprints; only changed
files are re-parsed. It is written as grep-able text to `.plumb/test_map.txt`:

```
# plumb test map v1 -- generated by `plumb tests map`; grep me
src/plumb/links.py -> tests/core/test_links.py tests/core/test_validate.py
SR-003 -> tests/core/test_links.py::test_pin_drift tests/core/test_links.py::test_crlf_is_not_drift
tests/core/test_links.py <- src/plumb/links.py src/plumb/hashing.py src/plumb/model.py
```

### 7.2 Selection

`plumb tests select [--changed | PATH ...] [--json]` returns the covering tests of a set of
changed paths, in priority order:

1. tests linked by `verified_by` to requirements whose `implemented_by` ends, or whose record
   files, changed;
2. tests that mention a changed path literally (its POSIX path or module name);
3. tests whose import closure reaches a changed file, nearest importers first;
4. tests matched by naming.

Rules (R5):

- **Documentation-only changes select nothing** (`docs/**`, `*.md` outside `.plumb/`).
- **Shared test infrastructure never triggers a per-turn full run.** A change to a path in
  `verify.infra_globs` (default `**/conftest.py`, `pyproject.toml`, `uv.lock`,
  `pytest.ini`, `tox.ini`, `setup.cfg`, plus plumb's own `src/plumb/verify/pytest_plugin.py`
  in plumb's config) adds nothing to the selection and sets `full verification pending`.
- **Unknown coverage gives a bounded sample plus the pending flag.** A changed source file
  with no covering test adds the nearest tests by path (same package directory, then its
  parent), deterministically, at most `verify.sample_size` (10), and sets
  `full verification pending`.
- **The per-turn budget caps the selection.** Tests are taken in priority order until their
  expected duration reaches `verify.fill_fraction` (0.65) of `verify.turn_budget_s` (15 s);
  expected duration comes from earlier evidence, 1 s when unknown, times the **pace scale**
  of the evidence index: each test-run entry carries `timing: {expected_s, elapsed_s}`, a
  finished run of 2 s or more moves the scale halfway to its elapsed/expected ratio, a
  timed-out run raises it at once to that ratio (a lower bound), within [1, 3]. Interpreter
  start-up and collection time are not in the per-test durations; the scale and the fill
  fraction keep a selection well inside the hard limit. The rest are `deferred (budget)`: not run, previous
  evidence state kept, listed at the merge boundary.

`full verification pending` is derived, never stored: it holds while an infrastructure file's
current hash differs from its hash in the latest full-suite `test-run` entry, or no full-suite
entry exists, or a file that triggered the unknown-coverage rule differs from its hash in that
entry. Only `plumb tests run --full` (owner request or merge boundary) satisfies it; no hook
requests it.

### 7.3 Running

`plumb tests run [--changed | --paths P ... | --nodes N ...] [--full] [--budget S] [--json]`
(alias `plumb verify`):

- runs `sys.executable -m pytest -p plumb.verify.pytest_plugin -q <nodes>` from the
  repository root, with `PLUMB_REPORT=<tmp json path>`; never `-n` unless `verify.workers`
  is 1 or 2 and `pytest-xdist` is installed;
- hard wall-clock limit `verify.hard_limit_factor` x budget (1.5 x 15 s); on timeout plumb
  terminates the pytest process it started (and only that one) and records the run as
  `timeout`. The plugin streams every phase, flushed as it completes, to
  `$PLUMB_REPORT.stream`, so the tests that finished (through teardown) before the limit
  are recorded as evidence; the test that was running and the ones after it give none;
- the plugin reports collection errors, per-phase outcomes and the exit status; a setup or
  teardown failure outranks a pass;
- appends one `test-run` entry to `evidence.jsonl` and prints a short result, including any
  regression instruction (7.5) and `deferred N (budget)`.

### 7.4 Evidence and identity

A `test-run` payload:

```json
{"run_id": "20261006T031245Z-1a2b3c4d", "full": false,
 "tree": {"head": "<commit sha>", "head_tree": "<tree sha>", "dirty": "sha256:<changed paths + hashes>"},
 "env": {"env_key": "sha256:...", "identity": "sha256:... | null"},
 "selection": {"changed": [...], "deferred": [...], "sampled": [...], "budget_s": 15},
 "infra": {"pyproject.toml": "sha256:...", "uv.lock": "sha256:..."},
 "nodes": [{"id": "tests/core/test_links.py::test_pin_drift", "outcome": "passed",
            "duration_s": 0.04, "closure": "sha256:...", "test_hash": "sha256:...",
            "attempts": ["failed", "passed"]}],
 "exit_status": 0, "self": "sha256:<checksum of this payload without self>"}
```

- `closure`: hash over the sorted `(path, file hash)` pairs of the test module's import
  closure. `test_hash`: the test node's normalized source hash (5.4).
- `env_key`: sha256 of the LF-normalized `uv.lock` (or `no-lock`), the Python version, the
  platform and the `home` of `pyvenv.cfg`. Cheap; computed every run.
- `identity`: the content-based environment identity (the lock, the base interpreter's bytes,
  each installed distribution's name, version and normalized `RECORD` digest), extracted from
  pi-agent-factory's `environment_content_identity`. It costs about a second, so it is
  computed only when evidence is recorded and cached under `env_key` in
  `.plumb/cache/env_identity.json`. When it cannot be computed it is `null`.
- `infra`: hashes of the infrastructure files; required on full runs.
- If any closure file's hash changes during the run, the run is recorded with
  `"discarded": "inputs changed"` and gives no fresh evidence.

Freshness of one node: its latest `test-run` entry has the same `closure`, `test_hash` and
`env_key` as now. Then the node is `fresh-pass`, `flaky-pass` or `fresh-fail` by its outcome;
otherwise `stale` (with `reuse_miss` naming the part that differed) or `none`. This is the
concept's 1a rule (evidence keyed by node, closure and the cheap `env_key`). The content
`identity` is a SHOULD item (plan VS3): a build without it omits the `identity` key from the
payload; once it is built, freshness also requires a non-null `identity` equal to the current
one, and an unknown identity means no reuse. The reuse index
(`.plumb/cache/evidence_index.json`) is derived from `evidence.jsonl` by byte offset, so a
deleted cache loses nothing.

### 7.5 Failure policy

- **Flaky rerun on the same tree** (a SHOULD item, plan VS2). After a run, failed nodes are
  rerun once, only if the tree identity (`head_tree` plus `dirty`) and `env_key` are
  unchanged. A fail then pass is outcome `flaky` with both attempts recorded; it counts as a
  pass and is reported as flaky.
- **Regression (R3 exactly, F10).** An existing test that previously passed with recorded
  evidence and now fails IS a regression, even if its source changed: a node regresses when
  it now fails and an earlier `test-run` entry recorded the same node id `passed` or `flaky`.
  Edits to the test since that pass do not change this: the `test_hash` is not part of the
  regression rule. When the node's current `test_hash` differs from the one of its last pass
  (or either is unknown), its `NodeEvidence` has `test_changed_since_pass` set and the
  regression instruction carries the note `test source changed since the pass` (6.4), but the
  trigger fires all the same. Only a NEW test that starts red (the test-first step) is exempt:
  a node id with no recorded `passed` or `flaky` entry is `not yet passing`, never a
  regression, and never interrupts. With the SHOULD item VS1, a node that passed with recorded
  evidence and is no longer collected while its file exists is listed as `removed after
  passing` by `plumb tests run` and `plumb status` (shown, never an interruption).
- **Owner waiver** (a SHOULD item, plan VS6). `plumb tests waive --diff-digest <d>
  --reason "..."`, owner only (refused under the marker and by deny rule), appends a `waiver`
  event pinned to that diff digest. It is listed by `validate --merge`; using it in place of
  a full rerun belongs to sub-project 3.
- **Full rerun only when shared test infrastructure changes, and only at the merge boundary**
  (7.2).

## 8. Bridge: importer and judgment

### 8.1 Minimal pi-agent-factory importer

A plan SHOULD item (BRIDGE BS2), built only with time left after the dogfoodable core; the
concept places the importer in sub-project 5 (F13). Without it, `plumb import` reports
`not available in this build` (12.3).

`plumb import pi-agent-factory <source> [--dry-run] [--only SR,FEAT,NC] [--json]` reads the
source repository and never writes to it (files are opened read-only; no git command is run
in it). It writes plumb records into the current repository's `.plumb/` (nothing with
`--dry-run`) and prints a findings report:

- `requirements/SR-*.md` -> requirement: `id`, `title`, `statement`, `domain` kept;
  `acceptance[]` -> examples `{id: AC-n, criterion}`; `upstream` -> `upstream` links;
  `relates_to` -> `relates_to` links; `implemented_by` and `verified_by` entries -> links,
  pinned when their ends exist in the target repository, otherwise reported as findings;
  legacy `checksum:` values verified with the extracted `content_checksum` and reported.
- `docs/features/FEAT-*.md` plus `bundles/*.json`: the union of both memberships becomes the
  feature's `requirements`; every difference between them is a finding.
- `docs/nonconformances/NC-*.md` -> nc, read leniently; `corrected_by` kept verbatim.
- An ID already present in the target is a finding and that record is skipped.

Every imported record is proposed (F11). One `import` event records the source path, its git
`HEAD` (read from `.git/HEAD` files, not by running git there), counts and findings digest.

### 8.2 Judgment backends

`plumb.judgment.get_backend(core, *, hook) -> JudgmentBackend` picks from
`judgment.backend` in `config.yaml`:

- `heuristic` (default): deterministic, no network, no key.
  - `intent_change`: section 6.2 step 3;
  - `drift_triage`: `cosmetic` when the before and after texts are equal after stripping
    comments, docstrings and whitespace (Python: equal `ast.dump`), otherwise `material`;
  - `fidelity`: always `unsure` with tier `escalate-llm`, so the packet goes to the host
    agent (R4).
- `jev`: the JEV adapter (a plan SHOULD item, BRIDGE BS3; without it, `jev` falls back to
  the heuristic with one notice), active only when a key exists in `TYPESAFE_API_KEY` or the
  user store `~/.config/plumb/jev` (never inside the repository). It sends `POST
  {base_url}/v1/systemone` with `Authorization: Bearer <key>` and the pinned body
  `{state, model, questions}` using `urllib.request`, hard timeout 800 ms in hooks
  (`judgment.hook_timeout_ms`), 10 s on the command line, no retries in hooks. Questions are
  `noul` (intent change, drift) or `score` (fidelity, levels `drifts`, `unsure`, `fits`).
  State is assembled from tracked files only, secret-bearing paths excluded, truncated
  deterministically (extracted `assemble_state`). A missing key, timeout or error falls back
  to the heuristic with one logged notice per session.
- `disabled`: every call returns `unsure` with tier `escalate-llm`.
- `fake` (tests only): canned answers.

Cascade routing (extracted `tiers.route`): confidence >= 0.9 accept; 0.5 to 0.9
`escalate-llm`; below 0.5 `escalate-human`, which reaches the owner only if the item also
meets a trigger of 6.5. When the resolved model version differs from
`judgment.jev.validated_against`, `accept` becomes `escalate-llm`. Judgments are advisory:
they order, filter and annotate; they never confirm a record or freshen evidence. Every JEV
judgment is a `judgment` event with its request fingerprint.

**Cascade-to-LLM hook point (interface only).** `LLMCascade.escalate(EscalationRequest)` is
part of the frozen contracts; the default implementation (a SHOULD item, plan BS1),
`HostAgentCascade`, queues the request's one-line instruction in
`.plumb/session/escalations.jsonl`, which the next prompt or stop hook prints for the host
agent. No LLM is called by plumb in sub-project 1.

### 8.3 Fidelity (advisory, no JEV needed)

`plumb fidelity <SR> [--json]` builds a `FidelityPacket`: the requirement's statement and
examples, each `implemented_by` and `verified_by` end at its current content (truncated
deterministically at 4,000 characters per end) with its hash, and the covering tests'
evidence state. It carries no procedure. With JEV enabled, plumb first scores it and prints
the result and tier. The host agent answers with `plumb judge <SR> --verdict
fits|drifts|unsure --note "<one line>"`, which appends a `judgment` event
`{subject, verdict, backend: host-agent, requirement_hash, end_hashes, note}`. A requirement
is `fidelity unjudged` when an `implemented_by` or `verified_by` end changed and no judgment
covers the current hashes; `drifts` and `unsure` are drift signals, never questions on their
own.

## 9. CLI reference

Global options on every command: `--root PATH` (default: walk up from the working directory to
the first directory holding `.plumb/`, else `.git`), `--json` where noted. Exit codes: 0 ok;
1 findings or errors; 2 usage; 3 refused by the guard; 4 merge waits for owner confirmation.

| Command | Lane (tier) | Purpose |
|---|---|---|
| `plumb init` | CORE (MUST) | Create `.plumb/` (dirs, `config.yaml`, `claims.yaml`, `.gitignore`, `.gitattributes`, empty logs); idempotent |
| `plumb new <kind> ...` | CORE (SHOULD) | New record with the next ID (5.8) |
| `plumb show <ID>... [--json]` | CORE (built) | The full read-back (`record_lines`), confirmation state, path and body of each record; what the summary's "not shown" line points to |
| `plumb link <ID> <kind> <target> [--example EX-n]` | CORE (MUST) | Add a pinned link; target `ID` or `path`; `path::Qual.name` (implemented_by) and `path::test_name` (verified_by) with the SHOULD symbol hashing |
| `plumb repin <link-id> \| <ID> \| --all-stale` | CORE (MUST) | Refresh pins, log `repin` |
| `plumb approve <ID>... \| --proposed [--yes]` | CORE (MUST) | Owner approval (refused under the marker) |
| `plumb relay <ID>... --prompt D --quote Q [--revoke]` | CORE (MUST) | Agent-relayed approval or revocation, quote-checked |
| `plumb revoke <ID>...` | CORE (MUST) | Owner revocation |
| `plumb validate [--merge BASE] [--json]` (alias `check`) | CORE (MUST) | 5.10, 5.11 |
| `plumb status [--json]` | CORE (MUST) | Counts, drift, awaiting confirmation, tests (via VerifyAPI when present) |
| `plumb brief [--max-lines N] [--all]` | CORE (MUST) | The session brief text (6.1) |
| `plumb drift [--json]` | CORE (SHOULD) | Drift signals only |
| `plumb why <ID\|path>` | CORE (SHOULD) | Upward chain: path -> SRs -> INT quotes and deciding DECs |
| `plumb log [--stream events\|evidence] [--kind K] [-n N]` | CORE (SHOULD) | Read the logs |
| `plumb trailers check-msg <file>` | BRIDGE (MUST) | `commit-msg` check (5.9) |
| `plumb trailers install-hook` | BRIDGE (MUST) | Write the git `commit-msg` hook (5.9) |
| `plumb claims check [--range R] [--json]` | BRIDGE (MUST) | Claimed vs declared paths (5.9) |
| `plumb tests map\|select\|run` (aliases `map`, `verify`) | VERIFY (MUST) | 7.1 to 7.5 |
| `plumb tests waive` | VERIFY (SHOULD) | Owner waiver (7.5) |
| `plumb impact <ID\|path> [--json]` | VERIFY (SHOULD) | Downstream: records and covering tests with evidence state |
| `plumb hook session-start\|prompt\|post-edit\|stop` | HOST (MUST) | Hook entry points (6.1 to 6.4) |
| `plumb hooks install` (alias `install claude-code`) | HOST (MUST) | 6.7 |
| `plumb hooks uninstall\|status` | HOST (SHOULD) | 6.7 |
| `plumb statusline` | HOST (MUST) | 6.6 |
| `plumb fidelity <SR>`, `plumb judge <SR> --verdict V --note N` | BRIDGE (MUST) | 8.3 |
| `plumb judgment status` | BRIDGE (SHOULD) | Backend in use, key state (never prints the key) |
| `plumb import pi-agent-factory <src> [--dry-run]` | BRIDGE (SHOULD) | 8.1 |

A command whose module is not built reports `plumb: '<command>' is not available in this
build` and exits 2 (12.3); unbuilt commands are listed in `docs/followups.md`.

## 10. Performance design

Budgets, measured on this 2-core Windows machine where a bare `python -c pass` takes about
225 ms:

| Path | Budget (p95, end to end) | How |
|---|---|---|
| `post-edit` hook | async; under 300 ms if run synchronously | stdlib only; append one line |
| `prompt` hook | soft budget 1200 ms (typically 0.45 to 0.6 s warm) | JSON caches; no YAML import on a warm cache; at most 5 records; record tests from the derived cache |
| `stop` hook | soft budget 1400 ms (typically 0.65 to 1.2 s with changes) | one `git status`; hashes only for touched records; map from cache; never runs tests |
| `session-start` hook | soft budget 1400 ms (typically 0.55 to 0.8 s warm) | once per session; tests line from the derived cache |
| `statusline` | under 350 ms | reads one JSON file |
| Every hook | hard limit 1.9 s from the hook's start (watchdog) | the 2 s rule |
| `plumb tests run` in a turn | `verify.turn_budget_s` 15 s, hard limit 22.5 s | in the agent's turn, not in a hook |

The soft budgets sit near the 2-second ceiling on purpose. Measured on this 2-core machine
under load (CPU at 90 to 100 %), the earlier 600/800/900 ms budgets cut the prompt and stop
hooks on most turns, and the cut dropped the read-back first. A soft budget is a ceiling,
not the typical cost.

What a cut keeps (R1, decision 5): each hook computes its intent-translation lines first and
hands them to `HookContext.keep`: the prompt hook its relay line, relevant records with their
examples, intent-change flags, compare line and escalation hint; the stop hook its touched
line, the decisions that matter and the proposed read-back; the session-start hook the
records brief. A budget cut, an internal error or the watchdog prints those kept lines plus
`plumb: check skipped (budget): <step>`. Only evidence detail (covering tests, fidelity, the
tests line) can be lost, and a skipped regression check reads `questions: regressions not
checked (budget)`, never `none`.

Rules every lane follows:

- The `plumb` entry point imports nothing beyond `sys` and the dispatcher until it knows the
  command; `plumb hook` and `plumb statusline` never import `argparse` handlers of other
  commands, YAML, `subprocess` (except the stop hook's single git call) or `ast` unless a
  cache is cold.
- The record index is cached in `.plumb/cache/index.json` (each file's parsed frontmatter)
  keyed by the record file's content digest, so an approval never pins a stale parse; a warm
  hook imports no YAML and re-parses only changed files. Values JSON cannot keep exactly
  (dates) are never cached. Config is cached as JSON keyed by `config.yaml`'s fingerprint.
- Map-derived answers (`full_pending`, the record-to-test map, the session-start tests line)
  are cached in `.plumb/cache/derived.json` under the verify fingerprint: the scanned Python
  files' `(size, mtime_ns)`, the records and their links, the evidence log, the config, the
  environment key and identity, and the shared test infrastructure. A warm session start or
  prompt builds no test map. `platform.machine()` (a WMI query of about 0.2 s on Windows) is
  cached per interpreter in `.plumb/cache/platform.json`.
  These caches are CORE's SHOULD item KS1, the last one its drop order cuts; without them a
  hook parses plumb's few dozen records on each call, and the benchmark measures the cost.
- Log reads are incremental: derived indexes store the byte offset they have read up to.
- No hook walks the repository, scans `site-packages`, or starts one process per file.
- Each hook carries a deadline (`time.monotonic()`); a step that would pass it is skipped and
  reported as `check skipped (budget)`.
- Tests across plumb never run more than `pytest -n 2`; plumb's own suite runs without xdist.

## 11. Configuration (`.plumb/config.yaml`)

All keys optional; defaults shown.

```yaml
source_dirs: [src, tests]
test_dirs: [tests]
verify:
  turn_budget_s: 15
  hard_limit_factor: 1.5
  fill_fraction: 0.65        # the selection's scaled estimate fills this share of the budget
  sample_size: 10
  default_test_s: 1.0
  workers: 0                 # 0 = no -n; at most 2
  flaky_rerun: true
  infra_globs: ["**/conftest.py", pyproject.toml, uv.lock, pytest.ini, tox.ini, setup.cfg]
hooks:
  budget_ms: {session_start: 1400, prompt: 1200, stop: 1400, post_edit: 300}
  brief_lines: 30
  prompt_lines: 20
  summary_proposed_cap: 3    # proposed records shown in full per summary
approve:
  affirmations: [ok, okay, yes, approve, approved, confirm, confirmed, agreed, lgtm, go ahead, sounds good]
judgment:
  backend: heuristic          # heuristic | jev | disabled
  hook_timeout_ms: 800
  jev: {model: jev-latest, validated_against: jev-1.13.0, base_url: "https://api.typesafe.ai",
        thresholds: {accept: 0.9, escalate_llm: 0.5}}
escalation: {max_requirements: 3, max_features: 1, diff_lines: 400, diff_files: 10}
```

`.plumb/claims.yaml`: `require_trailer` (bool, default false), `exempt` (globs, defaults of
5.9 added), `baseline` (list of `{commit, path, nc}`).

## 12. Interface contracts between lanes

These are written and frozen by the CORE lane in phase 1, which runs alone, so they exist on
`main` before the VERIFY, HOST and BRIDGE lanes start. Those lanes build on the real core and
may import CORE modules directly; between themselves they call only the factory functions of
12.2. A lane may add private helpers but must not change a contract; a contract change goes
through the coordinator, who updates this section and `src/plumb/contracts.py` on `main`, and
every lane rebases.

### 12.1 `src/plumb/contracts.py` (data shapes and protocols, no I/O)

```python
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

SCHEMA_VERSION = 1
Hash = str  # "sha256:" + 64 lowercase hex digits

RecordKind = Literal["intent", "requirement", "decision", "feature", "nc"]
KIND_PREFIX: Mapping[str, str] = {"intent": "INT", "requirement": "SR", "decision": "DEC",
                                  "feature": "FEAT", "nc": "NC"}
KIND_DIR: Mapping[str, str] = {"intent": "intents", "requirement": "requirements",
                               "decision": "decisions", "feature": "features", "nc": "ncs"}
ID_RE = r"^(?:(?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})$"
LinkKind = Literal["derives_from", "decides", "upstream", "relates_to", "implemented_by",
                   "verified_by", "corrects", "supersedes"]
Confirmation = Literal["proposed", "confirmed", "unconfirmed-edit"]
ApprovalBy = Literal["owner", "agent-relayed", "import"]
LogStream = Literal["events", "evidence"]


@dataclass(frozen=True)
class Pin:
    source: Hash          # YAML key "from"
    target: Hash          # YAML key "to"


@dataclass(frozen=True)
class Target:
    record: str | None = None   # "SR-004"            (YAML key "to")
    path: str | None = None     # repo-relative POSIX path
    symbol: str | None = None   # "plumb.links:link_states"
    test: str | None = None     # "tests/core/test_links.py::test_pin_drift"


@dataclass(frozen=True)
class Link:
    source: str                 # source record ID
    index: int                  # position in the source's links list
    kind: LinkKind
    target: Target
    example: str | None = None  # "EX-1" / "AC-1"
    pin: Pin | None = None

    @property
    def id(self) -> str:
        return f"{self.source}#{self.index}"


@dataclass(frozen=True)
class Example:
    id: str
    given: str = ""
    when: str = ""
    then: str = ""
    criterion: str = ""         # imported acceptance text


@dataclass(frozen=True)
class Record:
    id: str
    kind: RecordKind
    title: str
    path: str                   # repo-relative POSIX path of the .md file
    fields: Mapping[str, Any]   # frontmatter without id, title, links
    body: str
    links: tuple[Link, ...]
    examples: tuple[Example, ...] = ()
    hash: Hash = ""


@dataclass(frozen=True)
class LinkState:
    link: Link
    state: Literal["current", "stale", "dangling", "unpinned"]
    moved: Literal["source", "target", "both"] | None = None
    current: Pin | None = None  # current hashes, when both ends exist


@dataclass(frozen=True)
class RecordStatus:
    id: str
    confirmation: Confirmation
    approved_by: ApprovalBy | None
    covered: bool                         # requirements only; False otherwise
    uncovered_examples: tuple[str, ...]
    links: tuple[LinkState, ...]
    superseded_by: str | None = None


@dataclass(frozen=True)
class LogEntry:
    stream: LogStream
    kind: str
    at: str                               # UTC, "YYYY-MM-DDTHH:MM:SSZ"
    marker: str                           # PLUMB_AGENT_SESSION value or "none"
    payload: Mapping[str, Any]
    prev: Hash | None
    digest: Hash
    offset: int = -1                      # byte offset of the line, when read


SelectionReason = Literal["verified_by", "literal", "import", "naming", "sample"]
EvidenceState = Literal["fresh-pass", "flaky-pass", "fresh-fail", "stale", "none"]


@dataclass(frozen=True)
class Selection:
    changed: tuple[str, ...]
    nodes: tuple[str, ...]                # priority order, within budget
    reasons: Mapping[str, SelectionReason]
    deferred: tuple[str, ...] = ()
    sampled: tuple[str, ...] = ()
    unknown_coverage: tuple[str, ...] = ()
    infra_changed: tuple[str, ...] = ()
    doc_only: bool = False
    expected_s: float = 0.0


@dataclass(frozen=True)
class NodeEvidence:
    node_id: str
    state: EvidenceState
    regression: bool = False              # failing now, passed or flaky earlier (7.5)
    test_changed_since_pass: bool = False # regression note only; never clears `regression`
    last_run: str | None = None           # run_id
    reuse_miss: Literal["closure", "test", "env", "identity"] | None = None


@dataclass(frozen=True)
class FullPending:
    pending: bool
    reasons: tuple[str, ...] = ()


JudgmentAction = Literal["intent-change", "drift-triage", "fidelity"]
Tier = Literal["accept", "escalate-llm", "escalate-human"]


@dataclass(frozen=True)
class Judgment:
    action: JudgmentAction
    subject: str                          # record ID or link ID
    verdict: str                          # change|no-change, cosmetic|material, fits|drifts|unsure
    confidence: float
    tier: Tier
    backend: str                          # heuristic | jev:<version> | host-agent | disabled | fake
    fingerprint: Hash
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FidelityPacket:
    requirement: str
    requirement_hash: Hash
    statement: str
    examples: tuple[Example, ...]
    ends: tuple[Mapping[str, Any], ...]   # {link, kind, path, symbol|test, hash, content, truncated}
    evidence: tuple[Mapping[str, Any], ...]  # {node_id, state}
    fingerprint: Hash


@dataclass(frozen=True)
class EscalationRequest:
    judgment: Judgment
    instruction: str                      # one line for the host agent
    packet: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StatusSnapshot:
    at: str
    requirements_total: int
    requirements_confirmed: int
    proposed: int                         # all kinds, proposed or unconfirmed edit
    stale_links: int
    dangling_links: int
    tests: Literal["ok", "failing", "regression", "not-run", "unknown"]
    failing: tuple[str, ...] = ()
    regressions: tuple[str, ...] = ()
    deferred: int = 0
    full_pending: bool = False
    full_pending_reasons: tuple[str, ...] = ()
    fidelity_unjudged: tuple[str, ...] = ()
    ask: int = 0
    skipped: str | None = None            # "budget" | "error" | None


@runtime_checkable
class CoreAPI(Protocol):
    root: Path
    def index(self) -> Mapping[str, Record]: ...
    def status(self, ids: Iterable[str] | None = None) -> Mapping[str, RecordStatus]: ...
    def link_states(self, ids: Iterable[str] | None = None) -> Sequence[LinkState]: ...
    def records_for_paths(self, paths: Iterable[str]) -> Mapping[str, tuple[str, ...]]: ...
    # maps each given repo-relative path to the IDs of the records it is a link end of
    # (or whose record file it is)
    def relevant(self, text: str, limit: int = 5) -> Sequence[tuple[str, float]]: ...
    def brief_lines(self, max_lines: int = 30) -> list[str]: ...
    def hash_target(self, target: Target) -> Hash | None: ...
    def write_record(self, kind: RecordKind, fields: Mapping[str, Any], body: str = "",
                     *, record_id: str | None = None) -> Record: ...
    def add_link(self, source: str, kind: LinkKind, target: Target,
                 example: str | None = None) -> Link: ...
    def log_append(self, stream: LogStream, kind: str,
                   payload: Mapping[str, Any]) -> LogEntry: ...
    def log_read(self, stream: LogStream, kinds: Iterable[str] | None = None,
                 since_offset: int = 0) -> Iterator[LogEntry]: ...


@runtime_checkable
class VerifyAPI(Protocol):
    def select(self, changed: Sequence[str], *,
               budget_s: float | None = None) -> Selection: ...
    def evidence(self, nodes: Iterable[str]) -> Mapping[str, NodeEvidence]: ...
    def full_pending(self) -> FullPending: ...
    def tests_for(self, refs: Iterable[str]) -> Mapping[str, tuple[str, ...]]: ...  # ID or path


@runtime_checkable
class JudgmentBackend(Protocol):
    name: str
    def intent_change(self, prompt: str, records: Sequence[Record]) -> Sequence[Judgment]: ...
    def drift_triage(self, states: Sequence[LinkState],
                     texts: Mapping[str, tuple[str, str]]) -> Sequence[Judgment]: ...
    def fidelity(self, packet: FidelityPacket) -> Judgment: ...


@runtime_checkable
class LLMCascade(Protocol):
    def escalate(self, request: EscalationRequest) -> None: ...
```

### 12.2 Factory functions (one per lane, imported lazily by consumers)

| Function | Module (owner) | Signature |
|---|---|---|
| `open_core` | `plumb.api` (CORE) | `def open_core(root: Path) -> CoreAPI` |
| `merge_check` | `plumb.merge` (CORE) | `def merge_check(core: CoreAPI, base: str, *, as_json: bool) -> int` (exit code of 5.11) |
| `open_verify` | `plumb.verify` (VERIFY) | `def open_verify(core: CoreAPI) -> VerifyAPI` |
| `install_commit_msg_hook` | `plumb.claims` (BRIDGE) | `def install_commit_msg_hook(root: Path, interpreter: str) -> Path` |
| `get_backend` | `plumb.judgment` (BRIDGE) | `def get_backend(core: CoreAPI, *, hook: bool) -> JudgmentBackend` |
| `get_cascade` | `plumb.judgment` (BRIDGE, SHOULD) | `def get_cascade(core: CoreAPI) -> LLMCascade` |
| `build_packet` | `plumb.judgment.fidelity` (BRIDGE) | `def build_packet(core: CoreAPI, verify: VerifyAPI \| None, sr: str) -> FidelityPacket` |
| `unjudged` | `plumb.judgment.fidelity` (BRIDGE) | `def unjudged(core: CoreAPI, ids: Iterable[str] \| None = None) -> tuple[str, ...]` (requirements whose fidelity is unjudged, `drifts` or `unsure`, 8.3) |

A consumer whose provider is missing (import error) degrades: HOST prints the line
`plumb: <part> unavailable` and continues (the prompt hook prints `plumb: intent check
unavailable` without `get_backend`); `validate --merge` and `status` print
`verification: unavailable` (or `fidelity: unavailable`); `hooks install` without
`plumb.claims` skips the `commit-msg` hook with a notice; without `get_cascade`, escalations
are not queued.

### 12.3 CLI dispatcher contract (`src/plumb/cli.py`, CORE, phase 1)

```python
ROUTES: dict[str, str] = {
    # CORE
    "init": "plumb.commands", "new": "plumb.commands", "show": "plumb.commands",
    "link": "plumb.commands", "repin": "plumb.commands", "validate": "plumb.commands",
    "check": "plumb.commands", "status": "plumb.commands", "drift": "plumb.commands",
    "brief": "plumb.commands", "why": "plumb.commands", "log": "plumb.commands",
    "approve": "plumb.commands", "relay": "plumb.commands", "revoke": "plumb.commands",
    # VERIFY
    "tests": "plumb.verify.cli", "map": "plumb.verify.cli", "verify": "plumb.verify.cli",
    "impact": "plumb.verify.cli",
    # HOST
    "hook": "plumb.hosts.claude_code.cli", "hooks": "plumb.hosts.claude_code.cli",
    "install": "plumb.hosts.claude_code.cli", "statusline": "plumb.hosts.claude_code.cli",
    # BRIDGE (trailers and claims, judgment, importer)
    "trailers": "plumb.claims", "claims": "plumb.claims",
    "import": "plumb.importer.cli", "fidelity": "plumb.judgment.cli",
    "judge": "plumb.judgment.cli", "judgment": "plumb.judgment.cli",
}

def main(argv: Sequence[str] | None = None) -> int:
    """`plumb <command> ...`: import ROUTES[command] lazily and return its run()."""
```

Each routed module exposes `def run(command: str, argv: list[str]) -> int`, where `argv`
excludes the command token. Shared argument helpers live in `plumb/cliutil.py` (CORE,
phase 1): `add_common(parser)` (adds `--root`, `--json`), `resolve_root(arg: str | None) ->
Path`, `emit(obj: Any, as_json: bool) -> None`. A missing module prints
`plumb: '<command>' is not available in this build` and returns 2.

### 12.4 Shared primitives (CORE, phase 1, frozen after the CORE merge)

- `plumb/paths.py`: `find_root(start: Path) -> Path`; `PlumbPaths(root)` with attributes
  `plumb, config, claims, log_events, log_evidence, cache, session, test_map_txt,
  test_map_json, index_cache, hash_cache, evidence_index, env_identity, lock, prompts,
  status, stated, escalations, errors` and `session_dir(session_id) -> Path`
  (`touched.txt`, `turn.json` inside).
- `plumb/normalize.py`: `normalize_text(s: str) -> str` (5.4 body rules),
  `canonical_json(obj: Any) -> bytes`, `sha256_bytes(b: bytes) -> Hash`,
  `sha256_text(s: str) -> Hash` (of `normalize_text(s)`), `file_digest(path: Path) -> Hash`
  (normalized text, raw bytes if not UTF-8), `utc_now() -> str`.
- `plumb/config.py`: `@dataclass(frozen=True) class Config` mirroring section 11 (nested
  frozen dataclasses `VerifyConfig`, `HooksConfig`, `ApproveConfig`, `JudgmentConfig`,
  `EscalationConfig`) and `load_config(root: Path) -> Config` (JSON cache keyed by
  `config.yaml`'s fingerprint; YAML imported only on a cache miss; defaults when absent).
- `plumb/log.py` (5.7): `append(paths: PlumbPaths, stream: LogStream, kind: str,
  payload: Mapping[str, Any]) -> LogEntry` (lock, `prev`, `digest`, one `write`),
  `read(paths, stream, kinds=None, since_offset=0) -> Iterator[LogEntry]`,
  `verify_chain(paths, stream) -> list[str]` (problems found). CoreAPI's `log_append` and
  `log_read` delegate to it, so every lane writes the same format.
- `plumb/text.py`: `terms(s: str) -> frozenset[str]` (lowercase words of 3 or more letters,
  minus a fixed stopword list), `overlap(a: frozenset[str], b: frozenset[str]) -> float`
  (`|a & b| / sqrt(|b|)`, 0 when empty), `CHANGE_WORDS: frozenset[str]`.
- `tests/conftest.py`: fixtures `repo` (a temp git repository with `.plumb/` dirs,
  `git init`, user config, one commit), `write_record(repo, text)`, `hook_input(event,
  **fields) -> str` (Claude Code stdin JSON).
- Fakes: the later lanes use the real core. HOST keeps `FakeVerify`, `FakeBackend` and
  `FakeCascade` (in-memory implementations of the protocols) in `tests/host/fakes.py`;
  BRIDGE passes `verify=None` or a local fake. The integration phase checks `open_core`,
  `open_verify`, `get_backend`, `get_cascade` (when built) and HOST's fakes against the
  protocols in `tests/integration/test_conformance.py`.

### 12.5 File-format contracts between lanes

| File | Writer | Readers | Shape |
|---|---|---|---|
| `.plumb/log/events.jsonl`, `evidence.jsonl` | `plumb/log.py` (CORE), called through CoreAPI `log_append` by every lane | all | 5.7; `approval` and `revocation` payloads 5.6; `test-run` payload 7.4; `judgment` payload `{subject, action, verdict, confidence, tier, backend, fingerprint, requirement_hash?, end_hashes?, note?}` |
| `.plumb/session/prompts.jsonl` | HOST prompt hook | CORE `relay` | one line `{"digest", "session", "at", "text"}` |
| `.plumb/session/stated.json` | HOST stop hook | CORE `relay`, HOST prompt hook | `{"at", "session", "reply_after_prompt": digest\|null, "records": [{"id", "hash", "shown"}]}` |
| `.plumb/session/status.json` | HOST (stop, session-start) | HOST `statusline` | `StatusSnapshot` as JSON plus `"v": 1` |
| `.plumb/session/<sid>/touched.txt` | HOST post-edit | HOST stop, VERIFY `--changed` | one repository-relative POSIX path per line |
| `.plumb/session/<sid>/turn.json` | HOST prompt hook | HOST stop | `{"turn_start": epoch_seconds, "prompt_digest", "asked": {record_id: hash}}` |
| `.plumb/session/escalations.jsonl` | BRIDGE `HostAgentCascade` (SHOULD) | HOST prompt and stop hooks (SHOULD) | `{"at", "subject", "instruction"}` |
| `.plumb/cache/test_map.json`, `.plumb/test_map.txt` | VERIFY | VERIFY, HOST (path only) | 7.1 |
| `.plumb/cache/index.json`, `hashes.json` | CORE | CORE | private to CORE |

`plumb tests run --changed` takes changed paths from `git status --porcelain` plus the
touched lists of every session directory.

## 13. Extraction from pi-agent-factory (read-only source)

Source: `C:/coding/pi-agent-factory/.worktrees/nc-t120/src`. Copy, then simplify; port the
listed tests where they exist; no `factory.*`, `coherence.*` or `substrate.*` import remains.

| plumb module | Extracted from | Keep | Drop |
|---|---|---|---|
| `plumb/model.py`, `store.py` | `coherence/register/register.py` | frontmatter parse, binding shapes | `python-frontmatter` dependency, consent fields |
| `plumb/claims.py` | `coherence/register/claims.py` (+ `tests/unit/coherence/register/test_claims.py`) | `parse_sr_trailer`, `glob_match`, `exempting_glob`, baseline entries, commit check | strict policy diffing, claim corrections |
| `plumb/links.py` | `coherence/register/relations.py` (+ `test_relations.py`) | path confinement, symbol and test resolution | `CodeIndex` dependency (use `ast` directly) |
| `plumb/normalize.py` | `substrate/freshness/fingerprint.py` | `sha256_bytes` | dependency fingerprints |
| `plumb/verify/imports.py` | `substrate/codemap/imports.py` (+ `tests/unit/substrate/test_codemap_imports.py`) | `_import_edges`, `_resolve_import`, `_closure_walk`, `transitive_imports` | overlap and symbol reachability |
| `plumb/verify/markers.py` | `coherence/register/markers.py` (+ `test_register_markers.py`) | `collect_markers` | |
| `plumb/verify/select.py`, `policy.py` | `coherence/integration/failure_policy.py` (+ `test_integration_failure_policy.py`) | `InfrastructureMatcher`, `is_documentation`, `covering_test_modules`, `diff_digest`, same-tree verdict, `OwnerWaiver` shape | suite attempts across integration transactions |
| `plumb/verify/pytest_plugin.py` | `coherence/execution/pytest_evidence_plugin.py` (+ `test_pytest_evidence_plugin.py`) | per-phase outcomes, collection report, exit status | xdist node plumbing beyond `-n 2`, bound expectations |
| `plumb/verify/envid.py` | `coherence/integration/evidence.py` (`environment_content_identity` and helpers) | lock, base interpreter, distributions | gate environment normalization |
| `plumb/judgment/*` | `substrate/judgment/{model,client,tiers,config,state}.py` (+ `tests/unit/substrate/judgment/*`) | `JudgmentQuestion`/`Answer`/`Record`, `make_record`/`seal`, `route`, key resolution, `assemble_state` | interactive key onboarding prompts, run markers |
| `plumb/importer/pi_factory.py` | `coherence/register/register.py` (`parse_requirement`, `content_checksum`) | SR parsing and legacy checksum | |

The JEV live client is new: pi-agent-factory has only disabled and fake clients. Its wire
shapes come from `C:/coding/pi-agent-factory/docs/coherence/records/2026-09-28-jev-vendor-verification.md`
("Request and response shapes (pinned)").

## 14. Dogfooding and definition of done

### 14.1 Dogfooding: core first, bootstrap, then each part as it lands

plumb is used on plumb as early as possible (D6; concept 11, slice 1a). The plan
(`docs/plans/sp1-plan.md`, sections 1, 4 and 11) gives the conditions, steps, gates and drop
rules, and protects the dogfooding from every cut.

- **CORE alone first.** The CORE lane builds only what plumb's own records need: the record
  model with parse and write, the normalized content hash, hash-pinned links and staleness,
  pinned approvals including agent-relayed approvals with the owner's quote and the prompt
  digest, the append-only event log, `plumb validate` including `--merge` (R1 at the merge
  boundary), `plumb brief` and `plumb status`, plus `plumb init` and the frozen contracts.
- **Dogfood bootstrap**, right after the CORE merge and before the other lanes start:
  `plumb init` in `C:/coding/plumb` (`.plumb/config.yaml` adds
  `src/plumb/verify/pytest_plugin.py` to `verify.infra_globs`); plumb's own records from
  `docs/concept.md` and the owner intent brief: `INT` records with the owner's verbatim
  quotes, `SR-001` onward each with given/when/then examples, `FEAT-001`, and the `DEC`
  records that matter (F2, F4, F6); every link pinned; `plumb validate` without errors;
  `plumb validate --merge <first commit>` exiting 4 with the records awaiting the owner. From
  the bootstrap commit on, every commit carries an `SR:` trailer.
- **VERIFY, HOST and BRIDGE in parallel**, on top of the core and of plumb's own records. Each
  lane agent reads `plumb brief` and `plumb status` before it starts, marks its tests with
  `@pytest.mark.sr` so plumb's test map covers them, and runs `plumb validate` before each
  hand-over.
- **Each part set up in plumb's repository as it lands:** when BRIDGE's trailer check lands,
  the `commit-msg` hook is installed and `require_trailer: true` is set, so every later commit
  and merge is checked; when HOST lands (in two merge points), `plumb hooks install` writes
  the hooks into `C:/coding/plumb/.claude/settings.json` at once, and a driven loop check
  calls the real hook entry points on plumb's own repository; when VERIFY lands,
  `plumb tests map` runs on plumb's tests and every later merge runs `plumb tests run --full`,
  so evidence is recorded and R3 regressions between merges are reported.
- **Known limitation, stated honestly.** Hooks in `C:/coding/plumb/.claude/settings.json`
  fire only for a Claude Code session whose project directory is `C:/coding/plumb`. The build
  agents of this overnight run are subagents of a session rooted elsewhere, so they do not run
  under plumb's own hooks: no build agent sees plumb's session brief, per-prompt context,
  intent-change flag, covering-test request or end-of-turn summary in its own turns. The
  driven loop check proves the hooks work on plumb's repository; it is not an interactive
  session. **Full interactive dogfooding starts when the owner opens Claude Code in
  `C:/coding/plumb`.** The handoff says so in its first section.

All records stay **proposed**: no agent writes an approval, because no owner prompt in these
sessions affirmed them (R2). The morning handoff gives the owner one line to confirm them
(`plumb approve --proposed`, or "ok" in a session, relayed).

### 14.2 Definition of done

1. `uv run pytest` passes on `main` (all lanes plus integration tests) and `uv run ruff check
   src tests` is clean.
2. Every command of section 9 that was built exists and has at least one test; `plumb --help`
   lists them. Unbuilt SHOULD commands are listed in `docs/followups.md`.
3. The integration test of the full loop passes: `init`, records, `link`, session-start,
   prompt, post-edit, stop (blocks once asking for the covering tests), `tests run --changed`
   (appends evidence), stop again (summary, no block), `statusline`.
4. Guard tests pass: `plumb approve` refuses under the marker; `plumb relay` refuses a quote
   not in the prompt, a quote without an affirmation, and a record outside the stated set, and
   records the owner's quote and the prompt digest when it accepts; the installer writes the
   deny rules and the marker.
5. `plumb validate --merge <base>` exits 4 on a range touching an unconfirmed requirement and
   0 once it is approved.
6. The regression rule is R3 exactly: tests show that an existing test that passed with
   recorded evidence and now fails is a regression even after its source changed, and that
   only a new test that starts red is exempt and never interrupts.
7. Latency: `scripts/bench_hooks.py` on plumb's own repository reports p95 prompt + stop under
   1.5 s and each hook within its section 10 budget; any miss is recorded in
   `docs/followups.md`.
8. If the importer (SHOULD) was built: `plumb import pi-agent-factory
   C:/coding/pi-agent-factory --dry-run` runs read-only against the real register and reports
   findings; the unit tests import fixture copies of real SR, FEAT, bundle and NC files.
9. Without a key the judgment backend is `heuristic`; if the JEV adapter (SHOULD) was built,
   its tests pass against a local stub HTTP server; no test calls the network.
10. Dogfood done (14.1): the bootstrap passed its gate; plumb's own records validate with no
    errors (warnings for proposed records are expected); the `commit-msg` hook is installed
    and has checked every commit since the trailer check landed; every commit since the
    bootstrap carries an `SR:` trailer and `plumb claims check` accepts that range (or each
    undeclared path is recorded); plumb's hooks are installed in
    `C:/coding/plumb/.claude/settings.json` and the driven loop check passed; plumb's test
    map and recorded evidence exist; `plumb validate --merge <first commit>` exits 4 listing
    the records awaiting the owner.
11. `docs/fork-plan.md` exists on `main` (D9, D10). A later workflow phase writes it, outside
    the lanes; the handoff links it and names its first owner decision.
12. Every unfinished item is recorded in `docs/followups.md` with its state; medium and low
    review findings are recorded there; no HIGH finding is open.
13. The morning minimum (plan 11) is on `main` by the clock rule, 2026-10-06 07:15 local, and
    the handoff is committed by 07:45, before the owner's deadline of about 08:00. The handoff
    states the known limitation of 14.1 first, then any part of the minimum still missing, and
    every KEEP-list item not built, named against the owner's KEEP list.

## 15. Out of scope for sub-project 1

- Escalation set approvals, `plumb decline`, and the full escalation trigger set (sub-project
  2); only the SHOULD hint of 6.2 step 5 is here.
- The merge-boundary full-suite run, evidence promotion, waivers in place of full reruns, the
  claims audit as a gate and a CI entry point (sub-project 3).
- Codex, Pi, Hermes adapters and an MCP server (sub-project 4).
- `by: import` approvals, a complete import and pi-agent-factory's migration (sub-project 5).
  The fork plan for these steps (decisions D9 and D10) is `docs/fork-plan.md`, written by a
  later workflow phase of the overnight run and required by the definition of done (14.2);
  its steps after sub-project 1 run outside this sub-project's lanes.
- Any run state machine, phases, consent phrases, manifests, handoff hashes, review swarms or
  governed execution (concept non-goals).
