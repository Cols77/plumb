# Sub-project 5 spec: presentation, context economy and owner commands

Status: implementation spec, written 2026-10-06. The owner does not review it (D11); verifier
agents check it against the owner intent brief, rulings R1 to R12 (R9 above all) and
`docs/concept.md` (D13, sections 6 and 9). Quotes and rulings win, then the concept, then
this spec. Lane PRESENT of `docs/plans/next-plan.md` builds it. Requirements: `FEAT-005`,
`SR-061` to `SR-068`, all proposed; it builds on `SR-032` (deduplicated delta) and `SR-033`
(`plumb explain`), which sub-project 1 shipped.

## 1. Outcome

The owner's words for this sub-project (ruling R9):

> "isnt there a smarter way ... Isnt the risk to bloat the context way too fast with
> redundant tokens?"

> "a proper way to present the relevant information to the user, but only when it is
> important. Otherwise it should only be small card that indicates status and intent summary
> perhaps, which should be collapsible or configured to be disabled."

> "the user don't necessarily know the code, the coding agent always handles the abstraction
> between user's mental model of the system and the actual system. All the commands should be
> designed to handle this properly."

> "use obsidian as the frontend perhaps?"

At the end of sub-project 5:

- every hook output is a deduplicated delta within a token budget, and details come only on
  demand (SR-063, building on SR-032);
- the owner sees a one-line **status card** by default, and the full **intent card** only
  when it matters; both are configurable `full | compact | off` (SR-061, SR-062);
- owner commands are plain-language slash commands executed through the agent:
  `/plumb explain`, `/plumb status`, `/plumb review`, `/plumb confirm`, with IDs and paths
  still accepted and never required (SR-064, SR-065);
- the R8 commands of sub-project 2 reach the owner in their terms: `/plumb review` shows the
  triage groups, `/plumb confirm` drives the grouped and the per-record confirmation, and
  every view says "confirmed by you" or "confirmed by JEV";
- `plumb align [scope]` judges each edge of the intent-to-evidence chain, weakest first
  (R12.2, SR-067);
- `plumb view` writes a generated Obsidian vault and a Canvas intent map (SR-066);
- the `/plumb why` bug stays fixed, and no command is advertised that the build lacks
  (SR-068).

## 2. Owner intent served

| Ruling or decision | Where |
|---|---|
| R9 CONTEXT ECONOMY: compact deduplicated delta, progressive disclosure, per-turn token budget, nothing when nothing is new, session state of seen hashes | 3 |
| R9 USER CARD: one-line status card by default; the full intent card only when it matters; `full \| compact \| off` | 4 |
| R9 THE USER'S MENTAL MODEL: plain-language arguments; answers in the owner's terms; slash commands through the agent; the raw CLI stays the agent's interface | 5, 6 |
| R9 DEEP REVIEW (Obsidian): vault, index notes, Canvas, generated and idempotent, editing never approves | 7 |
| R9 BUG: `/plumb why` | 6.4 |
| R8 A and B as the owner sees them; "the status line and brief distinguish 'confirmed by you' from 'confirmed by JEV'" | 4.1, 6.3 |
| R12.2 EDGE ALIGNMENT, "shown in /plumb review and in the Obsidian view (edge badges)" | 8 |
| R1, R2: confirmation non-blocking and only by the owner's explicit words | 6.3 |
| D5 "A": few, meaningful interruptions | 4.2 (the intent card appears only on the triggers) |

## 3. Context economy (SR-063)

Sub-project 1 made the prompt hook inject one line per record (ID, state, title), only when
the record is newly relevant in the session or its hash or confirmation state changed, within
`hooks.prompt_tokens` (200), nothing when nothing is new, with `/clear` and compaction
resetting the seen set (SR-032), and the session brief a few lines plus a pointer. This
sub-project extends the same rule to every agent-facing output, at one choke point:

