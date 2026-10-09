# Hermes compatibility: reconciliation and implementation handoff

Status: proposed implementation corrections; documentation-only reconnaissance, not Release A acceptance or owner approval.

## Intent and authority

The owner requested an assessment of the Claude integration and a Hermes-compatible implementation with honest evidence of supported surfaces. This card makes the bounded hardening plan implementable. It does not implement the adapter, enable a real profile, or close the full intent. Release A improves the existing project-bound bridge; Release B still covers native skills, authenticated origin, multi-project routing and optional integrations. Unsupported surfaces must remain labelled as fallback, not quietly counted as parity.

Task: `t_bc2169f1`, board run 1, profile `default`. Actual worker session environment identifies `20261009_121832_92237e`, source `kanban`. Session context identifies model `gpt-6.1-sol`, provider `openai-codex`; these agree with the card overrides. This is session/card evidence, not a provider billing receipt. No additional workers or cards were spawned. There are no parent cards. Downstream implementation card is `t_d1caf576`; its existing acceptance child is `t_e4130cae`. This card completes the reconciliation phase only.

Starting HEAD: `31765fcfe9371c2a7e36f100453f4f24f27f95e6`, branch `feat/hermes-compat`, clean worktree. Baseline is provenance, never reset permission. Only this report and the byte-preserved plan are authorized tracked changes here; no canonical SR is created by this documentation-only card. The implementation worker owns recording a proposed implementation SR using the native producer and actual example/test links. Do not attribute that proposal to the owner or approve it.

Source plan: `C:/coding/plumb/.hermes/plans/2026-10-09_120026-plumb-hermes-spec-and-plan.md`.
Durable worktree copy: `.hermes/plans/2026-10-09_120026-plumb-hermes-spec-and-plan.md`.
Both byte streams: 36,399 bytes, SHA-256 `a27fad812d3c0be2be204d8c5fade579f21118417e1b78424517142804a43e36` (copy equality checked).
Assessment provenance: `C:/coding/plumb/.plumb/requirements/SR-099.md`, read without edits. It assesses compatibility, explicitly not installation authorization; the Kanban execution request supplies the subsequent implementation authorization. SR-099 is not present as a new canonical requirement here.

Read `CLAUDE.md`, `pyproject.toml`, `docs/hosts.md`, `docs/specs/sp4-hosts-mcp.md`, shared/installer/template/neutral/CLI APIs, approvals guard, Hermes/conformance fixtures, and relevant Hermes runtime call sites. No credentials, `.env` contents, real profile configuration, or private user transcripts were inspected.

## Verdict

Implement Release A with the corrections below; do not execute the original snippets verbatim. No high-level product decision blocks this bounded phase. Reversible implementation choices are settled here. Preserve approval semantics, shared latency logic, other adapters, and the existing subprocess boundary. No engine relocation, new ownership database, global plugin, or speculative lifecycle refactor.

The strongest new discrepancy is context loader drift: the installed runtime recognizes `AGENTS.override.md` and does not implement a universal 'first nonempty file across six names' rule for Hermes-named files. There is also a real child-start ordering gap: the session-start producer omits parent metadata, so filtering only that observer's kwargs does not exclude child startup events.

## Severity-ranked necessary corrections

### High H1 — choose the file the runtime actually loads

Plan A2/Task 1's six-name loop can place the block in an invisible file. Installed `agent/prompt_builder.py:104-125` selects the first existing regular `.hermes.md` or `HERMES.md`; `_load_hermes_md` at 2233-2256 returns empty on empty/unreadable content and then the loader falls through to AGENTS, not to the second Hermes filename. At 2286-2329, AGENTS uses `AGENTS.override.md`, `AGENTS.md`, `agents.md`, first readable nonempty per directory. CLAUDE uses readable nonempty uppercase/lowercase at 2344-2360. `build_context_files_prompt` at 2400 onward chooses the first successful context type.

Settled root-local algorithm for Hermes only:

1. Check `.hermes.md`, then `HERMES.md`, for the first regular file, matching the runtime's Hermes-name selection. If that selected file is readable and nonempty, use it. If empty/unreadable, move to the AGENTS type; do not select the second Hermes name merely because it has content. Do not overwrite the empty/unreadable Hermes file.
2. Choose first readable nonempty `AGENTS.override.md`, `AGENTS.md`, `agents.md`.
3. Otherwise choose first readable nonempty `CLAUDE.md`, `claude.md`.
4. Otherwise create/use `AGENTS.md` as the bounded CLI fallback.

