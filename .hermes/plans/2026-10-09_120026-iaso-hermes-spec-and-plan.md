# Iaso Hermes Compatibility — Specification and Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Keep edits serialized in one worktree; use an independent reviewer after each green work package.

**Goal:** Make Iaso's existing project-local Hermes adapter honest about activation, preserve repository instructions, and validate its event bridge without claiming unproven desktop or owner-authentication guarantees.

**Architecture:** Keep the existing project-local plugin and subprocess boundary into `iaso hook`; do not fork the intent engine or move it out of Claude-named modules during this work. Harden installation and root binding first, then establish a real-runtime acceptance gate before enabling automatic owner-prompt logging on additional surfaces. CLI fallback remains available when activation or surface support is unverified.

**Tech stack:** Python, pytest, existing Iaso CLI and Hermes plugin API; no new production dependency.

**Status:** Proposed specification. Only this plan was written during planning. This is an implementation-ready bounded first release, plus explicitly gated follow-on scope—not a claim that full desktop parity is already specified or proven.

---

## 1. Review of the previous assessment

### Confirmed from source

- The adapter already exists at `src/iaso/hosts/hermes/install.py` and `src/iaso/hosts/hermes/templates/plugin.py`. This is not a greenfield port.
- It registers six hooks and `/iaso`; runs a separate Iaso process because Hermes uses its own interpreter; maps context, continuation requests, and owner summaries into host outputs.
- `src/iaso/hosts/neutral.py` exposes `TurnEvent` / `TurnOutput` orchestration. **It still imports and delegates to Claude Code handlers.** Reuse is real, but calling the engine physically host-independent was too strong.
- The installer currently treats `HERMES_ENABLE_PROJECT_PLUGINS=1` plus generated files as activation evidence. Hermes's standalone plugin loading also requires enablement. File presence and an environment variable cannot prove a callback actually ran.
- `src/iaso/hosts/common.py:341` selects `.hermes.md`, `HERMES.md`, or newly created `AGENTS.md`; it does not preserve the existing `CLAUDE.md` fallback.
- Hermes's `agent/prompt_builder.py:2408` documents first-successful-source context loading: Hermes files, AGENTS files, Claude files, Cursor rules. Creating AGENTS can shadow existing Claude instructions. It also supports lowercase `agents.md` and `claude.md`; selection is more subtle than file existence alone.
- The plugin runs subprocesses using `os.getcwd()`, not a session-scoped workspace. This is unsuitable as evidence that a globally installed plugin is safe in a multi-session desktop process.
- `parent_session_id` exclusion is implemented and tested. It proves exclusion when that field is supplied, **not that every cron/background/synthetic message supplies it**.
- `transform_llm_output` is first-valid-result-wins. `_settle()` conservatively marks missing summaries unseen, but a final text value is not a transport delivery receipt.
- `/iaso` injection is supported in CLI. Hermes `PluginContext.inject_message()` needs an existing `session_key` and a configuration grant for gateway injection. The current callback supplies neither. Do not claim universal command parity.
- `require_owner()` refuses marked processes and noninteractive terminals. Hermes can also expose PTYs. A TTY check is defense in depth, not a security boundary against an arbitrary agent-controlled shell that can remove environment markers or write files.
- FakeCtx tests prove adapter behavior against supplied events. Plugin Doctor proves discovery/import/registration, not real turn behavior, transport delivery, or activation in the user's running process.

### Corrections to the earlier recommendation

1. Withdraw the numerical reuse/readiness estimates: they were judgments, not measured coverage.
2. **Do not switch to a user-global plugin in this release.** Root selection and session provenance must be proven first. The existing project-local approach is the smaller change.
3. Do not automatically edit Hermes configuration, enable trust, install MCP, or copy files into the real Hermes home.
4. Do not implement a shell-command deny regex and describe it as approval protection. Generic Python, subprocesses, delegated tools, and PTYs bypass simplistic text matching.
5. Do not change the MCP installer in this adapter release. It is independently usable but has its own configuration-migration/consent scope.
6. Do not fix the shared latency failure by raising budgets or deleting the assertion. Diagnose it separately before claiming the full regression suite is green.

### Evidence freshness

