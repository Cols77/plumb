"""SR-326: a defect of plumb in plumb's own repository becomes a landed fix on a branch of its
own. One git worktree and branch per debug case (the main checkout is never written and never
merged); a fixer (a headless ``claude`` run in the worktree, injectable) names a failing test
and edits plumb; the round is verified (the test fails without the source change and passes
with it, the covering tests pass, nothing is stale, the judge keeps every meaning); then the
fix is committed with the requirement trailer and the case is resolved. Three rounds without
that end as a defect report on the case, for the agent. Nothing here confirms a record."""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb import debug
from plumb.heavy import heavy

ISSUES_REPO = "Cols77/plumb"
Runner = Callable[[list[str]], tuple[bool, str]]
ID = re.compile(r"\b(?:SR|DEC|INT)-\d+\b")
FIX_SCHEMA = {"type": "object", "required": ["test"], "additionalProperties": True,
              "properties": {"test": {"type": "string"},
                             "files": {"type": "array", "items": {"type": "string"}}}}
DIAGNOSIS_SCHEMA = {"type": "object", "required": ["cause", "path"], "additionalProperties": True,
                    "properties": {"cause": {"type": "string"}, "path": {"type": "string"}}}
REVIEW_SCHEMA = {"type": "object", "required": ["ok", "findings"], "additionalProperties": True,
                 "properties": {"ok": {"type": "boolean"},
                                "findings": {"type": "array", "items": {"type": "string"}}}}
READ_ONLY = "Read,Grep,Glob"       # SR-388: the diagnosis and the review get no editing tool


@dataclass
class Outcome:
    state: str                  # fixed | landed | owner | held | reported
    branch: str = ""
    detail: str = ""
    line: str = ""              # a line to say once (the judge could not be reached)
    rounds: list[str] = field(default_factory=list)


def _own(root: Path) -> bool:
    try:
        return bool((root / "src" / "plumb" / "__init__.py").exists() and re.search(
            r'^name\s*=\s*"plumb"', (root / "pyproject.toml").read_text("utf-8"), re.M))
    except OSError:
        return False


def applies(core: Any) -> str | None:
    """None in plumb's own repository, or elsewhere with ``debug.self_fix`` on and
    ``debug.source`` set (SR-327); else why self-debug does not run here."""
    cfg = core.config.debug
    if _own(Path(core.root)) or (cfg.self_fix and cfg.source):
        return None
    return ("self-debug is on but debug.source names no plumb checkout" if cfg.self_fix
            else "this is not plumb's own repository")


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", check=check)
    return done.stdout


def _slug(case_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", case_id.lower()).strip("-")[:40]


def _checked_out(root: Path, branch: str) -> Path | None:
    """The worktree that has ``branch`` checked out, if any."""
    path = None
    for line in _git(root, "worktree", "list", "--porcelain", check=False).splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:])
        elif line == f"branch refs/heads/{branch}" and path is not None:
            return path
    return None


def _own_commits(root: Path, branch: str) -> bool:
    """The branch moved by something other than its creation or a fast-forward, read from
    its reflog; with no reflog, False."""
    log = _git(root, "reflog", "show", "--format=%gs", f"refs/heads/{branch}", check=False)
    return any(not s.startswith("branch: Created") and not s.endswith("Fast-forward")
               for s in log.splitlines())


def landed(root: Path, branch: str) -> bool:
    """The branch has a commit of its own and its tip is in the root's HEAD (a fix already
    merged); a branch only created, or moved forward to HEAD, is not."""
    if not _own_commits(root, branch):
        return False
    return subprocess.run(["git", "merge-base", "--is-ancestor", f"refs/heads/{branch}",
                           "HEAD"], cwd=root, capture_output=True).returncode == 0