Add cases: empty `.hermes.md` + nonempty `HERMES.md` + CLAUDE -> CLAUDE; nonempty override + AGENTS + CLAUDE -> override only; unreadable selected Hermes file -> fallback type; both Hermes names nonempty -> `.hermes.md`. Read errors may be skipped for selection, but existing safe-write helpers must still refuse unsafe overwrites of an unreadable destination. No imports of Hermes internals into production.

This intentionally revises A2's proposed ordering based on source, not an owner contract. Keep Codex/Pi `context_file` results unchanged. Root-only install is explicit; ancestor, progressive subdirectory, YAML-frontmatter and scanner behavior are not replicated. Unknown context sources such as Cursor rules are not promised preserved by this release; document that boundary rather than claiming universal instruction preservation.

### High H2 — child exclusion must happen before obtaining a brief

`agent/conversation_loop.py:1107-1117` emits `on_session_start` with session/model/platform only, no `parent_session_id`. `agent/turn_context.py:1393-1405` emits parent metadata at pre-LLM time. The current plugin starts a subprocess at the earlier observer, even for a child whose ancestry is only learned later. Plan A6's literal `_started` addition does not fix that.

Settled correction: the session-start observer may note a pending startup for a session, but must defer Plumb's actual session-start subprocess and brief retrieval to its first eligible pre-LLM callback, after `_owner_session` filters parent metadata. Do not call the observer recursively if it only notes startup; use a small internal once-only initializer. Mark the session initialized before dispatch so a failure does not cause repeated starts. Retain the existing in-process lifetime; no new cleanup subsystem.

Required tests: explicit observer + parentless prompt => exactly one session-start and one prompt; repeated observer/prompt => no duplicate brief; no observer + prompt => same first-turn initialization; observer without parent followed by a child pre-LLM payload => zero subprocess events across all subsequent child callbacks. Later transform/edit/post callbacks rely on the learned child set, as they lack parent metadata. This does not certify parentless scheduled or other synthetic turns.

### High H3 — root index is correct, but the sentinel alone is not an install-layout guard

`parents[3]` is correct for `<repo>/.hermes/plugins/plumb/plugin.py`: indexes 0=plumb, 1=plugins, 2=.hermes, 3=repo (verified with pathlib). Do not change it to 4. The plan's guard only checks `.plumb`; a loose plugin under `<repo>/loose/plugins/plumb/plugin.py` also resolves to `<repo>` and would dispatch if `<repo>/.plumb` exists. A shallow path can also raise IndexError during import.

Settled correction: compute/validate the resolved installed path defensively, checking the exact `.hermes/plugins/plumb/plugin.py` layout plus a root-local `.plumb` directory. Invalid/shallow/loose layouts must still import and register for Doctor, but every `_run`, including background events, returns a fresh empty output without spawning. Keep root computation in the template, not shared core; no `shell=True`. Resolve failures must fail inert rather than break plugin import.

Required regressions include loose layout under a real adopted root, shallow invalid file, missing `.plumb`, and repo-A plugin with cwd in repo B. Assert both subprocess cwd and serialized payload cwd for every dispatch. This binds a plugin to one project; it does not establish session routing, sandbox containment, or a global-plugin security guarantee.

### High H4 — retain unknown/shared ownership, including new override targets

Task 2's Claude preservation is sound; apply it to uppercase/lowercase aliases. Runtime drift adds an override target that other agents may read but `remove_shared_block` cannot prove is owned. Conservatively preserve a marked `AGENTS.override.md` block too, with an ownership-unknown explanation; do not introduce ownership metadata. Keep existing AGENTS/Pi-sharing behavior unchanged.

Uninstall must not chase historical context targets or remove every marked block: if an owner creates a higher-priority context file after installation, leave old blocks rather than guessing their ownership. Status reports the current selected context only, not complete historical inventory. Add dry-run/uninstall preservation coverage and document that useful fallback text may remain. Existing shared helper uses selected paths, not an ownership ledger (`common.py:351-360`).

### Medium M1 — Windows lowercase tests must actually create lowercase files

