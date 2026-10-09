# Hermes compatibility runtime evidence

Status: bounded Release B investigation. Release A remains accepted only as a project-local, offline-tested adapter; this report does not certify live activation, owner authentication, desktop parity, or full intent closure.

## Scope and safety

This investigation read the installed Hermes source and current official documentation, ran registration/offline checks, and used synthetic payload fixtures. It did not enable a real profile, edit Hermes configuration, call a model, connect to MCP, read credentials or `.env`, or change the installed Hermes checkout.

Runtime under test:

- `hermes --version`: `Hermes Agent v0.21.0 (2026.8.31) · upstream 6005aa1f`
- Installed source checkout: `b20cc5f787ea816ea8645603b7b2ac8234dcb8b4`
- Plugin Doctor: exit 0; discovery/import/registration passed; 0 tools and 6 hooks
- Official references consulted: plugin guide, context-files guide, MCP guide, event-hooks guide, agent-loop guide, and desktop-plugin-SDK guide

The source checkout had a pre-existing unrelated modified file. It was not read or changed.

## Runtime hook contract (source-backed)

The sanitized fixture `tests/hosts/hermes_probe/hook_payloads.json` records representative shapes with credentials and user content replaced. `ABSENT_FROM_RUNTIME_CALL_SITE` means the field is not passed at the inspected call site; it is not a claim that no other subsystem has that value.

| Hook | Producer and observed kwargs | Frequency / result semantics | Provenance and workspace finding |
|---|---|---|---|
| `on_session_start` | `agent/conversation_loop.py:1107-1117`: `session_id`, `model`, `platform` | Once when a new session prompt is built; return is ignored | No `parent_session_id`, sender, session key, cwd, or workspace in this call. A plugin cannot exclude a child at this point from this payload alone. |
| `pre_llm_call` | `agent/turn_context.py:1389-1405`: `session_id`, `task_id`, `turn_id`, `user_message`, `conversation_history`, `is_first_turn`, `model`, `platform`, `parent_session_id`, `sender_id` | Once per LLM turn; string or `{"context": ...}` results are appended to the user message ephemerally | Parent metadata is available here, but no cwd/workspace/session-key field is supplied to the plugin. This is the earliest inspected callback with ancestry metadata. |
| `post_tool_call` | `model_tools.py:1184-1235`: `tool_name`, `args`, `result`, `task_id`, `session_id`, `tool_call_id`, `turn_id`, `api_request_id`, `duration_ms`, `status`, `error_type`, `error_message`, `middleware_trace` | Once per terminal tool outcome, including error/cancel paths; observer result is not a transport receipt | No owner-origin or workspace identity is supplied. The tool runtime separately carries task/session cwd through internal state, not this plugin payload. |
| `pre_verify` | `hermes_cli/plugins.py:6871-6917`: `session_id`, `platform`, `model`, `coding`, `attempt`, `final_response`, `changed_paths` | Only after edits, bounded by the verify-nudge budget; `continue`/`block` plus a nonempty message keeps the loop going | Changed paths are evidence of file mutation, not authenticated ownership or a workspace association. |
| `transform_llm_output` | `agent/turn_finalizer.py:607-628`: `response_text`, `session_id`, `model`, `platform` | Once after a non-interrupted turn; first nonempty string wins and replaces the response | No delivery acknowledgement, owner identity, session key, cwd, or workspace. |
| `post_llm_call` | `agent/turn_finalizer.py:630-649`: `session_id`, `task_id`, `turn_id`, `user_message`, `assistant_response`, `conversation_history`, `model`, `platform` | Once only for a nonempty, non-interrupted final response | Returned assistant text is observable, but not proof that a client displayed or a human read it. |

Plugin registration is real and general: `PluginContext.register_hook` stores callbacks, and `PluginContext.register_skill` stores a namespaced read-only skill. `register_skill(name, path, ...)` requires an existing `SKILL.md`; the qualified name is `<plugin namespace>:<name>`. It is explicitly not added to the flat `~/.hermes/skills/` tree or the system prompt's available-skills index.

`PluginContext.inject_message` has a supported interface, but its boundary is explicit: CLI injection queues/interupts the local CLI; gateway injection requires an existing `session_key`, `plugins.entries.<plugin_id>.allow_gateway_injection: true`, and a live gateway. A true return means asynchronous queue acceptance, not platform delivery completion.

## Original requirement aliases

