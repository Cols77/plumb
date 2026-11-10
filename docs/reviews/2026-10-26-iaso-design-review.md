# iaso design review, 2026-10-26

Input for an intent loop (`/iaso intent <words>`), not a plan. Each finding names the
owner's principle it bears on (`docs/specs/v2-principles-confirmed.md`), the evidence, the
options with a recommendation, and the one question the loop should put to the owner. Only
critical and high findings are listed; smaller ones are counted at the end.

What this repo does: iaso keeps a coding agent's work tied to what the owner asked for. It
stores the owner's intent as small records under `.iaso/`, has a background model judge
approve them, links them to code and tests, and holds a merge until the links and tests agree.
It ships as a Claude Code plugin (hooks, a panel, five skills, one `/iaso` command) and as
a CLI with adapters for Codex, Pi and Hermes. Load assumed: one owner, one or a few agent
sessions at a time, on one Windows machine with a slow file system.

Size, for scale: 57,700 lines of Python in `src/` (259 files, 19 packages), 57,400 lines of
tests (364 files), a 2,000-line TypeScript panel, a 1,400-line Svelte browser workspace,
about 90 CLI verbs. The repository tracks 45,356 files, of which 43,850 are log entries.
Records: 37 INT, 166 SR, 231 DEC, 8 FEAT, 3 NC; 18 confirmed, 415 proposed, 12 edited since
confirmation.

Method: the audit mapped the hot paths that run on every turn (the prompt, pre-tool,
edit-check and stop hooks; `clarify --wait`; the judge worker and its dispatcher), the plugin
bundle and its skills, the records' state, the hook error log and the logs' shape. The
plugin-dev validator and skill reviewer were run on `plugin/`. Not read in full: the browser
workspace, the Obsidian view, the importer, the benchmark, the Codex, Pi and Hermes adapters,
`understand/judge.py` beyond its surface, and the 57,000 lines of tests.

---

## Critical

### 1. The stop hook hits its 90-second watchdog on almost every turn

Principle: P12 (iaso shows the owner little), P13 (background work, visible progress), P1.

**What happens.** `.iaso/session/errors.log` holds 1,708 entries; 630 are watchdog cuts, 392
of them on the stop hook. On the last three working days every stop-hook error was a cut at
the hard limit:

| day | stop-hook errors | of which "hard limit 90.0s reached" |
|---|---|---|
| 2026-10-23 | 35 | 35 |
| 2026-10-24 | 42 | 42 |
| 2026-10-25 | 34 | 34 |

The prompt hook was cut 193 times and the session start 34 times over the same log. A cut
drops the cards and the summary, so the owner sees the read-back only, after a 90-second
wait at the end of each turn. The README still promises "a soft budget near the 2-second
ceiling and a 1.9 s watchdog" and the plugin's `hooks.json` gives every hook, the pre-tool
gate included, a 120-second host timeout.

**Why.** The defaults in `src/iaso/config.py` give every hook a 60-second soft budget and a
90-second hard limit (`DEFAULT_HOOK_BUDGET_MS`, `HARD_LIMIT_S`), so a slow turn is "normal"
and no debug case opens for it (a watchdog cut is logged by `hookio.log_error` only; a raised
error would open a case under SR-325). The stop hook's work grows with the repository.
Measured on this machine, warm cache, no other load:

| step | time |
|---|---|
| `iaso brief` (what the session-start hook prints) | 26 s |
| `iaso show SR-260` | 7 s |
| `open_core` + `core.index()` (457 records) | 0.9 s |
| `core.events()` (59,423 log entries read from disk) | 4.5 s |
| `core.link_states()` (2,179 links hashed) | 3.5 s |
| `git status` over 45,356 tracked files (the hook allows 5 s) | 2 s |

Every iaso process, hook or command, pays the events and link-states cost again: nothing is
cached across processes except the file-hash stat cache. The stop hook does all of the
above plus the covering-test selection over a 6.6 MB test map and the summary of the
understanding layer. See finding 2 for the largest part of that growth.

**Options.**
- A. Measure each stop-hook step once (a timing line per step in `errors.log` when a cut
  happens), then move everything but the read-back and the block decision off the stop hook
  into the detached worker, as P13 already says for model work. Recommended.
- B. Lower the budgets back to a few seconds and accept that the stop hook says less.
- C. Keep 90 seconds and show a progress bar for the wait.

**Question for the owner.** At the end of a turn, how long may iaso keep you waiting before
you would rather have less? (Seconds, or "never: do it in the background".)

### 2. The logs are 97 % of the repository's tracked files

Principle: P15 (iaso keeps the repository fit).

