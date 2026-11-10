"""SR-359: a judge that cannot settle a record is noted for the band's red line, naming the
judge and the exact cause (from a cause code), until it answers again; a judge that answered but
whose question iaso set aside is noted apart and never called unreachable. JEV and the model
are stubs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from iaso.judgment import cause_code
from understand.fakes import FakeDispatcher
from understand.test_judge_cascade import StubJev, configure, world  # noqa: F401
from understand.test_judge_job import build_job
from understand.test_judge_questions import answer, applied_on, asking, notes

pytestmark = pytest.mark.sr("SR-359")


def judges(repo: Path) -> dict[str, Any]:
    path = repo / ".iaso" / "session" / "judges.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def cascade(core: Any, dispatcher: Any = None, **kw: Any) -> Any:
    from iaso.understand import verdict

    try:
        return verdict.cascade(core, build_job(core, ["INT-001"]), system="judge", schema={},
                               dispatcher=dispatcher or FakeDispatcher(reason="no model here"),
                               **kw)
    except verdict.Waiting:          # the model is down too: only JEV's line is looked at
        return None


def test_ex1_no_jev_key_the_band_names_the_judge_and_the_key(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    core = configure(world, "  jev:\n    credential_env: OPENROUTER_API_KEY\n")
    cascade(core)
    down = judges(world)["down"]
    assert down["JEV"]["code"] == "no-key"
    assert down["JEV"]["line"] == "JEV judge, no key (OPENROUTER_API_KEY not found)"


def test_ex1_each_cause_has_its_code() -> None:
    assert [cause_code(c) for c in (
        "judgment.backend is not set in .iaso/config.yaml", "no JEV key (X is not in the env",
        "timeout", "no answer within 120 seconds", "OpenRouter could not be reached (x)",
        "HTTP 500", "HTTP 429", "the answer was not JSON", "HTTP 429: key limit exceeded",
        "a monkey answered")] == [
        "not-configured", "no-key", "timeout", "timeout", "network", "provider-error", "quota",
        "unusable-answer", "quota", "provider-error"]


def test_ex1_the_model_judge_cannot_be_reached_its_line_names_it_and_why(
        world: Path) -> None:  # noqa: F811
    cascade(configure(world), FakeDispatcher().failing(), jev=None)
    line = judges(world)["down"]["model"]["line"]
    assert line.startswith("fake:") and line.endswith(
        " judge, network down (the model could not be reached)")


def test_ex1_records_too_large_are_not_an_unreachable_judge(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    from iaso.understand import verdict

    monkeypatch.setattr(verdict, "INPUT_MAX", 10)
    cascade(configure(world), FakeDispatcher(), jev=None)
    assert "model" not in judges(world).get("down", {})


def test_ex2_a_question_set_aside_is_shown_apart_and_never_unreachable(
        world: Path) -> None:  # noqa: F811
    one = asking("SR-001", question="Should only the public pages get faster?")
    one["options"] = one["options"][:1]      # out of schema: one option
    applied_on(world, ["SR-001"], answer(("SR-001", "beyond"), questions=[one]))
    state = judges(world)
    assert state.get("down", {}) == {}
    (aside,) = state["set_aside"]
    assert aside["question"] == "Should only the public pages get faster?"
    assert aside["why"].startswith("a question lacks two to four options")
    (line,) = notes(world)
    assert "no judge can be reached" not in line and "two to four options" in line


def test_ex3_the_judge_answers_again_the_red_line_is_gone(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    core = configure(world, "  jev:\n    credential_env: OPENROUTER_API_KEY\n")
    cascade(core)
    assert "JEV" in judges(world)["down"]
    cascade(core, jev=StubJev(0.95))
    assert "JEV" not in judges(world)["down"]


def test_ex3_the_model_judge_answers_again_its_line_is_gone(
        world: Path) -> None:  # noqa: F811
    core = configure(world)
    cascade(core, FakeDispatcher().failing(), jev=None)
    assert "model" in judges(world)["down"]
    cascade(core, FakeDispatcher(script=lambda job: {"verdicts": []}), jev=None)
    assert "model" not in judges(world)["down"]


def test_ex3_a_recovered_judge_stops_showing_red_when_nothing_calls_it(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """report-b3f947ec: a checkout where no judge job runs after a quota or a missing claude
    binary kept the red line for good; the status refresh rechecks JEV cheaply at most once a
    window and looks the model judge's command up again, so a recovered judge stops showing
    red; a model that failed a job (not a missing command) keeps its line until one answers."""
    from capture.capture_helpers import JevStub, use_jev

    from iaso.api import open_core
    from iaso.judgment import JUDGE_RECHECK_S, judge_down, recheck_judges

    stub = JevStub()
    try:
        use_jev(world, stub, monkeypatch)
        core = open_core(world)
        judge_down(world, "JEV", "JEV: a quota (HTTP 402)", code="quota", now=1000.0)
        judge_down(world, "claude-code:haiku", "the claude command was not found on this "
                   "machine", code="not-configured", slot="model", now=1000.0)
        recheck_judges(core, now=1000.0 + 60)        # inside the window: no probe, lines stay
        assert set(judges(world)["down"]) == {"JEV", "model"} and not stub.requests
        later = 1000.0 + JUDGE_RECHECK_S + 1
        recheck_judges(core, now=later, dispatcher=FakeDispatcher(reason="still no claude"))
        assert "JEV" not in judges(world)["down"] and stub.requests   # the probe answered
        assert judges(world)["down"]["model"]["line"].endswith("(still no claude)")
        recheck_judges(core, now=later + JUDGE_RECHECK_S + 1, dispatcher=FakeDispatcher())
        assert judges(world).get("down", {}) == {}
        judge_down(world, "fake:haiku", "the model could not be reached", slot="model",
                   now=0.0)                           # a failed job, not a missing command
        recheck_judges(core, now=later, dispatcher=FakeDispatcher())
        assert "model" in judges(world)["down"]
    finally:
        stub.close()


def test_ex3_a_judge_still_down_keeps_its_line_with_the_fresh_cause(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    from iaso.judgment import JUDGE_RECHECK_S, judge_down, recheck_judges

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    core = configure(world, "  jev:\n    credential_env: OPENROUTER_API_KEY\n")
    judge_down(world, "JEV", "JEV: a quota (HTTP 402)", code="quota", now=1000.0)
    recheck_judges(core, now=1000.0 + JUDGE_RECHECK_S + 1)
    down = judges(world)["down"]["JEV"]
    assert down["code"] == "no-key"                     # the cause as it stands now
    assert down["line"] == "JEV judge, no key (OPENROUTER_API_KEY not found)"
    assert down["checked"] == 1000.0 + JUDGE_RECHECK_S + 1   # probed once a window, no more


def test_ex3_the_status_refresh_rechecks_the_judges(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    from capture.capture_helpers import JevStub, use_jev

    from iaso.api import open_core
    from iaso.hosts.claude_code.snapshot import refresh_counts
    from iaso.judgment import judge_down

    stub = JevStub()
    try:
        use_jev(world, stub, monkeypatch)
        judge_down(world, "JEV", "JEV: a quota (HTTP 402)", code="quota", now=0.0)
        refresh_counts(open_core(world))
        assert "JEV" not in judges(world).get("down", {})
    finally:
        stub.close()
