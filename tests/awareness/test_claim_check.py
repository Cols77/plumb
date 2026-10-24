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

from awareness.gitrepo import add_worktree, requirement
from awareness.scenario import change, setup
from plumb import cli
from plumb.api import open_core
from plumb.hosts.claude_code import stop
from plumb.understand.summary import ASK_OWNER

pytestmark = pytest.mark.sr("SR-259")
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


def agent_channel(root: Path, session: str = "s1") -> str:
    """SR-266, SR-295: what the stop queued for the agent (the cards in full, each the owner
    must settle tagged for the agent to ask), taken once."""
    path = root / ".plumb" / "session" / session / "agent_notes.json"
    notes = json.loads(path.read_text("utf-8")) if path.exists() else []
    path.unlink(missing_ok=True)
    return "\n\n".join(str(n) for n in notes)


def _turn(root: Path, hook_input: Any) -> tuple[list[str], str]:
    """The stop hook's two passes: the owner's plumb lines (SR-265, SR-363: never the card
    nor a count of it) and the agent's channel of the last pass (the card in full)."""
    lines = [_stop(root, hook_input)]
    agent_channel(root)
    lines.append(_stop(root, hook_input, active=True))
    return [line for line in lines if line], agent_channel(root)


def _decisions(root: Path) -> list[Any]:
    return [r for r in open_core(root).index().values() if r.kind == "decision"]


def _answer(root: Path, ref: str, take: str = "feat-x") -> int:
    """The owner's own terminal answers the card."""
    return cli.main(["conflict", "choose", ref, "--take", take, "--root", str(root)])


def early_heads(reply: str, title: str) -> list[str]:
    """The early conflict cards (SR-012: the owner sees cards, titles not IDs) about the
    record titled ``title``."""
    lines = reply.splitlines()
    return [f"{line} {lines[n + 1]}" for n, line in enumerate(lines[:-1])
            if line == title and lines[n + 1].startswith(("feat-x says", "main says"))]


def _assert_asked_and_answered(root: Path, lines: list[str], cards: str, record: str) -> None:
    # the stop never blocks for it: the owner's text counts no question (SR-363), and the card
    # reaches the agent tagged for the owner to settle (SR-265, SR-295)
    assert lines == [], lines
    assert ASK_OWNER in cards, cards
    assert early_heads(cards, open_core(root).index()[record].title), cards
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
    lines, cards = _turn(mine, hook_input)
    _assert_asked_and_answered(mine, lines, cards, "SR-005")


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
    lines, cards = _turn(mine, hook_input)
    _assert_asked_and_answered(mine, lines, cards, new)


def test_capture(tmp_path: Path, hook_input: Any) -> None:
    _other, mine = _lanes(tmp_path)
    _start_turn(mine)
    result = change(mine, OURS)
    assert any('"relay checks" waits as a card' in line for line in result.lines)
    lines, cards = _turn(mine, hook_input)
    assert early_heads(cards, "relay checks"), cards
    [dec] = _decisions(mine)
    assert _answer(mine, dec.id) == 0
    assert open_core(mine).index()[dec.id].fields["chosen"] == "feat-x's version"
    assert lines == [], lines                     # SR-363: no question count


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
    assert 'over "relay checks" waits as a card' in _clarify(mine)
    requirement(mine, "SR-005", "relay checks", OURS, feature="FEAT-002")
    lines, cards = _turn(mine, hook_input)
    # the read-back's card is drawn once (its decision has its own card since SR-012)
    assert len(early_heads(cards, "relay checks")) == 1
    _assert_asked_and_answered(mine, lines, cards, "SR-005")


def test_clarify_card_answered_before_any_edit(tmp_path: Path, hook_input: Any) -> None:
    """The owner answers the read-back card at once, before anything is written: the
    decision is raised from the card the owner saw and holds the owner's pick."""
    _other, mine = _lanes(tmp_path)
    _start_turn(mine)
    _clarify(mine)
    line = _stop(mine, hook_input)                # a turn that changed no file
    assert line == "", line                       # SR-363: no question count
    cards = agent_channel(mine)
    assert early_heads(cards, "relay checks"), cards
    assert _decisions(mine) == []
    assert _answer(mine, "SR-005") == 0
    [dec] = _decisions(mine)
    assert dec.fields["chosen"] == "feat-x's version"
    assert open_core(mine).status([dec.id])[dec.id].confirmation == "confirmed"