**What happens.** `git ls-files` counts 45,356 files; 43,850 are under `.iaso/log/`:
19,770 `judgment/` entries, 23,546 `offer/` entries, 4,553 `repin/`, 1,780 `test-run/`;
296 MB on disk. Each `judgment/` and `offer/` kind has exactly one archive segment, so the
compaction P15 asks for ran once and never again. `core.events()` reads all 59,423 entries
in every iaso process (4.5 s, finding 1). Every `git status`, every merge, every checkout
and the record merge driver pay for these files too. The owner's session start says
"untracked log in main holds merges" (a memory from 2026-10-18), which is the same problem
seen from the merge side.

The `offer/` kind is also a defect, not only a volume: 4,000 of its entries were written on
2026-10-25 alone, all `"surface": "browser"`, one per time a card was drawn in the browser
workspace (sample: card `regression:a0163ea53c28`, record SR-028). A card drawn by a polling
page should not be a log entry each time.

**Why.** One file per log entry was chosen so branches never conflict on a log (README,
"Logs never conflict"). That is right for the few owner-facing kinds (approval, question
answers, decisions). It is wrong for the two machine kinds that are written at every
judgment and every offer: they are telemetry, not intent, and nothing reads them back except
`validate` for the hash chain.

**Options.**
- A. Compact `judgment/` and `offer/` into their archive segment at every landing (the P15
  tidy job), and stop tracking the live entries of those two kinds in git (`.gitignore`,
  the segment stays tracked). Recommended; the archive code exists (`iaso.log.archive`).
- B. Stop writing `offer/` entries at all (23,546 entries, no reader found outside
  `validate`).
- C. Keep everything and move the logs out of git into `.iaso/cache/`.

**Question for the owner.** Which logs must stay in git for you: only the ones that record
your words and answers, or every judgment iaso made?

### 3. The approval loop does not converge: 415 of 445 records stay proposed

Principle: P3 (a validated interpretation counts), P9 (the fast track), P7 (few records).

**What happens.** `iaso status --json` reports confirmation `proposed: 415, confirmed: 18`.
The session brief says "waiting on a judge: 427 records" and "33 questions await you"; one
session's question store holds 24 open questions. The 2026-10-16 intent-loop spec set the
target at "about thirty records"; there are 445. The merge check holds any fast-forward that
touches an unconfirmed record (memory, 2026-10-15), so nearly every merge now waits for a
judge that has not approved, and the owner parks merges on side branches.

**Why.** The fast track is structurally out of reach. JEV is asked whether the owner's
logged words *entail* the formal record (`capture/autoapprove.py`: every part strictly above
0.9 and labelled high). P3 says the agent must reword the owner's approximate words into a
coherent, formal requirement, so the record always says more than the words did. The last
3,000 entries in `.iaso/log/judgment/`, the record-approval action only:

| action, claim kind | verdict | count |
|---|---|---|
| faithfulness, example-restatement | not-entailed | 787 |
| faithfulness, example-restatement | entailed | 0 |
| faithfulness, intent-readback | not-entailed | 16 |
| faithfulness, intent-readback | entailed | 0 |

698 of those "not-entailed" verdicts carry a probability of 0.9 or more (example: SR-362,
probability 0.97, label high, tier accept): the judge is confident, and confident that the
agent's restatement does not follow from the owner's words. Of the 35 live approval entries,
33 are `auto-model` (the Haiku fallback), 1 is the owner's, 0 are `auto-jev`. The fast
track has never fired, and it cannot while the question it asks is entailment. Every
not-entailed verdict goes to the judge model, which asks the owner. Questions never expire, are not capped per
session, and are asked again at each `clarify --wait` until answered, so they pile up faster
than one owner answers them. Nothing in the cascade approves a record by the owner's silence
or by time, and nothing retires a question whose record was later superseded. At the same
time the agent keeps creating records: 231 decisions, many of them "I assumed A" lines that
P3 says should be assumptions, not records waiting on a judge.

**Options.**
- A. Change what a judge question costs: at most N open questions per session (the rest
  wait, oldest first), a question is withdrawn when its record is superseded or edited, and
  a record the judge scored above a lower bar (say 0.75) with no contradiction is approved
  as "judge-approved, low" rather than asked. Recommended.
- B. Make "proposed" stop holding the merge for records the merge does not change
  (confirmed records keep their hold).
- C. Change what JEV is asked: not "do the owner's words entail this record" but "does this
  record contradict the owner's words or add intent they did not give" (the `benign` and
  `extends` verdicts already exist). A benign extension is approved as judge-approved; only
  `contradicts` and `extends` with new intent ask. This is what P3 describes and what the
  current question does not test.
