# Hermes compatibility next plan

Status: proposed follow-up plan from the bounded runtime investigation. The namespaced skill slice below is implemented offline; this document is not approval to enable Hermes, change Hermes core/security contracts, run live models, install MCP, merge, or push.

## Support boundary to carry forward

Release A is a project-local Python plugin bridge validated by offline adapter tests and Plugin Doctor against Hermes Agent v0.21.0 (`b20cc5f787ea816ea8645603b7b2ac8234dcb8b4`). It is not authenticated owner capture for parentless scheduled turns, not session-scoped routing for a globally loaded plugin, not adversarial approval protection, and not native desktop/streaming UX. The implemented skill slice is explicit namespaced resolution, not automatic skill discovery.

The runtime facts that constrain every follow-up are captured in `docs/hermes-compat-runtime-evidence.md` and `tests/hosts/hermes_probe/hook_payloads.json`. Do not invent `cwd`, `workspace`, `origin`, `is_owner`, or delivery-receipt fields in plugin callbacks.

## Ordered execution graph

### Investigation Gate B2 (original requirement B3): namespaced native skill bridge

Type: implementation, then separate read-only review. This is the first executable follow-up because the runtime API is available without a core contract change.

Allowed paths:

- `src/plumb/hosts/hermes/install.py`
- `src/plumb/hosts/hermes/templates/plugin.py`
- `tests/hosts/test_hermes.py`
- `tests/hosts/hermes_probe/`
- `docs/hosts.md`

Prohibited paths: installed Hermes source/config, real profile homes, `.env`/credentials, `src/plumb/approvals.py`, unrelated adapters, MCP installer, and desktop SDK files.

Work completed in this slice:

1. Installer-generated plugin-owned `skills/` files reuse the canonical Claude templates with the same launcher substitution; no duplicate canonical production source is maintained.
2. `ctx.register_skill` receives bare `plumb` and `plumb-clarify` names. Hermes resolves these as `plumb:plumb` and `plumb:plumb-clarify`; there is no flat available-skills claim.
3. Offline tests cover install, idempotent launcher update, owned path-to-uv byte parity, missing/foreign preservation, dry-run, owned-only uninstall, digest-guarded registration, and a temporary-home pinned PluginManager/`skill_view` subprocess.
4. Keep all validation offline and synthetic; Plugin Doctor remains registration-only evidence.

The committed `tests/hosts/hermes_probe/hook_contract.py` consumer validates the
actual pinned producer dispatch calls and absent fields, replays only those kwargs
into generated installed plugins, captures subprocess payloads and cwd during a
two-project interleave, and records explicit-parent exclusion plus a parentless-
cron non-authentication counterexample. It does not claim live routing or owner
certification.

Acceptance commands:

```text
export PYTHONPATH=C:/coding/plumb-wt/hermes-compat/src
C:/coding/plumb/.venv/Scripts/python.exe -m pytest tests/hosts/test_hermes.py -o addopts= -q --tb=short
C:/coding/plumb/.venv/Scripts/python.exe -m pytest tests/hosts -o addopts= -q --tb=short
hermes plugins doctor src/plumb/hosts/hermes/templates --ci
```

These commands use Git Bash syntax on Windows; use the equivalent environment assignment in another shell.

The worker must print `plumb.__file__` before tests, record exact counts, and commit only the allowlisted paths. The separate reviewer must verify byte parity and the no-global-skill claim.

### Card B4: latency ordering correction

Type: implementation, then separate read-only review. It depends on no B2 files and should be serialized after B2 only for one-worktree safety.

Allowed paths:

- `src/plumb/hosts/claude_code/hookio.py`
- `src/plumb/hosts/claude_code/stop.py`
- `tests/host/test_latency.py`
- `docs/followups.md` only if the accepted cause needs durable explanation

Prohibited paths: Hermes adapter, approval semantics, global watchdog policy, unrelated host handlers, budget increases without owner decision, and deletion/weakening of the contention assertion.

RED/GREEN work:

1. RED: deterministically delay the pre-read-back path or use an injected clock/fixture so the watchdog reaches its deadline before the current first `ctx.keep`; assert that the required record read-back still appears.
2. Implement the smallest ordering change that establishes the documented invariant: minimum read-back is kept before expensive evidence/awareness work. Preserve the one-process hook contract and skip notice.
3. GREEN: run the contention test, the in-process budget test, CLI hook tests, and host/conformance suites in normal and stressed modes. Capture wall times and output shape.

Acceptance commands:

```text
export PYTHONPATH=C:/coding/plumb-wt/hermes-compat/src
C:/coding/plumb/.venv/Scripts/python.exe -m pytest tests/host/test_latency.py -o addopts= -q --tb=short
C:/coding/plumb/.venv/Scripts/python.exe -m pytest tests/hosts tests/host -o addopts= -q --tb=short
```

Do not call the full suite green unless it completes with a final summary. The independent reviewer must inspect the watchdog/read-back ordering and confirm no approval or output-contract changes.

### Card B1: provenance and project routing capability proposal

Type: read-only runtime investigation first; implementation is blocked on an owner decision if Hermes core must expose new fields.

Allowed paths:

- `tests/hosts/hermes_probe/`
- `docs/hermes-compat-runtime-evidence.md`
- `docs/hermes-compat-next-plan.md`

Investigation:

1. Use a temporary Hermes home and the real PluginManager with no network.
2. Capture sanitized callback payloads for CLI, desktop/gateway, cron, background review, and delegated child paths.
3. Interleave two project roots and a parentless scheduled run. Use only fields supplied by the runtime.
4. If no callback carries both ancestry/origin and workspace identity, leave those surfaces on explicit CLI fallback and prepare a narrow core-extension proposal. Do not add guessed kwargs.

Acceptance: fixture payloads include exact keys and absent fields; source/version references are pinned; no real profile is enabled.

### Card B5: direct-tool and approval threat-model matrix

Type: read-only capability matrix, followed by a human decision only if the contract must change.

Allowed paths: `tests/hosts/hermes_probe/`, `docs/hermes-compat-runtime-evidence.md`, `docs/hermes-compat-next-plan.md`.

Exercise offline temporary paths for `write_file`, both patch modes, multiple files, absolute/relative paths, traversal, and symlink cases. Separately record PTY, marker-removal, `execute_code`, terminal subprocess, and delegation limitations. A passing matrix may establish defense-in-depth behavior only; it cannot establish adversarial containment. Do not add a text deny-regex.

### Card B6: native desktop/transport surface

Type: separate design and review card, not a Python adapter change.

Inspect the official JavaScript desktop-plugin SDK and its status-bar/session APIs. Define whether Plumb needs a native desktop plugin, a gateway event consumer, or no additional UX. Preserve the Python hook limitations: first-nonempty transform wins, post-LLM is not a delivery receipt, and gateway injection requires a session key plus explicit grant.

Acceptance is a written surface contract and offline fixture plan. Any live desktop enablement or transport test needs explicit authorization and a separate gate.

## Deferred owner decisions

These are genuine high-level boundaries, not routine worker questions:

- whether to request a Hermes core extension for trusted origin and session/workspace identity;
- whether an out-of-band approval boundary is required beyond the existing owner-terminal defense in depth;
- whether to build a separate native desktop plugin for status/streaming UX.

Until those decisions are made, the adapter must retain its current fallback labels and must not claim full Claude parity.
