# plumb

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
supported first. plumb keeps pi-agent-factory's IDs and `SR:` commit trailers, and it can
import that project's records.

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

`status` shows `awaiting your confirmation: SR-001`. A new record stays `proposed` until you
confirm it from your own terminal:

```bash
uv run plumb approve SR-001
```

You can also mark a test directly with `@pytest.mark.sr("SR-001")`. Register the marker in your
pytest configuration (`markers = ["sr(id): links a test to a plumb requirement"]`).

**Import one.** To import from a pi-agent-factory checkout (it reads `requirements/SR-*.md`,
`docs/features/FEAT-*.md`, `bundles/*.json` and `docs/nonconformances/NC-*.md`):

```bash
uv run plumb import pi-agent-factory /path/to/pi-agent-factory --dry-run
uv run plumb import pi-agent-factory /path/to/pi-agent-factory --only SR,FEAT
```

The source is read only. Imported records arrive as `proposed`. A link whose target file does
not exist in your repository is reported and not added.

### 4. Connect Claude Code

```bash
uv run plumb hooks install --dry-run   # show what would change
uv run plumb hooks install
uv run plumb hooks status
```

The install is idempotent and keeps every entry that does not belong to plumb. It writes:

- `.claude/settings.json`: the `SessionStart`, `UserPromptSubmit`, `PostToolUse` (on edits,
  async) and `Stop` hooks, the status line, the `PLUMB_AGENT_SESSION` marker, and deny rules
  that stop the agent from running `plumb approve`, `plumb revoke` or `plumb tests waive`, or
  editing `.plumb/log/`;
- `.claude/skills/plumb/SKILL.md`, a short skill that tells the agent where the records and the
  test map are and which commands to use;
- `.claude/commands/plumb.md`, the `/plumb` slash command;
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

When your prompt touches a record, the agent receives that record, its confirmed examples and
its covering tests:

```
plumb: relevant records (state; examples; covering tests):
SR-001 [confirmed] add returns the sum of two numbers
  EX-1: given a = 1 and b = 2, when add(a, b) is called, then it returns 3
  tests: tests/test_calc.py
plumb: compare this request with the confirmed examples of SR-001; if it contradicts or
extends them, read back the change and ask before editing.
```

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

When the turn proposed records, the summary then shows each one in full (at most three
records): an intent's read-back, what will and won't be done and its labelled assumptions; a
requirement's statement and every given/when/then example; a decision and its alternatives.
Records past that cap are named, never hidden behind a count:

```
plumb: proposed SR-002: divide returns a / b.
plumb: proposed SR-002/EX-1: given 6 and 3, when divide runs, then it returns 2
plumb: proposed SR-002/EX-2: given 1 and 0, when divide runs, then it returns 0
plumb: +1 more not shown: SR-005 (plumb show SR-005); a confirmation must name them
```

Your "ok" on the next prompt confirms only what was shown; SR-005 needs words naming it.

The status line reads:

```
plumb | SR 1/1 ok | proposed 0 | stale 1 | tests ok | ask 0
```

Read-backs and proposed examples appear in the summary as `proposed` and never block the work.
To confirm them, reply in the session in your own words, for example "ok, SR-009 is right".
The agent then records your words with `plumb relay`, and the approval is marked
`agent-relayed` with your quote and the digest of your prompt. A prompt that does not object
does not count as a confirmation.

Hook timing on the 2-core development machine, warm caches: session start 0.55 to 0.8 s,
prompt 0.45 to 0.6 s, stop 0.65 to 1.2 s on a turn with changes (the first call after a code
change rebuilds the test map and can take about 1.4 s). Each hook has a soft budget near the
2-second ceiling and a 1.9 s watchdog. When a loaded machine cuts a hook short, it still
prints the read-back, the relevant records and the relay line, and names the skipped step
(`plumb: check skipped (budget): covering tests`): evidence detail is dropped first, never
the intent lines.

At a merge boundary, run:

```bash
uv run plumb validate --merge main   # exit 4: a touched requirement or an untraced change
                                     # waits for you; exit 5: a regression is unresolved
uv run plumb tests run --full        # if "full verification pending"
```

## Command reference

Every command accepts `--root ROOT` (by default, plumb walks up to the first directory that
holds `.plumb/`, else `.git`). Most commands accept `--json`. Run `plumb <command> --help` for
the full options.

