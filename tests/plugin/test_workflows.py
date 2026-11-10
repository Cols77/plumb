"""SR-385: iaso ships its own workflows (debug-cases, intent-build, land) and names them."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from iaso.understand import summary

from .helpers import PLUGIN, REPO

pytestmark = pytest.mark.sr("SR-385")

TEMPLATES = REPO / "src" / "iaso" / "hosts" / "claude_code" / "templates" / "workflows"
NAMES = ("debug-cases", "intent-build", "land")
ROWS = [{"id": f"c{n}", "kind": "stale-link", "target": f"SR-{n}", "detail": "d",
         "state": "open"} for n in (1, 2, 3)]
TODAY = ("iaso: 3 debug cases open, 0 resolved:\n"
         "- c1 (stale-link) SR-1: d\n- c2 (stale-link) SR-2: d\n- c3 (stale-link) SR-3: d\n"
         "Run them as a Workflow on Sonnet: repin after tests, relink, rerun; a changed "
         "meaning is one question to the owner through the question tool; "
         "`iaso understand debug done <case id>` marks one resolved.")


def script(name: str) -> str:
    return (TEMPLATES / f"{name}.js").read_text(encoding="utf-8")


def models(text: str) -> list[tuple[str, str]]:
    """Each ``model:`` level with the line that holds it and the line before."""
    lines = text.splitlines()
    return [(m.group(1), lines[i - 1] + "\n" + line) for i, line in enumerate(lines)
            for m in [re.search(r"model:\s*LEVEL\.(\w+)", line)] if m]


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
    for needed in ("git merge main", "iaso-heavy.lock", "repin --after-tests", "merge-check"):
        assert needed in text, needed
    for banned in ("--no-verify", "--force", "mergeHold", "git merge --no-ff"):
        assert banned not in text, banned


@pytest.mark.parametrize("name", NAMES)
def test_ex4_sonnet_level_everywhere_and_one_level_up_on_a_retry(name: str) -> None:
    text = script(name)
    assert "{ haiku: 'haiku', sonnet: 'sonnet', opus: 'opus', fable: 'fable' }, input.models" in text
    assert text.count("model:") == len(models(text))  # a stage names a level, never a model
    found = models(text)
    assert found and all(m in ("sonnet", "opus") for m, _ in found)
    opus = [ctx for m, ctx in found if m == "opus"]
    assert len(opus) == 1 and re.search(r"fail|not resolved|retry|again", opus[0], re.I)


@pytest.mark.parametrize("name", NAMES)
def test_each_script_starts_with_meta_and_the_plugin_copy_matches(name: str) -> None:
    from iaso.hosts.claude_code.install import Launcher

    text = script(name)
    assert text.lstrip().startswith("export const meta = {")
    expected = text.replace("{iaso}", Launcher("path", "iaso", "iaso").agent_prefix)
    copy = Path(PLUGIN / "workflows" / f"{name}.js")
    assert copy.read_text(encoding="utf-8") == expected


def test_ex1_only_claude_code_with_the_plugin_is_told_the_workflow(monkeypatch) -> None:
    from iaso.hosts.neutral import cases_workflow

    monkeypatch.setenv("IASO_PLUGIN_ROOT", "/p")
    assert cases_workflow("claude-code") == "iaso:debug-cases"
    assert cases_workflow("codex") == ""
    monkeypatch.delenv("IASO_PLUGIN_ROOT")
    assert cases_workflow("claude-code") == ""


def run(name: str, args: dict, answers: dict) -> dict:
    """The script run under node with scripted agents: its result and the agents it started."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(Path(__file__).with_name("run_workflow.mjs")),
                          str(TEMPLATES / f"{name}.js"),
                          json.dumps({"args": args, "answers": answers})],
                         capture_output=True, text=True, check=True, timeout=60)
    return json.loads(out.stdout)


OK = {"ok": True, "finding": "done"}
PLAN = {"intent": "INT-1", "plan": [{"id": "1", "sr": "SR-1", "summary": "x"}],
        "worktree": "/w", "session": "s"}


def test_ex2_run_a_failed_plan_gate_starts_no_build() -> None:
    ran = run("intent-build", PLAN, {"plan tests": [OK],
                                     "plan gate": [{"exitCode": 1, "finding": "a conflict"}]})
    assert ran["result"]["done"] is False and ran["result"]["stopped"].startswith("plan gate")
    assert [c["label"] for c in ran["calls"]] == ["plan tests", "plan gate"]


def test_ex2_run_each_phase_follows_its_passed_gate() -> None:
    gate = {"exitCode": 0, "finding": "passed"}
    ran = run("intent-build", PLAN, {"plan tests": [OK], "plan gate": [gate], "build 1": [OK],
                                     "check 1": [OK], "prove": [gate]})
    assert ran["result"]["built"] == ["1"] and ran["result"]["done"] is True
    assert [c["phase"] for c in ran["calls"]] == ["Plan", "Plan", "Build", "Build", "Prove"]


def test_ex3_run_a_failed_full_run_stops_the_landing() -> None:
    ran = run("land", {"branch": "b", "worktree": "/w"},
              {"Merge main in": [OK], "Full run": [{"ok": False, "finding": "a test fails"}]})
    assert ran["result"]["ready"] is False and "a test fails" in ran["result"]["holds"][0]
    assert [(c["label"], c["model"]) for c in ran["calls"]] == [
        ("Merge main in", "sonnet"), ("Full run", "sonnet"), ("Full run", "opus")]


def test_ex4_run_a_level_up_only_after_a_failed_round() -> None:
    case = {"id": "c1", "kind": "stale-link", "target": "SR-1", "detail": "d"}
    answers = {"fix c1": [{"resolved": True, "finding": "repinned"}],
               "verify c1": [{"resolved": False, "finding": "still stale"},
                             {"resolved": True, "finding": "fresh"}]}
    ran = run("debug-cases", {"cases": [case], "worktree": "/w"}, answers)
    assert ran["result"] == {"resolved": ["c1"], "open": [], "questions": []}
    assert [c["model"] for c in ran["calls"]] == ["sonnet", "sonnet", "opus", "sonnet"]
    given = run("debug-cases", {"cases": [case], "worktree": "/w",
                                "models": {"sonnet": "m1", "opus": "m2"}}, answers)
    assert [c["model"] for c in given["calls"]] == ["m1", "m1", "m2", "m1"]


def test_a_question_comes_back_and_no_agent_asks_the_owner() -> None:
    case = {"id": "c1", "kind": "stale-link", "target": "SR-1", "detail": "d"}
    asked = {"resolved": False, "finding": "meaning changed",
             "question": {"question": "Which one?", "options": ["a", "b"]}}
    ran = run("debug-cases", {"cases": [case], "worktree": "/w"}, {"fix c1": [asked]})
    assert ran["result"]["questions"] == [{"id": "c1", "question": "Which one?",
                                           "options": ["a", "b"]}]
    assert len(ran["calls"]) == 1
