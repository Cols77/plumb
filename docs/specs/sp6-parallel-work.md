# Sub-project 6 spec: parallel work by awareness instead of locks

Status: implementation spec, written 2026-10-06. The owner does not review it (D11); verifier
agents check it against the owner intent brief, rulings R1 to R15, `docs/concept.md`
(D15, sections 4.3, 4.7, 7.5 and 11 item 6) and the sp2 to sp5 specs. Quotes and rulings
win, then the concept, then this spec. `docs/plans/sp6-plan.md` builds it in four lanes:
IDS, LOGS, MERGEDRIVER and AWARENESS. Requirements: `FEAT-006`, `INT-022`, `SR-070` to
`SR-079`, decisions `DEC-020` to `DEC-022`, all proposed. Every item of R10 is a MUST.

## 1. Outcome

Several agents, worktrees and clones work on one repository at once. The owner approved
ruling R10 ("yes"): awareness instead of locks. git is the coordinator, and plumb holds no
shared mutable runtime state. After this sub-project:

1. **New IDs never collide between worktrees.** Every new record ID is reserved through the
   shared ref `refs/plumb/ids` with git's atomic compare-and-swap (`git update-ref <ref>
   <new> <old>`), which every worktree of a repository shares. Clones still may collide;
   `plumb merge-fix` renumbers the incoming record at merge and rewrites every reference
   the incoming side introduced, never history (SR-070, SR-071).
2. **Logs never conflict.** Every log entry is its own file under `.plumb/log/<kind>/`, as
   concept 4.7 already says. The implementation drift (`events.jsonl`, `evidence.jsonl`) is
   fixed by an idempotent migration that keeps the hash chain and the evidence identities;
   readers accept both formats during the transition (SR-073, SR-074).
3. **Record files merge field by field.** A frontmatter-aware git merge driver, installed by
   `plumb hooks install`, merges non-overlapping changes on its own (links added on both
   sides, independent fields). A real content conflict becomes an INTENT CONFLICT
   (`IC-###`): one card with both versions at the merge boundary, an optional JEV
   compatibility judgment, and a record that stays unconfirmed until the owner chooses
   (SR-075, SR-076).
4. **Each session knows what the others are changing.** The brief, the prompt hook's delta
   (R9) and the status line say "SR-005 "relay checks" is also being changed on branch
   feat-x". They read the other worktrees' `.plumb/` read-only, from small cached files,
   within the hook budget (SR-078, SR-079).
5. **The merge boundary covers both.** `plumb check --merge` and `plumb merge-check` on the
   merge result report ID collisions (exit 1) and open intent conflicts (exit 4), and run as
   the pre-push hook (sp3) or a new pre-merge-commit hook (SR-072, SR-077).

There are no leases, no admission, no transaction machinery and no guarded publish
(R10.4, R10.5). Nothing in this sub-project runs in a hook except the awareness read
(9) and the publication of the worktree's own changed records (9.2).

## 2. Owner intent served

| Owner decision or ruling | Where |
|---|---|
| R10: "awareness instead of locks: git is the coordinator, and plumb holds no shared mutable runtime state" | 3; the only shared writable object is a git ref, written by git's own atomic update (4) |
| R10.1: reserve "through the shared ref `refs/plumb/ids` with git's atomic compare-and-swap ... shared by every worktree"; "`plumb merge-fix` renumbers at merge and rewrites every reference" | 4, 5 |
| R10.2: "one file per entry under .plumb/log/<kind>/ ... with a migration of existing entries that keeps the hash chain" | 6 |
| R10.3: "Non-overlapping changes merge automatically. A content conflict becomes an INTENT CONFLICT, shown at the merge boundary as one intent card with both versions (and an optional JEV compatibility judgment)" | 7, 8 |
| R10.4: "the brief and status line warn ... It reads the other worktrees' .plumb cheaply, read-only, with no leases and no admission" | 9 |
| R10.5: "`plumb check --merge` on the merge result ... as a pre-merge or pre-push hook. There is no transaction machinery and no guarded publish" | 10 |
| KEEP: "append-only evidence and decision records"; "content hashes and staleness on records and links"; "relation validation (no dangling links)" | 6 (chain kept), 5.4 (references rewritten, pins repinned only for a pure renumber), 8.1 (the conflicted record matches no approval) |
| KEEP: "`SR:` commit trailers and claims checks" | 5.5: history keeps its trailers; claims reads them through the renumber map |
| R2: "A confirmation requires the owner's explicit words" | 8.4: only the owner chooses a side; the agent relays the owner's words, checked like an approval |
| R1, decision 5: questions only on a real intent change, an unconfirmed decision that matters, or a regression | An intent conflict is a contradiction between two versions of confirmed or proposed intent (trigger 1 or 2); an ID collision and a log merge never ask the owner |
| R9: compact deduplicated delta; full card only when it matters | 9.4: one line per overlapping record, repeated only when the other side changed; 8.3: the conflict card is a full card because it awaits the owner |
| Quality bar: "Per-turn overhead is seconds, not minutes"; owner rule: "Hook latency stays in seconds. Awareness must stay cheap" | 9.5, 12: at most 50 ms warm, no git process per prompt |
| R14, R15: every owner capability through `/plumb` commands or plain words; the plugin is the bootstrap | 11 |
| D3: no per-turn admission or coordination weight | No leases, no locks across worktrees; the per-worktree log lock stays local (6.2) |

## 3. Principles for parallel work

1. **git is the coordinator.** The only state shared between worktrees that plumb writes is
   one git ref, `refs/plumb/ids`, updated only by `git update-ref` with the expected old
   value. Everything else plumb shares travels in commits and merges.
2. **No shared mutable runtime state.** No lock spans worktrees, no lease, no admission, no
   service. A worktree publishes only into its own gitignored `.plumb/cache/`, and other
   worktrees read that file without writing anything (9).
