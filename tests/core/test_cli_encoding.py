"""Every CLI verb prints plumb's glyphs through a pipe in a legacy code page (audit round 3).

An agent's shell tool runs ``plumb`` with stdout piped, which Python encodes in the locale
code page (cp1252 on Windows) unless PYTHONUTF8 or PYTHONIOENCODING says otherwise: the
status card's ● or the confirm card's ▸ then raised UnicodeEncodeError. The one choke point
is ``plumb.cli.main`` (``utf8_output``); one test per owner-view entry point, each in a
subprocess with the code page forced to cp1252 and PYTHONUTF8=0.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-202")

SR1 = """---
id: SR-001
title: add returns the sum → ✓ always
statement: add(a, b) returns the sum ≥ both.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3 ✓
---
"""


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "setup"], cwd=repo, check=True,
                   capture_output=True)
    return repo


def _run_legacy(repo: Path, *argv: str) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONIOENCODING", "PYTHONUTF8", "PLUMB_AGENT_SESSION")}
    env.update({"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"})  # the owner's console
    return subprocess.run([sys.executable, "-m", "plumb", *argv, "--root", str(repo)],
                          cwd=repo, env=env, capture_output=True, timeout=120)


@pytest.mark.parametrize("argv", [
    ("status", "--card"),
    ("review",),
    ("explain", "the add function"),
    ("resolve", "the add function"),
    ("impact", "the add function"),
    ("align",),
], ids=lambda argv: argv[0] + ("-card" if "--card" in argv else ""))
def test_owner_view_prints_through_a_cp1252_pipe(project: Path, argv: tuple[str, ...]) -> None:
    result = _run_legacy(project, *argv)
    err = result.stderr.decode("utf-8", "replace")
    assert "UnicodeEncodeError" not in err and "Traceback" not in err, err
    assert result.returncode in (0, 1), err
    out = result.stdout.decode("utf-8")  # UTF-8 on the pipe, whatever the code page
    assert out.strip()
