"""R17: the owner's answer to an early intent-conflict card, in the card's own words, is
recorded once (the decision) and both lanes build on it (SR-081 EX-6 to EX-9).

One test per entry point that shows the card (capture, the clarify read-back, the stop
hook's question card, /iaso conflicts) and per path that records the answer (the prompt
hook's relay, a host without a prompt hook, the owner's own terminal), plus the merge side:
a merge-time conflict between the two versions the owner already chose between is settled
by that answer, never asked again."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any

import pytest

from awareness.scenario import change, setup
from awareness.test_claim_check import agent_channel, early_asks
from iaso import cli
from iaso.api import open_core
from iaso.awareness import early, inflight
from iaso.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-259")


def _later(seconds: float = 5.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds))


def _start_turn(root: Path, session: str = "s1", ago: float = 0.5) -> None:
    """``ago``: how far back the turn began; a turn that holds a relay needs seconds of room,
    because the stop hook compares whole seconds and a slow machine stretches the relay."""
    path = root / ".iaso" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - ago,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}),
                    encoding="utf-8")


def _stop(root: Path, hook_input: Any, *, active: bool = False, session: str = "s1") -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=session, stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=root, verify=None,
                     unjudged=None) == 0
    text = out.getvalue()
    if not text.strip():
        return ""
    data = json.loads(text)
    return str(data.get("systemMessage") or data.get("reason") or "")


def _decision(root: Path) -> Any:
    [dec] = [r for r in open_core(root).index().values() if r.kind == "decision"]
    return dec


def _state(root: Path, record_id: str) -> str:
    return open_core(root).status([record_id])[record_id].confirmation


def _choose(root: Path, ref: str, take: str) -> int:
    """The owner's own terminal answers the card."""
    return cli.main(["conflict", "choose", ref, "--take", take, "--root", str(root)])


def _validate_errors(root: Path) -> list[str]:
    from iaso.validate import validate

    return [f.line() for f in validate(open_core(root)) if f.severity == "error"]


def _captured_with_card(tmp_path: Path, hook_input: Any) -> tuple[Path, Path]:
    """feat-x claims SR-005; main captures another version: the capture card, the decision,
    and the stop hook's turn (blocked once, then the summary with its cards)."""
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    _start_turn(main)
    result = change(main, "A relay pins only the records the owner's words affirm.")
    assert any('"relay checks" comes back at the end of this turn' in line for line in result.lines)
    _stop(main, hook_input)                 # trigger 2 blocks: the agent asks
    _stop(main, hook_input, active=True)    # the reply the owner reads
    return main, other


# -- the card's own words record the answer (findings: relay refused "keep feat-x's")


def test_capture_card_answer_keep_theirs(tmp_path: Path, hook_input: Any) -> None:
    """The owner says exactly "keep feat-x's" after the capture card: recorded, confirmed,
    and the other lane hears it as feat-x's version."""
    main, other = _captured_with_card(tmp_path, hook_input)
    dec = _decision(main)
    assert dec.fields["chosen"] == "main's version"          # the preset side
    assert _choose(main, dec.id, "feat-x") == 0
    dec = _decision(main)
    assert dec.fields["chosen"] == "feat-x's version"
    assert "main's version" in dec.fields["alternatives"]
    assert _state(main, dec.id) == "confirmed"
    assert _validate_errors(main) == []                      # the re-check accepts it
    # both lanes build on it: feat-x reads the owner's answer at once (no extra turn)
    line = early.check_text(open_core(other), "make SR-005 pin the stated group")
    assert line.lines == ['iaso: SR-005 "relay checks": the owner settled it on branch '
                          "main: \"feat-x's version\"; build on that"]


def test_capture_card_answer_keep_this_one(tmp_path: Path, hook_input: Any) -> None:
    main, _other = _captured_with_card(tmp_path, hook_input)
    dec = _decision(main)
    assert _choose(main, "SR-005", "main") == 0      # named by its record
    assert _decision(main).fields["chosen"] == "main's version"
    assert _state(main, dec.id) == "confirmed"


def test_stop_hook_question_card_answer_both(tmp_path: Path, hook_input: Any) -> None:
    """The stop hook's question card of the decision asks in the card's words, never a
    bare "ok" to a preset side; "both" is recorded as both."""
    main, _other = setup(tmp_path)
    change(_other, "A relay pins the stated group, named by its title.")
    _start_turn(main)
    change(main, "A relay pins only the records the owner's words affirm.")
    dec = _decision(main)
    # SR-265, SR-363: the owner's text counts no card; the card in full is the agent's to ask
    assert _stop(main, hook_input) == ""
    shown = agent_channel(main)
    # DEC-384: no card; the agent asks both versions by branch, "or both", never "ok"
    [asked] = early_asks(shown, "A relay pins the stated group")
    assert "or both?" in asked and 'say "ok" to confirm' not in shown
    assert _stop(main, hook_input, active=True) == ""
    assert _choose(main, dec.id, "both") == 0
    assert _decision(main).fields["chosen"] == "both, combined"
    assert _state(main, dec.id) == "confirmed"