On this Windows volume, `CLAUDE.md` and `claude.md` are the same file (`samefile` verified). A naive assertion that uppercase does not exist will fail even for correct lowercase preservation, and writing both aliases cannot exercise precedence.

Create one requested spelling at a time and check directory-entry spelling or bytes, not absence of its uppercase alias. Parameterize individual lowercase CLAUDE/AGENTS cases; avoid an uppercase/lowercase duplicate-files fixture on case-insensitive filesystems. A dual-name precedence fixture belongs only on a demonstrably case-sensitive volume. Lowercase selection on Windows may return the canonical uppercase Path alias; preservation must be physical-file/byte correct, not dependent on the returned Path spelling. Do not skip the basic lowercase cases on Windows.

### Medium M2 — unknown activation is not verified absence of a marker or hooks

Task 3 correctly removes `active = installed and enabled`. Keep file ownership/presence, discovery flag, enablement instructions and restart guidance distinct. Do not parse the complete real Hermes config or assert hooks run from these prerequisites.

However `marker_lines(False, ...)` literally says 'no session marker on this host'; runtime is unknown, not necessarily absent. Retain required compatibility wording only under an explicit 'CLI fallback (runtime marker unverified):' label. Likewise prefix fallback prompt guidance so it does not deny that an independently running process may have hook-origin entries. Preserve TRUST_LINE and self-recorded confirmation counts. Tests must assert no positive runtime marker/prompt claim for either discovery flag value, missing files and foreign/partial files; status must clearly say runtime activation unverified.

Document `hermes plugins enable plumb` as an owner-run profile enablement step, not a project trust side effect of installation. Plugin discovery and profile allowlisting are independent. Do not run enablement here.

### Medium M3 — lazy initialization necessarily changes existing fake event expectations

Moving `_fake_plugin` under `project / hermes.PLUGIN_DIR` is correct. It must still isolate Python module names and command log files; avoid helper reuse that overwrites one module's state unexpectedly. Existing direct first-prompt tests currently have no session-start event. They will now acquire one.

Update expected event sequences narrowly: child tests remain zero calls; first parent prompt gains exactly one session-start, later prompts do not. Preserve summary settlement suffix assertions, exact prompt words, attempt 0/1 behavior and real subprocess `via: hook` checks. Explicit observer tests should still have one start overall, although dispatch now occurs at the eligible prompt. Add a delayed observer after initialization and an interrupted reply test. Do not relax prompt text or guard assertions to make this green.

### Medium M4 — support wording must separate event provenance from human authentication

`neutral.py:43-46` defines `via: hook` from the host identity, not trusted human evidence. Hermes pre-LLM kwargs include `sender_id`, but its mere presence is not a human-authentication contract. `cron/scheduler.py:6427-6465` constructs an agent with `platform='cron'` and no parent-session argument. Parent absence demonstrably cannot certify human origin. Never label all cron/background messages skipped.

A project plugin remains callable by synthetic turns in that runtime process. A's supported claim is an event bridge for explicitly controlled project CLI usage, not automatic authenticated owner capture across all host modes. Real enablement must wait for the origin/routing acceptance gate, particularly on shared desktop/gateway/cron processes. Keep this risk visible in install/docs; do not change approval policy or invent origin kwargs in A.

`transform_llm_output` is first nonempty string wins (`turn_finalizer.py:607-626`). `post_llm_call` receives the returned `assistant_response` only for nonempty, noninterrupted responses at 630-649. `_settle` can infer summary presence in that returned string, not delivery/read receipts. `/plumb` uses `inject_message` correctly for CLI queuing; gateway requires a session key and explicit grant (`plugins.py:2046-2114`), absent in this callback. Existing FakeCtx success does not establish desktop command parity.

## Concrete acceptance additions for the proposed implementation SR

Record these through `plumb new requirement`, `plumb example`, and `plumb link` during implementation, as proposed only; relate to existing SR-056 and assessment SR-099 where source provenance is available without inventing a local canonical record. Link actual changed files/tests, not future guessed paths.