The preceding investigation reported successful focused adapter/conformance tests and Plugin Doctor, plus a reproducible CPU-contention latency failure. This planning turn reread code; it did not rerun tests or treat those earlier reports as fresh execution evidence. Reproduce them in Task 0 before implementation.

Authoritative reference: https://hermes-agent.nousresearch.com/docs . Local runtime corroboration inspected at `C:/Users/33630/AppData/Local/hermes/hermes-agent/`:

- `hermes_cli/plugins.py`: registration, enablement, transform semantics, injection.
- `hermes_cli/plugin_dev.py`: Doctor uses a temporary home, blocks network, and loads through PluginManager.
- `agent/turn_context.py:1389`: pre-LLM callback fields include session/task/turn/user message/platform/parent; no workspace field in this call site.
- `agent/turn_finalizer.py:630`: post-LLM callback uses `assistant_response`.
- `agent/prompt_builder.py:2408`: project context precedence.

Do not vendor/import these installed Hermes source files into Iaso production code.

## 2. Scope and acceptance specification

### Release A — implement now after approval

A1. Installation remains project-local at `.hermes/plugins/iaso/`; no host configuration writes. Reinstallation is idempotent; foreign plugin files and owner text are preserved; dry-run changes nothing.

A2. Hermes context selection chooses the first nonempty readable root-local file in this order: `.hermes.md`, `HERMES.md`, `AGENTS.md`, `agents.md`, `CLAUDE.md`, `claude.md`. With none, use `AGENTS.md`. Codex and Pi behavior is unchanged. Root-local scope is explicit; this release does not clone Hermes's ancestor-context discovery.

A3. Uninstall must not remove a iaso block in `CLAUDE.md` / `claude.md`, because it may have been installed/shared by Claude independently and current metadata cannot prove ownership. Report that conservative preservation. This intentionally leaves a useful CLI fallback block rather than risking removal of another host's instructions. Do not introduce an ownership database just for this case.

A4. Status distinguishes **installed files**, **project discovery flag**, and **runtime activation not verified**. It must never claim hooks are running or a session marker is set solely because files and an environment flag exist. Print both activation prerequisites and a restart reminder; retain fallback guidance. Do not parse the user's complete Hermes config to infer live state.

A5. Every event subprocess is bound to the generated plugin's project root, not whatever process cwd happens to be at callback time. For the installed path `.hermes/plugins/iaso/plugin.py`, root is `Path(__file__).resolve().parents[3]`. Require `.iaso` there; outside a valid installed location, return the existing empty output without launching a subprocess. This is project binding, not session routing; concurrent desktop support is not implied.

A6. The template's session-start brief is lazily obtained at the first pre-LLM callback when the session-start observer did not supply it. Never call session-start twice for the same live session. Child sessions remain excluded before any event call.

A7. Installation prints an explicit support boundary: project-bound event bridge, delegated-child filtering by parent metadata, desktop/cron provenance not yet certified. Documentation must not say all background or cron messages are skipped.

A8. Existing successful behavior remains: exact prompt text; once-per-attempt continuation behavior; no synthesized owner affirmations; missing summaries marked unseen; real Iaso integration through subprocess; no production dependency on Hermes's Python installation.

### Release B — gated, do not silently fold into A

B1. Prove trusted owner-message origin for desktop, cron, background review, and delegated agents through actual host call sites. Absence of `parent_session_id` is not proof of human origin. If the runtime does not expose sufficient provenance, remain on explicitly labelled CLI fallback for the affected surface; do not manufacture provenance using message contents or session-name guesses.

B2. Prove session-scoped project routing with two simultaneous desktop projects. A process cwd, a global environment variable, or a project-root constant cannot by itself route a globally loaded plugin across sessions. No global plugin until the runtime supplies a supported session→workspace association.

B3. Native skills: reuse the behavioral content of `src/iaso/hosts/claude_code/templates/skills/iaso/SKILL.md` and `iaso-clarify/SKILL.md`. Determine actual supported project/plugin skill discovery from the target Hermes version before choosing paths. Do not put files in an invented `.hermes/skills` location or duplicate canonical skill content. This is deferred because hook compatibility does not establish skill-discovery compatibility.

B4. Optional read-only MCP: preserve other servers, use supported Hermes setup and consent mechanisms, and verify exact target registration. No MCP dependency for Release A.

