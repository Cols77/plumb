# Hermes compatibility Release A implementation evidence

Status: Release A implementation complete; runtime activation and Release B surfaces remain unverified and out of scope.

Requirement record: proposed SR-100 (bounded Hermes adapter hardening), related to SR-056. The source assessment SR-099 is outside this worktree's `.plumb` record set, so no synthetic SR-099 record or owner link was created.

Implemented behavior

- Hermes context selection is root-local and chooses the first nonempty readable file in this order: `.hermes.md`, `HERMES.md`, `AGENTS.md`, `agents.md`, `CLAUDE.md`, `claude.md`.
- Uninstall preserves a Claude-named block because ownership is shared or unknown.
- Install and status distinguish installed files, project discovery, and runtime activation. Status intentionally reports activation as unverified and retains CLI fallback guidance.
- Generated callbacks bind subprocesses to the installed project root and return empty output without spawning when the generated path is not a valid `.hermes/plugins/plumb/plugin.py` installation under a `.plumb` project.
- The first owner prompt lazily obtains the session-start brief exactly once when no session-start observer fired.
- Documentation states the project-bound bridge and the unsupported desktop multi-project, scheduled-turn provenance, native skill, MCP, status-bar, and transport-receipt boundaries.

Commits

- `ae0417e` — `fix: harden bounded Hermes adapter behavior` (SR-100)
- `ba70f59` — `docs: record bounded Hermes hardening scope` (SR-100)

Validation evidence

- Worktree import check: `C:\coding\plumb-wt\hermes-compat\src\plumb\__init__.py`.
- Focused Hermes/conformance suite: passed, 22 tests.
- Host suite after implementation: passed, 67 tests.
- Plugin Doctor: passed; Hermes Agent v0.21.0 (2026.8.31), 6 hooks and 0 tools registered.
- Broad host/host-latency/MCP invocation was not clean in combined runs: transient failures appeared in an unrelated Codex shell assertion and the CPU-contention/session-brief tests; each failed test passed when rerun in isolation. The broad result is therefore not claimed green.
- Full `pytest -q` was attempted once and exceeded the tool's 420-second execution limit without a final result. No full-suite pass is claimed.
- `git diff --check` passed for the committed candidate.

Safety boundary

No Hermes runtime configuration, real profile, credentials, `.env`, paid/live model call, merge, or push was changed. Plugin Doctor and offline tests prove registration and adapter behavior for supplied fixtures; they do not prove live activation, transport delivery, owner provenance for every scheduled turn, or multi-project desktop routing.
