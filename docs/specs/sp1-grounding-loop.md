# Sub-project 1 spec: core, grounding loop and covering-test verification

Status: implementation spec, written 2026-10-06. The owner does not review it (decision
D11: "I wont review the concept spec or any plan. use agents that verify that my intent based
on that conversation is respected."); independent verifier agents check it against the owner
intent brief and its rulings R1 to R7. When this spec, `docs/concept.md` and the owner's
quoted words disagree, the quotes and rulings win, then the concept, then this spec. Section
3 lists every place where this spec refines the concept, with the reason.

Companion documents: `docs/concept.md` (the reference concept), `docs/plans/sp1-plan.md`
(lanes, tasks, tests, schedule) and `docs/followups.md` (medium and low findings).

## 1. Outcome

At the end of sub-project 1, plumb is a working tool that develops itself:

- plumb's own intent lives in `.plumb/` as `INT`, `SR`, `DEC` and `FEAT` records derived from
  `docs/concept.md`, each with a content hash, pinned links and a derived state;
- every commit from the contract phase on carries an `SR:` trailer, checked by a `commit-msg`
  hook from dogfood checkpoint D1 on (14.1);
- Claude Code sessions on `C:/coding/plumb` run plumb's hooks: a short intent brief at session
  start, the relevant requirements and tests on every prompt with an intent-change flag, edit
  tracking, and an end-of-turn alignment summary that gets the covering tests run within a
  time budget and asks the owner only on the three agreed triggers;
- `plumb tests run` runs the covering tests of a change and appends identity-pinned evidence;
- `plumb validate --merge <base>` refuses a merge whose touched requirements are not all
  confirmed by the owner's own words;
- a judgment backend interface carries a heuristic default; with time left (plan stretch
  items), a read-only importer reads pi-agent-factory's SR, FEAT, bundle and NC records into
  plumb records and an optional JEV adapter plugs into the interface.

plumb is used on plumb from the first hour, following concept section 11, slice 1a: plumb's
own records are written while the lanes start, every commit carries an `SR:` trailer, the
trailer check turns on as soon as the record and approval core merges, and each hook is
installed in plumb's own repository as soon as it lands (14.1). From then on, the build's own
work on `main` runs through those hooks as loop steps, with evidence that the loop ran on each
one (14.1). The work is about 6 hours of agent time: a contract phase, four parallel lanes with
dogfood checkpoints, an integration phase, a short dogfood completion and a review of the
dogfooded result (`docs/plans/sp1-plan.md`). It is time-boxed to the owner's deadline, an
absolute time: 2026-10-06 08:00 local, the earliest reading of 9 hours from the owner's
request on the evening of 2026-10-05 (the repository was initialized at 23:25 +11:00, shortly
after it).

## 2. Owner intent served

| Owner decision or ruling | Where this spec serves it |
|---|---|
| Purpose: "make vibe coding grounded on the projects artifacts in an efficient, reliable and trustable manner" | Records (5), grounding loop (6), evidence (7), latency (10) |
| "a lighter, more elegant and interactive way to leverage coherence" | No run state machine, no phases; four hooks and a status line (6); non-goals (15) |
| D1 "A / B": standalone, pi-agent-factory can migrate | Installable in any repository (`plumb init`, `plumb hooks install`); importer (8.1, a plan stretch item) |
| D2 "C": incremental capture by default, escalation suggested | Records written as work happens (5.8); escalation hint in the prompt hook (6.2, stretch item) |
| Intent translation: read-back, confirmed examples, explicit decisions, traceable links, drift signals | `INT` read-backs, `SR` examples, `DEC` records, pinned links, drift (5, 6) |
| D3 "B": host-neutral core, Claude Code first, reuse by extraction | CLI and library core; `plumb/hosts/claude_code` adapter (6); extraction table (13) |
| D4 "B" and the KEEP list ("Keep list looks fine") | Hashes and staleness (5.4, 5.5), pinned approvals (5.6), append-only logs (5.7), `SR:` trailers and claims (5.9), relation validation (5.10), NCs (5.2), features (5.2), identity-pinned evidence and failure policy (7.4, 7.5), advisory fidelity (8.3) |
| D5 "A": background, three triggers only | Stop hook summary and the exhaustive trigger list (6.4, 6.5) |
| D6: dogfood "as soon as possible and build with it" | Dogfood checkpoints D0 to D3 (14.1): own records from the first hour, `SR:` trailers on every commit from the contract phase, the trailer check on from D1, each hook installed in plumb's repository as it lands, and from then on the build's own work on `main` run as loop steps through those hooks, with evidence that the loop ran (14.1; plan 4.5); dogfooding is never cut for review or later items (plan 12) |
| D7: reuse SR, FEAT, NC formats and IDs | Same ID formats and `SR:` trailers; importer (8.1, a plan stretch item) |
| D8: JEV optional, cascade, works without it | `JudgmentBackend` with heuristic default and JEV adapter (8.2) |
| D9: pi-agent-factory into maintenance mode, fork plan | Out of scope here: the fork plan is a separate document (15) |
| D10, D11: concept plus plans; owner does not review; implementation by the morning | This spec and the plan; verifier agents; a 6-hour schedule anchored to the owner's absolute deadline (2026-10-06 08:00 local; clock rule at 07:15, handoff by 07:45), must items of at most 150 min per lane, and a drop order that protects the dogfoodable core (plan 1, 6, 12) |
| D12: the name plumb | Package, CLI and `.plumb/` directory |
| R1: read-back and examples non-blocking; touched requirements confirmed at merge | `proposed` lines in the summary (6.4); `validate --merge` (5.11) |
| R2: no no-objection approval; `agent-relayed` with verbatim quote and prompt digest; honest trust model | `plumb relay` checks (5.6); merge-boundary approval list (5.11); trust model (5.6) |
| R3: regression = previously passed with recorded evidence | Regression rule (7.5) |
| R4: `plumb fidelity <SR>` packet for the host agent, JEV only accelerates | Fidelity (8.3) |
| R5: shared test infrastructure sets `full verification pending`; bounded sample on unknown coverage | Selection rules (7.2) |

## 3. Refinements of the concept, with reasons

Each refinement keeps the concept's guarantee and changes only its mechanism. Each becomes a
`DEC` record at dogfood checkpoint D0, so the owner sees it among the proposed records.

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
| F10 | Regression: a test that previously passed now fails (6.6) | Same, and only when the test's own source hash is unchanged since that pass | A rewritten test that starts red is a test-first step (R3), not a regression |
| F11 | Imported records with an upstream approval get `by: import` (10) | The minimal importer imports every record as proposed; `by: import` approvals wait for the full importer (sub-project 5) | Never manufactures a confirmation; safe lower bound of the concept rule |
| F12 | Links live in their source record (4.5) | Unchanged; "link" is a first-class data type (`Link`, `LinkState`) and command (`plumb link`), not a separate file | A link file per link would double the files a hook reads and split a requirement from its evidence chain |
| F13 | Slice 1a is built in the listed order, one step after another; plumb's own `SR` records and `SR:` trailers start at step 3, and each hook is installed in plumb's repository as soon as it lands (11) | Slice 1a is built by four parallel lanes, with dogfood checkpoints (14.1). plumb's own records are written at D0, while the lanes start, which is earlier than step 3, and every commit from the contract phase on carries an `SR:` trailer. The `commit-msg` check turns on at D1, as soon as the record core and the approval, trailer and merge-boundary items (concept steps 1, 2 and 4) merge. Each hook is installed in plumb's repository at D2, as soon as its lane merge point lands, and from then on the coordinator's work on `main` runs as loop steps through the installed hooks (a headless Claude Code session rooted in plumb's repository, or the real hook entry points driven around the work item), because the building workflow's own sessions are not rooted in plumb's repository and would not fire the hooks. The map and verification join at D3. Dogfooding comes before review. The JEV live client and the minimal importer are stretch items here (the concept puts them in sub-projects 2 and 5). The judgment interface with its heuristic backend moves up from 1b into the must items, because the prompt hook's intent-change flag (trigger 1) uses it; the owner waiver (concept 1b) is a stretch item, since using it in place of a full rerun belongs to sub-project 3 (15) | The 9-hour box (D11) needs parallel lanes. The checkpoints keep "as soon as possible and build with it" (D6): the records and trailers start earlier than in the concept, and no checkpoint waits for a whole lane or for review |

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

