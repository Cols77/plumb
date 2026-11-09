"""H4: the session-start brief and the first status snapshot (spec 6.1)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fakes import FakeVerify

from iaso.api import open_core
from iaso.contracts import FullPending, NodeEvidence, Target
from iaso.hosts.claude_code import session_start

pytestmark = pytest.mark.sr("SR-278")


@pytest.fixture(autouse=True)
def _roomy_hook_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests check what the brief says, not how fast the machine is: a real hook
    budget (1.4 s) is overrun by any load on a shared machine and adds a 'check skipped'
    line. The cut itself is tested on a fake clock that jumps 5 s, past this budget; the
    hook's real speed is held by test_hook_perf."""
    monkeypatch.setattr(session_start, "hook_budget", lambda name: (lambda root: 4000.0))


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


@pytest.mark.sr("SR-277")
def test_brief_is_a_few_lines_and_a_pointer_by_default(repo: Path, write_record,
                                                       hook_input) -> None:
    """R9, SR-374 EX-9: the session brief is a few lines, never every proposed record and no
    counts (they are in iaso status)."""
    _many_records(repo, write_record)
    lines = _run(repo, hook_input, verify=FakeVerify()).splitlines()
    assert len(lines) <= 6
    assert not any("Intent number 7" in line or "60" in line or "open NCs" in line
                   for line in lines)


@pytest.mark.sr("SR-277")
def test_a_session_brief_setting_no_longer_picks_a_long_brief(repo: Path, write_record,
                                                              hook_input) -> None:
    """SR-374, SR-277 (INT-114): the session start gives the table's session lines only; an old
    ``session_brief: full`` in the config changes nothing, and no long brief is built."""
    from iaso.config import HooksConfig

    assert not hasattr(HooksConfig(), "session_brief")
    _many_records(repo, write_record)
    (repo / ".iaso" / "config.yaml").write_text("hooks:\n  session_brief: full\n", "utf-8")
    out = _run(repo, hook_input, verify=FakeVerify())
    assert len(out.splitlines()) <= 6 and "iaso brief" not in out.splitlines()[0]
    assert "more (iaso brief --all)" not in out


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
    # SR-374 EX-9: what blocks now, not the counts of what waits or drifts
    assert "waiting on a judge" not in out and "drift" not in out
    assert "iaso: tests block now: not yet passing: tests/test_a.py::test_x" in out


def test_writes_status_snapshot(repo: Path, write_record, hook_input) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: One\nstatement: s\n---\n")
    _run(repo, hook_input, verify=FakeVerify(pending=FullPending(True, ("pyproject.toml",))))
    data = json.loads((repo / ".iaso" / "session" / "status.json").read_text("utf-8"))
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
    import iaso.api
    from iaso.hosts.claude_code import hookio

    clock = _Clock()
    monkeypatch.setattr(hookio, "time", clock)
    write_record(repo, "---\nid: SR-001\ntitle: Links pin both ends\nstatement: s\n---\n")
    real_open = iaso.api.open_core

    class SlowCore:
        def __init__(self, core) -> None:
            self._core = core

        def status(self, *args, **kwargs):
            clock.now += 5.0
            return self._core.status(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._core, name)

    monkeypatch.setattr(iaso.api, "open_core", lambda root: SlowCore(real_open(root)))
    (repo / ".iaso" / "session").mkdir(parents=True, exist_ok=True)
    (repo / ".iaso" / "session" / "brief_seen.json").write_text("{}", "utf-8")  # all changed
    verify = FakeVerify()
    out = _run(repo, hook_input, verify=verify).splitlines()
    assert out[0].startswith("iaso: changed since you last looked: SR-001")
    assert out[-1] == "iaso: check skipped (budget): tests"