The original plan's B-numbers are preserved here: B1 is trusted origin and
session/project routing; B2 is native skill lifecycle; B3 is the approval threat
boundary; B4 is latency ordering; B5 is direct-tool defense; B6 is native UX,
transport and composition. Earlier investigation notes used a different
investigation-gate numbering; those aliases are not requirements and must not
be read as additional acceptance gates.

## B1 — trusted origin and session/project routing

Result: not certified; remain on the labelled CLI/project-local fallback for affected surfaces.

The first-turn producer supplies `parent_session_id` to `pre_llm_call`, so the adapter can exclude a child after that callback. The session-start producer does not supply it; the adapter must defer any owner/event side effect until the eligible pre-LLM callback. Parentless cron is not authenticated owner input: `cron/scheduler.py:6427-6449` constructs an agent with runtime/provider fields and no parent-session argument. The official hook/event docs likewise describe scheduled and gateway contexts, but do not turn parent absence into human authentication.

Project/workspace data exists in some host paths (for example ACP binds a session cwd and cron records a job workdir), but no inspected lifecycle hook payload exposes that association to a Python plugin. The plugin's project-root binding therefore proves only the installed project copy, not session-to-project routing. Two simultaneous desktop projects cannot be certified without a supported session/workspace field or a core extension.

Offline evidence is limited to source inspection and registration. No live callback was run because that would require real profile enablement and potentially model/provider execution.

## B2 — native skill lifecycle

Result: implemented and offline-verified for the pinned runtime; live profile activation remains unverified.

Official plugin documentation describes Python plugins as a supported extension surface. Installed source provides `ctx.register_skill(name, path, description, frontmatter)`. The path must exist, the name cannot contain `:`, and the result is opt-in namespaced resolution rather than automatic availability indexing. This rules out inventing `.hermes/skills` as a discovery path and rules out claiming that copying Claude skill files makes them globally available.

Minimal follow-up can be implemented without Hermes core changes:

1. Add canonical-content parity tests that read the existing Claude skill sources and a project-local plugin fixture.
2. Register `plumb` and `plumb-clarify` through `ctx.register_skill` from a plugin-owned `skills/` directory, with namespaced names and no global copy.
3. Test install, idempotent update, foreign-file preservation, dry-run, uninstall, missing-file failure, and explicit `skill_view("plumb:<name>")` resolution in a temporary Hermes home/plugin manager.
4. Document that namespaced plugin skills are explicit loads, not entries in the flat available-skills prompt.

The plugin owns the generated `skills/<name>/SKILL.md` files and registers bare
names only when their recorded digest matches. Explicit qualified loads are
`plumb:plumb` and `plumb:plumb-clarify`; flat discovery is intentionally not
claimed. The installer preserves foreign files, supports idempotent updates,
dry-run and owned-only uninstall. Actual PluginManager/skill_view resolution is
covered in a temporary-home subprocess with no network or model call.

## B3 — approval threat boundary

Result: no adapter-level security contract change is justified.

The existing Plumb owner-terminal and marker checks remain defense in depth. They prove behavior for marked/noninteractive test boundaries, not tamper-proof security against an agent with arbitrary code execution. Hermes exposes terminal subprocesses, PTY-capable paths and delegation; an adversarial process may remove a marker or write files directly. A text deny-regex would not establish an approval boundary.

The official MCP trust guidance is also placement/configuration based: local stdio commands and remote servers execute with the configured trust and permissions. The supported product decision still belongs to the owner: either keep the current explicit owner-terminal boundary, or separately authorize an out-of-band approval mechanism. No such contract amendment was inferred here.

## B4 — latency cause

Result: reproduced as a real baseline limitation; no production fix attempted.

Commands, with worktree import proven first:

- `PYTHONPATH=C:/coding/plumb-wt/hermes-compat/src C:/coding/plumb/.venv/Scripts/python.exe ...`: printed `C:\coding\plumb-wt\hermes-compat\src\plumb\__init__.py`
- `pytest tests/host/test_latency.py::test_intent_lines_survive_cpu_contention -o addopts= -q --tb=short`: failed in 16.07 s under full CPU contention; output was only `plumb: check skipped (budget)`, and the expected kept record line was absent
- Same test without contention: passed, 1 test in 14.17 s

The source explains the failure path. `hookio.py` has a 1.9 s hard watchdog. `stop.handle` performs `git_changed`, `open_core`, index/status/path analysis and `session_intent` before its first `ctx.keep` at `stop.py:530-544`. Under contention the watchdog can fire before that first keep, so the writer emits only the skip notice. This contradicts the module's intended guarantee that the read-back is kept before expensive evidence work; it is a concrete ordering/budget defect, not evidence that increasing budgets is safe.

