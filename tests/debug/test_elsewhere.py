"""SR-327: outside iaso's own repository a debug case whose rerun fails again ends with a
defect report and changes nothing, unless the configuration turns self-debug on and names
iaso's source checkout (then the fix lands on a branch there); issue reporting files one
issue per case through gh. gh is a fake executable on PATH; the fixer and the runner are
scripted; git is real."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from iaso import debug, selfdebug
from iaso.api import open_core
from iaso.cli import main
from iaso.commands import init_repo

pytestmark = pytest.mark.sr("SR-327")

CASE = "hook-stop-1"
LOG = "Traceback ... ValueError: boom"
SECRET = "the-repositorys-own-secret"
TEST = "tests/test_calc.py::test_add"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout


def _config(repo: Path, text: str) -> None:
    (repo / ".iaso" / "config.yaml").write_text(text, "utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "config")


@pytest.fixture
def case_repo(repo: Path) -> Path:
    """Another repository (not iaso's own) with code of its own and one open debug case."""
    (repo / "app.py").write_text(f"# {SECRET}\n", "utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "app")
    debug.open_case(repo, id=CASE, kind="hook-error", target="stop", detail="ValueError: boom",
                    log=LOG)
    return repo


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A iaso-shaped source checkout with a defect in src/iaso/calc.py."""
    root = tmp_path / "iaso-src"
    (root / "src" / "iaso").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "iaso"\n', "utf-8")
    (root / "src" / "iaso" / "__init__.py").write_text("", "utf-8")
    (root / "src" / "iaso" / "calc.py").write_text("def add(a, b):\n    return a - b\n", "utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "core.autocrlf", "false")
    (root / ".iaso").mkdir()   # an old repository, as tests/conftest.py's repo (SR-431)
    init_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "setup")
    return root


@pytest.fixture
def gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake gh on PATH: it appends its arguments and its stdin to a log, prints an url."""
    bin_dir, log = tmp_path / "bin", tmp_path / "gh.log"
    bin_dir.mkdir()
    script = bin_dir / "gh.py"
    script.write_text(
        "import sys\nopen(sys.argv[1], 'a', encoding='utf-8').write(\n"
        "    ' '.join(sys.argv[2:]) + '\\n' + sys.stdin.read() + '\\n---\\n')\n"
        "print('https://github.com/Cols77/iaso/issues/1')\n", "utf-8")
    if sys.platform == "win32":
        (bin_dir / "gh.cmd").write_text(f'@"{sys.executable}" "{script}" "{log}" %*\r\n', "utf-8")
    else:
        launcher = bin_dir / "gh"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "{log}" "$@"\n',
                            "utf-8")
        launcher.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return log


def _case(repo: Path) -> dict:
    return next(c for c in debug.all_cases(repo) if c["id"] == CASE)


def _debug(repo: Path) -> int:
    return main(["debug", "--root", str(repo)])


def test_ex1_self_debug_off_ends_with_a_defect_report_and_changes_no_code(
        case_repo: Path) -> None:
    assert _debug(case_repo) == 1
    row = _case(case_repo)
    assert row["state"] == "open"
    for part in (CASE, "ValueError: boom", LOG, "Repro: iaso debug", "Missing:"):
        assert part in row["report"]
    assert _git(case_repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert not (case_repo / ".iaso" / "wt").exists()


def test_ex2_self_debug_on_with_a_source_lands_the_fix_on_a_branch_of_the_source(
        case_repo: Path, source: Path) -> None:
    _config(case_repo, f"debug:\n  self_fix: true\n  source: '{source.as_posix()}'\n")
    head = _git(case_repo, "rev-parse", "HEAD")
    calc = source / ".iaso" / "wt" / f"debug-{CASE}" / "src" / "iaso" / "calc.py"

    def fixer(**kw) -> dict:
        wt = kw["worktree"]
        (wt / "tests").mkdir(exist_ok=True)
        (wt / "tests" / "test_calc.py").write_text(
            "from iaso.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n", "utf-8")
        (wt / "src" / "iaso" / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                                      "utf-8")
        return {"test": TEST}

    def runner(paths):
        return "return a + b" in calc.read_text("utf-8"), "ran"

    core = open_core(case_repo)
    assert selfdebug.applies(core) is None
    from debug.staged import ok_stages  # SR-388: the diagnosis and the review, scripted

    out = selfdebug.handle(core, _case(case_repo), fixer=fixer, runner=runner, **ok_stages())
    assert out.state == "fixed", out.detail
    assert "return a + b" in _git(source, "show", f"debug/{CASE}:src/iaso/calc.py")
    assert _git(source, "show", f"debug/{CASE}:tests/test_calc.py")
    assert [e.payload["case"] for e in open_core(source).log_read(
        "events", ["selfdebug-review"])] == [CASE]
    assert _case(case_repo)["state"] == "resolved"
    assert _git(case_repo, "rev-parse", "HEAD") == head
    assert _git(case_repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert (case_repo / "app.py").read_text("utf-8") == f"# {SECRET}\n"


def test_ex3_self_debug_on_without_a_source_says_once_what_is_missing_and_reports(
        case_repo: Path, capsys) -> None:
    _config(case_repo, "debug:\n  self_fix: true\n")
    assert _debug(case_repo) == 1
    assert capsys.readouterr().out.count("debug.source names no iaso checkout") == 1
    assert "debug.source" in _case(case_repo)["report"]
    assert selfdebug.report_elsewhere(open_core(case_repo), _case(case_repo)).line == ""


def test_ex4_issue_reporting_files_one_issue_with_the_case_and_log_and_never_the_repository(
        case_repo: Path, gh: Path) -> None:
    _config(case_repo, "debug:\n  report_issues: true\n")
    (case_repo / ".iaso" / "intents" / "INT-001.md").write_text(
        f"---\nid: INT-001\n---\n{SECRET}\n", "utf-8")
    assert _debug(case_repo) == 1
    row = _case(case_repo)
    assert row["issue"] == "https://github.com/Cols77/iaso/issues/1"
    sent = gh.read_text("utf-8")
    assert sent.count("issue create -R Cols77/iaso") == 1
    for part in (CASE, "ValueError: boom", LOG, "Repro: iaso debug"):
        assert part in sent
    assert SECRET not in sent
    selfdebug.report_elsewhere(open_core(case_repo), row)
    assert gh.read_text("utf-8").count("issue create") == 1


def test_ex5_issue_reporting_off_or_without_gh_files_no_issue(
        case_repo: Path, gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _debug(case_repo) == 1
    assert not gh.exists() and "issue" not in _case(case_repo)
    _config(case_repo, "debug:\n  report_issues: true\n")
    monkeypatch.setattr("shutil.which", lambda name, *a, **k: None)
    selfdebug.report_elsewhere(open_core(case_repo), _case(case_repo))
    assert not gh.exists() and "issue" not in _case(case_repo)
    assert "Missing:" in _case(case_repo)["report"]
