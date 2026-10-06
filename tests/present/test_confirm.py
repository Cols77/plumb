"""P5: /plumb confirm prepares a confirmation the owner's own words then give (sp5 6.3,
SR-065)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from present_helpers import FEAT1, FEAT2, INT1, SR1, SR2, SR3, run_prompt, run_stop, write_all

from plumb import approvals, cli
from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-065")

LOGIN = """---
id: SR-010
title: the login form checks the password
feature: FEAT-002
statement: Logging in with a wrong password shows an error and keeps the user out.
examples:
- id: EX-1
  given: a wrong password
  when: the user logs in
  then: an error is shown
---
"""


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    return write_all(repo, write_record, SR1, SR2, SR3, INT1, FEAT1, FEAT2, LOGIN)


def _approvals(repo: Path) -> list:
    return [e for e in open_core(repo).events() if e.kind == "approval"]


def _stated(repo: Path) -> dict:
    return json.loads((repo / ".plumb" / "session" / "stated.json").read_text("utf-8"))


def test_confirm_writes_no_approval(records: Path, capsys) -> None:
    """EX-1, first half: whatever the words, no approval event is written."""
    for argv in ([], ["the", "login", "thing"], ["SR-001"]):
        assert cli.main(["confirm", "--root", str(records), *argv]) == 0
    assert _approvals(records) == []
    assert all(s.confirmation == "proposed" for s in open_core(records).status().values())
    assert "approves nothing" in capsys.readouterr().out


def test_plain_words_put_records_in_stated_set_shown(records: Path, capsys) -> None:
    """EX-1: plumb confirm the login thing shows the match as a card and states it."""
    assert cli.main(["confirm", "--root", str(records), "the", "login", "thing"]) == 0
    out = capsys.readouterr().out
    assert '▸ Requirement  SR-010 "the login form checks the password"' in out
    assert "Logging in with a wrong password shows an error and keeps the user out." in out
    stated = _stated(records)
    assert stated["records"] == [{"id": "SR-010",
                                  "hash": open_core(records).index()["SR-010"].hash,
                                  "shown": True, "via": "confirm"}]


def test_relayed_ok_then_confirms_exactly_the_shown(records: Path, hook_input,
                                                    capsys) -> None:
    """The owner's next affirming prompt confirms exactly the carded records (R2), even
    after the stop hook of the confirm turn ran."""
    run_prompt(records, hook_input, "/plumb confirm the login thing")
    assert cli.main(["confirm", "--root", str(records), "the", "login", "thing"]) == 0
    run_stop(records, hook_input)  # no change this turn: the stated set is kept
    text = "ok, that's right"
    out = run_prompt(records, hook_input, text)
    assert "plumb relay SR-010" in out
    approvals.relay(open_core(records), ["SR-010"], prompt=approvals.prompt_digest(text),
                    quote="ok")
    statuses = open_core(records).status()
    assert statuses["SR-010"].confirmation == "confirmed"
    assert statuses["SR-010"].approved_by == "agent-relayed"
    with pytest.raises(approvals.Refused):
        approvals.relay(open_core(records), ["SR-002"],
                        prompt=approvals.prompt_digest(text), quote="ok")


def test_ids_with_confirm_relay_directly(records: Path, hook_input, capsys) -> None:
    """EX-2: "/plumb confirm SR-002" names the ID and affirms: relayed at once."""
    text = "/plumb confirm SR-002"
    run_prompt(records, hook_input, text)
    assert cli.main(["confirm", "--root", str(records), "SR-002"]) == 0
    assert "relay them at once with plumb relay SR-002" in capsys.readouterr().out
    approvals.relay(open_core(records), ["SR-002"], prompt=approvals.prompt_digest(text),
                    quote=text)
    status = open_core(records).status(["SR-002"])["SR-002"]
    assert status.confirmation == "confirmed" and status.approved_by == "agent-relayed"


def test_no_words_shows_proposed_records_up_to_the_limit(records: Path, capsys) -> None:
    assert cli.main(["confirm", "--root", str(records), "--limit", "2"]) == 0
    out = capsys.readouterr().out
    assert out.count("▸ ") == 2
    assert "more await you, not shown" in out
    assert [r["id"] for r in _stated(records)["records"]] == ["INT-001", "SR-001"]