Directories and globs cannot be link ends; line numbers are never identity. A symbol or test
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
     agreed, lgtm, go ahead, sounds good);
   - every approved record is in the stated set (`.plumb/session/stated.json`, written by the
     stop hook of the reply just before that prompt) or is named by ID in the quote.

   A failed check exits 3 and writes nothing. On success plumb appends a `prompt` event
   `{digest, session, at}` (if that digest is not yet in `events.jsonl`; `at` is the time
   the prompt hook recorded) and then the approval with `prompt_digest`, `quote`,
   `quote_digest`, `affirmation` and `stated_set`.

There is no other way to confirm. Silence, or a prompt that neither affirms nor objects,
confirms nothing (R2). `plumb revoke <ID>` (owner) and `plumb relay --revoke <ID> --prompt
--quote` (relayed; the quote need not affirm) append a `revocation` event; the record returns
to proposed or unconfirmed edit.

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
  `claims.require_trailer: true` in `.plumb/claims.yaml` (plumb's own repository sets it at
  dogfood checkpoint D1). In a checkout with no `.plumb/` directory (a repository that has not
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

Exit 0 without errors, 1 with errors. `plumb drift` prints only the drift signals (stale and
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
2. **Approvals in the range, for a glance.** Every approval and revocation event added in the
   range, owner and agent-relayed, with its record and quote.
3. **Fidelity, advisory.** Touched requirements with no judgment for their current hashes, or
   whose latest judgment is `drifts` or `unsure`, each with its `plumb fidelity` command.
4. **Verification state.** `full verification pending` with its reasons, tests deferred by
   the per-turn budget, and touched requirements that are confirmed but not covered. If the
   verify lane is not importable, the line says `verification: unavailable`.
5. **Log integrity** against `<base>` (5.7).

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
5. Escalation hint (stretch item, plan lane HOST): when the matched records span more than
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
   trigger-2 instruction of this stop).
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
     read-back, and ask how to proceed.` A regression found by the agent's own
     `plumb tests run` is printed by that command with the same instruction.
5. Otherwise answer `{"systemMessage": "<summary>"}`, at most five lines plus at most three
   `proposed` lines and a `+N more (plumb status)` line:

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
  are registered, so running install again after a new hook lands adds it (dogfood
  checkpoint D2, 14.1). The launcher prefix is `plumb` when it is on `PATH`,
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
- `.claude/commands/plumb.md`: `/plumb brief`, `/plumb why <ref>`, `/plumb impact <ref>`,
  running `plumb $ARGUMENTS` with `allowed-tools: Bash(plumb brief:*), Bash(plumb why:*),
  Bash(plumb impact:*)` and summarizing the output.
- A block between `<!-- plumb:begin -->` and `<!-- plumb:end -->` in `CLAUDE.md`: records live
  in `.plumb/`, the test map is `.plumb/test_map.txt`, `plumb brief` for the current intent.
- The git `commit-msg` hook (path from `git rev-parse --git-path hooks`) running
  `plumb trailers check-msg "$1"`, written by TRUST's `install_commit_msg_hook` (5.9, 12.2).
  An existing non-plumb hook is left untouched and reported.

`plumb hooks uninstall` removes exactly what install added. `plumb hooks status` reports what
is installed.

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
  expected duration reaches `verify.turn_budget_s` (15 s); expected duration comes from
  earlier evidence, 1 s when unknown. The rest are `deferred (budget)`: not run, previous
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
  `timeout`;
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
`identity` is a 1b item (plan V9): a build without it omits the `identity` key from the
payload; once it is built, freshness also requires a non-null `identity` equal to the current
one, and an unknown identity means no reuse. The reuse index
(`.plumb/cache/evidence_index.json`) is derived from `evidence.jsonl` by byte offset, so a
deleted cache loses nothing.

### 7.5 Failure policy

- **Flaky rerun on the same tree** (plan VERIFY 1b item). After a run, failed nodes are
  rerun once, only if the tree identity (`head_tree` plus `dirty`) and `env_key` are
  unchanged. A fail then pass is outcome `flaky` with both attempts recorded; it counts as a
  pass and is reported as flaky.
- **Regression (R3, F10).** A node regresses when it now fails, an earlier `test-run` entry
  recorded it `passed` or `flaky`, and its `test_hash` equals the one of that pass. A new test,
  or a rewritten one, that starts red is `not yet passing`, never a regression, and never
  interrupts.
- **Owner waiver** (stretch item, plan lane VERIFY). `plumb tests waive --diff-digest <d>
  --reason "..."`, owner only (refused under the marker and by deny rule), appends a `waiver`
  event pinned to that diff digest. It is listed by `validate --merge`; using it in place of
  a full rerun belongs to sub-project 3.
- **Full rerun only when shared test infrastructure changes, and only at the merge boundary**
  (7.2).

## 8. Bridge: importer and judgment

### 8.1 Minimal pi-agent-factory importer

A plan stretch item (TRUST T10), built only with time left after the dogfoodable core; the
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
- `jev`: the JEV adapter (a plan stretch item, TRUST T11; without it, `jev` falls back to
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

**Cascade-to-LLM hook point (interface only).** `LLMCascade.escalate(EscalationRequest)`;
the default implementation, `HostAgentCascade`, queues the request's one-line instruction in
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

| Command | Lane | Purpose |
|---|---|---|
| `plumb init` | CORE | Create `.plumb/` (dirs, `config.yaml`, `claims.yaml`, `.gitignore`, `.gitattributes`, empty logs); idempotent |
| `plumb new <kind> ...` | CORE | New record with the next ID (5.8) |
| `plumb show <ID> [--json]` | CORE | Record, hash, state, links with states, approvals |
| `plumb link <ID> <kind> <target> [--example EX-n]` | CORE | Add a pinned link; target `ID`, `path`, `path::Qual.name` (implemented_by) or `path::test_name` (verified_by) |
| `plumb repin <link-id> \| <ID> \| --all-stale` | CORE | Refresh pins, log `repin` |
| `plumb approve <ID>... \| --proposed [--yes]` | TRUST | Owner approval (refused under the marker) |
| `plumb relay <ID>... --prompt D --quote Q [--revoke]` | TRUST | Agent-relayed approval or revocation, quote-checked |
| `plumb revoke <ID>...` | TRUST | Owner revocation |
| `plumb validate [--merge BASE] [--json]` (alias `check`) | CORE (`--merge` runs TRUST's `merge_check`) | 5.10, 5.11 |
| `plumb status [--json]` | CORE | Counts, drift, awaiting confirmation, tests (via VerifyAPI when present) |
| `plumb drift [--json]` | CORE | Drift signals only |
| `plumb brief [--max-lines N] [--all]` | CORE | The session brief text (6.1) |
| `plumb why <ID\|path>` | CORE | Upward chain: path -> SRs -> INT quotes and deciding DECs |
| `plumb log [--stream events\|evidence] [--kind K] [-n N]` | CORE | Read the logs |
| `plumb trailers check-msg <file>` | TRUST | `commit-msg` check (5.9) |
| `plumb trailers install-hook` | TRUST | Write the git `commit-msg` hook (5.9) |
| `plumb claims check [--range R] [--json]` | TRUST | Claimed vs declared paths (5.9) |
| `plumb tests map\|select\|run\|waive` (aliases `map`, `verify`) | VERIFY | 7.1 to 7.5 |
| `plumb impact <ID\|path> [--json]` | VERIFY | Downstream: records and covering tests with evidence state |
| `plumb hook session-start\|prompt\|post-edit\|stop` | HOST | Hook entry points (6.1 to 6.4) |
| `plumb hooks install\|uninstall\|status` (alias `install claude-code`) | HOST | 6.7 |
| `plumb statusline` | HOST | 6.6 |
| `plumb import pi-agent-factory <src> [--dry-run]` | TRUST (stretch) | 8.1 |
| `plumb fidelity <SR>`, `plumb judge <SR> --verdict V --note N` | TRUST | 8.3 |
| `plumb judgment status` | TRUST | Backend in use, key state (never prints the key) |

## 10. Performance design

Budgets, measured on this 2-core Windows machine where a bare `python -c pass` takes about
225 ms:

| Path | Budget (p95, end to end) | How |
|---|---|---|
| `post-edit` hook | async; under 300 ms if run synchronously | stdlib only; append one line |
| `prompt` hook | under 600 ms | JSON caches; no YAML import on a warm cache; at most 5 records |
| `stop` hook | under 800 ms | one `git status`; hashes only for touched records; map from cache; never runs tests |
| `session-start` hook | under 900 ms | once per session |
| `statusline` | under 350 ms | reads one JSON file |
| Per-turn synchronous hook total (prompt + stop) | under 1.5 s | well under the 2 s rule |
| `plumb tests run` in a turn | `verify.turn_budget_s` 15 s, hard limit 22.5 s | in the agent's turn, not in a hook |

Rules every lane follows:

- The `plumb` entry point imports nothing beyond `sys` and the dispatcher until it knows the
  command; `plumb hook` and `plumb statusline` never import `argparse` handlers of other
  commands, YAML, `subprocess` (except the stop hook's single git call) or `ast` unless a
  cache is cold.
- The record index is cached in `.plumb/cache/index.json` (parsed records and hashes) keyed by
  each record file's `(size, mtime_ns)`; a warm hook re-parses only changed files. File hashes
  are cached the same way. Config is cached as JSON keyed by `config.yaml`'s fingerprint.
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
  sample_size: 10
  default_test_s: 1.0
  workers: 0                 # 0 = no -n; at most 2
  flaky_rerun: true
  infra_globs: ["**/conftest.py", pyproject.toml, uv.lock, pytest.ini, tox.ini, setup.cfg]
hooks:
  budget_ms: {session_start: 900, prompt: 600, stop: 800, post_edit: 300}
  brief_lines: 30
  prompt_lines: 20
  summary_proposed_cap: 3
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

These are frozen in the contract phase (plan phase 0) before the lanes start. A lane may add
private helpers but must not change a contract; a contract change goes through the
coordinator, who updates this section and `src/plumb/contracts.py` on `main`, and every lane
rebases.

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
    regression: bool = False
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
| `open_verify` | `plumb.verify` (VERIFY) | `def open_verify(core: CoreAPI) -> VerifyAPI` |
| `merge_check` | `plumb.merge` (TRUST) | `def merge_check(core: CoreAPI, base: str, *, as_json: bool) -> int` (exit code of 5.11) |
| `install_commit_msg_hook` | `plumb.claims` (TRUST) | `def install_commit_msg_hook(root: Path, interpreter: str) -> Path` |
| `get_backend` | `plumb.judgment` (TRUST) | `def get_backend(core: CoreAPI, *, hook: bool) -> JudgmentBackend` |
| `get_cascade` | `plumb.judgment` (TRUST) | `def get_cascade(core: CoreAPI) -> LLMCascade` |
| `build_packet` | `plumb.judgment.fidelity` (TRUST) | `def build_packet(core: CoreAPI, verify: VerifyAPI \| None, sr: str) -> FidelityPacket` |

A consumer whose provider is missing (import error) degrades: HOST prints the line
`plumb: <part> unavailable` and continues; `validate --merge` and `status` print
`verification: unavailable` (or `fidelity: unavailable`); `validate --merge` without
`plumb.merge` prints `merge boundary: unavailable` and exits 2; `hooks install` without
`plumb.claims` skips the `commit-msg` hook with a notice.

### 12.3 CLI dispatcher contract (`src/plumb/cli.py`, contract phase)

```python
ROUTES: dict[str, str] = {
    # CORE
    "init": "plumb.commands", "new": "plumb.commands", "show": "plumb.commands",
    "link": "plumb.commands", "repin": "plumb.commands", "validate": "plumb.commands",
    "check": "plumb.commands", "status": "plumb.commands", "drift": "plumb.commands",
    "brief": "plumb.commands", "why": "plumb.commands", "log": "plumb.commands",
    # TRUST
    "approve": "plumb.trust_cli", "relay": "plumb.trust_cli", "revoke": "plumb.trust_cli",
    "trailers": "plumb.trust_cli", "claims": "plumb.trust_cli",
    # VERIFY
    "tests": "plumb.verify.cli", "map": "plumb.verify.cli", "verify": "plumb.verify.cli",
    "impact": "plumb.verify.cli",
    # HOST
    "hook": "plumb.hosts.claude_code.cli", "hooks": "plumb.hosts.claude_code.cli",
    "install": "plumb.hosts.claude_code.cli", "statusline": "plumb.hosts.claude_code.cli",
    # TRUST (judgment and importer)
    "import": "plumb.importer.cli", "fidelity": "plumb.judgment.cli",
    "judge": "plumb.judgment.cli", "judgment": "plumb.judgment.cli",
}

def main(argv: Sequence[str] | None = None) -> int:
    """`plumb <command> ...`: import ROUTES[command] lazily and return its run()."""
```

Each routed module exposes `def run(command: str, argv: list[str]) -> int`, where `argv`
excludes the command token. Shared argument helpers live in `plumb/cliutil.py` (contract
phase): `add_common(parser)` (adds `--root`, `--json`), `resolve_root(arg: str | None) ->
Path`, `emit(obj: Any, as_json: bool) -> None`. A missing module prints
`plumb: '<command>' is not available in this build` and returns 2.

### 12.4 Shared primitives (contract phase, frozen)

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
  `log_read` delegate to it, and `FakeCore` uses it too, so every lane writes the same
  format.
- `plumb/text.py`: `terms(s: str) -> frozenset[str]` (lowercase words of 3 or more letters,
  minus a fixed stopword list), `overlap(a: frozenset[str], b: frozenset[str]) -> float`
  (`|a & b| / sqrt(|b|)`, 0 when empty), `CHANGE_WORDS: frozenset[str]`.
- `tests/fakes.py`: `FakeCore`, `FakeVerify`, `FakeBackend`, `FakeCascade`, in-memory
  implementations of the protocols, built from plain dicts, used by every lane's unit tests.
- `tests/conftest.py`: fixtures `repo` (a temp git repository with `.plumb/` dirs,
  `git init`, user config, one commit), `write_record(repo, text)`, `hook_input(event,
  **fields) -> str` (Claude Code stdin JSON).
- `tests/contracts/`: shape tests and a protocol conformance suite parametrized over every
  implementation importable at run time (fakes always; `plumb.api.open_core`,
  `plumb.verify.open_verify` and `plumb.judgment.get_backend` once they exist).

### 12.5 File-format contracts between lanes

| File | Writer | Readers | Shape |
|---|---|---|---|
| `.plumb/log/events.jsonl`, `evidence.jsonl` | `plumb/log.py` (contract phase), called through CoreAPI `log_append` by every lane | all | 5.7; `test-run` payload 7.4; `judgment` payload `{subject, action, verdict, confidence, tier, backend, fingerprint, requirement_hash?, end_hashes?, note?}` |
| `.plumb/session/prompts.jsonl` | HOST prompt hook | TRUST `relay` | one line `{"digest", "session", "at", "text"}` |
| `.plumb/session/stated.json` | HOST stop hook | TRUST `relay`, HOST prompt hook | `{"at", "session", "reply_after_prompt": digest\|null, "records": [{"id", "hash"}]}` |
| `.plumb/session/status.json` | HOST (stop, session-start) | HOST `statusline` | `StatusSnapshot` as JSON plus `"v": 1` |
| `.plumb/session/<sid>/touched.txt` | HOST post-edit | HOST stop, VERIFY `--changed` | one repository-relative POSIX path per line |
| `.plumb/session/<sid>/turn.json` | HOST prompt hook | HOST stop | `{"turn_start": epoch_seconds, "prompt_digest", "asked": {record_id: hash}}` |
| `.plumb/session/escalations.jsonl` | TRUST `HostAgentCascade` | HOST prompt and stop hooks | `{"at", "subject", "instruction"}` |
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

### 14.1 Dogfood checkpoints (from the first hour)

plumb is used on plumb as early as possible (D6; concept 11, slice 1a). Dogfooding is not a
final phase: it starts while the lanes start and grows at a checkpoint each time a lane's
must items merge. The plan (`docs/plans/sp1-plan.md`, sections 4 and 12) gives the
conditions, steps and gates, and protects the checkpoints from every cut.

- **Trailers from the first commit.** Every commit from the contract phase on carries an
  `SR:` trailer naming the plumb requirements it serves; the IDs are fixed by the plan, so a
  trailer is valid before the record files exist.
- **D0, own records.** While the lanes start, plumb's concept-level intent is written by hand
  under `.plumb/`: `INT` records with the owner's verbatim quotes (purpose, decisions D1 to
  D12), `FEAT-001` to `FEAT-004`, requirements `SR-001` onward with given/when/then examples
  taken from the lanes' tests, and `DEC` records for refinements F1 to F13.
- **D1, records checked and trailers enforced**, as soon as the record core and the
  approval, trailer and merge-boundary items merge (concept 1a steps 1 to 4): `plumb init`
  in `C:/coding/plumb` (`.plumb/config.yaml` adds `src/plumb/verify/pytest_plugin.py` to
  `verify.infra_globs`); every record's links pinned; `implemented_by` and `verified_by` links
  for the files already merged; `plumb validate` without errors; the `commit-msg` hook
  installed and `claims.yaml` set to `require_trailer: true`. From D1 on, every commit and
  merge on `main` is checked.
- **D2, hooks installed as they land** (concept 1a step 5): `plumb hooks install` (with the
  `venv` launcher) runs again each time a HOST merge point lands, and registers the hooks
  present in that build: session start, edit tracking and the status line first, then the
  prompt hook, then the stop hook. Claude Code sessions on `C:/coding/plumb` then run
  plumb's own hooks. Installation alone does not put the build in the loop: the coordinating
  workflow session is not rooted in `C:/coding/plumb`, and its subagents do not receive the
  prompt and stop events.
- **Loop steps, from D2 on** (plan 4.5): every unit of the coordinator's work on `main` after
  the first hook install (later lane merges and checkpoints, the integration items, the
  completion steps and the review fixes) runs as a loop step. In host mode it is a headless
  Claude Code session whose project directory is `C:/coding/plumb`, so the installed hooks
  fire. In driven mode, the fallback, the coordinator calls the real entry points around the
  work item: `plumb hook session-start`, `plumb hook prompt` with the work item text,
  `plumb hook post-edit` per written file, `plumb hook stop` (running
  `plumb tests run --changed` when it blocks, then stop again), and `plumb statusline`. Each
  step must leave evidence that the loop ran: its prompt in `.plumb/session/prompts.jsonl`,
  `status.json` rewritten by the step, a `test-run` entry in `.plumb/log/evidence.jsonl` after
  each stop block that asked for the covering tests, and a line in `docs/sp1-loop-log.md`.
  Overnight, a trigger becomes a proposed `DEC` with `matters: true` for the morning merge
  boundary instead of a live question. Lane work inside the worktrees is built by workflow
  subagents outside the loop, and the handoff says so.
- **D3, map and covering tests** (concept 1a step 6): `plumb tests map` on plumb's own tests
  once the verification lane's must items merge.
- **Completion**, before review, as loop steps: the links for code merged later, the first
  `plumb tests run --full`, and the hook benchmark on plumb's own repository. Review then
  runs on the dogfooded result, and each of its fixes is made as a loop step and committed
  through plumb's `commit-msg` hook.

All records stay **proposed**: no agent writes an approval, because no owner prompt in these
sessions affirmed them (R2). The morning handoff gives the owner one line to confirm them
(`plumb approve --proposed`, or "ok" in a session, relayed).

### 14.2 Definition of done

1. `uv run pytest` passes on `main` (all lanes plus integration tests) and `uv run ruff check
   src tests` is clean.
2. Every command of section 9 that was built exists and has at least one test; `plumb --help`
   lists them. Unbuilt 1b and stretch commands are listed in `docs/followups.md`.
3. The integration test of the full loop passes: `init`, `new`, `link`, session-start, prompt,
   post-edit, stop (blocks once asking for the covering tests), `tests run --changed` (appends
   evidence), stop again (summary, no block), `statusline`.
4. Guard tests pass: `plumb approve` refuses under the marker; `plumb relay` refuses a quote
   not in the prompt, a quote without an affirmation, and a record outside the stated set; the
   installer writes the deny rules and the marker.
5. `plumb validate --merge <base>` exits 4 on a range touching an unconfirmed requirement and
   0 once it is approved.
6. Latency: `scripts/bench_hooks.py` (integration phase) on plumb's own repository reports
   p95 prompt + stop under 1.5 s and each hook within its section 10 budget; the result is
   recorded in `docs/followups.md` if any budget is missed.
7. If the importer (stretch) was built: `plumb import pi-agent-factory
   C:/coding/pi-agent-factory --dry-run` runs read-only against the real register and reports
   findings; the unit tests import fixture copies of real SR, FEAT, bundle and NC files.
8. `plumb judgment status` reports `heuristic` without a key; if the JEV adapter (stretch) was
   built, its tests pass against a local stub HTTP server; no test calls the network.
9. Dogfood done (14.1): checkpoints D0 to D3 and the completion step passed; `plumb validate`
   reports no errors on plumb's own records (warnings for proposed records are expected), the
   hooks are installed in `C:/coding/plumb/.claude/settings.json`, every commit since the
   contract phase carries an `SR:` trailer, the `commit-msg` hook has checked every commit
   since D1, and `plumb claims check` accepts the latest commits. Every loop step since D2
   left the evidence listed in 14.1, and the handoff states honestly, from
   `docs/sp1-loop-log.md`, which parts of the loop ran during the build, in which mode, and
   which work was built outside it.
10. Every unfinished item is recorded in `docs/followups.md` with its state; medium and low
    review findings are recorded there; no HIGH finding is open.
11. The morning minimum (plan 12) is on `main` and dogfooded by the clock rule, 2026-10-06
    07:15 local, and the handoff is committed by 07:45, before the owner's 08:00 deadline;
    any part of the minimum still missing is listed first in the handoff.

## 15. Out of scope for sub-project 1

- Escalation set approvals, `plumb decline`, and the full escalation trigger set (sub-project
  2); only the stretch hint of 6.2 step 5 is here.
- The merge-boundary full-suite run, evidence promotion, waivers in place of full reruns, the
  claims audit as a gate and a CI entry point (sub-project 3).
- Codex, Pi, Hermes adapters and an MCP server (sub-project 4).
- `by: import` approvals, a complete import and pi-agent-factory's migration (sub-project 5);
  the fork plan (a separate document, decision D9).
- Any run state machine, phases, consent phrases, manifests, handoff hashes, review swarms or
  governed execution (concept non-goals).
