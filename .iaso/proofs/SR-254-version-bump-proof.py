"""SR-254 EX-24/EX-25 proof: after a green full run, does a [project] version bump of pyproject.toml
set a full run pending, and what does the merge check run after main moves with one? Run with
PYTHONPATH=<checkout>/src (intent/version-bump-not-infra, then main for contrast).
Committed at .iaso/proofs/SR-254-version-bump-proof.py; its output is the evidence beside it."""
import shutil, subprocess, sys, tempfile
from pathlib import Path

import iaso
from iaso.api import open_core
from iaso.boundary import fullrun
from iaso.verify import open_verify

PYPROJECT = ('[project]\nname = "pkg"\nversion = "0.1.1"\n\n[tool.pytest.ini_options]\n'
             'pythonpath = ["src"]\ntestpaths = ["tests"]\n')
FILES = {
    "pyproject.toml": PYPROJECT,
    "src/pkg/__init__.py": "",
    "src/pkg/mod.py": "def add(a, b):\n    return a + b\n",
    "src/pkg/other.py": "def mul(a, b):\n    return a * b\n",
    "tests/test_mod.py": "from pkg.mod import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    "tests/test_other.py": "from pkg.other import mul\n\ndef test_mul():\n    assert mul(2, 3) == 6\n\n"
                           "def test_mul_zero():\n    assert mul(0, 5) == 0\n",
}
BUMP = PYPROJECT.replace('"0.1.1"', '"0.1.2"')
SETTING = BUMP + 'addopts = "-q"\n'  # a pytest setting: shared test infrastructure
NEW_MOD = "def add(a, b):\n    return b + a\n"
CODE = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=Path(iaso.__file__).parent,
                      capture_output=True, text=True).stdout.strip()  # the branch of the code under test


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=p", "-c", "user.email=p@p", *args], cwd=repo,
                   check=True, capture_output=True)


def write(repo, files):
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")


def green_repo():
    repo = Path(tempfile.mkdtemp(prefix="bump-proof-"))
    git(repo, "init", "-q", "-b", "main")
    subprocess.run([sys.executable, "-m", "iaso", "init", "--root", str(repo)], check=True,
                   capture_output=True)
    write(repo, FILES)
    (repo / ".iaso" / "config.yaml").write_text("verify:\n  flaky_rerun: false\n", encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "base")
    full = open_verify(open_core(repo)).run(full=True)
    assert full.ok, "the base full run must pass"
    return repo, len(full.outcomes)


def merge_check_run(repo):
    """What the merge check's run step runs (fullrun.full_run, as merge-check --run calls it)."""
    core = open_core(repo)
    out = fullrun.full_run(core, open_verify(core), pending=True, reasons=["main moved"],
                           unverified=False, waived=False, run_full=True, runner=None)
    run = [e.payload for e in open_core(repo).log_read("evidence", kinds=["test-run"])][-1]
    ran = sorted({str(n.get("id") or n.get("nodeid")) for n in run.get("nodes") or ()})
    kind = "only the affected tests" if out.get("delta") else "the full suite"
    return f"{kind}: {len(ran)} test(s) {ran}, verdict {out['verdict']}"


print(f"code under test: {CODE}")
for name, text, also in (("a [project] version bump only", BUMP, {}),
                         ("a version bump and main moving src/pkg/mod.py", BUMP,
                          {"src/pkg/mod.py": NEW_MOD}),
                         ("a version bump plus a pytest setting, and src/pkg/mod.py", SETTING,
                          {"src/pkg/mod.py": NEW_MOD})):
    repo, n = green_repo()
    try:
        write(repo, {"pyproject.toml": text, **also})
        git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", f"main moved: {name}")
        pending = open_verify(open_core(repo)).full_pending()
        print(f"\nafter a green full run ({n} tests), {name}:")
        print(f"  full run pending: {pending.pending} {list(pending.reasons)}")
        if also:
            print(f"  the merge check's run step ran {merge_check_run(repo)}")
    finally:
        shutil.rmtree(repo, ignore_errors=True)