B5. Optional direct-tool defense in depth: cover `write_file` and both patch modes, multiple files, absolute/relative paths, traversal, and symlinks. Terminal arbitrary-code protection requires a real enforcement boundary, not regexes. Keep approval policy changes separate.

B6. No native status bar, streaming transport receipt, or compositional output-transform promise. `/iaso status` and final text remain the baseline UX.

### Given/when/then acceptance examples

| ID | Given | When | Then |
|---|---|---|---|
| A-01 | Only nonempty CLAUDE.md exists | Install Hermes | CLAUDE text retained; no AGENTS shadow created |
| A-02 | Nonempty Hermes and Claude files exist | Install | Only the selected Hermes file receives the block |
| A-03 | Empty Hermes file and nonempty CLAUDE exist | Install | Select CLAUDE, matching fallback semantics |
| A-04 | Claude context has a block | Uninstall Hermes | Keep it and explain conservative ownership |
| A-05 | Plugin files and discovery flag exist | Status | Installed reported; runtime activation still unverified |
| A-06 | Plugin belongs to repo A; process cwd is repo B | Prompt callback | Only repo A receives the hook payload |
| A-07 | Generated plugin root lacks .iaso | Any event | No subprocess; empty adapter output |
| A-08 | No session-start observer fired | First parent prompt | One brief plus one prompt; later prompt gets no duplicate brief |
| A-09 | Explicit parent_session_id | Prompt and later callbacks | No owner prompt or summary events for child |
| A-10 | Other transform wins or reply is interrupted | Settlement | Missing summary is marked unseen |
| B-01 | Cron message without parent metadata | Provenance validation | Do not certify it as owner input |
| B-02 | Two desktop projects share a process | Runtime routing validation | No cross-project writes; otherwise no global enablement |

## 3. Repository guide and execution rules

Read before editing:

- `CLAUDE.md`, `pyproject.toml`, `docs/hosts.md`, `docs/specs/sp4-hosts-mcp.md`.
- `src/iaso/hosts/common.py`: shared install helpers, instruction block, context selection.
- `src/iaso/hosts/hermes/install.py`: rendering, install, status, uninstall.
- `src/iaso/hosts/hermes/templates/plugin.py`: generated plugin source.
- `src/iaso/hosts/neutral.py`, `src/iaso/hosts/cli.py`: event bridge and bounded CLI execution.
- `tests/hosts/test_hermes.py`: `project`, `_fake_plugin`, FakeCtx, real-process smoke.
- `tests/hosts/test_conformance.py`: host-output equivalence.
- `src/iaso/approvals.py`: owner guard and prompt provenance; **do not change its semantics in A**.

Use a new implementation worktree after approval; do not reset, clean, or overwrite current untracked files. Planning observed untracked judgment logs, `.iaso/requirements/SR-099.md`, and `IDEA.md`; these are not your cleanup targets. Do not commit with `git add .`.

Commands below assume repository root and the existing interpreter:

```bash
PY='C:/coding/iaso/.venv/Scripts/python.exe'
```

If running in a worktree, ensure this interpreter imports that worktree, not the original editable checkout:

```bash
export PYTHONPATH="$PWD/src"
"$PY" -c 'import iaso; print(iaso.__file__)'
```

Expected: a path inside the implementation worktree. Stop if not.

Do not run live LLM calls, enable plugins in the owner's real profile, or spend tokens without explicit permission. Test subprocesses must use temporary repositories and homes. The phase-A implementation stays within the file allowlist below, plus proposed requirement/test-map records created through the existing Iaso workflow after implementation approval.

## 4. Step-by-step implementation tasks

Each numbered substep is a separate focused action, approximately 2–5 minutes; a work package includes several such steps. Do not pretend a whole runtime investigation is a five-minute task. Every code package is RED → GREEN → targeted regression → commit. Expected outcomes below are requirements, not test results already obtained.

### Task 0 — establish baseline and requirement boundary

**Files:** read-only baseline; after approval record the implementation scope through Iaso, separate from assessment SR-099.

0.1 Inspect `git status --short`, `git branch --show-current`, and `git worktree list`. Select a new worktree/branch without touching the current branch.

0.2 Run focused baseline:

```bash
"$PY" -m pytest tests/hosts/test_hermes.py tests/hosts/test_conformance.py -q
```

Expected: pass. Any failure is a baseline blocker to diagnose before changes; do not assume the previously reported count remains current.

0.3 Reproduce the broader baseline:

```bash
"$PY" -m pytest tests/hosts tests/host tests/mcp/test_mcp_install.py tests/mcp/test_server.py -q
"$PY" -m pytest tests/host/test_latency.py::test_intent_lines_survive_cpu_contention -q
```

Save actual failure text outside tracked source. The known latency assertion may fail; record platform and unchanged baseline. Do not label it unrelated without comparing before/after.

0.4 Read `iaso new --help`, `iaso example --help`, and `iaso link --help`; create a proposed implementation requirement using A1–A8 and examples A-01–A-10. Relate it to SR-056 and SR-099. Do not auto-approve it. Link actual changed files and covering tests when implemented, not imagined future files. Commit only intentional requirement records as `docs: record bounded Hermes hardening scope`.

### Task 1 — preserve recognized existing project instructions

**Modify:** `src/iaso/hosts/common.py` (`context_file` only).
**Test:** `tests/hosts/test_hermes.py`.

1.1 Append these tests:

```python
@pytest.mark.parametrize("name", ["CLAUDE.md", "claude.md"])
def test_install_preserves_claude_context(project, name):
    (project / "AGENTS.md").unlink()
    context = project / name
    context.write_text("# Existing instructions\nKeep this rule.\n", "utf-8")
    hermes.install(project)
    assert not (project / "AGENTS.md").exists()
    assert context.read_text("utf-8").startswith("# Existing instructions\nKeep this rule.")
    assert "iaso:begin" in context.read_text("utf-8")


def test_empty_hermes_file_does_not_shadow_claude(project):
    (project / "AGENTS.md").unlink()
    (project / ".hermes.md").write_text(" \n", "utf-8")
    (project / "CLAUDE.md").write_text("# Claude rules\n", "utf-8")
    hermes.install(project)
    assert "iaso:begin" in (project / "CLAUDE.md").read_text("utf-8")
    assert (project / ".hermes.md").read_text("utf-8") == " \n"
```

1.2 RED:

```bash
"$PY" -m pytest tests/hosts/test_hermes.py -k 'preserves_claude_context or empty_hermes_file' -q
```

Expected before change: failures because AGENTS is created or empty Hermes file receives the block.

1.3 Replace `context_file` with:

```python
def context_file(root: Path, host: str) -> Path:
    """Select a nonempty root-local context without shadowing another host's rules."""
    if host == "hermes":
        for name in (".hermes.md", "HERMES.md", "AGENTS.md", "agents.md",
                     "CLAUDE.md", "claude.md"):
            candidate = root / name
            try:
                if candidate.read_text(encoding="utf-8").strip():
                    return candidate
            except (OSError, UnicodeDecodeError):
                continue
    return root / "AGENTS.md"
```

1.4 GREEN: repeat 1.2, then `"$PY" -m pytest tests/hosts -q`. The existing Hermes-precedence and other-host tests must still pass.

1.5 Commit:

```bash
git add src/iaso/hosts/common.py tests/hosts/test_hermes.py
git commit -m "fix: preserve existing Hermes fallback context"
```

### Task 2 — do not uninstall a possibly shared Claude block

**Modify:** `src/iaso/hosts/hermes/install.py` (`uninstall`).
**Test:** `tests/hosts/test_hermes.py`.

2.1 Append:

```python
def test_uninstall_keeps_claude_shared_block(project):
    (project / "AGENTS.md").unlink()
    path = project / "CLAUDE.md"
    path.write_text("# Claude rules\n", "utf-8")
    hermes.install(project)
    before = path.read_bytes()
    report = hermes.uninstall(project)
    assert path.read_bytes() == before
    assert any("ownership is shared or unknown" in line for line in report.lines)
    assert not (project / hermes.PLUGIN_DIR / "plugin.py").exists()
```

2.2 RED: `"$PY" -m pytest tests/hosts/test_hermes.py::test_uninstall_keeps_claude_shared_block -q`. Expected: block removed or preservation explanation missing.

2.3 Replace only the existing `remove_shared_block(...)` call in `uninstall` with:

