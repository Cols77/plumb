# plumb

## Browser issue workspace

Open one project's issue inbox, decisions, diagrams and evidence in your browser:

```sh
plumb ui --root /path/to/project --port 8765 --open
plumb ui --demo --port 8765 --open
```

The demo creates an isolated temporary project with labelled records. The server binds
only to `127.0.0.1`; use its printed launch URL. The fragment capability is removed from
the address bar immediately and retained in this tab's session storage for authenticated
requests. Never share that launch URL. Sessions are the original source sessions, so
answering does not steal the Claude panel registration. Queued follow-up context is
retained for that session's next prompt hook; it does not wake the agent. A recorded
answer is not proof of implementation or passing tests.

The workspace's Python tests, `tests/browser`, stay out of a plain `pytest` run: name the
directory or pass `--browser` to run them. Built frontend assets are included in
`src/plumb/browser/static/`. To rebuild with Node 22:

```sh
cd ui
npm ci
npm test
npm run check
npm run build
```

The pinned Svelte/TypeScript/Vite project builds directly into the packaged static
directory; commit updated assets with source changes. Fonts and third-party license
notices are bundled locally. `plumb ui --assets /path/to/build` selects another build.
Only the index and `/assets/` files are served. Repository HTML is never a document in
the app: extracted diagrams are sanitized and rendered as SVG image Blobs, with scripts,
embedded HTML and external resources removed. Some complex SVG styling is omitted by
this boundary; the source disclosure and download show the sanitized image.

For frontend development, start the Python server on port 8765, then run `npm run dev`
from `ui/`. Open the Vite address with the same `#token=...` fragment from the Python
launch URL. Vite's loopback-only proxy sends API requests to the local server with its
matching Origin; set `PLUMB_API` to another loopback origin before starting Vite if needed.
Do not expose either development server to a network. The browser API and independent
process concurrency limits are documented in [docs/browser-api.md](docs/browser-api.md).
Upstream revisions and license details are in [ui/THIRD_PARTY_NOTICES.md](ui/THIRD_PARTY_NOTICES.md).

A plumb line shows whether a wall is true. plumb does the same check for software: it keeps a
coding agent's work aligned with what you intend to build.

The goal, in the owner's words, is "to ensure the alignment between user's intent and
understanding of what he wants to build and the current state of the system being built."
Coding agents usually leave you two options. You micro-manage them, or you "vibe code" or
follow a heavy spec-driven process. plumb takes a third path: it makes "vibe coding grounded on
the projects artifacts in an efficient, reliable and trustable manner." It does not run heavy
black-boxed workflows. It works mostly in the background, and you can inspect everything it
does.