- D. Calibrate JEV on the owner's past answers (`iaso jev calibrate` exists; 14
  calibration entries) and raise or lower 0.9 from the measurement.

**Question for the owner.** Your words are approximate and the records are formal, so a
record almost never follows word for word from what you said. Should the judge approve a
record that adds nothing you would object to (benign), and ask you only when it contradicts
you or adds intent you did not give?

### 4. The plugin's version never changes, so the installed plugin never refreshes (KI-7)

Principle: P14 (each host installs its own things), P1.

**What happens.** `pyproject.toml`, `plugin/.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json` and the vendored wheel all say `0.1.0`, unchanged since
2026-10-05, through 1,006 commits. Claude Code's plugin cache keys on the version, so a
`/plugin update` sees nothing new; the private environment is keyed on the wheel's sha256
(`plugin/bin/iaso`) and would rebuild, but it never sees the new wheel. Known issue KI-7
("behaviour fixed in main still shows; stuck at 0.1.0") is open, and the owner's session
notes record it as the reason fixes seem not to land.

**Why.** `scripts/build_plugin.py` copies the version from `pyproject.toml` and nothing bumps
it. The build is run on every change, so the wheel's sha256 changes while its version does
not.

**Options.**
- A. Derive the version at build time from git (`0.1.<commit count>` or `0.1.0+<short sha>`)
  and write it to the four places; one function in `build_plugin.py`. Recommended.
- B. Bump by hand before each landing (a step the landing coordinator will forget).

**Question for the owner.** None; this is a defect against KI-7. One decision only: a version
that counts commits (`0.1.1006`) or one that names the commit (`0.1.0+9519a7f`)?

### 5. An ordinary message blocks the agent on a model call, then on the owner

Principle: P6 (outside the loop the gate closes only on a contradiction), P13 (model work in
the background), and the study's own claim.

**What happens.** The study "What iaso does, from request to landed change" teaches: "the
judge never blocks the agent while it works (it runs as a background job)". The code does the
opposite on every ordinary message:

- `iaso clarify --wait` (`understand/cmd_clarify.py`, `_judged`) runs the pending judge
  jobs in the agent's own process (`worker.run_once`) before answering, and each job is one
  `claude -p` subprocess with a 120-second timeout that grows on each retry
  (`understand/dispatch/claude_code.py`, `budget_scale_for`). The skills tell the agent to
  run this command first on every message and to run it again on `waiting`.
- The ask gate (`hosts/claude_code/ask_gate.py`) then refuses every edit and every shell
  command that is not on its read-only list until the agent has put the judge's questions
  to the owner, so one unanswered question about an old record stops unrelated work.

Together with finding 3 this is the owner's daily experience: a message, a wait, questions
about records from other days, then the work.

**Why.** SR-361 ("every judge question is asked as soon as it is raised") was implemented as
a gate on the agent's tools, which is stronger than P6 allows and than the study says. The
synchronous run inside `--wait` was a shortcut so the first answer is not "waiting".

**Options.**
- A. Judge jobs always run in the detached worker; `clarify --wait` answers at once with what
  is known; questions reach the agent as text at the next prompt and are asked between
  tasks; the gate closes only on a contradiction with a confirmed record, as P6 says.
  Recommended.
- B. Keep the ask gate but scope it: only questions about records this request touches hold
  edits.
- C. Keep it as it is and correct the study.

**Question for the owner.** May the agent keep working on your request while iaso's judge
still has questions about other records, as long as it asks them before the turn ends?

---

## High

### 6. The skills contradict each other on how questions are asked

Principle: P5, P6, P12.

**What happens.** From the skill review of `plugin/skills/*` and `plugin/commands/iaso.md`:

- iaso-clarify says "every question at once, as soon as it is raised" (rule 1), "One
  question at a time, grill-style" (Discipline), "at most three in a turn" and "between
  tasks, never in the middle of one" (the `ask` state), and "as soon as raised" again. An
  agent cannot do all four; it picks one per turn.
- iaso-clarify says "Outside a spec session you never ask the owner anything" and, twenty
  lines later, "Any other quick question ... goes to the owner with Claude Code's question
  tool".
- `/iaso clarify <words>` runs `iaso clarify --wait` in two skills and `iaso intent open
  --wait` in the command.
- The fourteen-line "Questions and approval" block is pasted into five files and has already
  drifted (iaso-records has a rule 5 the others lack).
- Two skills say "Use on every owner request" (iaso-records and iaso-clarify), so about
  16 KB of rules load on every turn, on top of the same loop described in `AGENTS.md`.
