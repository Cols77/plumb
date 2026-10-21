# plumb evaluate (INT-105): a cheap benchmark of plumb run by a cheap model

Intent: INT-105. Requirements: SR-344 (the run), SR-345 (the scripted owner), SR-346 (the
score), SR-347 (the issues file), SR-348 (evaluate, debug, merge, evaluate again), SR-349 (the
two tasks). Decisions: DEC-303 to DEC-312. Proof (all six, kind command): one live run of
`plumb evaluate simple --model haiku`, its printed score line, its run folder, and for SR-348 the
round lines of `plumb evaluate simple --loop 2` (`plumb proof SR-34x --evidence`).

Build on main in this checkout (the loop's session is 188a3d82). Tests run with at most `-n 2`
under `.git/plumb-heavy.lock`. No new dependency: subprocess, json, re, shutil, tempfile.

## What exists and is reused

- `plumb.understand.dispatch.claude_code.ClaudeCodeDispatcher`: one `claude -p` call with a
  plumb-shipped agent (`understand/agents/<kind>.md`), no tools, a JSON schema, in an empty temp
  dir. The scripted owner is one more kind, `owner`.
- `plumb.selfdebug.FixerDispatcher.command` shows the headless flags; `selfdebug.fix(core, case,
  fixer=, runner=, judge=)` is the debug round (worktree + branch `debug/<slug>`); its `Outcome.state`
  is `fixed | owner | held | reported`.
- `plumb.debug.open_case(root, id=, kind=, target=, detail=, log=)` writes one case file under
  `.plumb/cache/debug/`, idempotent on id; `debug._case_path(root, id)`.
- `plumb.commands.init_repo(root)` adopts a repository; `plumb.hosts.claude_code.install.install(root)`
  writes plumb's hooks and skills into `<root>/.claude/settings.json` (the owner's choice, DEC-306).
- `plumb.api.open_core(root)`: `core.index()` (records by id, `.kind`), `core.link_states()`
  (`.state` in stale|dangling|...), `core.paths`.
- Plumb's log: one JSON file per entry under `.plumb/log/<kind>/`; an intent gate is
  `core.log_append("events", "intent-gate", {...})`, a proof shown is a `proof` evidence on the SR
  file (`plumb.capture.proof.not_shown(core, ids)` says which lack it).
- CLI routing: `ROUTES` in `src/plumb/cli.py` (`"evaluate": "plumb.evaluate.cli"`), the help text
  in the same file (a `development:` line next to `understand`).

## Layout

```
src/plumb/evaluate/__init__.py
src/plumb/evaluate/cli.py          run(command, argv): plumb evaluate <task> [--model M] [--owner-model M] [--loop N] [--runs-dir D]
src/plumb/evaluate/run.py          run_task(...) -> RunResult; the scratch repository; one turn per request
src/plumb/evaluate/owner.py        ScriptedOwner: answers from the hidden brief, or says nothing is asked
src/plumb/evaluate/score.py        checks(...) and trail(...) -> score dict; line(score) -> str
src/plumb/evaluate/issues.py       collect(...) and open_cases(...)
src/plumb/evaluate/loop.py         run_loop(...): evaluate, debug, merge, evaluate again
src/plumb/evaluate/tasks.py        load(task) -> Task (agent brief, owner brief, requests, checks dir)
src/plumb/evaluate/tasks/simple/{agent.md,owner.md,requests.json,checks/test_game.py}
src/plumb/evaluate/tasks/complex/{agent.md,owner.md,requests.json,checks/test_expenses.py}
src/plumb/understand/agents/owner.md
tests/evaluate/{conftest.py,test_run.py,test_owner.py,test_score.py,test_issues.py,test_loop.py,test_tasks.py}
```

`pyproject.toml`'s package data must ship `evaluate/tasks/**` (check how `understand/agents/*.md`
and `understand/evalset/*.json` are shipped and do the same).

## Shared contracts (every item codes against these)

