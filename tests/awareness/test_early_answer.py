"""R17: the owner's answer to an early intent-conflict card, in the card's own words, is
recorded once (the decision) and both lanes build on it (SR-081 EX-6 to EX-9).

One test per entry point that shows the card (capture, the clarify read-back, the stop
hook's question card, /plumb conflicts) and per path that records the answer (the prompt
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
from mergedriver.mdhelpers import log_prompt

from awareness.scenario import change, setup
from plumb import cli
from plumb.api import open_core
from plumb.awareness import early, inflight
from plumb.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-081")


def _later(seconds: float = 5.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds))


def _start_turn(root: Path, session: str = "s1") -> None:
    path = root / ".plumb" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
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


def _stated(root: Path) -> dict:
    return json.loads((root / ".plumb" / "session" / "stated.json").read_text("utf-8"))


def _decision(root: Path) -> Any:
    [dec] = [r for r in open_core(root).index().values() if r.kind == "decision"]
    return dec


def _state(root: Path, record_id: str) -> str:
    return open_core(root).status([record_id])[record_id].confirmation


def _relay(root: Path, ref: str, words: str, *, quote: str | None = None,
           take: str | None = None, via: str | None = "hook") -> int:
    digest = log_prompt(root, words, at=_later(), via=via)
    argv = ["conflict", "relay", ref, "--prompt", digest, "--quote", quote or words,
            "--root", str(root)]
    if take:
        argv[3:3] = ["--take", take]
    return cli.main(argv)


def _validate_errors(root: Path) -> list[str]:
    from plumb.validate import validate

    return [f.line() for f in validate(open_core(root)) if f.severity == "error"]


def _captured_with_card(tmp_path: Path, hook_input: Any) -> tuple[Path, Path]:
    """feat-x claims SR-005; main captures another version: the capture card, the decision,
    and the stop hook's turn (blocked once, then the summary with its cards)."""
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    _start_turn(main)
    result = change(main, "A relay pins only the records the owner's words affirm.")
    assert any(line.startswith('▸ Conflict  SR-005 "relay checks"') for line in result.lines)
    _stop(main, hook_input)                 # trigger 2 blocks: the agent asks
    _stop(main, hook_input, active=True)    # the reply the owner reads
    return main, other


# -- the card's own words record the answer (findings: relay refused "keep feat-x's")


def test_capture_card_answer_keep_theirs(tmp_path: Path, hook_input: Any) -> None:
    """The owner says exactly "keep feat-x's" after the capture card: recorded, confirmed,
    and the other lane hears it as feat-x's version."""
    main, other = _captured_with_card(tmp_path, hook_input)
    assert {"record": "SR-005", "branch": "feat-x"} in _stated(main)["early"]
    dec = _decision(main)
    assert dec.fields["chosen"] == "main's version"          # the preset side
    assert _relay(main, dec.id, "keep feat-x's") == 0
    dec = _decision(main)
    assert dec.fields["chosen"] == "feat-x's version"
    assert "main's version" in dec.fields["alternatives"]
    assert _state(main, dec.id) == "confirmed"
    assert _validate_errors(main) == []                      # the re-check accepts it
    # both lanes build on it: feat-x reads the owner's answer at once (no extra turn)
    line = early.check_text(open_core(other), "make SR-005 pin the stated group")
    assert line.lines == ['plumb: SR-005 "relay checks": the owner settled it on branch '
                          "main: \"feat-x's version\"; build on that"]


def test_capture_card_answer_keep_this_one(tmp_path: Path, hook_input: Any) -> None:
    main, _other = _captured_with_card(tmp_path, hook_input)
    dec = _decision(main)
    assert _relay(main, "SR-005", "keep this one") == 0      # named by its record
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
    asked = _stop(main, hook_input)
    assert "Show the owner the conflict card" in asked and "keep this one" in asked
    shown = _stop(main, hook_input, active=True)
    say = "awaits your choice — say \"keep feat-x's\", \"keep this one\", or \"both\""
    assert say in shown
    assert 'proposed — say "ok" to confirm' not in [
        line for line in shown.splitlines() if dec.id in line][0]
    assert any(r["id"] == dec.id and r["shown"] for r in _stated(main)["records"])
    assert _relay(main, dec.id, "both, the group pinned when it is named") == 0
    assert _decision(main).fields["chosen"] == "both, combined"
    assert _state(main, dec.id) == "confirmed"


