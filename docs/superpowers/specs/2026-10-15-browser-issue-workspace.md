# Plumb browser issue workspace

The owner approved extracting Escouade's visual foundation and selected components into a browser frontend backed by Plumb, and requested diagram-mod diagrams in explanations, subagent implementation/review/fix workflows, thorough button/navigation tests, and an automatically shown browser demonstration.

## Product and design

One repository at a time. An issue inbox leads to the selected issue, original context, options and consequences, with evidence and related activity alongside. Preserve existing card semantics and every issue kind. The visual direction is Escouade's warm charcoal workspace, Hanken Grotesk and JetBrains Mono, restrained amber attention and green evidence. The distinguishing interaction is understanding the issue through its diagram before answering it. Use Svelte 5, keyboard-accessible controls, responsive panes and local assets.

Reuse attributed Escouade theme primitives, Splitter and DiffView where appropriate, recording upstream revision 34322c696757790dd32589311f46c662c057ebd0 and MIT notices. Do not import its Tauri application state or agent runtime. Reuse diagram-mod's standalone SVG extraction/preparation under its MIT notice; do not import Claude UI adapter. Render extracted SVG as an image, never raw repository HTML or executable SVG markup in the application DOM.

## Architecture

`plumb ui` runs a loopback-only Python server and serves built browser assets. A browser capability secret is held in memory and provided in the launch URL fragment (never persisted/logged); authenticated requests, exact Origin/Host validation, bounded JSON and scoped static files protect owner actions. Support an explicit project root and port, `--open`, and isolated labelled `--demo` data. Never implicitly remove the agent session marker. Demo is available for exercising decisions without approving real project records.

The backend exposes source sessions, issues with existing fullcard content and offers, record/evidence details, and bounded diagram content. Browser registration is separate from `mod.json`; opening the browser must never retire or overwrite a live Claude panel. Reuse the core answer path and preserve exact shown-content checks, offer provenance, append-only logs, duplicate-answer protections, and approval rechecking after session files are absent. Any new browser provenance must be explicit and leave existing mod approvals valid.

Follow-up is a durable per-source-session outbox. Browser answers and optional correction text enqueue their truthful meaning, then the matching prompt hook delivers that context to the agent at its next user-triggered turn. It must not masquerade as an owner prompt for automatic approval extraction. Show queued/delivered accurately; do not claim the agent ran or the repair passed from a button press. Evidence remains authoritative. Mod and browser share issue state without stealing credentials.

## Interface

- Header: project identity, session selector, connection status, refresh, help.
- Inbox: status filters, kind filter/search, counts and selectable issues. Selection survives refresh when still available; browser back/forward restores navigation.
- Issue: kind/state, full issue/context/assumptions, diagram when present, question/options/consequences and actual existing action labels. Ask for a change supports editable follow-up text; Leave open stays discoverable. Preserve multi-question cards.
- Detail panes/tabs: explanation, evidence/related records and diff where available, activity/follow-up history. Every displayed control performs a real action; no placeholder agent controls.
- Diagram: original SVG from the card path, zoom in/out/reset and download, readable text description, clear missing/invalid fallback. Reject traversal/symlink escape and bounded oversized content; do not execute repository scripts.
- Handle no issues, no sessions, unavailable server, stale card, duplicate click, concurrent tabs, and missing evidence without losing owner work.
- Document launch/build/development, security boundary, handoff semantics, known host limitations and upstream attribution.

## Acceptance and review

Use real temporary Plumb repositories for API/integration tests. Test every issue kind, each offered action, multiple questions, stale records, repeat answers, preserved live mod registration, provenance rechecking, matching-session follow-up, restart recovery, request auth/origin/path/body checks, and diagram fallbacks. UI tests cover every button/navigation path, filters/search/empty states, keyboard/focus, resizing, browser history, reconnect, narrow viewport and diagram controls. Independent subagents perform spec then quality review and browser interaction testing; fix findings and rerun affected checks. Finish with passing Python checks, frontend typecheck/build/unit tests, real-server browser e2e tests, screenshots, and visible browser demonstration. Evidence should state limitations precisely; never test approval actions against the owner's live records.
