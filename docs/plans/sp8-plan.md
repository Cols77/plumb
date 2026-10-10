# SP8 plan: the hooks fix, then intent by exception in four lanes

Implements `docs/specs/sp8-intent-by-exception.md` ("spec 4.1" means section 4.1 of the sp8
spec) in the order the owner set (DEC-031, 3A): **the hooks fix first, then SP8**, then the
everyday loop's requirements are confirmed and verified, then SP7 resumes. The hooks fix is
the owner's addition of 10 Oct: SR-111 (drift caught at the edit that causes it, the turn held
open until resolved), SR-110 (tests selected by the functions they execute, run in parallel)
and bringing session start under its budget cold (2.1 s cold and 1.4 s warm today, against
1.4 s). SP8 proper is four lanes with disjoint files and a contracts phase done alone first.
Records: `FEAT-008`, `INT-028` to `INT-030`, `SR-101` to `SR-108`, `SR-110`, `SR-111`,
`DEC-027` to `DEC-031`, all proposed; agents never approve them.

| Phase | Lanes | SRs | Spec |
|---|---|---|---|
| H0. Config keys | coordinator, alone, a tiny step | none (the two phase H config keys) | none |
| H. Hooks first | STALE, SELECT, START (parallel) | SR-111; SR-110; SR-014 (budget) | none (owner's 10 Oct requests) |
| C. Contracts | coordinator, alone | none (frozen interfaces) | 4.4, 5, 10 |
| L. SP8 lanes | ENGINE, READ, JUDGE, SHOW (parallel) | SR-104, SR-101, SR-102 + SR-105 + SR-106 + SR-107, SR-103 + SR-108 | 4 to 9 |
| I. Integrate, R. Review | coordinator, verifiers | all | 9.3, 12 |

**Status at 10 Oct.** Phase H0 (the two config keys, `56a165f`) and phase C (contracts, file formats, stubs,
call sites and test helpers, `a6e1ace`, plus the route set in `f3e8198`) are already on `main`; they landed before
the phase H lanes. That order is safe because the stale-card adapter of phase C only reads STALE's
`stale_cards.json` and does nothing while the file is absent; the phase C gate's two STALE test files
(`tests/host/test_stop_stale.py`, and the adapter test's fixture use of it) are checked again at the H gate. What remains: the
phase H lanes (STALE, SELECT, START), then the four phase L lanes, integrate and review, in the order of the
table above with H0 and C marked done.

**Spec 11 says "any change to how tests are selected or run" is out of scope of SP8.** SR-110
is therefore not an SP8 lane: it is a phase H lane, recorded here because the owner asked for
it first (DEC-031's hooks fix). Nothing in phase L changes selection or the runner except the
progress call sites of SHOW (SR-108), which only report.

**SP7 stays frozen (DEC-031).** No lane edits an SP7-only file: `src/plumb/mod/**`,
`src/plumb/plugin/**`, `plugin/**`, `.claude-plugin/**`, `owner_actions.py`, `owner_cli.py`,
`launcher.py`, `guard.py`, `present/answers.py`, `docs/owner-matrix.md`, `scripts/build_plugin.py`,
and the SP7 branches (`sp7/contracts`, `sp7/spec-review`). The shared files SP8 must edit
(`stop.py`, `prompt.py`, `statusline.py`, `confirm.py`, `approvals.py`, `install.py`) exist on
`main` today and are listed in section 3.1 with one owner each. The SP8 gate's pre-tool hook
is its own module (`hosts/claude_code/pretool.py`), which SP7's PLUGIN lane later adopts
(spec 10), not `guard.py`. Names SP7 reserves (`Gap`, `ShownItem`, `InReplyTo`, `ModCard`) are
not used by SP8's contracts.

Binding rules for every agent (from the work order and the owner's standing rules):

1. **Python and tests.** Run Python and tests with `.venv/Scripts/python.exe` (in a worktree,
   `uv sync` once first so `.venv` exists). Run tests as `.venv/Scripts/python.exe -m pytest
   <files> -q -p no:cacheprovider`, never `uv run pytest`. No whole suite, no whole test
   directory: validate with plumb's own selection, `.venv/Scripts/python.exe -m plumb tests run
   --paths <the files you changed> --budget 900`, plus the tests you wrote.
2. **Test first.** A failing test, seen red, then the change. Mark every new test
   `pytest.mark.sr("SR-0xx")`. Never rewrite an existing test to make it pass. Before editing a
   file, run the tests `.plumb/test_map.txt` lists for it (`grep "^<path> ->" .plumb/test_map.txt`).
   A test that pins behaviour a requirement now removes is not edited by a lane: the lane stops
   that item and reports it (section 15, question 1).
3. **Never approve anything.** No lane runs `plumb approve`, `revoke`, `relay`, `triage
   --approve`, `config auto-approve`, `conflict choose`, and none relays a choice the owner did
   not give. Records change only through `.venv/Scripts/python.exe -m plumb capture --file
   <json> --prompt <digest>` (digest: the 16-hex prefix of the last entry's digest in
   `.plumb/session/prompts.jsonl`; in a worktree copy that file into its `.plumb/session/`
   first). Lanes create no records; a lane that needs one stops that item and asks the
   coordinator.
4. **Owner-visible text is at the owner's level**: titles instead of IDs, no shell commands, no
   plumb internals ("job", "dispatcher", "hash", "worker"). Every new owner string lives in
   `plumb.present.owner_text` (constants) and passes its two scanners. Text meant for the
   agent (hook context, refusal reasons) may name commands.
5. **Commits** carry `SR: SR-###` trailers for the requirements served and the line
   `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Another session (plumb-66) also
   commits on `main`: before landing, merge or rebase onto the current `main`; never
   force-push or reset `main`. Lane merges that plumb's merge hold stops are recorded after the
   coordinator verified their content with the focused set, using `git -c plumb.mergeHold=false`.
6. **Process safety.** Never kill a process you did not start. The machine has 2 cores: at most
   two workers (plumb's own selection already runs `verify.workers: 2`); direct pytest runs
   use no `-n`.
7. **No fallback, no second route** (INT-029, spec 3.2): code that interprets the owner's words
   calls the configured model; when it fails the result is an error and nothing is confirmed,
   settled or rejected. A test asserts this for every kind of job.
8. `C:/coding/pi-agent-factory` is out of scope: never read, write or run anything there.

## 1. Shape of the work

| Phase | What | Who | Gate before the next phase |
|---|---|---|---|
| H0. Config keys | The two config keys the phase H lanes read, `hooks.stale_holds_max` (default 3) and `verify.coverage` (`auto`, or `off`), added to `config.py` with their test, committed on `main` before any phase H worktree exists, so no phase H lane edits `config.py` | coordinator, alone, on `main` | H0 gate (3.3) |
| H. Hooks first | SR-111 (STALE), SR-110 (SELECT), session start cold (START), each in its own worktree | three lane agents | each lane's gate (3.4), then the H gate (3.3) on `main` |
| C. Contracts | Every cross-lane data class, file format, dispatcher and kind interface, stub, call site, config key, route and test helper (3.2), so the lanes start against real interfaces | coordinator, alone, on `main` | C gate (3.3) |
| L. Lanes | ENGINE, READ, JUDGE, SHOW in parallel, each in its own worktree (sections 8 to 11) | four lane agents | lane gate (3.4) at each merge point |
| I. Integrate | Merge the lanes, the end-to-end flows, the evaluation set against the configured model, the targeted validation, docs (section 12) | coordinator, on `main` | 12.4 |
| R. Review | Verifiers against the owner's words (section 13) | review agents; coordinator fixes | no finding that contradicts the owner's words left open |

Phase H goes first and alone because the lanes of phase L edit the same hooks (`prompt.py`,
`stop.py`, `session_start.py`, `statusline.py`) and because the gate of spec 4.3 needs hooks
that run within their budget. Phase H0 (two config keys) precedes the phase H worktrees, so
the three phase H lanes share no file. Phase C starts only after the H gate passes on `main`.
File ownership is per phase: a file may belong to one lane in phase H and to another in phase
L (for example `stop.py`, `verify/runner.py`), because the phases never overlap.

Orchestration uses the host's native mechanism (the user's global rule): in Claude Code, the
`Workflow` tool (phase H as one `parallel()` of three lane pipelines, then phase C as one agent
step, phase L as a `parallel()` of four lane pipelines, phases I and R as gated steps; each
step carries the gate that must pass before the next begins; `agent()` for the single
subagents). The `workflow-authoring` skill is loaded before the script is written. Starting it
needs the owner's opt-in where Claude Code asks for it; this plan does not grant it. Hosts
without a workflow tool run the same phases sequentially.

## 2. Conventions for every agent

- Repository `C:/coding/plumb`. Phases C and I run on `main`. Lanes work in worktrees
  `C:/coding/plumb-wt/<name>` on branches: `hooks-stale` (`hooks/stale`), `hooks-select`
  (`hooks/select`), `hooks-start` (`hooks/start`), then `sp8-engine`, `sp8-read`, `sp8-judge`,
  `sp8-show` (`sp8/engine`, ...), created from `main` after the previous phase's gate, then
  `uv sync` inside the worktree. `main` may hold untracked files of another session (`IDEA.md`,
  `.plumb/intents/INT-030.md`, log entries) when a lane starts; lanes never touch them, and the
  coordinator commits with path-limited commits.
- Each lane starts with `.venv/Scripts/python.exe -m plumb brief`, `... -m plumb status` and
  `... -m plumb show <its SRs>` and keeps the output as context.
- Test files are named in the task tables; a lane creates them red first. Tests that need git
  use a temporary repository (`tests/gitrepo.py`, the `repo` fixture), never the plumb
  repository. Tests never call a real model: they use `tests/understand/fakes.py` (3.2, item 9).
  Tests that need the user's home point it into `tmp_path` (the conftest does this).
- Timing assertions use the minimum of several runs against the budget times 0.9, as
  `tests/host/test_hook_perf.py` does, never one wall-clock run (a loaded machine slows single
  runs).
- `SR:` trailers: each commit names the SRs of the task rows it implements. Before committing a
  new module, link it: `plumb link SR-0xx implemented_by <path>` and `verified_by <test file>
  --example EX-n` (lanes may run `plumb link` and `plumb repin` on their own SRs; those never
  confirm anything), then `plumb validate`, `plumb drift` and `plumb claims check --range
  main..HEAD`.
- Lanes never edit another lane's files (3.1). A needed contract change stops that item; the
  lane asks the coordinator and moves to its next item.
- Medium and low findings, and anything unfinished with its state, go under the lane's own
  heading at the end of `docs/followups.md` (`## SP8 lane ENGINE (2026-10-..)`).

## 3. Files, contracts and gates

### 3.1 Ownership (disjoint)

Phase H lanes (paths relative to `src/plumb/` unless they start with `tests/`, `docs/` or are
root files):

| Owner | Paths |
|---|---|
| STALE | `stale.py` (new), `hosts/claude_code/edit_check.py` (new; `post_edit.py` stays untouched, async touch tracking), `hosts/claude_code/hookio.py` (the `additional_context` output form), `hosts/claude_code/cli.py` (the `edit-check` route), `hosts/claude_code/install.py` (the new hook entry), `hosts/claude_code/stop.py` (the hold-open and the stale lines), `hosts/claude_code/prompt.py` (the turn baseline write only), `capture/capture.py` (the reworded-record line of `result_lines` only), `links.py`, `commands.py` (`repin --after-tests` only), `cli.py` (`stale` route), `present/owner_text.py` (the stale-card strings only); `tests/core/test_stale.py`, `tests/core/test_stale_resolve.py`, `tests/host/test_edit_check.py`, `tests/host/test_stop_stale.py` (new) |
| SELECT | `verify/**` (all files), `contracts.py` (`Selection.unrecorded`, `SelectionReason` gains `"function"`), `pyproject.toml` and `uv.lock` (the `coverage` dev dependency), `tests/verify/**` (new files `test_funcmap.py`, `test_cov_record.py`, `test_select_functions.py`, `test_runner_workers.py`). The `api.py` that SELECT's tasks edit is `verify/api.py` (inside `verify/**`); the root `src/plumb/api.py` is START's alone |
| START | `hosts/claude_code/session_start.py`, `hosts/claude_code/providers.py`, `hosts/claude_code/hygiene.py`, `awareness/turn.py`, `awareness/scan.py`, `awareness/inflight.py` (cold-path reads only), `capture/triage.py` (`triage_offer` cold gating only), `api.py`, `hashing.py`, `model.py`, `store.py`, `present/delta.py` (import weight only); `tests/host/test_session_cold.py` (new), `tests/host/test_session_start.py` and `tests/host/test_hook_perf.py` (new cases appended, no existing case edited) |
| Any lane, append only | `docs/followups.md` (own heading) |

No path is in two rows of this table. The two config keys are the coordinator's (H0, below), the
root `api.py` is START's, `verify/api.py` is SELECT's, `present/owner_text.py` is STALE's (stale
card strings only), and `contracts.py` is SELECT's. Each lane's gate ends with `git diff
--name-only main...HEAD`, every path in its own row.

`contracts.py` is SELECT's in phase H (`Selection.unrecorded` and the `"function"` reason only); if START's profile shows the import cost of
`contracts.py` itself dominates (it is 58 ms self time in an import trace today), START
reports it and the coordinator makes the change after SELECT merges.

Phase H0 (coordinator, before the phase H worktrees): `config.py` (`hooks.stale_holds_max: 3`,
`verify.coverage: auto`) and `tests/core/test_config_h0.py` (new: both defaults, and a
`.plumb/config.yaml` override of each, loaded as `tests/core/test_primitives.py` loads config).

Phase C (coordinator): `contracts.py`, `config.py`, `cli.py`, `log.py` (the worker-token check,
3.2 item 3), `confirm.py` (the
re-check registry call only), `hosts/claude_code/hookio.py` (the job guard), the one-line call
sites in `prompt.py`, `stop.py`, `statusline.py`, `capture/capture.py`, `capture/cli.py`;
`understand/**` skeleton (`__init__`, `cli`, `hooks`, `cardstore`, `effects`, `kinds`, `recheck`, stub modules), `progress.py` skeleton, `validate.py` (one call site), `tests/understand/{fakes,harness,
test_contracts,test_status_settled,test_stale_card_adapter}.py`, `tests/core/test_log_worker_token.py`, `src/plumb/understand/evalrun.py`, `.plumb/**`,
`CLAUDE.md`, `docs/plans/**`, `docs/specs/**`, `docs/concept.md`.

Phase L:

| Owner | Paths (under `src/plumb/` unless noted) |
|---|---|
| ENGINE | `understand/jobs.py`, `queue.py`, `worker.py`, `ledger.py`, `schema.py`, `dispatch/__init__.py`, `dispatch/claude_code.py`, `dispatch/hermes.py`, `dispatch/openrouter.py`, `agents/__init__.py` (the loader), `cmd_worker.py`; `tests/understand/test_jobs.py`, `test_queue.py`, `test_worker.py`, `test_worker_authority.py`, `test_dispatch_claude.py`, `test_dispatch_hermes.py`, `test_dispatch_openrouter.py`, `test_failures.py`, `test_hooks_in_job.py`, `test_progress_worker.py` |
| READ | `understand/read.py`, `typed.py`, `threshold.py`, `recheck_words.py`, `agents/read.md`, `schemas/read.json`, `evalset/read.json`; `approvals.py`, `confirm.py` (word rules out), `commands.py` (`relay`, `approve`, `revoke` verbs), `hosts/claude_code/prompt.py`, `boundary/glance.py`, `mergedriver/conflicts.py`, `mergedriver/cli.py`, `awareness/answer.py`, `present/confirm.py`, `present/cli.py` (the `confirm` verb), `hosts/claude_code/templates/plumb-command.md`, `hosts/claude_code/templates/skills/plumb/SKILL.md`; `tests/understand/test_read_job.py`, `test_read_apply.py`, `test_read_cards.py`, `test_typed.py`, `test_threshold.py`, `test_owner_only.py`, `test_relay_terminal.py`, `test_retire_word_rules.py` |
| JUDGE | `understand/judge.py`, `premise.py`, `trial.py`, `settle.py`, `backlog.py`, `summary.py`, `cards.py`, `recheck_settled.py`, `cmd_settle.py`, `agents/judge.md`, `schemas/judge.json`, `evalset/judge.json`; `capture/capture.py`, `capture/calibrate.py`, `capture/autoapprove.py`, `capture/triage.py`, `capture/cli.py`, `capture/jevcmd.py`, `hosts/claude_code/stop.py`, `present/owner_text.py`; `tests/understand/test_judge_job.py`, `test_premise.py`, `test_trial.py`, `test_settle.py`, `test_settle_switch.py`, `test_summary.py`, `test_backlog.py`, `test_recheck_settled.py` |
| SHOW | `understand/clarify.py`, `gate.py`, `cmd_clarify.py`, `cmd_go.py`, `agents/clarify.md`, `schemas/clarify.json`, `evalset/clarify.json`, `progress.py`; `hosts/claude_code/pretool.py` (new), `hosts/claude_code/templates/gate.sh` (new), `hosts/claude_code/install.py`, `hosts/claude_code/cli.py` (the `pre-tool` route), `hosts/claude_code/statusline.py`, `hosts/claude_code/snapshot.py`, `capture/clarify.py`, `hosts/claude_code/templates/skills/plumb-clarify/SKILL.md`, `verify/runner.py`, `verify/pytest_plugin.py`, `verify/testmap.py`, `verify/funcmap.py`, `verify/cov_plugin.py` (progress call sites only), `boundary/fullrun.py`, `boundary/cli.py`, `importer/cli.py`, `align.py`; `tests/understand/test_clarify_job.py`, `test_gate.py`, `test_clarify_wait.py`, `test_clarify_release.py`, `test_pretool.py`, `test_progress.py`, `test_progress_sites.py`, `test_statusline_progress.py` |
| Any lane, append only | `docs/followups.md` (own heading) |

Data files have one writer each: `.plumb/session/<id>/jobs/*` by the queue (hook or `plumb
clarify`), `results/*` and `ran/*` by the worker only, `cards.json` by `understand.cardstore`
(frozen in phase C), `gate` by `understand.gate` (SHOW), `progress` by `progress.Reporter`; the
committed log kinds by their lane's module (3.2, item 3).

### 3.2 Phase C: what the coordinator writes before any lane starts

1. **`contracts.py`.** Frozen data classes with defaults on every field: `Job`, `JobError`,
   `JobResult`, `ReadItem`, `ReadCard`, `ReaderEntry`, `JudgeVerdict`, `ClarifyQuestion`,
   `ClarifyAnswer`, `CardState`, `Applied`, `GateState`, `SettleState`, `Progress`;
   `CardKind` (`clarify`, `trial`, `backlog`, `beyond`, `contradicts`, `couldnt_check`,
   `show_first`, `settle_offer`, `settled_item`, `link`, `stale_link`); the `Dispatcher` and `JobKind`
   protocols (below); `RecordStatus` gains `settled`, counted as confirmed everywhere and listed
   apart (see item 6).
2. **File formats** (all JSON, UTF-8, written atomically, one writer each).
   - Job `.plumb/session/<id>/jobs/<job-id>.json`: `{"v":1,"id","kind":"read|judge|clarify",
     "session","created","schema":"read.v1","needs":null|"<job-id>","inputs":{...},
     "inputs_digest":"sha256:..."}`. `job-id` = `<kind>-` plus the first 16 hex of the sha256 of
     the canonical JSON of `(kind, schema, inputs, needs)`, so the same inputs give the same id
     and a retried hook never queues twice. `needs` is the id of one job that must have been
     applied first (only a clarify job sets it, to the read job of the same message; `Job.needs`
     defaults to None). The worker runs a job only when its `needs` job has an `ok` result
     (the order rule of 3.2 item 2a). Inputs by kind: read `{"message":{"digest","text"},"shown":[{"id","hash",
     "text"}],"cards":[{"card","question","resolutions"}]}`; judge `{"records":[{"id","hash",
     "kind","text","assumptions","premise":{"messages":[{"digest","text"}],"question","parent"},
     "related":[{"id","status","text"}]}]}`; clarify `{"message":{"digest","text"},"touched":
     [{"id","status","text"}],"answered":[...]}`.
   - Result `.../results/<job-id>.json`: `{"v":1,"job","status":"ok|error","answer":{...}|null,
     "error":{"step","message"}|null,"model","dispatcher","started","finished","run_s"}`. It is
     a record of what the worker did, never an input: nothing reads it to confirm anything.
   - Ledger `.../ran/<job-id>`: written only by the worker, one line (pid, time). A result or job
     file with no ledger entry was not written by the worker and is reported (`job-note`).
   - Cards `.plumb/session/<id>/cards.json`: the open `CardState` list (kind, topic, issue,
     evidence, resolutions, questions with ids, status, answers, `owner_only`, turn).
   - Gate `.plumb/session/<id>/gate`: `{"state":"closed|open","message_digest","reason",
     "since"}`; progress `.plumb/session/<id>/progress` (worker) and `.plumb/session/cli/
     progress` (an execution started from a shell that knows no session): `{"step","done",
     "total","started","updated","state":"running|failed|done","kind"}`. The status line reads
     both (assumption: one execution per file at a time).
   - Worker lock `.plumb/session/<id>/worker.lock`: `{"pid","heartbeat","token"}` (the token is
     32 random hex characters made when the worker starts and given to that process alone as
     `PLUMB_WORKER`; the dispatcher's child process receives only `PLUMB_JOB`); a stale lock is
     taken over.
2a. **Order of jobs.** A message's clarify job (SR-103 EX-9, spec 4.3) has the message's read
   job as `needs`, so the card the owner just answered is applied before the clarifier runs and
   is not asked twice. The rule lives in the worker, which knows nothing about kinds: it skips a
   queued job whose `needs` job has no result yet, runs the `needs` job first when it is queued,
   and calls `recompute` only after the `needs` job was applied, so a clarify job's `answered`
   input is recomputed from the logs and `cardstore` as the read job left them (the queued file
   carries none). A `needs` job whose result is an error makes the dependent job an error result
   with step "needs" and no model call (nothing is built from stale inputs; the "couldn't check"
   card of S3 covers it, and `queue.retry_failed` re-queues both, the read job first). A `needs`
   id with no job file and no result is treated as satisfied and noted (`job-note`).
3. **Committed log kinds** (one file per entry; `log.py` changes only to accept them and for the worker-token check below):
   `premise` `{digest,text,session,used_by[]}`; `verdict` `{job,id,hash,verdict,beyond,
   contradicts,score,model,premise_digest}` (score = confidence for `supported`, 0 otherwise);
   `read-entry` `{job,id,hash,answer,confidence,evidence,message_digest}` (calibration labels);
   `approval` with `by: owner-words` `{prompt_digest,evidence,job,confidence,label?}` and `by:
   settled` `{job,model,score,premise_digest,calibration}`; `revocation` with `by: undone`;
   `settle-config` `{kind,on,via:typed|button|calibration,calibration}` (owner-only for
   `typed|button`); `trial` `{card,items,answers}`; `eval-run` `{model,prompt_digest,cases,
   passed,false_gap_rate}`; `gate` `{digest,state,by,reason}`; `job-note` `{kind,job,detail}`.
   **The worker token is checked in `log.py`, in phase C**, so no lane needs a file it does not
   own: `log.worker_token_problem(root, session, by)` returns a reason unless `PLUMB_WORKER` in
   the environment equals the `token` of that session's `worker.lock`, and the writer of an
   `approval` with `by: owner-words` or `by: settled` refuses (`LogError`) on that reason
   (tamper-evident, not tamper-proof, as in SP7 5.7). `undone` is not written by the worker but
   by the owner's typed command or button (J6); its guard is the typed-command check of
   `recheck_settled` (prompt digest in the log), not the token. ENGINE only creates the lock and
   the environment variable (E3); READ's and JUDGE's tests use the helper `as_worker(root,
   session)` of `tests/understand/fakes.py`. `tests/core/test_log_worker_token.py` (coordinator,
   a hand-written lock): `::test_owner_words_refused_without_token`, `::test_settled_refused_with_wrong_token`,
   `::test_accepted_with_matching_token`, `::test_other_by_values_unchanged`.
4. **Interfaces.**
   ```python
   class Dispatcher(Protocol):
       name: str
       def available(self) -> str | None: ...        # None = ready, else a plain reason
       def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
               on_step: Callable[[str], None]) -> Mapping[str, Any]: ...  # raises DispatchError(step, message)
   class JobKind(Protocol):
       kind: str; schema: Mapping[str, Any]
       def build(self, core, session: str, **context) -> Job | None: ...   # queue side, from the logs
       # context may carry after=<job id>: the read job of the same message (clarify sets Job.needs)
       def recompute(self, core, job: Job) -> Mapping[str, Any] | None: ... # worker side, from the logs only
       def apply(self, core, job: Job, answer: Mapping[str, Any]) -> Applied: ...  # in memory
       def describe(self, job: Job) -> str: ...                            # the plain-words step
   ```
   `understand.dispatch.configured(core)` returns exactly one dispatcher (`understand.dispatch`
   config: `auto` picks `claude-code` under Claude Code, `hermes` under Hermes, else an error;
   `openrouter` only when set). `understand.kinds.KINDS` maps `read`, `judge`, `clarify` to
   `plumb.understand.{read,judge,clarify}`. `understand.effects.register(card_kind, handler)`
   is the registry of what an answered card does (READ applies answers and calls the handler of
   the card's kind; JUDGE registers `trial`, `backlog`, `beyond`, `contradicts`; SHOW registers
   `clarify`, `couldnt_check`; READ registers `show_first`). `understand.recheck.problem(entry,
   core)` dispatches by `by` value to `recheck_words` (READ) and `recheck_settled` (JUDGE).
5. **Stubs with the final signatures**, each keeping today's behaviour: every `JobKind.build`
   returns None; `queue.enqueue`, `worker.start_detached` do nothing; `dispatch.configured`
   raises `NoModel("no model configured")`; `summary.stop_parts(ctx, core, turn)` returns empty
   parts; `judge.queue_for_capture`, `premise.commit` do nothing; `gate.is_closed` returns False;
   `recheck.problem` returns `"not available in this build"` for `owner-words`, `settled`,
   `undone` (so a hand-written entry of those kinds is never accepted); `cmd_*` print "not
   available in this build" (exit 2); `progress.Reporter` writes its file only (no rendering,
   no throttle: SHOW's), `progress.status_text(root, session)` returns the plain step text.
6. **Call sites, wired once, so lanes edit only their own modules.** `hookio.run_hook` returns
   at once, printing nothing and queuing nothing, when `PLUMB_JOB` is set (SR-104 EX-2).
   `prompt.py` calls `understand.hooks.on_prompt(ctx, core, entry)` after logging the prompt
   (it calls, in order, `read.on_prompt`, which returns the id of the read job it queued or
   None, `clarify.on_prompt(after=<that id>)`, which sets the clarify job's `needs`, and
   `queue.retry_failed`, and returns agent-facing lines, in a try/except: a failing understand layer never blocks the
   prompt); `validate.py` reports `understand.premise.problems(core)` and `gate.problems(core)`
   (stubs: none). `stop.py` calls `understand.summary.stop_parts` and places
   its three parts in the order of SR-105 (confirmations, settled line, cards) through the delta
   emitter. `capture.capture` calls `judge.queue_for_capture` and `premise.commit` after
   writing. `statusline.py` appends `progress.status_text`. `confirm.entry_problem` calls
   `recheck.problem` for the three new `by` values; `cardstore` also loads the open entries of
   `.plumb/session/<id>/stale_cards.json` (written by STALE's `stale.py` in phase H, read here
   and never written) as `CardKind.stale_link` cards with the same topic, issue and resolutions,
   proved by `tests/understand/test_stale_card_adapter.py`; until J7, `stop.py` keeps rendering
   those cards through STALE's own lines (no double rendering: the adapter feeds `cards.json`
   and the summary only once J7 removes the direct lines); `settled` counts as confirmed in
   `api.status`, `boundary/glance.py`, `premerge.py`, `validate.py` and `present/owner_text.py`,
   listed apart as "settled from your words", proved by `tests/understand/test_status_settled.py`
   with a fixture entry and a recheck patched to accept (with the stub, the entry confirms
   nothing).
7. **Config and routes.** `config.py` section `understand` (`dispatch: auto`, `model: haiku`,
   `timeout_s: 120`, `clarify_wait_s: 45`, `reader_threshold_start: 0.9`,
   `backlog_cards_per_turn: 3`, `progress_min_s: 2`, `progress_interval_s: 1`,
   `max_consecutive_failures: 3`). `cli.ROUTES` adds `understand`, `settle`, `undo`, `go` ->
   `plumb.understand.cli` (a thin router to `cmd_worker`, `cmd_settle`, `cmd_go`, `cmd_clarify`)
   and moves `clarify` there, forwarding to today's `capture.cli` function unchanged;
   `hosts/claude_code/cli.py` accepts `hook pre-tool` (stub: allow). `plumb --help` lists a verb
   only when its module is importable.
8. **Owner text.** `present/owner_text.py` constants for the six card kinds, the settled line,
   "reading your answer", "checking your request", "judging N records", "judging the backlog",
   the Build anyway / Wait wording and the reply that names `/plumb settle on`, `/plumb undo`
   and the buttons (first wordings; JUDGE finishes them).
9. **Test helpers.** `tests/understand/fakes.py`: `FakeDispatcher(script)` (answers by job kind
   or a callable; records every job; can block on an event or raise `DispatchError`),
   `as_worker(root, session)` (a context manager that writes a `worker.lock` with a token and sets
   `PLUMB_WORKER`, for tests that apply a kind in process), a fake
   `claude` executable that records its argv, cwd, environment and stdin;
   `tests/understand/harness.py`: `Session(repo)` driving the real hooks as subprocesses with a
   fake dispatcher (`say(text)`, `stop()`, `edit(path)`, `worker_idle()`, `status_line()`).
   `src/plumb/understand/evalrun.py` (`plumb understand eval [--fake]`) loads
   `understand/evalset/{read,judge,clarify}.json`, runs each case on the configured dispatcher,
   and writes an `eval-run` entry (model, prompt digest = digest of `agents/*.md` and
   `schemas/*.json`, per-case result, the clarifier's false-gap rate). The case files start as
   empty lists; each lane fills its own (11.1). `tests/understand/test_contracts.py`
   checks every stub against its signature.
10. **Records.** The proposed changes of spec 10 are written with `plumb capture` as
    proposed records (INT-028 and INT-029 reworded, SR-005 superseded, SR-088 and SR-065
    narrowed, SR-098 and SR-090 superseded, SR-041 superseded by settling, SR-040 and SR-042
    reworded around the judge, SR-043 narrowed, SR-081 reworded, SR-014 brought to the code's
    budgets, DEC-027 revised). Each is proposed and waits for the owner. Phase C links each stub
    module `implemented_by` its SR.

### 3.3 Gates for the phases

Phase H0 gate (on `main`, before the phase H worktrees are created):

```
.venv/Scripts/python.exe -m pytest tests/core/test_config_h0.py tests/core/test_primitives.py tests/host/test_hookio.py -q -p no:cacheprovider
.venv/Scripts/python.exe -m plumb tests run --paths src/plumb/config.py --budget 900
.venv/Scripts/python.exe -m plumb validate
```

Phase H gate (on `main`, after the three merges):

```
.venv/Scripts/python.exe -m pytest tests/core/test_stale.py tests/core/test_stale_resolve.py tests/host/test_edit_check.py tests/host/test_stop_stale.py tests/verify/test_funcmap.py tests/verify/test_select_functions.py tests/verify/test_runner_workers.py tests/host/test_session_cold.py tests/host/test_hook_perf.py tests/host/test_install.py tests/host/test_stop.py tests/core/test_config_h0.py -q -p no:cacheprovider
.venv/Scripts/python.exe -m plumb tests run --paths <every file the three lanes changed> --budget 900
.venv/Scripts/python.exe -m plumb validate
.venv/Scripts/python.exe -m plumb drift
```

Phase C gate:

```
.venv/Scripts/python.exe -m pytest tests/understand/test_contracts.py tests/understand/test_status_settled.py tests/host/test_hookio.py tests/host/test_prompt.py tests/host/test_stop.py tests/host/test_statusline.py tests/core/test_confirm.py tests/core/test_cli_core.py tests/capture/test_capture.py tests/merge/test_glance.py tests/core/test_validate.py tests/core/test_log.py tests/core/test_log_worker_token.py tests/understand/test_stale_card_adapter.py tests/host/test_stop_stale.py -q -p no:cacheprovider
.venv/Scripts/python.exe -m plumb tests run --paths <every file phase C changed> --budget 900
.venv/Scripts/python.exe -m plumb validate
.venv/Scripts/python.exe -m plumb drift
.venv/Scripts/python.exe -m plumb --help      # lists only importable verbs
```

Then the four SP8 worktrees are created from that `main`.

### 3.4 Lane gate (each merge point and before handing back)

```
.venv/Scripts/python.exe -m pytest <the lane's focused set> -q -p no:cacheprovider   # foreground, timeout 600000 ms
.venv/Scripts/python.exe -m plumb tests run --paths <the files the lane changed> --budget 900
.venv/Scripts/python.exe -m plumb validate
.venv/Scripts/python.exe -m plumb drift
.venv/Scripts/python.exe -m plumb claims check --range main..HEAD
git diff --name-only main...HEAD       # every path in the lane's row of 3.1
```

The focused sets are the "Gate" lines of sections 5 to 11. The lane reports `merge-ready <lane>
<merge point> <sha>`. The coordinator merges with `git merge --no-ff` (message with the merged
rows' `SR:` trailers), runs the merged lane's focused set once on `main`, and does not run the
whole suite.

### 3.5 Interface contracts between lanes (phase L)

| Provider | Interface | Consumers | Degraded form while missing |
|---|---|---|---|
| ENGINE | `queue.enqueue`, `queue.retry_failed`, `queue.failures`, `worker.start_detached`, `dispatch.configured`, `progress` steps per job, the `needs` order rule (3.2 item 2a) | READ, JUDGE, SHOW (they only call `enqueue` through their `build`) | phase-C stubs; tests use `FakeDispatcher` and run `worker.run_once` in process |
| READ | `read.build`/`apply`, `typed.parse`, `threshold.reader_threshold(core)`, `effects` dispatch of an answered card, `confirmation_lines(core, turn)` | JUDGE (answers to trial and backlog cards), SHOW (clarify and couldn't-check answers), the summary | `cardstore` fixtures and a scripted reader answer |
| JUDGE | `judge.queue_for_capture`, `premise.commit`/`premise_of`, `summary.stop_parts`, `cards.render`, `settle.state(core, kind)`, `trial` and `backlog` card builders | READ (settled and trial labels), SHOW (cards render), stop hook | the stub parts: no cards, no settled line |
| SHOW | `gate.is_closed/open/close`, `clarify.build`/`apply`, `progress.Reporter` rendering and `status_text`, `pretool` | ENGINE (worker progress), READ (go/wait answers), every long execution | the stub reporter writes its file only; the gate reads open |
| Coordinator | data classes, formats, registries, routes, call sites, config keys, fakes, harness, `evalrun` | all | frozen; changes only through the coordinator |

Unit tests never import another lane's new modules; they use the phase-C stubs, `cardstore`
fixtures or `FakeDispatcher`.

## 4. Phase H: how the three lanes work

Three lanes, all before SP8, after H0 (the two config keys, 3.1). STALE and START both read
hooks; SELECT reads only `verify/`. The three ownership rows of 3.1 share no path (`config.py`
is the coordinator's in H0; `api.py` is START's, `verify/api.py` SELECT's), so the three
worktrees merge without conflicts and each lane gate's `git diff --name-only` check holds.
Each lane writes its failing tests first, with the numbers below as the assertions (not
"faster", a stated limit).

## 5. Lane STALE (SR-111)

Today the edit hook is `post-edit`, asynchronous (it appends the edited path to `touched.txt`,
and `tests/host/test_install.py::test_post_edit_registered_async` pins that), so nothing it
printed would reach the agent, and the stop hook blocks at most once and never when the host
says `stop_hook_active`. The lane keeps `post-edit` as it is and adds a second, synchronous
`PostToolUse` entry, `edit-check`, appended after it (the existing test indexes `[0]`), costing
one more process start per edit (about 0.1 s, a design choice flagged in section 15, question 5).

| # | Task | Tests (first, red) | Merge point | Files touched |
|---|---|---|---|---|
| HA1 | `stale.py`: `links_touching(root, rel)` from a new cache `.plumb/cache/linkmap.json` (path and symbol ends to `[record, link id, pinned target hash]`, plus record to the records that derive from it), rebuilt by `stale.ensure_linkmap(core)`, which the prompt hook and the edit check call when the record index digest changed (a rewrite only then); `stale_after_edit(root, rel)` compares the end's current hash (the stat cache of `hashing.py`) with the pin; standard library plus `plumb.hashing`/`plumb.normalize` only, no YAML, no record index; a missing cache says nothing and leaves the stop hook as the backstop | `tests/core/test_stale.py`: `test_ex1_function_edit_names_sr005_link` (SR-111 EX-1), `::test_reformat_only_symbol_edit_not_stale`, `::test_unrelated_file_nothing`, `::test_missing_cache_silent`, `::test_linkmap_rebuilt_on_index_change` | H-1 | `stale.py` |
| HA2 | `edit_check.py` and `hook edit-check`: after an edit tool call, the one-line notice "plumb: SR-005's link to src/x.py is stale: the file changed; rerun its tests and repin, reword SR-005, or bring it to the owner as a card" as `additionalContext` (`HookOutput.additional_context` renders `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":...}}`), one line per stale link, at most five then "+N more"; `install.py` appends the entry (not async, matcher `Edit|Write|MultiEdit|NotebookEdit`); budget `hooks.budget_ms.post_edit` 300 | `tests/host/test_edit_check.py::test_ex1_notice_in_one_line`, `::test_budget_300_min_of_5`, `::test_silent_when_nothing_stale`, `::test_install_adds_sync_entry_after_async_one`; `tests/host/test_install.py` and `test_hookio.py` kept green | H-1 | `hosts/claude_code/edit_check.py`, `hookio.py`, `cli.py`, `install.py` |
| HA3 | Derived records: a record reworded (through `plumb capture` or a direct edit of its file) tells the agent which records derive from it (`derives_from`, `decides`, `upstream` links) may no longer agree: the capture result lines name "SR-032 derives from INT-016, which was reworded: check that it still agrees"; a direct edit goes through `edit-check` with the core index (cold path allowed, cut by the deadline: then the stop hook says it) | `tests/core/test_stale.py::test_ex2_reword_names_derived_record`, `::test_direct_record_edit_notice`, `tests/capture/test_capture.py` kept green | H-1 | `stale.py`, `capture/capture.py`, `edit_check.py` |
| HA4 | The turn baseline and the hold-open: the prompt hook writes `.plumb/session/<id>/stale_baseline.json` (the ids and pins of links stale at the turn start); at stop, the links stale now and not in the baseline, minus those resolved, are unresolved, and the stop hook returns a block naming each (SR-111 EX-3); the hold ends after `hooks.stale_holds_max` consecutive holds (the key and its default 3 are added by H0; STALE only reads it) with a line saying so and a stale card (HA5's format), so a turn is never held forever (section 15, question 2); the links stale before the turn are listed once per session, not blocking | `tests/host/test_stop_stale.py::test_ex3_unresolved_link_holds_the_turn_and_names_it`, `::test_pre_existing_stale_listed_once_not_blocking`, `::test_hold_ends_after_max_with_card`, `::test_active_flag_still_holds_for_stale_only`; `tests/host/test_stop.py`, `test_stop_question.py` kept green | H-2 | `prompt.py`, `stop.py`, `stale.py` |
| HA5 | Resolution: `plumb repin --after-tests <link or record>` reruns the linked tests (SELECT's selection) and, if they pass and a model judges the meaning unchanged, repins with the note "tests pass, meaning unchanged" (SR-111 EX-4: a reformat-only edit never involves the owner); a model that cannot be reached or says the meaning changed refuses and repins nothing (no rule-based reading, INT-029); `plumb stale card <link> --topic ... --issue ... --options a|b|c` records a stale card for an owner-intent question, which counts as resolving the link for the hold and shows in the end-of-turn summary naming the requirement, the change and the suggested resolutions, the turn ending with the card waiting (SR-111 EX-5). **The stale card is STALE's own format in phase H, because the phase C card store does not exist yet:** `.plumb/session/<id>/stale_cards.json`, a JSON list written atomically by `stale.py` alone (`stale.add_card`, `stale.close_card`), entries `{"link","record","path","topic","issue","options":[...],"recommended":0,"turn","status":"open|resolved"}`; `stale.card_lines(root, session)` renders the open cards as owner-level lines (title instead of ID, the change in words, the options with the recommended first, strings from the stale-card constants STALE adds to `present/owner_text.py`, both scanners passing) and the STALE lines in `stop.py` print them. Phase C then adds a read-only adapter (`cardstore` loads the open entries as `CardKind.stale_link`, 3.2 item 6) and JUDGE's J7 makes the summary render them and removes the direct lines from `stop.py` | `tests/core/test_stale_resolve.py::test_ex4_reformat_repinned_without_owner`, `::test_meaning_changed_refused`, `::test_model_unreachable_refuses_and_repins_nothing`, `::test_ex5_owner_question_becomes_card_and_turn_may_end` (the card is in `stale_cards.json`, the link counts as resolved for the hold), `::test_stale_cards_file_format`, `::test_repin_never_confirms`; `tests/host/test_stop_stale.py::test_ex5_summary_names_requirement_change_and_resolutions_and_the_card_waits`, `::test_stale_card_text_passes_both_owner_text_scanners` | H-2 | `commands.py`, `links.py`, `stale.py`, `cli.py`, `stop.py`, `present/owner_text.py` |
| HA6 | Budgets and the end-to-end: edit, stop and prompt stay inside `hooks.budget_ms` on plumb's own records with the new cache | `tests/host/test_hook_perf.py` kept green plus `tests/host/test_edit_check.py::test_own_records_inside_budget` | H-2 | tests only |

Merge points: H-1 after HA3, H-2 after HA6.

Gate (STALE): `.venv/Scripts/python.exe -m pytest tests/core/test_stale.py tests/core/test_stale_resolve.py tests/host/test_edit_check.py tests/host/test_stop_stale.py tests/host/test_post_edit.py tests/host/test_install.py tests/host/test_stop.py tests/host/test_stop_question.py tests/host/test_hookio.py tests/host/test_prompt.py tests/core/test_links.py tests/core/test_drift.py tests/capture/test_capture.py -q -p no:cacheprovider`

The model that judges "meaning unchanged" in HA5 is the judgment backend already configured for
plumb (JEV) until SP8's worker exists; afterwards the same question becomes a job kind of the
dispatcher (a follow-up, not SP8 scope; section 15, question 3).

## 6. Lane SELECT (SR-110)

SELECT owns `verify/**` including `verify/api.py` (the verification API; the root `src/plumb/api.py`
is START's and SELECT never edits it) and reads the `verify.coverage` key that H0 added. It does
not call `progress.Reporter`, which does not exist before phase C: SHOW's P3 wires the progress
call sites of the new coverage collection later.

`coverage` is not installed in the venv today (`pyproject.toml` has `pytest-xdist`, which the
runner already uses: `verify.workers: 2`, at most 2). Adding a dev dependency changes
`pyproject.toml` and `uv.lock`, which are `verify.infra_globs`: plumb will name a full run as
pending (section 12.4).

| # | Task | Tests (first, red) | Merge point | Files touched |
|---|---|---|---|---|
| HB1 | Probe, time-boxed, in a scratch copy: add `coverage` as a dev dependency, run 30 of plumb's own tests under coverage contexts (one context per test node), and record the overhead, the number of functions executed per test, and the size of an inverted function-to-tests map for the whole suite, in `docs/followups.md`. Choose the store (default: SQLite with the standard library in `.plumb/cache/funcmap.sqlite`, gitignored with the rest of the cache; a JSON file only if the measured size is under 2 MB) | none (a measurement; its numbers become the assertions of HB2 and HB3) | | `pyproject.toml`, `uv.lock`, `docs/followups.md` |
| HB2 | `verify/funcmap.py`: tables `tests(node, file, closure_digest, recorded_at, env_key)`, `funcs(path, qualname, hash)`, `hits(func, test)`; a function's hash is `hashing.hash_symbol` of its qualified name (so a reformat does not change it); queries `tests_executing(path, qualname)` and `functions_changed(paths)` (current hash differs from the recorded one, or the function is new) | `tests/verify/test_funcmap.py::test_roundtrip`, `::test_function_hash_ignores_formatting`, `::test_changed_function_found`, `::test_new_function_has_no_tests`, `::test_env_key_change_invalidates` | H-1 | `verify/funcmap.py` |
| HB3 | Recording: `plumb tests map --coverage` collects once for the whole suite under coverage contexts with the plumb pytest plugin (a new `verify/cov_plugin.py` switching the coverage context per test node), in parallel (`verify.workers`; each worker writes its own data file and they are combined); after that `plumb tests run` records contexts only for the tests it runs whose recorded entry is stale (the test's closure digest changed or it has no entry), so the cost is paid by changed tests only; there is no progress call in phase H (the `progress` module is created in phase C; SHOW's P3 adds the call sites to `verify/funcmap.py` and `verify/cov_plugin.py`) | `tests/verify/test_cov_record.py::test_collect_once_records_every_test`, `::test_refresh_only_stale_tests`, `::test_unchanged_test_not_rerun_for_recording`, `::test_workers_combine_data_files`, `::test_coverage_absent_says_so_and_selects_by_closure` | H-1 | `verify/cov_plugin.py`, `verify/funcmap.py`, `verify/runner.py`, `verify/api.py`, `verify/cli.py` |
| HB4 | `verify/select.py`: for each changed source file, the changed functions (HB2) give the tests that executed them, then the tests linked to the changed requirement (`verified_by`, today's first priority); the import-closure rule applies only to a file no recorded test has executed; a changed function with no recorded test is reported (`Selection.unrecorded`, reason `function`) and the file falls back to its closure with the line "no recorded test executes <function>", never silently to everything | `tests/verify/test_select_functions.py::test_ex1_twelve_executing_tests_not_the_import_closure` (SR-110 EX-1: 12 tests executed the function, 424 import the file, the selection has the 12 plus the requirement's linked tests), `::test_ex2_new_function_falls_back_to_closure_and_says_so`, `::test_requirement_linked_tests_added`, `::test_nothing_recorded_never_runs_everything`; `tests/verify/test_select.py`, `test_testmap.py`, `test_map_incremental.py`, `test_impact.py` kept green | H-2 | `verify/select.py`, `verify/api.py`, `contracts.py` |
| HB5 | Parallel runs: the selected tests run on `verify.workers` workers (1 or 2) with pytest-xdist; with xdist missing, the run says so and runs serially (never a silent change); `plumb tests run --paths`, `--changed` and the stop hook's run all pass the setting; the run still discards on "inputs changed" and reads the phase stream | `tests/verify/test_runner_workers.py::test_ex3_two_workers_with_xdist`, `::test_xdist_missing_runs_serial_and_says_so`, `::test_run_selection_passes_workers`; `tests/verify/test_runner.py`, `test_cli_verify.py` and `tests/host/test_hook_perf.py::test_plumbs_own_runs_use_two_xdist_workers` kept green | H-2 | `verify/runner.py`, `verify/api.py` |
| HB6 | CLI and config: `plumb tests select` prints each test's reason ("executed", "linked", "closure") and the unrecorded functions; `verify.coverage: auto|off` (the key and its default come from H0; `off` = today's closure rules, read by `verify/select.py` and `verify/api.py`); `docs/followups.md` records the numbers | `tests/verify/test_cli_verify.py` kept green plus `tests/verify/test_select_functions.py::test_cli_lines`, `::test_coverage_off_is_todays_selection` | H-2 | `verify/cli.py`, `docs/followups.md` |

Merge points: H-1 after HB3, H-2 after HB6.

Gate (SELECT): `.venv/Scripts/python.exe -m pytest tests/verify/test_funcmap.py tests/verify/test_cov_record.py tests/verify/test_select_functions.py tests/verify/test_runner_workers.py tests/verify/test_select.py tests/verify/test_runner.py tests/verify/test_testmap.py tests/verify/test_map_incremental.py tests/verify/test_cli_verify.py tests/verify/test_impact.py tests/verify/test_evidence.py tests/host/test_hook_perf.py -q -p no:cacheprovider`

## 7. Lane START (session start under its budget, cold)

Measured on 10 Oct: session start takes 2.1 s cold and 1.4 s warm against
`hooks.budget_ms.session_start: 1400` (the code's budget; SR-014's text still says 900, brought
to the code in phase C). Where the time goes is not known yet: HC1 measures first. Target
(plan's own, stated so it is checkable): best of four cold runs at most 0.9 of the budget
(1260 ms), best of four warm runs at most 900 ms, on plumb's own records.

| # | Task | Tests (first, red) | Merge point | Files touched |
|---|---|---|---|---|
| HC1 | Step timings: with `PLUMB_HOOK_TIMING=1` the hook writes `.plumb/session/<id>/timing.json` (step name and milliseconds: interpreter and imports, core open, index, brief, tests summary, snapshot, tree scan, awareness, triage offer); the lane records cold and warm numbers per step in `docs/followups.md` before changing anything | `tests/host/test_session_cold.py::test_cold_start_over_budget_today` (red: it asserts the target, so it fails first), `::test_timing_file_names_every_step` | H-1 | `hosts/claude_code/session_start.py`, `docs/followups.md` |
| HC2 | Imports: what a session start imports is the minimum (`yaml`, `plumb.contracts` and `plumb.hashing` cost about 45, 58 and 78 ms in an import trace); heavy modules load at the call that needs them; a test lists the modules that must not be in `sys.modules` after the hook's imports | `tests/host/test_session_cold.py::test_hook_import_set_has_no_judgment_or_verify_runner`, `tests/host/test_hook_perf.py::test_hookio_imports_only_what_a_hook_always_needs` kept green | H-1 | `api.py`, `hashing.py`, `model.py`, `store.py`, `present/delta.py`, `session_start.py`, `providers.py` |
| HC3 | Cold-state work leaves the hook: no test-map build in the hook (`verify.spawn_map_build` detached, the line "tests: not checked (checking in the background)"), no judgment network call (the triage offer only from a warm cache), the branch scan of `awareness.turn.at_session_start` bounded by its cache, one git status pass | `tests/host/test_session_cold.py::test_cold_start_spawns_map_build_does_not_wait`, `::test_no_network_call_cold`, `::test_git_called_once`, `::test_brief_kept_when_cut` | H-1 | `session_start.py`, `hygiene.py`, `awareness/turn.py`, `awareness/scan.py`, `capture/triage.py` |
| HC4 | Warm path to the target: `derived` caches keyed by the tree, no second pass over the records, link-end hashes from the stat cache | `tests/host/test_session_cold.py::test_warm_start_inside_target`; `tests/host/test_session_start.py` and `tests/host/test_latency.py` kept green | H-2 | `session_start.py`, `api.py`, `awareness/inflight.py`, `hashing.py` |
| HC5 | The gate tests on a copy of plumb's own records: the cold test wipes `.plumb/cache` before each of four runs and takes the best; the warm test the best of four | `tests/host/test_session_cold.py::test_cold_best_of_four_inside_90_percent_of_budget`, `::test_cold_has_no_check_skipped_line` | H-2 | tests only |

Merge points: H-1 after HC3, H-2 after HC5.

Gate (START): `.venv/Scripts/python.exe -m pytest tests/host/test_session_cold.py tests/host/test_session_start.py tests/host/test_latency.py tests/host/test_hook_perf.py tests/host/test_hookio.py tests/awareness/test_hooks.py tests/awareness/test_budget.py tests/awareness/test_two_worktrees.py -q -p no:cacheprovider`

## 8. Lane ENGINE (spec 4.4 and 5; SR-104; SR-101 EX-7; the job order of SR-103 EX-9)

The worker, the jobs and the dispatchers. It knows nothing about what a read, a judgment or a
clarification means: it builds the command, runs it, validates the answer against the schema,
and hands it to the kind's `apply` in memory.

| # | Task | Tests (first, red) | Merge point | Files touched |
|---|---|---|---|---|
| E1 | Probe this Claude Code build once (flags `--agent`, `--agents`, `--json-schema`, `--tools`, `--setting-sources`, `--strict-mcp-config`, `--disable-slash-commands`, `--no-session-persistence` exist and behave; the output JSON shape; that a plumb hook sees `PLUMB_JOB`); record in `docs/followups.md`. Then `dispatch/claude_code.py`: the command `claude -p --agent plumb-<kind> --agents <json> --model <haiku> --tools "" --json-schema <schema> --output-format json --no-session-persistence --setting-sources "" --strict-mcp-config --disable-slash-commands`, environment `PLUMB_JOB=<job-id>`, cwd a new empty temporary directory, the job prompt on stdin; `agents/` loader reads `agents/<kind>.md` (system prompt) | `tests/understand/test_dispatch_claude.py::test_ex6_command_selects_agent_and_isolates` (SR-104 EX-6: flags present, cwd empty and not the repository, no CLAUDE.md text and no plumb block marker in stdin or the agent definition), `::test_env_has_plumb_job`, `::test_missing_binary_is_a_plain_error`, `::test_bad_json_answer_fails_the_schema` (fake `claude` executable) | E-1 | `understand/dispatch/claude_code.py`, `agents/__init__.py`, `docs/followups.md` |
| E2 | `jobs.py`, `queue.py`: job id and file format of 3.2, atomic write, the `needs` field (default None, part of the id, 3.2 item 2), `enqueue` idempotent (the same inputs queued twice give one file; a job with a result is not run again unless the record behind it changed because its inputs changed, which gives a new id) | `tests/understand/test_jobs.py::test_id_is_stable_for_equal_inputs`, `::test_needs_is_part_of_the_id`, `tests/understand/test_queue.py::test_ex4_same_inputs_queued_twice_run_once`, `::test_changed_inputs_new_job`, `::test_result_reused` | E-1 | `understand/jobs.py`, `queue.py` |
| E3 | `worker.py`, `ledger.py`: `start_detached` (a detached process on Windows and POSIX, one per session by the lock, stale lock taken over), `run_once`/`run_loop`: for each queued job it calls the kind's `recompute` from the logs, compares with the file's inputs (a mismatch is reported as a `job-note` and the recomputed inputs are used), runs the dispatcher, validates the answer against the schema, calls `apply` in memory, writes `results/` and the ledger. It never reads a `results/` file to apply. **Order (3.2 item 2a):** a job with `needs` is skipped until the `needs` job has an `ok` result (the `needs` job runs first when queued; the worker picks the queued jobs in `created` order but never starts a job before its `needs`), `recompute` of the dependent runs only after the `needs` job was applied, and a `needs` job that ended in error makes the dependent an error result with step "needs", the model not called. **Authority:** the worker makes the token of `worker.lock` and puts it in its own environment as `PLUMB_WORKER` (never in the dispatcher child's environment); the check itself is phase C's, in `log.py` (`log.worker_token_problem`, 3.2 item 3), so ENGINE edits no `log.py`. | `tests/understand/test_worker.py::test_runs_queued_job_once`, `::test_one_worker_per_session`, `::test_stale_lock_taken_over`, `::test_job_waits_for_its_needs_then_runs` (fake kinds A and B, B `needs` A, queued in either order: B never starts before A has an `ok` result), `::test_dependent_recompute_sees_what_the_needs_job_applied` (B's `recompute` reads a log entry that A's `apply` wrote, and the model prompt of B contains it, SR-103 EX-9), `::test_needs_job_failed_dependent_is_an_error_and_the_model_is_not_called`, `::test_needs_without_job_file_or_result_is_satisfied_and_noted`; `tests/understand/test_worker_authority.py::test_ex7_judge_job_file_with_other_inputs_uses_recomputed_inputs` (SR-104 EX-7 and SR-101 EX-7: the file cannot make a record look supported), `::test_result_file_written_by_agent_confirms_nothing_and_is_reported`, `::test_apply_outside_worker_refused` (a fake kind whose `apply` writes an `approval` by `owner-words`: refused with no `PLUMB_WORKER`, with a wrong one, and accepted inside `run_once`, through phase C's `log.py` check), `::test_dispatcher_child_environment_has_no_worker_token`, `::test_lock_holds_a_token`, `::test_job_file_without_ledger_reported` | E-1 | `understand/worker.py`, `ledger.py`, `schema.py` |
| E4 | Failures: a dispatcher that fails, an answer that fails the schema, a timeout: the job's result is an error naming the step; nothing is confirmed, settled or rejected; `queue.retry_failed` re-queues failed jobs on the next turn, a failed `needs` job before its dependent; three consecutive failures set the flag the status line shows; the failure is data for the "couldn't check" line (`queue.failures`); no second dispatcher is tried, no word rule is called | `tests/understand/test_failures.py::test_ex3_unreachable_model_summary_says_not_checked_and_retries`, `::test_ex5_word_rules_not_called_when_dispatcher_fails` (the rules of `approvals.py` are patched to raise, `raising=False` so it survives their removal), `::test_no_second_route`, `::test_three_failures_flagged`, `::test_schema_failure_is_an_error_not_a_reading` | E-2 | `understand/queue.py`, `worker.py`, `dispatch/__init__.py` |
| E5 | `hookio` guard test and the batching contract of the queue side: `PLUMB_JOB` makes every hook exit at once; the queue refuses to queue when `PLUMB_JOB` is set; the prompt hook queues and returns without waiting (SR-104 EX-1); one read job covers every shown record and open card (EX-8, the build is READ's, the assertion that the hook queues one job per turn and one judge job per capture lives here with a fake kind for the count) | `tests/understand/test_hooks_in_job.py::test_ex2_hooks_exit_in_a_job_session` (all five hooks, nothing queued, nothing written), `::test_queue_refuses_inside_a_job`; `tests/understand/test_queue.py::test_ex1_prompt_hook_returns_within_budget_without_waiting`, `::test_one_job_per_turn_one_per_capture_with_fake_kinds` | E-2 | `understand/queue.py` |
| E6 | Progress of jobs: the worker reports each job's `describe` step in plain words at least once per second through `progress.Reporter` (the file is written by the stub reporter; SHOW makes it render): "reading your answer", "checking your request", "judging 7 records"; the file disappears when the job ends; a failed job replaces the line with the failed step | `tests/understand/test_progress_worker.py::test_ex10_status_text_says_reading_your_answer_while_running_and_agent_carries_on` (the fake dispatcher blocks on an event; nothing confirmed meanwhile), `::test_ex11_judging_7_records_then_line_gone`, `::test_ex12_failed_job_names_the_step_and_stops_running` | E-2 | `understand/worker.py` |
| E7 | `dispatch/hermes.py` (a delegated child session, without tools, given the job prompt and schema, following SR-099's assessment and the Hermes adapter plan; the exact call is spec question 12.1: the lane writes it behind a small `HermesDelegate` seam and records what it verified) and `dispatch/openrouter.py` (a direct call through the credential `judgment/jev.py` already reads, the same schema, configured only, never a silent fallback); `cmd_worker.py` (`plumb understand worker --session <id>` foreground, for tests and a terminal) | `tests/understand/test_dispatch_hermes.py::test_delegate_called_without_tools_with_schema`, `::test_unavailable_is_a_plain_error`; `tests/understand/test_dispatch_openrouter.py::test_posts_schema_and_reads_answer` (local fake HTTP server), `::test_not_configured_is_an_error_not_a_fallback`; one live test per dispatcher marked `dispatch_live`, skipped unless the host or credential is present | E-3 | `understand/dispatch/hermes.py`, `openrouter.py`, `cmd_worker.py` |

Merge points: E-1 after E3, E-2 after E6, E-3 after E7. READ, JUDGE and SHOW test against the
phase-C stubs and `FakeDispatcher`, so ENGINE's merge is not on their critical path.

Gate (ENGINE): `.venv/Scripts/python.exe -m pytest tests/understand/test_jobs.py tests/understand/test_queue.py tests/understand/test_worker.py tests/understand/test_worker_authority.py tests/understand/test_dispatch_claude.py tests/understand/test_dispatch_hermes.py tests/understand/test_dispatch_openrouter.py tests/understand/test_failures.py tests/understand/test_hooks_in_job.py tests/understand/test_progress_worker.py tests/understand/test_contracts.py tests/host/test_hookio.py -q -p no:cacheprovider`

## 9. Lane READ (spec 4.1, 6 and 10; SR-101; the reader's part of SR-103, SR-105, SR-106, SR-107)

| # | Task | Tests (first, red) | Merge point | Files touched |
|---|---|---|---|---|
| R1 | The reader kind: `read.build` assembles the job from the logs: the owner's logged message (text and digest from the prompt log), the stated set of the previous reply (records at their hash with the text shown), the open cards from `cardstore`; one job per turn covers all of it; `agents/read.md` and `schemas/read.json` (one entry per shown record or card question: `id`, `hash`, `answer` accepted/rejected/change/open, `rejection` misread/intent-changed, `change`, `evidence`, `confidence`); the prompt hook's `on_prompt` read part queues it when the previous reply stated anything | `tests/understand/test_read_job.py::test_ex12_five_records_and_a_card_one_job_one_entry_each`, `::test_one_job_per_turn_six_items` (SR-104 EX-8), `::test_no_job_when_nothing_stated`, `::test_schema_has_only_four_answers` | R-1 | `understand/read.py`, `agents/read.md`, `schemas/read.json` |
| R2 | Applying an answer, exact checks only: the message is in the prompt log; the id was in the stated set at that hash; the evidence occurs in the message; an `accepted` entry at or above the threshold confirms as `approval` `by: owner-words` (prompt digest, evidence, job id, confidence); `rejected` is logged as an SR-096 rejection (`misread` = the calibration "no"); `change` becomes a recapture task read back at the next turn; `open` or below the threshold confirms nothing; a record named but not shown becomes a `show_first` card; every entry is logged as `read-entry` for calibration; the confirmation lines "you said: <evidence>" for the summary | `tests/understand/test_read_apply.py::test_ex1_int008_ok_confirmed_sr088_change`, `::test_ex2_int24_read_as_int024_all_three_confirmed`, `::test_ex3_unshown_record_shown_as_card_first_then_confirmed_next_answer`, `::test_ex4_confidence_below_threshold_confirms_nothing`, `::test_ex5_edited_record_confirms_nothing_new_version_shown`, `::test_evidence_not_in_message_confirms_nothing`, `::test_message_not_in_log_confirms_nothing`, `::test_rejected_misread_labelled_no`, `::test_rejected_intent_changed_no_label`, `::test_confirmation_lines_say_you_said`, `::test_ex13_nothing_confirmed_while_the_job_runs_confirmed_when_it_returns` | R-1 | `understand/read.py` |
| R3 | The reader's threshold: `threshold.reader_threshold(core)` is 0.9 until twenty labelled answers are on file, then the lowest confidence at and above which the owner agreed with every reader answer (labels: trial yes/no, `misread` rejections, owner-words confirmations); `recheck_words.problem(entry, core)` re-checks an `owner-words` entry (prompt digest in the log, evidence in the message, hash the one shown) | `tests/understand/test_threshold.py::test_ex14_twenty_answers_support_0_8`, `::test_starting_value_until_enough_labels`, `::test_a_disagreement_raises_the_threshold`; `tests/understand/test_read_apply.py::test_recheck_owner_words_catches_forged_entry` | R-1 | `understand/threshold.py`, `recheck_words.py` |
| R4 | Cards answered in prose: `effects` dispatch by the card's kind for the four answers; card resolutions map (keep = accepted, drop = rejected, reword = change, pick or combine = change with the version); a trial batch's yes/no per item; the feature card's yes with named exceptions per record | `tests/understand/test_read_cards.py::test_ex11_keep_drop_reword_and_two_versions_map` (SR-101 EX-11 and SR-105 EX-4), `::test_sr105_ex5_yes_yes_no_third_rejected_as_misreading`, `::test_sr107_ex4_yes_except_sr040_only_17_confirmed_each_labelled_yes`, `::test_sr103_ex9_all_three_questions_mapped_in_one_message`, `::test_sr103_ex10_no_wait_maps_to_rejected` | R-2 | `understand/read.py` |
| R5 | Typed commands: `typed.parse(prompt_text)` is exact grammar, not reading: `/plumb approve|confirm <IDs>`, `/plumb undo <ID>`, `/plumb settle on|off <kind>`, `/plumb go`; a typed approve/confirm naming IDs confirms at once, recorded as passed on from the owner's typed command, the prompt digest checked against the logged prompt, the reader not called, shown or not; typed confirm with words confirms nothing (the words go to the reader as prose); owner-only settings, Undo and the release of a failed check change only by the typed command or a button: a prose "turn settling on" or "undo that" mapped to accepted changes nothing and the reply names the command or button | `tests/understand/test_typed.py::test_ex6_typed_approve_unshown_dec017_confirmed_at_once_reader_not_called`, `::test_ex10_typed_confirm_with_words_confirms_nothing`, `::test_grammar_is_exact`; `tests/understand/test_owner_only.py::test_ex8_prose_turn_settling_on_changes_nothing_and_names_the_command` (SR-101 EX-8 and SR-106 EX-4), `::test_prose_undo_that_names_the_button` (SR-105 EX-6), `::test_settle_offer_card_is_owner_only` | R-2 | `understand/typed.py`, `commands.py`, `present/cli.py` |
| R6 | **Waits for the owner's confirmation of the SR-005 supersession, exactly as R8 does, and lands with R8 in R-3.** `plumb relay` keeps only a terminal form (an interactive y/N, like `plumb approve`); run from the agent's shell under the session marker (`PLUMB_AGENT_SESSION`), or without a terminal, it is refused with exit 3 and nothing is written. Today the agent's relay under the marker is the supported route and `tests/core/test_confirm.py`, `tests/core/test_owner_terminal.py`, `tests/core/test_relay_mixed.py` and `tests/core/test_relay_reject.py` pin it, so before the confirmation the refusal would turn those tests red, which binding rule 2 forbids a lane to resolve. Until the confirmation, R6 is not started (no test file, no code); R1 to R5 and R7 touch no relay behaviour. After it, the commit that adds the refusal removes the tests of the superseded example in the same commit as the requirement text, naming the example id in the commit body (as R8) | `tests/understand/test_relay_terminal.py::test_ex9_agent_relay_with_a_quote_refused_exit_3_nothing_written`, `::test_relay_without_terminal_refused`, `::test_terminal_relay_still_works` | R-3 (after the owner's confirmation) | `commands.py`, `approvals.py` |
| R7 | The reader cases of the evaluation set (11.1): the owner's INT-008/SR-088 message, "Confirm SR-097, SR-098, INT-24", "Reject all G" for the ten generated variations, with their frozen shown sets | `tests/understand/test_read_job.py::test_evalset_reader_cases_load_and_run_on_the_fake`; `plumb understand eval --fake` runs them | R-2 | `understand/evalset/read.json` |
| R8 | Retire the word rules and their callers, **only after the owner confirms** the supersession of SR-005, SR-098 and SR-090 and the narrowing of SR-088 and SR-065 (spec 10; section 15, question 1). Remove `owner_scope`, `change_clauses`, `objection_clauses`, `affirmation_context_problem`, `_plain_named` from `approvals.py` and `affirmation_in` from `confirm.py`; replace each caller of spec 10's table: the relay line and `awaiting_line` of `prompt.py` (the line names the shown records and the typed command), the "message also objects" flag of `boundary/glance.py` (the reader's `change`/`rejected` shown on the merge line), `mergedriver/conflicts.relay_choice` and `mergedriver/cli.py` (a reader job on the merge card's question; an exact typed pick stays), `awareness/answer.py`, `confirm.entry_problem`, the `plumb confirm <words>` resolution of `present/confirm.py`. A test that pins a retired example is removed only in the commit that removes the example's requirement text, named in the commit body with its example id; no other existing test changes | `tests/understand/test_retire_word_rules.py::test_removed_names_do_not_exist`, `::test_each_caller_uses_the_reader`, `::test_old_agent_relayed_entries_stay_valid`; the kept tests of the gate pass unchanged | R-3 | `approvals.py`, `confirm.py`, `prompt.py`, `boundary/glance.py`, `mergedriver/conflicts.py`, `mergedriver/cli.py`, `awareness/answer.py`, `present/confirm.py` |
| R9 | Templates: `plumb-command.md` routes `settle`, `undo`, `go`, `approve`, `confirm` as typed commands with `--prompt`; the plumb skill says the owner's prose is read by a separate model and the agent never confirms | `tests/understand/test_typed.py::test_command_template_routes_every_typed_command`, `tests/capture/test_skills.py` kept green | R-3 | `templates/plumb-command.md`, `templates/skills/plumb/SKILL.md` |

Merge points: R-1 after R3, R-2 after R7 (R4, R5, R7), R-3 after R9 (R6, R8, R9; R6 and R8 only after the owner's confirmation, section 15, question 1; R9 alone may land earlier).

Gate (READ): `.venv/Scripts/python.exe -m pytest tests/understand/test_read_job.py tests/understand/test_read_apply.py tests/understand/test_read_cards.py tests/understand/test_typed.py tests/understand/test_threshold.py tests/understand/test_owner_only.py tests/understand/test_relay_terminal.py tests/understand/test_retire_word_rules.py tests/core/test_confirm.py tests/core/test_owner_terminal.py tests/present/test_present_confirm.py tests/host/test_prompt.py tests/merge/test_glance.py tests/capture/test_skills.py -q -p no:cacheprovider` (`test_relay_terminal.py` exists only once R6 has landed; after R6 and R8 the files of retired examples leave this list in the same commit).

## 10. Lane JUDGE (spec 4.2, 6, 7, 8; SR-102, SR-105, SR-106, SR-107)

| # | Task | Tests (first, red) | Merge point | Files touched |
|---|---|---|---|---|
| J1 | The judge kind: `judge.build` assembles one entry per record (an intent's read-back, will, won't; a requirement's statement and examples; a decision's question and chosen option), its premise (the owner's whole logged message or messages, the stored question for a short answer, the parent intent when confirmed), and the confirmed or settled records it relates to; labelled assumptions are shown and left out of what is judged; `agents/judge.md` asks "would the owner object to this record given their words?"; `schemas/judge.json`; `apply` logs one `verdict` per record with the model's confidence as the score (0 unless `supported`) | `tests/understand/test_judge_job.py::test_ex6_short_answer_premise_holds_the_question`, `::test_assumptions_shown_not_judged`, `::test_ex4_contradicts_names_both_examples`, `::test_verdict_logged_with_score`, `::test_ex5_option_picked_decision_supported_is_not_settled_waits_as_card`, `::test_evalset_judge_cases_load_and_run_on_the_fake` | J-1 | `understand/judge.py`, `agents/judge.md`, `schemas/judge.json` |
| J2 | The premise in the committed log: when a record first takes a message as premise, `premise.commit` writes `premise` (text and digest) to the committed log; `premise_of(core, record)` reads the committed log first, then the session log; `plumb validate` checks digest = sha256(text) and that a settled record's premise is present | `tests/understand/test_premise.py::test_ex7_capture_commits_message_text_and_digest`, `::test_ex8_fresh_clone_judges_from_committed_log`, `::test_validate_flags_a_premise_whose_digest_differs` | J-1 | `understand/premise.py` |
| J3 | One judge job per capture, covering every record the capture wrote or changed, queued by `capture.capture` and not awaited; the results come from the worker | `tests/understand/test_judge_job.py::test_ex9_capture_of_one_intent_and_six_requirements_queues_one_job_for_seven` (SR-104 EX-9 and SR-102 EX-7), `tests/capture/test_capture.py` kept green | J-1 | `capture/capture.py`, `understand/judge.py` |
| J4 | Trial: while no calibration passes for a kind, every `supported` record goes to a trial batch card of up to five (four the judge would settle, one drawn from below the threshold asked as "plumb would not settle this; right?"); yes is recorded as an owner confirmation (`by: owner-words`, `label: yes`, via the card answer), no rejects as `misread`; `calibrate.labelled_set` counts `owner-words` as well as `owner` and `agent-relayed`; `calibrate()` reads the logged score and makes no model call; SR-042's thresholds per kind | `tests/understand/test_trial.py::test_ex1_no_calibration_three_supported_one_batch_nothing_settled`, `::test_ex7_batch_of_five_four_plus_one_below_threshold`, `::test_ex6_yes_is_a_labelled_yes_and_recalibration_makes_no_model_call`, `::test_batch_of_more_than_five_split`; `tests/capture/test_calibrate.py`, `test_calibrate_rejections.py` kept green | J-2 | `understand/trial.py`, `cards.py`, `capture/calibrate.py` |
| J5 | Settling: eligibility (a decision, a set member, an escalated set member, an edit of an owner-confirmed record never settle: a trial or confirm card instead); `settle.py` states per kind; settling for requirements and their examples switches itself on when calibration passes, once told, logged with the calibration; for intents the owner is told once and turns it on with `/plumb settle on` or a button; off by `/plumb settle off` or a button, and a kind the owner switched off is never switched on again; a settled record is `by: settled` (job id, model, score, premise digest), counts as confirmed, returns to proposed when its text or premise changes; a model or prompt change suspends settling until the evaluation set passes and calibration reruns, after which a kind that switched itself on does so again unless the owner switched it off | `tests/understand/test_settle.py::test_ex5_decision_set_member_owner_edit_never_settled`, `::test_ex3_premise_message_edited_record_proposed_again`; `tests/understand/test_settle_switch.py::test_ex2_intents_told_once_stays_off_until_the_owner_turns_it_on`, `::test_ex8_requirements_switch_on_by_themselves_told_once_logged_with_calibration`, `::test_ex9_owner_switched_off_never_switched_on_again`, `::test_ex10_model_change_suspends_then_requirements_return_intents_only_if_owner_had`; `::test_settle_on_refused_in_prose_and_from_the_agent_shell` | J-2 | `understand/settle.py`, `cmd_settle.py`, `capture/calibrate.py`, `present/owner_text.py` |
| J6 | `recheck_settled.problem` (judgment logged with job id, model and score; premise digest unchanged), `undone` (the owner's typed `/plumb undo <ID>` or a button; an undone record is proposed again and shown as a card next turn), `cmd_settle.py` (`settle on|off`, `undo`, terminal and typed forms, refused for the agent) | `tests/understand/test_recheck_settled.py::test_forged_settled_entry_is_a_problem`, `::test_changed_premise_invalidates`, `::test_undone_only_by_typed_or_button`, `::test_sr105_ex3_undone_record_proposed_again_and_carded` | J-2 | `understand/recheck_settled.py`, `cmd_settle.py`, `settle.py` |
| J7 | The summary (SR-105): `summary.stop_parts` and `cards.render` give, in order, what the owner confirmed by their words, one settled line "Settled from your words: <title>; <title>" with Undo for each, and the cards (clarify, trial batch, backlog feature, goes beyond your words, contradicts, couldn't check), each naming the topic, the issue, the evidence and two or three suggested resolutions, the recommended first; `stop.py` fits the settled line in its 1400 ms budget; the agent words the resolutions from plumb's facts. **Stale cards (SR-111 EX-5) move here:** the phase C adapter already loads STALE's `stale_cards.json` entries as `stale_link` cards; `cards.render` renders that kind with the same facts, and the commit removes the direct STALE card lines from `stop.py` (phase H's `stale.card_lines` call) so each card shows once | `tests/understand/test_summary.py::test_sr105_ex1_two_settled_one_line_undo_each`, `::test_sr105_ex2_beyond_card_offers_keep_drop_reword`, `::test_order_confirmations_settled_cards`, `::test_each_card_kind_names_topic_issue_evidence_resolutions`, `::test_owner_text_passes_both_scanners`, `::test_stop_budget_holds`, `::test_couldnt_check_line_after_a_failed_job` (SR-104 EX-3), `::test_stale_link_card_rendered_by_the_summary_exactly_once` (SR-111 EX-5 carried over); `tests/host/test_stop.py` and `tests/host/test_stop_stale.py` (its EX-5 test unchanged) kept green | J-3 | `understand/summary.py`, `cards.py`, `stop.py`, `present/owner_text.py` |
| J8 | The backlog (spec 8): one pass judging every proposed record without a per-turn limit, as a series of judge jobs each covering the records of one intent, resumed after a failure from where it stopped, a record already judged not judged again unless it changed; one feature card per feature ("these 18 about the merge check would be settled; right?") with one record drawn from below the threshold; flagged records (`beyond`, `contradicts`) come as issue cards and are not on a feature card; a record whose premise is a fragment not found in the prompt log says the original words are not on file and offers its read-back; cards are offered a few per turn (`backlog_cards_per_turn`), the features with most records first (metering what is shown, not what is judged); progress "judging the backlog · 10/160" through `progress.Reporter`; a yes confirms every record on the card, each labelled yes | `tests/understand/test_backlog.py::test_sr107_ex1_150_records_one_pass_no_per_turn_limit_done_jobs_not_rerun`, `::test_sr107_ex2_fragment_premise_says_words_not_on_file`, `::test_sr107_ex3_18_supported_one_feature_card_yes_confirms_all_labelled`, `::test_sr107_ex5_three_flagged_are_issue_cards_not_on_the_feature_card`, `::test_sr107_ex6_progress_10_of_160`, `::test_sr107_ex7_model_unreachable_midway_resumes_without_rejudging`, `::test_sr105_ex7_eighteen_merge_check_records_one_card`, `::test_cards_per_turn_metered_most_records_first` | J-3 | `understand/backlog.py`, `cards.py`, `judge.py` |
| J9 | Retire the parts that settling supersedes, **only after the owner confirms** SR-041's supersession (section 15, question 1): `capture/autoapprove.py` keeps its revocation, undo and re-check parts (moved into `settle.py`) and the owner-only on/off switch; `triage.claim()` is replaced by the judge's verdict; `plumb triage` lists trial and backlog cards; the judge cases of the evaluation set (INT-016, INT-013, INT-004, INT-006, INT-007, "A" for INT-008 with its stored question) | `tests/understand/test_settle.py::test_autoapprove_exclusions_moved_to_settling`, `::test_ex1_int016_beyond_one_line_per_record_and_token_budget` (SR-102 EX-1, eval fixture), `::test_ex2_int013_beyond_maintenance_mode`, `::test_ex3_int006_answer_b_supported`; `tests/capture/test_triage.py`, `test_auto_approve.py` kept green until the owner confirms | J-3 | `capture/autoapprove.py`, `capture/triage.py`, `capture/cli.py`, `understand/settle.py`, `evalset/judge.json` |

Merge points: J-1 after J3, J-2 after J6, J-3 after J9.

Gate (JUDGE): `.venv/Scripts/python.exe -m pytest tests/understand/test_judge_job.py tests/understand/test_premise.py tests/understand/test_trial.py tests/understand/test_settle.py tests/understand/test_settle_switch.py tests/understand/test_recheck_settled.py tests/understand/test_summary.py tests/understand/test_backlog.py tests/capture/test_calibrate.py tests/capture/test_calibrate_rejections.py tests/capture/test_capture.py tests/capture/test_triage.py tests/capture/test_auto_approve.py tests/host/test_stop.py tests/host/test_stop_question.py tests/host/test_stop_stale.py -q -p no:cacheprovider`

## 11. Lane SHOW (spec 4.3 and 4.4; SR-103; SR-108)

What the owner waits for and sees: the up-front check and its gate, and the progress of every
long execution.

| # | Task | Tests (first, red) | Merge point | Files touched |
|---|---|---|---|---|
| S1 | The clarify kind: `clarify.build` (the message and the confirmed and settled records it touches; `needs` = the id of the read job of the same message, which `understand.hooks.on_prompt` passes as `after`, so ENGINE's worker runs it only once that job was applied; `clarify.recompute` then reads the cards the reader just mapped from `cardstore`); `agents/clarify.md`, `schemas/clarify.json` (`intent` yes/no, the draft read-back with will, won't, assumptions and two or three examples, the gaps that change what gets built, ranked, each with two or three suggested answers and a recommended one); plumb shows one card of at most three questions, the smaller gaps as labelled assumptions on the same card; more than three escalate to a short spec session; no gap means no card; no intent means no card | `tests/understand/test_clarify_job.py::test_ex1_export_request_one_card_format_and_scope_rest_assumptions`, `::test_ex2_request_that_maps_to_confirmed_requirement_no_card`, `::test_ex3_five_gaps_offer_a_spec_session`, `::test_ex4_a_question_carries_no_intent_no_card`, `::test_ex8_two_answers_confirmed_assumption_stays_proposed`, `::test_ex9_clarify_job_needs_the_read_job_and_its_inputs_hold_the_answered_card` (SR-103 EX-9: `clarify.build(after=<read job id>)` sets `Job.needs`; with a `cardstore` fixture in which the card was just answered, `clarify.recompute` returns `answered` with it and no second card is asked; the order itself is ENGINE's E3 test and the end-to-end flow 12.2 (1)) | S-1 | `understand/clarify.py`, `agents/clarify.md`, `schemas/clarify.json` |
| S2 | The gate: `gate.py` writes `.plumb/session/<id>/gate` (closed by the prompt hook through `on_prompt`, which queues the clarify job idempotently and does not wait); only plumb opens it, each time with a `gate` log entry: the clarify result says no intent or no gap, or carries a card whose questions are all mapped by the reader, or the owner releases a failed check; a file opened with no matching log entry is reported by `plumb validate` and the stop hook (tamper-evident, not tamper-proof) | `tests/understand/test_gate.py::test_prompt_hook_closes_gate_and_queues_clarify_job`, `::test_opens_on_no_intent`, `::test_opens_when_card_fully_answered`, `::test_stays_closed_with_a_pending_job`, `::test_open_without_log_entry_reported` | S-1 | `understand/gate.py` |
| S3 | `plumb clarify --wait` (`cmd_clarify.py`): returns the result, waiting up to the timeout (45 s) for the queued job, or runs the job itself when none was queued (same id, never twice); a late result after a timeout is collected by the next wait, never after the build; progress shows as a bar in a terminal and plain lines otherwise (P1); a dispatcher failure gives the "couldn't check" card asking "Build without the check?" with Build anyway and Wait; the gate opens only by the button, the typed `/plumb go` (`cmd_go.py`) or prose the reader maps to accepted at or above the reader's threshold; "no, wait" keeps it closed and the next turn retries; a failed clarify job for a message that was only "ok" keeps edits refused until released or retried | `tests/understand/test_clarify_wait.py::test_ex5_wait_blocks_until_card_ready`, `::test_ex6_late_result_collected_by_next_wait_no_build_started`, `::test_runs_the_job_itself_when_none_queued`, `::test_same_job_never_runs_twice`; `tests/understand/test_clarify_release.py::test_ex7_dispatcher_failure_couldnt_check_card_nothing_built`, `::test_release_by_button_typed_go_or_prose_at_threshold_only`, `::test_ex10_no_wait_keeps_gate_closed_next_turn_retries`, `::test_ex11_failed_job_for_ok_message_still_refuses_edits` | S-2 | `understand/cmd_clarify.py`, `cmd_go.py`, `gate.py` |
| S4 | The pre-tool gate (Claude Code only): `templates/gate.sh` is a shell script with no Python that reads the hook's JSON on stdin, extracts `session_id` with `sed`, reads the one small gate file and answers `permissionDecision: deny` with a reason for an edit tool (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`) while it says closed, within 50 ms; edits through Bash are out of scope and the reason says so; `install.py` registers `PreToolUse` (matcher the edit tools) running the script, and `plumb hook pre-tool` is the Python route of the same decision for tests and other launchers; other hosts get the skill instruction and the visible card, no hard refusal | `tests/understand/test_pretool.py::test_ex5_edit_refused_while_closed_message_names_clarify_wait`, `::test_edit_allowed_when_open`, `::test_script_text_contains_no_python`, `::test_script_answers_inside_50_ms_min_of_5`, `::test_bash_edit_not_gated_and_reason_says_so`, `::test_install_registers_pretool`; `tests/host/test_install.py` kept green | S-2 | `hosts/claude_code/pretool.py`, `templates/gate.sh`, `install.py`, `cli.py` |
| S5 | The skill and the old depth rule: `plumb-clarify` SKILL.md makes `plumb clarify --wait` the agent's first action and says the agent does not build until a card is answered; `capture/clarify.py`'s `AMBIGUITY_TERMS` and unmatched-term depth are replaced by the clarifier's gaps (INT-029), **after the owner confirms** the narrowing of SR-043 (section 15, question 1) | `tests/understand/test_clarify_wait.py::test_skill_first_action_is_clarify_wait`, `tests/capture/test_skills.py`, `test_clarify.py`, `test_clarify_e2e.py` kept green until then | S-2 | `templates/skills/plumb-clarify/SKILL.md`, `capture/clarify.py` |
| S6 | The clarifier's cases (11.1, spec 9.3): requests that need no clarification and requests with known gaps; the false-gap rate (questions asked that change nothing about what gets built) measured by `plumb understand eval` and reported with the calibration results; no pass mark (spec 12.3) | `tests/understand/test_clarify_job.py::test_ex12_false_gap_rate_measured_and_reported_with_calibration_results`, `::test_evalset_clarify_cases_load_and_run_on_the_fake` | S-3 | `understand/evalset/clarify.json` |
| P1 | `progress.py`: the renderers over the stub's file writer: no display for an execution under `progress_min_s` (2 s) (EX-5); at least one update per `progress_interval_s` (1 s); a terminal (stderr is a tty) draws one bar line redrawn in place with the step, done of total and the current item (EX-1); otherwise bounded plain lines at a steady interval, never one per test, the last line saying the run finished with its result (EX-2); an unknown total shows the step and the elapsed time, no percentage or bar fill (EX-4); a failure replaces the line with one naming the step that failed and stops the running state (EX-7) | `tests/understand/test_progress.py::test_sr108_ex1_terminal_bar_in_place_with_running_the_full_suite_120_of_400`, `::test_ex2_plain_lines_steady_never_per_test_last_line_says_finished`, `::test_ex4_unknown_total_elapsed_no_percentage`, `::test_ex5_under_two_seconds_nothing_shown`, `::test_ex7_failure_replaces_line_and_stops_running`, `::test_refresh_at_least_once_per_second` (fake clock) | S-3 | `progress.py` |
| P2 | The status line: `statusline.py` shows the live progress of the session's file and of `cli/progress` (stale when not updated for 5 s and its process gone): "plumb ⏳ merge check: running the full suite · 120/400" (EX-3) and "judging the backlog · 10/160" (EX-6); three consecutive job failures show in the line (spec 9.1); `snapshot.py` carries the flag | `tests/understand/test_statusline_progress.py::test_sr108_ex3_merge_check_line`, `::test_sr108_ex6_backlog_line`, `::test_stale_progress_not_shown`, `::test_failed_line_stops_showing_running`, `::test_three_failures_flag`; `tests/host/test_statusline.py` kept green | S-3 | `hosts/claude_code/statusline.py`, `snapshot.py` |
| P3 | Call sites: the full suite run (`verify/runner.py` counts nodes finished from the plugin's phase stream against the collected total, naming the test file currently running; `verify/pytest_plugin.py` writes the total once), the covering tests of a turn, the test-map build (unknown total), `boundary/fullrun.py` and `boundary/cli.py` (merge-check), `importer/cli.py`, `align.py`, and SELECT's coverage collection (`verify/funcmap.py`, `verify/cov_plugin.py`, which phase H built without any progress call because `progress.py` did not exist yet); each reports through `progress.Reporter` and changes nothing it decides | `tests/understand/test_progress_sites.py::test_full_run_reports_done_of_total_and_current_file`, `::test_merge_check_step_names`, `::test_map_build_elapsed_only`, `::test_coverage_collection_reports_done_of_total_tests` (SR-108 EX-1 shape, on a fake suite), `::test_import_and_align_report`, `::test_no_behaviour_change_exit_codes_and_evidence` ; `tests/verify/test_runner.py`, `tests/verify/test_cov_record.py`, `tests/verify/test_funcmap.py`, `tests/merge/test_fullrun.py`, `test_merge_check_cli.py` kept green | S-3 | `verify/runner.py`, `pytest_plugin.py`, `testmap.py`, `funcmap.py`, `cov_plugin.py`, `boundary/fullrun.py`, `boundary/cli.py`, `importer/cli.py`, `align.py` |

Merge points: S-1 after S2, S-2 after S5, S-3 after P3. Changing `verify/pytest_plugin.py` is a
`verify.infra_globs` change: plumb names a full run as pending (12.4).

Gate (SHOW): `.venv/Scripts/python.exe -m pytest tests/understand/test_clarify_job.py tests/understand/test_gate.py tests/understand/test_clarify_wait.py tests/understand/test_clarify_release.py tests/understand/test_pretool.py tests/understand/test_progress.py tests/understand/test_progress_sites.py tests/understand/test_statusline_progress.py tests/capture/test_clarify.py tests/capture/test_clarify_e2e.py tests/capture/test_skills.py tests/host/test_install.py tests/host/test_statusline.py tests/hosts/test_hermes.py tests/verify/test_runner.py tests/verify/test_cov_record.py tests/verify/test_funcmap.py tests/merge/test_fullrun.py tests/merge/test_merge_check_cli.py -q -p no:cacheprovider`

### 11.1 Spec 9.3's evaluation set

Cases are frozen copies (the records are reworded over time; the inputs are stored in the case
files, built from `.plumb/session/prompts.jsonl` and the git history of the records, never read
live). A case is `{id, kind, input, expect}`; `plumb understand eval` runs them on the
configured dispatcher, before calibration and after any model or prompt change, and writes the
`eval-run` entry. Read and judge cases must all match; the clarifier's false-gap rate is
measured and reported (no pass mark). `--fake` runs the loader and the comparison on scripted
answers (a unit test); a run against the real model is Integrate's (12.3).

| Case | Kind | Expect | Lane | Task |
|---|---|---|---|---|
| "INT-008 ok, I am not sure I agree with SR-088. In terms of UX, some features might have to remain internal to plumb." | read | INT-008 accepted (evidence "INT-008 ok"); SR-088 change (some features stay internal) | READ | R7 |
| "Confirm SR-097, SR-098, INT-24" | read | all three accepted (INT-24 read as INT-024) | READ | R7 |
| "Reject all G" over the ten generated variations | read | all ten rejected | READ | R7 |
| INT-016's first read-back with the owner's message | judge | beyond: one line per record and a token budget | JUDGE | J9 |
| INT-013's first read-back with the owner's message | judge | beyond: maintenance mode stated as decided | JUDGE | J9 |
| INT-004, INT-006 (answer B with its question), INT-007 | judge | supported | JUDGE | J9 |
| "A" for INT-008 with its stored question | judge | supported | JUDGE | J9 |
| requests that need no clarification (at least ten, from the prompt log) and requests with known gaps ("let users export their data", a five-gap request) | clarify | no card for the first; a card or escalation for the second; the false-gap rate = questions asked that change nothing about what gets built | SHOW | S6 |

## 12. Phase I: Integrate (coordinator, on `main`)

### 12.1 Merge order

Phase H0 first (the two config keys, on `main`, before any phase H worktree). Phase H: SELECT, STALE, START (each `git merge --no-ff` with its rows' `SR:` trailers, the
focused set once on `main` after each; a merge that the merge hold stops is verified by content
and recorded with `git -c plumb.mergeHold=false`). Phase L: ENGINE, READ, JUDGE, SHOW (SHOW
last: it edits `install.py`, `verify/` and `boundary/`, which the others do not). Conflicts on
`docs/followups.md` are append-merges. Before each merge, merge the current `main` into the lane
(plumb-66 also commits on `main`); never force-push or reset `main`.

### 12.2 End-to-end flows

`tests/understand/test_e2e_flows.py` (coordinator) on the harness of 3.2 item 9, through the
real hook entry points with `FakeDispatcher`: (1) a request with gaps: prompt hook closes the
gate and queues the job, an edit is refused, `clarify --wait` returns the card, the owner
answers in one message, the read job applies before the clarify job runs, the gate opens, no
second card; (2) a mixed answer ("INT-008 ok ... not sure about SR-088"): one read job, one
confirmed by words, one change, the status line says "reading your answer" meanwhile; (3)
capture of an intent and six requirements: one judge job, trial batch, owner yes, recalibration
without a model call, requirements switch settling on by themselves, the settled line with Undo,
undo reopens it; (4) the backlog pass on 40 proposed records with a failure midway and a resume;
(5) every failure of spec 9.1: nothing confirmed, "couldn't check", retry next turn; (6) a
result file and a job file written by the agent confirm nothing; (7) `STALE`: an edit names the
stale link, an unresolved link holds the turn, a reformat is repinned. Every owner-visible text
the flows capture passes both owner-text scanners. The dispatchers' live tests run where their
host or credential exists.

### 12.3 The evaluation set against the configured model

`plumb understand eval` once on the configured dispatcher (Claude Code: Haiku through
`claude -p`), then `plumb jev calibrate`; both results, with the clarifier's false-gap rate,
go to the owner in the next summary. A failing read or judge case blocks the switch-on of
settling for its kind (spec 7), not the merge.

### 12.4 Targeted validation and the one reason for a full run

`plumb tests run --paths <every file the batch changed> --budget 900` (SELECT's selection, on
two workers), then the focused sets once on `main`. No full suite unless plumb names a reason.
It will: this batch changes `pyproject.toml` and `uv.lock` (the `coverage` dependency) and
`verify/pytest_plugin.py`, all `verify.infra_globs`, so plumb reports full verification pending.
The coordinator then runs `plumb merge-check` once on the merged `main` (serial, one run, never
a second; failures triaged under the failure policy: a flaky node reruns once on the same tree,
a real failure is fixed with the lane's focused set). The owner may waive that run (owner
question 4); the coordinator never does.

### 12.5 Integrate gate

```
.venv/Scripts/python.exe -m plumb tests run --paths <every file the batch changed> --budget 900
.venv/Scripts/python.exe -m pytest tests/understand/test_e2e_flows.py tests/host/test_session_cold.py tests/host/test_hook_perf.py -q -p no:cacheprovider
.venv/Scripts/python.exe -m plumb merge-check       # the one run, if plumb still names a reason and the owner has not waived it
.venv/Scripts/python.exe -m plumb validate
.venv/Scripts/python.exe -m plumb drift
.venv/Scripts/python.exe -m plumb claims check --range <base>..HEAD
```

and `docs/concept.md` (the sections on intent capture, approvals and the hooks), `docs/hosts.md`
(the dispatchers, the gate's Claude Code scope) and `docs/specs/sp8-intent-by-exception.md`
(spec 4.4's progress path and the `go` command) describe the shipped behaviour.

## 13. Phase R: Review

Independent verifiers read the owner's words (INT-028 to INT-030, DEC-027 to DEC-031, the
quotes of the SR-101 to SR-111 records), the spec and the merged code. They exercise at least:
the owner's mixed message of 9.3 through the real hooks; a result file and a job file forged by
the agent; a prose "turn settling on" and "undo that"; an edit while the gate is closed and
after `go`; a dispatcher that fails at each step; a stale link made by an edit and by a
reworded intent; the cold session start; the status line during a read job and a backlog pass.
Findings that contradict or omit the owner's explicit words, decisions or rulings are fixed by
the coordinator, whole class (name the guarantee, enumerate every entry point, fix at one
choke point, one test per entry point); others go to `docs/followups.md` under "SP8 review".

## 14. Definition of done

1. Every example of SR-101 to SR-108, SR-110 and SR-111 has a passing test named in sections 5
   to 11 (the matrix below), and spec 9.3's evaluation set has run on the configured model.
2. `plumb show SR-1xx` lists linked code and tests for each; `plumb validate`, `plumb drift`
   and `plumb claims check` are clean.
3. Session start is inside its budget cold and warm on plumb's own records (HC5).
4. The word rules, the agent's `plumb relay` and the automatic approval of SR-041 are gone only
   where the owner confirmed their requirements' replacement (R6, R8, J9, S5); otherwise they stay,
   named in the review as waiting on the owner.
5. Every SP8 record stays proposed: the owner confirms them himself.

### 14.1 Example coverage matrix

| SR | Examples and the task that tests each |
|---|---|
| SR-101 | EX-1 R2; EX-2 R2; EX-3 R2; EX-4 R2; EX-5 R2; EX-6 R5; EX-7 E3; EX-8 R5; EX-9 R6 (after the owner's confirmation); EX-10 R5; EX-11 R4; EX-12 R1; EX-13 R2 and E6; EX-14 R3 |
| SR-102 | EX-1 J9; EX-2 J9; EX-3 J9; EX-4 J1; EX-5 J1; EX-6 J1; EX-7 J3 and J2; EX-8 J2 |
| SR-103 | EX-1 S1; EX-2 S1; EX-3 S1; EX-4 S1; EX-5 S3 and S4; EX-6 S3; EX-7 S3; EX-8 S1; EX-9 S1, E3 and R4 (order of the jobs: E3; flow 12.2 (1)); EX-10 S3 and R4; EX-11 S3; EX-12 S6 |
| SR-104 | EX-1 E5; EX-2 E5; EX-3 E4; EX-4 E2; EX-5 E4; EX-6 E1; EX-7 E3; EX-8 R1; EX-9 J3; EX-10 E6; EX-11 E6; EX-12 E6 |
| SR-105 | EX-1 J7; EX-2 J7; EX-3 J6; EX-4 R4; EX-5 R4; EX-6 R5; EX-7 J8 |
| SR-106 | EX-1 J4; EX-2 J5; EX-3 J5; EX-4 R5; EX-5 J5; EX-6 J4; EX-7 J4; EX-8 J5; EX-9 J5; EX-10 J5 |
| SR-107 | EX-1 J8; EX-2 J8; EX-3 J8; EX-4 R4; EX-5 J8; EX-6 J8; EX-7 J8 |
| SR-108 | EX-1 P1; EX-2 P1; EX-3 P2; EX-4 P1; EX-5 P1; EX-6 P2; EX-7 P1 |
| SR-110 | EX-1 HB4; EX-2 HB4; EX-3 HB5 |
| SR-111 | EX-1 HA1 and HA2; EX-2 HA3; EX-3 HA4; EX-4 HA5; EX-5 HA5 (stale card in STALE's own file), carried by J7 into the summary |
| Spec 9.3 | evaluation set: R7, J9, S6 (11.1); one dispatcher end-to-end test each: E1, E7 (marked `dispatch_live`); batching and progress: E5, E6, J3, J8 |

## 15. Questions for the owner

Asked in the owner's terms in the next summary; none blocks a lane (each has the stated
default):

1. When you confirm the new wording of the requirements the reader replaces (SR-005, SR-088,
   SR-090, SR-098, SR-041, SR-043), may the tests that only checked the old word-matching be
   removed with them? Until you confirm, those tests and rules stay, and so does your agent's
   ability to pass on your words by itself (R6, R8, J9, S5 wait).
2. If plumb holds your agent's turn open for a link it made stale, how many tries before it
   stops holding and brings you a card instead? Default: three.
3. Until the new model worker exists, which model decides that a changed piece of code still
   means the same thing? Default: the judgment model already set up for plumb; with none
   reachable, the agent brings you a card.
4. Changing the test tools (a coverage dependency and the test plugin) makes plumb ask for one
   full test run at the end. Run it, or waive it?
5. The check after every edit adds a second small step (about a tenth of a second) next to the
   existing quiet one, so the existing hook stays unchanged. Acceptable?
