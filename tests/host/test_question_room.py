"""SR-333: plumb puts each question to the owner through the question tool; one with more to see
(a diagram, or a long text) offers to study it in the room. Choosing that judges nothing again:
the question waits in the room as a card, the band's line names it, and only the owner's press
opens the room on it. An answer given in the room is the owner's answer to the question: it
leaves what waits and goes back to the judge."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from host.test_answer_rejudge import ASK, judge_asks, judge_jobs, world  # noqa: F401
from mod.helpers import DIGEST, KEY, run_mod
from understand.test_judge_job import SESSION

from plumb.api import open_core
from plumb.browser import launch
from plumb.hosts.claude_code import question_answer, snapshot
from plumb.present import owner_text
from plumb.understand import cardstore, cmd_clarify, files, judge, question

pytestmark = pytest.mark.sr("SR-333")

ROOM = {"label": owner_text.ROOM_STUDY, "description": owner_text.ROOM_STUDY_NOTE}
ORIGIN = "http://127.0.0.1:50123"


def asking(repo: Path, text: str = ASK, *, diagram: bool = False, options: int = 2) -> None:
    """The judge's one open question about SR-001, with ``options`` options."""
    judge_asks(repo, (text, ["SR-001"]))
    path = judge.questions_path(repo, SESSION)
    (asked,) = files.read_json(path)
    asked["options"] += [{"label": f"Other {n}", "description": "Else."}
                         for n in range(options - 2)]
    files.write_json_atomic(path, [{**asked, "diagram": diagram}])


def shown(repo: Path) -> dict[str, Any]:
    outcome = cmd_clarify.wait(open_core(repo), SESSION, timeout=10)
    assert outcome.state == "ask"
    (put,) = outcome.questions
    return put


def waits_in_room(repo: Path) -> list[str]:
    return [c.id for c in cardstore.load(repo, SESSION)]


def mark(repo: Path) -> Path:
    return files.session_dir(repo, SESSION) / question.ROOM_WAITS


@pytest.fixture
def no_browser(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr(launch, "_start", lambda root, token: ORIGIN)
    monkeypatch.setattr(launch, "_alive", lambda origin, token: False)
    monkeypatch.setattr(launch.webbrowser, "open", opened.append)
    return opened


@pytest.fixture
def studied(world: Path, hook_input: Any, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
            capsys: pytest.CaptureFixture[str]) -> tuple[Path, str, str]:
    """The owner chose to study the judge's question (which needs a diagram) in the room;
    the panel is registered. ``(repo, card id, what the hook told the agent)``."""
    asking(world, diagram=True)
    put = shown(world)
    payload = hook_input("PostToolUse", tool_name="AskUserQuestion",
                         tool_input={"questions": [put]},
                         tool_response={"answers": {put["question"]: ROOM["label"]}},
                         session_id=SESSION)
    out = io.StringIO()
    assert question_answer.main(stdin=io.StringIO(payload), stdout=out, root=world) == 0
    assert run_mod(monkeypatch, capsys, world, "hello", stdin={"key_digest": DIGEST})[0] == 0
    (card,) = waits_in_room(world)
    return world, card, out.getvalue()


def test_ex1_a_short_question_offers_no_room(world: Path, no_browser) -> None:  # noqa: F811
    """EX-1: options that fit in a few lines: the question tool, no option to study it."""
    asking(world)
    put = shown(world)
    assert put["question"] == ASK and ROOM not in put["options"]
    assert [o["label"] for o in put["options"]] == ["Public pages (Recommended)", "Every page"]


@pytest.mark.parametrize("need", ["a diagram", "a long text", "a diagram and four options"])
def test_ex2_a_question_with_more_to_see_offers_the_room_which_stays_closed(
        world: Path, no_browser, need: str) -> None:  # noqa: F811
    """EX-2: a question that needs a diagram (or whose text runs past ``ROOM_TEXT_MAX``) comes
    through the question tool with 'Study it in the room' last, within its four options; the
    room does not open, nothing waits in it."""
    long = need == "a long text"
    asking(world, ASK + " " + "Which pages count as public? " * 30 if long else ASK,
           diagram=not long, options=4 if "four" in need else 2)
    put = shown(world)
    assert put["options"][-1] == ROOM and len(put["options"]) <= 4
    assert put["options"][0]["label"] == "Public pages (Recommended)"
    assert no_browser == [] and waits_in_room(world) == [] and not mark(world).exists()


def test_ex3_chosen_the_question_waits_in_the_room_and_the_press_opens_it(
        studied: tuple[Path, str, str], no_browser: list[str],
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """EX-3: 'Study it in the room' chosen: no answer goes to the judge; the question waits in
    the room with its diagram (the agent is told to draw it) and is not asked again; the band's
    mark names it; the owner's press opens the room on it and the mark goes."""
    repo, card, told = studied
    assert judge_jobs(repo) == []
    (waiting,) = cardstore.load(repo, SESSION)
    assert waiting.issue == ASK and waiting.diagram.endswith(".html")
    assert waiting.diagram in told and "diagram:architecture-diagram" in told
    assert [c.label for c in waiting.questions[0].choices] == [
        "Public pages (Recommended)", "Every page"]
    assert cmd_clarify.wait(open_core(repo), SESSION, timeout=10).state == "ready"
    assert snapshot.awaiting_count(open_core(repo)) == 1
    assert files.read_json(mark(repo)) == {"card": card}
    assert no_browser == []                      # the room never opens by itself
    code, opened, _ = run_mod(monkeypatch, capsys, repo, "room", "--card", card,
                              stdin={"key": KEY})
    assert code == 0 and opened == {"origin": ORIGIN, "card": card}
    token = launch.room_token(KEY)
    assert no_browser == [f"{ORIGIN}/?session={SESSION}&card={card.replace(':', '%3A')}"
                          f"#token={token}"]
    assert not mark(repo).exists() and waits_in_room(repo) == [card]


def test_ex3_without_the_owners_key_the_room_stays_closed(
        studied: tuple[Path, str, str], no_browser: list[str],
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo, card, _ = studied
    assert run_mod(monkeypatch, capsys, repo, "room", "--card", card,
                   stdin={"key": "b2" * 32})[0] == 3
    assert no_browser == [] and mark(repo).exists()


def test_ex5_an_answer_in_the_room_leaves_what_waits_and_goes_to_the_judge(
        studied: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """EX-5: the owner answers in the room: the question is not among what waits at the next
    prompt or turn end, and their answer goes back to the judge with its records."""
    repo, card, _ = studied
    _, drawn, _ = run_mod(monkeypatch, capsys, repo, "draw", stdin={"key": KEY})
    (offer,) = [o for c in drawn["cards"] if c["id"] == card for o in c["offers"]]
    code, done, _ = run_mod(monkeypatch, capsys, repo, "press", "--offer", offer["offer_id"],
                            "--choice", "1", stdin={"key": KEY})
    assert code == 0 and done["confirmed"] == []      # an answer to the judge, not a confirmation
    core = open_core(repo)
    assert waits_in_room(repo) == [] and snapshot.awaiting_count(core) == 0
    assert judge.open_questions(core, SESSION) == []
    assert cardstore.states(core, SESSION)[card] == ("done", "")
    said = [e.payload for e in core.events() if e.kind == "question-answer"][-1]
    assert (said["question"], said["answer"]) == (ASK, "Every page")
    assert said["asked"]["records"] == [{"id": "SR-001", "hash": core.index()["SR-001"].hash}]
    (job,) = judge_jobs(repo)
    assert job.inputs["records"] == ["SR-001"]
