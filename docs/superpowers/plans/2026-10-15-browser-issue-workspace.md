# Browser Issue Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Follow test-driven-development and verification-before-completion. The owner has already selected subagent execution and authorized implementation.

**Goal:** Deliver a working Plumb issue-resolution browser workspace with Escouade UI reuse, embedded diagram-mod explanations, and proven owner-answer/agent-handoff behaviour.

**Architecture:** Loopback Python API over existing Plumb core, separate browser owner provenance, durable next-turn follow-up; Svelte frontend with attributed presentation components. Keep the original checkout untouched; implement in `C:/Users/33630/.codex/worktrees/1190/plumb`, branch `feat/browser-issue-workspace`.

**Tech Stack:** Python 3.12+, stdlib HTTP, Svelte 5/TypeScript/Vite, pytest, Vitest, Playwright, locally bundled fonts.

## Task 1: Browser core and transport

Files: `src/plumb/browser/{__init__,cli,server,service,session,followup,diagrams,demo}.py`; focused modifications to `src/plumb/cli.py`, mod offer/press plumbing, answer source/provenance recheck, and `src/plumb/hosts/claude_code/prompt.py`; tests under `tests/browser/`.

- [ ] Write failing tests using temporary real repositories. Assert snapshot exposes stored source-session cards and full content, browser registration never changes existing mod registration, an answer approves exactly displayed hashes, changed content refuses, duplicate press cannot duplicate approval, and approvals still recheck after runtime session data is removed.
- [ ] Implement a separately registered browser surface and authenticate it internally through the existing offers/press/answer path. Separate browser offers from mod offers to avoid credential collisions. Preserve mod behaviour and tests.
- [ ] Implement locked server operations with loopback-only binding, capability authentication, exact Origin/Host checks, JSON type/size errors and safe static routing. `plumb ui --root PATH --port PORT --open`, `--demo`, `--assets PATH` supported. Secret in fragment; no token in request logs. Use current Python package, never shell interpolated commands.
- [ ] Return a documented JSON contract consumed by Task 2, with sessions, issues, fullcontent, offers/actions, evidence and follow-ups. Keep issue id scoped by session. Read project sources only within root.
- [ ] Queue answer follow-up by source session; prompt hook consumes context without logging it as an owner prompt. Persist queued/delivered and deduplicate messages.
- [ ] Serve bounded diagram file text only for an existing card's diagram path, with path confinement and explicit error state; frontend parser performs SVG extraction. Supply original text and derived source path, not arbitrary file access.
- [ ] Implement labelled temporary demo project covering representative genuine card shapes, diagram, choices, evidence and blocked/done/left-open states. Tests may seed all kinds separately.
- [ ] Run `C:/coding/plumb/.venv/Scripts/python.exe -m pytest tests/browser tests/mod -q` with `PYTHONPATH` targeting this worktree. Run changed-area Ruff checks. Report exact results and contract. Commit only task-owned files.
- [ ] Independent spec review, fix/re-review; independent quality review, fix/re-review.

## Task 2: Svelte workspace and diagram presentation

Files: `ui/package.json`, lockfile, Vite/TypeScript/Vitest configs, `ui/src/{App.svelte,app.css,main.ts,lib/*,components/*}`, `ui/THIRD_PARTY_NOTICES.md`, component tests, README launch instructions. Build to `src/plumb/browser/static` and include distributable assets in package.

- [ ] Pin and attribute copied Escouade Splitter/DiffView/theme portions, adapting imports to local helpers and browser actions. Copy diagram-mod pure parser/model/preparation with MIT notice. Remove desktop-only dependencies. Install pinned compatible Svelte 5/Vite toolchain.
- [ ] Write failing interaction tests for issue selection/filtering, actual offer buttons, correction input, stale answer feedback and multi-question rendering.
- [ ] Implement project/session navigation, issue inbox, full explanation and actual core actions. Three-pane desktop composition; usable narrow layout. Preserve draft text during polling, selection by URL, back/forward, keyboard focus, error/retry and busy states. Fetch adapter authenticates using fragment token then removes it from history and retains in session storage only.
- [ ] Implement diagram above questions using extracted SVG image Blob; size cap, text alternative, zoom +/-/reset/download and clear fallback. Never inject raw HTML/SVG or trust external scripts. Revoke replaced Blob URLs.
- [ ] Implement evidence and activity views with record details and real diffs where provided. Clearly distinguish owner answer, pending agent follow-up and measured verification. No fake progress or placeholder controls.
- [ ] Run frontend unit tests, `npm run check`, `npm run build`; inspect actual compiled output. Commit task-owned files.
- [ ] Independent spec review, fix/re-review; independent quality review, fix/re-review.

## Task 3: Full interaction and integration proof

Files: `ui/tests/e2e/`, Playwright config, demo runner, `docs/browser-workspace-verification.md`, screenshots under ignored local artifacts (or documented deliverables), README.

- [ ] Independent test agent enumerates every visible control and navigation route; add e2e tests against real Python server and temporary project, avoiding real owner approvals.
- [ ] Assert real approval log plus source card state after clicks; stale hash refusal; matching-session hook receives exactly one follow-up; live mod unaffected; refresh/restart semantics and disconnected recovery.
- [ ] Browser test all offered actions, selector/search/filter/reset, tabs, record/diff modes, diagram zoom/reset/download, modal open/cancel/submit, refresh/help, keyboard and browser navigation, resize/mobile, error/empty state. Capture screenshots and browser errors.
- [ ] Fix agents address reproducible failures with regression tests; independent reviewers recheck. Build/serve latest assets after changes.
- [ ] Root verifies Python tests, frontend checks/build/tests and browser tests with fresh output. Final code review compares implementation with spec and checks provenance/security.
- [ ] Start a persistent server, open installed browser visibly (in-app browser execution unavailable), and show screenshot proof. Report worktree/branch, launch command, measured counts and precise limitations. Leave reviewable implementation on feature branch; no main merge without explicit request.