- **Intent lives in your repository.** plumb keeps small Markdown records with YAML frontmatter
  under `.plumb/`: intents `INT-###` (your verbatim words and a read-back), requirements
  `SR-###` (each with given/when/then examples), decisions `DEC-###` ("I assumed A; B also
  fits"), features `FEAT-###` and nonconformances `NC-####`. There is no hidden state.
- **Links are hash-pinned.** A link from a requirement to its code, its tests or another record
  pins the content hash of both ends. If either end changes, the link becomes stale, and that
  is drift.
- **Approvals are pinned to exact content.** Only your explicit words confirm a record. If the
  record changes afterwards, it shows up as an unconfirmed edit. Approvals, evidence and
  decisions go into append-only, hash-chained logs. These logs are tamper-evident, but they are
  not tamper-proof against a malicious agent.
- **Tests are the evidence.** plumb maps code to its covering tests, runs only those tests
  within a time budget on each turn, and records evidence pinned to the tree, the test source
  and the environment. The full suite runs at merge boundaries.
- **Interruptions are few.** Inside a Claude Code session you see a status line, a short
  alignment summary at the end of each turn, and a question only when one of three things
  happens: a request contradicts or extends a confirmed record, an unconfirmed decision that
  matters is relied on, or a test that passed before now fails. Everything else is logged and
  shown when you ask for it.

plumb is a host-neutral CLI and Python library with thin host adapters. Claude Code is
supported first; Codex and Hermes have thin adapters (frozen while Claude Code is the agent
working on plumb: `freeze:` in `.plumb/config.yaml`), and any other agent can use the CLI-only
fallback (`plumb turn start|end`). plumb keeps pi-agent-factory's IDs and `SR:` commit trailers.

## As a Claude Code plugin

In Claude Code, add this repository as a plugin marketplace and install plumb from it:

```
/plugin marketplace add <owner>/<repo>
/plugin install plumb@plumb
```

Then type `/plumb init` in a project to adopt it. The plugin brings `/plumb`, the `plumb-records`
and `plumb-clarify` skills and plumb's background checks to every project, and runs plumb from a
private copy it sets up on first use (it needs uv, or Python 3.12 or later). A project plumb has not
adopted sees one line per session and nothing else. The plugin is built by
`python scripts/build_plugin.py` (`plugin/`).

On Claude Code builds that load mods, the plugin also draws plumb's panel above the prompt:
plumb's status, and each card that waits for you in full (the requirement as it now reads, what
changed, your words, each option and why one is recommended) with buttons to confirm, ask for a
change, leave it open, or say no where the card suggests it. To try it from a checkout without
installing: `claude --plugin-dir plugin`. Its tests run with `claude plugin test plugin`.

## Quickstart (5 minutes)

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), git and a pytest test suite.

### 1. Install plumb into the project's environment

plumb runs your tests with the interpreter that runs plumb. Install it as a dev dependency of
the project so that interpreter can import your code and pytest. plumb is not published to a
package index yet, so install it from a local checkout:

```bash
uv add --dev pytest /path/to/plumb
uv run plumb --version
```

### 2. Adopt the repository

```bash
uv run plumb init
```

This creates `.plumb/` with the record folders (`intents/`, `requirements/`, `decisions/`,
`features/`, `ncs/`), the append-only logs in `log/`, `config.yaml` (every key optional, with
the defaults shown in comments) and `claims.yaml` (the `SR:` trailer policy). Running it again
is safe. Commit `.plumb/`.

### 3. Write or import a requirement

**Write one.** This build has no `plumb new` command, so create the file yourself. The record's
identity comes from the frontmatter `id`, not from the filename.

```markdown
<!-- .plumb/requirements/SR-001.md -->
---
id: SR-001
title: add returns the sum of two numbers
statement: app.calc.add(a, b) returns a + b for integers.
examples:
- id: EX-1
  given: a = 1 and b = 2
  when: add(a, b) is called
  then: it returns 3
---
```

Then link it to its code and its test, build the test map and record the first evidence:

```bash
uv run plumb link SR-001 implemented_by src/app/calc.py
uv run plumb link SR-001 verified_by tests/test_calc.py --example EX-1
uv run plumb map                 # writes .plumb/test_map.txt (grep it)
uv run plumb verify --full       # runs the suite and records evidence
uv run plumb status
```

A new record stays `proposed` until the judge approves it on your behalf: your logged words
entail it (JEV above 0.9, calibrated), or the judge model asks you one question through the
question tool and judges again with your answer. `status` counts what waits on a judge; no
command approves a record, and the agent never writes an approval.