```python
# tasks.py
@dataclass(frozen=True)
class Task:
    name: str                 # simple | complex
    agent_brief: str          # tasks/<name>/agent.md: the contract the agent builds to, plus the issues rule
    owner_brief: str          # tasks/<name>/owner.md: the hidden full picture for the scripted owner
    requests: list[str]       # tasks/<name>/requests.json: a JSON list of owner messages, in order
    checks: Path              # tasks/<name>/checks/: pytest files, each test marked `# request: n`
NAMES = ("simple", "complex")
def load(name: str) -> Task          # ValueError on another name

# owner.py
OWNER_SCHEMA = {"type": "object", "required": ["asks", "answer"], "additionalProperties": False,
                "properties": {"asks": {"type": "boolean"}, "answer": {"type": "string"}}}
class ScriptedOwner:
    def __init__(self, model: str = "haiku", dispatcher=None, timeout_s: float = 120): ...
    def answer(self, brief: str, request: str, reply: str) -> dict   # {"asks": bool, "answer": str}
    # system = agents.load("owner") + "\n\n# The owner's picture\n" + brief; user = JSON {request, reply}
    # dispatcher: anything with .run(job, system=, user=, schema=, on_step=) (ClaudeCodeDispatcher by default,
    # kind "owner", model=model); a DispatchError answers {"asks": False, "answer": ""} and is noted in the transcript

# run.py
TURN_CAP = 25            # --max-turns per request
OWNER_CAP = 3            # exchanges per request
RUN_CAP_S = 20 * 60      # per run
@dataclass
class Turn:              # one transcript line, written as JSON
    role: str            # owner | agent
    text: str
    request: int         # 1-based index of the scripted request this turn belongs to
    source: str = ""     # owner: "script" | "scripted-owner"; agent: "" | "capped" | "error"
@dataclass
class RunResult:
    run_dir: Path
    scratch: Path
    score: dict
    issues: list[dict]
    unanswered: int
def scratch_repo(parent: Path) -> Path
    # git init -q, a first commit so hooks work, commands.init_repo, install.install; returns the path
def claude_turn(binary, scratch, message, *, model, session_id, system, timeout_s, env) -> dict
    # the subprocess call: [binary, "-p", "--model", model, "--output-format", "json", "--max-turns", str(TURN_CAP),
    #   "--permission-mode", "acceptEdits", "--setting-sources", "project", "--append-system-prompt", system,
    #   *(["--resume", session_id] if session_id else [])], input=message, cwd=scratch, env without PLUMB_JOB/PLUMB_WORKER
    # returns {"text": result, "session_id": ..., "capped": num_turns >= TURN_CAP or the error names max turns, "error": str|""}
def run_task(root: Path, task: Task, *, model: str, owner: ScriptedOwner, runs_dir: Path | None = None,
             claude=claude_turn, now=time.monotonic, binary: str | None = None) -> RunResult
    # binary None: shutil.which("claude"); not found: raise RuntimeError("the claude command was not found on this machine")
    #   before anything is made (cli prints it as one line, exit 1)
    # run_dir = (runs_dir or root/.plumb/eval/runs) / f"{stamp}-{task.name}-{model}"
    # for n, request in enumerate(task.requests, 1): send it (source "script"); then up to OWNER_CAP times:
    #   verdict = owner.answer(task.owner_brief, request, reply); if not verdict["asks"]: break
    #   send verdict["answer"] (source "scripted-owner"); if the cap is reached and the last reply still asks: unanswered += 1
    # the time left (RUN_CAP_S - elapsed) is each call's timeout; at 0 the request is marked capped and the rest are skipped
    # after the last request: score = score.checks(scratch, task) | score.trail(scratch, transcript, issues)
    #   issues = issues.collect(scratch, run_dir, root, run_id, task.name, model); shutil.copytree(scratch/.plumb, run_dir/plumb)
    #   write score.json; print(score.line(score))