```python
    context = context_file(root, HOST)
    if context.name.lower() == "claude.md":
        if has_block(context):
            report.lines.append(
                f"{rel(root, context)} block kept: Claude ownership is shared or unknown"
            )
    else:
        remove_shared_block(root, HOST, report, dry_run)
```

2.4 GREEN: repeat 2.2, then `"$PY" -m pytest tests/hosts/test_hermes.py -q`. Existing AGENTS round-trip and Pi-sharing behavior must stay green.

2.5 Commit only installer/test files: `git commit -m "fix: preserve shared Claude instructions on Hermes uninstall"` after explicit `git add` of those two paths.

### Task 3 — report activation as unverified, not inferred

**Modify:** `src/iaso/hosts/hermes/install.py` (`install` message, `status`).
**Test:** `tests/hosts/test_hermes.py`.

3.1 Replace `test_status_names_missing_marker` with the following stricter test; it intentionally changes the old assertion that the discovery flag proves activation:

```python
@pytest.mark.parametrize("discovery", ["0", "1"])
def test_status_does_not_infer_activation(project, monkeypatch, discovery):
    hermes.install(project)
    monkeypatch.setenv(hermes.ENABLE_ENV, discovery)
    out = "\n".join(hermes.status(project))
    assert "runtime activation: unverified" in out
    assert "hermes plugins enable iaso" in out
    assert "restart" in out.lower()
    assert NO_MARKER_LINE in out
    assert FALLBACK_PROMPT_LINE in out
```

3.2 RED: `"$PY" -m pytest tests/hosts/test_hermes.py -k does_not_infer_activation -q`. Expected: missing unverified/enablement messages.

3.3 Replace `status` completely:

```python
def status(root: Path) -> list[str]:
    root = Path(root)
    installed = all(_ours(root / PLUGIN_DIR / name) for name in FILES)
    enabled = os.environ.get(ENABLE_ENV, "").strip().lower() in ("1", "true", "yes", "on")
    where = context_file(root, HOST)
    lines = [
        "plugin files: " + (PLUGIN_DIR.as_posix() if installed else "not installed"),
        f"project discovery: {ENABLE_ENV}=" + ("1" if enabled else "not enabled"),
        "runtime activation: unverified (file presence is not callback evidence)",
        f"activation requires {ENABLE_ENV}=1 and `hermes plugins enable iaso`; "
        "restart Hermes after enabling, then verify a hook-delivered prompt",
        "instruction block: " + ("present" if has_block(where) else "missing")
        + f" ({rel(root, where)}, iaso turn start/end)",
    ]
    lines += marker_lines(False, "runtime activation unverified")
    lines += prompt_lines(root, False, "runtime activation unverified")
    return lines
```

Replace the final activation `report.lines.append` in `install` with:

```python
    report.lines.append(
        f"Activation requires {ENABLE_ENV}=1 and `hermes plugins enable iaso`; "
        "restart Hermes and verify callbacks. Installation does not enable trust or "
        "prove runtime activation; the context-file fallback remains available."
    )
    report.lines.append(
        "Support: project-bound event bridge; delegated children are excluded when "
        "parent metadata is supplied. Desktop/cron provenance is not yet certified."
    )
```

3.4 GREEN: repeat 3.2; run all `tests/hosts`. Update only assertions that equated discovery with runtime activation; do not weaken unrelated prompt provenance assertions.

3.5 Commit installer/test files as `fix: distinguish Hermes installation from runtime activation`.

### Task 4 — bind event execution to the installed project

**Modify:** `src/iaso/hosts/hermes/templates/plugin.py` and test helper `_fake_plugin` in `tests/hosts/test_hermes.py`.

4.1 First adjust `_fake_plugin` to render under the real install layout rather than a loose temporary directory. Replace:

```python
    plugin_dir = tmp_path / name
    plugin_dir.mkdir()
```

with:

```python
    plugin_dir = project / hermes.PLUGIN_DIR
    plugin_dir.mkdir(parents=True, exist_ok=True)
```

It still passes `name` into `_load_plugin` to isolate Python modules. Run existing tests; this fixture-only change should be green before adding a regression.

4.2 Append:

