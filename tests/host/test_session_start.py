"""H4: the session-start brief and the first status snapshot (spec 6.1)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fakes import FakeVerify

from plumb.api import open_core
from plumb.contracts import FullPending, NodeEvidence, Target
from plumb.hosts.claude_code import session_start

pytestmark = pytest.mark.sr("SR-009")


@pytest.fixture(autouse=True)
def _roomy_hook_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests check what the brief says, not how fast the machine is: a real hook
    budget (1.4 s) is overrun by any load on a shared machine and adds a 'check skipped'
    line. The cut itself is tested on a fake clock that jumps 5 s, past this budget; the
    hook's real speed is held by test_hook_perf."""
    monkeypatch.setattr(session_start, "hook_budget", lambda name: (lambda root: 4000.0))
    # the triage offer fires whenever the budget leaves room for its judgment; it is held by
    # test_hook_perf, and here would make the line count depend on how much budget is left
    monkeypatch.setattr(session_start, "triage_offer_line", lambda core: None)


def _run(repo: Path, hook_input, **kwargs) -> str:
    out = io.StringIO()
    code = session_start.main(stdin=io.StringIO(hook_input("SessionStart", source="startup")),
                              stdout=out, root=repo, **kwargs)
    assert code == 0
    return out.getvalue()


def _many_records(repo: Path, write_record, count: int = 60) -> None:
    for i in range(1, count + 1):
        write_record(repo, f"---\nid: INT-{i:03d}\ntitle: Intent number {i}\nquote: q{i}\n---\n")
    for i in range(1, 6):
        write_record(repo, f"---\nid: NC-{i:04d}\ntitle: Open problem {i}\nstatus: open\n---\n")


@pytest.mark.sr("SR-032")
def test_brief_is_a_few_lines_and_a_pointer_by_default(repo: Path, write_record,
                                                       hook_input) -> None:
    """R9: the session brief is a few lines plus a pointer, never every proposed record."""
    _many_records(repo, write_record)
    lines = _run(repo, hook_input, verify=FakeVerify()).splitlines()
    assert lines[0] == "plumb brief: 0 feature(s), 0 SR (0 confirmed), 60 INT (0 confirmed)"
    assert len(lines) <= 6
    assert "open NCs: 5 (plumb brief --all)" in lines
    assert any(line.startswith("tests: ") for line in lines)
    assert lines[-1].startswith("plumb: records reach you once per session")
    assert not any("Intent number 7" in line for line in lines)


def test_brief_about_30_lines_with_cap(repo: Path, write_record, hook_input) -> None:
    _many_records(repo, write_record)
    (repo / ".plumb" / "config.yaml").write_text("hooks:\n  session_brief: full\n", "utf-8")
    out = _run(repo, hook_input, verify=FakeVerify())
    lines = out.splitlines()
    assert lines[0].startswith("plumb brief")
    assert 25 <= len(lines) <= 40
    assert any("more (plumb brief --all)" in line for line in lines)


def test_brief_never_passes_hard_cap(repo: Path, write_record, hook_input) -> None:
    _many_records(repo, write_record)
    config = repo / ".plumb" / "config.yaml"
    config.write_text("hooks:\n  brief_lines: 200\n  session_brief: full\n", encoding="utf-8")
    lines = _run(repo, hook_input, verify=None).splitlines()
    assert len(lines) <= 40
    assert any(line.startswith("tests: verification unavailable") for line in lines)


