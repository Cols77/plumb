# plumb on other hosts: capability tables

Sub-project 4 (`docs/specs/sp4-hosts-mcp.md`, SR-053 to SR-057; SR-380: the Pi adapter and the MCP
server are removed, and the Codex and Hermes adapters are frozen while Claude Code is the agent
working on plumb: `freeze:` in `.plumb/config.yaml`, awake when the host's session marker is set). Each table records the event
surface of the host version installed on this machine on 2026-10-06, read without running
the host's agent: its documentation or `--help`, and, for Codex, the JSON schemas embedded
in its binary. A row whose host has no mechanism uses the CLI-only fallback: the
instruction block plus `plumb turn start` and `plumb turn end`, which every adapter installs
whatever else the host supports.

Every adapter is thin: it turns the host's event into a `TurnEvent`, calls
`plumb.hosts.neutral.handle_event` (one `plumb` process per event, no daemon, no admission)
and renders the `TurnOutput`. The guard against self-approval is the same on every host:
every owner-only command writes through `approvals.require_owner`, which refuses under the
session marker and refuses, marker or not, unless stdin and stdout are an interactive
terminal where the owner answers `y`. In the tested marked/noninteractive shell boundary,
`plumb approve` (gone, SR-210: refused as no longer existing) exits 3 and writes nothing on
every host. This is not a guarantee about
every agent shell: PTYs, removable markers, and direct file writes are outside that tested
boundary. Marker and TTY checks are defense in depth, not authenticated owner provenance.

Prompts: a prompt that reaches plumb through a host's prompt hook is logged `via: hook`; one the
agent records itself with `plumb turn start` is logged `via: turn` and never confirms anything.

Hook commands that a host runs through the platform shell (Codex's `.codex/hooks.json`) are
rendered by one function, `plumb.hosts.common.shell_command`: POSIX `sh` quoting, and on
Windows a line that cmd and PowerShell both run (backslashed program path, no quoting; a
launcher that would need quoting is refused).

## Codex (codex-cli 0.160.0) — `plumb hosts install codex` (SR-054)

Codex 0.160 has lifecycle hooks (`codex features list`: `hooks stable true`) with the
Claude Code wire: the input carries `session_id`, `cwd`, `hook_event_name`, `prompt`,
`source`, `stop_hook_active`; the output accepts `hookSpecificOutput.additionalContext`
(session start, prompt), `decision: block` with a `reason` (stop) and `systemMessage`. Hooks
are read from a layer's `hooks.json` (the project layer is `.codex/hooks.json`); Codex keeps
a trusted hash per hook, so the owner trusts plumb's hooks once in Codex before they run.

| plumb event | Codex mechanism | Installed | Fallback |
|---|---|---|---|
| session-start | `SessionStart` hook in `.codex/hooks.json`: `plumb hook session-start --host codex --format claude` | yes | `AGENTS.md` block, `plumb turn start` |
| prompt | `UserPromptSubmit` hook: `plumb hook prompt --host codex --format claude` (logged `via: hook`) | yes | `plumb turn start` (logged `via: turn`, self-recorded) |
| edit | none needed: the stop event's one `git status` catches every edit | n/a | same |
| stop | `Stop` hook: `plumb hook stop --host codex --format claude` (block at most once, never while `stop_hook_active`) | yes | `plumb turn end` |
| stop (owner summary) | `notify` in `.codex/config.toml`: `plumb hook stop --host codex --format text --notify`, Codex appends the turn's JSON; it refreshes the status, never blocks and never rewrites the stated set (`notify` output is not shown to the owner) | yes, unless the project or user configuration already sets `notify` (kept) | `plumb status` |
| guard | owner-terminal guard (always); marker `PLUMB_AGENT_SESSION=codex` through `shell_environment_policy.set` in `.codex/config.toml` | yes, unless a foreign `shell_environment_policy` table exists (kept; status says the marker is missing) | `plumb hosts status codex` names the missing marker |

## Hermes (Hermes Agent 0.21.0) — `plumb hosts install hermes` (SR-056)

Hermes plugins are directories with `plugin.yaml` and an `__init__.py` exposing
`register(ctx)` (hermes_cli/plugins.py). Project plugins load from `.hermes/plugins/<name>/`
only with `HERMES_ENABLE_PROJECT_PLUGINS=1`. Hooks: `on_session_start` (return ignored),
`pre_llm_call` (returns `{"context": ...}`, appended to the turn's user message),
`post_tool_call`, `pre_verify` (accepts `{"decision": "block", "reason": ...}` to keep the
agent going, fires when the turn edited code), `transform_llm_output` (a returned string
replaces the reply), `post_llm_call` (`assistant_response`); commands with
`ctx.register_command`, messages with `ctx.inject_message`. Hermes runs its own
interpreter, so the plugin calls the plumb CLI (`--format json`) rather than importing plumb.

| plumb event | Hermes mechanism | Installed | Fallback |
|---|---|---|---|
| session-start | `on_session_start` only records a pending session; after ancestry filtering, the brief rides on the first `pre_llm_call` | yes | selected root-local context block |
| prompt | `pre_llm_call` (`user_message`): `plumb hook prompt --host hermes --format json`, `agent_context` returned as context (logged `via: hook`) | yes | `plumb turn start` |
| edit | `post_tool_call` for `write_file` and `patch`: `plumb hook post-edit` in the background | yes | stop's `git status` |
| stop | `pre_verify` (edited turns): the stop event, `block` returned once (`attempt == 0`); `transform_llm_output` (other turns): the stop event, never a block | yes | `plumb turn end` |
| stop (owner summary) | `transform_llm_output` appends `owner_lines` to the reply the owner reads; `post_llm_call` checks the reply carries them, else (interrupted turn, empty reply, another plugin's transform won, an older Hermes) reruns the stop event `--unseen`, so no stated record stays marked shown | yes | `plumb status` |
| child agents | sessions with `parent_session_id` are skipped (including startup deferred until after filtering); this does not certify provenance for parentless synthetic or scheduled turns | yes | n/a |
| owner commands | `/plumb <words>` (`ctx.register_command`): the words are passed to the agent with `ctx.inject_message` | yes | CLI |
| guard | owner-terminal guard (always); `register(ctx)` sets `PLUMB_AGENT_SESSION=hermes` in Hermes' environment, which its local terminal tool inherits (not remote terminal backends) | yes | `plumb hosts status hermes` labels the CLI fallback and marker status as runtime-unverified |

Release A support boundary

The tested surface is a project-bound event bridge. The generated plugin binds subprocesses
to the exact installed project root and refuses to run outside a valid `.hermes/plugins/plumb/plugin.py`
layout with a root-local `.plumb` directory; this does not provide multi-project routing for a
globally loaded plugin. Context selection is root-only and follows Hermes' selected current
target; ancestor/nested files, Cursor rules and other context sources are not universally
preserved, and uninstall does not chase historical block locations. Installation is idempotent,
preserves foreign plugin files and recognized existing context, and conservatively keeps
Claude-named and `AGENTS.override.md` instruction blocks on uninstall because ownership is
shared or unknown.

Runtime activation remains unverified until the owner enables the trusted project plugin and
observes a delivered hook prompt. File presence and `HERMES_ENABLE_PROJECT_PLUGINS=1` are
discovery prerequisites, not callback evidence. Delegated children are excluded when Hermes
supplies `parent_session_id`; that metadata is conditional, so desktop, background and cron
provenance are not certified. `/plumb`
injection outside the CLI requires supported routing and grants, and there is no native status
bar or streaming transport receipt. Native `plumb`/`plumb-clarify` skills are installed by this follow-up as
plugin-owned files under `.hermes/plugins/plumb/skills/`. The plugin registers
the bare names `plumb` and `plumb-clarify`; Hermes resolves them explicitly as
`plumb:plumb` and `plumb:plumb-clarify`. They are not copied to `.hermes/skills`
and are not entries in the flat available-skills index.

Owner-run installation

```bash
plumb hosts install hermes
# For an owner-run profile allowlist, independently of project discovery:
export HERMES_ENABLE_PROJECT_PLUGINS=1
hermes plugins enable plumb
# Restart the intended Hermes process after enabling.
plumb hosts status hermes
```

These commands are Git Bash syntax on Windows; use the equivalent environment assignment in
other shells. `hermes plugins enable plumb` changes the owner's selected Hermes profile
allowlist; it does not discover projects or prove that a project plugin is active. Project
discovery is the separate `HERMES_ENABLE_PROJECT_PLUGINS=1` prerequisite. The status command
intentionally reports runtime activation as unverified.
The CLI fallback remains in the selected context file and covers `turn start`/`turn end`,
owner words, proposed intent, and unseen-summary limitations.

## The understanding layer's dispatchers and the gate (SR-104, SR-103)

The jobs of the understanding layer (read, judge, clarify; `docs/specs/sp8-intent-by-exception.md`
section 4.4) each need one model call. `understand.dispatch` names the one dispatcher that makes
it; when it fails the job fails and nothing is confirmed (there is no second route).

| Host | Dispatcher | How |
|---|---|---|
| Claude Code | `claude-code` (the default there) | `claude -p` with the kind's agent from `understand/agents/<kind>.md`, no tools, the kind's answer schema (without plumb's own `id` label, which the command refuses), no session kept, none of the owner's settings, from a neutral directory; `understand.model` defaults to `haiku` |
| Hermes | `hermes` (the default there) | one delegated session behind `HermesDelegate`; a CLI one-shot fallback keeps Hermes' memory tool, as no toolless mode exists |
| any | `openrouter` | a direct chat-completions call with the answer schema, through the credential that JEV reads; chosen only by configuration |

The gate that refuses edits while a request's check is open is **Claude Code only**: it is a
`PreToolUse` hook on the edit tools (Edit, Write, NotebookEdit), a shell script that reads one
small state file. Edits made through a shell command are not checked, and the hook says so.
Other hosts get the skill's instruction to run `plumb clarify --wait` first and the visible
card, but no refusal. The end-of-turn summary of the understanding layer (what the owner's words
confirmed, the cards) is written by the same stop hook on every host that has one.
