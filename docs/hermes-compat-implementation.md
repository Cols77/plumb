# Hermes compatibility Release A implementation evidence

Status: bounded Release A implementation evidence; runtime activation and Release B surfaces remain unverified and out of scope.

Requirement record: proposed SR-100 (bounded Hermes adapter hardening), related to SR-056. The source assessment SR-099 is outside this worktree's `.iaso` record set, so no synthetic SR-099 record or owner link was created.

Implemented behavior

- Hermes context selection is root-local: the first regular `.hermes.md`/`HERMES.md` is selected as the Hermes type, and an empty or unreadable selection falls through to nonempty `AGENTS.override.md`, `AGENTS.md`, `agents.md`, then Claude aliases. The second Hermes name is not selected as a fallback. Ancestor/nested and Cursor context sources are not universally preserved; status concerns only the currently selected target and uninstall does not chase historical blocks.
- Uninstall preserves Claude-named and `AGENTS.override.md` blocks because ownership is shared or unknown, including dry-run.
- Install and status distinguish installed files, project discovery, and runtime activation. Status intentionally reports activation as unverified and retains CLI fallback guidance.
- Generated callbacks bind subprocesses to the installed project root and return empty output without spawning when the resolved path is not exactly `.hermes/plugins/iaso/plugin.py` under a `.iaso` project; shallow and loose copies remain importable for Doctor.
- The first eligible prompt obtains the session-start brief exactly once after ancestry filtering, regardless of whether an observer fired; an observer alone never dispatches startup.
- Documentation states the project-bound bridge and the unsupported desktop multi-project, parentless synthetic-turn provenance, native skill, MCP, status-bar, and transport-receipt boundaries. `hermes plugins enable iaso` is an owner-run profile allowlist step, independent of project discovery.

Commits

- `ae0417e` — `fix: harden bounded Hermes adapter behavior` (SR-100)
- `ba70f59` — `docs: record bounded Hermes hardening scope` (SR-100)

Validation evidence

- Worktree import check: `C:\coding\iaso-wt\hermes-compat\src\iaso\__init__.py`.
- Focused Hermes/conformance suite after correction: passed, 41 tests.
- Host suite after correction: passed, 89 tests.
- Plugin Doctor: passed; Hermes Agent v0.21.0 (2026.8.31), 6 hooks and 0 tools registered.
- Broad host/host-latency/MCP invocation was not clean in combined runs: transient failures appeared in an unrelated Codex shell assertion and the CPU-contention/session-brief tests; each failed test passed when rerun in isolation. The broad result is therefore not claimed green.
- Full `pytest -q` was attempted once and exceeded the tool's 420-second execution limit without a final result. No full-suite pass is claimed.
- `git diff --check` passed for the committed candidate.

Safety boundary

No Hermes runtime configuration, real profile, credentials, `.env`, paid/live model call, merge, or push was changed. Plugin Doctor and offline tests prove registration and adapter behavior for supplied fixtures; they do not prove live activation, transport delivery, owner provenance for every scheduled turn, or multi-project desktop routing.
