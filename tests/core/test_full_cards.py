"""SR-116 (INT-031): a stale card carries everything the owner needs to choose, and it is filed
in the session whose turn is in progress, so that session's end-of-turn hook sees it."""

from __future__ import annotations

import io
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from plumb import links, stale
from plumb.api import open_core
from plumb.cli import main
from plumb.contracts import Target
from plumb.understand import cardcontent, cardstore, fullcard
from plumb.understand.repin import Meaning, ModelDiagnoser

pytestmark = pytest.mark.sr("SR-116")

QUOTE = "the calculator adds"
PROMPT = "please make sure the calculator adds two numbers, nothing fancy"
PROMPT_DIGEST = "sha256:" + "c5" * 32
INT1 = f"""---
id: INT-001
title: Arithmetic helpers
quote: "{QUOTE}"
readback: The calculator adds two numbers.
prompt: {PROMPT_DIGEST[7:23]}
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
CHANGED = "def add(a, b):\n    return a * b\n"
LINK = "SR-001#1"            # #0 is the derives_from link to INT-001
OPTIONS = "Keep it and reword the requirement|Undo the change"
CONSEQUENCES = ("add keeps multiplying and the requirement says so; the sum is gone"
                "|add sums again as the requirement says; the multiplying is dropped")
WHY = "your words ask for a sum, and nothing in the turn asked for a product"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _log_prompt(repo: Path) -> None:
    prompts = Path(open_core(repo).paths.prompts)
    prompts.parent.mkdir(parents=True, exist_ok=True)
    with prompts.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"digest": PROMPT_DIGEST, "session": "s1",
                              "at": "2026-10-01T10:00:00Z", "text": PROMPT,
                              "via": "hook"}) + "\n")


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
    _log_prompt(repo)
    return repo


def _turn(repo: Path, session: str, *, turn_id: str | None = "t1", age: float = 0.0) -> None:
    path = repo / ".plumb" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"turn_start": time.time() - age}
    if turn_id:
        data["turn_id"] = turn_id
    path.write_text(json.dumps(data), "utf-8")
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))


def _card_args(*extra: str) -> list[str]:
    return ["stale", "card", LINK, "--topic", "Adds numbers", "--issue",
            "add now multiplies instead of adding", "--options", OPTIONS, *extra]


# --------------------------------------------------------------------------- the session bug


def test_card_goes_to_the_live_session_not_a_newer_default(project: Path, capsys,
                                                           monkeypatch) -> None:
    """The bug: ``default`` had the newest turn file, so the card landed there and the live
    session's stop hook never saw it."""
    _turn(project, "live-1", age=60)
    _turn(project, "default", age=1)            # newer, but not a turn of any agent
    _turn(project, "cli", age=0)
    _turn(project, "perf-probe", age=0)
    assert stale.current_session(project) == "live-1"
    code = main([*_card_args("--consequences", CONSEQUENCES, "--why", WHY),
                 "--root", str(project)])
    assert code == 0, capsys.readouterr().err
    assert stale.read_cards(project, "default") == []
    assert [c["link"] for c in stale.read_cards(project, "live-1")] == [LINK]


def test_a_session_without_a_live_turn_is_skipped(project: Path) -> None:
    _turn(project, "live-1", age=60)
    _turn(project, "stopped", turn_id=None, age=0)
    assert stale.current_session(project) == "live-1"
    assert stale.current_session(project / "nowhere") == "cli"


def test_the_host_session_id_wins_over_the_newest_turn(project: Path, monkeypatch) -> None:
    _turn(project, "other", age=0)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "6a18d0ce-4b7f")
    assert stale.current_session(project) == "6a18d0ce-4b7f"
    monkeypatch.setenv("PLUMB_SESSION_ID", "named")
    assert stale.current_session(project) == "named"


