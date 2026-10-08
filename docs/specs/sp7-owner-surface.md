# Sub-project 7 spec: the owner surface (plumb as a Claude Code plugin, no shell for the owner)

Status: proposed, 2026-10-07. Implements rulings R14 (no shell for the owner), R15 (plumb as
a Claude Code plugin), R16 (the relay's objection scope), R18 (assent provenance, the
read-back self-challenge, the owner-level abstraction rule, `done_when`, the structure
check with agent self-repair) and R19 (Claude Code mods inside the plugin), plus two SP6
leftovers. The owner does not review this spec (D11); verifier agents check it against the
owner intent brief and its rulings R1 to R19, `docs/concept.md` and the code. When this
spec and the owner's quoted words disagree, the words win.

Records (all proposed, written with plumb's own CLI; agents never approve them):
`FEAT-007`, `INT-023`, `SR-082` to `SR-095`, `DEC-023` to `DEC-025`. Plan:
`docs/plans/sp7-plan.md` (lanes PLUGIN, MOD, SURFACE, CAPTURE2).

Every R14, R15, R16, R18 and R19 item is a MUST. Per-step cheaper-model routing, subagent
model choice, `$.model.complete` as the cascade tier and JEV-driven routing are OUT of scope
(R19: deferred to an SP8 exploration).

## 1. Outcome

After SP7 the owner:

1. installs plumb once, with Claude Code's own plugin commands (`/plugin marketplace add`
   on the plumb repository, then `/plugin install plumb@plumb`), and has `/plumb`, the
   `plumb` and `plumb-clarify` skills and every plumb hook in every repository (R15);
2. adopts a repository by typing `/plumb init`; nothing is copied into the repository's
   `.claude/`; a repository not adopted shows one line per session,
   "/plumb init to adopt this repository", and nothing else (R15);
3. sees plumb where they look: a band above the prompt (one line, expanding to the intent
   card only when it matters), a pane to walk the intent, one summary line under each answer,
   a toast only for what matters, and `/plumb` answers drawn in the transcript (R19);
4. confirms by pressing **Confirm** (an action only the owner can take, pinned to exactly
   what was shown) or by typing "ok", as before (R2, R19);
5. never types, reads or is told to run a shell command, and never has to know plumb's or
   the code's internals: every capability has a `/plumb` route, plain words or a button,
   every owner-visible text names those and speaks at the owner's level, explaining any
   needed concept first (R14, R18);
6. is no longer refused when an ok shares a message with an unrelated request (R16);
7. is asked only about intent and tradeoffs: a bare "yes" records what it answered, the
   read-back challenges itself and labels its assumptions, an intent can say when it is done,
   and an escalated plan is checked and repaired by the agent before it is offered (R18).

## 2. Owner intent served

> "Approving DEC should be also a command, part of an automation I dont want to have to know
> those uv run commands. Analyse all the features, you should never have to tell me to run
> those bash commands it should all be abstracted through prompt/commands/skills" (R14)

> "Make plumb a plugin that you can install using claude code so that then all commands are
> built in" (R15)

> R16: the owner's message "Make plumb a plugin that you can install using claude code so
> that then all commands are built in. Ok, confirm DEC-017 and DEC-018" was refused. It must
> confirm both.

> "Yes Add these four to SP7" ... "It should never assume the user understands internals of
> the system. if the agent has to explain something that requires system internals
> understanding, it should first explain the corresponding concepts." ... "remember that it
> should maximize reliability and minimize human intervention. only question user for
> intent/tradeoffs related problems" (R18)

> "Yes agreed. Let's keep the cheaper model routing and jev routing for later on as an
> exploration" (R19)

These sit on decision 5 (mostly in the background; few, meaningful interruptions), R1 (read-
backs never block), R2 (no approval without the owner's explicit words; agent-relayed
approvals are labelled), R8 (triage and opt-in automatic confirmation), R9 (presentation and
context economy; plain-language commands; the agent bridges the owner's mental model) and
R17 (early intent conflicts; the cheap merge hold; the single full run at push).

## 3. Principles

1. **The owner acts; the agent runs plumb.** The CLI is the agent's and the plumbing's
   interface. The owner's interface is `/plumb`, plain words and buttons.
2. **Owner-only stays owner-only, and says honestly who wrote it.** A button press, a slash
   command the owner typed or the owner's typed words (logged by the prompt hook, or by the
   mod for a typed slash command) are the owner's explicit actions. The agent never
   initiates one; every owner-only write passes one choke point (`plumb.owner_actions`, 7.2)
   that names how the owner acted. Whatever the agent's shell writes on the owner's behalf
   (typed words or a typed slash command) is `by: agent-relayed` with the owner's verbatim
   words and the prompt digest (R2); `by: owner` is kept for the owner's own terminal and a
   button press, the two paths no agent shell runs. Concept 4.6's rule "a `by: owner` entry
   written under a marker is an error" stays as written.
6. **Nothing is approved before the owner saw it.** An approval is pinned to content the
   owner was shown (concept 4.6 check 3, the KEEP list). Plain words, typed or said, never
   approve a record the owner has not been shown in full; plumb resolves the words, shows
   the records, and confirms on the owner's next "ok" or press (7.2).
3. **Command hooks stay the engine; the mod presents (DEC-024).** Prompt logging, the tool
   guard, edit tracking and the turn's checks keep their tested command-hook paths on every
   host. The mod draws from what they wrote and owns owner actions in the UI. With the mod
   active, the hooks stay quiet toward the owner; without it, they print as before.
4. **One choke point per guarantee, one test per entry point** (the owner rule for HIGH
   classes, applied up front): each guarantee below names its choke point and lists its
   entry points with their tests.
5. **Seconds, not minutes.** Hook latency stays in seconds; a repository not adopted costs
   no Python start; the mod adds at most one plumb process per turn, off the prompt path.

## 4. The plugin (R15; SR-082, SR-083, SR-084)

### 4.1 Layout in the plumb repository

```
.claude-plugin/marketplace.json     # marketplace "plumb": one plugin, source "./plugin"
plugin/
  .claude-plugin/plugin.json        # name "plumb", version = the package version
  bin/plumb                         # POSIX sh launcher: the bundled environment's plumb
  bin/plumb.cmd                     # the same for cmd.exe
  bin/plumb-hook                    # POSIX sh: the cheap pre-checks, then `plumb hook <event>`
  commands/plumb.md                 # GENERATED from src/plumb/hosts/claude_code/templates/plumb-command.md
  skills/plumb/SKILL.md             # GENERATED from templates/skills/plumb/SKILL.md
  skills/plumb-clarify/SKILL.md     # GENERATED from templates/skills/plumb-clarify/SKILL.md
  hooks/hooks.json                  # {"modules": ["./register.tsx"], "hooks": {...command hooks...}}
  hooks/register.tsx                # the mod (section 5) and its modules, tests *.test.tsx
  hooks/jargon.gen.ts               # GENERATED from plumb.present.owner_text.JARGON (6.3)
  types/index.d.ts                  # PluginState for $.state
  tsconfig.json
  vendor/plumb-<version>-py3-none-any.whl
  vendor/MANIFEST.json              # {version, wheel, sha256, source_digest}
scripts/build_plugin.py             # builds the wheel and every GENERATED file
```