| Given | When | Then |
|---|---|---|
| Empty first Hermes filename, nonempty second and Claude | Install | Follow runtime fallback type; second Hermes file remains untouched |
| Nonempty AGENTS override and normal AGENTS | Install | Only the override receives the block |
| One lowercase context filename on Windows | Install/uninstall | No new physical shadow file; bytes preserved subject to owned block semantics |
| Session-start observer lacks ancestry, later prompt has a parent | Call hooks | No Plumb events for that child, including startup |
| Plugin loose under an adopted root, or at a shallow path | Import/register and call events | Registration works; no subprocess dispatch |
| Installed files and discovery flag both present | Status | Runtime remains unverified; marker/prompt fallback descriptions do not assert live absence/presence |
| Unknown Claude or override block ownership | Uninstall/dry-run | Keep bytes and report conservative preservation |
| First eligible prompt with/without observer; repeated/delayed observer | Initialize | One brief total, exact prompt retained, no duplicate startup |

## Full-intent coverage matrix

| Requested capability | Release A disposition / evidence | Release B or remaining gate |
|---|---|---|
| Assess Claude translation honestly | Existing engine reused via neutral TurnEvent/TurnOutput; Claude-named handlers remain. SR-099 preserved; no reuse percentage. | Full surface comparison must retain unsupported rows, not an all-host label. |
| Project installation, fallback, owner text | Harden selector, dry-run, idempotence, foreign files and uninstall preservation with above corrections. | Ancestor/nested sources and external symlink guarantees are not added. |
| Activation and registration | Status unverified; temporary Doctor registration available. | Explicit authorized real-process callback proof; installation is not activation. |
| Brief/delta and exact string prompts | Deferred once-only brief, fake sequencing, real Plumb subprocess and conformance tests. | Human origin, multimedia/non-string input semantics, resumed process/session lifecycle need surface evidence. |
| Edits and continuation | Existing write_file/patch observation and attempt handling retained. | Multi-file patch protection and arbitrary terminal enforcement are separate defense-in-depth/threat-model work. |
| Summaries / unseen state | Returned-text composition, conservative unseen settlement. | Transport/read receipts and compositional transform guarantees not offered. |
| Owner commands | Existing CLI queue or textual fallback; namespace `/plumb` remains. | Desktop/gateway routing key and injection grants must be proved. |
| Delegated/background/cron exclusion | Explicit parent filtering, deferred startup prevents early child event. | Parentless cron is not authenticated; map every synthetic producer before enabling owner logging there. |
| Session/project isolation | Fixed validated project-root cwd. | Two simultaneous desktop projects and supported session-to-workspace association; no global recommendation. |
| Native plumb/plumb-clarify skills | Not installed by A. | Supported plugin `skills/<name>/SKILL.md` + `ctx.register_skill` now identified; namespaced read-only loads, not automatic available-skills indexing. Canonical-content reuse and full lifecycle still need tests/design. |
| Read-only MCP | Existing independent server; no installer changes. | Consent-preserving registration using supported Hermes config mechanisms; no A dependency. |
| Approval guard | Existing marker/TTY defense retained and tested, no altered authority. | PTY/marker removal/arbitrary code make this non-tamper-proof; any out-of-band security contract change needs owner decision. |
| Native status/desktop UX | CLI status and final-text baseline only. | Native desktop UI is a separate surface; no status-bar promise. |
| Regression/latency assurance | Fresh focused pass and partial broad evidence below. | Broad completion and full final candidate run remain acceptance work; no green full-suite claim. |

Official docs and installed runtime agree on plugin skill registration. `PluginContext.register_skill` at 3597-3659 provides namespaced read-only skills without inserting them into the flat system-prompt index. This resolves the discovery API question but does not authorize global installation or implementation of B in the A worker. Preserve canonical Claude skill behavior and plan lifecycle separately.

## Fresh verification and limitations

All Plumb commands ran with `PYTHONPATH=C:/coding/plumb-wt/hermes-compat/src`; the first interpreter probe printed `C:\coding\plumb-wt\hermes-compat\src\plumb\__init__.py`. Subprocesses inherit that variable. Validation interpreter: `C:/coding/plumb/.venv/Scripts/python.exe`, Python 3.12.12. OS probe: Windows-10-10.0.19045-SP0. The interpreter path is shared tooling only; source imports are from this worktree.

Executed:

