"""SR-368: a study asked in any words is recognised by the agent's understanding, never by iaso
matching words (DEC-371); every session start names the built-in study commands in order, so the
agent never has to find out how iaso makes studies."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fakes import FakeBackend, FakeVerify

from iaso import study
from iaso.hosts.claude_code import prompt

pytestmark = pytest.mark.sr("SR-368")


@pytest.mark.parametrize("text", ["I'd like a study of how merges are held.",
                                  "study room on the judge", "/iaso study the judge"])
def test_ex3_the_prompt_hook_proposes_no_study_itself(repo: Path, hook_input,
                                                      monkeypatch: pytest.MonkeyPatch,
                                                      text: str) -> None:
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=text, session_id="s1")
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo,
                       verify=FakeVerify(), backend=FakeBackend()) == 0
    assert study.studies(repo) == []
    assert "study idea" not in out.getvalue()


def test_ex4_the_records_skill_names_the_study_commands_in_order() -> None:
    skills = Path(__file__).resolve().parents[2] / "plugin" / "skills" / "iaso-records"
    assert "references/study.md" in (skills / "SKILL.md").read_text("utf-8")
    steps = ["study propose --asked", "picks the depth", "study gather", "study add"]
    text = (skills / "references" / "study.md").read_text("utf-8")
    assert [text.index(s) for s in steps] == sorted(text.index(s) for s in steps)
