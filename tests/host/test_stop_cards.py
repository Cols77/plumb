"""The end of a turn shows the owner nothing when nothing needs them (SR-012 EX-5, SR-373); the
stop hook draws no card (SR-375)."""

from __future__ import annotations

import io
import json
import subprocess
import time
from pathlib import Path

import pytest
from fakes import FakeVerify

from iaso.api import open_core
from iaso.contracts import NodeEvidence, Target
from iaso.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-265")

SESSION = "s1"
NODE = "tests/test_a.py::test_a"
QUOTE = "the calculator adds"
PROMPT = "please make sure the calculator adds two numbers, nothing fancy"
PROMPT_DIGEST = "sha256:" + "c5" * 32
INT1 = f"""---
id: INT-001
title: Arithmetic helpers
quote: "{QUOTE}"
readback: The calculator adds two numbers.
prompt: {PROMPT_DIGEST[7:23]}
---
"""
FEAT1 = """---
id: FEAT-001
title: Merge check
---
"""
SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""
CODE = "def add(a, b):\n    return a + b\n"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _log_prompt(repo: Path, text: str = PROMPT, digest: str = PROMPT_DIGEST,
                at: str = "2026-10-01T10:00:00Z") -> None:
    prompts = Path(open_core(repo).paths.prompts)
    prompts.parent.mkdir(parents=True, exist_ok=True)
    with prompts.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"digest": digest, "session": SESSION, "at": at, "text": text,
                              "via": "hook"}) + "\n")


@pytest.fixture
def project(repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(repo)
    write_record(repo, INT1)
    write_record(repo, FEAT1)
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    core.add_link("SR-001", "verified_by", Target(test=NODE))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    _log_prompt(repo)
    return repo


def start_turn(repo: Path) -> None:
    path = repo / ".iaso" / "session" / SESSION / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}), "utf-8")


def edit(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    with (repo / ".iaso" / "session" / SESSION / "touched.txt").open("a",
                                                                       encoding="utf-8") as f:
        f.write(rel + "\n")


def run_stop(repo: Path, hook_input, *, verify=None, active: bool = False) -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=SESSION, stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=repo,
                     verify=verify if verify is not None else FakeVerify(), unjudged=None) == 0
    return out.getvalue()


def owner(out: str) -> str:
    data = json.loads(out) if out.strip() else {}
    assert data.get("decision") != "block", data
    return data.get("systemMessage", "")


# --------------------------------------------------------------------------- SR-012


def test_ex5_nothing_for_the_owner_shows_nothing(project: Path, hook_input) -> None:
    """EX-5: nothing needs the owner and nothing settled: the hook shows the owner nothing."""
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(NODE, "fresh-pass")})
    assert run_stop(project, hook_input, verify=verify) == ""


def test_a_failure_of_a_test_since_removed_is_not_a_regression(tmp_path: Path) -> None:
    """SR-012 EX-2: a regression card is raised only for a test still defined in its file."""
    from iaso.hosts.claude_code.stop import test_exists

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_kept(): pass\n", encoding="utf-8")
    assert test_exists(tmp_path, "tests/test_x.py::test_kept")
    assert test_exists(tmp_path, "tests/test_x.py::test_kept[a-b]")
    assert not test_exists(tmp_path, "tests/test_x.py::test_gone[a-b]")
    assert not test_exists(tmp_path, "tests/test_x.py::test_kep")
    assert not test_exists(tmp_path, "tests/test_missing.py::test_kept")
