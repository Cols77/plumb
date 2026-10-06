"""BRIDGE B2: the heuristic default backend and ``get_backend`` (spec 8.2, 6.2 step 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.contracts import JudgmentBackend, Link, LinkState, Pin, Target
from plumb.judgment import get_backend
from plumb.judgment.heuristic import HeuristicBackend

pytestmark = [pytest.mark.sr("SR-021"), pytest.mark.sr("SR-010")]

SR_004 = """---
id: SR-004
title: Approvals pin exact content
statement: An approval pins the record hash; an edit leaves the record unconfirmed.
examples:
- id: EX-1
  given: an approved requirement
  when: its statement is edited
  then: the requirement is an unconfirmed edit
---
"""


@pytest.fixture
def sr004(repo: Path, write_record):
    write_record(repo, SR_004)
    return open_core(repo).index()["SR-004"]


def test_intent_change_flags_change_words_on_confirmed_match(sr004) -> None:
    backend = HeuristicBackend()
    [j] = backend.intent_change("Instead, SR-004 should let approvals survive edits", [sr004])
    assert (j.action, j.subject, j.verdict) == ("intent-change", "SR-004", "change")
    assert j.backend == "heuristic"
    assert j.tier == "escalate-llm"
    assert j.fingerprint.startswith("sha256:")
    # strong term overlap without the ID also matches
    [j] = backend.intent_change("approvals should no longer pin the record hash after an "
                                "edit of the statement", [sr004])
    assert j.verdict == "change"
    # multi-word and contracted change language
    [j] = backend.intent_change("don't make SR-004 strict", [sr004])
    assert j.verdict == "change"


def test_no_flag_without_overlap(sr004) -> None:
    backend = HeuristicBackend()
    [j] = backend.intent_change("instead of tabs use spaces in the README", [sr004])
    assert j.verdict == "no-change"
    [j] = backend.intent_change("please look at SR-004 and tell me about it", [sr004])
    assert j.verdict == "no-change"
    # a change word inside another word is no change word
    [j] = backend.intent_change("SR-004 exchange rates", [sr004])
    assert j.verdict == "no-change"


def _state(path: str) -> LinkState:
    link = Link(source="SR-001", index=0, kind="implemented_by", target=Target(path=path),
                pin=Pin("sha256:a", "sha256:b"))
    return LinkState(link=link, state="stale", moved="target")


def test_drift_triage_cosmetic_for_comment_only_change() -> None:
    before = 'def f(x):\n    """Doc."""\n    return x + 1\n'
    after = 'def f(x):  # comment\n    """Another doc."""\n\n    return   x + 1\n'
    [j] = HeuristicBackend().drift_triage([_state("src/m.py")],
                                          {"SR-001#0": (before, after)})
    assert (j.action, j.subject, j.verdict) == ("drift-triage", "SR-001#0", "cosmetic")
    [j] = HeuristicBackend().drift_triage([_state("docs/a.md")],
                                          {"SR-001#0": ("a  b\n", "a b\n\n")})
    assert j.verdict == "cosmetic"


def test_drift_triage_material_for_logic_change() -> None:
    before = "def f(x):\n    return x + 1\n"
    after = "def f(x):\n    return x + 2\n"
    [j] = HeuristicBackend().drift_triage([_state("src/m.py")],
                                          {"SR-001#0": (before, after)})
    assert j.verdict == "material"
    # unparsable Python falls back to the whitespace comparison
    [j] = HeuristicBackend().drift_triage([_state("src/m.py")],
                                          {"SR-001#0": ("def (:\n", "def (: x\n")})
    assert j.verdict == "material"
    # a link without texts is not triaged
    assert HeuristicBackend().drift_triage([_state("src/m.py")], {}) == []


def test_fidelity_is_unsure_escalate_llm(repo: Path, sr004) -> None:
    from plumb.judgment.fidelity import build_packet

    packet = build_packet(open_core(repo), None, "SR-004")
    j = HeuristicBackend().fidelity(packet)
    assert (j.action, j.subject, j.verdict, j.tier) == ("fidelity", "SR-004", "unsure",
                                                        "escalate-llm")


def test_get_backend_default_is_heuristic(repo: Path) -> None:
    backend = get_backend(open_core(repo), hook=True)
    assert backend.name == "heuristic"
    assert isinstance(backend, JudgmentBackend)


def _set_backend(repo: Path, name: str) -> None:
    (repo / ".plumb" / "config.yaml").write_text(f"judgment:\n  backend: {name}\n",
                                                encoding="utf-8")


def test_disabled_backend_is_unsure(repo: Path, sr004) -> None:
    _set_backend(repo, "disabled")
    backend = get_backend(open_core(repo), hook=False)
    assert backend.name == "disabled"
    [j] = backend.intent_change("instead SR-004 changes", [sr004])
    assert (j.verdict, j.tier) == ("unsure", "escalate-llm")
    [j] = backend.drift_triage([_state("a.py")], {"SR-001#0": ("a", "b")})
    assert (j.verdict, j.tier) == ("unsure", "escalate-llm")


def test_fake_backend_returns_canned_answers(repo: Path, sr004, monkeypatch) -> None:
    import plumb.judgment as judgment

    _set_backend(repo, "fake")
    monkeypatch.setitem(judgment.FAKE_ANSWERS, ("intent-change", "SR-004"), ("change", 0.97))
    backend = get_backend(open_core(repo), hook=True)
    [j] = backend.intent_change("anything", [sr004])
    assert (j.verdict, j.confidence, j.tier, j.backend) == ("change", 0.97, "accept", "fake")


def test_unknown_backend_falls_back_to_heuristic(repo: Path) -> None:
    _set_backend(repo, "oracle")
    backend = get_backend(open_core(repo), hook=True)
    assert backend.name == "heuristic"
    assert any("oracle" in n for n in getattr(backend, "notices", ()))


def test_jev_without_adapter_falls_back_with_notice(repo: Path, monkeypatch) -> None:
    import sys

    _set_backend(repo, "jev")
    monkeypatch.setitem(sys.modules, "plumb.judgment.jev", None)
    backend = get_backend(open_core(repo), hook=True)
    assert backend.name == "heuristic"
    assert any("jev" in n for n in backend.notices)
    # one notice per session: the second resolution stays quiet
    again = get_backend(open_core(repo), hook=True)
    assert again.notices == ()


# -- sp2 11.2: the additions of the judgment protocol (SR-038, SR-039)


@pytest.mark.sr("SR-039")
def test_heuristic_entailment_is_term_coverage_never_high() -> None:
    backend = HeuristicBackend()
    assert backend.version == "heuristic"
    j = backend.entailment("add multiply next to add, 2 times 3 is 6",
                           "will: multiply returns the product\nwill: 2 times 3 is 6",
                           subject="INT-017", claim_kind="intent-readback")
    assert j.action == "faithfulness" and j.subject == "INT-017"
    assert j.probability is not None and 0 < j.probability < 1
    assert j.confidence_label == "low"  # the heuristic never auto-approves (R8 B)
    full = backend.entailment("add multiply next to add", "add multiply next to add",
                              subject="INT-017", claim_kind="intent-readback")
    assert full.verdict == "entailed" and full.probability == 1.0
    penalised = backend.entailment("add multiply next to add",
                                   "add multiply next to add\nwon't: floats or decimals",
                                   subject="INT-017", claim_kind="intent-readback")
    assert penalised.probability < full.probability
    assert any("unsupported won't" in r for r in penalised.reasons)
    empty = backend.entailment("", "anything", subject="X", claim_kind="intent-readback")
    assert empty.probability == 0.0


@pytest.mark.sr("SR-038")
def test_heuristic_contradiction_labels(sr004) -> None:
    backend = HeuristicBackend()
    assert backend.contradiction("approvals should no longer pin the record hash",
                                 sr004).verdict == "contradicts"
    assert backend.contradiction("SR-004 should also pin the owner's name next to the hash",
                                 sr004).verdict == "extends"
    assert backend.contradiction("fix the typo in the SR-004 docstring",
                                 sr004).verdict == "benign"


@pytest.mark.sr("SR-044")
def test_heuristic_choose_needs_a_clear_lead_and_ask_is_unsure() -> None:
    backend = HeuristicBackend()
    j = backend.choose("Which requirement owns src/app/mul.py?", ["SR-001", "SR-002"],
                       subject="src/app/mul.py", context="")
    assert j.verdict == "none"
    j = backend.choose("Which one?", ["multiply numbers", "export orders"],
                       subject="x", context="multiply two numbers")
    assert j.verdict == "multiply numbers"
    j = backend.ask("Does this diff serve SR-004?", "diff", subject="SR-004",
                    action="ownership")
    assert (j.verdict, j.confidence) == ("unsure", 0.0)