3. **Append, never rewrite.** Log entries are new files. A merge never edits an entry; a
   renumber or a conflict resolution is a new entry that refers to the old facts.
4. **Merges stay honest.** A merged record either combines two non-overlapping changes, or
   carries both versions and stays unconfirmed. plumb never silently picks a side of a
   content conflict, and never carries an approval to content the owner did not see.
5. **History is never rewritten.** Old commits keep their trailers; plumb maps them.

## 4. Collision-free IDs (SR-070)

### 4.1 The ref

`refs/plumb/ids` points to a blob holding canonical JSON:

```json
{"v": 1,
 "high": {"INT": 22, "SR": 79, "DEC": 22, "FEAT": 6, "NC": 3, "IC": 0},
 "recent": [{"id": "SR-079", "branch": "main", "worktree": "C:/coding/plumb",
             "at": "2026-10-06T23:10:04Z"}]}
```

`high` is the highest number reserved per prefix. `recent` keeps the last 50 reservations
for `plumb ids` and for diagnosis; it is never used to decide an ID. Refs outside
`refs/worktree/` are shared by every worktree of a repository, so one ref serves all of
them. The ref is local to the clone: plumb never pushes or fetches it (clones meet at
`plumb merge-fix`, 5). Old blobs become unreachable and `git gc` removes them.

### 4.2 Reservation