- iaso-intent tells the agent to run the loop as Workflow phases, but stage A needs the
  question tool, which a workflow agent does not have (rule 3 then says "stop asking"), and
  the owner's global instructions require an explicit opt-in before a workflow runs.
- Terms the agent must act on are never defined for it: band, room, loop pane, card, stale
  link, repin, relink, reword, IC, "two readings"; and record ids (DEC-207, SR-370) are
  cited in skills installed into repositories that do not hold those records.

**Options.**
- A. One owner of each rule: the per-message loop and the question rules live in
  iaso-records only; iaso-clarify triggers only when a request creates or changes intent
  or a spec session is accepted; one sentence states how questions are asked; a ten-line
  glossary reference; record ids out of skill text. Recommended.
- B. Merge iaso-records, iaso-clarify and iaso-intent into one skill with references.

**Question for the owner.** One rule for questions: all of them in one question-tool call
when the check returns them, between tasks; or one per message, grill-style? (The rest
follows from the answer.)

### 7. The product is far larger than what it has confirmed

Principle: P7 (few records), P15 (fit), P14 (any host) and the ponytail rule that every line
must be read, tested and fixed later.

**What happens.** For 18 confirmed records the repository carries:

| part | size | evidence of use |
|---|---|---|
| `understand/` (the judge cascade, cards, questions, recovery, eval) | 10,500 lines, 48 files | the core loop (findings 3 and 5) |
| `awareness/`, `boundary/`, `mergedriver/`, `ids/` (parallel work) | 10,800 lines | used daily by the owner's worktrees |
| browser workspace (`browser/`, `ui/`, `tests/browser`) | 970 + 1,400 lines, built assets committed | 5 `browser-hello` log entries |
| panel mod (`mod/`, `plugin/hooks/*.ts`) | 1,000 + 2,000 lines | 10 `mod-hello` entries |
| Codex, Pi, Hermes adapters (`hosts/`, `docs/hosts.md`) | 880 lines + templates | no prompt logged from any host but Claude Code |
| pi-agent-factory importer | 1,500 lines | none seen |
| benchmark (`evaluate/`) | 540 lines | 21 `eval-run` entries |
| Obsidian view, MCP server | 460 + 500 lines | none seen |
| video studies (`study/video.py`, two vendored Manim skills) | 960 lines + vendor | one study, two clips |
| three copies of one guard (`guard.py`, `bin/gate.sh`, `hooks/guard.gen.ts`) and a bespoke shell parser for "read-only" commands (`ask_gate.py`) | 1,000 lines | finding 5 |

Each of these parts has its own records, tests and drift, and each adds to the 90-second
stop hook and the 415 proposed records. `docs/concept.md` (1,246 lines) and
`docs/fork-plan.md` are still in the tree although P15 says the records are the only
specification.

**Options.**
- A. Name the core (records, judge, links and tests, the merge hold, the Claude Code plugin)
  and freeze the rest: no new records, no new tests, retired when it next breaks. Move the
  browser workspace, the importer, the benchmark, the MCP server and the Obsidian view
  behind one line in the README. Recommended.
- B. Delete what has no use evidence now (importer, MCP, Obsidian view, benchmark):
  about 3,000 lines and their tests.
- C. Keep everything; accept the cost.

**Question for the owner.** Which parts of iaso do you use every week? Everything else
is frozen (A) or removed (B).

### 8. `manim` is a hard dependency of every iaso install

Principle: P14 (each host installs only its own things), reliability of `iaso init`.

**What happens.** `pyproject.toml` lists `manim>=0.19` beside `pyyaml` as a runtime
dependency, and the vendored wheel carries it (`Requires-Dist: manim>=0.19`). Nothing in
`src/iaso` imports manim: `study/video.py` only runs `python -m manim` in a subprocess.
So every project that adopts iaso, and the plugin's private environment on first use, pulls
Manim and its tree (numpy, scipy, pillow, pycairo, moderngl, ffmpeg bindings; hundreds of
megabytes; pycairo needs a compiler or a wheel for the exact Python). That is the "first run
sets iaso up, which can take two minutes" in the command, and the first thing that breaks
on a machine without those wheels.

**Options.**
- A. Move it to `[project.optional-dependencies] video = ["manim>=0.19"]`; `study render`
  says "install iaso[video]" when `python -m manim` is missing. One edit, recommended.
- B. Drop video studies.

**Question for the owner.** None needed; A keeps video for you and costs nothing elsewhere.

### 9. The session brief alarms about everything, so it informs about nothing

Principle: P12 (iaso shows the owner little), P1 (drift caught while the work happens).

