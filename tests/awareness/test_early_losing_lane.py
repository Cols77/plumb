"""R17: "the answer is recorded once (a DEC) and both lanes build on it". The lane whose
version the owner turned down is told so on every turn until its record matches the answer,
and no "ok" confirms the rejected words meanwhile (SR-081).

One test per entry point: the relay, the prompt hook, the stop hook and status; for the lane
that holds the decision (it raised the question) and for the lane that hears the answer
through the register."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from mergedriver.mdhelpers import log_prompt

from awareness.test_early_answer import _captured_with_card as captured_with_card
from awareness.test_early_answer import _later as later
from awareness.test_early_answer import _relay as relay
from awareness.test_early_answer import _start_turn as start_turn
from awareness.test_early_answer import _stop as stop_hook
from awareness.gitrepo import write_record
from awareness.scenario import setup
from plumb import cli
from plumb.api import open_core
from plumb.hosts.claude_code import prompt

pytestmark = pytest.mark.sr("SR-081")

MAIN = "A relay pins only the records the owner's words affirm."
FEAT_X = "A relay pins the stated group, named by its title."
LINE = 'plumb: SR-005 "relay checks" here still says'


def _decision(root: Path) -> Any:
    [dec] = [r for r in open_core(root).index().values() if r.kind == "decision"]
    return dec


def _main_lost(tmp_path: Path, hook_input: Any) -> tuple[Path, Path]:
    """main raised the question; the owner kept feat-x's: main is the losing lane."""
    main, other = captured_with_card(tmp_path, hook_input)
    assert relay(main, _decision(main).id, "keep feat-x's") == 0
    return main, other


def _feat_x_lost(tmp_path: Path, hook_input: Any) -> tuple[Path, Path]:
    """main raised the question; the owner kept main's: feat-x hears it via the register."""
    main, other = captured_with_card(tmp_path, hook_input)
    assert relay(main, _decision(main).id, "keep this one") == 0
    return main, other


def _prompt(root: Path, hook_input: Any, words: str) -> str:
    out = io.StringIO()
    prompt.main(stdin=io.StringIO(hook_input("UserPromptSubmit", prompt=words)), stdout=out,
                root=root, backend=None)
    text = out.getvalue()
    if not text.strip():
        return ""
    try:
        data = json.loads(text)
    except ValueError:
        return text
    return json.dumps(data)


def _status(root: Path) -> list[str]:
    from plumb.awareness.lines import status_section

    return status_section(open_core(root))


# -- status


def test_status_names_the_losing_lane_until_it_matches(tmp_path: Path,
                                                       hook_input: Any) -> None:
    main, _other = _main_lost(tmp_path, hook_input)
    [line] = [x for x in _status(main) if x.startswith(LINE)]
    assert "the owner chose feat-x's version" in line and FEAT_X in line
    write_record(main, "SR-005", "relay checks", feature="FEAT-002", statement=FEAT_X)
    assert not any(x.startswith(LINE) for x in _status(main))


def test_status_of_the_lane_hearing_the_answer_from_the_register(tmp_path: Path,
                                                                 hook_input: Any) -> None:
    main, other = _feat_x_lost(tmp_path, hook_input)
    [line] = [x for x in _status(other) if x.startswith(LINE)]
    assert "the owner chose main's version" in line and MAIN in line
    assert not any(x.startswith(LINE) for x in _status(main))        # the winner: nothing


# -- the prompt hook


def test_prompt_hook_names_it_on_every_turn(tmp_path: Path, hook_input: Any) -> None:
    main, other = _feat_x_lost(tmp_path, hook_input)
    assert LINE in _prompt(other, hook_input, "go ahead and implement")
    assert LINE in _prompt(other, hook_input, "continue")              # persistent
    write_record(other, "SR-005", "relay checks", feature="FEAT-002", statement=MAIN)
    assert LINE not in _prompt(other, hook_input, "continue")
    assert LINE not in _prompt(main, hook_input, "go ahead and implement")


# -- the stop hook


def test_stop_hook_names_it(tmp_path: Path, hook_input: Any) -> None:
    main, _other = _main_lost(tmp_path, hook_input)
    start_turn(main)
    shown = stop_hook(main, hook_input, active=True)
    assert LINE in shown and "the owner chose feat-x's version" in shown


# -- the relay


def test_relay_refuses_an_ok_of_the_rejected_words(tmp_path: Path, hook_input: Any) -> None:
    main, _other = _main_lost(tmp_path, hook_input)
    dec = _decision(main)
    words = "ok SR-005 looks right"
    digest = log_prompt(main, words, at=later())
    err = io.StringIO()
    import contextlib

    with contextlib.redirect_stderr(err):
        assert cli.main(["relay", "SR-005", "--prompt", digest, "--quote", words,
                         "--root", str(main)]) == 3
    assert dec.id in err.getvalue() and "turned down" in err.getvalue()
    assert open_core(main).status(["SR-005"])["SR-005"].confirmation != "confirmed"


def test_relay_in_the_lane_hearing_the_answer_is_refused_too(tmp_path: Path,
                                                             hook_input: Any) -> None:
    _main, other = _feat_x_lost(tmp_path, hook_input)
    words = "ok SR-005 looks right"
    digest = log_prompt(other, words, at=later())
    assert cli.main(["relay", "SR-005", "--prompt", digest, "--quote", words,
                     "--root", str(other)]) == 3


def test_no_answer_no_signal(tmp_path: Path) -> None:
    """Before the owner answers, nothing is superseded (the card asks instead)."""
    from awareness.scenario import change
    from plumb.awareness.answer import superseded

    main, other = setup(tmp_path)
    change(other, FEAT_X)
    change(main, MAIN)
    assert superseded(open_core(main)) == {} and superseded(open_core(other)) == {}