`plumb.ids.reserve(paths, kind, count=1) -> list[str]` is the one allocation function. Every
writer of a new record calls it through `Store.next_id(kind)` (sp2 12: "IDs come from one
allocation function"):

1. Read the ref: `git rev-parse -q --verify refs/plumb/ids` and, when it exists,
   `git cat-file blob <oid>`. When it does not exist, seed it (4.3).
2. `n = max(high[prefix], highest number of that prefix in this worktree's records) + 1`.
3. Write the new blob (`git hash-object -w --stdin`) and move the ref with
   `git update-ref -m "plumb: reserve SR-080" refs/plumb/ids <new> <old>`, where `<old>` is
   the oid read in step 1, or the all-zero oid when the ref did not exist (create only).
4. If `update-ref` fails because the ref moved, go back to step 1 after a random 5 to 50 ms
   pause, at most 50 times and at most 3 s; then fail with exit 2 and
   "plumb: could not reserve an ID (refs/plumb/ids busy); try again". A number is never
   handed out twice: it is handed out only after the compare-and-swap succeeded.

`plumb.ids.peek(paths, kind)` returns the ID `reserve` would hand out without writing; every
preview uses it (`plumb capture --dry-run`, the intent card of a dry run). A reserved ID that
is never written leaves a gap; IDs are not dense and nothing relies on density.

The cost is four short git processes per reserved batch, about 0.1 to 0.2 s, paid only when a
record is created, never in a hook. `reserve(count=n)` reserves a batch in one
compare-and-swap (`plumb capture` writing an INT, three SRs and a DEC reserves per prefix
once).

### 4.3 Seeding and observing

- **Seed.** When the ref does not exist, `high` starts at the maximum of the records in
  this worktree and of the record file names on every local branch tip
  (`git for-each-ref refs/heads` and one `git ls-tree -r --name-only <tip> -- .plumb/`
  per branch). Branch names are read once; seeding happens once per clone.
- **Observe.** Every writer that keeps an existing ID calls
  `plumb.ids.observe(paths, ids)`, which raises `high` to cover them (compare-and-swap like
  a reservation): the pi-agent-factory importer (it keeps upstream IDs), `plumb merge-fix`
  (the IDs a merge brought in) and `plumb ids sync` (the agent's repair command, which
  re-runs the seed scan).
- **Kinds.** Prefixes `INT`, `SR`, `DEC`, `FEAT` (3 digits), `NC` (4 digits) and `IC`
  (3 digits, intent conflicts, 8.1). Examples are numbered inside their requirement and do
  not use the ref (7.3 handles their clashes).

### 4.4 Outside git

When the root is not inside a git work tree, or `git` cannot run, `reserve` returns the
highest local number plus one and the command prints one line: "plumb: SR-080 is not
reserved (no git repository); plumb merge-fix fixes a collision later". Nothing fails.

### 4.5 Entry points (one test each)

Every path that creates a record ID goes through `Store.next_id` -> `ids.reserve`:
`plumb new <kind>`, `plumb intent`, `plumb decide` (including `--supersede`),
`plumb capture` (INT, SR, DEC), the importer (`observe`), the merge driver's intent
conflict (`IC`, 8.1) and `plumb merge-fix` (5). A conformance test asserts that no module
other than `store.py` and `ids/` computes a new record number.

## 5. `plumb merge-fix` (SR-071, SR-072)

```
plumb merge-fix [--dry-run] [--json] [--from <ref>]
```

### 5.1 What is a collision

An ID collision is two different records with one ID. plumb finds them in three places:

1. **An in-progress merge** (`MERGE_HEAD` exists) with a record path unmerged because both
   sides added it (`git ls-files -u -- .plumb/`, stage 1 absent, stages 2 and 3 present).
   The merge driver leaves exactly this state on an add/add of two different records (7.5);
   without the driver, git's text merge leaves the same index stages.
2. **The working tree**: two record files declaring the same `id` at different paths
   (`Store.problems()` already reports them as `duplicate id`).
3. **Before a merge** (`--from <ref>`, read only): records added on both `HEAD` and `<ref>`
   since their merge base with the same ID and different content. This is a preview; it
   renumbers nothing.

Two files with the same ID and the same content (both sides imported the same record) are
not a collision: the driver keeps one and nothing is renumbered.

### 5.2 Which record keeps its ID (DEC-022)

The first parent, the branch being merged into, keeps its IDs. The incoming record (stage 3,
`MERGE_HEAD`'s side) gets a new ID from `ids.reserve` after `ids.observe` has raised `high`
over every ID both sides hold. For a duplicate in the working tree with no merge in progress,
the record whose file was added later in `git log --diff-filter=A` is the incoming one.
Renumbering changes no intent, so it is mechanical: the agent runs it, and it never asks the
owner.

### 5.3 What is rewritten

A reference is rewritten when the incoming side introduced it: it is in the incoming version
of a file and not in the merge base's version. A reference our side introduced still names
the old ID. When both sides introduced the same reference (both added `SR-070` to a
feature's `requirements`), both stay: the old ID for ours, the new ID for the incoming
record. The places, all enumerated, one test each:

- the incoming record itself: its file moves to the new ID's path and its `id` changes;
- frontmatter references in records: `links[].to`, `feature`, `requirements`, `members`,
  `supersedes`, `decides`, example references `SR-070/EX-2` in any string field;
- body wikilinks `[[SR-070]]` and `[[SR-070|title]]`;
- test markers `@pytest.mark.sr("SR-070")` in test files the incoming side added or changed
  since the merge base;
- `.plumb/claims.yaml` baseline entries naming an incoming `NC-####`;
- the pending commit message (`MERGE_MSG`, `SQUASH_MSG`): `SR:` trailers naming the old ID
  for the incoming side's work.

The test map is derived; `plumb map` rebuilds it. Rewritten links whose pin no longer matches
only because the ID changed (the end's hash with the old ID substituted equals the pin) are
repinned in the same step. Any other stale pin is left stale, a drift signal as usual.

### 5.4 Approvals carried across a renumber

The record hash covers every field but `links`, `id` included (concept 4.4), so a renumbered
record no longer matches its approvals. `merge-fix` appends one `renumber` log entry:

```json
{"from": "SR-070", "to": "SR-081", "kind": "requirement", "incoming": "<MERGE_HEAD sha>",
 "old_hash": "sha256:...", "new_hash": "sha256:...",
 "approvals": ["<digest of each incoming-side approval naming SR-070>"],
 "commits": ["<sha of each incoming commit since the merge base whose SR trailer names SR-070>"]}
```

The confirmation reader (`confirm.confirmation_of`, through `ids.approval_aliases`) treats
an approval listed in a `renumber` entry as an approval of the new ID only while the
record's current content, with `id` set back to the old ID, hashes to the approval's pinned
hash. So a renumber alone keeps the owner's confirmation; any later edit, or an approval of
other content, carries nothing. `plumb validate` re-checks every `renumber` entry the same
way (the listed approvals exist, name the old ID and come from the incoming side).

### 5.5 Trailers, never history

Old commits are never amended, rebased or rewritten. `plumb claims check` and claims
ingestion read the trailers of the commits listed in a `renumber` entry through
`ids.trailer_aliases`: in those commits, `SR-070` means `SR-081`. New commits carry the new
ID; the pending merge message is rewritten (5.3).

### 5.6 Behaviour

- `merge-fix` stages what it changed (`git add` of the renamed record, the rewritten files
  and the `renumber` entry) when a merge is in progress; it never commits.
- `--dry-run` prints the plan and writes nothing (no reservation either: it uses `peek`).
- Idempotent: a second run finds no collision and writes nothing.
- Output, for the agent to relay in the owner's terms: "SR-070 "export csv" from the merged
  branch is now SR-081 (4 references in 3 files; the owner's approval carried; 2 commits'
  trailers mapped)".
- Exit 0 when nothing is left to fix, 1 when a collision remains (for example a side that is
  not a parseable record), 2 on usage errors.

## 6. Logs that never conflict (SR-073, SR-074)

### 6.1 Layout

```
.plumb/log/<kind>/<stamp>-<suffix>.json
```

- `<kind>` is the entry's `kind`: `approval`, `revocation`, `prompt`, `repin`, `judgment`,
  `test-run`, `merge-evidence`, `waiver`, `triage`, `config`, `calibration`, `import`,
  `claims-ingest`, `renumber`, `conflict-resolution`, and any later kind.
- Each entry belongs to a stream, as today: `evidence` for `test-run` and `merge-evidence`,
  `events` for every other kind (`log.STREAM_OF_KIND`). The chain (`prev`) runs per stream.
- `<stamp>` is UTC `YYYYMMDDTHHMMSS.ffffffZ`. A new entry uses the wall clock with
  microseconds and `<suffix>` is 8 hex characters of a fresh uuid4. A migrated entry uses
  its own `at` with `.000000` and `<suffix>` is characters 8 to 15 of its digest's hex, so
  the same legacy line always gets the same file name (6.6).
- The file holds the entry's canonical JSON plus a newline, exactly the fields of today's
  JSONL line: `{v, kind, at, marker, payload, prev, digest}`. The digest is computed from
  the fields, not the bytes, so the format is unchanged for every reader.

### 6.2 Append

`log.append(paths, stream, kind, payload)` stays the only writer (the edit-tool guard keeps
denying writes under `.plumb/log/`):

1. Take the existing per-worktree log lock (`.plumb/cache/log.lock`). It serialises writers
   of one worktree only; nothing spans worktrees.
2. `prev` is the stream's head: `.plumb/cache/log-head.json` (`{stream: {digest, name}}`),
   rebuilt by a scan of the stream when missing or naming a file that no longer exists.
3. Write the entry to a temporary file in the kind's directory, then `os.link` it to its
   final name, which fails if the name exists (no replace; a new suffix is drawn), fsync,
   remove the temporary file, update the head pointer.

Two worktrees, or two branches, that append create different files, so git never sees two
changes to one path: merges under `.plumb/log/` cannot conflict. A merge makes the chain
fork; that is accepted while every `prev` resolves (concept 4.7).

### 6.3 Read

`log.read(paths, stream, kinds=None, since=None)` returns entries of both formats:

- per-entry files of the stream's kind directories (`os.scandir`, no recursion beyond one
  level);
- lines of the legacy `events.jsonl` or `evidence.jsonl`, if any remain;
- deduplicated by digest (a migrated line and its file are one entry);
- in order: by `at`, then by the chain (an entry after the entry its `prev` names), then by
  file name. This is the order every reader already assumes ("the latest approval").

A pack cache per stream (`.plumb/cache/log-<stream>.json`: parsed entries keyed by file
name) makes a warm read cost one directory listing per kind plus the new files: entries are
immutable, so a name seen once never needs reading again; a vanished name is dropped. The
cache is plain JSON, gitignored and deletable. `LogEntry` gains `name` (the file name, or
`events.jsonl:<line>` for a legacy line); `offset` stays for legacy lines and is `-1`
otherwise. `since` (a set of names already applied) replaces `since_offset` for incremental
readers. The evidence reuse index (`verify/evidence.load_index`) keys its incremental update
on the names applied and the last name, and rebuilds from scratch when a newly listed entry
sorts before the last one applied (an entry that arrived by a merge).

### 6.4 Verify

`log.verify_chain(paths, stream)` reports, naming the file (or the legacy line):

- a file that is not valid JSON or not an object;
- a digest that does not match the entry (an edited entry);
- a `prev` that resolves to no entry of the stream, in either format (a deleted entry that
  a later one names);
- a file name whose stamp does not parse, or a migrated name whose suffix does not match its
  digest.

At the merge boundary, `merge.log_integrity` checks against git, with one
`git diff --name-status --no-renames <fork> -- .plumb/log/` call: any entry file modified or
deleted since the fork is reported. For legacy files, each line present at the fork must
still be present, as a line or as a migrated entry with the same digest.

### 6.5 Migration (SR-074)

```
plumb log migrate [--dry-run] [--check] [--json]
```

1. Read every line of `events.jsonl` and `evidence.jsonl`. If any line is not valid JSON or
   its digest does not match, refuse (exit 1), name the lines and write nothing: tamper
   evidence is never laundered into the new format.
2. For each line, write `<kind>/<at stamp>.000000Z-<digest[8:16]>.json` with exactly the
   line's fields, unless a file with that name already exists (skip; the name is a function
   of the digest, so an existing name holds the same entry).
3. When every line is present as a file with the same digest, truncate both legacy files to
   zero bytes. They are emptied, not deleted, so a branch made before the migration that
   appends to them still merges: with `merge=union`, base lines removed on one side and
   lines appended on the other leave exactly the appended lines.
4. Rebuild the head pointer and the pack caches.

What stays identical, and is tested: every entry's fields, digest and `prev`, so the chain
verifies unchanged; every `test-run`'s `run_id`, node evidence and identity keys, so
`plumb verify` reuses the same evidence and the same tests stay fresh; every approval's
`evidence`, `prompt` and record references, so every confirmation stays as it was.

Idempotence: a second run writes nothing. Two branches that migrate independently write
identical files for their common lines, so they merge without conflict and without
duplicates (identical add/add). A legacy line that arrives later by a merge (step 3's union
case) is read by every reader at once (6.3) and moved by the next `plumb log migrate`.
`--check` exits 1 while legacy lines remain; `plumb validate` and the merge report show
"N legacy log lines not migrated (plumb log migrate)" as a warning, never a hold.
`plumb init` stops creating the JSONL files. `.plumb/.gitattributes` keeps
`log/*.jsonl merge=union` for the transition.

## 7. The record merge driver (SR-075)

### 7.1 Installation

`plumb hooks install` (and `/plumb init`, R15) installs the driver, idempotently:

- `.plumb/.gitattributes` gains, once each:
  `intents/*.md merge=plumb-record`, `requirements/*.md merge=plumb-record`,
  `decisions/*.md merge=plumb-record`, `features/*.md merge=plumb-record`,
  `ncs/*.md merge=plumb-record`. Other lines are kept. The file is committed, so every clone
  shares the attribute.
- The repository's git config (shared by every worktree of the clone) gains
  `merge.plumb-record.name = plumb record merge` and
  `merge.plumb-record.driver = <launcher> merge-driver %O %A %B %P %X %Y`, where `<launcher>`
  is the one the commit-msg hook uses (the plugin's bundled CLI once R15 lands). `%X` and
  `%Y` are the two sides' labels (git 2.44 or later); with an older git, the driver reads
  the labels from `HEAD` and `MERGE_HEAD`/`REBASE_HEAD`/`CHERRY_PICK_HEAD`.
- `plumb hooks uninstall` removes exactly these lines and keys. `plumb hooks status` reports
  "merge driver: installed | not installed | attribute without driver".

A clone where the driver is not configured falls back to git's text merge for record files
(the attribute names an unknown driver); `plumb check --merge` then reports any conflict
markers as an unparsable record (exit 1) with "/plumb init installs the record merge".

### 7.2 Invocation

`plumb merge-driver BASE OURS THEIRS PATH [OURS_LABEL THEIRS_LABEL]` reads three temporary
files, writes the result to `OURS` and exits 0 (merged, possibly carrying an intent
conflict, 8) or 1 (git must stop: 7.5 and 7.6). It imports only the frontmatter helpers
(`model.split_frontmatter`, `load_yaml`, `store.dump_frontmatter`, `ordered_frontmatter`,
`model.record_hash`), never the record index, and runs git only to reserve an `IC` ID.
Target: under 300 ms per file. It runs only for record files both sides changed.

### 7.3 Field rules

The driver parses base (B), ours (O) and theirs (T) and merges each top-level field of the
frontmatter against the base. For every field: unchanged on both sides keeps B; changed on
one side takes that side; changed identically on both takes it. When both sides changed it
differently:

| Field shape | Fields | Rule |
|---|---|---|
| Links | `links` | Three-way set merge keyed by `(kind, to, path, symbol, test, example)`: added on either side kept, removed on either side removed. The same link with different pins on both sides keeps ours's pin (a pin is a cache of hashes, not intent); the link shows stale if the pin no longer matches, cleared by `plumb repin`. Never a conflict. |
| Lists of strings | `will`, `wont`, `assumptions`, `alternatives`, `requirements`, `members` | Three-way set merge keeping the base order, then ours's additions, then theirs's. A conflict only when both sides removed the same item and each added a different one (both rewrote the same item). |
| Examples | `examples` (keyed by `id`) | Per example, the rules of this table for a whole value. Added on both sides with different IDs: both kept. Added on both sides with the same new `EX-n` and different content: theirs's becomes the next free `EX-n`, and theirs's added links whose `example` named it are rewritten. Changed on both sides differently, or removed on one side and changed on the other: conflict on `examples/EX-n`. |
| Scalars and mappings | `title`, `statement`, `quote`, `readback`, `chosen`, `rationale`, `matters`, `mode`, `feature`, `status`, any other field | Conflict on that field. |
| Body | the Markdown after the frontmatter | One side changed: take it. Both: `git merge-file -p` on the three bodies; a clean merge is taken, a conflicting one is a conflict on `body` (ours's body kept, both bodies in the conflict). |

Formatting never conflicts: the driver compares parsed values, and the result is written in
the stable key order of `store.ordered_frontmatter`, so a YAML style or key-order difference
between the sides merges cleanly and does not change the record hash.

### 7.4 Output without a conflict

The merged frontmatter and body, written to `OURS`, exit 0. The driver prints one line per
record to stderr, which git shows: "plumb: SR-005 merged field by field (links +2 from
feat-x, EX-4 from feat-x renumbered from EX-3)".

### 7.5 Both sides added the same ID (an ID collision)

When the base is empty (an add/add) and both sides declare the same `id` with different
content, this is an ID collision, not an intent conflict: two different records. The driver
writes ours unchanged, prints "plumb: SR-070 was created on both sides as different records;
/plumb merge-fix renumbers the incoming one", and exits 1. git stops with the path unmerged,
and its index keeps both versions as stages 2 and 3, which `plumb merge-fix` reads (5.1).
When the add/add contents are equal after parsing, the driver writes one and exits 0.

### 7.6 A side that is not a parseable record

When a side cannot be parsed, the driver falls back to `git merge-file` on the whole text
and returns its status (conflict markers, exit 1). `plumb validate` then names the
unparsable file. This is the only case where a record file gets conflict markers.

## 8. Intent conflicts (SR-076)

### 8.1 Where the conflict lives (DEC-020)

When any field conflicts (7.3), the driver writes ours's values for the conflicting fields,
the merged values for every other field, and a `conflict` block in the frontmatter:

```yaml
conflict:
  id: IC-004
  base: sha256:...            # record hash at the merge base
  ours: {label: main, hash: sha256:...}
  theirs: {label: feat-x, hash: sha256:...}
  fields:
    statement:
      base: A relay pins every stated record.
      ours: A relay pins only the records the owner's words affirm.
      theirs: A relay pins the stated group, named by its title.
    examples/EX-2: {base: {...}, ours: {...}, theirs: {...}}
  merged: [links +2 from feat-x, EX-4 from feat-x]
```

The `IC-###` ID comes from `ids.reserve(kind="conflict")` (4.3), so it is unique across the
worktrees of the clone. The block is inside the record's file because git runs a merge
driver while it holds the index lock: the driver can write only its own output file, and a
separate `.plumb/conflicts/IC-###.md` would not enter the merge commit. One file keeps both
versions next to the record, readable by anyone, with no state outside the repository.
`plumb show IC-004`, `plumb show SR-005` and every listing treat the block as the intent
conflict record `IC-004` on `SR-005`.

The block is a frontmatter field, so the record hash covers it: the merged record matches
neither side's hash, and no approval made on either side confirms it. The record is
`unconfirmed` until the owner chooses (8.4), whatever its state was on either side.

### 8.2 git's merge goes on (DEC-021)

The driver exits 0 after writing an intent conflict. git completes the merge (or continues
the rebase) with the record carrying the conflict. Parallel work is not stopped by plumb;
the merge boundary holds instead (10): `plumb check --merge`, `plumb merge-check`, the
pre-push hook and the optional pre-merge-commit hook report every open intent conflict and
exit 4 until the owner has chosen. With the pre-merge-commit hook installed, git does not
record the merge commit: the merged files stay staged and the merge stays in progress until
the choice is made, then `git commit` completes it.

### 8.3 The conflict card

The conflict is one card in the intent-card format of R9 (sp5 4.2, the `▸ Conflict` kind sp5
10 reserved), shown in full because it awaits the owner:

```
▸ Conflict  IC-004 on SR-005 "relay checks"   (awaits your choice)
  main     A relay pins only the records the owner's words affirm.
  feat-x   A relay pins the stated group, named by its title.
  Merged on their own: 2 links and EX-4 from feat-x
  Compatible? JEV: likely compatible (0.82): both can hold if a group is affirmed by name
  Say: "keep main's", "keep feat-x's", or how to combine them
```

- It shows only the conflicting fields, each as the two versions in the owner's terms; an
  example shows as its given/when/then.
- **Compatibility judgment, optional and advisory.** When JEV is configured, the card asks
  `backend.contradiction(ours, theirs)` once per pair of hashes (5 s limit, never inside the
  driver) and logs it as a `judgment` entry. With the heuristic or no backend, the line reads
  "Compatible? no judgment available". The judgment never resolves anything.
- Where it appears: `plumb conflicts` and `/plumb conflicts`; `plumb review`; the merge
  report (10); the stop hook's summary in the turn where a merge produced it (trigger 1 or 2:
  a contradiction between two versions of intent), once per conflict hash; the session brief
  and the status card count it ("1 conflict awaits you").

### 8.4 Only the owner chooses

```
plumb conflict choose <IC or plain words> --take ours|theirs [--prompt <digest> --quote "<words>"]
plumb conflict choose <IC> --take combined --file <record.yaml> [--prompt ... --quote ...]
plumb conflict propose <IC> --file <record.yaml>
```

- **Owner's terminal.** Without `--prompt`, the command writes `by: owner` through
  `approvals.require_owner` (refused under the session marker and without an interactive
  terminal, exit 3, nothing written; concept 4.6 check 4).
- **Relayed.** With `--prompt` and `--quote`, the agent relays the owner's own words. The
  prompt must be logged by the host's prompt hook (`approvals.owner_prompt`), the quote must
  be verbatim in it, the conflict card must be in the stated set of the reply before that
  prompt (the stop hook adds shown conflicts to `stated.json` as
  `conflicts: [{ic, ours_hash, theirs_hash, combined_hash}]`), and the quote must name the
  choice: the chosen side's label ("keep feat-x's"), "mine"/"ours" or "theirs"/"their
  version", or an affirmation of a combined wording shown in the card. A quote that names
  both sides, or that holds a reservation or a change clause (the readers of concept 4.6
  check 3), is refused. Recorded `by: agent-relayed` with the quote and the prompt digest.
  Self-recorded messages follow R13 Q4 like any relay.
- **Combined.** The agent may propose a combination (`plumb conflict propose`) in the
  owner's terms; it appears in the card as a third version. Only the owner's choice applies
  it.
- The guard denies `plumb conflict choose` without `--prompt` in the agent's shell (the
  Claude Code deny rules, in the three launcher forms).

Applying a choice writes the record with the chosen side's exact fields and body (or the
combined one), keeps the merged links, removes the `conflict` block and appends a
`conflict-resolution` entry `{ic, record, take, by, quote, prompt, base, ours_hash,
theirs_hash, result_hash}`. Choosing a side whose content the owner confirmed on that side
makes the record confirmed again by that existing approval (its hash is pinned). A combined
version is a new edit: `proposed` until the owner confirms it, like any read-back. The
choice is not itself an approval of new content.

