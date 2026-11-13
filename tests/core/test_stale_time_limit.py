"""SR-310, SR-175: the stale check at the turn end runs within the stop hook's remaining
time. ``settle_drift`` takes a budget, passes what is left to the repin's test run and stops
judging when it is gone (the check waits, nothing is decided), and the stop hook hands it the
deadline's remainder, so one slow stale link never pushes the hook into the watchdog's hard
limit (case hook-stop-e98405d1)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from iaso import links, stale
from iaso.api import open_core
from iaso.contracts import Target
from iaso.understand import repin

pytestmark = pytest.mark.sr("SR-310")

SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""
CODE = "def add(a, b):\n    return a + b\n"
REFACTORED = "def add(a, b):\n    return b + a\n"
LINK = "SR-001#0"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py", symbol="add"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    (repo / "src" / "calc.py").write_text(REFACTORED, "utf-8")
    monkeypatch.setattr(repin, "open_jev_tier", lambda core: None)
    judge = SimpleNamespace(same_meaning=lambda **shown: repin.Meaning(True, "said so", 1.0))
    monkeypatch.setattr(repin, "open_judge", lambda core: judge)
    return repo


def _state(repo: Path) -> str:
    return [s for s in open_core(repo).link_states(["SR-001"]) if s.link.id == LINK][0].state


def test_settle_drift_out_of_time_runs_no_tests_and_waits(project: Path, monkeypatch) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(links, "default_runner", lambda core, budget_s=None:
                        lambda paths: ran.append(paths) or (True, "passed"))
    core = open_core(project)
    waiting: set[str] = set()
    said = stale.settle_drift(core, "s1", stale.stale_rows(core), waiting, budget_s=0.0)
    assert ran == []                       # no test run starts past the deadline
    assert _state(project) == "stale"      # nothing decided: the check runs again later
    assert waiting == {"SR-001"} and said and "time" in said[0]
    assert list(core.log_read("events", ["repin"])) == []


def test_settle_drift_passes_the_remaining_budget_to_the_test_run(project: Path,
                                                                     monkeypatch) -> None:
    seen: list[float | None] = []

    def runner(core, budget_s=None):
        seen.append(budget_s)
        return lambda paths: (True, "passed")

    monkeypatch.setattr(links, "default_runner", runner)
    core = open_core(project)
    stale.settle_drift(core, "s1", stale.stale_rows(core), set(), budget_s=7.0)
    assert len(seen) == 1 and seen[0] is not None and 0 < seen[0] <= 7.0
    assert _state(project) == "current"


def test_default_runner_bounds_the_run_by_the_budget(project: Path, monkeypatch) -> None:
    from iaso import verify

    asked: list[float | None] = []

    class Lane:
        def run(self, *, changed, budget_s=None):
            asked.append(budget_s)
            return SimpleNamespace(run_id=None)

    monkeypatch.setattr(verify, "open_verify", lambda core: Lane())
    core = open_core(project)
    links.default_runner(core, 7.0)(["src/calc.py"])
    links.default_runner(core)(["src/calc.py"])
    assert asked == [links.test_budget_s(core, 7.0), links.REPIN_BUDGET_S]
    assert asked[0] < 7.0   # the lane kills at budget * hard_limit_factor: inside the 7 s


def test_stop_hook_hands_the_stale_check_its_remaining_time(project: Path, monkeypatch) -> None:
    from iaso.hosts.claude_code import stop
    from iaso.hosts.claude_code.hookio import Deadline, HookContext

    row = SimpleNamespace(link=LINK, record="SR-001", what="src/calc.py")
    given: list[dict] = []

    def settle(core, session, rows, waiting=None, *, budget_s=None):
        given.append({"budget_s": budget_s})
        return []

    monkeypatch.setattr(stale, "turn_state",
                        lambda core, s, t: SimpleNamespace(valid=True, before=[]))
    monkeypatch.setattr(stale, "unresolved", lambda core, s, state: [row])
    monkeypatch.setattr(stale, "settle_drift", settle)
    monkeypatch.setattr(stale, "ask_lost_tests", lambda core, s: None)
    ctx = HookContext("stop", {}, project, "s1", Deadline(20_000), extra={})
    core = open_core(project)
    stop.stale_hold(ctx, core, core.index(), {"turn_id": "t1"}, 0.0)
    assert len(given) == 1
    budget = given[0]["budget_s"]
    assert budget is not None and 0 < budget <= 20.0


# -- round 3: the budget alone is not enough (the round-1 review); each step inside the repin
# is cut to the time left, and the lane's time is capped under the watchdog's hard limit


class _Judge:
    """A reachable judge that records the time limit it is given and every call."""

    def __init__(self) -> None:
        self.limits: list[float] = []
        self.calls = 0

    def time_limit(self, seconds: float) -> None:
        self.limits.append(seconds)

    def same_meaning(self, **shown):
        self.calls += 1
        return repin.Meaning(True, "said so", 1.0)


def test_no_model_call_once_the_tests_used_up_the_time(project: Path) -> None:
    import time

    def slow_tests(paths):
        time.sleep(0.15)
        return True, "passed"

    judge = _Judge()
    step = links.repin_after_tests(open_core(project), "SR-001", runner=slow_tests, judge=judge,
                                   budget_s=0.05)
    assert judge.calls == 0 and judge.limits == []
    assert step.refused == [(LINK, links.OUT_OF_TIME)]
    assert step.unreachable == links.OUT_OF_TIME and step.changes == []
    assert _state(project) == "stale"


def test_the_judge_and_the_test_run_are_cut_at_the_time_left(project: Path) -> None:
    judge = _Judge()
    core = open_core(project)
    step = links.repin_after_tests(core, "SR-001", runner=lambda paths: (True, "passed"),
                                   judge=judge, budget_s=5.0)
    assert judge.calls == 1 and len(judge.limits) == 1 and 0 < judge.limits[0] <= 5.0
    assert step.changes and _state(project) == "current"
    # the lane kills a run at budget * verify.hard_limit_factor: the budget it gets is sized
    # so the kill lands inside the time left; an explicit repin keeps its own budget
    factor = float(core.config.verify.hard_limit_factor)
    assert links.test_budget_s(core, 7.0) == pytest.approx(7.0 / factor)
    assert links.test_budget_s(core, 1000.0) == links.REPIN_BUDGET_S
    assert links.test_budget_s(core, None) == links.REPIN_BUDGET_S


def test_a_run_whose_tests_were_all_deferred_by_time_is_not_read_as_untested(
        project: Path, monkeypatch) -> None:
    from iaso import verify

    class Lane:
        def run(self, *, changed, budget_s=None):
            return SimpleNamespace(run_id=None, selection=SimpleNamespace(deferred=("t_a",)))

    monkeypatch.setattr(verify, "open_verify", lambda core: Lane())
    core = open_core(project)
    assert links.default_runner(core, 1.0)(["src/calc.py"]) == (False, links.OUT_OF_TIME)
    ok, detail = links.default_runner(core)(["src/calc.py"])   # no budget: a plain untested end
    assert ok and detail.startswith("no test covers")


def test_a_test_run_cut_by_the_hook_time_waits_and_opens_no_case(project: Path,
                                                                  monkeypatch) -> None:
    from iaso import debug

    monkeypatch.setattr(links, "default_runner",
                        lambda core, budget_s=None: lambda paths: (False, links.OUT_OF_TIME))
    opened: list[str] = []
    monkeypatch.setattr(debug, "open_case", lambda root, **kw: opened.append(kw["id"]))
    core = open_core(project)
    waiting: set[str] = set()
    stale.settle_drift(core, "s1", stale.stale_rows(core), waiting, budget_s=5.0)
    assert opened == [] and waiting == {"SR-001"} and _state(project) == "stale"


def test_the_covering_selection_does_not_start_without_room_under_the_hard_limit(
        project: Path) -> None:
    import time

    from iaso.hosts.claude_code import stop
    from iaso.hosts.claude_code.hookio import HARD_LIMIT_S, Deadline, HookContext

    class Verify:
        selected = 0

        def select(self, changed, *, budget_s=None):
            Verify.selected += 1
            return SimpleNamespace(nodes=(), deferred=())

        def full_pending(self):
            return None

    def verification(budget_ms: float, elapsed: float) -> tuple[int, list[str]]:
        Verify.selected, skipped = 0, []
        ctx = HookContext("stop", {}, project, "s1",
                          Deadline(budget_ms, start=time.monotonic() - elapsed), extra={})
        core = open_core(project)
        stop._verification(ctx, core, Verify(), core.index(), {}, [], ["src/calc.py"], 0.0,
                           {}, skipped)
        return Verify.selected, skipped

    # a soft budget set past the hard limit is not expired, yet the watchdog is 5 s away
    assert verification(200_000, HARD_LIMIT_S - 5.0) == (0, ["covering tests"])
    assert verification(200_000, 10.0) == (1, [])


def test_time_limit_only_lowers_a_model_timeout() -> None:
    judge = repin.ModelMeaningJudge(SimpleNamespace(timeout_s=120.0))
    judge.time_limit(5.0)
    judge.time_limit(50.0)
    assert judge.dispatcher.timeout_s == 5.0
    judge.time_limit(0.0)
    assert judge.dispatcher.timeout_s > 0          # zero would mean "no timeout" to a socket
    tier = repin.JevTier(SimpleNamespace(client=SimpleNamespace(timeout_s=10.0)), 0.9)
    tier.time_limit(3.0)
    assert tier.backend.client.timeout_s == 3.0
    repin.ModelDiagnoser(SimpleNamespace(timeout_s=120.0)).time_limit(2.0)
    repin.ModelMeaningJudge(SimpleNamespace()).time_limit(2.0)   # a stub with no timeout: fine


def test_the_stale_lane_is_capped_under_the_hard_limit(project: Path) -> None:
    import time

    from iaso.hosts.claude_code import stop
    from iaso.hosts.claude_code.hookio import HARD_LIMIT_S, Deadline, HookContext

    def ctx(budget_ms: float, elapsed: float) -> HookContext:
        return HookContext("stop", {}, project, "s1",
                           Deadline(budget_ms, start=time.monotonic() - elapsed), extra={})

    # the soft budget bounds it: 60 s budget, 50 s gone
    assert 9.0 < stop.time_left_s(ctx(60_000, 50.0)) <= 10.0
    # a soft budget past the hard limit never lets the lane reach the watchdog
    reserve = stop.HARD_RESERVE_S
    assert stop.time_left_s(ctx(200_000, HARD_LIMIT_S - reserve - 5.0)) <= 5.0
    assert stop.time_left_s(ctx(200_000, HARD_LIMIT_S - 1.0)) == 0.0


def test_the_awareness_step_gets_a_deadline_capped_under_the_hard_limit(project: Path) -> None:
    import time

    from iaso.hosts.claude_code import stop
    from iaso.hosts.claude_code.hookio import HARD_LIMIT_S, Deadline, HookContext

    ctx = HookContext("stop", {}, project, "s1",
                      Deadline(200_000, start=time.monotonic() - (HARD_LIMIT_S - 1.0)), extra={})
    assert not ctx.deadline.expired()            # the soft budget alone would let git start
    assert stop.capped_deadline(ctx).expired()   # the capped one does not