- Focused `pytest tests/hosts/test_hermes.py tests/hosts/test_conformance.py -q`: exit 0, all 14 tests passed (12 Hermes, 2 conformance; collection confirmed). A later focused recheck also passed.
- `hermes plugins doctor src/plumb/hosts/hermes/templates --ci`: exit 0; discovery, manifest, import and registration passed; 0 tools, 6 hooks. Doctor temporary-home/socket safeguards were read in `hermes_cli/plugin_dev.py:36-77`; this is registration-only, not a sandbox or live callback test.
- `pytest tests/host/test_latency.py::test_intent_lines_survive_cpu_contention -q -ra`: exit 0, one test passed in isolation. This does not disprove earlier contention failures.
- Broad `pytest tests/hosts tests/host tests/mcp/test_mcp_install.py tests/mcp/test_server.py -q -ra`: terminal timeout, exit 124 at 240 seconds; partial progress contained one `F`, but no failure traceback or final summary was returned. Its identity is not established by that output. Do not call this a confirmed latency failure or a successful broad run.
- One bounded diagnostic `pytest tests/hosts tests/host -q -x --tb=short -ra`: exit 124 at 120 seconds, partial progress only, no final traceback. Stopped broader execution after that; no full suite was run and no assertion/budget was changed.
- Broad collection-only command: exit 0, enumerated test modules; not execution evidence.
- Path parent enumeration, Windows alias samefile check, and source/copy SHA-256 equality: all succeeded.

Terminal policy rejected Python `-c` and execute_code before execution in headless mode. Interpreter probes and the byte copy used ordinary Python stdin via shell printf; no policy/config was changed. Native Plumb producer help for `new`, `example`, `link` was successfully read. No proposed record was written on this read-only-code/documentation-only phase.

Runtime identification is intentionally precise: `hermes --version` printed `Hermes Agent v0.21.0 (2026.8.31) · upstream 6005aa1f`, install method git, host Python 3.11.16. Actual local runtime checkout HEAD is `b20cc5f787ea816ea8645603b7b2ac8234dcb8b4`. The banner upstream token is not the checkout SHA. Source conclusions are pinned to the actual checkout, not claimed valid for every release.

Authoritative online references retrieved during this run:

- https://hermes-agent.nousresearch.com/docs/llms.txt
- https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins

The skill's context reference still described AGENTS as cwd-only; official docs and installed source show the merged git-root-to-cwd chain. Use those authoritative/current observations in product docs. This card does not modify the user's installed skills or runtime.

## Read-only overlap inspection

`git worktree list`, status and committed deltas inspected without changing other trees:

- `C:/coding/plumb` main at baseline: untracked source plan, SR-099, judgment artifacts and IDEA.md; untouched.
- `C:/coding/plumb-jevor` at `e2f79eb4fc218c62bce4fd7459541182fcd2590a`: local .plumb config/log edits. Separate JEV lane; no direct A production path overlap observed.
- `C:/coding/plumb-wt/sp7-contracts` at baseline: many uncommitted changes including approvals, contracts, and Claude session_start/stop plus new owner/plugin/mod surfaces. None of the three A production paths or Hermes test path was listed modified. Semantic overlap exists because neutral delegates to those handlers. A must not absorb or certify those uncommitted changes; rerun integration review if they later land. In particular the sibling session_start introduces mod-owned brief suppression, so downstream integrations need separate coordination rather than copying it here.
- `C:/coding/plumb-wt/sp7-spec-review` at `4c70bc4f08924fffe836e520d1ac674eca5bfc2b`: clean; no committed divergent file changes relative to the common baseline in the inspected merge-base delta.

No direct changed-file collision hotspot is claimed; this report flags the semantic handler overlap for later landing review. Do not change branch/HEAD, clean, stash or commit another lane's files.

## Downstream execution boundary

Follow card `t_d1caf576` and this report before the preserved plan when they differ. Implement only its exact allowlist, TDD regressions and explicit scoped commits. Use this existing worktree/branch; ignore the older plan's instruction to create another implementation worktree and its subagent-spawning preamble. Do not spawn children, rewrite SR-099, enable profile plugins, change Hermes source/config, merge or push. Worker model calls are allowed by the card; paid/live acceptance is not.

Complete implementation-only with exact SHA/path/test evidence and release the pre-created independent acceptance lane. Do not additionally request same-card review. Only a high-level contract/security/authorization conflict warrants human interruption; the reversible corrections above are settled. Release A cannot close the original full intent by itself. Preserve B gates and unsupported-surface labels in the final acceptance handoff.