Owner-only commands ask y/N in an interactive terminal and refuse to run without one (in
Git Bash's mintty, prefix `winpty`), so an agent's shell cannot write an owner approval on
any host.

You can also mark a test directly with `@pytest.mark.sr("SR-001")`. Register the marker in your
pytest configuration (`markers = ["sr(id): links a test to a plumb requirement"]`).

### 4. Connect Claude Code

```bash
uv run plumb hooks install --dry-run   # show what would change
uv run plumb hooks install
uv run plumb hooks status
```

The install is idempotent and keeps every entry that does not belong to plumb. It writes:

- `.claude/settings.json`: the `SessionStart`, `UserPromptSubmit`, `PostToolUse` (on edits,
  async) and `Stop` hooks, the status line, the `PLUMB_AGENT_SESSION` marker, and deny rules
  that stop the agent from running the owner's or plumb's own commands (`plumb tests waive`,
  `plumb config auto-approve`, `plumb hook prompt`, `plumb hook question-answer`, ...) or
  editing `.plumb/log/`;
- `.claude/skills/plumb-records/SKILL.md` (with its `references/`), a short skill that tells the
  agent where the records and the test map are and which commands to use (`capture`,
  `decide`, `proof`), and
  `.claude/skills/plumb-clarify/SKILL.md`, which scales the clarification to the request
  (trivial, incremental, escalated) and asks only the questions that change what gets built,
  one per message;
- `.claude/commands/plumb.md`, the `/plumb` slash command (`status`, `explain`, `review`,
  `confirm`, `impact`, `view`, each taking your own words);
- a `<!-- plumb:begin -->` block in `CLAUDE.md`;
- the git `commit-msg` hook, which checks `SR:` trailers.

By default the hooks start plumb with the project's `.venv` Python. Use `--launcher path|venv|uv`
to choose another launcher. `plumb hooks uninstall` removes exactly what install added.

### 5. What you see in a session

The output below comes from a simulated session on the example project. At session start, the
agent receives the intent brief:

```
plumb brief (records in .plumb/, test map in .plumb/test_map.txt)
features: none
awaiting your confirmation: 0 proposed
drift: stale 0 | dangling 0 | uncovered examples 0
tests: 1/1 mapped tests with fresh passing evidence
```

When your prompt touches a record the agent has not seen in this session (or one that changed
since), the agent receives one line for it; it pulls the examples and covering tests with
`plumb show` when it needs them. A later prompt about the same unchanged record injects
nothing:

```
plumb: relevant records, new or changed this session (plumb show <ID> for examples and tests):
SR-001 [confirmed] add returns the sum of two numbers
plumb: compare this request with the confirmed examples of SR-001; if it contradicts or
extends them, read back the change and ask before editing.
```

`hooks.prompt_tokens` (200 by default) bounds what one prompt injects, and the session brief
is a few lines plus a pointer (`hooks.session_brief: full` gives the longer brief).

If the agent edits code and tries to finish, the stop hook first asks it to run the covering
tests of the turn. This happens at most once per turn and only within the budget:

```
plumb: run 'plumb tests run --paths src/app/calc.py' (covering tests of this turn, budget 15 s),
then finish your reply.
```

Then you get the end-of-turn alignment summary:

```
plumb: touched SR-001 | stale: SR-001#0 -> src/app/calc.py (target moved)
plumb: covering tests 1: 1 fresh pass, 0 not yet passing, 0 deferred (budget)
plumb: fidelity unjudged: SR-001
plumb: questions: none
```

When the agent records a new intent (`plumb capture`: your verbatim words, its read-back, a
requirement with examples, a decision), the summary shows one read-back card for the request,
in your words, with its date:

```
Your request of 2026-10-12: "add sub(a, b) beside add"
I will add sub(a, b), returning a - b, next to add.
Assumed: whole numbers, like add
Not doing: no change to add or mul
  1. Yes, that is what I meant (recommended) - Confirms this request and everything recorded from it
  2. Not quite - Say what to change; nothing is confirmed
```

A choice you have no better-supported answer to is its own card, one question at a time, the
recommended option first, each option saying what it does. A decision with a better-supported
answer is not asked: it is stated as an assumption you can flip ("Assumed: whole numbers").
A choice that is about structure or flow can show a block diagram above its question, when the
agent drew one with the architecture-diagram skill and the diagram mod is installed; without the
mod the card names the diagram file in one line.
`plumb show <ID>` prints a record's examples and tests.

The status line is a one-line card, the state plus a plain-language intent summary:

```
plumb ● awaits you · "Add sub(a, b) beside add, returning a..." · SR 2/3 ok · 3 awaits you · 1 question
```

Read-backs and proposed examples appear in the summary as `proposed` and never block the work.
To confirm them, answer the request's read-back card (Yes, that is what I meant) or reply in the session
in your own words, for example "ok, that is right". plumb's own reader of your message, or your
button press, confirms; the agent confirms nothing. A prompt that does not object does not count
as a confirmation, and an "ok" never confirms a record the same prompt objects to ("the pow
example is wrong, it should return 9. Ok, carry on" leaves the pow records proposed).

Hook timing on the 2-core development machine, warm caches: session start 0.55 to 0.8 s,
prompt 0.45 to 0.6 s, stop 0.65 to 1.2 s on a turn with changes (the first call after a code
change rebuilds the test map and can take about 1.4 s). Each hook has a soft budget near the
2-second ceiling and a 1.9 s watchdog. A hook never builds a cold test map inline (a fresh
clone): `plumb map` runs detached, and meanwhile a turn gets a bounded sample of nearby tests
with `full verification pending (coverage unknown)`. When a loaded machine cuts a hook short, it still
prints the read-back, the relevant records and the open assumptions, and names the skipped step
(for example `plumb: check skipped (budget): tests` at session start): evidence detail is
dropped first, never the intent lines.

At a merge boundary, run `uv run plumb merge-check main`: it is quick and runs no test (with
`--run`, or in the pre-push hook, it runs the full suite at most once, only when full
verification is pending or touched acceptance tests lack evidence), checks claims, links and log integrity, lists the approvals you did not type (agent-relayed,
auto-jev, import) with their revoke commands, and exits like `plumb validate --merge`
(which reports without running anything). `plumb merge-check --install-pre-push` makes it a
git pre-push hook (your choice). The report-only form:

```bash
uv run plumb validate --merge main   # exit 4: a touched or widened requirement, an untraced
                                     # change or a new trace.exempt glob waits for you;
                                     # exit 5: an acceptance test the change can affect
                                     # fails or has not passed on the current code, or
                                     # full verification is pending
uv run plumb tests run --full        # if "full verification pending"
```

## Working in parallel

You can run several agent sessions at once, each in its own git worktree or branch. plumb
coordinates them through git alone: it holds no locks and no shared runtime state.

- **IDs never clash between worktrees.** Every worktree of a repository takes new record IDs
  from one shared counter that git keeps (`refs/plumb/ids`), so two sessions proposing
  requirements at the same moment get, say, SR-082 and SR-083. A collaborator on another
  clone can still pick the same number; at merge, say "fix the ID clash" (`/plumb merge-fix`)
  and the incoming record is renumbered with every reference to it, without rewriting
  history. Your "ok" carries over only while the words are unchanged, and it is labelled
  "carried by renumber".
- **Logs never conflict.** Each approval, prompt and test run is its own small file under
  `.plumb/log/<kind>/`, so branches add log entries side by side. Older one-file logs move
  over when you say "migrate the logs"; every hash stays the same.
- **Records merge field by field.** When two branches change different parts of a
  requirement (one adds a link, the other an example), the merge combines them on its own.
  When both change the same words differently, the merge does not guess: the requirement
  becomes an intent conflict, shown as one card with both versions and the branch each came
  from. You answer in plain words ("keep feat-x's", or how to combine them), and nothing is
  chosen for you.
- **You hear about overlaps early.** When another worktree or branch is changing a
  requirement this session works on, the session brief and the status line say so once, for
  example `SR-005 "relay checks" is also being changed on branch feat-x`. When a new request
  contradicts intent another branch has in flight, you are asked right away, before either
  side builds on it ("keep feat-x's", "keep this one" or "both"), and your answer holds for
  both. When those two versions later meet at merge, your earlier answer decides them: you
  are not asked again.
- **The merge waits for you only when it must.** `/plumb init` sets up the record merge and
  a quick check that holds a merge carrying an open intent conflict, an unconfirmed
  requirement or an undeclared file, without running the tests. The one full test run
  happens when you push. Ask `/plumb conflicts` to see what waits, or `/plumb merge-check`
  for the whole merge report.

## Command reference

Every command accepts `--root ROOT` (by default, plumb walks up to the first directory that
holds `.plumb/`, else `.git`). Most commands accept `--json`. Run `plumb <command> --help` for
the full options.

Exit codes: `0` ok, `1` findings, `2` usage, `3` refused by the guard, `4` the merge waits on a
judge or your answer (a touched requirement, a requirement widened by a new link, an untraced
change no requirement owns, a `trace.exempt` glob added on the branch, or a confirmed
requirement whose acceptance test changed since it was confirmed),
`5` verification holds the merge (an acceptance test the change can affect fails or has no
passing run on the current code, a regression is unresolved, including one hidden by
rewriting the test, or `full verification pending` holds and no owner waiver covers this
exact change).

### Records and integrity

| Command | What it does |
|---|---|
| `plumb init` | Adopt the repository and create `.plumb/` (idempotent). |
| `plumb link SRC KIND TARGET [--example EX-n]` | Add a hash-pinned link. Kinds: `derives_from`, `decides`, `upstream`, `relates_to`, `implemented_by`, `verified_by`, `corrects`, `supersedes`. The target is a record ID or a repository path. |
| `plumb repin [SELECTOR] [--all-stale] [--note]` | Refresh link pins (`SR-003#2` or a record ID). It never confirms anything. |
| `plumb validate [--merge BASE]` (alias `check`) | Check records, links, logs and approvals. `--merge BASE` adds the merge-boundary checks: touched requirements confirmed, agent-relayed approvals listed, fidelity, full verification and log integrity. |
| `plumb status` | Counts, drift and the records awaiting your confirmation. |
| `plumb show IDS...` | A record in full: the read-back, will and won't, labelled assumptions, every example, the alternatives and the body. The end-of-turn summary names the records it could not show with this command; a bare "ok" never confirms them, only words that name their IDs do. |
| `plumb drift` | Drift signals only: stale and dangling links, unconfirmed edits, uncovered examples, and fidelity that a judgment no longer covers. |
| `plumb brief [--all] [--max-lines N]` | The short intent brief (about 30 lines). |
| `plumb explain WORDS...` (alias `why`) | Why a behaviour, a file or a record exists, in your terms: the requirement, your words it derives from, decisions, examples, test state and code. Takes plain words ("how totals are rounded"), a path or a record ID. In Claude Code, `/plumb explain <anything>`. |
| `plumb approve`, `plumb revoke`, `plumb confirm`, `plumb relay` | Gone (SR-210): refused with exit 3. The judge approves records on your behalf, from your logged words and your answers to its questions. |
| ~~`plumb approve IDS... [--proposed] [--exempt] [--note]`~~ | (retired) Owner approval of records at their current content. It asks y/N in your interactive terminal and is refused under the agent session marker or without a terminal (an agent's shell, a pipe), on every host. `revoke` and `tests waive` work the same way. |
| `plumb revoke IDS... [--note]` | Owner revocation of the latest approval. |

### Intent capture

| Command | What it does |
|---|---|
| `plumb capture --prompt DIGEST --file DOC` | Record a whole read-back in one call: your verbatim quote (checked against the logged prompt), the read-back, will, won't, labelled assumptions, requirements with given/when/then examples, decisions. Everything is proposed. `--dry-run` writes nothing. |
| `plumb new KIND --title ...` | One record with the next ID (`intent`, `requirement`, `decision`, `feature`, `nc`), proposed. |
| `plumb intent`, `plumb example SR --given --when --then`, `plumb decide --question --chosen --alt [--matters] [--supersede DEC]` | An INT read-back, an example, a decision ("I assumed A; B also fits"). |
| `plumb clarify "<request>" [--questions FILE]` | The clarification depth (trivial, incremental, escalated) and only the questions that change what gets built, ranked. |
| `plumb escalate check\|decline` | Escalation suggestions for large, risky or cross-cutting work; `decline` is yours. |
| `plumb spec show\|state INT` | An escalated up-front spec: every member in full, and whether the judge approved the set whole. |
| `plumb config auto-approve on\|off`, `config show`, `config card full\|compact\|off` | The opt-in auto-approval (off by default; needs JEV and its credential, no calibration: DEC-143) and the card verbosity. Your terminal only. |
| `plumb jev status [--probe]\|setup [--provider typesafe\|openrouter] [--env-var NAME] [--env-file PATH]\|calibrate` | The optional JEV backend (the agent runs it when you say `/plumb jev status`, `/plumb jev setup openrouter` or `/plumb jev calibrate`): provider, endpoint, where the key comes from (a label, never the key), reachability and the normalized resolved version; setup records the provider, model and the credential variable's NAME; calibration on your own decisions. |

### Owner views (plain words; none approves anything)

| Command | What it does |
|---|---|
| `plumb resolve WORDS...` | What your words mean: records, files and tests, best first; asks when ambiguous. |
| `plumb status --card` | The status card, what awaits you and drift. |
| `plumb review [WORDS...]` | The deep review: what awaits you, approvals you did not type, drift, alignment, the merge state. |
| `plumb align [SCOPE]` | Judges each edge from intent to code, weakest first, and names the gaps; never adds or removes an edge. |

In Claude Code these are `/plumb status`, `/plumb explain <anything>`, `/plumb review`,
`/plumb impact <anything>` and `/plumb view`.

### Verification

| Command | What it does |
|---|---|
| `plumb map [--rebuild]` (also `plumb tests map`) | Build the code-to-test map and write `.plumb/test_map.txt`. |
| `plumb tests select [PATHS...] [--changed] [--budget S]` | Covering tests of the changed paths, in priority order. |
| `plumb verify` / `plumb tests run [--changed \| --paths P... \| --nodes N... \| --full] [--budget S]` | Run the covering tests (or the full suite) and record evidence. A test that passed before and now fails is reported as a regression. |
| `plumb tests waive --reason "..." [--diff-digest sha256:... \| --merge BASE]` | Owner waiver pinned to a diff digest; `--merge BASE` waives the merge boundary's full run for exactly the change from BASE (any later edit voids it). Only the owner can run it. |
| `plumb impact REF` | What lies downstream of a record or a path: records and covering tests with their evidence state. |

A failing test is rerun once on the same tree to detect flakiness. If shared test
infrastructure changes (`conftest.py`, `pyproject.toml`, `uv.lock` and others, set by
`verify.infra_globs`), the status becomes `full verification pending` and no full run starts
during the turn.

### Host (Claude Code)

| Command | What it does |
|---|---|
| `plumb hooks {install,uninstall,status} [--launcher auto\|path\|venv\|uv] [--dry-run]` | Manage the hooks, status line, skill, slash command, `CLAUDE.md` block, guard settings and commit-msg hook. |
| `plumb install claude-code` | Alias of `plumb hooks install`. |
| `plumb hook {session-start\|prompt\|post-edit\|stop}` | Hook entry points. Each one reads the host's JSON on stdin, answers on stdout and always exits 0. |
| `plumb statusline` | Print the one-line status from `.plumb/session/status.json`. It recomputes nothing. |

### Other hosts

| Command | What it does |
|---|---|
| `plumb hosts install\|uninstall\|status codex\|hermes [--dry-run]` | Thin adapters over the same host-neutral turn API (see `docs/hosts.md` for each host's events). |
| `plumb turn start\|end [--session ID]` | The CLI-only fallback for a host without hooks; confirmations resting on a message the agent recorded itself are labelled "self-recorded message". On a host whose prompt hook runs (Claude Code, or Codex once its hooks are trusted), such a message never grounds a confirmation. |

### Merge boundary

| Command | What it does |
|---|---|
| `plumb merge-check [BASE] [--run] [--json]` | The merge boundary, quick (no test run); `--run` adds at most one full run, claims, links, log integrity, the glance of approvals you did not type, advisory fidelity. Exit codes as above. |
| `plumb merge-check --install-pre-push` / `--uninstall-pre-push` | The git pre-push hook, where the one full run happens; `plumb init` and `plumb hooks install` write it by default (R17). |

### Parallel work (the agent's interface)

| Command | What it does |
|---|---|
| `plumb ids [sync]` | The IDs reserved in `refs/plumb/ids`, shared by every worktree of a clone; `sync` reseeds from every local branch. |
| `plumb merge-fix [--from REF] [--dry-run]` | Renumber a record ID a merge brought twice (another clone): the incoming record gets a new ID, every reference the incoming side added follows, trailers are mapped, history is untouched. |
| `plumb log migrate [--dry-run] [--check]` | Move legacy `events.jsonl`/`evidence.jsonl` lines into one file per entry, digests unchanged. |
| `plumb merge-driver %O %A %B %P %X %Y` | git's merge driver for record files (git calls it; `plumb init` and `plumb hooks install` configure it). |
| `plumb conflicts` / `plumb conflict propose\|choose\|relay` | The intent conflicts a merge left, as cards; propose a combined version; record the owner's choice (owner-only, or relayed from the owner's logged words). |
| `plumb inflight [check\|drop\|sync]` | Intent other branches have in flight (`refs/plumb/claims`), the early intent-conflict check, and dropping an abandoned branch's claims. |
| `plumb merge-check --hook pre-merge-commit` | The quick merge check git runs before recording a merge (no test run); `plumb init` installs it with the pre-push hook. |

### Bridge

| Command | What it does |
|---|---|
| `plumb trailers check-msg FILE` / `plumb trailers install-hook` | Check a commit message's `SR:` trailers, or install the commit-msg hook. Set `require_trailer: true` in `.plumb/claims.yaml` to make trailers mandatory. |
| `plumb claims check [--range BASE..HEAD]` | Compare the paths each commit touched with the paths its `SR:` trailers declare. |
| `plumb fidelity SR` | Build the advisory fidelity packet (the statement, examples, linked code, tests and evidence) for the host agent to judge. |
| `plumb judge SR --verdict fits\|drifts\|unsure [--note]` | Record the host agent's advisory verdict. |
| `plumb judgment [status]` | Show the judgment backend in use: `heuristic` by default, `jev` optional, or `disabled`. |

## Configuration

`.plumb/config.yaml` lists every key with its default in comments. The main keys are
`source_dirs` and `test_dirs`; `verify` (`turn_budget_s`, `fill_fraction`: the share of the
budget a selection's estimate fills, scaled by the pace observed in earlier runs,
`sample_size`, `workers` of 2 at most, `flaky_rerun`, `infra_globs`); `hooks` (per-hook budgets in ms and brief length); the
`judgment` backend; and the `escalation` thresholds that make plumb suggest an up-front spec
for large or cross-cutting work.

### The optional JEV judge

plumb answers its judgment questions with a local heuristic by default. JEV, TypeSafe's fast
typed-judgment model, is optional, reached directly at TypeSafe or through OpenRouter. You set
it up in plain words in Claude Code; the agent runs plumb for you:

- `/plumb jev setup openrouter` (or "use OpenRouter for JEV"): records `provider:
  openrouter` and the name of the variable that holds your key, `OPENROUTER_API_KEY`. If the
  key already lives in an env file outside the repository, say so ("my key is in
  C:/secrets/.env"): plumb records that path in your user-level `~/.config/plumb/jev.json`
  and reads the key there in place each time. It never copies the key into the repository, a
  log, a record, a notice or any output, and it refuses an env file inside the repository.
  `/plumb jev setup typesafe` does the same for TypeSafe's own endpoint and
  `TYPESAFE_API_KEY`.
- `/plumb jev status`: the provider, the endpoint, where the key comes from (`env`,
  `env-file` or `user-store`; never the key), whether JEV answered one tiny probe, and the
  model version it resolved.
- `/plumb jev calibrate` (or "is JEV good enough to confirm for me?"): tries JEV on your own
  past yes and no answers and tells you, for each kind of record, whether it can be trusted
  to confirm records that only restate your words. It approves nothing and turns nothing on.
- Setting a provider again replaces the earlier provider's endpoint, path and validated
  version, so a switch from TypeSafe to OpenRouter (or back) never keeps the old endpoint.

The key is looked up in the process environment first, then in the env file that
`jev.json` names (`KEY=VALUE` lines, optional quotes, comments ignored), then in the older
user store `~/.config/plumb/jev`. With `provider: openrouter` the defaults are endpoint
`https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13` and validated version
`typesafe/jev-1.13`; any `judgment.jev` key you set (`base_url`, `path`, `model`,
`validated_against`, `credential_env`) wins over the preset. Model names are compared through
one normalizer, so `jev-1.13`, `jev-1.13.0` and OpenRouter's dated
`typesafe/jev-1.13-20260917` are the same version, while `jev-1.14` counts as a version change
(confident answers are escalated and auto-approval waits for a recalibration).

For the agent, the underlying commands are `plumb jev setup --provider openrouter --env-var
OPENROUTER_API_KEY [--env-file PATH]`, `plumb jev status --probe` and `plumb jev calibrate`.

## How plumb develops itself

plumb has been dogfooded from day one: this repository is developed with plumb.

- Its own intent is in `.plumb/`. The `INT` records quote the owner's intent brief verbatim.
  `SR-001` to `SR-081` (features `FEAT-001` to `FEAT-006`: the grounding loop, intent
  capture, the merge boundary, other hosts, presentation, parallel work)
  carry
  given/when/then examples, and `DEC` records hold the design choices. Every record written
  by an agent stays proposed until the owner confirms it. Each requirement is linked, with hash pins, to the
  modules that implement it and the tests that verify each example.
- The Claude Code hooks are installed here (`.claude/settings.json`, `.claude/skills/plumb-records/`),
  so every session on plumb gets the brief, the per-prompt context, the covering-test stop
  hook, the alignment summary and the status line.
- Its logs are one file per entry (migrated in SP6 with every digest kept), its IDs come
  from `refs/plumb/ids`, and git uses plumb's record merge driver, the quick merge check
  (pre-merge-commit and prepare-commit-msg) and the pre-push hook for the one full run.
- Commits carry `SR: SR-###` trailers. `require_trailer: true` is set in `.plumb/claims.yaml`,
  and the commit-msg hook enforces it. Run `plumb claims check` before committing to make sure
  every touched path is declared.
- Work is test-first. Use `uv run plumb tests run --changed` while iterating and
  `uv run pytest` (at most `-n 2`) before committing. `uv run ruff check` must pass.
  `scripts/drive_session.py` replays a whole Claude Code session through the installed hooks
  and times each one against the 2-second limit; `--capture` replays the capture flow (on a
  scratch copy) and `--merge-check BASE` adds the merge boundary report.
- Before a merge, run `plumb merge-check main` (quick; `--run` adds one full run when needed). On plumb itself it
  exits 4: the records await the owner.
- Review findings: only HIGH findings are fixed in the change that raised them. Medium and low
  findings go to `docs/followups.md`.

Design documents: `docs/concept.md` (the concept spec), `docs/specs/sp1-grounding-loop.md`
(sub-project 1), `docs/plans/sp1-plan.md` and `docs/fork-plan.md` (moving work from
pi-agent-factory to plumb). The next batch: `docs/specs/sp2-intent-capture.md`,
`docs/specs/sp3-merge-boundary.md`, `docs/specs/sp4-hosts-mcp.md`,
`docs/specs/sp5-presentation.md` and their one combined plan, `docs/plans/next-plan.md`
(five lanes, including the pi-agent-factory importer completion). Parallel work:
`docs/specs/sp6-parallel-work.md` and `docs/plans/sp6-plan.md`.
