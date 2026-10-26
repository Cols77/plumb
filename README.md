# plumb

**Keeps a coding agent building what you meant, not what it guessed.**

You tell your coding agent what you want. plumb writes that down as small plain-text records in your repository, links each one to the code and tests that deliver it, and tells you when the code and your intent drift apart.
It works in the background, asks you a question only when it must, and everything it knows is a file you can read.

```
/plugin marketplace add Cols77/plumb
/plugin install plumb@plumb
```

Then type `/plumb init` in your project. (Other ways to install are [below](#install).)

> Status: version 0.1.0, early. See [Limits](#limits).

## What you see

You ask your agent: "add sub(a, b) beside add". plumb has the agent restate the request, in your words, before it builds:

```
Your request of 2026-10-12: "add sub(a, b) beside add"
I will add sub(a, b), returning a - b, next to add.
Assumed: whole numbers, like add
Not doing: no change to add or mul
  1. Yes, that is what I meant (recommended)
  2. Not quite - Say what to change; nothing is confirmed
```

When the agent finishes a turn that changed code, plumb runs only the tests that cover that code and prints a short summary:

```
plumb: touched SR-001 | stale: SR-001#0 -> src/app/calc.py (target moved)
plumb: covering tests 1: 1 fresh pass, 0 not yet passing, 0 deferred (budget)
plumb: questions: none
```

A status line shows the state at a glance:

```
plumb ● awaits you · "Add sub(a, b) beside add, returning a..." · SR 2/3 ok · 1 question
```

(Sample output from an example project.) You are interrupted only when a request contradicts something you already confirmed, when a decision that matters is still a guess, or when a test that used to pass now fails. Everything else is logged and shown when you ask.

## Why

Coding agents leave you two options: watch every step, or "vibe code" and hope. The usual fix is a heavy up-front specification. plumb takes a third path: it keeps the agent grounded in records of your intent, stays mostly out of the way, and lets you inspect all of it.

- **Nothing hidden.** Records are Markdown files with YAML headers under `.plumb/`. Commit them like code.
- **Drift is visible.** A link between a requirement and its code or tests remembers the content of both ends. If either changes, the link is marked stale.
- **Tests are the evidence.** plumb maps code to its covering tests, runs those on each turn within a time budget, and records the result against the exact code that ran. The full suite runs at merge boundaries.

The name: a plumb line shows whether a wall is true. plumb does the same for software.

## How it works

plumb keeps five kinds of record in `.plumb/`:

| Record | ID | What it holds |
|---|---|---|
| Intent | `INT-###` | Your words, quoted, and the agent's read-back of them |
| Requirement | `SR-###` | A statement plus given / when / then examples |
| Decision | `DEC-###` | "I assumed A; B also fits" |
| Feature | `FEAT-###` | A group of requirements |
| Nonconformance | `NC-####` | A recorded gap or defect |

A new record starts as `proposed`. plumb's judge confirms it on your behalf, from your logged words or your answer to one question. There is no approve command, and the agent cannot write an approval. Approvals, test evidence and decisions go to append-only, hash-chained logs under `.plumb/log/`. They show tampering; they do not stop a malicious agent (see [Limits](#limits)).

## Install

You need Python 3.12 or later, git and [uv](https://docs.astral.sh/uv/). The checks run your tests with pytest.

**As a Claude Code plugin (recommended).**

```
/plugin marketplace add Cols77/plumb
/plugin install plumb@plumb
```

The plugin brings the `/plumb` command, skills (`plumb-records`, `plumb-clarify`, `plumb-intent`, `plumb-debug`, `plumb-study-video`) and the background checks. It runs plumb from a private copy it sets up on first use. A project plumb has not adopted sees one line per session and nothing else. To try it from a checkout: `claude --plugin-dir plugin`.

**As a command-line tool.** plumb is not on a package index yet. From a local checkout, add it to your project's dev environment so it can import your code and pytest:

```bash
uv add --dev pytest /path/to/plumb
uv run plumb --version
```

## First project

```bash
uv run plumb init          # creates .plumb/ ; safe to run again ; commit it
```

Write a requirement by hand (`plumb new requirement --title ...` also creates one), for example `.plumb/requirements/SR-001.md`:

```markdown
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

Link it to its code and its test, then run the checks:

```bash
uv run plumb link SR-001 implemented_by src/app/calc.py
uv run plumb link SR-001 verified_by tests/test_calc.py --example EX-1
uv run plumb map             # writes .plumb/test_map.txt
uv run plumb verify --full   # runs the suite, records evidence
uv run plumb status
```

For Claude Code without the plugin, `uv run plumb hooks install --dry-run` shows what would change, and `plumb hooks install` writes the hooks, status line, skills, `/plumb` command and git hooks. `plumb hooks uninstall` removes exactly what was added.

You can also mark a test directly with `@pytest.mark.sr("SR-001")`; register the marker in your pytest configuration.

## Look around

Ask in plain words: in Claude Code as `/plumb <words>`, in a shell as `plumb <command>`.

| Question | Command |
|---|---|
| Where do things stand? | `plumb status`, `plumb brief` |
| Why does this exist? | `plumb explain <words, a path or an ID>` |
| What waits for me, and what drifted? | `plumb review`, `plumb drift` |
| What would this change reach? | `plumb impact <ID or path>` |
| Show me a record in full | `plumb show SR-001` |
| Browse it as notes | `plumb view` (writes an Obsidian vault under `.plumb/view/`) |
| Browse it in the browser | `plumb ui --demo` opens an isolated example project; `plumb ui --root <project>` opens yours |

The browser workspace shows a project's issue inbox, decisions, diagrams and evidence, and listens on `127.0.0.1` only. The same browser room shows "studies": short explanations plumb writes at a step of the intent loop, as text, diagrams or short animated video clips. Reading a study or editing a note approves nothing.

## Working in parallel

Several agent sessions can work at once, each in its own git worktree or branch. plumb coordinates them through git alone.

- New record IDs come from one counter shared by all worktrees of a clone, so two sessions do not both pick SR-082.
- Each log entry is its own small file, so branches do not conflict on logs.
- Record files merge field by field. If two branches change the same words differently, plumb shows both versions and asks you; it never picks one.
- You are told early when another branch is changing a requirement you are working on.
- `plumb merge-check main` is a quick check (no test run) that holds a merge carrying an unconfirmed requirement, an open conflict or an undeclared file. The one full test run happens at push.

## Other agents

Claude Code is supported first. Codex, Pi and Hermes have thin adapters (`plumb hosts install codex|pi|hermes`). Any agent can use the command-line fallback: `plumb turn start` before the work and `plumb turn end` after. A read-only MCP server (`plumb mcp serve`) exposes the brief, relevant records, explain, impact and drift; it has no write tool. Per-host details are in [docs/hosts.md](docs/hosts.md).

## Commands

`plumb --help` groups them; `plumb <command> --help` gives the options.

- **Records and integrity:** `init`, `show`, `link`, `unlink`, `relink`, `repin`, `validate`, `status`, `brief`, `explain`, `proof`, `drift`, `debug`
- **Intent capture:** `capture`, `new`, `intent`, `example`, `decide`, `clarify`, `question`, `escalate`, `spec`, `triage`, `config`, `jev`, `study`
- **Owner views:** `resolve`, `review`, `align`, `view`, `impact`, `ui`
- **Verification:** `map`, `verify`, `tests` (map, select, run)
- **Host and other agents:** `hooks`, `hook`, `install`, `statusline`, `hosts`, `turn`, `mcp`
- **Merge and parallel work:** `merge-check`, `conflicts`, `conflict`, `merge-fix`, `ids`, `inflight`, `log`
- **Bridge:** `trailers`, `claims`, `fidelity`, `judge`, `judgment`, `import` (from pi-agent-factory)

Exit codes: `0` ok, `1` findings, `2` usage, `3` refused by the guard, `4` the merge waits for you (a conflict or a question), `5` a failing test or an unconfirmed proof holds the merge.

## Configuration

`.plumb/config.yaml` lists every key, with its default, in comments. The main ones are `source_dirs`, `test_dirs`, `verify` (turn time budget, workers), `hooks` (per-hook budgets), `judgment` and `escalation`.

plumb answers its judgment questions with a local heuristic by default. JEV, TypeSafe's typed-judgment model, is an optional judge, reached directly or through OpenRouter; `/plumb jev status` shows what is configured. plumb records only the name of the variable that holds your key, never the key.

## Limits

- Version 0.1.0. Not published to a package index; install is from a checkout or the plugin marketplace.
- The covering-test checks assume Python and pytest.
- Claude Code is the primary host. Codex, Pi and Hermes are thin adapters, and the command-line fallback has fewer guarantees than hooks.
- Hooks must finish in about 2 seconds, so on a cold clone the first turns test a sample of nearby tests and say "full verification pending".
- Logs are tamper-evident, not tamper-proof: an edit shows, but a determined malicious agent with write access could rewrite them.
- A recorded answer is not proof that a feature is implemented or that tests pass.
- The optional JEV judge is an external service. Without it, the local heuristic judges.
- The browser workspace and studies are young and change quickly.

## Contributing

Issues and pull requests are welcome. plumb is developed with plumb: its own records are in `.plumb/`, and its commits carry `SR: SR-###` trailers.

```bash
uv sync
uv run plumb tests run --changed   # while iterating
uv run pytest -n 2                 # before committing
uv run ruff check
```

The browser frontend is in `ui/` (Node 22: `npm ci`, `npm test`, `npm run build`); built assets are committed under `src/plumb/browser/static/`. Design documents are in [docs/](docs/): the concept in `docs/concept.md`, the browser API in `docs/browser-api.md`, host tables in `docs/hosts.md`.

## License

MIT. See [LICENSE](LICENSE).