Exit codes: `0` ok, `1` findings, `2` usage, `3` refused by the guard, `4` the merge waits for
your confirmation (a touched requirement, or an untraced change no requirement owns), `5` the
merge waits on an unresolved regression.

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
| `plumb approve IDS... [--proposed] [--yes] [--note]` | Owner approval of records at their current content. It is refused under the agent session marker. |
| `plumb relay IDS... --prompt DIGEST --quote "..." [--revoke]` | Record an approval or a revocation that you gave in a prompt, with your exact words. |
| `plumb revoke IDS... [--note]` | Owner revocation of the latest approval. |

`plumb new`, `why` and `log` are reserved and answer `not available in this build`.

### Verification

| Command | What it does |
|---|---|
| `plumb map [--rebuild]` (also `plumb tests map`) | Build the code-to-test map and write `.plumb/test_map.txt`. |
| `plumb tests select [PATHS...] [--changed] [--budget S]` | Covering tests of the changed paths, in priority order. |
| `plumb verify` / `plumb tests run [--changed \| --paths P... \| --nodes N... \| --full] [--budget S]` | Run the covering tests (or the full suite) and record evidence. A test that passed before and now fails is reported as a regression. |
| `plumb tests waive --reason "..." [--diff-digest sha256:...]` | Owner waiver pinned to a diff digest. Only the owner can run it. |
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

### Bridge

| Command | What it does |
|---|---|
| `plumb trailers check-msg FILE` / `plumb trailers install-hook` | Check a commit message's `SR:` trailers, or install the commit-msg hook. Set `require_trailer: true` in `.plumb/claims.yaml` to make trailers mandatory. |
| `plumb claims check [--range BASE..HEAD]` | Compare the paths each commit touched with the paths its `SR:` trailers declare. |
| `plumb fidelity SR` | Build the advisory fidelity packet (the statement, examples, linked code, tests and evidence) for the host agent to judge. |
| `plumb judge SR --verdict fits\|drifts\|unsure [--note]` | Record the host agent's advisory verdict. |
| `plumb judgment [status]` | Show the judgment backend in use: `heuristic` by default, `jev` optional, or `disabled`. |
| `plumb import pi-agent-factory SOURCE [--dry-run] [--only SR,FEAT,NC]` | Import pi-agent-factory records as proposed plumb records. |

## Configuration

`.plumb/config.yaml` lists every key with its default in comments. The main keys are
`source_dirs` and `test_dirs`; `verify` (`turn_budget_s`, `fill_fraction`: the share of the
budget a selection's estimate fills, scaled by the pace observed in earlier runs,
`sample_size`, `workers` of 2 at most, `flaky_rerun`, `infra_globs`); `hooks` (per-hook budgets in ms and brief length); the
`judgment` backend; and the `escalation` thresholds that make plumb suggest an up-front spec
for large or cross-cutting work.

## How plumb develops itself

plumb has been dogfooded from day one: this repository is developed with plumb.

- Its own intent is in `.plumb/`. The `INT` records quote the owner's intent brief verbatim.
  `SR-001` to `SR-025` (feature `FEAT-001`, sub-project 1) carry given/when/then examples, and
  `DEC` records hold the design choices. Each requirement is linked, with hash pins, to the
  modules that implement it and the tests that verify each example.
- The Claude Code hooks are installed here (`.claude/settings.json`, `.claude/skills/plumb/`),
  so every session on plumb gets the brief, the per-prompt context, the covering-test stop
  hook, the alignment summary and the status line.
- Commits carry `SR: SR-###` trailers. `require_trailer: true` is set in `.plumb/claims.yaml`,
  and the commit-msg hook enforces it. Run `plumb claims check` before committing to make sure
  every touched path is declared.
- Work is test-first. Use `uv run plumb tests run --changed` while iterating and
  `uv run pytest` (at most `-n 2`) before committing. `uv run ruff check` must pass.
  `scripts/drive_session.py` replays a whole Claude Code session through the installed hooks
  and times each one against the 2-second limit.
- Before a merge, run `plumb validate --merge main` and `plumb tests run --full`.
- Review findings: only HIGH findings are fixed in the change that raised them. Medium and low
  findings go to `docs/followups.md`.

Design documents: `docs/concept.md` (the concept spec), `docs/specs/sp1-grounding-loop.md`
(sub-project 1), `docs/plans/sp1-plan.md` and `docs/plans/fork-plan.md` (moving work from
pi-agent-factory to plumb).