def test_clarify_card_answer_before_capture(tmp_path: Path, hook_input: Any) -> None:
    """The read-back card (nothing written yet) reaches the owner through the stop hook of
    a turn that changed no file; the owner answers once capture raised the decision."""
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    _start_turn(main)
    out = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(out):
        assert cli.main(["clarify", "make SR-005 pin only the affirmed records",
                         "--root", str(main)]) == 0
    assert 'over "relay checks" comes back at the end of this turn' in out.getvalue()
    assert _stop(main, hook_input) == ""                       # SR-363: no question count
    cards = agent_channel(main)
    assert early_asks(cards, "A relay pins the stated group"), cards
    change(main, "A relay pins only the records the owner's words affirm.")
    dec = _decision(main)
    assert _choose(main, "SR-005", "feat-x") == 0
    assert _decision(main).fields["chosen"] == "feat-x's version"
    assert _state(main, dec.id) == "confirmed"


def test_iaso_conflicts_lists_the_early_card(tmp_path: Path, hook_input: Any) -> None:
    """/iaso conflicts shows the unanswered early conflict and asks the stop hook to show
    it; the owner's "keep feat-x's" then records it."""
    main, _other = setup(tmp_path)
    change(_other, "A relay pins the stated group, named by its title.")
    change(main, "A relay pins only the records the owner's words affirm.")
    dec = _decision(main)
    out = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(out):
        assert cli.main(["conflicts", "--root", str(main)]) == 0
    text = out.getvalue()
    assert '▸ Conflict on "relay checks"' in text
    assert "feat-x      A relay pins the stated group, named by its title." in text
    _start_turn(main)
    assert _stop(main, hook_input) == ""                       # SR-363: no question count
    assert early_asks(agent_channel(main), "A relay pins the stated group")
    assert _choose(main, "relay checks", "feat-x") == 0
    assert _state(main, dec.id) == "confirmed"


def test_owner_terminal_answer(tmp_path: Path, hook_input: Any) -> None:
    main, _other = _captured_with_card(tmp_path, hook_input)
    dec = _decision(main)
    assert cli.main(["conflict", "choose", dec.id, "--take", "feat-x",
                     "--root", str(main)]) == 0
    assert _decision(main).fields["chosen"] == "feat-x's version"
    assert _state(main, dec.id) == "confirmed"


# -- the heuristic never says "compatible" on its own (finding: a plain contradiction passed)


class _Verdict:
    def __init__(self, name: str, verdict: str, confidence: float) -> None:
        self.name, self.verdict, self.confidence = name, verdict, confidence

    def contradiction(self, prompt: str, record: Any) -> Any:
        from iaso.contracts import Judgment

        return Judgment(action="contradiction", subject=record.id, verdict=self.verdict,
                        confidence=self.confidence, tier="accept", backend=self.name,
                        fingerprint="f")


def _divisions(tmp_path: Path) -> tuple[Path, Path]:
    from awareness.scenario import new_requirement

    main, other = setup(tmp_path)
    new_requirement(other, "division by zero", "div(a, 0) returns 0.")
    return main, other


@pytest.mark.parametrize("judge", [_Verdict("heuristic", "benign", 0.6),
                                   _Verdict("jev", "benign", 0.55)])
def test_capture_overlap_without_a_confident_verdict_names_both(tmp_path: Path,
                                                                judge: Any) -> None:
    from awareness.scenario import new_requirement

    main, _other = _divisions(tmp_path)
    result = new_requirement(main, "division by zero raises",
                             "div(a, 0) raises ZeroDivisionError.", backend=judge)
    text = "\n".join(result.lines)
    assert "judged compatible" not in text and "nothing to ask" not in text
    assert "could not be judged" in text
    assert 'feat-x says "div(a, 0) returns 0."' in text
    assert 'this says "div(a, 0) raises ZeroDivisionError."' in text


def test_clarify_overlap_without_a_confident_verdict_names_both(tmp_path: Path) -> None:
    main, _other = _divisions(tmp_path)
    check = early.check_text(open_core(main),
                             "SR-006 status card: div(a, 0) raises ZeroDivisionError",
                             backend=_Verdict("heuristic", "benign", 0.6))
    assert check.conflicts == []
    [line] = [x for x in check.lines if "feat-x" in x]
    assert "judged compatible" not in line and "could not be judged" in line
    assert 'feat-x says "div(a, 0) returns 0."' in line


def test_confident_jev_still_says_compatible(tmp_path: Path) -> None:
    from awareness.scenario import new_requirement

    main, _other = _divisions(tmp_path)
    result = new_requirement(main, "status colours", "The card is green when aligned.",
                             backend=_Verdict("jev", "benign", 0.9))
    assert any("judged compatible, nothing to ask" in line for line in result.lines)


# -- the register: the answer is carried by the relay itself


def test_relay_carries_the_answer_into_the_register(tmp_path: Path,
                                                    hook_input: Any) -> None:
    main, _other = _captured_with_card(tmp_path, hook_input)
    dec = _decision(main)
    assert _choose(main, dec.id, "feat-x") == 0
    [mine] = [c for c in inflight.read(main, allow_git=True)[1]["claims"]
              if c["branch"] == "main"]
    assert mine["conflicts"][0]["state"] == "confirmed"
    assert mine["conflicts"][0]["chosen"] == "feat-x's version"
