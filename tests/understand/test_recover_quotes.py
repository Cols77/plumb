"""SR-118: older records' words are found in past session transcripts by a cascade (a text
match, then JEV ranking, Sonnet picking the exact span, Opus examining a record its best
message does not support) and shown on the record's card, never trusted: a transcript match
confirms nothing and never counts as verified in triage. Fake models and a temp transcript
directory only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from plumb.api import open_core
from plumb.cli import main
from plumb.contracts import DispatchError
from plumb.understand import cardcontent, recover
from plumb.understand.recover import Cascade, ModelExaminer, ModelPicker

pytestmark = pytest.mark.sr("SR-118")

INT9 = """---
id: INT-009
title: Short cards
quote: "cards stay short"
readback: You want the cards kept short, one screen at most.
---
"""
INT15 = """---
id: INT-015
title: Dark theme
quote: "make it dark"
readback: You want a dark theme.
---
"""
INT20 = """---
id: INT-020
title: Weekly digest
quote: "send a digest"
readback: You want a daily digest by email.
---
"""
SR1 = """---
id: SR-001
title: Card length
statement: A card fits one screen.
examples:
- id: EX-1
  given: a card
  when: it is drawn
  then: it fits one screen
---
"""
OCT4 = ("I think the cards should be short. Keep each card to one screen at most, "
        "nobody scrolls a card.")
DIGEST = "Please send me a digest every week, by email, nothing daily."
OTHER = "Fix the failing test in the merge driver."


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    for text in (INT9, INT15, INT20, SR1):
        write_record(repo, text)
    from plumb.contracts import Target

    open_core(repo).add_link("SR-001", "derives_from", Target(record="INT-009"))
    return repo


def _line(text, at: str, session: str = "sess-1", **more) -> str:
    content = text if isinstance(text, (str, list)) else str(text)
    return json.dumps({"type": "user", "timestamp": at, "sessionId": session,
                       "message": {"role": "user", "content": content}, **more})


@pytest.fixture
def transcripts(tmp_path: Path, project: Path) -> Path:
    base = tmp_path / "projects"
    folder = base / recover.project_dir_name(project)
    folder.mkdir(parents=True)
    (folder / "sess-1.jsonl").write_text("\n".join([
        _line([{"type": "text", "text": OCT4}], "2026-10-04T09:12:00.000Z"),
        _line([{"type": "tool_result", "tool_use_id": "t", "content": "make it dark"}],
              "2026-10-04T09:13:00.000Z"),
        _line("<command-name>/plumb</command-name>", "2026-10-04T09:14:00.000Z"),
        _line("make it dark", "2026-10-04T09:15:00.000Z", isMeta=True),
        json.dumps({"type": "assistant", "timestamp": "2026-10-04T09:16:00.000Z",
                    "message": {"content": [{"type": "text", "text": "make it dark"}]}}),
        _line(OTHER, "2026-10-05T10:00:00.000Z"),
    ]) + "\n", "utf-8")
    (folder / "sess-2.jsonl").write_text(
        _line(DIGEST, "2026-10-06T08:00:00.000Z", session="sess-2") + "\n", "utf-8")
    return base


class Jev:
    """A JEV backend giving 0.9 to the message holding ``favour`` (None: unreachable)."""

    def __init__(self, favour: str | None) -> None:
        self.favour, self.asked = favour, 0

    def _ask(self, questions, prefix):
        from plumb.judgment import JudgmentUnavailable

        self.asked += 1
        if self.favour is None:
            raise JudgmentUnavailable("JEV", "timed out")
        ((_, question),) = questions
        probabilities = {}
        for name, _ in question.criteria:
            match = re.search(rf"^\[{name}\] \([^)]*\) (.*)$", prefix, re.MULTILINE)
            probabilities[name] = 0.9 if match and self.favour in match.group(1) else 0.05
        best = max(probabilities, key=probabilities.get)
        return SimpleNamespace(answers={"source": SimpleNamespace(
            value=best, probabilities=probabilities)})


class Dispatcher:
    """A model with a fixed answer, or a function of the inputs (or DispatchError)."""

    def __init__(self, model: str, answer) -> None:
        self.name, self.model, self.answer, self.seen = "claude-code", model, answer, []

    def run(self, job, *, system, user, schema, on_step):
        self.seen.append(json.loads(user))
        if self.answer is None:
            raise DispatchError("spawn", "not reachable")
        return self.answer(json.loads(user)) if callable(self.answer) else self.answer


def _picks(favour: str, span: str, supports: bool = True, reason: str = "it says so"):
    def answer(inputs):
        for message in inputs["messages"]:
            if favour in message["text"]:
                return {"message": message["id"], "span": span, "supports": supports,
                        "reason": reason}
        return {"message": "none", "span": "", "supports": False, "reason": "none says it"}
    return answer


def _cascade(core, jev, sonnet, opus=None) -> Cascade:
    return Cascade(core, jev=jev, picker=ModelPicker(sonnet),
                   examiner=ModelExaminer(opus or Dispatcher("opus", None)))


def _card(core, record_id: str) -> tuple[dict, list[str]]:
    content = cardcontent.card_content(core, {
        "link": f"{record_id}#9", "record": record_id, "topic": "words", "issue": "check",
        "options": []})
    return content["owner_words"], cardcontent.content_lines(content)


def _unverified(core, record_id: str) -> bool:
    from plumb.capture.triage import UNVERIFIED, _Prompts, premise_problem

    problem = premise_problem(_Prompts(core), core.index(), core.index()[record_id])
    return bool(problem and problem.startswith(UNVERIFIED))


def test_owner_messages_keep_only_what_the_owner_typed(project: Path, transcripts: Path) -> None:
    texts = [m.text for m in recover.owner_messages(project, transcripts)]
    assert texts == [OCT4, OTHER, DIGEST]


def test_ex1_the_span_and_date_are_shown_and_the_record_stays_proposed(
        project: Path, transcripts: Path) -> None:
    core = open_core(project)
    sonnet = Dispatcher("sonnet", _picks("cards should be short",
                                         "Keep each card to one screen at most"))
    outcome = recover.recover(core, ["INT-009"], transcripts=transcripts,
                              cascade=_cascade(core, Jev("cards should be short"), sonnet))
    assert outcome.errors == []
    (finding,) = outcome.findings
    assert (finding.status, finding.by) == ("found", "sonnet")
    assert finding.span == "Keep each card to one screen at most"
    assert finding.at.startswith("2026-10-04") and finding.session == "sess-1"
    # JEV ranked; Sonnet read only the best few, the best first
    assert OCT4 in sonnet.seen[0]["messages"][0]["text"]
    assert len(sonnet.seen[0]["messages"]) <= recover.TOP_K

    core = open_core(project)
    words, lines = _card(core, "INT-009")
    found = words["items"][0]["found"]
    assert found["span"] == "Keep each card to one screen at most"
    assert found["at"].startswith("2026-10-04") and found["note"] == recover.NOT_VERIFIED
    assert any("found in a transcript of 2026-10-04" in line and "not verified" in line
               and "Keep each card to one screen at most" in line for line in lines)
    # a requirement's card shows the words found for the intent it derives from
    sr_words, _ = _card(core, "SR-001")
    assert sr_words["items"][0]["found"]["span"] == "Keep each card to one screen at most"
    # a transcript match confirms nothing and is not verified words in triage
    assert core.status()["INT-009"].confirmation != "confirmed"
    assert _unverified(core, "INT-009")
    assert not list((project / ".plumb" / "log").rglob("*recover*"))


def test_a_quote_word_for_word_in_a_message_is_found_by_text_with_no_model(
        project: Path, transcripts: Path) -> None:
    core = open_core(project)
    path = transcripts / recover.project_dir_name(project) / "sess-3.jsonl"
    path.write_text(_line("Then: cards  stay\nshort, please.", "2026-10-07T07:00:00.000Z",
                          session="sess-3") + "\n", "utf-8")
    jev, sonnet = Jev("x"), Dispatcher("sonnet", None)
    outcome = recover.recover(core, ["INT-009"], transcripts=transcripts,
                              cascade=_cascade(core, jev, sonnet))
    (finding,) = outcome.findings
    assert (finding.status, finding.by, finding.span) == ("found", "text", "cards stay short")
    assert finding.session == "sess-3"
    assert jev.asked == 0 and sonnet.seen == []
    assert _unverified(open_core(project), "INT-009")


def test_ex2_words_in_no_transcript_are_said_not_found(project: Path,
                                                       transcripts: Path) -> None:
    core = open_core(project)
    sonnet = Dispatcher("sonnet", _picks("never in any message", ""))
    outcome = recover.recover(core, ["INT-015"], transcripts=transcripts,
                              cascade=_cascade(core, Jev("merge driver"), sonnet))
    (finding,) = outcome.findings
    assert finding.status == "not_found"
    words, lines = _card(open_core(project), "INT-015")
    assert words["items"][0]["found"]["status"] == "not_found"
    assert any(recover.NOT_FOUND in line for line in lines)


def test_ex2_no_transcript_at_all_is_not_found_without_a_model(project: Path,
                                                               tmp_path: Path) -> None:
    core = open_core(project)
    outcome = recover.recover(core, ["INT-015"], transcripts=tmp_path / "empty",
                              cascade=_cascade(core, Jev(None), Dispatcher("sonnet", None)))
    assert [f.status for f in outcome.findings] == ["not_found"] and outcome.errors == []


def test_ex3_a_record_its_message_does_not_support_gets_a_proposed_rewording(
        project: Path, transcripts: Path) -> None:
    core = open_core(project)
    sonnet = Dispatcher("sonnet", _picks("digest", "send me a digest every week",
                                         supports=False, reason="weekly, not daily"))
    opus = Dispatcher("opus", {"verdict": "misreads",
                               "explanation": "The record says daily; you asked for weekly.",
                               "proposed_wording": "You want a weekly digest by email."})
    outcome = recover.recover(core, ["INT-020"], transcripts=transcripts,
                              cascade=_cascade(core, Jev("digest"), sonnet, opus))
    (finding,) = outcome.findings
    assert (finding.status, finding.by) == ("misreads", "opus")
    assert opus.seen[0]["span"] == "send me a digest every week"
    words, lines = _card(open_core(project), "INT-020")
    assert words["items"][0]["found"]["proposed_wording"] == "You want a weekly digest by email."
    assert any("may misread you" in line for line in lines)
    assert any("proposed rewording" in line and "weekly digest" in line for line in lines)
    assert open_core(project).index()["INT-020"].fields["readback"].startswith(
        "You want a daily")   # nothing is rewritten by recovery


def test_no_model_answer_decides_nothing(project: Path, transcripts: Path) -> None:
    core = open_core(project)
    outcome = recover.recover(core, ["INT-020"], transcripts=transcripts,
                              cascade=_cascade(core, Jev(None), Dispatcher("sonnet", None)))
    assert outcome.findings == [] and outcome.errors[0][0] == "INT-020"
    assert "JEV" in outcome.errors[0][1]
    outcome = recover.recover(core, ["INT-020"], transcripts=transcripts,
                              cascade=_cascade(core, Jev("digest"), Dispatcher("sonnet", None)))
    assert outcome.findings == [] and "no answer" in outcome.errors[0][1]
    assert not recover.cache_path(core).exists()


def test_a_span_not_word_for_word_in_the_message_is_no_answer(project: Path,
                                                              transcripts: Path) -> None:
    core = open_core(project)
    sonnet = Dispatcher("sonnet", _picks("digest", "send a weekly digest"))   # reworded
    outcome = recover.recover(core, ["INT-020"], transcripts=transcripts,
                              cascade=_cascade(core, Jev("digest"), sonnet))
    assert outcome.findings == [] and "word for word" in outcome.errors[0][1]


def test_a_changed_record_loses_its_finding(project: Path, transcripts: Path,
                                            write_record) -> None:
    core = open_core(project)
    recover.recover(core, ["INT-009"], transcripts=transcripts, cascade=_cascade(
        core, Jev("cards should be short"),
        Dispatcher("sonnet", _picks("cards should be short", "the cards should be short"))))
    write_record(project, INT9.replace("one screen at most", "half a screen"))
    words, _ = _card(open_core(project), "INT-009")
    assert words["items"][0]["found"] is None


def test_cli_dry_run_asks_no_model_and_writes_nothing(
        project: Path, transcripts: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setenv(recover.TRANSCRIPTS_ENV, str(transcripts))
    assert main(["quotes", "recover", "--dry-run", "--json", "--root", str(project)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {p["id"] for p in data["would_examine"]} == {"INT-009", "INT-015", "INT-020"}
    assert all(p["candidates"] == 3 for p in data["would_examine"])
    assert data["findings"] == []
    assert not recover.cache_path(open_core(project)).exists()
