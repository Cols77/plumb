"""R17: "Conflicts are detected when intent is CAPTURED, not at merge" and "the same record
being changed is caught deterministically", also when the other side's change already
LANDED on the default branch: its claim cleared there, but a branch that started before
still holds the words it replaced (SR-081).

The scenario of every test: feat-x starts from main; main captures new words for SR-005 and
commits them (main's claim clears); then feat-x changes SR-005 differently. One test per
entry point: capture, the clarify read-back, the stop hook's claim, status and the session
brief, and the prompt delta."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

from awareness.gitrepo import commit_all, requirement, run_git
from awareness.scenario import change, setup
from awareness.test_claim_check import _start_turn as start_turn
from awareness.test_claim_check import _turn as turn
from plumb import cli
from plumb.api import open_core
from plumb.awareness import inflight
from plumb.hosts.claude_code import prompt
from plumb.understand.summary import ASK_OWNER

pytestmark = pytest.mark.sr("SR-259")

MAIN = "A relay pins only the records the owner's words affirm."
FEAT_X = "A relay pins the stated group, named by its title."
SINCE = 'plumb: SR-005 "relay checks" was changed on main after this branch started'


def _main_landed(tmp_path: Path) -> tuple[Path, Path]:
    """main changed SR-005 and committed it (its claim cleared); feat-x started before."""
    main, other = setup(tmp_path)
    change(main, MAIN)
    commit_all(main, "main relay change")
    _oid, register = inflight.read(main, allow_git=True)
    assert not any("SR-005" in (c.get("records") or {}) for c in inflight.active(
        main, register, default="main", allow_git=True))    # the claim cleared on landing
    return main, other


def _decisions(root: Path) -> list[Any]:
    return [r for r in open_core(root).index().values() if r.kind == "decision"]


def _card(lines: str) -> None:
    assert '"relay checks" waits as a card' in lines, lines


def _note(lines: str) -> None:
    assert 'over "relay checks" waits as a card' in lines, lines


def _stop_card(lines: list[str], cards: str) -> None:
    """The stop hook's early conflict card (SR-012: a card in full, titles not IDs): main's
    version and this work's, in the owner's words, on the agent's channel; the owner's one
    line counts it (SR-265)."""
    from awareness.test_claim_check import early_heads

    assert lines == ["plumb: 1 question for you"], lines
    heads = early_heads(cards, "relay checks")
    assert heads and any(MAIN in h for h in heads), cards


# -- capture


def test_capture_raises_the_card_and_one_decision(tmp_path: Path) -> None:
    _main, other = _main_landed(tmp_path)
    result = change(other, FEAT_X)
    text = "\n".join(result.lines)
    _card(text)
    [dec] = _decisions(other)
    assert dec.fields["matters"] is True
    assert dec.fields["early"]["hashes"]["main"] != dec.fields["early"]["hashes"]["feat-x"]
    mine = [c for c in inflight.read(other, allow_git=True)[1]["claims"]
            if c["branch"] == "feat-x"]
    assert mine[0]["conflicts"][0]["branch"] == "main"
    again = change(other, FEAT_X + " Reworded.")                   # asked once
    assert not any("waits as a card" in line for line in again.lines)
    assert len(_decisions(other)) == 1


def test_the_owner_keeps_mains_and_the_lane_is_told(tmp_path: Path, hook_input: Any) -> None:
    from awareness.test_claim_check import _answer as answer
    from plumb.awareness.lines import status_section

    _main, other = _main_landed(tmp_path)
    start_turn(other)
    change(other, FEAT_X)
    _stop_card(*turn(other, hook_input))
    [dec] = _decisions(other)
    assert answer(other, dec.id, "keep main's") == 0
    dec = open_core(other).index()[dec.id]
    assert dec.fields["chosen"] == "main's version"
    status = status_section(open_core(other))
    assert any('SR-005 "relay checks" here still says' in line and MAIN in line
               for line in status), status


def test_capture_after_taking_main_or_of_another_record_raises_nothing(tmp_path: Path
                                                                         ) -> None:
    _main, other = _main_landed(tmp_path)
    result = change(other, "The status card shows the state in two lines.", record="SR-006")
    assert not any("waits as a card" in line for line in result.lines)
    run_git(other, "merge", "-q", "--no-edit", "main")            # feat-x takes main
    result = change(other, FEAT_X)
    assert not any("waits as a card" in line for line in result.lines)
    assert _decisions(other) == []


# -- the clarify read-back


def test_clarify_read_back_shows_the_card_before_anything_is_written(tmp_path: Path
                                                                       ) -> None:
    _main, other = _main_landed(tmp_path)
    before = sorted(p.name for p in (other / ".plumb").rglob("*.md"))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli.main(["clarify", "change SR-005 relay checks so the stated group is "
                         "pinned by its title", "--root", str(other)]) == 0
    _note(out.getvalue())
    assert sorted(p.name for p in (other / ".plumb").rglob("*.md")) == before


# -- the stop hook's claim


def test_direct_edit_then_stop_hook_asks(tmp_path: Path, hook_input: Any) -> None:
    _main, other = _main_landed(tmp_path)
    start_turn(other)
    requirement(other, "SR-005", "relay checks", FEAT_X, feature="FEAT-002")
    lines, cards = turn(other, hook_input)
    _stop_card(lines, cards)              # never a block: the card asks, tagged (SR-295)
    assert ASK_OWNER in cards, cards
    assert len(_decisions(other)) == 1


# -- status and the session brief


def test_status_and_brief_name_the_change_on_main(tmp_path: Path) -> None:
    from plumb.awareness.lines import brief_lines, status_section
    from plumb.awareness.turn import at_session_start, at_stop

    main, other = _main_landed(tmp_path)
    change(other, FEAT_X)
    at_stop(open_core(other), [".plumb/requirements/SR-005.md"], ["SR-005"])
    status = status_section(open_core(other))
    assert any(line.strip().startswith(SINCE) for line in status), status
    assert not any(line.startswith("also being changed elsewhere: nothing")
                   for line in status)
    at_session_start(open_core(other))
    assert any(line.startswith(SINCE) for line in brief_lines(open_core(other)))
    assert not any(line.strip().startswith(SINCE) for line in status_section(open_core(main)))


# -- the prompt delta


def _prompt(root: Path, hook_input: Any, words: str) -> str:
    out = io.StringIO()
    prompt.main(stdin=io.StringIO(hook_input("UserPromptSubmit", prompt=words)), stdout=out,
                root=root, backend=None)
    text = out.getvalue()
    try:
        return json.dumps(json.loads(text)) if text.strip() else ""
    except ValueError:
        return text


def test_prompt_delta_names_the_change_on_main(tmp_path: Path, hook_input: Any) -> None:
    from plumb.awareness.turn import at_session_start

    _main, other = _main_landed(tmp_path)
    at_session_start(open_core(other))         # the session start learns it (git, cached)
    assert SINCE in _prompt(other, hook_input, "make SR-005 relay checks pin the stated "
                                               "group by its title")
