"""R17: intent conflicts caught at capture and read-back time, before any work (SR-081)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from awareness.scenario import capture, change, new_requirement, setup
from plumb.api import open_core
from plumb.awareness import inflight
from plumb.contracts import Judgment

pytestmark = pytest.mark.sr("SR-259")


class Judge:
    """A judgment backend whose compatibility verdict the test sets."""

    name = "jev"

    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, str]] = []

    def contradiction(self, prompt: str, record: Any) -> Judgment:
        self.calls.append((prompt, record.id))
        return Judgment(action="contradiction", subject=record.id, verdict=self.verdict,
                        confidence=0.9, tier="act", backend="jev", fingerprint="f")


def _decisions(root: Path) -> list[Any]:
    return [r for r in open_core(root).index().values() if r.kind == "decision"]


def test_same_record_conflict_card_and_one_decision(tmp_path: Path) -> None:
    """SR-081 EX-1: deterministic, no judgment needed."""
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    result = change(main, "A relay pins only the records the owner's words affirm.")
    text = "\n".join(result.lines)
    assert '"relay checks" waits as a card' in text
    assert "Say:" not in text      # the card asks the owner, not the agent
    decisions = _decisions(main)
    assert len(decisions) == 1
    dec = decisions[0]
    assert dec.fields["matters"] is True
    assert dec.fields["question"].startswith('Branch feat-x says "A relay pins the stated group')
    assert dec.fields["question"].endswith(": which one, or both?")
    assert {(link.kind, link.target.record) for link in dec.links} >= {("decides", "SR-005"),
                                                                       ("derives_from",
                                                                        "INT-001")}
    assert dec.id in result.written
    mine = [c for c in inflight.read(main, allow_git=True)[1]["claims"]
            if c["branch"] == "main"]
    assert mine[0]["conflicts"][0]["dec"] == dec.id
    assert mine[0]["conflicts"][0]["branch"] == "feat-x"


def test_feature_overlap_judged_contradictory_is_a_conflict(tmp_path: Path) -> None:
    """SR-081 EX-2: new intent in the same feature, judged contradictory."""
    main, other = setup(tmp_path)
    new_requirement(other, "relay groups", "A relay confirms a group named by its title.")
    judge = Judge("contradicts")
    result = new_requirement(main, "relay single", "A relay confirms one record at a time.",
                             backend=judge)
    assert judge.calls and judge.calls[0][0] == "A relay confirms a group named by its title."
    text = "\n".join(result.lines)
    assert "waits as a card" in text
    assert len(_decisions(main)) == 1


def test_feature_overlap_judged_compatible_is_one_line(tmp_path: Path) -> None:
    """SR-081 EX-3: compatible: one warning line, no decision."""
    main, other = setup(tmp_path)
    new_requirement(other, "relay groups", "A relay confirms a group named by its title.")
    result = new_requirement(main, "status colours", "The card is green when aligned.",
                             backend=Judge("benign"))
    warnings = [line for line in result.lines if "judged compatible" in line]
    assert len(warnings) == 1 and "feat-x" in warnings[0]
    assert not any("Conflict" in line for line in result.lines)
    assert _decisions(main) == []


def test_heuristic_fallback_without_jev(tmp_path: Path) -> None:
    """Without JEV the heuristic judges; the capture never fails for it."""
    main, other = setup(tmp_path)
    new_requirement(other, "relay groups", "A relay confirms a group named by its title.")
    result = new_requirement(main, "status colours", "The card is green when aligned.")
    assert any("feat-x" in line for line in result.lines)


def test_conflict_raised_once_for_both_branches(tmp_path: Path) -> None:
    """SR-081 EX-4: the other branch already raised it: no second decision; the line names
    that branch, then the owner's answer once given."""
    main, other = setup(tmp_path)
    change(main, "main's version of the relay")
    change(other, "feat-x's version of the relay")              # feat-x raises the DEC
    [dec] = _decisions(other)
    result = change(main, "main's version again, reworded")
    assert _decisions(main) == []
    known = [line for line in result.lines if "asked on branch feat-x" in line]
    assert known == ['plumb: SR-005 "relay checks": the owner is asked on branch feat-x '
                     "whether this work or that branch's holds; build on the answer"]
    from plumb import approvals

    approvals.approve(open_core(other), [dec.id])           # the owner answers on feat-x
    assert inflight.sync_decisions(open_core(other)) is True
    assert inflight.sync_decisions(open_core(other)) is False  # nothing new to carry
    result = change(main, "main's version, third wording")
    settled = [line for line in result.lines if "settled it on branch feat-x" in line]
    assert settled == ['plumb: SR-005 "relay checks": the owner settled it on branch feat-x: '
                       "\"feat-x's version\"; build on that"]


