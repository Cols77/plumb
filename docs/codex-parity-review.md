# Claude plugin / Codex parity review

Review date: 2026-11-09. Source baseline: 6381c04be. Local Codex: 0.166.0.
Development branch: intent/codex-plugin-parity. This is a research and implementation
scope draft; no runtime changes or successful live proof are claimed.

## Capability inventory

| Claude Iaso capability | Current Codex integration | Required work / boundary |
| --- | --- | --- |
| Record grounding, capture, show, explain, review, impact, conflicts, test mapping, stale links and merge checks | Shared Python CLI is available; AGENTS fallback exists | Preserve shared semantics and prove execution in Codex |
| SessionStart, UserPromptSubmit, Stop | Project installer registers these three hooks | Diagnose actual failed hooks; verify prompt delivery in this thread, budgets and bootstrap paths |
| Background post-edit checks and synchronous edit-check | Not installed by Codex adapter | Normalize apply_patch payloads and install supported PostToolUse handlers |
| Pre-tool clarification gate and command guard | Not installed by Codex adapter | Adapt tool names and argument schemas; prove refusal before mutation and document shell coverage |
| Question answer capture | Claude AskUserQuestion PostToolUse handler exists; no Codex registration | Support synchronous answers; async tool return is not an owner answer; bind subsequent owner messages |
| SubagentStop and SessionEnd | Not installed by Codex adapter | Add host adapters with child/parent attribution and bounded teardown |
| Skills and plain-language /iaso entry point | Plugin skills are discoverable here, but project Codex installer installs no skills | Ship Codex-specific portable skills and references; remove Windows-only commands and Claude-only UI/workflow instructions |
| Explicit intent loop | Installed skill promises CODEX_THREAD_ID; runtime resolver omits it; $iaso-intent invocation does not open a loop | Correct thread identity and explicit skill invocation recognition; prohibit borrowing another session's latest prompt |
| Model clarification/judging | Auto dispatcher selects Claude or Hermes, not Codex | Add a Codex-capable model route with explicit unavailable outcomes and equivalent schemas; do not silently approve |
| Debug cases, intent build and landing workflows | Shipped JS uses Claude workflow globals (agent, phase, log) and Claude model names | Provide host-appropriate orchestration preserving gates, worktrees, proof, failure and handover behavior |
| Evaluation and independent proof checking | Evaluate run/owner/proofcheck invoke Claude | Introduce host-specific runners and live Codex acceptance coverage |
| Status band, loop pane, known problems, progress, clickable rows and buttons | Claude mod imports atom/read/update/Register from claude-code | No documented equivalent Codex UI module API established; keep command/text fallback; UI alternative requires a separate host-capability decision |
| Session reopen/send and pane navigation | Claude-oriented presentation and workflow contracts | Audit routing separately before claiming Codex session-control parity |
| Text/diagram/video studies | Shared study CLI; Claude plugin ships study-video and Manim skills | Package portable skills/assets; replace assumptions about Claude's diagram mod and window display |
| Plugin distribution and private wheel bootstrap | Claude manifest, hooks and bootstrap are bundled; Codex can discover imported skills | Add tested Codex packaging/host routing; avoid duplicate project/plugin hooks and false Claude provenance |
| Owner summary and notification | Stop plus notify configured; notify does not count as visible proof | Verify owner-visible summary and preserve unseen-summary semantics |

Evidence: plugin/hooks/hooks.json, plugin/hooks/register.tsx, plugin/commands/iaso.md,
plugin/workflows/*.js, plugin/skills/, src/iaso/hosts/codex/install.py,
src/iaso/hosts/cli.py, src/iaso/hosts/neutral.py, src/iaso/stale.py,
src/iaso/understand/clarify.py, src/iaso/understand/dispatch/__init__.py,
src/iaso/evaluate/{run,owner,proofcheck}.py and docs/hosts.md.

## Current host capabilities and mods

The old docs/hosts.md table describes Codex 0.160.0. Current official documentation
describes PreToolUse/PostToolUse (including apply_patch and nested code-mode tool
calls), SubagentStop and SessionEnd. Thus missing Iaso registrations must not be
described as unavailable host events. Wire contracts still require individual tests.

- https://learn.chatgpt.com/docs/hooks
- https://developers.openai.com/plugins/build/plugins

Claude's register.tsx cannot be reused directly: it imports a Claude-specific runtime
and uses its persistent atoms, UI resolution, docking and button events. The fetched
OpenAI documentation describes MCP Apps UI in ChatGPT, and ChatGPT extensions for
conversation panels/sidebar apps. It does not establish support for loading Claude-like
UI modules in Codex CLI or this Codex surface. This is an evidence limit, not proof that
all Codex surfaces can never support UI. A ChatGPT MCP panel would be a separate port,
not a verified Codex mod. The existing record decision to remove Iaso's MCP server
(SR-380) also needs review before proposing such a port.

- https://developers.openai.com/plugins/build/chatgpt-ui
- https://developers.openai.com/plugins/build/extensions

## Observed blockers

1. Owner reports two hook failures. Exact failed hook names/errors remain unavailable;
   no root cause is claimed. The project hook commands use uv and ten-second timeouts.
   Agent shell invocations of uv fail writing its external cache under this sandbox;
   that alone does not prove the host hook failed for the same reason.
2. No hook-recorded prompt was available for thread
   01a1bf49-bca0-7973-8a1c-dad67830ff3b. Explicit-session intent open initially returned
   an empty digest and null loop. The mandatory turn fallback recorded via: turn;
   it must not be presented as trusted hook evidence.
3. Session auto-resolution omits CODEX_THREAD_ID. The first unqualified intent open
   selected a different session (dfcc7cc3-feff-4b1f-ab6b-8550c3318ece). That loop was
   not adopted, advanced, or used as authorization for this work.
4. After fallback, explicit-session clarify returned digest
   sha256:35d073dc4432945c8c99315766294ce45de346ab03f5b0a6426b3f473c550da5.
   intent open still returned loop: null. The parser recognizes slash commands,
   not the owner's $iaso-intent skill invocation.
5. Installed local skills hardcode .venv/Scripts/python.exe, absent on this Linux host.
6. Turn-start fallback produced roughly 230,000 tokens of repository-wide output,
   including unrelated landed work and debugging cases. Context bounding needs review.

## Proposed implementation sequence and acceptance

1. Restore trustworthy thread-local workflow entry: session identity, skill command
   parsing, portable launcher and observable hook failures. Tests must cover concurrent
   threads, absent prompts, self-recorded provenance and explicit handovers.
2. Add the supported tool/lifecycle bridges, with fixture tests for each real Codex
   input/output contract and foreign-hook-preserving install/uninstall/idempotency.
3. Ship Codex skills and a native model/workflow/evaluation route. Test unavailable
   models, canceled/async questions, stopped workflows and proof refusal.
4. Prove the full owner journey in a fresh live Codex session: request, proposed
   records, clarification, isolated worktree, gates, build, tests, visible evidence,
   and completed intent. Owner proof preference is pending.
5. Decide the UI port only after establishing an actually supported target surface.
   Until then, explicitly document text/command equivalents for Claude's panel actions.

The intent skill requires ordered passing gates. No clarify/plan/build gate has passed
for this request and no implementation or proof is marked complete.
