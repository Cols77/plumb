"""R17: the early intent-conflict check runs wherever a branch's claim is written, not only
in ``plumb capture`` (SR-081 EX-11). Another branch claiming the same record at another
version raises the decision once and shows its card, so the owner's "keep feat-x's" is
recorded whatever tool wrote the record. One test per entry point that writes a claim: a
direct edit then the stop hook, ``plumb new`` then the stop hook, capture, and the clarify
read-back followed by an edit (and its card answered before any edit)."""

from __future__ import annotations

import contextlib
import io
import json
import time
from pathlib import Path
from typing import Any

import pytest
from mergedriver.mdhelpers import log_prompt

from awareness.gitrepo import add_worktree, requirement
from awareness.scenario import change, setup
from plumb import cli
from plumb.api import open_core
from plumb.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-081")
THEIRS = "A relay pins the stated group, named by its title."
OURS = "A relay pins only the records the owner's words affirm."


def _later() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 5))


def _lanes(tmp_path: Path) -> tuple[Path, Path]:
    """feat-x captured its version of SR-005 (its claim); feat-y starts from main."""
    main, other = setup(tmp_path)
    change(other, THEIRS)
    return other, add_worktree(main, tmp_path / "wt-y", "feat-y")


def _start_turn(root: Path, session: str = "s1") -> None:
    path = root / ".plumb" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}),
                    encoding="utf-8")


def _stop(root: Path, hook_input: Any, *, active: bool = False) -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id="s1", stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=root, verify=None,
                     unjudged=None) == 0
    text = out.getvalue()
    if not text.strip():
        return ""
    data = json.loads(text)
    return str(data.get("systemMessage") or data.get("reason") or "")


def _turn(root: Path, hook_input: Any) -> tuple[str, str]:
    """The stop hook's two passes: the block that tells the agent, the reply the owner
    reads."""
    return _stop(root, hook_input), _stop(root, hook_input, active=True)


def _decisions(root: Path) -> list[Any]:
    return [r for r in open_core(root).index().values() if r.kind == "decision"]


def _answer(root: Path, ref: str, words: str = "keep feat-x's") -> int:
    digest = log_prompt(root, words, at=_later())
    return cli.main(["conflict", "relay", ref, "--prompt", digest, "--quote", words,
                     "--root", str(root)])


def _assert_asked_and_answered(root: Path, asked: str, reply: str, record: str) -> None:
    assert "ask the owner now" in asked, asked
    assert f'▸ Conflict  {record} "' in reply, reply
    [dec] = _decisions(root)
    assert dec.fields.get("matters") is True
    assert _answer(root, record) == 0
    dec = open_core(root).index()[dec.id]
    assert dec.fields["chosen"] == "feat-x's version"
    assert open_core(root).status([dec.id])[dec.id].confirmation == "confirmed"


def test_direct_edit_then_stop_hook(tmp_path: Path, hook_input: Any) -> None:
    """feat-y edits SR-005's file by hand: the stop hook claims it, finds feat-x's claim
    at another version, raises the decision and shows the card."""
    _other, mine = _lanes(tmp_path)
    _start_turn(mine)
    requirement(mine, "SR-005", "relay checks", OURS, feature="FEAT-002")
    asked, reply = _turn(mine, hook_input)
    _assert_asked_and_answered(mine, asked, reply, "SR-005")


def test_plumb_new_then_stop_hook(tmp_path: Path, hook_input: Any,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """``plumb new`` writes a requirement in FEAT-002, which feat-x claims; the backend
    judges it contradictory: the stop hook raises the decision and shows the card."""
    import plumb.judgment as judgment
    from plumb.contracts import Judgment

    class Contradicts:
        name = "jev"

        def contradiction(self, prompt: str, record: Any) -> Any:
            return Judgment(action="contradiction", subject=record.id, verdict="contradicts",
                            confidence=0.9, tier="accept", backend="jev:test",
                            fingerprint="f")

    monkeypatch.setattr(judgment, "get_backend", lambda core, hook: Contradicts())
    _other, mine = _lanes(tmp_path)
    _start_turn(mine)
    with contextlib.redirect_stdout(io.StringIO()):
        assert cli.main(["new", "requirement", "--title", "relay names", "--feature",
                         "FEAT-002", "--statement", "A relay never pins a group by its "
                         "title.", "--root", str(mine)]) == 0
    [new] = [r.id for r in open_core(mine).index().values()
             if r.kind == "requirement" and r.title == "relay names"]
    asked, reply = _turn(mine, hook_input)
    _assert_asked_and_answered(mine, asked, reply, new)


def test_capture(tmp_path: Path, hook_input: Any) -> None:
    _other, mine = _lanes(tmp_path)
    _start_turn(mine)
    result = change(mine, OURS)
    assert any(line.startswith('▸ Conflict  SR-005 "relay checks"') for line in result.lines)
    asked, reply = _turn(mine, hook_input)
    assert '▸ Conflict  SR-005 "' in reply
    [dec] = _decisions(mine)
    assert _answer(mine, dec.id) == 0
    assert open_core(mine).index()[dec.id].fields["chosen"] == "feat-x's version"
    assert asked


def _clarify(root: Path) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli.main(["clarify", "change SR-005 relay checks so only the affirmed "
                         "records are pinned", "--root", str(root)]) == 0
    return out.getvalue()


def test_clarify_then_edit(tmp_path: Path, hook_input: Any) -> None:
    """The read-back card first (nothing written), then a direct edit: the stop hook raises
    the decision once, and the owner's "keep feat-x's" records it."""
    _other, mine = _lanes(tmp_path)
    _start_turn(mine)
    assert '▸ Conflict  SR-005 "relay checks"' in _clarify(mine)
    requirement(mine, "SR-005", "relay checks", OURS, feature="FEAT-002")
    asked, reply = _turn(mine, hook_input)
    assert reply.count('▸ Conflict  SR-005 "relay checks"') == 1
    _assert_asked_and_answered(mine, asked, reply, "SR-005")


def test_clarify_card_answered_before_any_edit(tmp_path: Path, hook_input: Any) -> None:
    """The owner answers the read-back card at once, before anything is written: the
    decision is raised from the card the owner saw and holds the owner's pick."""
    _other, mine = _lanes(tmp_path)
    _start_turn(mine)
    _clarify(mine)
    reply = _stop(mine, hook_input)               # a turn that changed no file
    assert '▸ Conflict  SR-005 "relay checks"' in reply
    assert _decisions(mine) == []
    assert _answer(mine, "SR-005") == 0
    [dec] = _decisions(mine)
    assert dec.fields["chosen"] == "feat-x's version"
    assert open_core(mine).status([dec.id])[dec.id].confirmation == "confirmed"