### 8.5 What is not an intent conflict

Links, pins and examples added on both sides (7.3), formatting, an ID collision (7.5), and
log entries (6) never produce one. A record deleted on one side and changed on the other is
git's modify/delete conflict (the driver is not called); `plumb check --merge` lists it as
an unmerged record path (exit 1) with the two choices. Records are superseded, not deleted,
so this is rare.

## 9. Cross-worktree awareness (SR-078, SR-079)

### 9.1 What "changing" means

A worktree is changing a record when, relative to the merge base of its branch with
`merge.default_base` (`main`), or in its uncommitted changes:

- the record's file changed (`edited`) or was added (`new`); or
- one of the record's `implemented_by` or `verified_by` ends changed (`ends`).

A local branch without a worktree is changing the records its commits since that merge base
change, by the same rule. Remote-tracking branches are off by default
(`awareness.remotes: false`).

### 9.2 Publishing (each worktree, its own cache only)

Each worktree writes `.plumb/cache/changing.json`, gitignored, in its own `.plumb/`:

```json
{"v": 1, "worktree": "C:/coding/plumb-wt/feat-x", "branch": "feat-x", "head": "<sha>",
 "base": "<sha>", "at": "2026-10-06T23:20:00Z",
 "paths": ["src/plumb/approvals.py", ".plumb/requirements/SR-005.md"],
 "records": {"SR-005": {"title": "relay checks", "hash": "sha256:...", "how": "edited"}}}
```

