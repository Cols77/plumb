"""H2: edit tracking without blocking (spec 6.3)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from iaso.hosts.claude_code import post_edit

pytestmark = pytest.mark.sr("SR-276")


def _touched(repo: Path, session: str = "test-session") -> list[str]:
    path = repo / ".iaso" / "session" / session / "touched.txt"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _run(repo: Path, payload: str) -> str:
    out = io.StringIO()
    assert post_edit.main(stdin=io.StringIO(payload), stdout=out, root=repo) == 0
    return out.getvalue()


def test_appends_repo_relative_path(repo: Path, hook_input) -> None:
    target = repo / "src" / "pkg" / "mod.py"
    _run(repo, hook_input("PostToolUse", tool_name="Edit",
                          tool_input={"file_path": str(target)}))
    _run(repo, hook_input("PostToolUse", tool_name="NotebookEdit",
                          tool_input={"notebook_path": "nb/analysis.ipynb"}))
    _run(repo, hook_input("PostToolUse", tool_name="MultiEdit",
                          tool_input={"file_path": str(repo / "README.md")}))
    assert _touched(repo) == ["src/pkg/mod.py", "nb/analysis.ipynb", "README.md"]


def test_ignores_paths_outside_repo(repo: Path, hook_input, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere.py"
    out = _run(repo, hook_input("PostToolUse", tool_name="Write",
                                tool_input={"file_path": str(outside)}))
    _run(repo, hook_input("PostToolUse", tool_name="Write",
                          tool_input={"file_path": "../escape.py"}))
    _run(repo, hook_input("PostToolUse", tool_name="Write", tool_input={}))
    assert _touched(repo) == []
    assert out == ""


def test_fast_path_imports_no_yaml(repo: Path, hook_input) -> None:
    payload = hook_input("PostToolUse", tool_name="Edit",
                         tool_input={"file_path": str(repo / "a.py")})
    code = ("import sys\n"
            "from iaso.cli import main\n"
            f"rc = main(['hook', 'post-edit', '--root', {str(repo)!r}])\n"
            "heavy = sorted(m for m in ('yaml', 'argparse', 'iaso.api', 'iaso.config',\n"
            "               'subprocess') if m in sys.modules)\n"
            "sys.stderr.write('HEAVY=' + ','.join(heavy) + ';RC=' + str(rc))\n")
    result = subprocess.run([sys.executable, "-c", code], input=payload, capture_output=True,
                            text=True, check=False, encoding="utf-8")
    assert "HEAVY=;RC=0" in result.stderr, result.stderr
    assert _touched(repo) == ["a.py"]


def test_output_is_silent_json_free(repo: Path, hook_input) -> None:
    out = _run(repo, hook_input("PostToolUse", tool_name="Edit",
                                tool_input={"file_path": "x.py"}))
    assert out == ""
    assert json.loads(hook_input("PostToolUse"))["hook_event_name"] == "PostToolUse"