`plugin/hooks/hooks.json` holds both the mod (`modules`) and the command hooks (`hooks`);
`claude plugin validate` accepts the two together (checked on Claude Code 2.1.290 while
writing this spec). The templates stay the one source of the command and skill text (the
legacy per-repository installer renders them too); `scripts/build_plugin.py` renders them
for the plugin with `{plumb}` as `plumb` (on the agent's PATH, 4.3). A freshness test
(`tests/plugin/test_bundle_fresh.py`) fails when a GENERATED file or the wheel no longer
matches its source (`source_digest` is the digest of `src/plumb/**` and the templates); it
runs in the PLUGIN lane gate, at Integrate and in plumb's own pre-push.

`plugin.json` declares no `userConfig` in SP7. The plugin version equals
`pyproject.toml`'s version (a test asserts it); Integrate bumps both to `0.7.0`.

### 4.2 The bundled environment (DEC-023)

The plugin never runs the target repository's `.venv` or a `plumb` found on the PATH:

- **Data directory.** `PLUMB_HOME` = `$CLAUDE_PLUGIN_DATA` when Claude Code sets it, else
  `~/.plumb`. The environment is `PLUMB_HOME/env/<version>-<wheel sha256 first 12>/`.
- **Bootstrap.** `bin/plumb` reads `PLUMB_HOME/current.json` (`{python, version,
  wheel_sha256, plugin_root}`). When it is missing or names another wheel, it takes a lock
  (`mkdir PLUMB_HOME/lock`), builds `<env>.tmp` with `uv venv --python 3.12` and
  `uv pip install <the vendored wheel>` (falling back to `python3.12 -m venv` and pip when
  `uv` is absent), renames it into place, writes `current.json` and the user-level launcher
  `PLUMB_HOME/bin/plumb` (and `plumb.cmd`), and keeps the two newest environments. Concurrent
  sessions wait on the lock; a stale lock (older than 10 minutes) is taken over.
- **Running.** `bin/plumb` execs `<python> -m plumb "$@"` with `PLUMB_PLUGIN_ROOT` and
  `PLUMB_HOME` set; the mod runs `[python, "-m", "plumb", ...]` with `$.process.run`, reading
  `python` from `current.json` with `$.fs` (no shell, no PATH lookup).
- **First session.** The session-start hook starts the bootstrap in the background when the
  environment is not ready, prints one plain line ("plumb is getting ready for its first
  run; it will follow this session from your next message"), and every other hook exits 0 at
  once until `current.json` exists. `/plumb init` waits for the bootstrap (it runs it in the
  foreground, at most 120 s).
- **Missing prerequisites.** Without `uv` and without Python 3.12 the line says: "plumb needs
  Python 3.12 on this machine; say 'install what plumb needs' and I will set it up". It never
  names a command.
- **User-level launcher.** `PLUMB_HOME/bin/plumb` is a two-line script calling the
  `python` of `current.json`. git hooks and the merge driver call it (4.6), so they follow
  plugin updates without being rewritten.

### 4.3 What the plugin's command hooks do

`plugin/hooks/hooks.json` command hooks, each `"${CLAUDE_PLUGIN_ROOT}/bin/plumb-hook" <event>`:

| Event | Matcher | plumb hook | Note |
|---|---|---|---|
| SessionStart | `startup\|resume\|clear\|compact` | `session-start` | writes the env file (below); the brief |
| UserPromptSubmit | | `prompt` | prompt-digest log, relay line, delta (model-facing) |
| PreToolUse | `Bash\|Edit\|Write\|MultiEdit\|NotebookEdit` | `pre-tool` (new) | the guard (below) |
| PostToolUse | `Edit\|Write\|MultiEdit\|NotebookEdit` (async) | `post-edit` | edit tracking |
| Stop | | `stop` | the turn's checks, triggers, summary |

`bin/plumb-hook` does the cheap checks in `sh` before any Python starts:

1. It walks up from `$CLAUDE_PROJECT_DIR` (else the working directory) for `.plumb/`. None
   found: on `session-start` with source `startup` or `resume`, inside a git work tree, and
   unless the repository is on the owner's "not here" list (`PLUMB_HOME/ignored`), it prints
   `{"systemMessage": "/plumb init to adopt this repository"}`; every other case exits 0.
   This is the whole cost of the plugin in a repository not adopted (SR-083 EX-3, EX-4).
2. A repository with the old per-repository install (its `.claude/settings.json` hooks
   run `-m plumb hook`) is handled by that install: exit 0 (SR-084 EX-1).
3. `pre-tool`: when stdin holds none of `plumb`, `PLUMB_`, `.plumb/log`, exit 0 (allow).
4. Environment not ready: as in 4.2.
5. Otherwise `exec plumb hook <event>`.

**Session marker and PATH.** The plugin cannot write `.claude/settings.json`'s `env`, so the
session-start hook appends to the file Claude Code names in `$CLAUDE_ENV_FILE`:
`export PLUMB_AGENT_SESSION=claude-code` and `export PATH="<plugin root>/bin:$PATH"`. Every
shell command the agent runs then carries the marker (concept 4.6 check 1) and finds
`plumb`. The PLUGIN lane verifies on this Claude Code build that the env file reaches the
agent's shell (a one-off probe recorded in `docs/hosts.md`); where it does not, the command
and skills name `"${CLAUDE_PLUGIN_ROOT}/bin/plumb"` and the marker falls back to check 4
(owner terminal; buttons and typed commands keep working, 7.2).

**The guard (concept 4.6 check 2) without settings deny rules.** A plugin cannot add
permission rules, so the `pre-tool` hook denies (`permissionDecision: deny`, with a plain
reason for the agent) every command and path the deny rules cover today, from ONE function,
`plumb.guard.denied(tool, tool_input) -> str | None`: `plumb approve|revoke|tests waive|
triage --approve|spec approve|config auto-approve|config show|turn start|hook prompt|
conflict choose` without `--prompt`; `plumb owner` without `--prompt` (7.2); `plumb mod
hello|press|typed` (5.5; never the agent's); anything naming `PLUMB_AGENT_SESSION`; edits and
writes under `.plumb/log/`; in all launcher spellings (`plumb`, `uv run plumb`, `python -m
plumb`, `<path>/python(.exe) -m plumb`, `<path>/bin/plumb`). `install.py` generates the legacy
deny rules from the same table, and the mod's `tool.call` hook denies the same set (5.9), so
the three agree by construction.

**Status line.** Plugins in this build have no status-line field; the band (5.2) is the
status surface. The legacy `statusLine` setting keeps working for per-repository installs.

### 4.4 Commands and skills

`/plumb` is the plugin's one command (`commands/plumb.md`), routed by its arguments (6.1).
The skills are `plumb` (grounding, the owner-level rule, the routes) and `plumb-clarify`
(intent capture, R11 and R18). When an old per-repository `.claude/commands/plumb.md` exists,
the project's copy answers `/plumb` until it is migrated (4.7).

### 4.5 `/plumb init` (SR-083)

The owner types `/plumb init` (or says "set up plumb here"); the agent runs `plumb init`
from the plugin's environment. It writes, idempotently:

- `.plumb/` with the commented `config.yaml`, `claims.yaml`, `.gitignore`, `.gitattributes`
  (the record merge driver and the log layout), and seeds `refs/plumb/ids`;
- the record merge driver in the repository's git config, its command
  `"<PLUMB_HOME>/bin/plumb" merge-driver ...`;
- git hooks, each a short script calling the user-level launcher, never an interpreter path
  of the repository: `commit-msg` (the SR trailer check; it was missing, see the SP6
  follow-ups), `pre-merge-commit`, `prepare-commit-msg` and `post-merge` (the cheap merge
  hold of R17: no test run), and `pre-push` (the single full run). A hook the owner already
  has is never overwritten: init keeps it, names it in plain words, and the agent adds the
  one call line when the owner says "call plumb from my push hook";
- nothing under `.claude/`, no `CLAUDE.md` block, no copy of hooks, commands or skills.

Each hook script starts with a guard: when `PLUMB_HOME/bin/plumb` does not exist (a teammate
or a machine without the plugin), it prints one line ("plumb is not set up on this machine;
this commit was not checked") and exits 0. The merge boundary at push catches what such a
commit skipped.

The answer to the owner is plain: "plumb now follows this repository. It will show what you
asked for, keep the work tied to it and check merges and pushes." It never lists hooks.

"Don't use plumb here" adds the repository to `PLUMB_HOME/ignored` (`plumb plugin ignore`);
"use plumb here again" removes it.

### 4.6 git hooks and the merge driver: one line through the launcher

`plumb.launcher.git_hook_line(hook)` and `plumb.launcher.driver_command()` are the only
places that spell how git reaches plumb. Under the plugin (`PLUMB_PLUGIN_ROOT` set) they use
`PLUMB_HOME/bin/plumb`; outside it (the legacy CLI-only use) they keep today's interpreter
path. `boundary/premerge.py`, `boundary/prepush.py`, `mergedriver/gitconfig.py` and the
commit-msg installer call them (phase 0 wires the calls).

### 4.7 Existing per-repository installs: fallback and migration (SR-084)

Fallback: a repository set up with `plumb install claude-code` / `plumb hooks install`
keeps working exactly as before, on machines with or without the plugin. Where the plugin
is active too, `plumb-hook` exits at check 2 and the mod draws nothing but, once per
session, a band line: "plumb is set up here the old way; say 'move plumb to the plugin' to
switch". Nothing runs twice.

Migration, `plumb plugin migrate` (the owner says "move plumb to the plugin", or answers
yes when `/plumb init` offers it in such a repository):

1. removes from `.claude/settings.json` exactly the entries plumb's installer generates
   (the hook entries whose command runs `-m plumb hook` or `-m plumb statusline`, the deny
   rules of `plumb.guard`, and `env.PLUMB_AGENT_SESSION`), keeping every other entry;
2. removes `.claude/commands/plumb.md` and `.claude/skills/plumb*/SKILL.md` only when the
   file equals a rendering of the template (current version, or a digest listed in
   `src/plumb/plugin/known_templates.json`); an edited copy is kept and named;
3. removes the `CLAUDE.md` block between `<!-- plumb:begin -->` and `<!-- plumb:end -->`;
4. rewrites the git hooks plumb wrote (those carrying plumb's marker line) and the merge
   driver to the user-level launcher (4.6);
5. answers in plain words what changed and what it kept.

plumb's own repository keeps its per-repository install during development, so its hooks
run the code under development; the plugin stays silent there (check 2). This is the
fallback path, dogfooded.

### 4.8 Entry points and tests (PLUGIN)

| Guarantee | Entry point | Test |
|---|---|---|
| bundled environment only | session-start, prompt, pre-tool, post-edit, stop hooks; `/plumb` (agent's `plumb`); the mod's `$.process.run`; git hooks; merge driver | `tests/plugin/test_env.py::test_hook_uses_bundled_env` (one parametrized case per hook, a repository `.venv` holding a poisoned `plumb` package), `::test_git_hooks_use_user_launcher`, `::test_driver_uses_user_launcher`; MOD's `cli.test.ts` for the mod |
| bootstrap once, concurrently safe | two sessions starting together | `tests/plugin/test_env.py::test_bootstrap_lock`, `::test_stale_lock_taken_over`, `::test_getting_ready_line` |
| silence when not adopted | each of the five hook events | `tests/plugin/test_unadopted.py::test_only_hint_at_startup`, `::test_silent_<event>` (four), `::test_no_python_started` (timing and a sentinel `python` on the PATH that must not run), `::test_ignored_repo_silent` |
| init writes no per-repository copies | `plumb init` | `tests/plugin/test_init.py::test_claude_dir_untouched`, `::test_git_hooks_written`, `::test_commit_msg_holds_missing_trailer`, `::test_foreign_hook_kept`, `::test_hook_without_plugin_passes_with_line` |
| guard | `pre-tool` hook, legacy deny rules, the mod | `tests/plugin/test_guard.py` (one case per denied form and launcher spelling, and allowed `plumb status`), `::test_install_rules_from_same_table` |
| migration | `plumb plugin migrate` | `tests/plugin/test_migrate.py::test_removes_only_plumb_entries`, `::test_edited_copy_kept`, `::test_hooks_repointed`, `::test_legacy_repo_hooks_run_once` |
| manifest and marketplace valid | `claude plugin validate plugin`, `claude plugin validate .` | `tests/plugin/test_validate.py` (skipped when `claude` is absent; run in the lane gate) |
| bundle fresh | build script | `tests/plugin/test_bundle_fresh.py` |

## 5. The mod (R19; SR-085, SR-086, SR-087)

The mod is `plugin/hooks/register.tsx` and the modules it imports (TypeScript, function
hooks; `on(event, hook)`, `$` the engine interface), declared in `hooks/hooks.json`
`modules`. Its contract is Claude Code's declaration file (`types/claude-code.d.ts` of the
build; regenerated by the engine beside the plugin as `.claude-plugin/types/`). The API is
early access: the MOD lane re-reads the declarations of the build it runs on and adapts
names, never the behaviour below.

### 5.1 Division of labour and the handshake (DEC-024)

- At `session.start` the mod finds the repository root with `$.fs` (walking up for
  `.plumb/`). Not adopted, or an old per-repository install (4.7): the mod stays idle (no
  band, no process) apart from 4.7's one line.
- It reads `python` from `current.json`; missing: idle (the command hooks cover everything).
- It makes a 32-byte random key (`crypto.getRandomValues`), keeps it in `$.state`, and runs
  `plumb mod hello --session <id> --json` with `{"key_digest": "<sha256 hex of the key>"}`
  on stdin. plumb writes `.plumb/session/<id>/mod.json` (`{active, since, key_digest,
  heartbeat}`); the first registration of a session wins and a second is refused (exit 3),
  so a key registered by anyone after the mod is useless (DEC-025). The answer carries the
  session background (5.6) and the first snapshot (5.2).
- On each `turn.start` the mod refreshes `heartbeat` in `mod.json` with `$.fs.write` (no
  process).
- The command hooks read `mod.json` for their session id (one small file):
  - `session-start`: when the mod is active, leaves the brief out of its context and records
    `brief.json` `{injected: false}`; when it ran first (no `mod.json` yet), it injects as
    today and records `{injected: true}`, and the mod then adds no background until the
    background changes. Whoever comes first owns the session's first background; the other
    defers.
  - `stop`: when the mod is active and its heartbeat is not older than the turn's start, it
    writes `.plumb/session/<id>/present.json` (the summary line, the status card, the cards
    with their offers, the toasts; 5.2) and returns no `systemMessage`. A block (the
    model-facing instruction) is unchanged. Otherwise it prints its `systemMessage` as
    today.
  - `prompt`, `pre-tool`, `post-edit`: unchanged (no owner-visible output).
- Choke point: `plumb.mod.handshake` (`active(paths, session, turn_start) -> bool`,
  `deliver(core, session, output) -> HookOutput`, `background_owned(paths, session) ->
  bool`), called by `session_start.py` and `stop.py` (phase 0 wires the calls; the stubs
  keep today's behaviour).

### 5.2 The band (AbovePrompt)

`ui.render` on `AbovePrompt`, sized to `e.props.bodyColumns`, `next(e)` when
`e.props.hasSurvey`, when idle, or when the card setting is `off`.

- **Collapsed (default):** one line, the status card in plain words: a state glyph and word
  (`✓ aligned`, `● 2 await you`, `△ something changed`, `✗ a check fails`, `⇄ two versions
  to choose from`) and the intent summary ("deadline reminders · late fees"), with a
  **Hide** button (collapses to a single glyph; **Show** restores).
- **Expanded, only when it matters** (R9: a new or changed intent awaiting the owner, one of
  the three triggers, a regression, an intent conflict): the intent card in the R9 format,
  at the owner's level (6.3), with **Confirm** and **Show all** buttons when an offer exists
  (5.4), and **Open** (the pane). Once the owner confirmed, pressed Hide, or the card's
  content did not change since it was last drawn, the band collapses again.
- **Compact** (`present.card: compact`): never expands; it shows "● 2 await you" with the
  buttons.
- Source: `plumb mod snapshot --session <id> --json` (`ModSnapshot`, section 10), run off
  the prompt path after `turn.complete` and after a button press, stored in `$.state`;
  drawing reads `$.state` only.

### 5.3 The pane

`/plumb pane` (the mod answers it, 5.5), or **Open** in the band, opens pane `plumb` with
`$.ui.open`. It draws `plumb mod pane --session <id> --json [--focus <key>]` (`PaneTree`):
intents by title with their state and "done when" lines, each intent's requirements by title
and state, each requirement's examples as given/when/then with a test state (passing,
failing, not yet passing, no test). It shows titles and the owner's words, never IDs, paths
or hashes (a **Details** toggle shows IDs only when the owner asks). Buttons: **Confirm** on
what awaits the owner (5.4), **Open in Obsidian** (`plumb view --open`). The pane is
navigation only; Obsidian stays the deep review.

### 5.4 The summary line, toasts and notices

- **Summary line.** On `turn.complete` the mod calls `next(e)`, then, when
  `present.json` was written for this turn and its summary line is not empty, returns the
  result with `text` set to that one line, which Claude Code shows beneath the answer; the
  answer itself is never rewritten. Example: `plumb ✓ aligned — touched 'deadline
  reminders' · 7 checks pass`. Off when the card setting is `off`. No `present.json` for
  this turn: the result is returned unchanged.
- **Toasts** only for what matters, chosen in Python (`ModSnapshot.toasts`): a regression,
  an intent conflict (early or at merge), a decision that matters newly asked, the result of
  a button press. Each is shown once per content (`$.state` `toastsShown`).
- **Notices.** After a press the mod appends one owner notice (`$.session.append`,
  `type: "system"`: the model never reads it) and one model note (`type: "user"`, stored as
  meta: the owner never sees it as typed): "The owner pressed Confirm; now confirmed:
  SR-082 'plumb installs as a plugin', ... Do not ask again." Owner notices and model notes
  never mix.

### 5.5 `/plumb` answers in the transcript (CommandOutput)

The mod hooks `command.run` for the `/plumb` command (matcher on the resolved command name;
the MOD lane checks whether the build resolves it as `plumb` or `plumb:plumb` and matches
both). It answers itself, with `{ text }` (what the model also reads) and draws the row on
the `CommandOutput` site, for the deterministic routes: no argument and `status` (the status
card and what awaits, with buttons), `pane` (opens the pane), `confirm` without words (the
cards of what awaits, with buttons). Every other route is passed on with `next(e)` to the
command's prompt, so the agent resolves the owner's words and runs the CLI (6.1). When the
command's origin is the owner's own Enter (`origin.kind === "composer"`), the mod logs the
typed command once with `plumb mod typed --session <id>` (key on stdin), so a typed owner
command is logged even if the host does not run the prompt hook for slash commands (the
MOD lane checks which it does; both paths write the same `prompt` log entry, `via: hook` or
`via: mod`).

### 5.6 Context economy: the background, `$.state`, `session.append`

- **Background.** The mod's `prompt.compose` hook appends one section
  `{ id: "plumb:background", scope: "session", text }` where `text` is the session brief (a
  few lines and a pointer, R9). It is computed at `session.start` and replaced only when the
  snapshot's `background_hash` changes, so it is byte-identical across requests otherwise
  (cache-friendly). The session-start hook then leaves the brief out (5.1). The per-prompt
  delta (one line per newly relevant or changed record) is unchanged: it is model context
  from the prompt hook and already deduplicated by hash.
- **`$.state`** (`types/index.d.ts`, `PluginState['plumb']`): `key`, `root`, `python`,
  `background {hash, text, owned}`, `snapshot`, `shown` (card key to content hash: a card is
  expanded once per content), `toastsShown`, `band {isHidden}`, `pane {focus, details}`,
  `degraded`. Drawing reads it; handlers write it with `update`.
- **Dedupe guarantee:** nothing the mod injects or shows is injected or shown twice for the
  same content: the background once per hash, a card once per content, a toast once per id
  and content, a summary line once per turn.

### 5.7 Confirm buttons (SR-086, DEC-025)

- **Offers.** Every card the snapshot returns with buttons carries an `offer`: `{offer_id,
  action, targets: [{id, hash}]}` where `offer_id` is the digest of the canonical
  `(action, targets)`, and plumb writes it to `.plumb/session/<id>/offers/<offer_id>.json`
  with `drawn_at`. Actions: `approve` (records), `group` (the triage group, R8 A), `set` (an
  escalated set; only when `spec.offerable` is true, 8.5), `conflict` (one per side:
  `take: ours|theirs|combined|<branch>`), `revoke` (also **Undo** under a confirmation), `auto_approve` (`on|off`), `waive`
  (the full run at push).
- **Press.** **Confirm** runs `plumb mod press --session <id> --offer <offer_id>` with
  `{"key": "<hex>"}` on stdin. plumb checks the key's digest against `mod.json` (exit 3 on
  mismatch, no `mod.json`, or a missing key), reads the offer, and calls
  `owner_actions.perform(core, action, targets, via="button", proof={session, offer_id,
  key_digest})` (7.2). A target whose current hash differs from the offer's is left out and
  named ("changed since it was shown"); the rest is recorded as `by: owner, via: button`
  with the offer's digest, pinned to exactly those hashes. `plumb mod press` refuses (exit
  3) whenever the session marker is set, and the mod runs it with `PLUMB_AGENT_SESSION`
  removed from the process environment, so a `by: owner` button entry never carries a
  marker and concept 4.6's marker check needs no exception. The answer (done, left out, one
  plain line) becomes a toast, a notice and a model note (5.4), and the snapshot refreshes.
- **Show all** expands every card the offer covers (in the band, the pane or the command
  row); it records nothing. A typed "ok" keeps working through the relay, unchanged.
- **Trust model** (concept 4.6, extended): a press is an owner action because the model has
  no tool that presses buttons and the key never leaves the mod (it is not on disk, not in
  any prompt, and the agent's shell is denied the `plumb mod` owner commands). An agent
  that bypasses the guard deliberately could still forge an entry; that stays tamper-
  evident, not tamper-proof, as stated in the concept. `plumb show` and the merge-boundary
  glance label these approvals "you pressed Confirm" (and approvals from a typed slash
  command "you typed /plumb ...", grouped with the other relayed approvals, 7.2).

### 5.8 Fallback (SR-087)

- The module fails to load, the host has no mods, or `register` throws: no `mod.json` is
  written, and the command hooks print and inject everything as today.
- A hook of the mod fails at run time: its `.catch` handler returns `next(e)` and sets
  `$.state.degraded`; the mod then stops refreshing the heartbeat, so from the next turn the
  stop hook prints its `systemMessage` again. One dim line says "plumb's panel is off for
  this session; plumb keeps working in the background".
- Other hosts (Codex, Pi, Hermes, MCP) keep their adapters; the host-neutral core is
  unchanged.

### 5.9 The guard inside the mod

A `tool.call` hook on `Bash` and the edit tools denies, before the command hook runs, every
form `plumb.guard.denied` denies; the patterns come from `jargon.gen.ts`'s sibling
`guard.gen.ts`, generated from the same Python table, so the mod and the hook agree. It is a
fast path, never the only guard (the `pre-tool` command hook remains).

### 5.10 Tests (`claude plugin test plugin`, MOD)

`plugin/hooks/*.test.tsx`, each body looped over `['terminal', 'desktop'] as const`,
`$.process.run` mocked with recorded `plumb mod ... --json` answers (fixtures written by the
Python tests from real runs, `tests/mod/fixtures/*.json`, so both sides share them):

| File | Cases |
|---|---|
| `band.test.tsx` | collapsed one line; Hide and Show; expands only for a card that matters, once per content; compact never expands; `off` draws nothing; idle in a repository not adopted; old install shows the one migration line once |
| `buttons.test.tsx` | Confirm calls `plumb mod press` with the offer and the key on stdin, never in argv; the refreshed snapshot redraws; a toast and two appended rows (system notice, user meta note) with the right texts; Show all expands without any process call; no Confirm on a set the snapshot marks not offerable |
| `pane.test.tsx` | `/plumb pane` opens it; the tree draws titles and given/when/then with test states; Details shows IDs; Open in Obsidian runs `plumb view --open` |
| `summary.test.tsx` | `turn.complete` returns the line from this turn's `present.json`; an older `present.json` or none returns the result unchanged; the answer is never rewritten |
| `compose.test.tsx` | the background section is appended once, identical across three compositions, replaced once when `background_hash` changes, absent while `brief.json` says the hook injected it |
| `command.test.tsx` | `/plumb` and `/plumb status` answered with `{ text }` and drawn on `CommandOutput`; `/plumb explain the reminders` passes through; a composer-origin command is logged once with `plumb mod typed` |
| `guard.test.tsx` | `$.tool.call` with each denied form returns a deny; `plumb status` passes |
| `fallback.test.tsx` | no `current.json`: no hello, no band; a throwing hook falls back to `next(e)` and stops the heartbeat |
| `jargon.test.tsx` | every text the band, pane, summary line and toasts draw from the fixtures passes `jargon.gen.ts` (6.3) |

Python side (`tests/mod/`): `test_hello.py` (first registration wins; a second is exit 3),
`test_press.py` (wrong key, no key, agent shell: exit 3 and nothing written; a changed
target left out and named; pinned hashes equal the offer's), `test_handshake.py` (stop
writes `present.json` and no `systemMessage` while the mod is active; prints again when the
heartbeat is stale; session-start leaves out the brief and the background owner rule),
`test_snapshot.py` (the snapshot and pane trees pass `owner_text.jargon`, offers only for
offerable sets), `test_fixtures.py` (writes the shared fixtures).

`tsc -p plugin` type-checks the module where TypeScript is available (`npx -p
typescript@5 tsc -p plugin`); `claude plugin validate plugin` lists every hook and every `$`
call the mod makes.

## 6. The owner surface (R14, R18 presentation; SR-088, SR-089)

### 6.1 Feature to owner entry point matrix

The matrix lives in `docs/owner-matrix.md` (SURFACE writes it from this table and keeps it
complete; `tests/surface/test_matrix.py` checks that every `cli.ROUTES` key and every
subcommand appears either as an owner entry point or as agent plumbing with the owner words
that lead to it). "Owner-only" rows go through `owner_actions` (7.2). Status: **exists**
(route already in the `/plumb` template), **new** (SP7 adds it), **button** (SP7 adds a
button beside the words). Every CLI form in "The agent runs" is also an entry point of the
owner-level guarantee: 6.6 classifies each by what its answer is to the owner (`owner`: its
default text is the answer the agent shows; `agent`: its output is the agent's and the
owner sees a card instead; `none`: plumb prints nothing the owner sees), and
`test_matrix.py::test_every_route_form_classified` fails on a form without a class.

| # | Feature | The owner says or presses | The agent runs | Owner-only | SP7 |
|---|---|---|---|---|---|
| 1 | Install plumb | `/plugin marketplace add <plumb repository>`, `/plugin install plumb@plumb` (Claude Code's own commands) | nothing | | new (R15) |
| 2 | Adopt a repository | `/plumb init`, "set up plumb here" | `plumb init` | | new |
| 3 | Not here / here again | "don't use plumb here", "use plumb here again" | `plumb plugin ignore [--undo]` | | new |
| 4 | Move an old install to the plugin | "move plumb to the plugin" (offered by `/plumb init`) | `plumb plugin migrate` | | new |
| 5 | Status card | the band; `/plumb`, `/plumb status`, "where are we?" | `plumb status --card` (the mod, 5.5) | | button |
| 6 | Session brief | automatic (background, 5.6); "what are we building?" | `plumb brief` | | exists |
| 7 | Another repository | "/plumb status for <that repository>" | `plumb status --root <path>` | | new |
| 8 | Explain anything | `/plumb explain <anything>`, "why does X exist?" | `plumb explain` | | exists |
| 9 | What a change reaches | `/plumb impact <anything>` | `plumb impact` | | exists |
| 10 | Show a record in full | `/plumb show <anything>`, "show me the reminder rules" | `plumb resolve`, `plumb show` | | new |
| 11 | Deep review | `/plumb review [<anything>]` | `plumb review` | | exists |
| 12 | Pane | `/plumb pane`; band **Open** | the mod (`plumb mod pane`) | | new |
| 13 | Obsidian view | `/plumb view`; pane **Open in Obsidian** | `plumb view --open` (every note at the owner's level, 6.3; what awaits the owner names `/plumb confirm <title>` or "say ok in a Claude Code session", never a CLI command) | | button; text rewritten |
| 14 | Alignment of a scope | `/plumb align [<anything>]`, "how well does X hang together?" | `plumb align` | | new route |
| 15 | Faithfulness of a requirement | "does X do what I meant?" | `plumb fidelity` (advisory) | | new route |
| 16 | Drift | `/plumb drift`, "what drifted?" | `plumb drift` | | new route |
| 17 | Show what awaits me | `/plumb confirm` (no words), "what awaits me?" | `plumb confirm` (cards with buttons; approves nothing) | | button |
| 18 | Confirm records | `/plumb confirm <anything or IDs>` or `/plumb approve <...>`: confirmed at once only when the command names the records by ID or names only records shown in full in the agent's previous reply; otherwise plumb resolves the words, shows the cards (with **Confirm**) and confirms on the owner's next "ok" or press; "which one do you mean?" when the words fit several sets (7.2); "ok"/"yes" after cards; **Confirm** | `plumb owner approve --prompt --quote` (recorded `agent-relayed`, `via: command`) / `plumb confirm <words>` then `plumb relay` / `plumb mod press` (`by: owner`, `via: button`) | yes | button, new |
| 19 | Confirm a decision | answer its question ("A", "email only"); `/plumb approve <decision words or ID>` (row 18's rule: at once by ID or when shown in the previous reply, else shown first); **Confirm** | `plumb relay`, `plumb owner approve --prompt --quote` (both `agent-relayed`) (the pick: `plumb decide --supersede` when the owner picks another option) | yes | new (R14 "Approving DEC should be also a command") |
| 20 | Revoke | `/plumb revoke <anything or IDs>` (same rule as row 18: at once by ID or for records shown in the previous reply, else shown first with **Revoke**); **Undo** under a confirmation; **Revoke** on a card | `plumb owner revoke --prompt --quote` (`agent-relayed`, `via: command`) / `plumb mod press` (`by: owner`) | yes | new |
| 21 | Triage view | `/plumb triage`, "what can I confirm in one go?" | `plumb triage` | | new route |
| 22 | Confirm a group | "ok" to the offer line; **Confirm all N** | `plumb relay --group` / press | yes | button |
| 23 | Escalation suggestion | "yes, plan it properly" / "no, keep it small" | `plumb escalate decline --prompt --quote` | owner words | exists |
| 24 | Escalated plan: see it | `/plumb plan <anything>`, "show me the plan for X" | `plumb spec show` | | new route |
| 25 | Escalated plan: structure check and repair | automatic (the agent, 8.5) | `plumb spec check`, then fixes, again | | new |
| 26 | Escalated plan: approve | "ok" to the set offer (only for a clean set); **Confirm the plan** | `plumb relay --set` / press | yes | button, gated |
| 27 | Automatic confirmation | `/plumb auto-confirm on` / `off`; **Turn on** / **Turn off** in `/plumb settings` | `plumb owner auto-approve on --prompt --quote` (`agent-relayed`, `via: command`) / press (`by: owner`) | yes | new |
| 28 | Settings | `/plumb settings` | `plumb owner settings --prompt --quote` (read only; owner-only today, kept; logged `agent-relayed`, `via: command`) | yes | new |
| 29 | Card size | `/plumb card full\|compact\|off`, "make the card smaller" | `plumb config card` | | new route |
| 30 | JEV judge set up | `/plumb jev setup [provider]`, "use OpenRouter for JEV" | `plumb jev setup`, `plumb jev status --probe` | | exists |
| 31 | JEV status | `/plumb jev status` | `plumb jev status --probe` (plain-words rendering, 6.3) | | exists |
| 32 | JEV calibration | `/plumb jev calibrate`, "is JEV good enough to confirm for me?" | `plumb jev calibrate` | | exists |
| 33 | Run the checks | "run the checks for X" | `plumb tests run`, `plumb verify` | | agent |
| 34 | Waive the full run at push | `/plumb waive the full run` (with a reason in words); **Waive** on the push report's card | `plumb owner waive --prompt --quote` (`agent-relayed`, `via: command`) / press (`by: owner`) | yes | new |
| 35 | Merge check | `/plumb merge-check`, "can I merge?" | `plumb merge-check` | | exists |
| 36 | Merge, finish, undo | "merge feat-x", "finish the merge", "continue the rebase", "undo the merge of feat-x" | git and `plumb merge-check --hook ...` as the template says | | exists |
| 37 | Hooks at merge and push | covered by `/plumb init`; "call plumb from my push hook" | adds the `hook_line` to the owner's hook | | exists |
| 38 | ID clash after a merge | `/plumb merge-fix`, "fix the ID clash" | `plumb merge-fix` | | exists |
| 39 | Intent conflicts | `/plumb conflicts`, "what conflicts?" | `plumb conflicts` | | exists |
| 40 | Choose a side | "keep feat-x's" / "keep this one" / "both"; **Keep feat-x's** / **Keep this one** / **Keep both** | `plumb conflict relay` / press | yes | button |
| 41 | Propose a combination | "combine them: ..." | `plumb conflict propose` | | exists |
| 42 | Early intent conflict | answer the early card in its words; the same buttons | `plumb conflict relay` | yes | button |
| 43 | Other branches' work | `/plumb status`, "what are the other branches working on?", "drop that work" | `plumb inflight`, `plumb inflight drop` | | exists |
| 44 | Text-merge leftovers | "keep mine" / "keep theirs" / "keep the changed one" / "keep it removed" | git as the template says, then `plumb validate` | | exists |
| 45 | Migrate old logs | "migrate the logs" | `plumb log migrate` | | exists |
| 46 | IDs look off | "the record numbers look off" | `plumb ids sync` | | new route |
| 47 | Import pi-agent-factory records | `/plumb import <where they are>`, "bring in my old requirements" | `plumb import` (dry run, the summary, then apply on the owner's ok) | owner words to apply | new route |
| 48 | Other hosts | "set plumb up for Codex / Pi / Hermes" | `plumb hosts install <host>` | | new route |
| 49 | Read-only MCP server | "let <tool> read plumb's records" | writes the MCP config for `plumb mcp serve` | | new route |
| 50 | Capture intent | just ask ("add a multiply"); answer the questions; "ok" to the read-back | `plumb clarify`, `plumb capture`, `intent`, `example`, `decide`, `new` (proposed records) | | exists; R18 |
| 51 | Known defect | "that's a known bug, keep track of it" | `plumb new nc` | | new route |
| 52 | Why was my commit or push held? | "why was my commit held?" | `plumb trailers`, `plumb claims check`, `plumb merge-check` | | new route |
| 53 | A reviewed change is fine | "the change to <title> is fine" (after `/plumb review`) | `plumb repin` (never confirms) | | exists (review) |
| 54 | Help | `/plumb help`, "what can plumb do?" | the template's plain-words list | | new |
| — | Agent plumbing | (no owner step) `link`, `hook`, `hooks`, `install`, `statusline`, `map`, `judge`, `judgment`, `merge-driver`, `turn`, `mod`, `owner` (only with the owner's logged words), `button` forms | | | |

### 6.2 The `/plumb` command

`templates/plumb-command.md` (SURFACE) routes every row of 6.1, each route one bullet: what
the owner may say, the CLI the agent runs, and how to answer at the owner's level. The
frontmatter's `allowed-tools` lists every agent-side form the routes use (never the
owner-only forms without `--prompt`). Rules stated once at the top: take the owner's words
as they are; ask "which one do you mean?" in the owner's terms; never ask the owner to type
or run anything except a `/plumb` route or plain words; answer with titles, the owner's own
words, examples and test states, explaining any internal concept first (6.3); show the
owner only the default text of an `owner` form (6.6), or its `--details` text when the
owner asked for detail; read for yourself with `--agent` or `--json`; never paste an
`--agent` text, the output of an `agent` form or git's output.

### 6.3 Owner-visible text: two scanners, one module (SR-089)

Guarantee: no owner-visible text names a shell command, and none uses plumb's or the code's
internals without first explaining them in one plain sentence (R14, R18).

Choke point: `plumb.present.owner_text` (SURFACE). It holds every owner-visible string of
SP7 as a constant or small formatting function (lanes import them; MOD's TypeScript gets
the few it draws itself, button labels and fixed lines, from `jargon.gen.ts`'s sibling
`text.gen.ts`, generated) and exports:

- `shell_commands(text) -> list[str]`: everything `bare_cli_verbs` finds, plus `uv run`,
  `uvx`, `python -m`, `.venv`, `pip install`, `git <verb>`, `--no-verify`, any `--flag`, a
  line starting with `$ `, and a backticked span holding any of these. A `/plumb ...` route,
  Claude Code's own `/plugin ...` commands and the label prefix `plumb:` pass.
- `jargon(text, *, details=False) -> list[str]`: every internal term in `JARGON` found in
  `text`: hash, digest, pin/pinned, sha256, record IDs (`INT-`, `SR-`, `DEC-`, `FEAT-`,
  `NC-`, `IC-`, `EX-`) not beside their quoted title on the same line, `.plumb` paths,
  file paths, test node ids (`::`), stale link, relay, trailer, frontmatter, stated set,
  session marker, prompt digest, exit code, link kinds (`derives_from`, `verified_by`,
  `implemented_by`), repin, JSONL. A term passes when its one-sentence explanation from
  `CONCEPTS` appears earlier in the same text (the explain-first rule), or with
  `details=True` (the owner asked for details: `/plumb show <x> in detail`, the pane's
  Details, the vault's frontmatter and `## Details` sections). Record IDs inside the
  owner's own quoted words (a span the renderer marks as the owner's quote, or a
  double-quoted span in a record field) pass: the owner typed them.
- `CONCEPTS`: the plain explanation of each term used in owner text, for example
  "confirmed wording: plumb remembers the exact wording you confirmed and asks again when it
  changes"; `explain(term) -> str`.

The rewrite covers every surface below; each surface's test renders it for real and asserts
`shell_commands(out) == []` and `jargon(out) == []` (SURFACE; one test per surface):

| Surface | Today (examples) | Test |
|---|---|---|
| Stop hook summary and cards (`systemMessage`, and `present.json` for the mod) | "touched DEC-001", "SR-001/EX-1", "(unconfirmed-edit)", "covering tests 0: 0 fresh pass", "see plumb show SR-..." | `tests/surface/test_summary_text.py` (each card kind: intent, decision, group offer, set offer, conflict, regression, early conflict) |
| Status card (band, legacy status line, `plumb status --card`) | IDs, counts by kind | `tests/surface/test_status_text.py` |
| Session-start owner lines (getting ready, adopt hint, migration line, brief's owner part) | | `tests/surface/test_session_text.py` (and the sh launcher's hint equals `ADOPT_HINT`: `tests/plugin/test_unadopted.py::test_hint_from_owner_text`) |
| `/plumb` answers drawn by the mod (status, confirm cards, pane tree) | | `tests/mod/test_snapshot.py` (5.10) |
| Route answers: the default text of every CLI form of 6.1 whose answer the agent shows the owner (every `owner` form of 6.6: the views `explain`, `review`, `confirm`, `align`, `impact`, `triage`, `spec show`, `conflicts`, `inflight`, and `drift`, `show`, `resolve`, `fidelity`, `brief`, `status --root`, `init`, `plugin ignore`, `plugin migrate`, `import`, `merge-fix`, `ids sync`, `log migrate`, `escalate`, the success lines of `relay`, `owner` and `conflict relay`, and the rest of 6.6's list), plus `/plumb help` | `drift`: "SR-082 uncovered examples: EX-1, EX-2 ...", "SR-001 EX-1 is verified by the whole file tests/core/test_model.py; proposed node tests/core/test_model.py::test_identity_...", "stale links: ..."; `fidelity SR-090`: "fidelity packet SR-090 (sha256:520c92add09e)", "tier escalate-llm"; `show DEC-017`: ".plumb/decisions/DEC-017.md", "plumb relay --group ... plumb triage --approve"; `brief`: "(records in .plumb/, test map in .plumb/test_map.txt)" | `tests/surface/test_answers_text.py`, one case per `owner` form, parametrized over `present.answers.FORMS` (6.6) |
| The Obsidian vault (`plumb view`, the pane's **Open in Obsidian**): every record note, `awaiting-you.md`, `by-feature.md`, `drift.md`, the Canvas labels | each unconfirmed note: `## Confirm (your terminal, or say "ok" in a session)` then `` `plumb approve SR-090` ``; `awaiting-you.md`: "Confirm in your own terminal (copy a command)", `` `plumb triage --approve low-risk` ``, one `` `plumb approve <ID>` `` per waiting record; bare `[[SR-090]]` links; "stale"/"dangling" link wording | `tests/surface/test_view_text.py`: generates the vault for a fixture repository (a confirmed, a proposed, a changed and a conflicted record, a group, a drift entry) and runs both scanners on every generated note and Canvas label; frontmatter (R9 keeps state and hash there) and a section headed `## Details` are scanned with `details=True`, everything else with `details=False`. The notes say "To confirm, type /plumb confirm <title> or say ok in a Claude Code session; editing this note confirms nothing"; wikilinks carry the title as their label (`[[SR-090\|An unrelated request never blocks an ok]]`) (SR-089 EX-6) |
| Merge report (`merge-check`, `check --merge`, `validate --merge`) | "`plumb approve SR-001 SR-003 DEC-001`, or say ok", "review the change, then plumb repin SR-001#3", "+N more (plumb merge-check --json)", "(plumb fidelity SR-...)", "(plumb tests run --nodes <id>)", "(plumb spec show ...)", "`plumb approve --exempt`", `.plumb/requirements/...` paths | `tests/surface/test_merge_text.py` (one case per report section) |
| pre-push hook output | the report above plus "push with --no-verify to bypass the hook", "(plumb tests waive --merge <sha> --reason ...)", "plumb link SR-001 implemented_by app.py" | `tests/surface/test_prepush_text.py` (a real `git push` to a bare remote in a temporary repository) |
| pre-merge-commit, prepare-commit-msg, post-merge output | | `tests/surface/test_premerge_text.py` |
| commit-msg hook output (trailer check) | names `SR:` trailers and IDs | `tests/surface/test_commit_text.py` |
| Merge driver stderr (SP6 constants) | | kept: `tests/mergedriver/test_owner_text.py`, plus `jargon` |
| Refusals the owner can see (owner actions, button presses, typed commands) | "exit 3", "--prompt <digest>" | `tests/surface/test_refusal_text.py` (refusal text has two parts: the owner's line and the agent's line; only the owner's is scanned, and the agent's is never drawn) |
| `jev status` rendered for the owner | "judgment.backend", "validated against" | `tests/surface/test_jev_text.py` |
| `validate` warnings the agent may repeat (`auto-approve-mirror`) | "plumb config auto-approve on, in the owner's own terminal" | `tests/surface/test_validate_text.py` |
| The records' own owner-facing content (what fills most of every card: title, read-back, will, won't, assumptions, done when, statement, examples, a decision's question, options and reasons, a feature's title and description) | SP7's own records before this review: "the commit-msg check of SR trailers", "its reference and its digest", "in_reply_to", "done_when", "never the repository's .venv", "refused with exit 3" | checked where it is written, not where it is drawn (6.5): `tests/capture2/test_record_text.py`, one case per write entry point |
| README owner sections, `docs/owner-matrix.md`, `docs/hosts.md` owner parts | `uv run plumb ...` in Quickstart and "At a merge boundary" | `tests/surface/test_docs_text.py` (every Markdown section outside a heading marked `<!-- agent-interface -->`) |

R9 allowed the vault to "carry copyable confirm commands"; R14 ("you should never have to
tell me to run those bash commands") supersedes that: the vault names `/plumb confirm
<title>` or "say ok in a Claude Code session", and editing a note still confirms nothing.

The surfaces above are what hooks, the mod and the vault draw. What the agent relays from
the CLI on any route of 6.1 is the same guarantee's other half, with its own choke point and
one test per CLI form: 6.6.

Every SP6 constant of `owner_text` gains the `jargon` assertion (`tests/present/
test_owner_text.py::test_every_constant_passes` checks both scanners).

**Owner text vs agent text.** Owner-only refusals and hook answers carry two parts: the
owner's line (scanned, drawn) and the agent's instruction (the CLI form to use; never shown
to the owner: the stop hook's block reason, the prompt hook's context, `--json` fields
named `agent`). `HookOutput` and the `--json` answers keep them in separate fields, so a
surface cannot draw the agent's part by accident.

### 6.4 The README

The README is split: "Using plumb" (owner level: installing with `/plugin`, `/plumb init`,
what the band, pane and summary show, what to say, the buttons, what happens at merge and
push) and "The agent's interface" (the CLI reference, under a heading marked
`<!-- agent-interface -->`). The Quickstart has no shell command. `docs/hosts.md` keeps its
capability tables for agents and gains the plugin and mod rows.

### 6.5 Record content at the owner's level (R18; SR-089 EX-7, EX-8)

Guarantee: **the owner-facing fields of a record are at the owner's level.** Most of what a
card, the pane, the vault or a read-back shows is the record's own content, which the agent
writes and the owner confirms; scanning only the renderers' fixed wording would miss it.

Owner-facing fields: `title`; an intent's `readback`, `will`, `wont`, `assumptions` and
`done_when`; a requirement's `statement` and each example's `given`, `when`, `then`; a
decision's `question`, `chosen`, `alternatives` and `rationale`; a feature's `description`;
an NC's title and description. Not scanned: `quote` and `in_reply_to.text` (the owner's own
words, or the proposal exactly as it was shown), IDs inside double-quoted spans (the owner
typed them), `links`, and the new agent-only field `agent_notes`.

`agent_notes` (optional string, every kind) is where technical detail goes: the spec
section, file names, CLI forms, test names. Like `links`, it is outside the record's
hash (an approval pins the content the owner was shown, and the owner is never shown it);
it is drawn only by `plumb show --agent` (6.6), the pane's and the vault's Details, and
`--json` for the agent.

Choke point: `store.write_record` (every record write goes through it) calls
`present.owner_text.record_gaps(kind, fields, previous) -> list[Gap]`, which runs
`shell_commands` and `jargon` (with the quote exemption of 6.3) on each owner-facing field
that is new or differs from the stored version. Two modes, chosen by the caller:

- `refuse` (the default; every path where the agent writes the content now): any gap
  refuses the write, exit 2, nothing written; the answer is agent-only (`Gap.agent_line`:
  the field, the term, and "say it in the owner's words, or move it to agent_notes"), never
  an owner question, like the structure check of 8.5. The agent rewrites and retries.
- `report` (content the agent did not write now: `plumb import`, the record merge driver,
  `plumb merge-fix` renumbering, the conflict choice taking one side): the write proceeds
  and the gaps go to the agent's repair list.

Link-only writes (`store.set_links`: `link`, `repin`, approvals) never scan. `plumb
validate` lists the gaps of records written before SP7 as agent-facing `owner-text`
warnings (never shown to the owner), so the agent rewords a record when it next changes it.
The SP7 records themselves (FEAT-007, INT-023, SR-082 to SR-095, DEC-023 to DEC-025) were
reworded to this rule before they are offered (this spec's review, 2026-10-07).

Entry points and tests (`tests/capture2/test_record_text.py`, one each): `plumb capture` (a
statement naming "digest": refused, nothing written, the agent line names the field and
term), `plumb intent` (a read-back naming ".venv"), `plumb new` (a title with an ID and no
title), `plumb example` (a `then` saying "exit 3"), `plumb decide` and `decide --supersede`
(an option saying "uv run plumb"), `plumb conflict propose` (a combined version), `plumb
import` (written, gaps reported), the merge driver and `merge-fix` (written, gaps reported),
the library `api.write_record` (refused), `link`/`repin` of an old record with jargon (not
scanned), a quote holding "uv run" and an `agent_notes` holding paths (both pass, and
changing `agent_notes` leaves the hash unchanged), `validate` (old records listed as agent
warnings).

### 6.6 Route answers at the owner's level (every route of 6.1; SR-089 EX-9)

Guarantee: **every CLI answer the agent may show the owner, on any route of 6.1, is at the
owner's level**: `shell_commands(out) == []` and `jargon(out) == []`. The surfaces of 6.3
cover what hooks, the mod and the vault draw; this covers what the agent relays from the
CLI. Measured in plumb's own repository on 2026-10-07, before this rule: `plumb drift`
printed "SR-082 uncovered examples: EX-1, EX-2 ...", "SR-001 EX-1 is verified by the whole
file tests/core/test_model.py; proposed node tests/core/test_model.py::test_identity_..."
and, for out-of-date links, "stale links: ..."; `plumb fidelity SR-090` printed "fidelity
packet SR-090 (sha256:520c92add09e)" and "tier escalate-llm"; `plumb show DEC-017` printed
".plumb/decisions/DEC-017.md" and "plumb relay --group ... plumb triage --approve"; `plumb
brief` printed "(records in .plumb/, test map in .plumb/test_map.txt)". Each is on a route
the matrix gives the owner ("what drifted?", "does X do what I meant?", `/plumb show`, "what
are we building?").

**Entry points: every CLI form of 6.1.** `plumb.present.answers.FORMS` (SURFACE; complete
from phase 0) maps each form in 6.1's "The agent runs" column to its class:

| Class | Forms (6.1 rows) | What the owner sees |
|---|---|---|
| `owner` | `init` (2); `plugin ignore [--undo]` (3); `plugin migrate` (4); `status --card` (5, 43; its own row in 6.3); `brief` (6); `status --root <path>` (7); `explain` (8); `impact` (9); `resolve`, `show` (10); `review` (11); `view --open` (13: its answer line; the vault is 6.3's row); `align` (14); `fidelity` (15); `drift` (16); `confirm` and `confirm <words>` (17, 18); the success line (`OwnerActionResult.owner_line`) of `relay` in every form, `owner <action>`, `conflict relay` and `escalate decline` (18 to 23, 26 to 28, 34, 40, 42; their refusals are 6.3's refusal row); `triage` (21); `escalate` (23); `spec show` (24); `config card` (29); `jev setup`, `jev status --probe`, `jev calibrate` (30 to 32); `tests run`, `verify` (33); `merge-check` (35, 52; its own rows in 6.3); `merge-fix` (38); `conflicts` (39); `conflict propose` (41); `inflight`, `inflight drop` (43); `log migrate` (45); `ids sync` (46); `import`, dry run and apply (47); `hosts install` (48); `trailers`, `claims check` (52); `repin` (53) | the command's default text, rendered by `present.answers.render` |
| `agent` | `clarify`, `capture`, `intent`, `example`, `decide` (and `--supersede`), `new` (19, 50, 51); `spec check` (25); `merge-check --hook ...` (36); `validate` (44); `mod pane` (12) | never the output itself: the card, summary or line the hooks and the mod draw (6.3's stop-hook, merge-hook, `validate` and pane rows) and the record content checked where it is written (6.5) |
| `none` | Claude Code's `/plugin` commands (1); git (36, 44: the agent says in plain words what git did and never pastes git's output); the hook line the agent adds (37); the MCP configuration (49); help (54) | the agent's own words under the template's rules (6.2); help's plain-words list is scanned in the generated command (`test_answers_text.py::test_help`) |

**Choke point: `plumb.cliutil.answer(args, form, payload, agent_text)`** (coordinator,
phase 0). Every command of an `owner` form prints its answer through it and nowhere else:

- `--json`: the payload, the agent's structured read (kept where `--json` exists; added
  where it was missing);
- `--agent` (new in `add_common`): today's text, the agent's plain read, CLI hints
  included; never shown to the owner;
- `--details` (new in `add_common`): `present.answers.render(form, payload, details=True)`,
  the owner's answer with the internals beside it (record numbers, file names, fingerprints),
  for an owner who asked for detail ("/plumb show the reminders in detail"); it passes
  `shell_commands`, and `jargon` with `details=True`;
- default: `present.answers.render(form, payload)`, the owner's answer (SURFACE), built from
  `owner_text`'s constants and `CONCEPTS`: titles beside or instead of IDs, examples in
  their given/when/then words, test states as "passes" or "fails", no file or folder names,
  no hashes, and the next step as a `/plumb` route or plain words.

A renderer returning `None` (the phase-0 stub) prints today's text. Exit codes are
unchanged.

First wordings for the measured cases (SURFACE finishes them in `owner_text`):

- drift: "'<title>': 2 of its examples have no check yet (when ..., then ...)"; "'<title>',
  example 1, is checked only by a broad group of tests; I can point it at the one test that
  matters"; for an out-of-date link, the concept first: "plumb ties parts of the work
  together so it notices when one changes and the other may need a look. '<title>' changed
  after '<other title>' was tied to it; say /plumb review <title> to look."
- fidelity: the requirement's title, its examples in words, their test states and the
  judge's word in plain terms ("likely what you meant", "unsure: I will read it myself and
  tell you"). The packet the host agent judges (R4) is the `--json` and `--agent` form.
- show: the record's card by title (read-back, will, won't, assumptions, done when,
  examples with test states) and, when it awaits the owner, "say ok or type /plumb confirm
  <title>"; never a file path or a CLI command.
- brief: what is being built, by title, and what awaits the owner; never where plumb keeps
  its files.

The agent reads with `--agent` or `--json`: the `/plumb` template, the `plumb` skill, the
prompt hook's delta pointer and the session brief's pointer name those forms, so R9's
progressive disclosure is unchanged; only the default text changes. Tests that assert
today's default text of an `owner` form switch to `--agent` in phase 0, while the change is
still a no-op.

Tests, one per entry point:

- `tests/surface/test_answers_text.py::test_owner_answer[<form>]`, parametrized over every
  `owner` form of `FORMS`: the command run for real on a fixture repository (a confirmed, a
  proposed, a changed and a conflicted record, an example without a check, an example
  checked by a whole test file, an out-of-date link, an ID clash, a fake calibrated JEV), the
  default output through both scanners, the `--details` output through `shell_commands` and
  `jargon(details=True)`, and `--agent` equal to today's text; `::test_drift_kinds`, `::test_fidelity_answer`,
  `::test_show_awaiting`, `::test_brief_no_paths` hold the measured cases above;
  `::test_help` scans the generated `/plumb help` list.
- `tests/integration/test_answer_choke_point.py::test_owner_form_emits_through_answer[<form>]`
  (phase 0): with `present.answers.render` replaced by a sentinel renderer, each `owner`
  form's default output is the sentinel's, and its `--json` output is the payload; the
  forms SP7 adds (`plugin ignore`, `plugin migrate`, `owner <action>`) get the same check in
  their lane's tests.
- `tests/surface/test_matrix.py::test_every_route_form_classified`: every CLI form of
  `docs/owner-matrix.md` has a class in `FORMS`, and every `owner` form has its
  `test_owner_answer` case.
- `tests/surface/test_command_routes.py::test_agent_forms_never_shown`: each `agent` form's
  route tells the agent to answer from the card, never by pasting the output; each `owner`
  form's route says to show the default text (or `--details` when the owner asked for
  detail) and to read for itself with `--agent` or `--json`.
- The owner e2e (12 item 2) scans the stdout of every CLI call the scripted agent makes on
  an `owner` form, and fails when the scripted agent shows the owner an `agent` form's
  output or an `--agent` text.

## 7. Owner actions without a shell (R14; SR-088)

### 7.1 What is owner-only

`approve` (records), `revoke`, `group` (triage), `set` (an escalated plan), `conflict` (a
side), `auto_approve` (`on|off`), `settings` (read), `waive` (the full run at push). The
relay paths that already exist (an ok in words) stay as they are for `approve`, `group`,
`set` and `conflict`.

### 7.2 One choke point: `plumb.owner_actions` (SURFACE)

```python
def perform(core, action: str, targets: Sequence[Target], *, via: str,
            proof: Mapping[str, Any]) -> OwnerActionResult: ...
def require_owner_action(core, action, targets, *, via, proof) -> None: ...  # raises Refused (exit 3)
```

`via` is one of:

- `terminal`: today's `approvals.require_owner` (marker refused, an interactive terminal and
  a `y`); unchanged.
- `words`: the existing relay checks (`approvals.relay`: prompt digest, quote verbatim,
  affirmation, owner scope, stated set), for `approve`, `group`, `set`, `conflict`.
- `command`: a slash command the owner typed. `proof = {prompt: <digest>, quote: <the whole
  command>}`. Accepted only when the digest names a prompt logged `via: hook` or `via: mod`
  (never `via: turn`: a self-recorded message cannot carry an owner-only setting), the quote
  is the entire prompt text, and it parses (`owner_actions.parse_command`) to exactly this
  action and these targets: `/plumb confirm|approve <IDs or words>`, `/plumb revoke <IDs or
  words>`, `/plumb auto-confirm on|off`, `/plumb settings`, `/plumb waive the full run
  <reason words>`. The agent runs this CLI from its own shell, under the session marker, so
  the entry is honest about it: `by: agent-relayed`, `via: command`, the prompt digest, and
  the whole typed command as the quote (R2). It is never `by: owner`.

  **Show first (the stated-set rule, concept 4.6 check 3).** For `approve`, `revoke`,
  `group` and `set`, `perform(via="command")` acts at once only on targets the owner has
  already seen: every target is named by ID in the typed command, or was shown in full in
  the agent's reply just before that prompt (the stated set of that turn, section 6.6 of
  the concept). Otherwise it writes nothing and answers `show_first` with the resolved
  candidates: plain words are resolved with `plumb resolve` (R9); when they point to one
  set of records (the resolver's best group, with no second group within its margin), the
  agent runs `plumb confirm <the owner's words>`, which shows that set's cards in the
  reply, records them as this turn's stated set and, with the mod, as an offer with
  **Confirm** (or **Revoke**); plumb confirms or revokes only on the owner's next "ok"
  (relayed, `via: words`) or press (`via: button`), pinned to exactly the hashes shown.
  When the words fit several sets, nothing is shown as confirmable: plumb lists the
  candidate groups and asks "which one do you mean?" in the owner's terms. Either way the
  entry records `resolved_from: <the owner's words>` beside the targets, so the merge-
  boundary glance reads "you typed /plumb confirm the reminder timing; plumb showed you
  <titles>; you said ok". This is R14's order: "resolves the records, shows what is being
  confirmed, and relays the owner's typed words". Plain words alone never approve or
  revoke a record the owner has not been shown.

  **`plumb check` after a typed command.** `plumb check` re-checks a `via: command` entry
  like every `agent-relayed` entry (concept 4.6): its prompt digest is in the prompt log,
  logged `via: hook` or `via: mod` before the entry, and its stored quote matches its quote
  digest. For `via: command` the affirmation-term check is replaced by the parse check: the
  stored quote parses (`parse_command`) to the entry's action and targets (or to its
  `resolved_from` words). The marker rule for `by: owner` entries is unchanged; no
  `via: command` entry is `by: owner`, so a `/plumb confirm` leaves `plumb check` clean.
- `button`: `proof = {session, offer_id, key_digest}` from `plumb mod press` (5.7): the
  offer exists in the session, was drawn before the press, its action and targets are
  these, and the targets' hashes are rechecked.

Each action then calls the existing library function (`approvals.approve`,
`approvals.revoke`, the triage group approval, `spec.approve_set`, the conflict choice,
`configfile.set_auto_approve`, the config view, the waiver), writing `by: owner` for
`terminal` and `button`, and `by: agent-relayed` for `words` and `command`, each with `via`
and the proof's digests. The merge-boundary glance and `plumb show` group every
`agent-relayed` entry (words and typed commands) with the auto-JEV ones, worded at the
owner's level: "you said 'ok' to: <titles>", "you typed /plumb confirm <words>; plumb
showed you <titles>", "you pressed Confirm on: <titles>" (owner_text, 6.3). `auto_approve on` still refuses without a passing calibration for
the current JEV model version (R12.1), now with a plain line ("JEV has not been tried on your
own past answers yet; say /plumb jev calibrate first"). `set` refuses a set that is not
clean (8.5). The CLI is `plumb owner <action> ... --prompt <digest> --quote "<text>"` for
`command` (the agent runs it after the owner typed the command) and `plumb mod press` for
`button`; `plumb approve`, `revoke`, `triage --approve`, `spec approve`, `config
auto-approve`, `config show`, `tests waive` and `conflict choose` keep their terminal form,
now also routed through `perform(..., via="terminal")`.

Entry points and tests (`tests/surface/test_owner_actions.py`), one per action and via: each
`command` case with a hook-logged typed command (accepted, and the entry is `by:
agent-relayed`, `via: command`, with the whole command as the quote), the same text typed in
a self-recorded message (refused), no logged prompt (refused, exit 3, nothing written), and a
command whose words name another action or other targets (refused); each `button` case is in
`tests/mod/test_press.py` (the entry is `by: owner`, `via: button`, marker `none`); each
`terminal` case keeps its test with no marker and stdin a pipe holding "y" (exit 3).

Guarantee "plain words never approve unseen records", one test per entry point
(`tests/surface/test_show_first.py`): `/plumb confirm <words>`, `/plumb approve <words>`
(a decision), `/plumb revoke <words>`, `/plumb confirm <the group's words>` and `/plumb
confirm the plan for <title>`, each against records not shown in the previous reply:
nothing written, `show_first` returned, the cards shown and recorded as the stated set;
then "ok" confirms (or revokes) exactly those hashes (relayed), and in a second case a
press does (`by: owner`); a record edited between the cards and the "ok" is left out and
named. The same commands naming the records by ID, or naming only records shown in full in
the previous reply, act at once. `tests/surface/test_owner_actions.py::
test_check_clean_after_typed_confirm`: after `/plumb confirm SR-...` under the session
marker, `plumb check` reports no error, and the glance lists the entry under "you typed".

## 8. Capture, round two (R16, R18 items 1 to 4; CAPTURE2)

### 8.1 The relay's objection scope (R16; SR-090)

Guarantee: objection and change detection is scoped to the sentences that name, or plainly
refer to, the records being approved; an unrelated request in the same message neither
blocks the approval nor counts as a reservation, and the quote need not include it.

Choke point: `approvals.owner_scope` and `approvals.change_clauses` read clauses through one
new filter, `approvals._in_scope(text, span, *, affirmation, targets, records)`, and the
reservation rule (concept 4.6 check 3: "from the sentence holding the affirmation on, any
clause beyond the vocabulary of assent is a reservation") reads clauses through the same
filter. Let A be the sentence holding the first affirmation and T the records being
approved: the records the ok answers. For an ok that names records by ID, T is those
records; for a bare ok ("ok", "yes, go ahead") or an ok scoped to a kind ("ok for the
examples"), T is what that ok answers: the stated set of the reply before the prompt (the
cards shown), the shown group offer, or the shown set offer, narrowed to the kind when the
ok names one. A change clause or a reservation counts only when it is in scope:

1. it lies inside A; or
2. it names a record of T by ID, or in plain words through a word distinctive of that record:
   a word of its naming stems that is not common across the record index (it appears in the
   naming stems of at most a quarter of the records, or of fewer than three) and is not the
   repository's or plumb's name; or
3. it refers back: it holds a general reference to records (`_refers_generally`, a kind
   word such as "the example", "the decision"), a pronoun among it, this, these, those,
   they, them, or "that" opening the clause or followed by is, 's, was, should, must.

There is no fallback that puts every clause of the message in scope: the same three rules
apply whether the ok names records by ID, is bare, or is scoped to a kind, and on every
entry point below. A clause out of scope is an unrelated request: it does not object, does
not reserve, does not make the quote cover it, and does not set `prompt_objects`. The
concept's rule "when none of the prompt's change clauses names a record ... it objects to
every one" now applies to the change clauses in scope only: an in-scope correction that
names no record (inside A, or referring back) still holds back every record of T ("ok,
except 3 minus 5 should return 0"; "ok. That should be 0 though."). Everything else of
concept 4.6 check 3 is unchanged.

So "Make plumb a plugin ... . Ok" and "Ok. Also add a dark mode to the settings page."
after cards confirm the stated set, while "ok, and also add a dark mode" (one sentence:
rule 1) still holds the ok back, as R16 scopes detection to the sentence of the ok; and
"ok. The reminder should go out a day earlier." holds back the reminder record when
"reminder" is distinctive of it (rule 2).

The R16 message ("Make plumb a plugin that you can install using claude code so that then
all commands are built in. Ok, confirm DEC-017 and DEC-018") confirms both decisions: the
affirmation names its records by ID, the first sentence is outside A, names neither decision
by ID, and its only words shared with them ("plumb") are not distinctive; it holds no
reference back. The same message ending in a bare "Ok." after the two decisions' cards
confirms both as well.

Entry points (one test each, `tests/capture2/test_relay_scope.py`, every case using real
copies of DEC-017 and DEC-018 for the R16 prompt): `plumb relay <IDs>`; `plumb relay
--group`; `plumb relay --set`; `plumb conflict relay` (and the early-conflict answer);
`owner_actions` `words` (7.2); the prompt hook's relay line (`prompt.py` calls
`owner_scope`); the approval's `prompt_objects` flag read by the merge-boundary glance. Each
entry point has two R16 cases: the ID-naming message above, and an unrelated request plus a
bare "ok" (before or after it, in its own sentence) after the cards, the group offer or the
set offer that entry point answers, which confirms exactly that stated set, group or set
(SR-090 EX-7). Each entry point also keeps a refusal case: an out-of-sentence correction
that refers back, or uses a distinctive word of a record of T, still holds the ok back
(SR-090 EX-3, EX-5, EX-8). The regression cases of SR-090's examples (unchanged behaviour)
run against every entry point that accepts them. The medium follow-up "restating the record's own content is assent" stays
in `docs/followups.md` unless these tests show it in the same choke point.

### 8.2 Assent provenance (R18.1; SR-091)

- **Bare assent.** `capture.assent.is_bare_assent(quote, records)`: after normalization the
  quote's residue beyond the vocabulary of assent is empty (`approvals._residue`), or it is
  an option label (a letter or a digit with optional `)`/`.`, "option B", or a decision's
  option label).
- **`in_reply_to`**, a new optional field on an INT and on an example: `{kind: dec |
  proposal, ref, digest, text}`. For `dec`, `ref` is the DEC and `text` its question; for
  `proposal`, `ref` names what the stop hook showed (a card or an offer: `<record>@<hash
  prefix>`, `offer:<id>`, `readback:<clarify session>`), `digest` the digest of the shown
  text, and `text` that proposal in plain words.
- **Recorded as shown.** The stop hook calls `capture.assent.record_shown(core, session,
  items)` for every card, question and offer it shows; it appends one `shown` log entry per
  turn that showed any (digests only, no text) and keeps the texts in session state.
- **Capture checks** (`capture.assent.check(core, quote, in_reply_to)`, called by `plumb
  capture`, `plumb intent`, `plumb example`): a bare-assent quote without `in_reply_to` is
  refused (exit 2, nothing written); a `proposal` digest that no `shown` entry holds, or a
  `dec` ref that does not exist, is refused.
- **Cards** show `you said "A" to: <text>` (SURFACE renders the field, `owner_text.
  YOU_SAID_TO`).
- **Automatic confirmation** (`capture/autoapprove.py`): a record whose supporting quote is a
  bare assent qualifies only when `in_reply_to.kind == "proposal"`, the shown item was a
  single proposal (not options), and the record restates that proposal (its content digest
  is the shown one); the owner's words judged for entailment are then the proposal's text
  plus the assent. `kind == "dec"` never qualifies: picking among options never makes the
  question citable.
- `plumb validate` checks every `in_reply_to` against the log (a missing `shown` entry is an
  error).

Tests: `tests/capture2/test_assent.py`, one per example of SR-091 and one per entry point
(`capture`, `intent`, `example`, the auto-approval gate, `validate`).

### 8.3 The read-back self-challenge and the abstraction rule (R18.2; SR-092)

- `plumb clarify` returns, as agent hints (`ClarifyView.challenges`), the request's
  unexamined absolutes (always, never, all, every, instantly, zero, any), unstated
  tradeoffs (two goals the backend judges in tension), unsupported claims ("users want",
  "it's faster") and contradictions with confirmed records. They are never written as
  records and never gate anything.
- `plumb-clarify`'s SKILL.md (CAPTURE2) adds a step before the read-back: challenge it; turn
  each challenge into a labelled assumption by default ("Assumed: 'instantly' means within a
  minute"); ask a question only when the answer changes what gets built (then it is a DEC
  that matters, one per message, R11). It states the owner-level rule (6.3) for the read-back
  and every question: the owner's goals, behaviours and words; an internal concept is
  explained in one plain sentence before it is used.
- The stop hook never shows challenge hints to the owner.

Tests: `tests/capture2/test_challenge.py` (the clarify hints for each kind; no record
written; the stop hook shows none), `tests/capture/test_skills.py` extended (the skill text
names the step and the rule), and the e2e clarify scenario (12, item 2).

### 8.4 `done_when` (R18.3; SR-093)

- INT gains `done_when: [{id: DW-n, text}]` (capture accepts plain strings and numbers
  them); it is part of the record's meaning and hash. Examples gain an optional
  `done_when: [DW-n]` naming the items they cover.
- `plumb clarify` returns `ClarifyView.uncovered`: scope (no `will`), non-goals (no `wont`),
  success (no `done_when`), failure modes (no example whose `then` is an error or a refusal),
  as hints to the agent only; no owner question is raised for them.
- `plumb align` reports each `done_when` item no example covers as a gap
  (`owner_text.DONE_WHEN_GAP`: "done when 'you get a reminder three days before each
  deadline': no example shows it yet").
- Cards show "Done when: ..." (SURFACE renders the field).

Tests: `tests/capture2/test_done_when.py` (capture, hash, align gap and its clearing, the
hints, no owner question in the stop output).

### 8.5 The structure check and agent self-repair (R18.4; SR-094)

- INT `will` items are numbered `W-n` (as `done_when` items are); a requirement may list the
  will items it serves in `serves: [W-n]`.
- `plumb spec check INT-### [--json]` = `capture.spec.structure(core, anchor) ->
  StructureReport` (deterministic, except the won't judgment):
  - structural gaps (the agent fixes them): a member without `derives_from` the anchor; a
    `will` item no member serves; a requirement without an example; a `done_when` item no
    example covers; a member outside the anchor's `members` list or the reverse;
  - intent gaps (the owner decides): a member the judgment backend judges to contradict a
    `wont` item (JEV, else the heuristic; an unsure verdict is an intent gap, never a pass);
    an open decision that matters on a member.
- `capture.spec.offerable(core, anchor) -> bool`: no structural gap and no unanswered intent
  gap. It is the one gate for every offer: the stop hook's set offer line, `plumb confirm`
  of a set, the mod's set offer (5.7), `owner_actions.perform("set")` on every via, and
  `relay --set` (refused naming the gaps, for the agent).
- `capture.spec.repair_note(core, anchor) -> str | None`: the agent-facing instruction the
  stop hook puts in its block when a set is not clean ("the plan for <title> has 2 gaps you
  can fix: ...; run plumb spec check INT-### after fixing"). It is model-facing only; the
  owner sees at most "preparing the plan".
- `plumb-clarify` (escalated depth) and the `plumb` skill: after writing an escalated set,
  run the check, fix every structural gap (add examples and links, map `serves`, split or
  merge records), run it again until clean; ask the owner only the intent gaps, one per
  message, as decisions that matter.

Tests: `tests/capture2/test_structure.py` (each gap kind; the repair loop with a scripted
agent: gaps, fixes, clean, offer appears; an intent gap raises exactly one question; every
offer entry point refuses or hides an unclean set; the owner's views never contain a
structural gap).

### 8.6 Records in an intent conflict are not stale links (SP6 leftover; SR-095)

Guarantee: a record a merge left in an intent conflict is reported once, under its conflict,
never as stale links.

Choke point: `mergedriver.holds.held_by_conflict(core) -> Mapping[str, str]` (record to
conflict), and `holds.split(states, held) -> (stale, held_links)`. Phase 0 wires it into every
place that lists stale links: the merge report's links gate (`boundary/gates.py`), `plumb
validate` and `plumb drift`, the status snapshot's drift count, the stop hook's drift lines,
`plumb review`, and the Obsidian view's badges. When the owner's choice is recorded (`conflict
choose`, `conflict relay`, the conflict button), `mergedriver.conflicts` repins that record's
links with the note "after the owner's choice" (a repin never confirms; the choice itself is
the owner's confirmation).

Tests: `tests/capture2/test_conflict_holds.py`, one per entry point (merge-check exits 4 with
the card and no stale link for the record; validate; drift; status; the stop summary;
review; view), and the repin after each of the three ways to choose.

### 8.7 SP6 text leftovers

The merge report, pre-push, pre-merge-commit and post-merge texts are rewritten in SURFACE
(6.3): no shell command, no `--no-verify` hint, titles instead of IDs and paths.

## 9. Interfaces

```python
# plumb.launcher (PLUGIN)
def git_hook_line(hook: str) -> str: ...            # one line calling the user-level launcher
def driver_command() -> str: ...
def plumb_home() -> Path: ...

# plumb.guard (PLUGIN; the one table of denied forms)
def denied(tool: str, tool_input: Mapping[str, Any]) -> str | None: ...
DENIED: tuple[DeniedForm, ...]

# plumb.plugin (PLUGIN)
def migrate(root: Path, *, dry_run: bool) -> MigrationResult: ...
def ignore(root: Path, *, undo: bool) -> None: ...
def legacy_install(root: Path) -> bool: ...

# plumb.mod (MOD)
def hello(paths, session: str, key_digest: str) -> ModHello: ...       # first wins, else Refused
def snapshot(core, session: str) -> ModSnapshot: ...
def pane(core, session: str, focus: str | None, details: bool) -> PaneTree: ...
def press(core, session: str, offer_id: str, key: str) -> OwnerActionResult: ...
def typed(core, session: str, key: str, text: str) -> None: ...        # logs a typed /plumb command
# plumb.mod.handshake (MOD; stubs in phase 0)
def active(paths, session: str, turn_start: str | None = None) -> bool: ...
def deliver(core, session: str, output: HookOutput) -> HookOutput: ...
def background_owned(paths, session: str) -> bool: ...

# plumb.owner_actions (SURFACE)
def perform(core, action: str, targets: Sequence[Target], *, via: str,
            proof: Mapping[str, Any]) -> OwnerActionResult: ...
def parse_command(text: str) -> tuple[str, list[str]] | None: ...

# plumb.present.owner_text (SURFACE; SP6 names kept)
def shell_commands(text: str) -> list[str]: ...
def jargon(text: str, *, details: bool = False) -> list[str]: ...
def record_gaps(kind: str, fields: Mapping[str, Any], previous: Mapping[str, Any] | None
                ) -> list[Gap]: ...                  # called by store.write_record (6.5)
CONCEPTS: Mapping[str, str]
def explain(term: str) -> str: ...

ADOPT_HINT, GETTING_READY, NEEDS_PYTHON, LEGACY_INSTALL, NOT_SET_UP_HERE, PANEL_OFF,
YOU_SAID_TO, DONE_WHEN, DONE_WHEN_GAP, PREPARING_PLAN, CHANGED_SINCE_SHOWN,
BUTTON_CONFIRM, BUTTON_SHOW_ALL, BUTTON_HIDE, BUTTON_SHOW, BUTTON_OPEN, BUTTON_OBSIDIAN,
BUTTON_REVOKE, BUTTON_UNDO, BUTTON_TURN_ON, BUTTON_TURN_OFF, BUTTON_WAIVE, BUTTON_KEEP: str

# plumb.present.answers (SURFACE; phase 0: FORMS complete, render returns None)
FORMS: Mapping[str, str]          # CLI form of 6.1 -> "owner" | "agent" | "none" (6.6)
def render(form: str, payload: Any, *, details: bool = False) -> str | None: ...

# plumb.cliutil (coordinator, phase 0; add_common gains --agent and --details)
def answer(args, form: str, payload: Any, agent_text: Callable[[], Sequence[str]]) -> None: ...

# plumb.capture.assent, plumb.capture.spec, plumb.mergedriver.holds (CAPTURE2)
def is_bare_assent(quote: str, records: Mapping[str, Any] | None = None) -> bool: ...
def record_shown(core, session: str, items: Sequence[ShownItem]) -> None: ...
def check(core, quote: str, in_reply_to: Mapping[str, Any] | None) -> None: ...
def structure(core, anchor: str) -> StructureReport: ...
def offerable(core, anchor: str) -> bool: ...
def repair_note(core, anchor: str) -> str | None: ...
def held_by_conflict(core) -> Mapping[str, str]: ...
def split(states, held) -> tuple[list[LinkState], list[LinkState]]: ...
```

New frozen data classes in `contracts.py` (defaults on every field): `ModHello`
(`background`, `background_hash`, `snapshot`), `ModSnapshot` (`state`, `card_line`,
`summary`, `summary_line`, `matters`, `cards`, `toasts`, `awaiting`, `background_hash`),
`ModCard` (`key`, `kind`, `title`, `lines`, `offer`, `buttons`), `ModOffer` (`offer_id`,
`action`, `targets`), `ModButton` (`action`, `label`, `take`), `ModToast` (`id`, `text`),
`PaneTree`, `PaneNode`, `OwnerActionResult` (`done`, `left_out`, `owner_line`,
`agent_line`, `show_first`: the resolved candidates when nothing was done because the owner
has not seen them, 7.2), `StructureReport` (`clean`, `structural`, `intent`), `Gap` (`kind`, `record`,
`item`, `owner_line`, `agent_line`), `InReplyTo` (`kind`, `ref`, `digest`, `text`),
`ShownItem` (`ref`, `kind`, `digest`, `text`, `single`), `MigrationResult` (`removed`,
`kept`, `repointed`). `ClarifyView` gains `challenges`, `uncovered`. Every record kind
gains the optional `agent_notes` field, outside the record hash like `links`
(`model.record_hash`), and `store.write_record` gains `text_check: "refuse" | "report"`
(default `refuse`; 6.5), raising `RecordTextGaps` (exit 2) in `refuse` mode. Approval and
event entries gain `via` (`terminal`, `words`, `command`, `button`) and `resolved_from`. Config gains `mod`
(`enabled: true`, `summary_line: true`, `toasts: true`), `plugin` (`hint: true`) and keeps
`present.card`.

Routes: `owner` -> `plumb.owner_cli` (SURFACE), `mod` -> `plumb.mod.cli` (MOD), `plugin` ->
`plumb.plugin.cli` (PLUGIN); `hook pre-tool` (PLUGIN); `spec check` (CAPTURE2).

## 10. Latency and cost

| Path | Budget | How |
|---|---|---|
| Any hook in a repository not adopted | under 100 ms, no Python | `plumb-hook` walk-up in `sh` (4.3) |
| `pre-tool` for a command not about plumb | under 50 ms, no Python | the `sh` grep (4.3); the mod's `tool.call` is in-process |
| `mod.json` check in the session-start and stop hooks | one small file read | 5.1 |
| Mod per turn | one `plumb mod snapshot` after `turn.complete`, off the prompt path, about 0.3 s warm | 5.2 |
| `prompt.compose` | no process; `$.state` only | 5.6 |
| Summary line | one `$.fs` read | 5.4 |
| Button press | one process, about 0.3 s | 5.7 |
| First bootstrap | seconds to a minute, once per plugin version, in the background | 4.2 |
| Structure check | deterministic part under 200 ms for 30 records; the won't judgment once per member and won't item, cached by hash | 8.5 |

Hook budgets of `config.yaml` are unchanged. No hook runs the full suite; the full suite runs
once at push (R17).

## 11. What is not done in SP7

- Per-step cheaper-model routing (`turn.step` model or effort rewrites), subagent model
  choice (`agent.offer`, spawn), `$.model.complete` as the LLM cascade tier, JEV-driven
  routing: an SP8 exploration that measures cost, prompt-cache impact and quality first
  (R19).
- Mods for other hosts; any change to the host-neutral core's contract.
- Publishing the marketplace anywhere but the plumb repository; installing the plugin into
  the owner's Claude Code without the owner's go-ahead (it changes the owner's user
  settings; the owner types the two `/plugin` commands, or says "install the plumb plugin
  for me").
- Moving plumb's own repository off its per-repository install (4.7).
- Challenge records, challenge gates, or owner questions about structural gaps.

## 12. Definition of done

1. Every SR of FEAT-007 has tests marked with its SR, at least one per example, and the
   entry-point tests of 4.8, 5.10, 6.3, 6.5, 6.6, 7.2, 8.1 to 8.6.
2. **Owner e2e** (`tests/owner/test_owner_flows_e2e.py`, Integrate): a temporary repository
   and a bare remote; the hooks run through `plugin/bin/plumb-hook` exactly as the plugin's
   `hooks.json` names them; a scripted agent runs only the CLI forms the generated
   `plugin/commands/plumb.md` names for each route (the test parses the routes and fails on a
   CLI call no route names); a simulated mod (`hello`, `snapshot`, `press`, `typed`) presses
   buttons with its key. The owner's inputs are ONLY slash commands, prompts and button
   presses (asserted: each input is a `/plumb` or `/plugin` command, prose with
   `shell_commands(input) == []`, or a press). It covers every owner-facing row of 6.1: adopt
   with `/plumb init` (and the hint before it), status, status for another repository,
   "what are we building?", explain, show, review, impact, align (with a `done_when` gap),
   drift (each kind of 6.6), "does X do what I meant?", `/plumb help`, "the record numbers
   look off", view (written, not opened; every note scanned), the
   pane tree, confirm by words (nothing confirmed until the cards were shown) then "ok",
   confirm by **Confirm**, `plumb check` clean after a typed `/plumb confirm`, `/plumb approve DEC-...`, a decision answered
   "A" (assent provenance), revoke by slash and "ok" and by button, triage and the group by
   "ok" and by button, an escalated plan (the agent repairs a structural gap, then the offer
   appears, then **Confirm the plan**; an intent gap asks one question), auto-confirm on
   (refused in plain words without a calibration, then accepted with a fake calibrated JEV)
   and off, settings, card compact and off, jev setup, status and calibrate (fake backend),
   merge-check, a merge held by an unconfirmed requirement and "finish the merge", an intent
   conflict chosen in words and by button (its links not reported stale, 8.6), an early
   conflict answered, merge-fix after a clone collision, import (fixture), "move plumb to
   the plugin" on an old install, migrate the logs, waive the full run, the R16 message
   (by IDs, and an unrelated request beside a bare "ok" after cards), a push whose pre-push
   report is read. Every owner-visible output captured (system messages, `present.json`,
   the mod's command rows, snapshots and pane trees, every generated vault note and Canvas
   label, the owner-facing fields of every record the scripted agent wrote, the merge,
   commit, merge-hook and pre-push outputs from real git, and the stdout of every CLI call
   the scripted agent makes on an `owner` form of 6.6: the default text with
   `details=False`, a `--details` call only after the owner asked for detail, with
   `details=True`) passes `shell_commands` and `jargon`. The harness fails when the scripted
   agent shows the owner the output of an `agent` form or an `--agent` text, or calls a
   form `FORMS` does not classify.
3. **Jargon scan**: the e2e above, the per-surface tests of 6.3 (the vault included),
   the route answers of 6.6 (one case per `owner` form), the record-content check of 6.5
   on every write entry point, `jargon.test.tsx`, and
   `tests/surface/test_docs_text.py` on the README and owner docs. `record_gaps` finds
   nothing in FEAT-007, INT-023, SR-082 to SR-095 and DEC-023 to DEC-025 before they are
   offered to the owner.
4. **Plugin**: `claude plugin validate plugin` and `claude plugin validate .` pass;
   `claude plugin test plugin` passes; the bundle is fresh; `tsc -p plugin` passes where
   TypeScript is available; a live smoke, `claude -p --plugin-dir plugin "/plumb status"` in
   an adopted temporary repository (the mod answers without the model), prints the card with
   no shell command and no jargon (run once at Integrate when `claude` is signed in; skipped
   otherwise and noted).
5. R16 regression: exactly the owner's message confirms DEC-017 and DEC-018, and an
   unrelated request beside a bare "ok" confirms the shown set, through every entry point
   of 8.1.
6. No owner-only write without the owner: every new owner-only path has its refusal test
   (agent shell, no logged prompt, self-recorded message, wrong key) with exit 3 and nothing
   written.
7. Hook latency tests still pass, plus the not-adopted and `pre-tool` budgets of 10.
8. `docs/concept.md` (sections 4.2, 4.6, 5, 6, 9, 11), the README, `docs/hosts.md` and
   `docs/owner-matrix.md` describe the shipped behaviour; medium and low findings are in
   `docs/followups.md`.