- The stop hook writes it, from the paths it already has (`git status` of the turn, sp1 6.3)
  plus the branch's committed changes, which it recomputes only when `HEAD` moved (one
  `git merge-base` and one `git diff --name-only <base>...HEAD`, cached by `HEAD`).
- The post-edit hook only appends the edited path to `paths` (no index, within its 300 ms
  budget), so another session sees an edit before the turn ends.
- The session-start hook refreshes it when `HEAD` moved since it was written.
- A reader maps `paths` to records with its own index as well (`records_for_paths`), so a
  stale `records` map does not hide a changed end.

### 9.3 Reading the others (read only)

`plumb.awareness.overlaps(core, mine)` lists, for each record in `mine`, the other places
changing it:

- **Worktrees**, found without running git: the common git directory (from `.git`, or the
  `gitdir:` and `commondir` files of a linked worktree), its `worktrees/*/gitdir` files
  (each worktree's path) and `worktrees/*/HEAD` (its branch); the main worktree is the
  common directory's parent. A worktree whose path no longer exists is ignored. For each,
  read its `.plumb/cache/changing.json`; ignore it when older than
  `awareness.max_age_days` (7).
- **Branches without a worktree**, at session start only: branch tips from
  `refs/heads/**` and `packed-refs` (read as files). For each branch whose tip differs from
  the cached one in `.plumb/cache/awareness-branches.json`, most recently changed first, run
  `git diff --name-only <default>...<tip>` (one process per branch), at most
  `awareness.branch_max` (8) branches and `awareness.branch_scan_ms` (400 ms) per session
  start; the rest keep their cached result and are scanned at a later session start. The
  default branch and this worktree's branch are skipped.
- Nothing is written outside this worktree's `.plumb/cache/`; no lock is taken in another
  worktree; no git command runs in another worktree's directory. The other side's record
  title and hash come from its `changing.json`, or from reading its record file (one small
  read) when the file is newer.

`mine` is the records this worktree is changing (9.1) plus the records this session has
seen (the delta's seen set, sp5 3) and the records the current prompt is about.

### 9.4 Where the owner and the agent see it

- **Session brief:** one line per overlap with this worktree's changing records, at most
  `awareness.brief_lines` (3), then "+N more (plumb status)":
  `plumb: SR-005 "relay checks" is also being changed on branch feat-x`.
- **Prompt delta:** when a record relevant to the prompt (sp1 6.2 step 2) is being changed
  elsewhere, one line through `present.delta.emit`, keyed by
  `(overlap, record, branch, other side's hash)`: shown once per session, again only when the
  other side's version changed (R9).
- **Stop hook:** when the turn touched a record being changed elsewhere, the same line, keyed
  the same way.
- **Status line:** the snapshot gains `overlaps` and `overlap_labels`, and the status card
  adds `· 1 also changed on feat-x` (`overlap 1 (feat-x)` in ASCII). Nothing when zero.
- **`plumb status`** lists every overlap with worktree paths; the owner asks in plain words
  ("is anyone else changing the relay checks?") or `/plumb status`.

Awareness informs; it never blocks, never asks the owner, and never stops an edit. Two
sessions changing the same record will meet the merge driver (7) and, for a real content
conflict, the owner's choice (8).

### 9.5 Cost

The warm overlap check reads at most one small JSON file per other worktree plus a handful
of git files, with no git process: at most 50 ms for five other worktrees (a latency test
asserts it). The branch scan runs only at session start within its cap. The hooks keep their
sp1 budgets; a check that runs out of budget is skipped with "plumb: awareness skipped
(budget)" in the error log, never an error to the owner.

## 10. The merge boundary (SR-072, SR-077)

`merge_report` (sp3 9) gains three sections, so `plumb check --merge <base>`,
`plumb validate --merge`, `plumb merge-check` and both git hooks report them alike:

| Section | Content | Exit |
|---|---|---|
| `id_collisions` | two record files with one ID; record paths unmerged by an add/add; each with its paths and "/plumb merge-fix" | 1 |
| `unmerged` | record paths git left unmerged for another reason (modify/delete, an unparsable side, no driver), with the plain choices | 1 |
| `intent_conflicts` | every open `IC`, as its card (8.3) | 4 |

Exit precedence stays 1, then 5, then 4 (sp3). Legacy log lines not migrated are a warning
line. The report runs on the merge result: the working tree, including staged and
uncommitted changes, so it can run in the middle of a merge.

**pre-merge-commit hook.** `plumb merge-check --install-pre-merge-commit` and
`--uninstall-pre-merge-commit` mirror the pre-push hook (sp3 8): the shared hooks directory
(`git rev-parse --git-path hooks/pre-merge-commit`), a marker line, a foreign hook left
untouched with the line to call plumb from it. The hook runs
`plumb merge-check --hook pre-merge-commit`: the base is `HEAD` (the first parent), the
change is the staged merge result, the claims range is `HEAD..MERGE_HEAD`, and the full
suite runs once as in sp3 4 unless `merge.premerge_run_full: false`. A non-zero report
refuses the merge commit; the merge stays in progress. git runs this hook only when
`git merge` commits on its own; a merge stopped by a conflict and finished with
`git commit` is covered by the pre-push hook and by `/plumb merge-check`.

## 11. Owner entry points (R14, R15)

The owner never runs a shell command. Every SP6 capability is a `/plumb` command or plain
words; the agent runs the CLI:

| Capability | Owner says | Agent runs |
|---|---|---|
| Install the merge driver | `/plumb init` (plugin, R15) or "set up plumb here" | `plumb hooks install` |
| Fix ID collisions after a merge | `/plumb merge-fix` or "fix the ID clash" | `plumb merge-fix` (no owner words needed: it changes no intent) |
| See intent conflicts | `/plumb conflicts` or "what conflicts?" | `plumb conflicts` |
| Choose a side | "keep feat-x's version of the relay checks" | `plumb conflict choose ... --prompt ... --quote ...` |
| Check a merge | `/plumb merge-check` | `plumb merge-check` / `plumb check --merge` |
| Who else changes what | `/plumb status` or "is anyone else changing X?" | `plumb status` |
| The hooks at merge and push | "check merges before they are recorded" | `plumb merge-check --install-pre-merge-commit`, `--install-pre-push` |

Cards, hook lines and error messages name the `/plumb` command or the words to say, never a
shell command (R14). The CLI forms in this spec are the agent's interface. The feature to
owner entry point matrix (R14 deliverable) gains these rows.

## 12. Interfaces

```python
# plumb.ids (IDS)
def reserve(paths: PlumbPaths, kind: RecordKind | Literal["conflict"], count: int = 1) -> list[str]: ...
def peek(paths: PlumbPaths, kind: str) -> str: ...
def observe(paths: PlumbPaths, ids: Iterable[str]) -> None: ...
def state(paths: PlumbPaths) -> IdState: ...                  # high, recent, reserved: bool
def collisions(core: CoreAPI, base: str | None) -> tuple[Collision, ...]: ...
def approval_aliases(core: CoreAPI) -> Mapping[tuple[str, str], tuple[str, str]]: ...
#   (new id, current hash) -> (old id, pinned hash) for approvals carried by a renumber
def trailer_aliases(core: CoreAPI) -> Mapping[tuple[str, str], str]: ...  # (sha, old) -> new
def merge_fix(core: CoreAPI, *, dry_run: bool, from_ref: str | None) -> MergeFixResult: ...

# plumb.log (LOGS); signatures kept, ``since`` added
def append(paths, stream, kind, payload) -> LogEntry: ...
def read(paths, stream, kinds=None, since_offset=0, *, since: Collection[str] | None = None) -> Iterator[LogEntry]: ...
def verify_chain(paths, stream) -> list[str]: ...
def migrate(paths, *, dry_run: bool) -> MigrationReport: ...  # plumb.logcmd routes `plumb log`

# plumb.mergedriver (MERGEDRIVER)
def merge_texts(base: str, ours: str, theirs: str, *, labels: tuple[str, str],
                reserve_ic: Callable[[], str]) -> DriverResult: ...  # pure; result text, exit, notes
def open_conflicts(core: CoreAPI) -> tuple[IntentConflict, ...]: ...
def conflict_card(core: CoreAPI, conflict: IntentConflict, *, backend: Any = None) -> list[str]: ...
def stated_entries(core: CoreAPI, shown: Iterable[str]) -> list[dict[str, Any]]: ...
def install(root: Path, launcher: Launcher, *, dry_run: bool) -> list[str]: ...
def uninstall(root: Path, *, dry_run: bool) -> list[str]: ...
def status(root: Path) -> str: ...

# plumb.awareness (AWARENESS)
def publish(core: CoreAPI, changed_paths: Sequence[str], *, head_moved: bool | None = None) -> None: ...
def note_edit(paths: PlumbPaths, path: str) -> None: ...       # post-edit hook, no index
def overlaps(core: CoreAPI, mine: Iterable[str], *, deadline: Any = None,
             scan_branches: bool = False) -> tuple[Overlap, ...]: ...
def brief_lines(core: CoreAPI, deadline: Any) -> list[str]: ...
def delta_lines(core: CoreAPI, ids: Iterable[str]) -> list[Line]: ...  # keyed for present.delta
def snapshot_fields(core: CoreAPI, seen: Iterable[str]) -> Mapping[str, Any]: ...
```

New data classes (contracts, frozen, defaults on every field): `IdState`, `Collision`
(`id`, `paths`, `sides`, `how`), `MergeFixResult`, `MigrationReport`, `DriverResult`,
`IntentConflict` (`ic`, `record`, `title`, `fields`, `labels`, `hashes`, `merged`,
`proposed`), `Overlap` (`record`, `title`, `branch`, `worktree`, `how`, `other_hash`,
`at`). `LogEntry` gains `name`. `StatusSnapshot` gains `overlaps: int = 0`,
`overlap_labels: tuple[str, ...] = ()`, `conflicts: int = 0`. `MergeReport` gains
`id_collisions`, `unmerged`, `intent_conflicts`, `legacy_log_lines`. Config: `ids`
(`retries: 50`, `retry_s: 3`), `awareness` (`enabled: true`, `branches: true`,
`remotes: false`, `max_age_days: 7`, `branch_max: 8`, `branch_scan_ms: 400`,
`brief_lines: 3`), `merge.premerge_run_full: true`.

## 13. Latency and cost

| Path | Budget | How |
|---|---|---|
| Overlap check in the prompt and stop hooks (warm) | 50 ms, no git process | 9.5 |
| Branch scan at session start | 400 ms cap, 8 branches | 9.3 |
| Publishing in the stop hook | 2 git processes only when HEAD moved | 9.2 |
| Post-edit `note_edit` | within the 300 ms hook budget | append one path |
| Log read (warm) | one directory listing per kind plus new files | 6.3 pack cache |
| Log append | one file, one link, one fsync | 6.2 |
| ID reservation | about 0.1 to 0.2 s, only when a record is created | 4.2 |
| Merge driver | under 300 ms per conflicted record file | 7.2 |

No hook runs `merge-fix`, the migration or the driver.

## 14. Definition of done

1. Every SR of FEAT-006 has tests marked with its SR, at least one per example, and the
   entry-point tests of 4.5 and 5.3.
2. **A real two-worktree scenario** (`tests/integration/test_parallel_e2e.py`, a temporary
   repository, real `git worktree add`, the real driver configured by `plumb hooks install`):
   worktrees A (`main`) and B (`feat-x`) create records at the same time and get distinct
   IDs; both append approvals, prompts and test runs; B edits SR-001's statement and adds a
   link to SR-002 while A edits SR-001's statement differently and changes SR-002's title;
   A's brief and prompt delta say SR-001 is also being changed on branch feat-x, once;
   merging B into A conflicts on nothing under `.plumb/log/`, merges SR-002 field by field,
   and turns SR-001 into an intent conflict with both statements; `plumb check --merge`
   exits 4 with the card; the owner's choice (terminal path, faked tty as in
   `tests/core/test_owner_terminal.py`) resolves it, and the check no longer lists it.
3. **A clone scenario** in the same file: a `git clone` creates SR-00N while the origin
   creates SR-00N; merging the clone's branch stops on the add/add; `plumb merge-fix`
   renumbers the incoming record, rewrites its references and markers, maps its trailers
   (history unchanged), carries the clone owner's approval of unchanged content; the check
   shows no collision.
4. plumb's own logs are migrated in one commit: 510+ events and 18+ evidence entries become
   files with unchanged digests; `plumb validate` is clean; `plumb verify` reuses the same
   evidence; a lane branch made before the migration merges cleanly afterwards, and a second
   `plumb log migrate` moves its new lines.
5. The hook latency tests still pass, with the overlap check under 50 ms warm for five
   worktrees and no git process on the prompt path.
6. No owner-facing text instructs a shell command (R14); every new owner-only write
   (`plumb conflict choose` without `--prompt`) has the exit-3 test with no marker and stdin
   a pipe holding "y".
7. `docs/concept.md` 4.3, 4.7 and 7.5 and the README describe the shipped behaviour; medium
   and low findings are in `docs/followups.md`.

## 15. Out of scope

- Pushing or fetching `refs/plumb/ids` between clones; clones meet at `plumb merge-fix`.
- Any lock, lease or admission across worktrees; any service.
- Rewriting history, or editing a committed log entry.
- Awareness of remote-tracking branches by default (opt-in `awareness.remotes`) and of other
  clones.
- Automatic resolution of intent conflicts by JEV or the agent: the judgment is advisory and
  only the owner chooses.
- Merging non-record files under `.plumb/` (`config.yaml`, `claims.yaml`) beyond git's text
  merge.
