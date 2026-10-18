"""SR-326: a defect of plumb in plumb's own repository becomes a landed fix on a branch of its
own. One git worktree and branch per debug case (the main checkout is never written and never
merged); a fixer (a headless ``claude`` run in the worktree, injectable) names a failing test
and edits plumb; the round is verified (the test fails without the source change and passes
with it, the covering tests pass, nothing is stale, the judge keeps every meaning); then the
fix is committed with the requirement trailer and the case is resolved. Three rounds without
that end as a defect report on the case, for the agent. Nothing here confirms a record."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb import debug

Runner = Callable[[list[str]], tuple[bool, str]]
ID = re.compile(r"\b(?:SR|DEC|INT)-\d+\b")
FIX_SCHEMA = {"type": "object", "required": ["test"], "additionalProperties": True,
              "properties": {"test": {"type": "string"},
                             "files": {"type": "array", "items": {"type": "string"}}}}
SYSTEM = ("You fix a defect in plumb's own code, in the git worktree you run in. Write a test "
          "that fails because of the defect, then change the source under src/ until it "
          "passes. Do not touch .plumb records. Answer with the test as path::name.")


@dataclass
class Outcome:
    state: str                  # fixed | owner | held | reported
    branch: str = ""
    detail: str = ""
    line: str = ""              # a line to say once (the judge could not be reached)
    rounds: list[str] = field(default_factory=list)


def applies(core: Any) -> str | None:
    """None in plumb's own repository; else why self-debug does not run here."""
    root = Path(core.root)
    try:
        own = (root / "src" / "plumb" / "__init__.py").exists() and re.search(
            r'^name\s*=\s*"plumb"', (root / "pyproject.toml").read_text("utf-8"), re.M)
    except OSError:
        own = None
    return None if own else "this is not plumb's own repository"


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", check=check)
    return done.stdout


def _worktree(root: Path, case_id: str) -> tuple[Path, str]:
    slug = re.sub(r"[^a-z0-9]+", "-", case_id.lower()).strip("-")[:40]
    path, branch = root / ".plumb" / "wt" / f"debug-{slug}", f"debug/{slug}"
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
    """``claude -p`` in the worktree with its default tools, loading nothing of the owner's
    setup (``--setting-sources ""``); the model is the round's (DEC-243)."""

    def __init__(self, timeout_s: float = 1800) -> None:
        self.timeout_s = timeout_s

    def command(self, binary: str, model: str) -> list[str]:
        from plumb.understand.dispatch.claude_code import cli_schema

        agent = {"plumb-fixer": {"description": "plumb self-debug fixer", "prompt": SYSTEM}}
        return [binary, "-p", "--agent", "plumb-fixer", "--agents", json.dumps(agent),
                "--model", model, "--permission-mode", "acceptEdits",
                "--json-schema", json.dumps(cli_schema(FIX_SCHEMA)), "--output-format", "json",
                "--no-session-persistence", "--setting-sources", "", "--strict-mcp-config",
                "--disable-slash-commands"]

    def __call__(self, *, round: int, case: dict[str, Any], evidence: dict[str, Any],
                 worktree: Path, model: str, previous: list[str]) -> dict[str, Any]:
        import shutil

        from plumb.understand.dispatch.claude_code import ClaudeCodeDispatcher

        binary = shutil.which("claude")
        if binary is None:
            raise RuntimeError("the claude command was not found on this machine")
        user = json.dumps({"round": round, "evidence": evidence, "earlier_rounds": previous},
                          ensure_ascii=False, indent=1)
        done = subprocess.run(self.command(binary, model), input=user, capture_output=True,
                              text=True, encoding="utf-8", cwd=worktree,
                              timeout=self.timeout_s)
        return dict(ClaudeCodeDispatcher.answer_of(done.stdout, done.returncode, done.stderr,
                                                   FIX_SCHEMA))


def _runner(wt_core: Any) -> Runner:
    """Test ids run through pytest on the worktree's source; source paths through the verify
    lane's covering tests."""
    from plumb.links import default_runner

    covering, wt = default_runner(wt_core), Path(wt_core.root)

    def run(paths: list[str]) -> tuple[bool, str]:
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
        runner: Runner | None = None, judge: Any = None) -> Outcome:
    from plumb import stale
    from plumb.api import open_core
    from plumb.judgment import waiting_line

    root = Path(core.root)
    wt, branch = _worktree(root, case["id"])
    wt_core = open_core(wt)
    session = stale.current_session(root)
    baseline = {s.link.id for s in core.link_states() if s.state in ("stale", "dangling")}
    runner, fixer = runner or _runner(wt_core), fixer or FixerDispatcher()
    evidence, tried = _evidence(core, case), []
    old = os.environ.get("PLUMB_JOB")
    os.environ["PLUMB_JOB"] = "selfdebug"      # a hook in the fixer's run opens no case
    try:
        for n in range(1, rounds + 1):
            model = getattr(core.config.understand, "repin_model" if n == 1
                            else "diagnose_model")
            try:
                got = fixer(round=n, case=case, evidence=evidence, worktree=wt, model=model,
                            previous=list(tried))
                test = str(got.get("test") or "")
                state, why = ("", "") if test else ("fail", "the fixer named no test")
                if not state:
                    state, why = _verify(core, wt_core, wt, test, runner, judge, baseline,
                                         session, case)
            except Exception as exc:  # noqa: BLE001 - a round that crashes is a failed round
                state, why = "fail", f"{type(exc).__name__}: {exc}"
            if state == "owner":
                return Outcome("owner", branch, why, rounds=tried)
            if state == "held":
                line = waiting_line(root, "self-debug", why) or ""
                return Outcome("held", branch, why, line, tried)
            if not state:
                _commit(wt, wt_core, case)
                debug.resolve(root, [case["id"]])
                return Outcome("fixed", branch, f"fixed on {branch}", rounds=tried)
            tried.append(f"round {n}: {why}")
    finally:
        if old is None:
            os.environ.pop("PLUMB_JOB", None)
        else:
            os.environ["PLUMB_JOB"] = old
    text = "; ".join(tried) + f". Missing: {why}. Nothing was committed (branch {branch})."
    debug.report(root, case["id"], text)
    return Outcome("reported", branch, text, rounds=tried)
