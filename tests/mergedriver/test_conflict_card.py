"""D5: the conflict card and its advisory compatibility judgment (sp6 8.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mergedriver.mdhelpers import (
    OURS_STATEMENT,
    THEIRS_STATEMENT,
    conflicted,
    events,
    ex,
    iaso,
    record,
)
from iaso import cli
from iaso.api import open_core
from iaso.contracts import Judgment
from iaso.mergedriver import conflict_card, open_conflicts

pytestmark = pytest.mark.sr("SR-256")


def test_card_shows_both_versions_and_what_merged(repo: Path) -> None:
    """SR-076 EX-2: one card: both statements, what merged on its own, the choices."""
    conflicted(repo)
    core = open_core(repo)
    (conflict,) = open_conflicts(core)
    card = conflict_card(core, conflict)
    assert card[0] == "▸ Conflict IC-001 on \"relay checks\"   (awaits the owner's choice)"
    assert "SR-" not in " ".join(card)   # SR-267 EX-1: no record id
    assert card[1].split(None, 1) == ["main", OURS_STATEMENT]
    assert card[2].split(None, 1) == ["feat-x", THEIRS_STATEMENT]
    assert card[3] == "  Merged on their own: links +1 from feat-x"
    assert card[-1] == ("  Ask the owner with the question tool (main's, feat-x's, or combined); "
                        "never in prose")


def test_card_in_owner_terms_example_as_given_when_then(repo: Path) -> None:
    base = record(statement="s", examples=[ex(1), ex(2, "a cart", "it totals", "the sum")])
    ours = record(statement="s1", examples=[ex(1), ex(2, "a cart", "it totals", "rounded")])
    theirs = record(statement="s2", examples=[ex(1), ex(2, "a cart", "it totals", "exact")])
    conflicted(repo, base=base, ours=ours, theirs=theirs)
    core = open_core(repo)
    card = conflict_card(core, open_conflicts(core)[0])
    assert "  What it says:" in card and "  Example 2:" in card
    assert any(line.strip() == "feat-x   given a cart, when it totals, then exact"
               for line in card)
    assert not any("examples/" in line or "sha256" in line for line in card)


def test_no_backend_says_no_judgment_available(repo: Path) -> None:
    """SR-076 EX-5, SR-021 EX-1: no judge: the card says judging is unavailable and why, and
    choosing works the same."""
    conflicted(repo)
    core = open_core(repo)
    card = conflict_card(core, open_conflicts(core)[0])
    assert ("  Compatible? judging unavailable: no judge: judgment.backend is not set in "
            "the records folder's config.yaml; set it to jev") in card
    assert cli.main(["conflict", "choose", "IC-001", "--take", "theirs",
                     "--root", str(repo)]) == 0
    assert open_conflicts(open_core(repo)) == ()


class _FakeJev:
    name = "jev"
    version = "jev-test-1"

    def __init__(self) -> None:
        self.calls = 0

    def contradiction(self, prompt: str, record: object) -> Judgment:
        self.calls += 1
        return Judgment(action="intent_change", subject="SR-005", verdict="benign",
                        confidence=0.8, tier="accept", backend="jev:test", fingerprint="f",
                        reasons=("both can hold if a group is affirmed by name",),
                        probability=0.82)


def test_fake_jev_judgment_logged_once_per_pair(repo: Path) -> None:
    conflicted(repo)
    backend = _FakeJev()
    core = open_core(repo)
    conflict = open_conflicts(core)[0]
    first = conflict_card(core, conflict, backend=backend)
    second = conflict_card(open_core(repo), conflict, backend=backend)
    assert backend.calls == 1
    line = ("  Compatible? JEV: likely compatible (0.82): both can hold if a group is "
            "affirmed by name")
    assert line in first and line in second
    logged = [p for p in events(repo, "judgment") if p.get("subject") == "IC-001"]
    assert len(logged) == 1 and logged[0]["advisory"] is True


def test_show_ic_and_show_record(repo: Path) -> None:
    conflicted(repo)
    for ref in ("IC-001", "SR-005"):
        out = iaso(repo, "show", ref)
        assert out.returncode == 0, out.stderr
        assert "Conflict IC-001 on \"relay checks\"" in out.stdout
    listed = iaso(repo, "conflicts")
    assert listed.returncode == 0 and "Conflict IC-001" in listed.stdout


def test_review_shows_the_card(repo: Path) -> None:
    """SR-076 EX-2: /iaso review shows the conflict card in its merge section."""
    conflicted(repo)
    out = iaso(repo, "review")
    assert "intent conflicts wait for your choice (/iaso conflicts):" in out.stdout
    assert "Conflict IC-001 on \"relay checks\"" in out.stdout