def _worktree(root: Path, case_id: str) -> tuple[Path, str]:
    slug = _slug(case_id)
    path, branch = root / ".plumb" / "wt" / f"debug-{slug}", f"debug/{slug}"
    there = _checked_out(root, branch)
    if there is not None and there.resolve() != root.resolve():   # checked out once: reuse
        if not _own_commits(root, branch) and not _git(
                there, "status", "--porcelain", "--untracked-files=no", check=False).strip():
            _git(there, "merge", "--ff-only", _git(root, "rev-parse", "HEAD").strip(),
                 check=False)                   # current code for the fix
        return there, branch
    if not path.exists():
        known = subprocess.run(["git", "rev-parse", "--verify", "-q", branch], cwd=root,
                               capture_output=True).returncode == 0
        _git(root, "worktree", "add", *([str(path), branch] if known
                                        else ["-b", branch, str(path)]))
    return path, branch


def _evidence(core: Any, case: dict[str, Any]) -> dict[str, Any]:
    from plumb.understand.judge import record_text

    index = core.index()
    ids = dict.fromkeys(ID.findall(f"{case.get('target')} {case.get('detail')}"))
    return {"case": {k: case.get(k) for k in ("id", "kind", "target", "detail")},
            "log": case.get("log", ""),
            "records": {i: record_text(index[i]) for i in ids if i in index}}


class FixerDispatcher:
    """``claude -p`` in the worktree, loading nothing of the owner's setup
    (``--setting-sources ""``); the model is the round's (DEC-243). SR-388: the one stage
    runner: ``agent`` names the prompt, ``schema`` the answer, ``mode`` the permission mode,
    ``tools`` (when set) the only tools the run has."""

    def __init__(self, timeout_s: float = 1800, agent: str = "fixer",
                 schema: dict[str, Any] = FIX_SCHEMA, mode: str = "acceptEdits",
                 tools: str | None = None) -> None:
        self.timeout_s, self.agent, self.schema, self.mode, self.tools = (
            timeout_s, agent, schema, mode, tools)

    def command(self, binary: str, model: str) -> list[str]:
        from plumb.understand import agents
        from plumb.understand.dispatch.claude_code import cli_schema

        return [binary, "-p", "--agent", agents.name(self.agent),
                "--agents", json.dumps(agents.definition(self.agent), ensure_ascii=False),
                "--model", model, "--permission-mode", self.mode,
                *(["--tools", self.tools] if self.tools else []),
                "--json-schema", json.dumps(cli_schema(self.schema)), "--output-format", "json",
                "--no-session-persistence", "--setting-sources", "", "--strict-mcp-config",
                "--disable-slash-commands"]

    def __call__(self, *, round: int, worktree: Path, model: str, previous: list[str],
                 **given: Any) -> dict[str, Any]:
        import shutil

        from plumb.understand.dispatch.claude_code import ClaudeCodeDispatcher

        binary = shutil.which("claude")
        if binary is None:
            raise RuntimeError("the claude command was not found on this machine")
        user = json.dumps({"round": round, **given, "earlier_rounds": previous},
                          ensure_ascii=False, indent=1)
        done = subprocess.run(self.command(binary, model), input=user, capture_output=True,
                              text=True, encoding="utf-8", cwd=worktree,
                              timeout=self.timeout_s)
        return dict(ClaudeCodeDispatcher.answer_of(done.stdout, done.returncode, done.stderr,
                                                   self.schema))


@contextlib.contextmanager
def _out(guard: Any) -> Iterator[None]:
    """SR-388: let go of the worker's ``guard`` (when there is one) while an agent run or a
    test run is out."""
    if guard is None:
        yield
        return
    guard.release()
    try:
        yield
    finally:
        guard.acquire()


_JOB = {"n": 0, "old": None}
_JOB_LOCK = threading.Lock()


@contextlib.contextmanager
def _job_env() -> Iterator[None]:
    """``PLUMB_JOB=selfdebug`` (a hook in an agent's run opens no case) until the last of the
    fixes running at once ends; then what was there before."""
    with _JOB_LOCK:
        if not _JOB["n"]:
            _JOB["old"] = os.environ.get("PLUMB_JOB")
        _JOB["n"] += 1
        os.environ["PLUMB_JOB"] = "selfdebug"
    try:
        yield
    finally:
        with _JOB_LOCK:
            _JOB["n"] -= 1
            if not _JOB["n"]:
                if _JOB["old"] is None:
                    os.environ.pop("PLUMB_JOB", None)
                else:
                    os.environ["PLUMB_JOB"] = str(_JOB["old"])


