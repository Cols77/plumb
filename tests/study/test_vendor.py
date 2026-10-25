"""The Manim install and the vendored scene rules (SR-317): Manim Community on Cairo, the
vendored skill with its MIT licence and pinned commit, the agent told to use Manim CE."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from plumb.study import video

pytestmark = pytest.mark.sr("SR-317")

SKILL = (Path(__file__).resolve().parents[2] / "src/plumb/hosts/claude_code/templates/skills"
         / "plumb-study-video")
COMMIT = "cef045011722"


def test_ex1_manim_is_installed_and_the_render_uses_no_opengl(tmp_path, monkeypatch):
    """SR-317 EX-1: Manim comes with the install; the render command asks for no OpenGL."""
    assert re.search(r"^\s*\"manim>=", (SKILL.parents[6] / "pyproject.toml").read_text(
        encoding="utf-8"), re.M)   # the install brings it; the env may not be synced yet
    seen: list[str] = []

    def fake(cmd, **kw):
        seen.extend(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "stop here")

    monkeypatch.setattr(video.subprocess, "run", fake)
    with pytest.raises(RuntimeError):
        video.run_manim(tmp_path / "scene.py", tmp_path)
    assert "manim" in seen and not any("opengl" in a.lower() for a in seen)


def test_ex2_the_vendored_files_carry_the_mit_licence_and_name_the_commit():
    """SR-317 EX-2: LICENSE is MIT; VENDORED.md names the commit; both skills are there."""
    vendor = SKILL / "vendor"
    assert (vendor / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    named = (vendor / "VENDORED.md").read_text(encoding="utf-8")
    assert COMMIT in named and "adithya-s-k/manim_skill" in named
    assert (vendor / "manimce-best-practices" / "SKILL.md").is_file()
    assert (vendor / "manim-composer" / "SKILL.md").is_file()


def test_ex3_the_skill_tells_the_agent_manim_ce_and_forbids_manimlib():
    """SR-317 EX-3: the agent is told `from manim import *` and never manimlib."""
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "from manim import *" in text
    assert "Never `manimlib`" in text