def test_warm_brief_skips_the_test_map(repo: Path, write_record, hook_input,
                                       monkeypatch) -> None:
    """The tests line is cached by the verify fingerprint: a warm session start builds no
    test map (it used to cost 0.65 s of 1.37 s on iaso itself)."""
    import iaso.verify.testmap as testmap

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
    assert "fresh passing evidence" not in warm   # SR-374 EX-9: no counts


def test_status_snapshot_survives_a_budget_cut_of_the_tests_line(
        repo: Path, write_record, hook_input, monkeypatch) -> None:
    """The status line reads this snapshot: when the tests check is cut by the budget the
    snapshot is still written (tests unknown), so the line never keeps an older session's
    state."""
    import iaso.api
    from iaso.hosts.claude_code import hookio

    clock = _Clock()
    monkeypatch.setattr(hookio, "time", clock)
    write_record(repo, "---\nid: SR-001\ntitle: Links pin both ends\nstatement: s\n---\n")
    real_open = iaso.api.open_core

    class SlowCore:
        def __init__(self, core) -> None:
            self._core = core

        def status(self, *args, **kwargs):
            clock.now += 5.0
            return self._core.status(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._core, name)

    monkeypatch.setattr(iaso.api, "open_core", lambda root: SlowCore(real_open(root)))
    (repo / ".iaso" / "session").mkdir(parents=True, exist_ok=True)
    (repo / ".iaso" / "session" / "brief_seen.json").write_text("{}", "utf-8")  # all changed
    out = _run(repo, hook_input, verify=FakeVerify()).splitlines()
    assert out[-1] == "iaso: check skipped (budget): tests"
    data = json.loads((repo / ".iaso" / "session" / "status.json").read_text("utf-8"))
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
    assert "git " not in lines[0] and "iaso " not in lines[0].replace("iaso:", "")


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
    assert f"An earlier {word} was left unfinished" in lines[0].replace("iaso: ", "")
    assert "1 file in conflict" in lines[0]


def test_a_resumed_session_is_not_told(repo: Path, hook_input) -> None:
    (repo / "README.md").write_text("this session's own edit\n", "utf-8")
    out = io.StringIO()
    session_start.main(stdin=io.StringIO(hook_input("SessionStart", source="resume")),
                       stdout=out, root=repo, verify=FakeVerify())
    assert _notice(out.getvalue()) == []


def test_no_git_is_skipped_silently(repo: Path, hook_input, monkeypatch) -> None:
    from iaso.hosts.claude_code import hygiene

    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    (repo / "README.md").write_text("edited\n", "utf-8")
    monkeypatch.setattr(hygiene.subprocess, "run", missing)
    out = _run(repo, hook_input, verify=FakeVerify())
    assert _notice(out) == [] and "check skipped" not in out
    assert not (repo / ".iaso" / "session" / "errors.log").exists()


def test_a_slow_git_is_skipped_silently(repo: Path, hook_input, monkeypatch) -> None:
    import subprocess

    from iaso.hosts.claude_code import hygiene

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 0.1)

    (repo / "README.md").write_text("edited\n", "utf-8")
    monkeypatch.setattr(hygiene.subprocess, "run", slow)
    out = _run(repo, hook_input, verify=FakeVerify())
    assert _notice(out) == [] and "check skipped" not in out


@pytest.mark.sr("SR-210")
def test_ex4_low_risk_records_give_no_offer_line(repo: Path, write_record, hook_input,
                                                 monkeypatch) -> None:
    """SR-135 EX-4: records the judge rates faithful to the owner's words add no approve line to
    the brief; iaso triage still lists them."""
    from capture.capture_helpers import log_prompt, record_text, use_coverage_judge

    use_coverage_judge(monkeypatch)
    said = "add multiply number 11 next to add"
    log_prompt(repo, said, at="2026-10-06T00:00:00Z")
    write_record(repo, record_text("INT-011", "multiply number 11", quote=said, readback=said,
                                   will=["multiply number 11"], prompt=_digest(said)))
    out = _run(repo, hook_input)
    assert "rated faithful" not in out
    assert "approve the" not in out


def _digest(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
