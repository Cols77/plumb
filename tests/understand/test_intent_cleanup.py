# ruff: noqa: F811
"""SR-308: an ended intent loop removes its own working files and no one else's."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.capture import proof
from plumb.contracts import CardState
from plumb.understand import cardstore, cmd_intent, files
from understand.test_intent_loop import DIGEST, SESSION, _findings, _run, intent  # noqa: F401, F811

pytestmark = pytest.mark.sr("SR-308")


def _passed_plan(intent: Path, tmp_path: Path) -> tuple[Path, Path]:
    clarify, plan = _findings(tmp_path, "low"), tmp_path / "plan.json"
    plan.write_text(Path(clarify).read_text(encoding="utf-8"), encoding="utf-8")
    _run(intent, "gate", "clarify", "--intent", "INT-001", "--findings", clarify)
    _run(intent, "gate", "plan", "--intent", "INT-001", "--findings", str(plan))
    return Path(clarify), plan


def _proved(intent: Path) -> None:
    proof.set_plan(open_core(intent), "SR-040", "run the command and see it", "command")
    (intent / "out.txt").write_text("it worked\n", encoding="utf-8")
    proof.set_evidence(open_core(intent), "SR-040", "out.txt", "it printed", True)


def test_ex1_done_removes_the_loops_own_files_and_keeps_the_records(
        intent: Path, tmp_path: Path) -> None:
    clarify, plan = _passed_plan(intent, tmp_path)
    _proved(intent)
    result = files.results_dir(intent, SESSION) / "j1.json"
    result.parent.mkdir(parents=True)
    result.write_text("{}", encoding="utf-8")
    cardstore.save(intent, SESSION, [CardState(id="a", status="answered"),
                                     CardState(id="w", status="withdrawn"),
                                     CardState(id="o", status="open")])
    assert _run(intent, "done", "--intent", "INT-001") == 0
    assert not any(p.exists() for p in (clarify, plan, result,
                                        cmd_intent.loop_path(intent, SESSION, DIGEST)))
    assert [c.id for c in cardstore.own_cards(intent, SESSION)] == ["o"]
    assert (intent / ".plumb" / "requirements" / "SR-040.md").exists()


def test_ex2_another_loops_files_are_untouched(intent: Path, tmp_path: Path) -> None:
    other = cmd_intent.open_loop(intent, "other", "sha256:" + "c" * 64)
    other_result = files.results_dir(intent, "other") / "j.json"
    other_result.parent.mkdir(parents=True)
    other_result.write_text("{}", encoding="utf-8")
    _passed_plan(intent, tmp_path)
    _proved(intent)
    assert _run(intent, "done", "--intent", "INT-001") == 0
    assert other.exists() and other_result.exists()


def test_ex3_a_refused_done_removes_nothing(intent: Path, tmp_path: Path) -> None:
    clarify, plan = _passed_plan(intent, tmp_path)
    assert _run(intent, "done", "--intent", "INT-001") == 1     # no proof shown
    assert clarify.exists() and plan.exists()
    assert cmd_intent.loop_path(intent, SESSION, DIGEST).exists()
