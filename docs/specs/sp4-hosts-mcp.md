# Sub-project 4 spec: more hosts (Codex, Pi, Hermes) and a read-only MCP server

Status: implementation spec, written 2026-10-06. The owner does not review it (D11); verifier
agents check it against the owner intent brief, rulings R1 to R12 and `docs/concept.md`
section 9. Quotes and rulings win, then the concept, then this spec. Lane HOSTS of
`docs/plans/next-plan.md` builds it. Requirements: `FEAT-004`, `SR-053` to `SR-057`, all
proposed. (The pi-agent-factory importer completion, lane IMPORT, shares `FEAT-004` and is
specified in the plan, section 9.)

## 1. Outcome

Decision D3: "B. I guess the CLI / lib can be re-used from pi-agent-factory?" — a
host-neutral core (CLI and library) with thin adapters; Claude Code first, then "Codex, Pi,
Hermes and MCP". At the end of sub-project 4:

- one host-neutral turn API serves every adapter, so the same records, deltas, cards and
  questions reach the agent and the owner whatever the host (SR-053);
- `plumb hosts install codex|pi|hermes` writes a thin adapter for each host, mirroring the
  Claude Code hooks where the host supports them, and always leaves a CLI-only fallback that
  works with no hook at all (SR-054, SR-055, SR-056);
- `plumb mcp serve` is a read-only MCP server on stdio exposing the brief, the relevant
  records, why and impact, and drift (SR-057).

Adapters are thin: they translate the host's event into a `TurnEvent`, call the core and
print the `TurnOutput` the way the host can show it. No adapter decides anything, computes a
hash, selects a test or approves a record.

## 2. Owner intent served

| Owner decision or ruling | Where |
|---|---|
| D3: host-neutral core, thin adapters, "Codex, Pi, Hermes and MCP come later" | 3 to 6 |
| D3: "Do NOT bring the per-turn admission/coordination weight" | adapters call one process per event, no admission, no locks (3.3) |
| D5 "A": background, status line, end-of-turn summary, questions on three triggers only | the same `TurnOutput` on every host; the fallback keeps the CLI path (3.2) |
| R2: only the owner's explicit words confirm; the guard | session marker on every host; the MCP server has no write tool (6.3) |
| R9: context economy and the owner's mental model | every host renders PRESENT's output contract; deltas, not full records (3.1) |
| Quality bar: "Per-turn overhead is seconds, not minutes." | one interpreter start per event; budgets of sp1 10 (3.3) |
| R10 (SP6): "git is the coordinator, and plumb holds no shared mutable runtime state" | adapters keep per-session state under `.plumb/session/<sid>/` only (7) |

## 3. The host-neutral turn API (SR-053)

### 3.1 Contract

PRESENT owns it (`src/plumb/hosts/neutral.py`, sp5 9); HOSTS consumes it and never changes
it. The coordinator writes it in phase 0, delegating to the existing Claude Code handlers.

```python
@dataclass(frozen=True)
class TurnEvent:
    kind: Literal["session-start", "prompt", "edit", "stop"]
    root: Path
    session_id: str
    host: str                         # "claude-code" | "codex" | "pi" | "hermes" | "cli"
    text: str | None = None           # prompt text (prompt)
    path: str | None = None           # edited path (edit)
    source: str | None = None         # session start source: startup | resume | clear | compact
    stop_active: bool = False         # the host is already continuing after a block

@dataclass(frozen=True)
class TurnOutput:
    agent_context: tuple[str, ...] = ()   # lines added to the agent's context
    owner_lines: tuple[str, ...] = ()     # status card, summary, intent card (owner-facing)
    block: str | None = None              # one instruction that keeps the agent working
    status_line: str = ""                 # the one-line status card

def handle_event(event: TurnEvent) -> TurnOutput: ...
```

`plumb hook <event> --host <name> [--format claude|json|text]` is the CLI form: it builds the
`TurnEvent` from stdin JSON (Claude Code's shape by default; `--format json` takes the fields
above directly), calls `handle_event`, and prints in the requested format. Every hook exits 0
and keeps the sp1 budgets, watchdog and "check skipped (budget)" behaviour.

### 3.2 The CLI-only fallback

Every adapter installs it, and it is all a host without lifecycle hooks gets:

- an always-loaded instruction block (`AGENTS.md` for Codex and Pi, the host's context file
  for Hermes), the same content as the Claude Code `CLAUDE.md` block: records in `.plumb/`,
  read back each request and record it with `plumb capture`, `plumb brief`, `plumb show`,
  `plumb explain`, relay only the owner's own affirming words;