Required separate fix card: add a deterministic RED test that forces the pre-keep path past the watchdog and asserts the read-back survives; move or precompute the minimum record read-back before the watchdog-sensitive work without changing owner approval semantics; run focused latency plus host/conformance suites under normal and contention modes; independently review timing and output ordering. Do not broaden this investigation into a shared-budget refactor.

## B5 — direct tools and PTYs

Result: capability boundary remains explicit and unproven as a security guarantee.

The installed runtime has separate edit-approval handling for `write_file` and `patch`, with tool args and outcomes visible to `post_tool_call`. That supports defense-in-depth observation. It does not prove complete protection across absolute/relative paths, traversal, symlinks, multiple patch files, `execute_code`, terminal subprocesses, PTYs, or delegated execution. No deny-regex or adapter approval change is proposed.

A future offline matrix should use temporary files and symlinks for both patch modes and `write_file`, then separately document what the runtime approval layer actually blocks. Any claim of adversarial containment requires an owner-approved core/security contract.

## B6 — native UX, transport, and composition

Result: unsupported for this adapter release.

The Python plugin hook contract provides user-message context injection and final-response transformation. It does not provide a streaming delivery receipt, a native status bar, or proof that another transform did not win. `transform_llm_output` is first-nonempty-result-wins; `post_llm_call` is skipped for empty/interrupted responses. `/plumb` gateway injection is queue acceptance only and requires a session key plus explicit grant.

Official desktop plugins are a separate JavaScript/ESM SDK loaded from `$HERMES_HOME/desktop-plugins/<id>/plugin.js`; that SDK does expose status-bar and other UI contribution areas. It is not the Python project-plugin lifecycle used by this adapter. Native UX therefore needs a separately scoped desktop-plugin card, not a claim added to the Python bridge.

## A/B coverage matrix

| Requirement | Evidence/disposition | Next action |
|---|---|---|
| A1 installation safety | Accepted Release A tests/docs; project-local only | No global install |
| A2 context selection | Accepted with installed-runtime corrections | Preserve root-local boundary |
| A3 conservative uninstall | Accepted; unknown Claude/override ownership preserved | No ownership database |
| A4 activation status | Accepted; installation is not callback evidence | Real callback requires owner enablement |
| A5 project root binding | Accepted for installed path and `.plumb` guard | Does not prove session routing |
| A6 lazy brief / child filtering | Accepted for supplied parent metadata | Parentless synthetic turns remain unsupported |
| A7 support boundary | Accepted in docs/status | Keep fallback labels |
| A8 existing behavior | Accepted focused/conformance coverage | Full regression remains incomplete |
| B1 origin and routing | Not certified; payload gap confirmed | Core/session metadata or fallback; no global enablement |
| B2 native skills | API identified; lifecycle not implemented | New adapter skill card + review |
| B3 approval threat model | Boundary characterized; no contract decision | Owner decision before security changes |
| B4 latency | Failure reproduced; cause localized | Separate RED/GREEN timing card |
| B5 direct-tool defense | Observation surface exists; containment unproven | Offline matrix; no regex security claim |
| B6 native UX/transport | Separate desktop SDK exists; bridge does not provide it | Separate desktop/transport design card |

## Exact follow-up graph

1. B2 implementation card: only the Hermes plugin template/installer, canonical skill fixture/tests, and Hermes-temp-home probes; no Hermes runtime/config edits. Acceptance: namespaced `register_skill`, explicit `skill_view`, idempotent lifecycle, foreign preservation, dry-run, and byte parity. Separate review card.
2. B4 implementation card: only the latency hook/test paths needed by the accepted plan; RED first, then minimal ordering fix. Acceptance: contention test preserves read-back and normal hook/host suites pass; separate review card.
3. B1 capability/core proposal card: read-only design unless the owner authorizes a Hermes core contract amendment. Acceptance: two-project interleave and parentless cron fixtures either route/exclude correctly using actual fields or remain explicitly unsupported.
4. B5 threat-model card: read-only fixture matrix first. Any approval/security contract change is a human decision, not an adapter follow-up.
5. B6 desktop card: separate JavaScript desktop-plugin design and review; do not mix with Python project-plugin support.

No card in this report authorizes live model calls, real profile activation, MCP installation, Hermes configuration writes, merge, or push.
