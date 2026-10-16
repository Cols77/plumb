"""The manifest and the marketplace pass Claude Code's own validation (SP7 4.8; SR-082 EX-4).
Skipped where ``claude`` is not installed; run in the PLUGIN lane gate."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from .helpers import PLUGIN, REPO

pytestmark = [pytest.mark.sr("SR-279"),
              pytest.mark.skipif(shutil.which("claude") is None, reason="claude is not installed")]


def _validate(target: str) -> dict:
    claude = shutil.which("claude")
    assert claude is not None
    result = subprocess.run([claude, "plugin", "validate", "--json", target], cwd=REPO,
                            capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_plugin_valid() -> None:
    report = _validate(str(PLUGIN))
    assert report["success"] is True
    assert report["manifest"]["errors"] == []
    hooks = [c for c in report["contents"] if c["type"] == "hooks"]
    assert hooks and all(c["errors"] == [] for c in hooks)
    # the validation lists what the mod responds to (SR-082 EX-4); the stub hooks nothing yet
    assert any("register.tsx hooks:" in note for c in hooks for note in c["notes"])


def test_marketplace_valid() -> None:
    report = _validate(str(REPO))
    assert report["success"] is True