```python
def test_hook_root_is_not_process_cwd(project, tmp_path, monkeypatch):
    ctx, calls = _fake_plugin(project, tmp_path, monkeypatch, "iaso_root_bound")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    ctx.hooks["pre_llm_call"](session_id="root-bound", user_message="hello")
    logged = calls()
    assert logged
    assert all(Path(item["cwd"]).resolve() == project.resolve() for item in logged)


def test_uninstalled_template_does_not_spawn(tmp_path, monkeypatch):
    loose = tmp_path / "loose" / "plugins" / "iaso"
    loose.mkdir(parents=True)
    (loose / "plugin.py").write_text(hermes.render("plugin.py", ["iaso"]), "utf-8")
    plugin = _load_plugin(loose, "iaso_no_project")
    calls = []
    monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **kw: calls.append(kw))
    assert plugin._run("prompt", {"session_id": "s", "text": "hello"}) == plugin.EMPTY
    assert calls == []
```

4.3 RED: `"$PY" -m pytest tests/hosts/test_hermes.py -k 'hook_root or uninstalled_template' -q`. Expected: wrong cwd or subprocess attempted.

4.4 Add `from pathlib import Path` to the template imports. Add immediately after `EDIT_TOOLS`:

```python
PROJECT_ROOT = Path(__file__).resolve().parents[3]
```

At the start of `_run`, replace `cwd = os.getcwd()` with:

```python
    if not (PROJECT_ROOT / ".iaso").is_dir():
        return dict(EMPTY)
    cwd = str(PROJECT_ROOT)
```

Preserve JSON construction, timeout, exception handling, and subprocess argument arrays. Do not add `shell=True`.

4.5 GREEN: repeat 4.3, then all `tests/hosts/test_hermes.py`. `test_real_iaso_through_the_plugin` must still write its prompt only in the temporary project.

4.6 Commit template/test files as `fix: bind Hermes event subprocesses to installed project`.

**Boundary:** This solves process-cwd drift for one project plugin. It does not solve multiple globally registered copies or multi-project desktop routing; those remain Release B gates.

### Task 5 — obtain a brief when the session-start observer is absent

**Modify:** `src/iaso/hosts/hermes/templates/plugin.py`.
**Test:** `tests/hosts/test_hermes.py`.

5.1 Append:

```python
def test_first_prompt_lazily_loads_brief(project, tmp_path, monkeypatch):
    ctx, calls = _fake_plugin(project, tmp_path, monkeypatch, "iaso_lazy_brief")
    first = ctx.hooks["pre_llm_call"](session_id="lazy", user_message="hello")
    second = ctx.hooks["pre_llm_call"](session_id="lazy", user_message="again")
    assert first == {"context": "ctx session-start\nctx prompt"}
    assert second == {"context": "ctx prompt"}
    assert [x["event"] for x in calls()] == ["session-start", "prompt", "prompt"]
```

5.2 RED: `"$PY" -m pytest tests/hosts/test_hermes.py::test_first_prompt_lazily_loads_brief -q`. Expected: missing session-start context.

5.3 Add `_started: set[str] = set()` alongside existing state dictionaries. In `on_session_start`, after the existing child check and before `_run`, add:

```python
    if session in _started:
        return
    _started.add(session)
```

In `pre_llm_call`, after the existing child check and before `_settle`, add:

```python
    if session not in _started:
        on_session_start(**kwargs)
```

Keep child filtering before this branch. Update the existing `test_real_iaso_through_the_plugin` only if its assertion expects the exact context rather than a substring; do not remove its real prompt-log check.

5.4 GREEN: repeat 5.2, then the entire Hermes test module. Existing explicit session-start and child tests must not gain duplicate session-start calls.

5.5 Commit template/test files as `fix: initialize Hermes brief on first owner turn`.

**Tradeoff:** This preserves current in-process state lifetime and does not add session-finalization hooks. State cleanup is a follow-on if long-lived runtime testing demonstrates growth; do not add lifecycle machinery speculatively.

### Task 6 — remove unsupported claims and document skills/MCP boundaries

**Modify:** `src/iaso/hosts/hermes/templates/plugin.py` docstrings, `src/iaso/hosts/hermes/install.py` module docstring, `docs/hosts.md`. No behavior change in this task.