# score.py
def checks(scratch: Path, task: Task, python: str = sys.executable) -> dict
    # copy task.checks/* to scratch/eval_checks/, run [python, "-m", "pytest", "eval_checks", "-q", "-rf", "-p", "no:cacheprovider"]
    # parse "N passed", "N failed" from the summary and the "FAILED eval_checks/...::name" lines
    # -> {"checks_passed": int, "checks_total": int, "failed": [names]}
def trail(scratch: Path, transcript: list[Turn], issues: list[dict], unanswered: int) -> dict
    # records: count files under .plumb/{intents,requirements,decisions}; questions_asked = scripted-owner turns + unanswered,
    # questions_answered = scripted-owner turns; gates = events log entries whose kind/event is "intent-gate";
    # proofs = requirements with evidence (open_core(scratch): the ones not in proof.not_shown); stale = link_states in stale/dangling;
    # issues = len(issues)
def line(task: str, model: str, score: dict) -> str
    # "simple haiku: checks 5/6, records 7, questions 2/2, gates 2, stale 0, issues 3"

# issues.py
ISSUES_FILE = ".plumb/eval-issues.jsonl"        # in the scratch repository, written by the agent
ACCUMULATED = (".plumb", "eval", "issues.jsonl")  # in plumb's repository, tracked
def collect(scratch: Path, run_dir: Path, root: Path, run_id: str, task: str, model: str) -> list[dict]
    # read scratch/ISSUES_FILE (missing: []), keep the JSON lines (skip bad ones), write run_dir/issues.jsonl,
    # append each with {"run": run_id, "task": task, "model": model} to root/ACCUMULATED (unchanged when none)
def case_id(issue: dict) -> str       # "eval-" + sha1(command + "\n" + got)[:8]
def open_cases(root: Path, issues: list[dict]) -> list[str]
    # debug.open_case(root, id=case_id(i), kind="eval-issue", target=i["command"], detail=f"expected: {expected}; got: {got}",
    #   log=context); returns the ids whose file did not exist before (an open case with the same command and got is kept)

# loop.py
def run_loop(root: Path, task: Task, *, model: str, rounds: int, run=run_task, fix=selfdebug.fix,
             merge=merge_branch, **run_kw) -> int
    # for n in 1..rounds: print(f"round {n}"); result = run(root, task, model=model, **run_kw)
    #   if not result.issues: print("stopped: the run filed no issue"); return 0
    #   ids = issues.open_cases(root, result.issues); print(f"cases opened: {len(ids)}")
    #   for id in ids: out = fix(core, case); print(f"  {id}: {out.state}: {out.detail}")
    #     if out.state in ("owner", "held"): print(f"stopped: {id} waits for the owner ({out.detail})"); return 1
    #     if out.state == "fixed": held = merge(root, out.branch); print(f"  merged {out.branch}" or f"stopped: the merge of {branch} is held: {held}"); return 1 when held
    # print("stopped: rounds done"); return 0
def merge_branch(root: Path, branch: str) -> str
    # git merge --no-ff --no-edit -m "Merge <branch>: evaluate fix" <branch> in root; exit 0 -> ""; else git merge --abort and
    # return the hook's last stderr line (what holds it); never --no-verify
```

`.plumb/.gitignore` gains `eval/runs/`. `cli.py` gains the route and this help line under a new
`development:` group: `evaluate     the benchmark: a cheap model works through a task with plumb
(simple|complex; --model, --loop)`.

The agent brief (`tasks/<name>/agent.md`) states the file names and the input/output the owner
will hold it to (the checks hold it to the same), and the issues rule, verbatim in both tasks:

> Whenever plumb behaves wrongly (a refusal you cannot explain, an error, a command or hook line
> that contradicts plumb's skills or its own words, a question you cannot answer), append one
> JSON line to `.plumb/eval-issues.jsonl`: `{"when": ISO time, "command": the plumb command or
> hook, "expected": what you expected, "got": what plumb said, "context": what you were doing}`.
> Then go on with the work.

## The tasks (SR-349)

**simple**, `game.py`, three requests:
1. "Build a two-player tic-tac-toe I can play at the keyboard: `python game.py`. It prints the
   board after every move, prompts `X: ` then `O: ` for a cell number 1 to 9 (1 is top left), rejects
   a taken or invalid cell with `invalid` and asks again, and prints `X wins` or `O wins` when a
   line is made, then exits."
2. "When the board fills with no winner, print `draw`, clear the board and start a new game
   instead of exiting."
3. "Keep a score across games: after each game ends, print `score X <n> O <m>`. An empty line at a
   prompt quits."
Checks (`test_game.py`, each test `# request: n`): a win for X (request 1), an invalid cell then a
valid one (1), a draw line then a fresh board (2), the score line after a win (3), quitting on an
empty line (3), O wins (1). Six checks, run with `subprocess.run([sys.executable, "game.py"],
input=moves, ...)` from the scratch dir.