def _runner(wt_core: Any) -> Runner:
    """Test ids run through pytest on the worktree's source; source paths through the verify
    lane's covering tests. Every run takes the heavy lock (a no-op under its holder)."""
    from plumb.links import default_runner

    covering, wt = default_runner(wt_core), Path(wt_core.root)

    def run(paths: list[str]) -> tuple[bool, str]:
        with heavy(wt, f"selfdebug {wt.name}: pytest"):
            return _run(paths)

    def _run(paths: list[str]) -> tuple[bool, str]:
        if not all(Path(p.split("::")[0]).name.startswith("test_") for p in paths):
            return covering(paths)
        done = subprocess.run(
            [sys.executable, "-m", "pytest", *paths, "-q", "-p", "no:cacheprovider"], cwd=wt,
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONPATH": str(wt / "src")})
        return done.returncode == 0, (done.stdout or done.stderr).strip()[-300:]

    return run


def _changed(wt: Path) -> list[str]:
    _git(wt, "add", "-A")
    return _git(wt, "diff", "--cached", "--name-only", "HEAD").split()


def _staged(wt: Path) -> str:
    """The change in the worktree against HEAD, staged."""
    _changed(wt)
    return _git(wt, "diff", "--cached", "HEAD")


def _undo(wt: Path) -> None:
    _git(wt, "reset", "-q", "--hard", "HEAD")
    _git(wt, "clean", "-fdq")


def _touched(wt_core: Any, wt: Path) -> dict[str, str]:
    """The text of the records that link to a file the change touches."""
    from plumb.understand.judge import record_text

    changed = set(_changed(wt))
    return {r.id: record_text(r) for r in wt_core.index().values()
            if any((link.target.path or "") in changed for link in getattr(r, "links", ()))}


def _fails_without_fix(wt: Path, test: str, runner: Runner) -> bool:
    """The named test must fail with the source change taken out, and the change back after."""
    with tempfile.TemporaryDirectory() as tmp:
        patch = Path(tmp) / "fix.patch"
        _changed(wt)
        patch.write_bytes(subprocess.run(
            ["git", "diff", "--cached", "--binary", "HEAD", "--", "src"], cwd=wt,
            capture_output=True, check=True).stdout)
        if not patch.stat().st_size:
            return False
        _git(wt, "apply", "-R", str(patch))
        try:
            return not runner([test])[0]
        finally:
            _git(wt, "apply", str(patch))


def _verify(core: Any, wt_core: Any, wt: Path, test: str, runner: Runner, judge: Any,
            baseline: set[str], session: str, case: dict[str, Any]) -> tuple[str, str]:
    """``("", "")`` when the round holds, else ``(state, why)``: ``fail`` (try again),
    ``owner`` (a question was filed) or ``held`` (no judge)."""
    from plumb.links import NO_MODEL
    from plumb.understand import judge as judges

    if not runner([test])[0]:
        return "fail", f"the test {test} does not pass with the change"
    if not _fails_without_fix(wt, test, runner):
        return "fail", f"the test {test} does not fail without the source change"
    src = [p for p in _changed(wt) if p.startswith("src/")]
    if src and not (ok := runner(src))[0]:
        return "fail", f"the covering tests do not pass ({ok[1]})"
    states = [s for s in wt_core.link_states() if s.state in ("stale", "dangling")]
    now = {s.link.id for s in states}
    wanted = sorted(now - baseline | ({case["target"]} & now))
    found = debug.cases(wt_core, wanted, session=session, judge=judge, runner=runner) \
        if wanted else []
    core.log_append("events", "selfdebug-review", {"case": case["id"], "links": wanted,
                                                   "cases": found})
    left = [c for c in found if c["state"] != "resolved"]
    asked = judges.open_questions(wt_core, session)
    for question in asked:
        judges.add_question(core, session, question)
    if asked:
        return "owner", "the judge reads a requirement's meaning as changed: one question asked"
    if any(NO_MODEL in c["what"] for c in left):
        return "held", NO_MODEL
    if left:
        return "fail", "; ".join(f"{c['case']} is still open: {c['what']}" for c in left)
    return "", ""


def _commit(wt: Path, wt_core: Any, case: dict[str, Any]) -> None:
    changed = set(_changed(wt))
    srs = sorted({r.id for r in wt_core.index().values() if r.id.startswith("SR-")
                  for link in r.links if (link.target.path or "") in changed})
    text = f"Fix plumb for debug case {case['id']}: {case.get('detail', '')}"[:200]
    text += (f"\n\nSR: {', '.join(srs)}" if srs else "") + \
        "\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
    try:
        _git(wt, "commit", "-q", "-F", f.name)
    finally:
        Path(f.name).unlink(missing_ok=True)


def fix(core: Any, case: dict[str, Any], *, rounds: int = 3, fixer: Any = None,
        runner: Runner | None = None, judge: Any = None, diagnoser: Any = None,
        reviewer: Any = None, guard: Any = None) -> Outcome:
    from plumb import stale
    from plumb.api import open_core
    from plumb.judgment import waiting_line

    root = Path(core.root)
    if not _own(root):
        return handle(core, case, rounds=rounds, fixer=fixer, runner=runner, judge=judge,
                      diagnoser=diagnoser, reviewer=reviewer, guard=guard)
    branch = f"debug/{_slug(case['id'])}"
    if landed(root, branch):        # an earlier fix is in HEAD: nothing to run, nothing to merge
        debug.resolve(root, [case["id"]])
        return Outcome("landed", branch, f"already landed: {branch}")
    wt, branch = _worktree(root, case["id"])
    wt_core = open_core(wt)
    session = stale.current_session(root)
    baseline = {s.link.id for s in core.link_states() if s.state in ("stale", "dangling")}
    own = runner or _runner(wt_core)

    def runner(paths: list[str]) -> tuple[bool, str]:     # type: ignore[misc] # SR-388
        with _out(guard):       # never wait for the heavy lock holding the guard
            return own(paths)

    # SR-388: three stages, three agent runs; the diagnosis and the review are read-only
    fixer = fixer or FixerDispatcher()
    diagnoser = diagnoser or FixerDispatcher(
        agent="diagnoser", schema=DIAGNOSIS_SCHEMA, mode="default", tools=READ_ONLY)
    reviewer = reviewer or FixerDispatcher(
        agent="reviewer", schema=REVIEW_SCHEMA, mode="default", tools=READ_ONLY)
    evidence, tried = _evidence(core, case), []
    from plumb.config import LEVELS, model_of

    cfg = core.config
    models = [{"stage": "evidence", "model": model_of(cfg, cfg.understand.judge_model)}]
    end = ""      # what the case's stage reads once this fix ends: nothing, or why it waits
    first = cfg.understand.repin_model
    base = LEVELS.index(first) if first in LEVELS else 1   # a model name counts as sonnet

    def stage(call: Any, name: str, n: int, level: str, model: str, **given: Any) -> Any:
        models.append({"stage": f"round {n} {name}", "level": level, "model": model})
        debug._update(root, [case["id"]], models=models)   # SR-328: the model per stage
        with _out(guard):
            return call(round=n, case=case, worktree=wt, model=model, previous=list(tried),
                        **given)

    with _job_env():
        try:
            for n in range(1, rounds + 1):
                debug._update(root, [case["id"]], stage="fix", round=n, pid=os.getpid())
                # SR-389: a failed round is retried one level up, never past the largest
                level = first if n == 1 else LEVELS[min(base + n - 1, len(LEVELS) - 1)]
                model = model_of(cfg, level)
                try:
                    before = _staged(wt)
                    said = stage(diagnoser, "diagnosis", n, level, model, evidence=evidence)
                    if _staged(wt) != before:
                        _undo(wt)
                        raise RuntimeError("the diagnosis changed a file")
                    cause = {"cause": str(said.get("cause") or ""),
                             "path": str(said.get("path") or "")}
                    got = stage(fixer, "fix", n, level, model, evidence=evidence,
                                diagnosis=cause)
                    test = str(got.get("test") or "")
                    state, why = ("", "") if test else ("fail", "the fixer named no test")
                    if not state:
                        seen = stage(reviewer, "review", n, level, model, cause=cause,
                                     change=_staged(wt), records=_touched(wt_core, wt))
                        if not seen.get("ok"):
                            state, why = "fail", "the review found: " + "; ".join(
                                map(str, seen.get("findings") or ["it is not ok"]))
                    if not state:
                        debug._update(root, [case["id"]], stage="tests")
                        state, why = _verify(core, wt_core, wt, test, runner, judge, baseline,
                                             session, case)
                except Exception as exc:  # noqa: BLE001 - a round that crashes is a failed round
                    state, why = "fail", f"{type(exc).__name__}: {exc}"
                if state == "owner":
                    end = "owner"
                    return Outcome("owner", branch, why, rounds=tried)
                if state == "held":
                    end = "held"
                    line = waiting_line(root, "self-debug", why) or ""
                    return Outcome("held", branch, why, line, tried)
                if not state:
                    _commit(wt, wt_core, case)
                    debug._update(root, [case["id"]], branch=branch)   # DEC-317: ready to land
                    debug.resolve(root, [case["id"]])
                    return Outcome("fixed", branch, f"fixed on {branch}", rounds=tried)
                tried.append(f"round {n}: {why}")
                if n < rounds:      # the next round starts from HEAD; the last try stays
                    _undo(wt)
        finally:
            debug._update(root, [case["id"]], stage=end, round=0, pid=0)
    text = "; ".join(tried) + f". Missing: {why}. Nothing was committed (branch {branch})."
    debug.report(root, case["id"], text)
    return Outcome("reported", branch, text, rounds=tried)


def handle(core: Any, case: dict[str, Any], **kw: Any) -> Outcome:
    """SR-327: outside plumb's own repository, the fix in the configured source checkout
    (the repository itself is never written), else a defect report."""
    root = Path(core.root)
    cfg = core.config.debug
    if not (cfg.self_fix and cfg.source):
        return report_elsewhere(core, case)
    from plumb.api import open_core

    src = open_core(Path(cfg.source))
    path = debug._case_path(src.root, case["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**case, "state": "open"}), encoding="utf-8")
    out = fix(src, case, **kw)
    if out.state == "fixed":
        debug.resolve(root, [case["id"]])
    elif out.state == "reported":
        debug.report(root, case["id"], out.detail)
    return out


def report_elsewhere(core: Any, case: dict[str, Any]) -> Outcome:
    """SR-327: the defect report for the agent (the case, plumb's log entry, the repro, what
    is missing), nothing changed; with ``debug.report_issues`` and gh, one issue per case
    carrying only that (DEC-247), its url stored on the case."""
    import shutil

    from plumb.judgment import notice_once

    root, cfg = Path(core.root), core.config.debug
    missing = applies(core) or "the fix did not run"
    repro = "plumb debug" + (f" {case['target']}" if case.get("kind") == "stale-refused" else "")
    text = (f"Defect in plumb, case {case['id']} ({case['kind']}): {case.get('detail', '')}\n"
            f"Log entry: {case.get('log') or '(none)'}\nRepro: {repro}\n")
    debug.report(root, case["id"], text + f"Missing: {missing}")
    line = notice_once(root, f"selfdebug:{missing}", f"plumb: self-debug: {missing}; "
                       "the defect is reported, nothing was changed") or ""
    gh = shutil.which("gh")
    if cfg.report_issues and gh and not case.get("issue"):
        done = subprocess.run(
            [gh, "issue", "create", "-R", cfg.issues_repo or ISSUES_REPO, "--title",
             f"plumb defect: {case['kind']}: {str(case.get('detail', ''))[:80]}",
             "--body-file", "-"], input=text, capture_output=True, text=True,
            encoding="utf-8")
        if done.returncode == 0 and done.stdout.strip():
            debug._update(root, [case["id"]], issue=done.stdout.strip().splitlines()[-1])
    return Outcome("reported", detail=text + f"Missing: {missing}", line=line)