def test_the_stop_hook_of_the_host_session_sees_the_card(project: Path, capsys, monkeypatch,
                                                         hook_input) -> None:
    from plumb.hosts.claude_code import stop

    session = "abc-123"
    _turn(project, session, turn_id="t1", age=1)
    stale.write_baseline(open_core(project), session, "t1")
    _turn(project, "default", age=0)
    (project / "src" / "calc.py").write_text(CHANGED, "utf-8")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", session)
    assert main([*_card_args("--consequences", CONSEQUENCES, "--why", WHY),
                 "--root", str(project)]) == 0
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    state = stale.turn_state(open_core(project), session, "t1")
    assert stale.unresolved(open_core(project), session, state) == []
    out = io.StringIO()
    stop.main(stdin=io.StringIO(hook_input("Stop", session_id=session)), stdout=out,
              root=project, verify=None, unjudged=None)
    text = out.getvalue()
    assert '"decision": "block"' not in text


class _Dispatcher:
    name, model = "claude-code", "opus"

    def __init__(self, answer: dict) -> None:
        self.answer = answer

    def run(self, job, *, system, user, schema, on_step):
        return self.answer


class _Judge:
    def same_meaning(self, **shown):
        return Meaning(False, "add now multiplies", 0.9)


OWNER = {"outcome": "owner", "topic": "Adds numbers",
         "explanation": "your words ask for a sum, add now multiplies",
         "options": OPTIONS.split("|")}


def _cascade(repo: Path, answer: dict, session: str | None = None):
    (repo / "src" / "calc.py").write_text(CHANGED, "utf-8")
    return links.repin_after_tests(open_core(repo), LINK, runner=lambda paths: (True, "ran"),
                                   judge=_Judge(), diagnoser=ModelDiagnoser(_Dispatcher(answer)),
                                   session=session)


def test_the_cascade_owner_card_goes_to_the_live_session(project: Path, monkeypatch) -> None:
    _turn(project, "live-1", age=60)
    _turn(project, "default", age=0)
    _cascade(project, {**OWNER, "consequences": CONSEQUENCES.split("|"), "why": WHY})
    assert stale.read_cards(project, "default") == []
    (card,) = stale.read_cards(project, "live-1")
    assert card["by"] == "diagnosis" and stale.card_complete(card)
    assert LINK in stale.carded_links(project, "live-1")


def test_a_diagnosis_without_consequences_files_an_incomplete_card(project: Path) -> None:
    result = _cascade(project, OWNER, session="s1")
    (card,) = stale.read_cards(project, "s1")
    assert card["status"] == "open" and not stale.card_complete(card)
    assert LINK not in stale.carded_links(project, "s1")     # not offered: the hold holds
    (item,) = result.diagnoses
    assert item["card"] is True and item["card_missing"]
    assert "lacks" in result.refused[0][1] and "--consequences" in result.refused[0][1]


# --------------------------------------------------------------------------- refusal (EX-3)


@pytest.mark.parametrize("extra, named", [
    ((), "what option 1"),
    (("--consequences", CONSEQUENCES), "why the recommended option"),
    (("--why", WHY), "what option 2"),
    (("--consequences", "only one", "--why", WHY), "gives 1 for 2 options"),
])
def test_ex3_an_incomplete_card_is_refused_naming_what_is_missing(project: Path, capsys,
                                                                   extra, named) -> None:
    assert main([*_card_args(*extra), "--session", "s1", "--root", str(project)]) == 2
    err = capsys.readouterr().err
    assert "refused as incomplete" in err and named in err
    assert stale.read_cards(project, "s1") == []


def test_completing_a_card_keeps_its_topic_issue_and_options(project: Path, capsys) -> None:
    stale.add_card(project, "s1", link=LINK, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="add multiplies", options=OPTIONS.split("|"),
                   recommended=1, turn=7)                       # filed before SR-116
    assert main(["stale", "card", LINK, "--consequences", CONSEQUENCES, "--why", WHY,
                 "--session", "s1", "--root", str(project)]) == 0, capsys.readouterr().err
    (card,) = stale.read_cards(project, "s1")
    assert card["topic"] == "Adds numbers" and card["issue"] == "add multiplies"
    assert card["options"] == OPTIONS.split("|") and card["recommended"] == 1
    assert card["turn"] == 7 and card["status"] == "open" and stale.card_complete(card)


# --------------------------------------------------------------------------- the content (SR-129)