def test_clarify_card_answer_before_capture(tmp_path: Path, hook_input: Any) -> None:
    """The read-back card (nothing written yet) reaches the owner through the stop hook of
    a turn that changed no file; the answer is relayed once capture raised the decision."""
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    _start_turn(main)
    out = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(out):
        assert cli.main(["clarify", "make SR-005 pin only the affirmed records",
                         "--root", str(main)]) == 0
    assert '▸ Conflict  SR-005 "relay checks"' in out.getvalue()
    reply = _stop(main, hook_input)
    assert '▸ Conflict  SR-005 "relay checks"' in reply
    assert _stated(main)["early"] == [{"record": "SR-005", "branch": "feat-x"}]
    words = "keep feat-x's"
    digest = log_prompt(main, words, at=_later())
    change(main, "A relay pins only the records the owner's words affirm.")
    dec = _decision(main)
    assert cli.main(["conflict", "relay", "SR-005", "--prompt", digest, "--quote", words,
                     "--root", str(main)]) == 0
    assert _decision(main).fields["chosen"] == "feat-x's version"
    assert _state(main, dec.id) == "confirmed"


def test_plumb_conflicts_lists_the_early_card(tmp_path: Path, hook_input: Any) -> None:
    """/plumb conflicts shows the unanswered early conflict and asks the stop hook to show
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
    assert '▸ Conflict  SR-005 "relay checks"' in text
    assert "feat-x      A relay pins the stated group, named by its title." in text
    _start_turn(main)
    assert "▸ Conflict  SR-005" in _stop(main, hook_input, active=True)
    assert _relay(main, "relay checks", "keep feat-x's", take="feat-x") == 0
    assert _state(main, dec.id) == "confirmed"


def test_host_without_prompt_hook_is_labelled(tmp_path: Path, hook_input: Any) -> None:
    """The CLI-fallback host: a message the agent recorded itself answers too, labelled
    "self-recorded message" (R13 Q4)."""
    main, _other = _captured_with_card(tmp_path, hook_input)
    dec = _decision(main)
    assert _relay(main, dec.id, "keep feat-x's", via="turn") == 0
    approval = [e.payload for e in open_core(main).log_read("events", ["approval"])][-1]
    assert approval["self_recorded"] is True and approval["choice"]["take"] == "feat-x"
    assert _state(main, dec.id) == "confirmed"


def test_owner_terminal_answer(tmp_path: Path, hook_input: Any) -> None:
    main, _other = _captured_with_card(tmp_path, hook_input)
    dec = _decision(main)
    assert cli.main(["conflict", "choose", dec.id, "--take", "feat-x",
                     "--root", str(main)]) == 0
    assert _decision(main).fields["chosen"] == "feat-x's version"
    assert _state(main, dec.id) == "confirmed"


# -- the answer is never inverted


def test_plain_ok_naming_the_other_side_is_refused(tmp_path: Path, hook_input: Any) -> None:
    """"ok DEC-001, keep feat-x's" never confirms the preset "main's version"."""
    main, _other = _captured_with_card(tmp_path, hook_input)
    dec = _decision(main)
    words = f"ok {dec.id}, keep feat-x's"
    digest = log_prompt(main, words, at=_later())
    assert cli.main(["relay", dec.id, "--prompt", digest, "--quote", f"ok {dec.id}",
                     "--root", str(main)]) == 3
    assert _state(main, dec.id) == "proposed"
    assert _relay(main, dec.id, words) == 0                    # the pick path records it
    assert _decision(main).fields["chosen"] == "feat-x's version"


def test_words_naming_no_version_or_two_are_refused(tmp_path: Path, hook_input: Any) -> None:
    main, _other = _captured_with_card(tmp_path, hook_input)
    dec = _decision(main)
    assert _relay(main, dec.id, "hmm, not sure yet") == 3
    assert _relay(main, dec.id, "keep main's or feat-x's, whatever") == 3
    assert _relay(main, dec.id, "keep feat-x's but change the title") == 3
    assert _relay(main, dec.id, "keep feat-x's", take="main") == 3
    assert _state(main, dec.id) == "proposed"


def test_answer_needs_the_card_shown(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    change(main, "A relay pins only the records the owner's words affirm.")
    dec = _decision(main)
    assert _relay(main, dec.id, "keep feat-x's") == 3          # no reply showed it
    assert _relay(main, dec.id, f"keep feat-x's for {dec.id}") == 0  # the owner named it


# -- the heuristic never says "compatible" on its own (finding: a plain contradiction passed)


class _Verdict:
    def __init__(self, name: str, verdict: str, confidence: float) -> None:
        self.name, self.verdict, self.confidence = name, verdict, confidence

    def contradiction(self, prompt: str, record: Any) -> Any:
        from plumb.contracts import Judgment

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
    assert _relay(main, dec.id, "keep feat-x's") == 0
    [mine] = [c for c in inflight.read(main, allow_git=True)[1]["claims"]
              if c["branch"] == "main"]
    assert mine["conflicts"][0]["state"] == "confirmed"
    assert mine["conflicts"][0]["chosen"] == "feat-x's version"