**What happens.** Every session starts with: 33 questions, 427 records waiting on a judge,
151 stale links, 586 uncovered examples, "0/2839 mapped tests with fresh passing evidence",
"full verification pending" with a list of twelve vendored example files that "have no
covering test", three open NCs, two known issues. None of it changed since yesterday and
none of it says what to do first. Evidence goes stale at every commit (freshness is pinned
to the tree digest, `verify/evidence.py`), so "0 fresh" is the permanent state of a
repository that commits daily, and "full verification pending" holds the merge until a
3,134-node run.

**Options.**
- A. The brief shows only deltas since the owner last saw it and the one thing that blocks
  now; counts go to `iaso status`. Vendored example files are exempt from tracing
  (`trace.exempt`). Evidence freshness is pinned to the digests of the files a test covers
  (the test map already knows them), not the whole tree. Recommended.
- B. Keep the counts, cap the brief at five lines.

**Question for the owner.** At a session start, what do you want to know: what changed
since you last looked, what blocks you now, or the full state?

### 10. The README and the help text describe a different iaso

Principle: P2 (the owner never needs commands), P15 (records are the only specification).

**What happens.** `README.md` (35 KB) says hooks run under a 2-second ceiling (finding 1:
90 seconds); its command table lists `iaso approve`, `iaso revoke`, `iaso triage
--approve`, `iaso spec approve`, `iaso config show` and `tests waive` as live owner
commands while the same page and `AGENTS.md` say they are gone or refused; it says "This
build has no `iaso new` command" and lists `iaso new` three tables later; it says the
plugin brings two skills (there are five). The study `how-a-question-travels-to-you-2.md`
is 407 bytes beside a 4.7 KB sibling with the same title.

**Options.**
- A. The README becomes one page: what iaso is, install, the three things the owner types
  (`/iaso intent`, `/iaso status`, `/iaso go`). The command reference is generated from
  `cli.py`'s help text, or dropped. Recommended.
- B. Fix the wrong lines only.

**Question for the owner.** None; a tidy under P15. The loop should confirm which commands
the owner still types, so the page lists only those.

### 11. `/iaso` pre-approves destructive git commands and every hook may hold a tool for two minutes

Principle: safety of the owner's repository; P13.

**What happens.** `plugin/commands/iaso.md` `allowed-tools` grants, to anyone who types
`/iaso`, `Bash(git rm:*)`, `Bash(git commit -m:*)`, `Bash(git merge --no-ff:*)`,
`Bash(git checkout --ours:*)` and `--theirs:*` without a prompt; `git rm -r .` fits
`git rm:*`. `plugin/hooks/hooks.json` gives the PreToolUse hook on every `Bash`, `Edit`,
`Write` and `AskUserQuestion` call a 120-second timeout; the Python route of that hook runs
whenever the tool input names iaso.

**Options.**
- A. Scope the git grants to the merge flow's paths (`git rm .iaso/*`, `git add .iaso` is
  already scoped) and drop `git commit`; PreToolUse and edit-check timeouts to 10 seconds.
  Recommended.
- B. Drop the Bash grants and let the normal permission prompt apply.

**Question for the owner.** None; a safety tidy.

---

## Smaller findings, not expanded here

Fourteen medium and low items from the two reviews were left out of this file: the
plugin's `tsconfig.json` extends a file that does not exist in the repository; vendored
third-party `SKILL.md` files nested under a skill; relative cross-skill paths; the `/iaso`
description is a 397-character sentence; `argument-hint` and the command body list
different verbs; `iaso-debug` asks the agent to read a config it is forbidden to read; the
study procedure is written four times with three depth rules; and so on. They follow from
findings 6 and 10.

## Verdict

Not healthy for daily use. Fix first, in this order: 4 (one build-script change unblocks
every other fix reaching the installed plugin), 2 (the logs: 59,000 entries read by every
process is the first cause of 1), 1 (the stop hook), then open the intent loop on 3, 5 and 6
together, since they are one principle: what iaso may do without the owner, and when it
may stop the agent. Finding 3's option C is the one design change in this file that would
change the owner's day most: it replaces a judge question that has answered "not entailed"
803 times out of 803 with one that asks only about contradictions.

Lean: about 3,000 to 6,000 lines and one dependency removable (findings 7 and 8), before
any decision on the larger parts.

Not checked: the browser workspace, the Obsidian view, the importer, the benchmark, the
Codex, Pi and Hermes adapters, the record merge driver's correctness, the test suite's own
quality, and the two video clips (the hook asked for an independent review of the
`debug-case` clip; not done here).
