"""SR-114: the repin check is a cascade. JEV clears the easy links above its calibrated
threshold, Sonnet judges the rest, and a link Sonnet says changed goes to Opus, which says
whether the record is reworded, the change goes back to development, or the owner gets a
card (SR-113). Fake JEV backends, judges and dispatchers only."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.stale_asked import asked
from iaso import links, stale
from iaso.api import open_core
from iaso.cli import main
from iaso.config import config_from_mapping
from iaso.contracts import DispatchError, Target
from iaso.understand import repin
from iaso.understand.repin import JevTier, Meaning, ModelDiagnoser

pytestmark = pytest.mark.sr("SR-242")

INT1 = """---
id: INT-001
title: Arithmetic helpers
quote: "the calculator adds"
readback: The calculator adds two numbers.
---
"""
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
REFORMATTED = "def add(a, b):\n    return a  +  b\n"
CHANGED = "def add(a, b):\n    return a * b\n"
LINK = "SR-001#1"           # #0 is the derives_from link to INT-001
TURN = "make the cold start faster"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, INT1)
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/calc.py", symbol="add"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    return repo


def _edit(repo: Path, text: str, turn: str | None = None) -> None:
    if turn is not None:   # the owner's prompt is logged a minute before the edit
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
        prompts = Path(open_core(repo).paths.prompts)
        prompts.parent.mkdir(parents=True, exist_ok=True)
        with prompts.open("a", encoding="utf-8") as out:
            out.write(json.dumps({"digest": "sha256:x", "session": "s1", "at": at,
                                  "text": turn, "via": "hook"}) + "\n")
    (repo / "src" / "calc.py").write_text(text, "utf-8")


def _state(repo: Path) -> str:
    (state,) = [s for s in open_core(repo).link_states(["SR-001"]) if s.link.id == LINK]
    return state.state


class Judge:
    """Sonnet with a fixed verdict; it records what it was shown."""

    def __init__(self, unchanged: bool | None, reason: str = "only formatting") -> None:
        self.answer, self.asked = Meaning(unchanged, reason, 0.9), []

    def same_meaning(self, **shown):
        self.asked.append(shown)
        return self.answer


class Backend:
    """A JEV backend giving ``p`` (or raising when ``p`` is None); records the prompts."""

    def __init__(self, p: float | None) -> None:
        self.p, self.asked = p, []

    def _ask(self, questions, prefix):
        from iaso.judgment import JudgmentUnavailable

        self.asked.append((questions, prefix))
        if self.p is None:
            raise JudgmentUnavailable("JEV", "timed out")
        return SimpleNamespace(answers={"yes_no": SimpleNamespace(value=self.p)})


class Dispatcher:
    """The Opus dispatcher with a fixed answer (or a DispatchError); records the inputs."""

    name, model = "claude-code", "opus"

    def __init__(self, answer: dict | None) -> None:
        self.answer, self.seen = answer, []

    def run(self, job, *, system, user, schema, on_step):
        self.seen.append((job.kind, json.loads(user), system))
        if self.answer is None:
            raise DispatchError("run", "the model could not be reached")
        return self.answer


def _runner(paths):
    return True, "ran"


def _resolve(repo: Path, *, judge=None, jev=None, answer=None, dry_run=False):
    diagnoser = ModelDiagnoser(Dispatcher(answer)) if answer is not ... else None
    result = links.repin_after_tests(open_core(repo), LINK, runner=_runner, judge=judge,
                                     jev=jev, diagnoser=diagnoser, session="s1",
                                     dry_run=dry_run)
    return result, diagnoser


def test_ex1_jev_above_threshold_repins_without_sonnet(project: Path) -> None:
    _edit(project, REFORMATTED)
    sonnet, backend = Judge(True), Backend(0.9)
    result, _ = _resolve(project, judge=sonnet, jev=JevTier(backend, 0.8))
    assert [c["link"] for c in result.changes] == [LINK] and result.refused == []
    assert result.changes[0]["tier"] == "jev"
    assert sonnet.asked == []                                    # Sonnet is not asked
    assert _state(project) == "current"
    (entry,) = open_core(project).log_read("events", ["repin"])
    assert entry.payload["note"].startswith("tests pass, meaning unchanged (jev)")
    # the question JEV is asked is the one the repin eval scores
    ((name, question),), prefix = backend.asked[0]
    assert question.instructions == repin.JEV_QUESTION
    from iaso.understand import evalrepin

    assert evalrepin.JEV_QUESTION == repin.JEV_QUESTION
    assert "add returns the sum." in prefix and "+    return a  +  b" in prefix


def test_ex2_jev_below_threshold_goes_to_sonnet(project: Path) -> None:
    _edit(project, REFORMATTED)
    sonnet = Judge(True)
    result, _ = _resolve(project, judge=sonnet, jev=JevTier(Backend(0.4), 0.8))
    (shown,) = sonnet.asked
    assert "add returns the sum." in shown["requirement"] and "a  +  b" in shown["after"]
    assert [c["link"] for c in result.changes] == [LINK]
    assert result.changes[0]["tier"] == "sonnet"
    (entry,) = open_core(project).log_read("events", ["repin"])
    assert entry.payload["note"].startswith("tests pass, meaning unchanged (sonnet)")


REWORD = {"outcome": "reword", "topic": "Adds numbers",
          "explanation": "SR-001 says add sums, while INT-001 now asks for products",
          "proposed_wording": "add returns the product."}


def test_ex3_requirement_disagreeing_with_intent_is_reworded(project: Path) -> None:
    _edit(project, CHANGED)
    result, diagnoser = _resolve(project, judge=Judge(False, "add now multiplies"),
                                 answer=REWORD)
    ((kind, inputs, system),) = diagnoser.dispatcher.seen
    assert kind == "diagnose" and "intent" in system.lower()
    assert inputs["intents"][0]["id"] == "INT-001"
    assert "The calculator adds two numbers." in inputs["intents"][0]["text"]
    assert inputs["sonnet_reason"] == "add now multiplies"
    assert "-    return a + b" in inputs["diff"]
    (item,) = result.diagnoses
    assert item["outcome"] == "reword" and item["asked"] is False
    ((link, why),) = result.refused
    assert link == LINK and "add returns the product." in why and "iaso capture" in why
    assert "development" not in why
    assert asked(project, "s1") == [] and _state(project) == "stale"


BACK = {"outcome": "back-to-development", "topic": "Adds numbers",
        "explanation": "the turn was about start-up time, not about what add returns",
        "broken_example": "SR-001/EX-1 (1 and 2 now give 2, not 3)"}


def test_ex4_change_away_from_agreeing_intent_goes_back_to_development(project: Path) -> None:
    _edit(project, CHANGED, turn=TURN)
    result, diagnoser = _resolve(project, judge=Judge(False, "add now multiplies"),
                                 answer=BACK)
    ((_, inputs, _),) = diagnoser.dispatcher.seen
    assert inputs["turn"]["text"] == TURN and "not proof" in inputs["turn"]["note"]
    ((link, why),) = result.refused
    assert "back to development" in why and TURN in why
    assert "SR-001/EX-1" in why and "src/calc.py: +1/-1 lines" in why
    (item,) = result.diagnoses
    assert item["outcome"] == "back-to-development" and item["turn"]["text"] == TURN
    assert asked(project, "s1") == []               # the owner is not asked


OWNER = {"outcome": "owner", "topic": "Adds numbers",
         "explanation": "INT-001 wants a sum, add now multiplies, and the turn does not say "
                        "whether that was wanted",
         "options": ["Keep it and reword SR-001", "Undo the change"]}


def test_ex5_unclear_change_becomes_an_owner_question(project: Path) -> None:
    _edit(project, CHANGED, turn=TURN)
    result, _ = _resolve(project, judge=Judge(False, "add now multiplies"), answer=OWNER)
    (card,) = asked(project, "s1")
    assert card["link"] == LINK and card["topic"] == "Adds numbers"
    assert card["issue"] == OWNER["explanation"] and card["options"] == OWNER["options"]
    (item,) = result.diagnoses
    assert item["outcome"] == "owner" and item["asked"] is True
    assert "question" in result.refused[0][1] and result.changes == []
    assert LINK in stale.asked_links(open_core(project), "s1")   # the hold counts it as asked


def test_ex5_owner_question_with_consequences_holds_the_link(project: Path) -> None:
    _edit(project, CHANGED, turn=TURN)
    answer = {**OWNER, "consequences": ["add multiplies; the sum is gone",
                                        "add sums again; the product is gone"],
              "why": "the owner's words ask for a sum"}
    result, _ = _resolve(project, judge=Judge(False, "add now multiplies"), answer=answer)
    (card,) = asked(project, "s1")
    first = card["descriptions"][0]
    assert answer["consequences"][0] in first and answer["why"] in first
    assert card["by"] == "diagnosis" and result.diagnoses[0]["asked"] is True
    assert LINK in stale.asked_links(open_core(project), "s1")


def test_ex5_dry_run_diagnoses_but_files_no_card(project: Path) -> None:
    _edit(project, CHANGED)
    result, diagnoser = _resolve(project, judge=Judge(False, "add now multiplies"),
                                 answer=OWNER, dry_run=True)
    assert len(diagnoser.dispatcher.seen) == 1
    (item,) = result.diagnoses
    assert item["outcome"] == "owner" and item["asked"] is False
    assert asked(project, "s1") == [] and _state(project) == "stale"


def test_dry_run_runs_jev_and_repins_nothing(project: Path) -> None:
    _edit(project, REFORMATTED)
    result, _ = _resolve(project, judge=Judge(True), jev=JevTier(Backend(0.95), 0.8),
                         dry_run=True)
    ((link, why),) = result.would
    assert link == LINK and why.startswith("jev: JEV gives 0.95")
    assert result.changes == [] and _state(project) == "stale"


@pytest.mark.parametrize("jev", ["no-threshold", "unreachable"])
def test_ex6_jev_skipped_sonnet_judges(project: Path, jev: str) -> None:
    _edit(project, REFORMATTED)
    if jev == "no-threshold":
        core = open_core(project)
        assert core.config.understand.repin_jev_threshold is None
        assert repin.open_jev_tier(core) is None
        tier = None
    else:
        tier = JevTier(Backend(None), 0.8)
    sonnet = Judge(True)
    result, _ = _resolve(project, judge=sonnet, jev=tier)
    assert len(sonnet.asked) == 1
    assert result.changes[0]["tier"] == "sonnet"


def test_ex6_nothing_is_repinned_on_a_guess(project: Path, monkeypatch) -> None:
    _edit(project, REFORMATTED)
    monkeypatch.setattr(repin, "open_judge", lambda core: None)
    result, _ = _resolve(project, jev=JevTier(Backend(None), 0.8))
    assert result.changes == [] and "no model" in result.refused[0][1]
    assert _state(project) == "stale"


@pytest.mark.parametrize("answer", [None, {"outcome": "owner", "topic": "t",
                                           "explanation": "unclear", "options": ["only one"]},
                                    {"outcome": "maybe", "topic": "t", "explanation": "e"}])
def test_opus_unreachable_or_unusable_is_a_plain_refusal(project: Path, answer) -> None:
    _edit(project, CHANGED)
    result, _ = _resolve(project, judge=Judge(False, "add now multiplies"), answer=answer)
    ((link, why),) = result.refused
    assert why.startswith("the model says the meaning changed: add now multiplies")
    assert "no diagnosis" in why
    assert result.diagnoses == [] and asked(project, "s1") == []
    assert _state(project) == "stale"


def test_no_diagnoser_configured_is_the_plain_refusal(project: Path) -> None:
    _edit(project, CHANGED)
    result = links.repin_after_tests(open_core(project), LINK, runner=_runner,
                                     judge=Judge(False, "add now multiplies"))
    assert result.refused == [(LINK, "the model says the meaning changed: add now multiplies")]


def test_cli_prints_the_diagnosis(project: Path, capsys, monkeypatch) -> None:
    _edit(project, CHANGED)
    monkeypatch.setattr(links, "default_runner", lambda core, budget_s=None: _runner)
    monkeypatch.setattr(repin, "open_judge", lambda core: Judge(False, "add now multiplies"))
    monkeypatch.setattr(repin, "open_diagnoser",
                        lambda core: ModelDiagnoser(Dispatcher(OWNER)))
    monkeypatch.setenv("IASO_SESSION_ID", "s1")
    assert main(["repin", "--after-tests", LINK, "--root", str(project)]) == 1
    out = capsys.readouterr()
    assert f"{LINK} needs the owner (question filed): Adds numbers" in out.out
    assert "1. Keep it and reword SR-001" in out.out
    assert "filed as a question for the owner" in out.err
    assert main(["repin", "--after-tests", LINK, "--dry-run", "--json",
                 "--root", str(project)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["diagnoses"][0]["outcome"] == "owner"


def _snapshot(repo: Path) -> dict[str, bytes]:
    """Every file in the project (records, logs, the pin blob store); not git's object store
    and not the derived read cache."""
    files = {}
    for path in repo.rglob("*"):
        rel = path.relative_to(repo).as_posix()
        kept = not rel.startswith(".git/") or rel.startswith(".git/iaso")
        if path.is_file() and kept and not rel.startswith(".iaso/cache/"):
            files[rel] = path.read_bytes()
    return files


@pytest.mark.sr("SR-198")
@pytest.mark.parametrize("after_tests", [False, True], ids=["pins-only", "after-tests"])
@pytest.mark.parametrize("selector", [LINK, "SR-001", "--all-stale"],
                         ids=["link", "record", "all-stale"])
def test_dry_run_changes_nothing(project: Path, capsys, monkeypatch, selector: str,
                                 after_tests: bool) -> None:
    """A dry run prints what it would repin and writes no file and no log entry."""
    if after_tests and selector == "--all-stale":
        pytest.skip("--after-tests takes one link id or record ID")
    _edit(project, REFORMATTED)
    monkeypatch.setattr(links, "default_runner", lambda core, budget_s=None: _runner)
    monkeypatch.setattr(repin, "open_judge", lambda core: Judge(True))
    monkeypatch.setattr(repin, "open_jev_tier", lambda core: None)
    before = _snapshot(project)
    argv = ["repin", selector, "--dry-run", "--root", str(project)]
    if after_tests:
        argv.insert(1, "--after-tests")
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "would repin" in out and (LINK in out)
    assert _snapshot(project) == before and _state(project) == "stale"
    assert main(argv + ["--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["repinned"] == [] and [w["link"] for w in data["would_repin"]] == [LINK]
    assert _snapshot(project) == before


def test_config_reads_the_cascade_settings() -> None:
    settings = config_from_mapping({"understand": {"repin_jev_threshold": 0.83}}).understand
    assert settings.repin_jev_threshold == 0.83 and settings.diagnose_model == "opus"


@pytest.mark.sr("SR-198")
def test_sr166_default_runner_lets_the_meaning_judge_gate_when_no_test_covers(project: Path,
                                                                monkeypatch) -> None:
    class Lane:
        def run(self, changed, budget_s=None):
            return SimpleNamespace(run_id=None)

    monkeypatch.setattr("iaso.verify.open_verify", lambda core: Lane())
    ok, detail = links.default_runner(open_core(project))(["notes.md"])
    assert ok and detail == "no test covers notes.md: judged on meaning only"


@pytest.mark.sr("SR-198")
def test_sr166_untested_end_repins_on_meaning_with_the_gap_in_the_note(project: Path) -> None:
    _edit(project, REFORMATTED)
    untested = "no test covers src/calc.py: judged on meaning only"
    result = links.repin_after_tests(open_core(project), LINK, judge=Judge(True),
                                     runner=lambda paths: (True, untested))
    assert [c["link"] for c in result.changes] == [LINK]
    (entry,) = open_core(project).log_read("events", ["repin"])
    assert entry.payload["note"].endswith(f"(no test gate: {untested})")
    _edit(project, CHANGED)                       # a changed meaning is still not repinned
    result = links.repin_after_tests(open_core(project), LINK, judge=Judge(False, "sums"),
                                     runner=lambda paths: (True, untested))
    assert result.changes == []
