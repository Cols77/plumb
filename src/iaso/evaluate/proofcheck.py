"""SR-397, SR-398, SR-399: the independent proof evaluator. A fresh headless session that took
no part in the build is given a requirement, its examples, the proof and the built tree, writes
and runs an evaluation case, and ends on one verdict. ``evaluate_proofs`` runs one per proof,
side by side, and records each verdict through ``proof.record_verdict`` (the only writer)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iaso.evaluate import run as runmod

VERDICTS = ("verified", "not verified", "could not check")
TREE_NOT_HELD = "the evaluator changed the built tree"   # DEC-471

BRIEF = """\
You are an independent evaluator. You did not build this change and you see nothing of the \
builder's conversation. You are given a requirement, its examples, the proof its owner asked \
for, and the path of the built tree. Read the tree; never change it.

Write an evaluation case and run it. When the proof needs a session of the agent under iaso, \
write a case folder (requests.json, owner.md, agent.md, checks/test_*.py) and run \
`iaso evaluate case <folder> --runs-dir runs`: it makes a scratch repository with this tree's \
iaso set up, sends each request as a headless turn, lets the scripted owner answer the \
questions, runs the checks and leaves transcript.jsonl, score.json and the scratch \
repository's .iaso/ in the run folder. Otherwise run the proof's command yourself.

Your case must reach what each example's "given" states before it can judge the "then": read \
the tree's own documentation to learn how that state is reached (the commands its owner types, \
the skills its agent follows) and set it up in the case. A case that never reached the "given" \
shows nothing either way: that is "could not check", never "not verified".

Your shell runs only plain commands that start with python, python3, iaso, git, pytest, ls, \
cat or echo: no cd, no &&, no pipes, no variables in front. Name folders by absolute path and \
with each tool's own option (git -C, iaso's --root, a path given to pytest).

Be strict: verified only when you saw what the proof states. End by writing verdict.json in \
your working folder: {"verdict": "verified" | "not verified" | "could not check", \
"summary": "<what you saw, or what was not shown, or why you could not check>"}.
"""


@dataclass
class Verdict:
    name: str
    verdict: str
    summary: str
    run_dir: Path


def subject(record: Any) -> str:
    """What the evaluator is given: the requirement, its examples and the proof. Nothing else."""
    from iaso.capture import proof

    plan = proof.proof_of(record) or {}
    shown = [f"{record.id}: {record.title}", str(record.fields.get("statement") or "")]
    shown += [f"{e.id}: given {e.given}; when {e.when}; then {e.then}" for e in record.examples]
    shown.append(f"Proof ({plan.get('kind', 'other')}): {plan.get('plan', '')}")
    return "\n".join(shown) + "\n"


def _fingerprint(root: Path) -> str:
    """DEC-471: the tree's content (status, the diff against HEAD and every untracked file), so
    an edit to a file that was already modified or untracked is seen too. The run folders and
    iaso's own log and session files are left out: other sessions write them meanwhile."""
    def git(*args: str) -> bytes:
        return subprocess.run(["git", "-C", str(root), *args, "--", ".",
                               *(f":!.iaso/{d}" for d in ("eval", "log", "session"))],
                              capture_output=True).stdout

    seen = hashlib.sha256(git("status", "--porcelain") + git("diff", "HEAD"))
    for name in filter(None, git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")):
        seen.update(name)
        path = root / os.fsdecode(name)
        if path.is_file():
            seen.update(path.read_bytes())
    return seen.hexdigest()


def _read_verdict(workspace: Path) -> tuple[str, str]:
    try:
        data = json.loads((workspace / "verdict.json").read_text(encoding="utf-8"))
        verdict, summary = data["verdict"], str(data["summary"]).strip()
    except (OSError, ValueError, KeyError, TypeError):
        return "could not check", "the evaluator wrote no valid verdict.json"
    if verdict not in VERDICTS or not summary:
        return "could not check", "the evaluator wrote no valid verdict.json"
    return verdict, summary


def evaluate(root: Path, name: str, subject: str, *, model: str = "sonnet", minutes: int = 30,
             claude: Any = runmod._claude_call, binary: str | None = None,
             runs_dir: Path | None = None) -> Verdict:
    """SR-397 EX-7: one fresh session (no ``--resume``) in a folder outside the repository."""
    root = Path(root)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    run_dir = runmod._new_run_dir(runs_dir or root / ".iaso" / "eval" / "runs",
                                  f"{stamp}-proof-{name}")
    binary = binary or shutil.which("claude")
    if binary is None:
        verdict, summary = "could not check", "the claude command was not found on this machine"
        return _keep(run_dir, None, name, verdict, summary, "")
    workspace = Path(tempfile.mkdtemp(prefix="iaso-proof-"))
    try:
        before = _fingerprint(root)
        env = dict(os.environ)
        if (root / "src" / "iaso").is_dir():   # the case and the scratch hooks run the tree
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(root / "src"),
                                                              env.get("PYTHONPATH", "")]))
        got = claude(binary, workspace, f"{subject}\nThe built tree is at {root}.", model=model,
                     session_id=None, system=BRIEF, timeout_s=minutes * 60, env=env,
                     max_turns=None, extra=["--add-dir", str(root)],
                     tools=["Read", "Glob", "Grep", "Write", "Edit"])
        verdict, summary = _read_verdict(workspace)
        if got.get("error"):
            verdict, summary = "could not check", f"the evaluator's session failed: {got['error']}"
        elif _fingerprint(root) != before:
            verdict, summary = "could not check", TREE_NOT_HELD
        return _keep(run_dir, workspace, name, verdict, summary, str(got.get("text") or ""))
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _keep(run_dir: Path, workspace: Path | None, name: str, verdict: str, summary: str,
          reply: str) -> Verdict:
    if workspace is not None:
        shutil.copytree(workspace, run_dir, dirs_exist_ok=True)
    (run_dir / "evaluator.txt").write_text(reply, encoding="utf-8")
    (run_dir / "verdict.json").write_text(
        json.dumps({"name": name, "verdict": verdict, "summary": summary}, indent=1),
        encoding="utf-8")
    return Verdict(name, verdict, summary, run_dir)


