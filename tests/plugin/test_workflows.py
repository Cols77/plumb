"""SR-385: plumb ships its own workflows (debug-cases, intent-build, land) and names them."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from plumb.understand import summary

from .helpers import PLUGIN, REPO

pytestmark = pytest.mark.sr("SR-385")

TEMPLATES = REPO / "src" / "plumb" / "hosts" / "claude_code" / "templates" / "workflows"
NAMES = ("debug-cases", "intent-build", "land")
ROWS = [{"id": f"c{n}", "kind": "stale-link", "target": f"SR-{n}", "detail": "d",
         "state": "open"} for n in (1, 2, 3)]
TODAY = ("plumb: 3 debug cases open, 0 resolved:\n"
         "- c1 (stale-link) SR-1: d\n- c2 (stale-link) SR-2: d\n- c3 (stale-link) SR-3: d\n"
         "Run them as a Workflow on Sonnet: repin after tests, relink, rerun; a changed "
         "meaning is one question to the owner through the question tool; "
         "`plumb understand debug done <case id>` marks one resolved.")


def script(name: str) -> str:
    return (TEMPLATES / f"{name}.js").read_text(encoding="utf-8")


def models(text: str) -> list[tuple[str, str]]:
    """Each ``model:`` value with the line that holds it and the line before."""
    lines = text.splitlines()
    return [(m.group(1), lines[i - 1] + "\n" + line) for i, line in enumerate(lines)
            for m in [re.search(r"model:\s*['\"](\w+)['\"]", line)] if m]


def test_ex1_the_case_text_names_the_shipped_workflow() -> None:
    text = summary.cases_text(ROWS, workflow="debug-cases")
    assert "debug-cases" in text and "3 debug cases" in text
    assert all(c in text for c in ("c1", "c2", "c3"))


def test_no_workflow_leaves_the_case_text_as_it_was() -> None:
    assert summary.cases_text(ROWS) == TODAY


def test_ex2_intent_build_has_phases_and_stops_on_a_failed_gate() -> None:
    text = script("intent-build")
    for phase in ("Plan", "Build", "Prove"):
        assert re.search(rf"phases:.*['\"]{phase}['\"]", text, re.S), phase
    assert "intent gate plan" in text and "intent done" in text
    assert re.search(r"if\s*\([^)]*(gate|pass)[^)]*\)", text, re.I)


def test_ex3_land_merges_main_under_the_lock_and_forces_nothing() -> None:
    text = script("land")
    for needed in ("git merge main", "plumb-heavy.lock", "repin --after-tests", "merge-check"):
        assert needed in text, needed
    for banned in ("--no-verify", "--force", "mergeHold", "git merge --no-ff"):
        assert banned not in text, banned


@pytest.mark.parametrize("name", NAMES)
def test_ex4_sonnet_everywhere_and_one_opus_on_a_retry(name: str) -> None:
    found = models(script(name))
    assert found and all(m in ("sonnet", "opus") for m, _ in found)
    opus = [ctx for m, ctx in found if m == "opus"]
    assert len(opus) == 1 and re.search(r"fail|not resolved|retry|again", opus[0], re.I)


@pytest.mark.parametrize("name", NAMES)
def test_each_script_starts_with_meta_and_the_plugin_copy_matches(name: str) -> None:
    from plumb.hosts.claude_code.install import Launcher

    text = script(name)
    assert text.lstrip().startswith("export const meta = {")
    expected = text.replace("{plumb}", Launcher("path", "plumb", "plumb").agent_prefix)
    copy = Path(PLUGIN / "workflows" / f"{name}.js")
    assert copy.read_text(encoding="utf-8") == expected