def test_the_card_shows_its_options_consequences_and_why_and_no_diff(project: Path) -> None:
    (project / "src" / "calc.py").write_text(CHANGED, "utf-8")
    entry = stale.add_card(project, "s1", link=LINK, record="SR-001", path="src/calc.py",
                           topic="Adds numbers", issue="add now multiplies",
                           options=OPTIONS.split("|"), consequences=CONSEQUENCES.split("|"),
                           why=WHY)
    content = fullcard.stale_content(open_core(project), entry, session="s1")
    assert content["kind"] == "stale_link"
    assert content["context"] == [WHY] and content["link"] == LINK
    first, second = content["options"]
    assert first["recommended"] and first["consequence"].startswith("add keeps multiplying")
    assert second["consequence"].startswith("add sums again")
    text = fullcard.render(content)
    assert "  1. Keep it and reword the requirement (recommended) - add keeps multiplying" in text
    assert WHY in text and "return a * b" not in text
    json.dumps(content)                                     # plain data for present.json


def test_owner_words_not_on_file_are_said_plainly(project: Path, write_record) -> None:
    write_record(project, SR1.replace("SR-001", "SR-002").replace("Adds numbers", "Subtracts"))
    words = cardcontent.owner_words(open_core(project), open_core(project).index()["SR-002"])
    assert words == {"items": [], "note": 'The words of yours "Subtracts" came from are not '
                                          "on file."}


def test_an_intent_quoting_several_messages_shows_each(project: Path, write_record) -> None:
    write_record(project, "---\nid: INT-002\ntitle: Two asks\nquote:\n- first ask\n- 'B'\n"
                          "readback: Both.\n---\n")
    write_record(project, SR1.replace("SR-001", "SR-002"))
    open_core(project).add_link("SR-002", "derives_from", Target(record="INT-002"))
    words = cardcontent.owner_words(open_core(project), open_core(project).index()["SR-002"])
    assert words["items"][0]["quote"] == "first ask / B"


def test_the_words_a_requirement_came_from_are_the_quote_and_the_logged_message(
        project: Path) -> None:
    words = cardcontent.owner_words(open_core(project), open_core(project).index()["SR-001"])
    (item,) = words["items"]
    assert item["id"] == "INT-001" and item["quote"] == QUOTE and item["prompt"] == PROMPT


# --------------------------------------------------------------------------- old cards stay open


def test_an_old_card_loads_and_shows_its_options_without_a_placeholder(
        project: Path, capsys) -> None:
    raw = [{"link": LINK, "record": "SR-001", "path": "src/calc.py", "topic": "Adds numbers",
            "issue": "add multiplies", "options": ["Keep it", "Undo it"], "recommended": 0,
            "turn": 3, "status": "open"}]
    file = stale.cards_path(project, "old")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(raw), "utf-8")
    before = file.read_text("utf-8")
    (card,) = cardstore.load(project, "old")                 # still offered as before
    assert card.kind == "stale_link" and card.status == "open"
    (content,) = [fullcard.stale_content(open_core(project), e, session="old")
                  for e in stale.read_cards(project, "old")]
    assert [o["consequence"] for o in content["options"]] == [None, None]
    assert content["context"] == [] and content["missing"]
    assert fullcard.render(content).splitlines()[-2:] == ["  1. Keep it (recommended)",
                                                         "  2. Undo it"]
    assert main(["stale", "cards", "--incomplete", "--root", str(project)]) == 0
    out = capsys.readouterr().out
    assert f"{LINK} (session old) lacks: what option 1" in out
    assert "plumb stale card SR-001#1 --session old" in out
    assert main(["stale", "cards", "--incomplete", "--json", "--root", str(project)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [c["link"] for c in data["cards"]] == [LINK]
    assert file.read_text("utf-8") == before                 # nothing resolved or rewritten


def test_stale_cards_lists_complete_ones_in_full(project: Path, capsys) -> None:
    stale.add_card(project, "s1", link=LINK, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="add multiplies", options=OPTIONS.split("|"),
                   consequences=CONSEQUENCES.split("|"), why=WHY)
    assert main(["stale", "cards", "--incomplete", "--root", str(project)]) == 0
    assert "no open stale cards lacking anything" in capsys.readouterr().out
    assert main(["stale", "cards", "--root", str(project)]) == 0
    out = capsys.readouterr().out
    assert WHY in out and "add sums again as the requirement says" in out and "lacks" not in out