def test_clarify_shows_the_card_before_anything_is_written(tmp_path: Path) -> None:
    """SR-081 EX-5: the read-back check, nothing written."""
    from plumb.capture.clarify import clarify, view_lines

    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    before = sorted(p.name for p in (main / ".plumb").rglob("*.md"))
    view = clarify(open_core(main), "make SR-005 pin only the affirmed records")
    lines = view_lines(view)
    assert lines[0] == ('a conflict with feat-x over "relay checks" waits as a card for the '
                        "owner at the end of this turn; do not restate it")
    assert not any("SR-005" in line or "Say:" in line for line in lines)    # SR-151 EX-3
    assert sorted(p.name for p in (main / ".plumb").rglob("*.md")) == before
    assert inflight.read(main, allow_git=True)[1]["claims"][0]["branch"] == "feat-x"


def test_dry_run_checks_and_records_nothing(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    result = change(main, "main's version", dry_run=True)
    assert any("waits as a card" in line for line in result.lines)
    assert "plumb: nothing recorded (a preview)" in result.lines
    assert _decisions(main) == []
    assert [c["branch"] for c in inflight.read(main, allow_git=True)[1]["claims"]] == [
        "feat-x"]


def test_own_branch_claims_never_conflict(tmp_path: Path) -> None:
    main, _other = setup(tmp_path)
    change(main, "first wording")
    result = change(main, "second wording")
    assert not any("Conflict" in line for line in result.lines)
    assert _decisions(main) == []


def test_capture_never_fails_on_an_inflight_error(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    main, _other = setup(tmp_path)

    def broken(*a: object, **k: object) -> None:
        raise RuntimeError("register unreadable")

    from plumb.awareness import early

    monkeypatch.setattr(early, "after_capture", broken)
    result = capture(main, {"intent": "INT-001",
                            "updates": [{"id": "SR-005", "statement": "still written"}]})
    assert "SR-005" in result.updated
    assert any("not checked" in line for line in result.lines)


def test_same_version_on_both_branches_asks_nothing(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group.")
    result = change(main, "A relay pins the stated group.")
    assert not any("Conflict" in line for line in result.lines)
    assert _decisions(main) == []


# -- the owner's answer reads the same on every branch (R17: both lanes build on one answer):
#    one test per surface that shows it


def _settled(tmp_path: Path) -> tuple[Path, Path]:
    """main and feat-x both change SR-005; feat-x raises the decision; the owner confirms
    it on feat-x, which keeps feat-x's version."""
    from plumb import approvals

    main, other = setup(tmp_path)
    change(main, "main's version of the relay")
    change(other, "feat-x's version of the relay")
    [dec] = _decisions(other)
    assert dec.fields["chosen"] == "feat-x's version"       # named by branch at the source
    approvals.approve(open_core(other), [dec.id])
    inflight.sync_decisions(open_core(other))
    return main, other


_SETTLED = ('plumb: SR-005 "relay checks": the owner settled it on branch feat-x: '
            "\"feat-x's version\"; build on that")


def test_settled_answer_on_the_capture_line(tmp_path: Path) -> None:
    main, _other = _settled(tmp_path)
    result = change(main, "main's version, reworded")
    assert _SETTLED in result.lines
    assert not any("this request's version" in line for line in result.lines)


def test_settled_answer_on_the_clarify_read_back(tmp_path: Path) -> None:
    from plumb.awareness import early

    main, _other = _settled(tmp_path)
    check = early.check_text(open_core(main), "make SR-005 pin only the affirmed records")
    assert check.lines == [_SETTLED] and check.conflicts == []


def test_settled_answer_on_the_brief_line(tmp_path: Path) -> None:
    from plumb import awareness

    main, _other = _settled(tmp_path)
    assert _SETTLED in awareness.brief_lines(open_core(main))


def test_settled_answer_on_the_prompt_delta_line(tmp_path: Path) -> None:
    from plumb import awareness

    main, _other = _settled(tmp_path)
    assert _SETTLED in [line.text for line in awareness.delta_lines(open_core(main),
                                                                    ["SR-005"])]


def test_an_answer_in_relative_words_is_shown_by_branch(tmp_path: Path) -> None:
    """A register (or a relayed answer) holding "this request's version" or "keep this one"
    is shown on the other branch as the raising branch's version."""
    from plumb import awareness

    main, _other = _settled(tmp_path)

    def relative(data: dict) -> dict:
        for claim in data["claims"]:
            for conflict in claim.get("conflicts") or []:
                conflict["chosen"] = "this request's version"
        return data

    inflight.update(main, relative)
    assert _SETTLED in awareness.brief_lines(open_core(main))
    assert inflight.neutral_chosen("Keep this one.", "feat-x") == "feat-x's version"
    assert inflight.neutral_chosen("both, combined", "feat-x") == "both, combined"


# -- the same record is caught whatever part of it changed (R17): the record's whole content
#    decides "the same version", never the clipped words a claim keeps for the card


def _examples(then: str) -> dict:
    return {"intent": "INT-001", "updates": [{"id": "SR-005", "examples": [
        {"given": "a relay of SR-005", "when": "the owner says ok", "then": then}]}]}


def test_different_examples_are_a_conflict(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    capture(other, _examples("the group is pinned"))
    result = capture(main, _examples("only the affirmed records are pinned"))
    assert any('"relay checks" waits as a card' in line for line in result.lines)
    assert len(_decisions(main)) == 1


_LONG = "A relay pins the stated records. " * 8          # longer than a claim keeps


def test_different_tails_of_a_long_statement_are_a_conflict(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    change(other, _LONG + "Then the group is pinned.")
    result = change(main, _LONG + "Then only the affirmed records are pinned.")
    assert any("waits as a card" in line for line in result.lines)
    assert len(_decisions(main)) == 1


def test_preview_of_a_different_tail_shows_the_card(tmp_path: Path) -> None:
    """The dry-run entry point (``preview``): a planned version is never 'the same'."""
    main, other = setup(tmp_path)
    change(other, _LONG + "Then the group is pinned.")
    result = change(main, _LONG + "Then only the affirmed records are pinned.", dry_run=True)
    assert any("waits as a card" in line for line in result.lines)
    assert _decisions(main) == []


# -- a branch holds each record ONCE, at the version it wrote last (R17: asked once; the same
#    words ask nothing): one test per entry point that reads a branch's claims


_SR005 = ".plumb/requirements/SR-005.md"


def _edited_outside_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch
                            ) -> tuple[Path, Path]:
    """feat-x claims SR-005 by a capture (claim ``feat-x:INT-001``), then changes it again
    with no claim written (an edit outside capture); its stop hook claims the new version
    (claim ``feat-x:-``)."""
    from plumb.awareness.publish import publish
    from plumb.awareness.turn import claim_changes

    main, other = setup(tmp_path)
    change(other, "feat-x version one")
    with monkeypatch.context() as patched:
        patched.setattr(inflight, "record_claim", lambda *a, **k: None)
        change(other, "feat-x version two")
    assert claim_changes(open_core(other), publish(open_core(other), [_SR005])) is True
    return main, other


def test_stop_hook_claim_moves_the_record_out_of_the_older_claim(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main, other = _edited_outside_capture(tmp_path, monkeypatch)
    holders = [c for c in inflight.read(main, allow_git=True)[1]["claims"]
               if "SR-005" in (c.get("records") or {})]
    assert [c["id"] for c in holders] == ["feat-x:-"]
    assert holders[0]["records"]["SR-005"]["hash"] == open_core(other).index()["SR-005"].hash


def test_capture_asks_once_against_the_newest_version(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check_records: one card and one decision, not one per claim of feat-x."""
    main, _other = _edited_outside_capture(tmp_path, monkeypatch)
    result = change(main, "main version")
    cards = [line for line in result.lines if "waits as a card" in line]
    assert len(cards) == 1
    assert len(_decisions(main)) == 1


def test_capture_of_the_newest_version_asks_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check_records: the same words feat-x now holds are no conflict (no stale claim)."""
    main, _other = _edited_outside_capture(tmp_path, monkeypatch)
    result = change(main, "feat-x version two")
    assert not any("Conflict" in line for line in result.lines)
    assert _decisions(main) == []


def test_read_back_asks_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check_text: one card for the record, with feat-x's newest words."""
    from plumb.awareness import early

    main, _other = _edited_outside_capture(tmp_path, monkeypatch)
    check = early.check_text(open_core(main), "make SR-005 pin only the affirmed records")
    assert [(c.record, c.branch, c.theirs) for c in check.conflicts] == [
        ("SR-005", "feat-x", "feat-x version two")]


class _Unavailable:
    name = "jev"

    def contradiction(self, prompt: str, record: Any) -> Judgment:
        from plumb.judgment import JudgmentUnavailable

        raise JudgmentUnavailable("no judge", "judgment.backend is not set")


@pytest.mark.sr("SR-237")
def test_check_live_contradicts_benign_and_unavailable(tmp_path: Path) -> None:
    from plumb.awareness.early import check_live

    main, _ = setup(tmp_path)
    result = new_requirement(main, "relay checks pin nothing",
                             "A relay pins no stated record at all.", backend=Judge("benign"))
    new = result.written[0]
    core = open_core(main)
    bad = check_live(core, [new], backend=Judge("contradicts"))
    assert any(f"{new} contradicts SR-005" in line and "supersedes: [SR-005]" in line
               for line in bad)
    assert not any("SR-005" in line for line in check_live(core, [new], exclude=["SR-005"],
                                                           backend=Judge("contradicts")))
    unsure = check_live(core, [new], backend=_Unavailable())
    assert any("judging unavailable: no judge: judgment.backend is not set" in line
               and f"{new} not checked against SR-005" in line for line in unsure)
    assert not any("may change what" in line for line in unsure)
    assert check_live(core, [new], backend=Judge("benign")) == []


@pytest.mark.sr("SR-237")
def test_check_live_with_no_configured_judge_says_not_checked(tmp_path: Path) -> None:
    """eval-e135b2b0: with judgment.backend unset, the live check says it could not judge;
    it never claims "may change" with the unavailability as its reason."""
    from plumb.awareness.early import check_live

    main, _ = setup(tmp_path)
    result = new_requirement(main, "relay checks pin nothing",
                             "A relay pins no stated record at all.", backend=Judge("benign"))
    new = result.written[0]
    lines = check_live(open_core(main), [new])
    assert not any("may change what" in line for line in lines), lines


@pytest.mark.sr("SR-237")
def test_check_live_judges_the_opposite_even_when_wordier_records_outrank_it(
        repo: Path, write_record) -> None:
    """SR-165 EX-2: SR-076 (the agent relays the choice) and SR-150 (never relayed) ranked 4th
    by words behind longer, related records; the opposite is still judged and named."""
    from plumb.awareness.early import check_live

    def sr(n: int, statement: str) -> str:
        return (f"---\nid: SR-{n:03d}\ntitle: t{n}\nstatement: {statement}\nexamples:\n"
                f"- {{id: EX-1, given: g, when: w, then: t}}\n---\n")

    base = "the agent relays the owner's conflict choice on the conflict card to the driver"
    write_record(repo, sr(1, base + " and the owner answers"))
    for n in range(2, 7):    # five related records that share more words than the opposite
        write_record(repo, sr(n, base + f" and the owner answers it again {n}"))
    write_record(repo, sr(7, "the agent never relays the owner's conflict choice"))
    judge = Judge("contradicts")
    lines = check_live(open_core(repo), ["SR-001"], backend=judge)
    assert any("never relays" in prompt for prompt, _ in judge.calls)
    assert any("SR-001 contradicts SR-007" in line for line in lines)
