"""SP6 6.2: ``log.append`` (and the migration in ``log.py``) is the only writer under
``.plumb/log/`` (SR-073)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.sr("SR-073")

SRC = Path(__file__).resolve().parents[2] / "src" / "plumb"
LOG_REF = re.compile(r"log_dir|log_kind_dir|log_events|log_evidence|log_path\(|log_head|"
                     r"log_pack\(|\.plumb/log")
WRITES = re.compile(r"write_text|write_bytes|\.touch\(|os\.link|os\.replace|unlink|"
                    r"os\.remove|open\([^)]*[\"'][wa]b?[\"']")
# readers and declarations that name the log directory without writing under it
# (ids/mergefix.py and mergedriver/conflicts.py only stage, with git add, the entries
# log.append wrote)
READERS = {"paths.py", "commands.py", "merge.py", "validate.py", "hosts/claude_code/install.py",
           "hosts/claude_code/stop.py", "ids/mergefix.py", "mergedriver/conflicts.py"}


def test_only_log_py_writes_under_plumb_log() -> None:
    referencing: dict[str, list[str]] = {}
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        lines = [line for line in path.read_text(encoding="utf-8").splitlines()
                 if LOG_REF.search(line)]
        if lines:
            referencing[rel] = lines
    assert "log.py" in referencing
    assert set(referencing) - {"log.py"} <= READERS, sorted(set(referencing) - READERS)
    for rel, lines in referencing.items():
        if rel == "log.py":
            continue
        assert not [line for line in lines if WRITES.search(line)], rel
