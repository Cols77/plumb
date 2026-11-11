"""BRIDGE B2: ``get_backend`` and the backends that remain (spec 8.2, INT-029).

The file keeps its name because records link to it; there is no heuristic backend any more.
With no judge configured, or one that cannot answer, judging raises an error naming the judge
and the cause; nothing rule-based answers in its place (SR-021, INT-011).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso.api import open_core
from iaso.contracts import JudgmentBackend, Link, LinkState, Pin, Target
from iaso.judgment import JudgmentUnavailable, get_backend

pytestmark = [pytest.mark.sr("SR-245"), pytest.mark.sr("SR-225")]

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


def _state(path: str) -> LinkState:
    link = Link(source="SR-001", index=0, kind="implemented_by", target=Target(path=path),
                pin=Pin("sha256:a", "sha256:b"))
    return LinkState(link=link, state="stale", moved="target")


def _set_backend(repo: Path, name: str) -> None:
    (repo / ".iaso" / "config.yaml").write_text(f"judgment:\n  backend: {name}\n",
                                                encoding="utf-8")


def test_no_judge_configured_raises_an_error_naming_the_setting(repo: Path) -> None:
    (repo / ".iaso" / "config.yaml").write_text("", encoding="utf-8")
    with pytest.raises(JudgmentUnavailable) as caught:
        get_backend(open_core(repo), hook=True)
    assert "judgment.backend" in str(caught.value)
    assert caught.value.judge == "no judge"


@pytest.mark.parametrize("name", ["heuristic", "oracle"])
def test_a_name_that_is_not_a_judge_raises_instead_of_falling_back(repo: Path,
                                                                  name: str) -> None:
    _set_backend(repo, name)
    with pytest.raises(JudgmentUnavailable) as caught:
        get_backend(open_core(repo), hook=True)
    assert name in str(caught.value) and "judgment.backend" in str(caught.value)


def test_jev_without_adapter_raises_naming_jev(repo: Path, monkeypatch) -> None:
    import sys

    _set_backend(repo, "jev")
    monkeypatch.setitem(sys.modules, "iaso.judgment.jev", None)
    with pytest.raises(JudgmentUnavailable) as caught:
        get_backend(open_core(repo), hook=True)
    assert caught.value.judge == "JEV"


def test_disabled_backend_is_unsure(repo: Path, sr004) -> None:
    _set_backend(repo, "disabled")
    backend = get_backend(open_core(repo), hook=False)
    assert backend.name == "disabled"
    assert isinstance(backend, JudgmentBackend)
    [j] = backend.intent_change("instead SR-004 changes", [sr004])
    assert (j.verdict, j.tier) == ("unsure", "escalate-llm")
    [j] = backend.drift_triage([_state("a.py")], {"SR-001#0": ("a", "b")})
    assert (j.verdict, j.tier) == ("unsure", "escalate-llm")


def test_fake_backend_returns_canned_answers(repo: Path, sr004, monkeypatch) -> None:
    import iaso.judgment as judgment

    _set_backend(repo, "fake")
    monkeypatch.setitem(judgment.FAKE_ANSWERS, ("intent-change", "SR-004"), ("change", 0.97))
    backend = get_backend(open_core(repo), hook=True)
    [j] = backend.intent_change("anything", [sr004])
    assert (j.verdict, j.confidence, j.tier, j.backend) == ("change", 0.97, "accept", "fake")


def test_unavailable_backend_raises_the_error_on_every_call(repo: Path, sr004) -> None:
    from iaso.judgment import optional_backend

    (repo / ".iaso" / "config.yaml").write_text("", encoding="utf-8")
    backend = optional_backend(open_core(repo), hook=True)
    assert backend.name == "unavailable"
    with pytest.raises(JudgmentUnavailable):
        backend.intent_change("anything", [sr004])
    with pytest.raises(JudgmentUnavailable):
        backend.contradiction("anything", sr004)


def test_the_heuristic_module_is_gone() -> None:
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("iaso.judgment.heuristic")