6.1 Replace claims that cron/background always has parent metadata with the exact narrower statement: `Sessions with parent_session_id are excluded; this does not certify provenance for every synthetic or scheduled turn.`

6.2 Add a Hermes support table to `docs/hosts.md` using sections 1 and 2 of this plan. State: CLI/project plugin bridge validated by tests; live activation requires explicit trust and enablement; desktop multi-project routing and cron provenance not certified; command injection outside CLI requires supported routing/grants; no native status bar.

6.3 Include exact installation instructions, explicitly owner-run, not installer side effects:

```bash
iaso hosts install hermes
# For a trusted project only; launch Hermes from this project:
export HERMES_ENABLE_PROJECT_PLUGINS=1
hermes plugins enable iaso
# Restart the intended Hermes process after enabling.
iaso hosts status hermes
```

Explain that the status command intentionally reports runtime activation as unverified. On Windows these commands are Git Bash syntax. Other shells need their equivalent environment assignment; do not present Bash as PowerShell.

6.4 Document the existing CLI fallback from `instruction_block`, including `turn start/end`, owner words, proposed intent, and unseen-summary limitations. Native `iaso` / `iaso-clarify` skills and MCP are follow-on tasks, not installed by Release A. Do not copy skill files to unverified discovery paths.

6.5 Verify with `git diff --check` and `"$PY" -m pytest tests/hosts -q`, then commit the explicit three files as `docs: define tested Hermes compatibility boundaries`.

### Task 7 — real-runtime registration gate and final regression

**No production changes unless an actual failure demands a separate RED/GREEN task.**

7.1 Run `hermes --version` and record actual output in the implementation report. Do not claim all future versions are compatible.

7.2 Run:

```bash
hermes plugins doctor src/iaso/hosts/hermes/templates --ci
```

Expected: exit 0, successful discovery/import/registration, six declared hooks. Doctor is a registration test; it deliberately does not prove the owner's actual plugin enablement. The loose template root guard must allow import and registration without invoking Iaso.

7.3 Run:

```bash
"$PY" -m pytest tests/hosts/test_hermes.py tests/hosts/test_conformance.py -q
"$PY" -m pytest tests/hosts tests/host tests/mcp/test_mcp_install.py tests/mcp/test_server.py -q
"$PY" -m pytest -q
git diff --check
git status --short
```

Expected: all relevant focused tests pass, no introduced regression, clean whitespace, only intended changes. Report actual counts, baseline failures, and runtime version. If the latency failure persists, report it as an unresolved acceptance limitation; do not call the full suite green.

7.4 Independent review must check: context preservation, shared-block uninstall, root binding, discovery-vs-activation wording, exact owner words, child filtering, and unchanged approval semantics. It must specifically reject any claim that PTY or marker defenses are tamper-proof.

7.5 Stop at Release A. Offer Release B runtime work explicitly; do not enable the real plugin merely because tests passed.

## 5. Release B investigation gates and handoff specification

These are bounded read-only investigations before a second implementation plan. They are not missing details the implementer is permitted to guess.

### Gate B1 — owner provenance and session/root routing

Inspect the target runtime's producers of `pre_llm_call`, `on_session_start`, `post_tool_call`, `pre_verify`, `transform_llm_output`, and `post_llm_call`, including cron and delegated execution. Record for each: exact kwargs, emission frequency, whether the text is a human message or synthetic text, and how cwd/workspace is resolved. Use a no-network test harness around the real PluginManager in a temporary home; do not call private `_doctor_runtime` as a production API.

Acceptance artifacts for the next plan:

- An exact hook payload fixture per surface, with credentials/user content removed.
- Actual source/version references for trusted provenance and workspace identity.
- Tests interleaving two project sessions and a parentless scheduled run.
- A design that either routes/excludes correctly or stays explicitly unsupported.

If no supported host metadata exists, ask for a narrow Hermes core extension or retain fallback. Do not invent `cwd`, `origin`, or `is_owner` kwargs not supplied by runtime.

### Gate B2 — native skills

Inspect current Hermes official docs and runtime discovery for plugin/project skills. Produce an exact supported install layout plus lifecycle: install, idempotent update, foreign preservation, dry-run, uninstall. Only then extract shared canonical source out of the Claude template location if necessary; preserve Claude generated skill content byte-for-byte where behavior is unchanged. The neutral API's existing delegation is not a reason to refactor all adapters.