**complex**, `expenses.py` and `expenses.csv`, five requests:
1. "A command-line expense tracker, `python expenses.py add <YYYY-MM-DD> <category> <amount>
   [note]` and `python expenses.py list` (one line per expense: date, category, amount, note),
   kept in `expenses.csv` beside it. Amounts are decimal, like 12.50."
2. "`python expenses.py report <YYYY-MM>`: the month's total per category, one line
   `<category> <total>`, then `total <sum>`."
3. "`python expenses.py budget <category> <amount>` sets a monthly budget (kept in `budgets.csv`);
   `add` prints `over budget: <category>` when the month's total for that category goes past it."
4. "Amounts are whole cents from now on: `add` and `budget` take an integer number of cents
   (1250, never 12.50), and every amount is printed as cents. Float amounts are refused with
   `invalid amount`. Existing rows in the CSV are converted once."
5. "`python expenses.py import <file.csv>` reads a bank's export whose header is
   `Description,Amount,Date` (date as DD/MM/YYYY, amount in cents, negative for spending) and adds
   each spending row under category `bank`."
Checks (`test_expenses.py`): add then list (1), report of one month (2), over budget warning (3),
float refused after request 4 (4), cents printed (4), import adds the spending rows (5), import
skips income rows (5). Seven checks.

The owner briefs hold the full picture (the same contracts, the reasons, the answers to the
questions a builder would ask: Python 3.12, standard library only, no colours, no AI opponent,
the CSV columns), and the role: "You are the owner. Answer from this picture only, in one or
two plain sentences; when the agent asks nothing, say so."

## Items

Each item names its acceptance tests (one per example), marked `@pytest.mark.sr("SR-3xx")`.
Tests never call a real model or the real `claude`: `claude` is a Python callable double passed
as `claude=`, the owner a `ScriptedOwner(dispatcher=<double>)`, `fix` and `merge` doubles.

1. **tasks.py and the two tasks** (SR-349). `load("simple")`, `load("complex")`, the files above.
   Tests `test_tasks.py`: EX-1 three requests, the first names tic-tac-toe at the keyboard; EX-2 the
   complex fourth request names whole cents; EX-3 every request number 1..n appears as `# request: n`
   in the task's checks and the agent brief names no check (no `test_` or `eval_checks` in it).
   Also: the six simple checks pass against a reference `game.py` kept in the test (short: a
   straight implementation), so the checks are known good; same for the seven complex checks
   against a reference `expenses.py`.
2. **owner.py and agents/owner.md** (SR-345). Tests `test_owner.py` with a dispatcher double that
   records `system`/`user` and returns a canned answer: EX-1 a reply asking the board size gets the
   brief's answer; EX-4 the system holds the brief and the user holds request and reply, never a
   file of the scratch repository (the double asserts no path from `tmp_path` appears); EX-3 and
   EX-2 are run.py's (item 3).