- **One emitter.** All agent-facing lines from any hook go through
  `present.delta.emit(ctx, lines, kind)`. It keys each line by `(kind, record id, record
  hash, state)` or, for lines with no record, by the line's digest; it drops a line already
  emitted this session with the same key; it enforces the per-turn budget
  (`hooks.prompt_tokens` for the prompt hook, `hooks.stop_tokens`, default 150, for the
  stop hook's agent instructions); a line cut by the budget is named with `plumb show` and is
  not marked seen. The prompt, stop and session-start hooks, and the host-neutral API (9),
  use only this emitter.
- **Instructions too.** The intent-change instruction, the compare line, the untraced-change
  instruction, escalation suggestions, ownership proposals and drift hints are deduplicated
  the same way: the agent gets each once per session per state, not every prompt.
- **Progressive disclosure.** Examples, covering tests and evidence never ride along in the
  delta; the agent pulls them with `plumb show <ID>` or the MCP `plumb_show` tool. The skill
  says so in one line.
- **The session brief** stays a few lines and a pointer (`hooks.session_brief: compact`),
  never a list of every proposed record; with R8 A it adds at most one line, the triage
  offer ("4 records rated faithful to your words await you: plumb triage").
- **Measure.** A test drives 10 prompts about the same three records and asserts that the
  records' lines appear once each, that a changed record reappears once, and that total
  injected characters stay under the budget times the number of turns with something new.

## 4. Cards (SR-061, SR-062)

### 4.1 Status card (default)

One line, owner-facing, in the status line and as the first line of the end-of-turn summary:

```
plumb ✓ aligned · "add multiply next to add" · SR 12/14 ok (2 by JEV) · 1 awaits you
```

- the state glyph and word: `✓ aligned`, `● awaits you`, `▲ drift`, `✗ failing` or
  `✗ regression`, by precedence regression > failing > awaits you > drift > aligned;
- a plain-language intent summary: the title (or the first clause of the read-back) of the
  intent this session is working on (the most recent `INT` touched or captured in the
  session), clipped to 40 characters, never a code term;
- counts that distinguish "confirmed by you" from "confirmed by JEV" (`(2 by JEV)` appears
  only when auto-approvals exist), and what awaits the owner;
- `full pending` and `auto-approve suspended` when they hold.

ASCII fallback (`cards.ascii: true`, or a terminal that cannot encode the glyphs):
`plumb | aligned | "add multiply next to add" | SR 12/14 ok (2 by JEV) | 1 awaits you`.
The status line still recomputes nothing: it renders `status.json`, which gains the fields
of 9 (`intent_summary`, `confirmed_by`, `state`).

### 4.2 Intent card (only when it matters)

The full card appears in the owner-facing summary only when one of these holds:

1. a new or changed intent awaits the owner (an `INT` or `SR` captured or edited this turn,
   still proposed);
2. one of the three triggers: a real intent change (trigger 1), an unconfirmed decision that
   matters (trigger 2: a `matters: true` DEC, an escalated set awaiting approval, the
   requirements a merge boundary needs), or a regression (trigger 3);
3. the owner asked (`/plumb explain`, `/plumb review`, `/plumb confirm`).

Format (the owner liked it; R9):

```
▸ Intent  INT-016 "add multiply"   (proposed — say "ok" to confirm)
  Will: multiply(a, b) returns a * b · Won't: floats · Assumed: integers only
  Examples  EX-1 given 2 and 3, multiply returns 6  EX-2 given 0, returns 0   (proposed)
  Tests  tests/test_calc.py::test_multiply  ✓ passing
```

- Line 1: kind, ID, the title in the owner's words, and the state with the action
  (`proposed — say "ok" to confirm`, `confirmed by you`, `confirmed by JEV — say "revoke" to
  undo`, `changed since you confirmed it`).
- Line 2: will, won't and every labelled assumption (an INT) or the statement (an SR).
- Line 3: every example (given/when/then, compact), with their state.
- Line 4: covering tests and their evidence (`✓ passing`, `✗ failing`, `○ not yet run`,
  `◌ not yet passing`).
- A trigger card says why it is shown on line 1 (`▸ Question  DEC-014 ...`,
  `▸ Regression  tests/test_calc.py::test_add ...`).

A card shows its record in full or not at all, so the stated-set rule (shown in full before a
bare "ok" can confirm it, sp1 6.4) keeps holding: the card is the "shown" form. At most
`hooks.summary_proposed_cap` (3) cards per summary; the rest are named with the command that
prints them, as today.

### 4.3 Verbosity: `full | compact | off`

`present.card: compact` (default):

| Mode | Status card | Intent card | Summary lines |
|---|---|---|---|
| `full` | always | on every turn that touched or captured intent, plus the cases of 4.2 | the sp1 five-line summary under the card |
| `compact` | always | only in the cases of 4.2 | at most two lines besides cards |
| `off` | status line only (no summary line) | only for the triggers (4.2 item 2), never for item 1 | none, except a trigger question |

`off` never hides a trigger: an interruption the owner must answer still shows its card.
`plumb config card full|compact|off` sets it (agent or owner; it is a display preference, not
a guarantee). "Collapsible": the card is the expanded form of the status card; hosts that
support collapsing render it collapsed after the first view of the same hash.

## 5. The owner's mental model: plain-language resolution (SR-064)

`plumb resolve <words> [--kind K] [--json]` maps the owner's words to records, paths and
tests: exact IDs and paths first; then record titles, statements, examples, quotes and
feature names by term overlap (`text.terms`), then file and symbol names; ranked, with a
confidence and the reason ("matched the title of SR-004"). Every owner-facing command
(`explain`, `impact`, `show`, `review`, `confirm`, `align`, `view --scope`) accepts plain
words through it. When the best match is not clearly ahead (the top score below
`resolve.min_score`, or within `resolve.margin` of the second), the command lists the
candidates in the owner's terms and asks which one, instead of guessing; this is an answer to
the owner's own request, not an interruption.

Answers use titles, the owner's quotes, will/won't, examples and test states; code paths
appear only when the owner asks or when no record exists.

## 6. Owner slash commands (SR-064, SR-065, SR-068)

### 6.1 Executed through the agent

`/plumb <verb> <words>` is a slash command the owner types; the agent executes it with the
raw CLI (the agent's interface) and answers in the owner's terms. The installed command file
(`.claude/commands/plumb.md`, and the Pi and Hermes command registrations of sp4) lists:

| Owner types | The agent runs | The owner gets |
|---|---|---|
| `/plumb` or `/plumb status` | `plumb status --card` | the status card, what awaits them, drift in one or two lines |
| `/plumb explain <anything>` (alias `why`) | `plumb explain <words>` | why it exists: the owner's words it comes from, decisions, examples, test state |
| `/plumb review [<anything>]` | `plumb review [<words>]` | the deep review (6.2) |
| `/plumb confirm [<anything>]` | `plumb confirm [<words>]` | the confirmation flow (6.3) |
| `/plumb impact <anything>` | `plumb impact <resolved>` | what a change would reach |
| `/plumb view` | `plumb view --open` | the Obsidian vault (7) |

### 6.2 `/plumb review`

`plumb review [words] [--json]` prints, scoped to the words when given (resolved by 5):

1. what awaits the owner: the triage groups of sp2 (low-risk group first, then each riskier
   record with its rating and reason), escalated sets awaiting approval, decisions that
   matter;
2. approvals not typed by the owner (agent-relayed, by JEV) since the last merge evidence,
   for a glance, with the revoke form;
3. drift: stale links, unconfirmed edits, failing acceptance tests, hidden-dependency and
   ownership hints (from sp2);
4. alignment: the `plumb align` result for the scope, weakest edges first (8);
5. the merge state: `merge_report(run_full=False)` against `merge.default_base` (sp3),
   summarized in one line.

### 6.3 `/plumb confirm` (SR-065)

Confirmation stays explicit (R2, R9 "Confirmation stays explicit (`plumb triage` / "ok" in
chat)"). The command never approves by itself; it prepares what the owner's own words then
confirm:

- `/plumb confirm` with no words: the agent runs `plumb confirm`, which shows the triage
  offer (the low-risk group, every ID named) and each riskier record as an intent card, and
  records them in the stated set. The owner's next "ok" (or "ok SR-034") is relayed with
  `plumb relay --group low-risk` or `plumb relay <IDs>`, with the R2 checks.
- `/plumb confirm SR-034 INT-017`: the owner's prompt names the IDs and contains an
  affirmation term ("confirm"), so the agent relays it at once
  (`plumb relay SR-034 INT-017 --prompt D --quote "/plumb confirm SR-034 INT-017"`), exactly
  as for "ok SR-034" (sp1 5.6).
- `/plumb confirm the login thing`: plain words name no ID, so the agent runs
  `plumb confirm the login thing`, which resolves the words (5), shows each matched record as
  an intent card in the owner-facing summary (so it is "shown" in full), and puts them in the
  stated set. The owner's next affirming prompt confirms them. One step more, because the
  owner must see what they confirm.
- The owner's terminal: `plumb triage --approve low-risk` and `plumb approve` (sp2, sp1).

### 6.4 The `/plumb why` bug, and nothing unavailable advertised (SR-068)

Sub-project 1 fixed the bug (SR-033): `why` is an alias of `explain`, routed, and the
installed `/plumb` command routes `why <anything>` to `plumb explain`. This sub-project adds
the regression test that keeps it fixed: for every verb the installed command file and
`plumb --help` advertise, the command is routed in `cli.ROUTES` and `plumb <verb> --help`
exits 0. The help text never lists a command the build lacks.

## 7. `plumb view`: the Obsidian vault (SR-066)

`plumb view [--out DIR] [--scope words] [--open]` writes "la grappe d'artefacts" as an
Obsidian-compatible vault, by default to `.plumb/view/` (gitignored, generated):

- one note per record, `<ID>.md`, with frontmatter `{id, kind, title, state, confirmed_by,
  hash, feature, badges}` and a body in the owner's terms: the quote, the read-back, will,
  won't, assumptions, examples, tests with evidence, code ends, and `[[wikilinks]]` along the
  chain INT -> SR -> EX -> tests -> code (example notes `SR-034.EX-1.md`, test notes
  `test--<node>.md`, code notes `code--<path>.md`, each with backlinks);
- badges as tags and callouts: `#stale`, `#failing`, `#proposed`, `#confirmed-by-jev`,
  `#awaits-you`, `#hint`, and edge-alignment badges from `plumb align` (8) on the links;
- index notes: `index.md`, `by-feature.md`, `awaiting-you.md` (with copyable confirm commands
  `plumb triage --approve low-risk`, `plumb approve SR-034`, for the owner's terminal),
  `drift.md`;
- `intent-map.canvas` (JSON Canvas 1.0): one node per INT, FEAT and SR (file nodes pointing
  to their notes), edges for `derives_from`, feature membership and `upstream`, colored by
  state (confirmed green, proposed yellow, stale or failing red), laid out deterministically
  (intents in a column, features beside them, requirements in a grid per feature).

It is generated, never hand-edited: every file starts with a "generated by plumb view; edits
are overwritten" line, regenerating is idempotent (byte-identical output for the same records
and evidence, files of records that no longer exist removed), and editing a note never
approves anything: plumb never reads the vault. `--open` opens the vault folder with the
platform's opener (or `obsidian://open?path=...` when Obsidian is registered); in tests it is
not called.

## 8. `plumb align [scope]` (R12.2, SR-067)

- **Collect, deterministically.** The scope (plain words, a feature, an INT or an SR,
  resolved by 5; default: everything touched since `merge.default_base`) is expanded along
  existing links: intent -> feature -> requirement -> example -> test -> code -> evidence.
  The collection has a fingerprint (sorted node hashes and edges). Families with no member
  (an SR with no test, an example with no evidence) are reported as named gaps
  (`gap: SR-034/EX-2 has no test`).
- **Judge each edge once.** One question per edge, phrased for its edge class (Noul, sp2
  `ask`): INT -> SR "does this requirement serve this intent?", SR -> EX "does this example
  illustrate this requirement?", EX -> test "does this test check this example?", SR -> code
  "does this code realize this requirement?". Edges are listed weakest first.
- **Edges stay deterministic.** Whether an edge exists comes from the links only; judgments
  never create or remove an edge, never mark staleness and never confirm.
- **Degraded.** With the heuristic, each edge gets a term-overlap score labelled
  `heuristic`; with no backend, "no judgments available" and only the gaps.
- Results are cached by fingerprint and logged as `judgment` events when they come from JEV;
  shown in `/plumb review` and as edge badges in the vault.

## 9. Interfaces

PRESENT owns, after phase 0 of the plan:

```python
# plumb.present.api — read-only views used by the CLI, the MCP server (sp4) and /plumb review
def brief(core, *, full: bool = False) -> list[str]: ...
def relevant(core, text: str, limit: int = 5) -> list[dict]: ...      # {id, state, title}
def show(core, ids: Sequence[str]) -> list[str]: ...
def explain(core, query: str) -> dict: ...                           # {lines, ids, resolved}
def impact(core, ref: str) -> dict: ...
def drift(core) -> dict: ...                                         # signals + sp2 hints
def resolve(core, words: str, *, kind: str | None = None) -> Resolution: ...

# plumb.present.render — the output contract every host renders (sp4 5)
def status_card(snapshot: StatusSnapshot, *, ascii: bool = False) -> str: ...
def intent_card(card: IntentCardData, *, mode: CardMode = "compact") -> list[str]: ...

# plumb.hosts.neutral — the host-neutral turn API (sp4 3.1)
def handle_event(event: TurnEvent) -> TurnOutput: ...
```

`StatusSnapshot` gains `state`, `intent_summary`, `confirmed_by: {owner, agent-relayed,
auto-jev, import}`, `auto_approve: on|off|suspended` (defaults keep old snapshots readable).
PRESENT consumes `plumb.capture.api` (sp2 11.1) for card data, triage, flags, escalation,
hints and confirmation counts, and `plumb.boundary.merge_report` (sp3 9), each imported
lazily with a degraded line when missing (`plumb: triage unavailable`).

## 10. R10 compatibility

The vault is generated and gitignored, so it never conflicts between worktrees. The emitter's
seen set is per session directory. Cards render whatever records exist; when SP6 adds intent
conflicts, they are one more card kind (`▸ Conflict`), with no change to the modes.

## 11. Definition of done

1. The emitter test of 3 passes, and the prompt, stop and session-start hooks emit agent lines
   only through it.
2. Card tests: the status card for each state (glyph and ASCII), `(2 by JEV)` shown only with
   auto-approvals; the intent card format of 4.2; the mode table of 4.3, including that `off`
   still shows a trigger card.
3. `plumb resolve`, `review`, `confirm`, `align`, `view` exist with tests marked with their
   SR; `explain`, `impact` and `show` accept plain words.
4. `/plumb confirm` tests: no approval is written by `plumb confirm`; plain words put the
   resolved records in the stated set as shown; a relayed "ok" then confirms exactly them.
5. `plumb view` twice gives byte-identical output; a note edit changes no record state; the
   canvas validates as JSON Canvas (nodes, edges, ids unique).
6. The routing test of 6.4 passes for every advertised verb.
7. Hook benchmark on plumb's own repository stays within the sp1 budgets.

## 12. Out of scope

- Data computation for triage, flags, escalation and hints (sp2): PRESENT renders them.
- Adapters for other hosts (sp4): they render this sub-project's output contract.
- Any approval path; the vault and the cards never approve.
- A web UI or server; Obsidian is the deep-review frontend, read-only.
