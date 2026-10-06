"""P3: the intent card, only when it matters; full | compact | off (sp5 4.2, 4.3, SR-062)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from present_helpers import (
    INT1,
    SR1,
    SR2,
    FakeVerify,
    fake_capture,
    run_stop,
    touch,
    write_all,
)

from plumb import approvals
from plumb.api import open_core
from plumb.contracts import IntentCardData, NodeEvidence, Target
from plumb.present.render import intent_card

pytestmark = pytest.mark.sr("SR-062")

CARD = IntentCardData(
    id="INT-016", title="add multiply", state="proposed",
    will=("multiply(a, b) returns a * b",), wont=("floats",), assumed=("integers only",),
    examples=(("SR-016", "EX-1", "given 2 and 3, when multiply runs, then it returns 6"),
              ("SR-016", "EX-2", "given 0, when multiply runs, then it returns 0")),
    tests=(("tests/test_calc.py::test_multiply", "passing"),), kind="intent")


def test_format_four_lines() -> None:
    lines = intent_card(CARD)
    assert lines == [
        '▸ Intent  INT-016 "add multiply"   (proposed — say "ok" to confirm)',
        "  Will: multiply(a, b) returns a * b · Won't: floats · Assumed: integers only",
        "  Examples  SR-016/EX-1 given 2 and 3, when multiply runs, then it returns 6  "
        "SR-016/EX-2 given 0, when multiply runs, then it returns 0   (proposed)",
        "  Tests  tests/test_calc.py::test_multiply  ✓ passing",
    ]


def test_state_actions_and_trigger_heading() -> None:
    jev = IntentCardData(id="SR-004", title="t", state="confirmed", confirmed_by="JEV")
    assert 'confirmed by JEV — say "revoke" to undo' in intent_card(jev)[0]
    edited = IntentCardData(id="SR-004", title="t", state="unconfirmed-edit")
    assert "changed since you confirmed it" in intent_card(edited)[0]
    relayed = IntentCardData(id="SR-004", title="t", state="confirmed",
                             confirmed_by="you (relayed)", label="self-recorded message")
    assert "confirmed by you (relayed), self-recorded message" in intent_card(relayed)[0]
    assert intent_card(edited, why="Regression")[0].startswith("▸ Regression  SR-004")
    assert intent_card(CARD, ascii=True)[0].startswith("> Intent  INT-016")
    assert all(line.isascii() for line in intent_card(CARD, ascii=True))


def test_off_renders_only_triggers() -> None:
    assert intent_card(CARD, mode="off") == []
    assert intent_card(CARD, mode="off", why="Question")


@pytest.fixture
def calc(repo: Path, write_record) -> Path:
    write_all(repo, write_record, SR1, SR2, INT1)
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "src" / "app" / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                                  "utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text("def test_add():\n    pass\n", "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/app/calc.py"))
    core.add_link("SR-001", "verified_by", Target(path="tests/test_calc.py"), "EX-1")
    return repo


def _config(repo: Path, card: str) -> None:
    (repo / ".plumb" / "config.yaml").write_text(f"present:\n  card: {card}\n", "utf-8")


def test_shown_only_when_it_matters(calc: Path, hook_input) -> None:
    """EX-1: a captured proposed intent gets its card; EX-2: code under confirmed records
    with fresh tests gets none."""
    touch(calc, ".plumb/intents/INT-001.md")
    message = run_stop(calc, hook_input)["systemMessage"]
    lines = message.splitlines()
    assert lines[0].startswith("plumb ● awaits you")
    assert ('▸ Intent  INT-001 "add multiply next to add"   (proposed — say "ok" to '
            'confirm)') in lines
    assert len([line for line in lines if line.startswith("plumb: ")]) <= 2

    approvals.approve(open_core(calc), ["SR-001", "SR-002", "INT-001"])
    touch(calc, "src/app/calc.py", session="s2")
    verify = FakeVerify(nodes=("tests/test_calc.py::test_add",), evidence_map={
        "tests/test_calc.py::test_add": NodeEvidence("tests/test_calc.py::test_add",
                                                     "fresh-pass")})
    message = run_stop(calc, hook_input, session="s2", verify=verify)["systemMessage"]
    assert "▸" not in message
    assert message.splitlines()[0].startswith("plumb ✓ aligned")


def test_full_mode_cards_every_touched_record(calc: Path, hook_input) -> None:
    approvals.approve(open_core(calc), ["SR-001"])
    _config(calc, "full")
    touch(calc, "src/app/calc.py")
    message = run_stop(calc, hook_input)["systemMessage"]
    assert '▸ Requirement  SR-001 "add returns the sum of two numbers"   (confirmed by you)' \
        in message
    assert "plumb: questions: none" in message  # the sp1 summary lines under the card


def test_off_still_shows_trigger(calc: Path, hook_input) -> None:
    """EX-3: card off and a regression: the regression card is shown."""
    approvals.approve(open_core(calc), ["SR-001"])
    _config(calc, "off")
    node = "tests/test_calc.py::test_add"
    verify = FakeVerify(nodes=(node,), evidence_map={
        node: NodeEvidence(node, "fresh-fail", regression=True, last_run="r2")})
    touch(calc, "src/app/calc.py")
    touch(calc, ".plumb/intents/INT-001.md")
    import io

    from plumb.hosts.claude_code import stop
    out = io.StringIO()
    stop.main(stdin=io.StringIO(hook_input("Stop", session_id="s1", stop_hook_active=True)),
              stdout=out, root=calc, verify=verify, unjudged=lambda c, i: ())
    message = json.loads(out.getvalue())["systemMessage"]
    assert '▸ Regression  SR-001 "add returns the sum of two numbers"' in message
    assert "INT-001" not in message  # a proposed intent is no trigger in off mode
    assert not message.startswith("plumb ")


def test_card_marks_record_shown_in_stated_set(calc: Path, hook_input) -> None:
    touch(calc, ".plumb/requirements/SR-002.md")
    message = run_stop(calc, hook_input)["systemMessage"]
    assert "  app.calc.divide(a, b) returns a / b." in message
    assert "EX-2 given 1 and 0, when divide runs, then it returns 0" in message
    stated = json.loads((calc / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    assert {"id": "SR-002", "hash": open_core(calc).index()["SR-002"].hash,
            "shown": True} in stated["records"]


def test_cards_past_the_cap_are_named_not_shown(calc: Path, hook_input,
                                                write_record) -> None:
    for n in range(5, 10):
        write_record(calc, f"---\nid: SR-00{n}\ntitle: rule {n}\nstatement: s {n}\n---\n")
        touch(calc, f".plumb/requirements/SR-00{n}.md")
    message = run_stop(calc, hook_input)["systemMessage"]
    assert message.count("▸ Requirement") == 3
    assert "plumb: +2 more not shown: SR-008, SR-009 (plumb show SR-008 SR-009)" in message
    stated = json.loads((calc / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    shown = {r["id"]: r["shown"] for r in stated["records"]}
    assert shown["SR-005"] and not shown["SR-009"]


def test_decision_that_matters_gets_a_question_card(calc: Path, hook_input,
                                                    write_record) -> None:
    write_record(calc, "---\nid: DEC-001\ntitle: Rounding\nchosen: half-up\nalternatives: "
                 "[banker's rounding]\nmatters: true\nlinks:\n  - {kind: decides, to: SR-002}"
                 "\n---\n")
    touch(calc, ".plumb/decisions/DEC-001.md")
    import io

    from plumb.hosts.claude_code import stop
    out = io.StringIO()
    stop.main(stdin=io.StringIO(hook_input("Stop", session_id="s1", stop_hook_active=True)),
              stdout=out, root=calc, verify=FakeVerify(), unjudged=lambda c, i: ())
    message = json.loads(out.getvalue())["systemMessage"]
    assert '▸ Question  DEC-001 "Rounding"' in message
    assert "Assumed: half-up · Also fits: banker's rounding" in message


def test_intent_change_flag_gets_a_card(calc: Path, hook_input) -> None:
    from present_helpers import run_prompt

    approvals.approve(open_core(calc), ["SR-001"])
    run_prompt(calc, hook_input, "SR-001 add should use floats instead")
    touch(calc, "src/app/calc.py")
    message = run_stop(calc, hook_input)["systemMessage"]
    assert '▸ Intent change  SR-001 "add returns the sum of two numbers"' in message


def test_triage_offer_line_and_group(calc: Path, hook_input, monkeypatch) -> None:
    """R8 A: the offer of CAPTURE's triage appears and its group is pinned in the stated
    set; without CAPTURE nothing is offered."""
    from types import SimpleNamespace

    index = open_core(calc).index()
    item = SimpleNamespace(id="SR-002", hash=index["SR-002"].hash, title="divide",
                           rating="faithful", score=0.9)
    view = SimpleNamespace(backend="heuristic", available=True, low_risk=(item,),
                           individual=(),
                           offer='plumb: approve the 1 record rated faithful to your words: '
                                 '"divide" (SR-002)? say "ok" or see plumb triage')
    fake_capture(monkeypatch, triage=lambda core, ids: view,
                 stated_group=lambda v: {"group": "low-risk", "records": [
                     {"id": "SR-002", "hash": index["SR-002"].hash}]})
    touch(calc, ".plumb/requirements/SR-002.md")
    message = run_stop(calc, hook_input)["systemMessage"]
    assert "plumb: approve the 1 record rated faithful to your words" in message
    stated = json.loads((calc / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    assert stated["groups"][0]["group"] == "low-risk"


@pytest.mark.parametrize("mode", ["compact", "full", "off"])
def test_triage_group_pinned_only_when_its_offer_is_shown(calc: Path, hook_input, monkeypatch,
                                                          mode: str) -> None:
    """R2, R13 Q2 (SR-062 EX-5): the stop pins the triage group in the stated set only when
    the owner saw its offer line; ``present.card: off`` hides the offer, so nothing is
    relayable with ``plumb relay --group``."""
    from types import SimpleNamespace

    _config(calc, mode)
    index = open_core(calc).index()
    item = SimpleNamespace(id="SR-002", hash=index["SR-002"].hash, title="divide",
                           rating="faithful", score=0.9)
    offer = ('plumb: approve the 1 record rated faithful to your words: "divide" (SR-002)? '
             'say "ok" or see plumb triage')
    view = SimpleNamespace(backend="heuristic", available=True, low_risk=(item,),
                           individual=(), offer=offer)
    fake_capture(monkeypatch, triage=lambda core, ids: view,
                 stated_group=lambda v: {"group": "low-risk", "records": [
                     {"id": "SR-002", "hash": index["SR-002"].hash}]})
    touch(calc, ".plumb/requirements/SR-002.md")
    message = run_stop(calc, hook_input).get("systemMessage", "")
    stated = json.loads((calc / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    groups = stated.get("groups") or []
    if mode == "off":
        assert offer not in message.splitlines()
        assert groups == []
    else:
        assert offer in message.splitlines()
        assert [g["group"] for g in groups] == ["low-risk"]