3. **run.py** (SR-344, SR-345 EX-2/EX-3). Tests `test_run.py` with `claude=` a double that returns
   scripted replies per message and records the argv-equivalent (model, session_id, message):
   SR-344 EX-1 the scratch has `.plumb/` and `.claude/settings.json`, every request was sent once in
   order, the run folder has transcript.jsonl, score.json, issues.jsonl and `plumb/`; EX-2 the double
   saw model `sonnet` and the folder name ends `-sonnet`; EX-3 `binary=None` and `which` patched to
   None raises before any folder exists and the cli prints one line; EX-4 a double answering
   `capped: True` marks the agent turn `capped` and the next request is still sent. SR-345 EX-2 an
   owner double that always asks: three exchanges, `unanswered == 1`, the next request sent; EX-3 an
   owner double saying `asks: False` is called once per request and no extra message is sent.
   score/issues are real (the checks dir may be an empty task double with no checks: 0/0).
4. **score.py** (SR-346). Tests `test_score.py`: EX-1 a scratch with a `game.py` that wins but never
   draws (the reference minus the draw) scores 5 of 6 and names the draw check; EX-2 a scratch
   `.plumb/log/events/` with two `intent-gate` entries written through `core.log_append` and one SR
   with evidence (`plumb.capture.proof` API) gives `gates == 2`, `proofs == 1`; EX-3 `line()` renders
   exactly `simple haiku: checks 5/6, records 7, questions 2/2, gates 2, stale 0, issues 3`.
5. **issues.py** (SR-347, SR-348 EX-1/EX-2). Tests `test_issues.py`: SR-347 EX-1 is the agent's
   act (the brief's rule, asserted in item 1's EX-3 companion: the rule text is in both briefs); EX-2
   three lines collected: the run file has three, the accumulated file gained three with run, task,
   model; EX-3 no file: run file empty, accumulated unchanged (byte-equal). SR-348 EX-1
   `open_cases` writes a case of kind `eval-issue` with target, detail and log; EX-2 the same
   command and got twice opens one case and returns one id the first time, none the second.
6. **loop.py** (SR-348 EX-3..EX-7). Tests `test_loop.py` with `run=`, `fix=`, `merge=` doubles:
   EX-3 rounds 3, the second run has no issues: two runs, the line says stopped; EX-4 fix returns
   `owner`: no second run, the line names the case; EX-5 fix returns `fixed` and merge returns "":
   the second run starts and prints its line after the first's; EX-6 (merged through the check) the
   merge double was called with the branch; EX-7 merge returns a hold reason: no second run, the
   reason printed, nothing forced (the double records no `--no-verify`; `merge_branch` itself is
   tested once on a real tmp git repo with a feature branch: merged, and a conflicting branch: the
   reason returned and the tree clean after abort).
7. **cli.py, the route, the help line, `.plumb/.gitignore`, package data.** Test: `plumb evaluate
   nope` exits 2 with usage; `plumb evaluate simple` with `claude` absent prints the one line and
   exits 1 (covers SR-344 EX-3 end to end).
8. **Link the records.** `plumb link SR-344 src/plumb/evaluate/run.py` and so on for each
   requirement's files (implemented_by), and each test file as `verified_by` of its examples
   (the `sr` marker plus `plumb tests map`); `plumb repin --after-tests` for anything stale.
9. **Proof.** The live run (the owner's choice): `plumb evaluate simple --model haiku`, then
   `plumb proof SR-344 --evidence .plumb/eval/runs/<id>/score.json --summary "..." --passed` and
   the same evidence for SR-345, SR-346, SR-347, SR-349; `plumb evaluate simple --loop 2` for SR-348
   (its evidence: the round lines saved to the run folder as `loop.txt`).

## Risks named

- The merge of a fixed branch (item 6) writes the owner's main checkout; it runs only under
  `--loop`, only through the hooks, and aborts on any refusal.
- A live run costs real model calls: Haiku for both roles, at most 25 turns per request and 20
  minutes; the loop adds Sonnet/Opus rounds in self-debug (the configured repin/diagnose models).
- In headless mode the question tool is absent; questions reach the owner as text in the reply,
  which is what the scripted owner reads. plumb's judge questions in the scratch repository's store
  are counted by the trail only when the agent relays them.