- the agent runs `plumb turn start` at the start of a task and `plumb turn end` before its
  final reply: `turn start --prompt-file F` (or the text on stdin) logs the prompt digest and
  prints the delta (the `prompt` event); `turn end` prints the summary and, when the stop
  logic would block, the instruction on stdout with exit 0 (the `stop` event). Both are the
  same `handle_event` calls;
- the session marker `PLUMB_AGENT_SESSION=<host>` wherever the host lets the adapter set the
  agent's shell environment; where it cannot, the adapter says so in `plumb hosts status`
  ("guard layer 1 unavailable on this host: rely on the deny rules or the owner's glance at
  the merge boundary"), and the trust model of concept 4.6 is restated there.

### 3.3 Budgets and weight

One `plumb` process per event, never a resident daemon, no admission, no per-call locks
beyond the log lock. The sp1 budgets apply to every host (prompt 1.2 s, stop 1.4 s, session
start 1.4 s soft; 1.9 s watchdog). A host that runs hooks synchronously on every tool call
gets no per-tool-call hook from plumb except edit tracking where the host makes it cheap.

## 4. Adapters

Each adapter lives in `src/plumb/hosts/<host>/` with `install.py` (idempotent install,
uninstall, status, `--dry-run`, preserving every foreign entry, like sp1 6.7) and the files it
renders from templates. `plumb hosts install <host> [--dry-run]`,
`plumb hosts uninstall <host>`, `plumb hosts status [<host>]`. `plumb hooks install` stays
the Claude Code installer.

The lane first records each host's event surface from the host version installed on the
machine (its documentation or `--help`, read-only) in `docs/hosts.md`, as a capability table.
The mappings below are the design; where the installed host lacks an event, that row falls
back to the CLI-only path of 3.2 and the table says so.

### 4.1 Codex (SR-054)

| plumb event | Codex mechanism | Fallback |
|---|---|---|
| session-start, prompt, stop | Codex lifecycle hooks when the installed version has them (configured in the project's `.codex/` configuration), each running `plumb hook <event> --host codex --format json` | `AGENTS.md` block and `plumb turn start/end` |
| stop (owner summary) | the `notify` program Codex runs after each agent turn, which receives the turn's JSON and runs `plumb hook stop --host codex --format text` to refresh the status and log the summary for `plumb status` | `plumb turn end` |
| edit | none needed: the stop event's `git status` catches every edit (sp1 6.4 step 1) | same |
| tools | the MCP server of 6, registered as `[mcp_servers.plumb]` in the project's Codex configuration | CLI |
| guard | the marker in the configured shell environment, if supported | 3.2 |

### 4.2 Pi (SR-055)

Pi extensions are TypeScript modules subscribing to session and agent events and able to
register commands and a status footer (pi-agent-factory's `pi-ext/factory-watch` is the
reference shape: a thin TypeScript layer that shells out to a Python CLI).

| plumb event | Pi mechanism | Fallback |
|---|---|---|
| session-start | the session-start event: run `plumb hook session-start --host pi --format json` and add `agent_context` as a context message | `AGENTS.md` block |
| prompt | the before-agent-start (input) event: add `agent_context` to the turn | `plumb turn start` |
| edit | the tool-result event for edit and write tools: `plumb hook post-edit --host pi` in the background | stop's `git status` |
| stop | the agent-end event: show `owner_lines` as a notice, set the footer status to `status_line`; when `block` is set, send it as a follow-up user-role steering message once | `plumb turn end` |
| owner commands | `/plumb ...` registered as a Pi command that passes the words to the agent (sp5 6) | the agent runs the CLI |

`plumb hosts install pi` renders `.pi/extensions/plumb/index.ts` (about 120 lines, no
dependencies beyond Pi's extension API and Node's `child_process`) and a `package.json` if the
host needs one. It is tested by a Python test that renders the template and checks the event
names and commands it contains, and, when `node` is available, by type-checking it
(skipped otherwise); no Pi installation is required for the suite.

### 4.3 Hermes (SR-056)

Hermes plugins are Python packages with a `plugin.yaml` manifest and a `register(ctx)` entry
that registers commands and, where the version supports it, lifecycle hooks
(pi-agent-factory's `.hermes/plugins/*` is the reference for the manifest and `register`).

| plumb event | Hermes mechanism | Fallback |
|---|---|---|
| session-start, prompt, stop | lifecycle hooks registered in `register(ctx)` when the installed Hermes exposes them; each calls `plumb.hosts.neutral.handle_event` in-process (Hermes is Python) or the CLI | context-file block and `plumb turn start/end` |
| owner commands | `ctx.register_command("plumb", ...)` passing the words to the agent | CLI |
| tools | the MCP server of 6 if Hermes is configured with MCP servers | CLI |

`plumb hosts install hermes` renders `.hermes/plugins/plumb/{plugin.yaml,__init__.py,
plugin.py}`. Tests import `plugin.py` with a fake `ctx` and drive each registered callback.

## 5. Output contract on every host

Adapters render `TurnOutput` and nothing else (PRESENT defines its content, sp5 9):

- `agent_context` goes to the agent where the host can inject context; otherwise to stdout of
  `plumb turn start/end`, which the agent reads;
- `owner_lines` go to the owner's channel (a notice, the footer, a system message); when the
  host has none, they are in `plumb status` and the stop output;
- `status_line` goes to the host's status bar if any;
- `block` is honoured at most once per turn and never when the host reports it is already
  continuing (`stop_active`), so no host can loop.

A conformance test drives the same scripted session through `handle_event` with each
`host` value and asserts identical `agent_context`, `owner_lines` and `block` (only the
rendering differs).

## 6. Read-only MCP server (SR-057)

### 6.1 Transport

`plumb mcp serve [--root PATH]`: JSON-RPC 2.0 over stdio, newline-delimited, standard
library only (no MCP SDK dependency: runtime dependencies stay the standard library and
PyYAML). It implements `initialize` (server name `plumb`, version, `capabilities: {tools:
{}}`, the protocol version the client asks for when supported, else the latest it supports),
`notifications/initialized`, `ping`, `tools/list` and `tools/call`. Unknown methods answer
error `-32601`. One request at a time; each tool call opens the core afresh, so it sees the
current files.

### 6.2 Tools

| Tool | Input | Output (text plus `structuredContent`) |
|---|---|---|
| `plumb_brief` | `{full?: bool}` | the session brief lines (sp5 `present.api.brief`) |
| `plumb_relevant` | `{text: str, limit?: int}` | relevant records, one line each (ID, state, title), the R9 delta shape without session dedupe |
| `plumb_show` | `{ids: [str]}` | each record in full (read-back, examples, tests, state) |
| `plumb_explain` | `{query: str}` | why something exists, in the owner's terms (`plumb explain`), plain words, path or ID |
| `plumb_impact` | `{ref: str}` | what a change would reach (`plumb impact`), words resolved first (sp5 5) |
| `plumb_drift` | `{}` | drift signals and hints (`plumb drift`) |

Every tool carries `annotations: {readOnlyHint: true, idempotentHint: true}` and calls the
frozen `plumb.present.api` functions (sp5 9), so it shows exactly what the CLI shows.

### 6.3 Read-only guarantee

There is no write tool: no capture, link, repin, approve, relay, revoke, test run or waive.
A test calls every tool and asserts that `.plumb/` outside `cache/` is byte-identical before
and after, and that `tools/list` contains no other tool. Approval stays on the paths of
concept 4.6 and R8; the MCP server cannot reach them.

### 6.4 Registration

`plumb mcp install claude-code|codex|hermes [--dry-run]` writes the host's MCP server entry
(`.mcp.json` for Claude Code, the Codex project configuration, the Hermes configuration) with
the launcher of sp1 6.7, preserving foreign entries; `plumb mcp uninstall` removes it.

## 7. R10 compatibility

Adapters keep state only under `.plumb/session/<sid>/` (the host's session id, sanitized as
`safe_session_id` does), never in a shared file other worktrees would write. The MCP server
is stateless. Cross-worktree awareness (R10.4) will reach every host through `TurnOutput`,
with no adapter change.

## 8. Definition of done

1. `plumb hosts install|uninstall|status` for `codex`, `pi`, `hermes`, idempotent, preserving
   foreign entries, each with tests in a temporary repository; `--dry-run` writes nothing.
2. `docs/hosts.md` holds each host's capability table, stating which rows use the fallback.
3. `plumb turn start/end` and `plumb hook <event> --host X --format json` work with no host
   installed; the conformance test of 5 passes for every host value.
4. `plumb mcp serve` passes a scripted JSON-RPC session test (initialize, tools/list, each
   tool, an unknown method) and the read-only test of 6.3.
5. No adapter imports a module of another adapter; no test needs Codex, Pi, Hermes or Node
   installed (tests that would use them are skipped when absent).

## 9. Out of scope

- Changes to the Claude Code adapter's output (PRESENT, sp5).
- Write tools over MCP, remote MCP transports (HTTP), authentication.
- A resident daemon or service of any kind.