def test_brief_lists_awaiting_confirmation_and_drift(repo: Path, write_record,
                                                      hook_input) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: Links pin both ends\nstatement: s\n---\n")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/a.py"))
    (repo / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    verify = FakeVerify(tests={"SR-001": ("tests/test_a.py::test_x",)},
                        evidence_map={"tests/test_a.py::test_x": NodeEvidence(
                            "tests/test_a.py::test_x", "fresh-fail")},
                        pending=FullPending(True, ("uv.lock",)))
    out = _run(repo, hook_input, verify=verify)
    assert "awaiting your confirmation: 1 proposed (SR-001)" in out
    assert "drift: stale 1" in out
    assert ("tests: 1 failing (tests/test_a.py::test_x) | full verification pending (uv.lock)"
            in out)


def test_writes_status_snapshot(repo: Path, write_record, hook_input) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    _run(repo, hook_input, verify=FakeVerify(pending=FullPending(True, ("pyproject.toml",))))
    data = json.loads((repo / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert data["v"] == 1
    assert data["requirements_total"] == 1 and data["proposed"] == 1
    assert data["full_pending"] is True


def test_context_not_procedure(repo: Path, write_record, hook_input) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    out = _run(repo, hook_input, verify=FakeVerify())
    assert not json.dumps(out).startswith("{\"decision")
    assert "you must" not in out.lower() and "step 1" not in out.lower()


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def __getattr__(self, name: str):
        import time

        return getattr(time, name)


def test_brief_survives_a_budget_cut(repo: Path, write_record, hook_input,
                                     monkeypatch) -> None:
    """On a loaded machine the records brief is printed and only the tests line is cut."""
    import plumb.api
    from plumb.hosts.claude_code import hookio

    clock = _Clock()
    monkeypatch.setattr(hookio, "time", clock)
    write_record(repo, "---\nid: SR-001\ntitle: Links pin both ends\nstatement: s\n---\n")
    real_open = plumb.api.open_core

    class SlowCore:
        def __init__(self, core) -> None:
            self._core = core

        def status(self, *args, **kwargs):
            clock.now += 5.0
            return self._core.status(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._core, name)

    monkeypatch.setattr(plumb.api, "open_core", lambda root: SlowCore(real_open(root)))
    verify = FakeVerify()
    out = _run(repo, hook_input, verify=verify).splitlines()
    assert out[0].startswith("plumb brief")
    assert "awaiting your confirmation: 1 proposed (SR-001)" in out
    assert "tests: not checked (budget)" in out
    assert out[-1] == "plumb: check skipped (budget): tests"


def test_warm_brief_skips_the_test_map(repo: Path, write_record, hook_input,
                                       monkeypatch) -> None:
    """The tests line is cached by the verify fingerprint: a warm session start builds no
    test map (it used to cost 0.65 s of 1.37 s on plumb itself)."""
    import plumb.verify.testmap as testmap

    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_one.py").write_text(
        "import pytest\n\n\n@pytest.mark.sr('SR-001')\ndef test_one():\n    pass\n", "utf-8")
    cold = _run(repo, hook_input)

    def no_build(*args, **kwargs):
        raise AssertionError("test map built on a warm session start")

    monkeypatch.setattr(testmap, "build_map", no_build)
    warm = _run(repo, hook_input)
    assert warm == cold
    assert "tests: 0/1 mapped tests with fresh passing evidence" in warm


def test_status_snapshot_survives_a_budget_cut_of_the_tests_line(
        repo: Path, write_record, hook_input, monkeypatch) -> None:
    """The status line reads this snapshot: when the tests check is cut by the budget the
    snapshot is still written (tests unknown), so the line never keeps an older session's
    state."""
    import plumb.api
    from plumb.hosts.claude_code import hookio

    clock = _Clock()
    monkeypatch.setattr(hookio, "time", clock)
    write_record(repo, "---\nid: SR-001\ntitle: Links pin both ends\nstatement: s\n---\n")
    real_open = plumb.api.open_core

    class SlowCore:
        def __init__(self, core) -> None:
            self._core = core

        def status(self, *args, **kwargs):
            clock.now += 5.0
            return self._core.status(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._core, name)

    monkeypatch.setattr(plumb.api, "open_core", lambda root: SlowCore(real_open(root)))
    out = _run(repo, hook_input, verify=FakeVerify()).splitlines()
    assert out[-1] == "plumb: check skipped (budget): tests"
    data = json.loads((repo / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert data["requirements_total"] == 1 and data["proposed"] == 1


# --- the working tree's leftovers, told once at the start (INT-027) -----------------------

def _git(root: Path, *args: str, check: bool = True) -> str:
    import subprocess

    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", check=False)
    if check and result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def _notice(out: str) -> list[str]:
    return [line for line in out.splitlines() if "before this session" in line]


def _conflicting_branches(repo: Path) -> None:
    """main and side both change README.md on top of the initial commit."""
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "README.md").write_text("side\n", "utf-8")
    _git(repo, "commit", "-qam", "side change")
    _git(repo, "checkout", "-q", "main")
    (repo / "README.md").write_text("main\n", "utf-8")
    _git(repo, "commit", "-qam", "main change")


def test_a_clean_tree_adds_no_line(repo: Path, hook_input) -> None:
    (repo / "scratch.txt").write_text("untracked files are not work in progress\n", "utf-8")
    assert _notice(_run(repo, hook_input, verify=FakeVerify())) == []


def test_staged_and_modified_files_are_told_in_one_plain_line(repo: Path, hook_input) -> None:
    (repo / "staged.txt").write_text("x\n", "utf-8")
    _git(repo, "add", "staged.txt")
    (repo / "README.md").write_text("edited since the last commit\n", "utf-8")
    lines = _notice(_run(repo, hook_input, verify=FakeVerify()))
    assert len(lines) == 1
    assert "1 file staged" in lines[0] and "1 file modified" in lines[0]
    assert "git " not in lines[0] and "plumb " not in lines[0].replace("plumb:", "")


@pytest.mark.parametrize(("start", "word"), [("merge", "merge"), ("cherry-pick", "cherry-pick"),
                                              ("rebase", "rebase")])
def test_an_unfinished_operation_is_named(repo: Path, hook_input, start: str,
                                          word: str) -> None:
    _conflicting_branches(repo)
    if start == "merge":
        _git(repo, "merge", "side", check=False)
    elif start == "cherry-pick":
        _git(repo, "cherry-pick", "side", check=False)
    else:
        _git(repo, "rebase", "side", check=False)
    lines = _notice(_run(repo, hook_input, verify=FakeVerify()))
    assert len(lines) == 1
    assert f"An earlier {word} was left unfinished" in lines[0].replace("plumb: ", "")
    assert "1 file in conflict" in lines[0]


def test_a_resumed_session_is_not_told(repo: Path, hook_input) -> None:
    (repo / "README.md").write_text("this session's own edit\n", "utf-8")
    out = io.StringIO()
    session_start.main(stdin=io.StringIO(hook_input("SessionStart", source="resume")),
                       stdout=out, root=repo, verify=FakeVerify())
    assert _notice(out.getvalue()) == []


def test_no_git_is_skipped_silently(repo: Path, hook_input, monkeypatch) -> None:
    from plumb.hosts.claude_code import hygiene

    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    (repo / "README.md").write_text("edited\n", "utf-8")
    monkeypatch.setattr(hygiene.subprocess, "run", missing)
    out = _run(repo, hook_input, verify=FakeVerify())
    assert _notice(out) == [] and out.startswith("plumb brief")
    assert not (repo / ".plumb" / "session" / "errors.log").exists()


def test_a_slow_git_is_skipped_silently(repo: Path, hook_input, monkeypatch) -> None:
    import subprocess

    from plumb.hosts.claude_code import hygiene

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 0.1)

    (repo / "README.md").write_text("edited\n", "utf-8")
    monkeypatch.setattr(hygiene.subprocess, "run", slow)
    out = _run(repo, hook_input, verify=FakeVerify())
    assert _notice(out) == [] and out.startswith("plumb brief")