### Gate B3 — approval threat model

Separate accidental agent self-approval from an adversarial shell with write permission. List PTY, marker removal, direct file writes, `execute_code`, terminal subprocesses, and delegation. Decide with the owner whether a real out-of-band approval boundary is required. Do not amend the approval contract as an incidental adapter change.

### Gate B4 — latency failure

Reproduce `tests/host/test_latency.py::test_intent_lines_survive_cpu_contention` unchanged. Inspect `src/iaso/hosts/claude_code/hookio.py` and the stop handler to identify whether the outer watchdog can fire before intent lines are kept. Supply timing evidence and a deterministic regression before changing shared hook budgets or output ordering. This requires a separate small fix plan; it is not permission for performance refactoring.

## 6. Verification meaning and release criteria

| Evidence | Proves | Does not prove |
|---|---|---|
| FakeCtx tests | Local event mapping and ordering for supplied payloads | Runtime payload completeness, scheduling, or platform routing |
| Real Iaso subprocess test | Prompt persists with hook provenance through actual Iaso CLI | That source was truly human, or that no other plugin intercepts |
| Conformance test | Same neutral event sequence has equivalent semantic outputs | Equivalent host UX or lifecycle frequency |
| Plugin Doctor | Runtime manifest/import/registration compatibility | Live activation, callbacks, delivery, or sandbox security |
| Cwd regression | Project-local plugin does not follow process cwd drift | Global/multi-project session isolation |
| Full pytest | Repository regressions covered by existing tests | Paid/live model behavior or transport delivery |

Release A is complete only when its code/tests/docs are committed intentionally, focused tests pass, broad-suite results are reported honestly, and independent review accepts the stated limited support boundary. It is **not** full Claude parity and must not be marketed as such.

## 7. File allowlist

Release A production/test/docs:

- `src/iaso/hosts/common.py`
- `src/iaso/hosts/hermes/install.py`
- `src/iaso/hosts/hermes/templates/plugin.py`
- `tests/hosts/test_hermes.py`
- `docs/hosts.md`
- Proposed `.iaso/` requirement/example/test-map changes through repository workflow after approval.

Do not modify Hermes's installed source, real Hermes config, `.env`, credentials, `src/iaso/approvals.py`, MCP behavior, other adapters, or shared latency logic in Release A. A regression exposing a required sibling fix must be reported and scoped before exceeding this allowlist.

## 8. Risks, tradeoffs, and open decisions

- Conservative status may say unverified even when hooks are working. This is intentional; a later observed-runtime capability report can improve it without lying today.
- Preserving shared Claude blocks on uninstall leaves fallback text. This is safer than erasing another adapter's instructions; ownership migration is not justified for this small release.
- Context selection is root-local, while Hermes can walk ancestors and load nested context. Installing from repo root is the documented supported path; nested contexts remain a limitation.
- Root binding fixes cwd drift but not message provenance or simultaneous plugin copies. No global distribution until Gate B1 passes.
- Asynchronous edit subprocesses and synchronous hook timeouts remain existing behavior. A callback timeout from the prior investigation is not proof of its cause; do not tune timeouts without tracing.
- Summary presence in returned text is not proof the owner read it. Existing unseen handling is useful but cannot provide transport receipts.
- Native skills, MCP modernization, direct-tool protection, and desktop certification are intentionally separated to avoid a misleading one-shot parity claim.
- No numerical readiness percentage or fixed delivery estimate is warranted before real-runtime gates. Release A has concrete bounded edits; Release B depends on what the runtime actually exposes.

## 9. Handoff checklist

- [ ] Fresh baseline captured; no untracked owner data staged.
- [ ] Proposed implementation intent recorded separately from SR-099 assessment.
- [ ] Each code task demonstrated RED and GREEN.
- [ ] Existing Claude/Pi/Codex tests remain unchanged in meaning.
- [ ] Runtime version and Doctor output captured.
- [ ] Broader/full suite results reported, including latency failure if present.
- [ ] Independent reviewer checked safety and support claims.
- [ ] No real profile enabled, no secrets read, no live LLM calls made.
- [ ] Owner chooses whether to proceed with Release B gates.