def evaluate_proofs(core: Any, ids: list[str], *, run: Any = evaluate,
                    **kw: Any) -> list[dict[str, Any]]:
    """SR-399: one evaluator per proof, at the same time; SR-397: each verdict recorded here, in
    ``ids`` order. Refused before anything runs for a proof the owner did not pick it for."""
    from iaso.capture import proof

    ids = list(dict.fromkeys(ids))
    records = [proof._requirement(core, i) for i in ids]
    for record in records:
        if not proof.evaluator_picked(record):
            raise ValueError(f"the owner did not pick the evaluator for {record.id}: show the "
                             f"proof and ask them, iaso proof {record.id} --ask")
    def one(record: Any) -> Verdict:
        try:
            return run(Path(core.root), record.id, subject(record), **kw)
        except Exception as exc:  # noqa: BLE001 - one evaluator's crash keeps the others' verdicts
            return Verdict(record.id, "could not check",
                           f"the evaluator's run failed: {type(exc).__name__}: {exc}", Path())

    with ThreadPoolExecutor(max_workers=len(ids)) as pool:
        verdicts = list(pool.map(one, records))
    given = {r.id: r.hash for r in records}
    from iaso.api import open_core

    core = open_core(core.root)   # the records as they are now, not as read before the runs
    rows = []
    for v in verdicts:
        if v.verdict != "could not check" and core.index()[v.name].hash != given[v.name]:
            # SR-397 EX-6: a verdict counts only for the words the evaluator was given
            v = Verdict(v.name, "could not check",
                        "the requirement was reworded while the evaluator ran", v.run_dir)
        got = proof.record_verdict(core, v.name, v.verdict, v.summary, str(v.run_dir))
        rows.append({"id": v.name, "verdict": v.verdict, "summary": v.summary,
                     "run_dir": str(v.run_dir), "retry_left": got.get("retry_left", False)})
    return rows


def lines(rows: list[dict[str, Any]]) -> list[str]:
    """SR-397, SR-398: what the agent does next, one line per proof."""
    out = []
    for r in rows:
        i, why = r["id"], r["summary"]
        if r["verdict"] == "verified":
            out.append(f"iaso: {i} verified: {why} (evidence: {r['run_dir']}); tell the owner "
                       "this verdict and where the evidence is; ask nothing")
        elif r["verdict"] == "not verified" and r["retry_left"]:
            out.append(f"iaso: {i} not verified: {why}; fix it and run iaso evaluate proof "
                       f"{i} again; the owner is not asked")
        elif r["verdict"] == "not verified":
            out.append(f"iaso: {i} still not verified after the retry: tell the owner in one "
                       f"plain line what was not shown ({why}); the loop stays open and "
                       "nothing is merged")
        else:
            out.append(f"iaso: {i} could not be checked: {why}; show it yourself, record it "
                       f"(iaso proof {i} --evidence ... --summary ... --passed) and ask the "
                       f"owner (iaso proof {i} --ask)")
    return out


def check_fix(root: Path, case: dict[str, Any], branch: str, *, run: Any = evaluate,
              **kw: Any) -> str:
    """SR-396 EX-5, DEC-470: "" when the evaluator verified the fix of ``case`` on the worktree
    holding ``branch``, else the summary (not verified and could not check alike)."""
    from iaso import selfdebug

    tree = selfdebug._checked_out(Path(root), branch)
    if tree is None:   # never judge another tree in the fix's place
        return f"no worktree holds {branch}: the fix could not be checked"
    reported = case.get("detail") or case.get("what") or case.get("id")
    text = (f"Defect {case.get('id')}: {reported}\n\nCheck on this tree that the reported "
            "behaviour is gone.\n")
    v = run(tree, f"fix-{case.get('id')}", text, **kw)
    return "" if v.verdict == "verified" else v.summary
