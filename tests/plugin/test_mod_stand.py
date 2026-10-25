"""The mod's tests run from outside the shipped plugin (SR-123): ``tests/plugin/mod/stand.py``
lays the mod and its tests in a stand and runs ``claude plugin test`` there."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from .helpers import PLUGIN, REPO

pytestmark = [pytest.mark.sr("SR-279")]


def _stand():
    spec = importlib.util.spec_from_file_location("mod_stand", REPO / "tests" / "plugin" / "mod" /
                                                  "stand.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_test_files_in_the_plugin() -> None:
    shipped = [p.relative_to(PLUGIN).as_posix() for p in PLUGIN.rglob("*")
               if p.is_file() and (".test." in p.name or p.name in ("harness.ts", "fixtures.ts"))]
    assert shipped == []


def test_the_stand_holds_the_mod_and_its_tests(tmp_path: Path) -> None:
    stand = _stand().assemble(tmp_path / "plumb")
    assert (stand / ".claude-plugin" / "plugin.json").is_file()
    assert (stand / "hooks" / "register.tsx").is_file()
    assert (stand / "types" / "index.d.ts").is_file()
    # the tests' own import of the contract resolves inside the stand
    assert (stand / "plugin" / "types" / "index.d.ts").is_file()
    names = {p.name for p in (stand / "tests" / "plugin" / "mod").iterdir()}
    assert {"band.test.tsx", "harness.ts", "fixtures.ts"} <= names


@pytest.mark.skipif(shutil.which("claude") is None, reason="no claude binary on this machine")
def test_the_mod_tests_pass() -> None:
    done = _stand().run(shutil.which("claude") or "claude")
    # a failure names its cases and keeps the run's whole output: each failed case's error with it
    failed = [line for line in done.stdout.splitlines() if line.startswith("(fail)")]
    assert done.returncode == 0, ("failed cases:\n" + "\n".join(failed or ["(none named)"]) +
                                  "\n\nclaude plugin test said:\n" + done.stdout)
