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
    """EX-1: a captured proposed intent gets its card, drawn in full (SR-012 EX-3); EX-2: code
    under confirmed records with fresh tests gets none, and the stop shows nothing (SR-012
    EX-5: no status card, no summary)."""
    touch(calc, ".plumb/intents/INT-001.md")
    message = run_stop(calc, hook_input)["systemMessage"]
    lines = message.splitlines()
    assert lines[0].startswith('Proposed this turn, "add multiply next to add": ')
    assert "  As it now reads (add multiply next to add): Add multiply(a, b) beside add." in lines
    assert "    won't: floats" in lines
    assert "    assumed: integers only" in lines
    assert not [line for line in lines if line.startswith("plumb: ")]

    approvals.approve(open_core(calc), ["SR-001", "SR-002", "INT-001"])
    touch(calc, "src/app/calc.py", session="s2")
    verify = FakeVerify(nodes=("tests/test_calc.py::test_add",), evidence_map={
        "tests/test_calc.py::test_add": NodeEvidence("tests/test_calc.py::test_add",
                                                     "fresh-pass")})
    assert "systemMessage" not in run_stop(calc, hook_input, session="s2", verify=verify)


# retired: test_full_mode_cards_every_touched_record. SR-012 (INT-008 "won't": no list-style
# summary at the end of a turn) removed the card of every touched record and the sp1 summary
# lines ("plumb: questions: none") that present.card: full added; the stop hook no longer
# reads present.card.


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
    assert message.startswith('Something that worked now fails, "add returns the sum of two '
                              'numbers"')
    assert ("  Evidence: tests/test_calc.py::test_add passed in an earlier run and fails now "
            "(last run r2)") in message.splitlines()
    # SR-012 EX-3 made a proposed intent a card in every mode ("INT-001 not in message", the
    # off-mode rule, is retired with present.card in the stop hook)
    assert not message.startswith("plumb ")


def test_card_marks_record_shown_in_stated_set(calc: Path, hook_input) -> None:
    touch(calc, ".plumb/requirements/SR-002.md")
    lines = run_stop(calc, hook_input)["systemMessage"].splitlines()
    assert ("  As it now reads (divide returns the quotient): app.calc.divide(a, b) returns "
            "a / b.") in lines
    assert "    EX-2: given 1 and 0, when divide runs, then it returns 0" in lines
    stated = json.loads((calc / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    assert {"id": "SR-002", "hash": open_core(calc).index()["SR-002"].hash,
            "shown": True} in stated["records"]


def test_many_proposed_records_are_one_card_each_drawn(calc: Path, hook_input,
                                                     write_record) -> None:
    """SR-012 EX-4 (DEC-029) replaced the cap of three cards and the "+N more not shown"
    line: five proposed records are one card that draws every one, and each is shown."""
    for n in range(5, 10):
        write_record(calc, f"---\nid: SR-00{n}\ntitle: rule {n}\nstatement: s {n}\n---\n")
        touch(calc, f".plumb/requirements/SR-00{n}.md")
    message = run_stop(calc, hook_input)["systemMessage"]
    heads = [line for line in message.splitlines() if line and not line.startswith(" ")]
    assert len(heads) == 1 and "these 5 were written from your words" in heads[0]
    for n in range(5, 10):
        assert f"  - rule {n}" in message.splitlines()
    assert "not shown" not in message
    stated = json.loads((calc / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    shown = {r["id"]: r["shown"] for r in stated["records"]}
    assert all(shown[f"SR-00{n}"] for n in range(5, 10))


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
    lines = message.splitlines()
    assert lines[0] == ('A choice this work relies on, "Rounding": I assumed half-up; '
                        "banker's rounding also fits. Which one?")
    assert "  1. Keep it: half-up (recommended)" in lines
    assert "  2. Switch to: banker's rounding" in lines


def test_intent_change_flag_gets_a_card(calc: Path, hook_input) -> None:
    from present_helpers import run_prompt

    approvals.approve(open_core(calc), ["SR-001"])
    run_prompt(calc, hook_input, "SR-001 add should use floats instead")
    touch(calc, "src/app/calc.py")
    # the flag alone is the agent's instruction: no owner card until the agent concludes
    assert "systemMessage" not in run_stop(calc, hook_input)
    # the agent concluded there is a change: it updated the flagged record
    run_prompt(calc, hook_input, "SR-001 add should use floats instead")
    record = calc / ".plumb" / "requirements" / "SR-001.md"
    record.write_text(record.read_text("utf-8").replace("for integers", "for floats"),
                      "utf-8")
    touch(calc, ".plumb/requirements/SR-001.md")
    lines = run_stop(calc, hook_input)["systemMessage"].splitlines()
    # SR-012: the changed record reaches the owner as a card that draws it as it now reads
    assert lines[0].startswith('Proposed this turn, "')
    assert ("  As it now reads (add returns the sum of two numbers): app.calc.add(a, b) "
            "returns a + b for floats.") in lines


# retired: test_triage_offer_line_and_group. SR-012 and DEC-029 replaced CAPTURE's triage offer
# line ("plumb: approve the 1 record rated faithful...? say \"ok\"") with one card per feature;
# no offer line is drawn at the end of a turn.


@pytest.mark.parametrize("mode", ["compact", "full", "off"])
def test_triage_group_pinned_only_when_its_offer_is_shown(calc: Path, hook_input, monkeypatch,
                                                          mode: str) -> None:
    """R2, R13 Q2 (SR-062 EX-4): the stop pins the triage group in the stated set only when
    the owner saw its offer line. Since SR-012 (DEC-029) no offer line is drawn in any mode,
    so no group is ever relayable with ``plumb relay --group``; the record's own card is."""
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
    assert offer not in message.splitlines()
    assert (stated.get("groups") or []) == []
    assert message.startswith("Proposed this turn, \"this turn's work\"")


def test_examples_carry_their_own_record_state() -> None:
    """R2, R9: an intent card confirmed by the owner labels a member requirement's
    examples with that requirement's own state, never the intent's."""
    from dataclasses import replace

    card = replace(CARD, state="confirmed", confirmed_by="you",
                   examples=(*CARD.examples, ("SR-017", "EX-1", "given -3, then 3")),
                   member_states=(("INT-016", "confirmed"), ("SR-016", "confirmed"),
                                  ("SR-017", "proposed")))
    [line] = [x for x in intent_card(card) if x.lstrip().startswith("Examples")]
    assert line.endswith("it returns 0   (confirmed)  SR-017/EX-1 given -3, then 3   "
                         "(proposed)")
    unknown = replace(card, member_states=())       # never "confirmed" without knowing
    [line] = [x for x in intent_card(unknown) if x.lstrip().startswith("Examples")]
    assert "(confirmed)" not in line and line.endswith("(proposed)")
