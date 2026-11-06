"""SR-328: the self-debug workflow stands alone in plumb: the fixer runs from plumb's own
agent definition with no other plugin, skill or setting, and each stage records the model it
used (the smallest for evidence, the middle for the first round, the largest after a failure).
The fixer and the judge are scripted; git is real."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import debug
from plumb.selfdebug import FixerDispatcher
from plumb.understand import agents
from plumb.understand.repin import Meaning
from tests.debug.test_selffix import (  # noqa: F401 - fixtures and helpers
    CASE,
    Fixer,
    _fix,
    fixes_add,
    fixes_nothing,
    no_real_models,
    plumb_repo,
)

pytestmark = pytest.mark.sr("SR-328")
PLUGIN = Path(__file__).resolve().parents[2] / "plugin"


def test_ex1_every_stage_runs_from_plumbs_own_definition_and_nothing_of_another_plugin(
) -> None:
    cmd = FixerDispatcher().command("claude", "sonnet")
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert "--disable-slash-commands" in cmd and "--strict-mcp-config" in cmd
    given = json.loads(cmd[cmd.index("--agents") + 1])
    assert given == agents.definition("fixer") and "path::name" in given["plumb-fixer"]["prompt"]
    assert not [a for a in cmd if "--plugin" in a or "--mcp-config" in a]
    text = "\n".join((PLUGIN / "skills" / "plumb-debug" / "SKILL.md").read_text("utf-8")
                     for _ in [0]) + (agents.AGENTS_DIR / "fixer.md").read_text("utf-8")
    assert "superpowers" not in text.lower() and "plumb debug fix" in text


def test_ex2_the_smallest_model_gathers_evidence_the_middle_one_fixes_the_largest_retries(
        plumb_repo: Path,  # noqa: F811
) -> None:
    fixer = Fixer(fixes_nothing, fixes_add)
    out, _, _ = _fix(plumb_repo, fixer, Meaning(True, "wording only", 0.9))
    assert out.state == "fixed", out.detail
    assert fixer.models == ["sonnet", "opus"]
    row = next(c for c in debug.all_cases(plumb_repo) if c["id"] == CASE)
    # SR-388: each round is three stages, all at the round's level
    assert row["models"] == [{"stage": "evidence", "model": "haiku"}] + [
        {"stage": f"round {n} {s}", "level": m, "model": m}
        for n, m in ((1, "sonnet"), (2, "opus")) for s in ("diagnosis", "fix", "review")]


@pytest.mark.sr("SR-389")
def test_ex3_the_sonnet_like_level_set_to_another_model_runs_the_first_round(
        plumb_repo: Path,  # noqa: F811
) -> None:
    (plumb_repo / ".plumb" / "config.yaml").write_text(
        "understand:\n  levels:\n    sonnet: other-model\n", encoding="utf-8")
    fixer = Fixer(fixes_nothing, fixes_add)
    out, _, _ = _fix(plumb_repo, fixer, Meaning(True, "wording only", 0.9))
    assert out.state == "fixed", out.detail
    assert fixer.models == ["other-model", "opus"]
    row = next(c for c in debug.all_cases(plumb_repo) if c["id"] == CASE)
    assert row["models"][1:4] == [{"stage": f"round 1 {s}", "level": "sonnet",
                                   "model": "other-model"} for s in ("diagnosis", "fix", "review")]


@pytest.mark.sr("SR-389")
def test_a_failed_round_is_retried_one_level_up_never_past_fable(
        plumb_repo: Path,  # noqa: F811
) -> None:
    fixer = Fixer(fixes_nothing, fixes_nothing, fixes_nothing, fixes_nothing)
    _fix(plumb_repo, fixer, Meaning(True, "wording only", 0.9), rounds=4)
    assert fixer.models == ["sonnet", "opus", "fable", "fable"]


@pytest.mark.sr("SR-389")
def test_ex4_an_unknown_level_is_refused_naming_the_four() -> None:
    from plumb.config import config_from_mapping

    with pytest.raises(ValueError, match="haiku, sonnet, opus, fable"):
        config_from_mapping({"understand": {"levels": {"giant": "x"}}})


def test_the_help_names_every_debug_subcommand_the_skill_tells_agents_to_run(
        capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        debug.run("debug", ["--help"])
    text = " ".join(capsys.readouterr().out.split())
    for sub in ("plumb debug fix", "plumb debug done", "plumb debug report"):
        assert sub in text
