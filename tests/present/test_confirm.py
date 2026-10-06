"""P5: /plumb confirm prepares a confirmation the owner's own words then give (sp5 6.3,
SR-065)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from present_helpers import (
    FEAT1,
    FEAT2,
    INT1,
    SR1,
    SR2,
    SR3,
    fake_capture,
    run_prompt,
    run_stop,
    touch,
    write_all,
)

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


def test_plain_words_put_records_in_stated_set_prepared(records: Path, capsys) -> None:
    """EX-1: plumb confirm the login thing prepares the match as a card in the stated set;
    it is not shown to the owner until the stop hook renders it (sp5 6.3)."""
    assert cli.main(["confirm", "--root", str(records), "the", "login", "thing"]) == 0
    out = capsys.readouterr().out
    assert '▸ Requirement  SR-010 "the login form checks the password"' in out
    assert "Logging in with a wrong password shows an error and keeps the user out." in out
    stated = _stated(records)
    assert stated["records"] == [{"id": "SR-010",
                                  "hash": open_core(records).index()["SR-010"].hash,
                                  "shown": False, "via": "confirm"}]


def test_relayed_ok_then_confirms_exactly_the_shown(records: Path, hook_input,
                                                    capsys) -> None:
    """The owner's next affirming prompt confirms exactly the carded records (R2), even
    after the stop hook of the confirm turn ran."""
    run_prompt(records, hook_input, "/plumb confirm the login thing")
    assert cli.main(["confirm", "--root", str(records), "the", "login", "thing"]) == 0
    message = run_stop(records, hook_input)["systemMessage"]  # no change this turn
    assert '▸ Requirement  SR-010 "the login form checks the password"' in message
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


# --- the confirm turn's stop hook is the one place the cards reach the owner ---------------


def _age(repo: Path) -> None:
    """Date the fixture's files a minute back: on Windows a file written just before the
    prompt can carry an mtime at or after the turn start, which the stop reads as a change."""
    import os
    import time

    then = time.time() - 60
    for path in repo.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            os.utime(path, (then, then))


def _card_heads(message: str) -> list[str]:
    return [line for line in message.splitlines() if line.startswith("▸ ")]


@pytest.mark.parametrize(("argv", "prompt", "expected"), [
    ([], "/plumb confirm", ["INT-001", "SR-001"]),
    (["the", "login", "thing"], "/plumb confirm the login thing", ["SR-010"]),
    (["SR-002"], "/plumb confirm SR-002", ["SR-002"]),
], ids=["no-words", "plain-words", "ids"])
def test_stop_renders_confirm_cards_and_marks_only_them_shown(
        records: Path, hook_input, capsys, argv, prompt, expected) -> None:
    """Every entry point of /plumb confirm: the stop hook of the turn shows each prepared
    record as a full intent card in the owner's summary, and only then marks it shown."""
    _age(records)
    run_prompt(records, hook_input, prompt)
    assert cli.main(["confirm", "--root", str(records), "--limit", "2", *argv]) == 0
    capsys.readouterr()
    assert not any(r["shown"] for r in _stated(records)["records"])
    message = run_stop(records, hook_input)["systemMessage"]
    heads = _card_heads(message)
    assert [h.split()[2] for h in heads] == expected
    shown = {r["id"] for r in _stated(records)["records"] if r["shown"]}
    assert shown == set(expected)


def test_stop_with_changes_renders_confirm_cards(records: Path, hook_input,
                                                 capsys) -> None:
    """A confirm turn that also changed files still shows the prepared cards."""
    run_prompt(records, hook_input, "/plumb confirm the login thing")
    assert cli.main(["confirm", "--root", str(records), "the", "login", "thing"]) == 0
    touch(records, ".plumb/requirements/SR-003.md")
    message = run_stop(records, hook_input)["systemMessage"]
    assert '▸ Requirement  SR-010 "the login form checks the password"' in message
    assert {r["id"]: r["shown"] for r in _stated(records)["records"]}["SR-010"] is True


def test_unrendered_confirm_record_is_not_relayed_on_a_bare_ok(records: Path, hook_input,
                                                               capsys) -> None:
    """Without the stop hook's rendering (no session stop ran), a bare "ok" relays
    nothing: the owner never saw the card (R2)."""
    run_prompt(records, hook_input, "/plumb confirm the login thing")
    assert cli.main(["confirm", "--root", str(records), "the", "login", "thing"]) == 0
    text = "ok"
    out = run_prompt(records, hook_input, text)
    assert "relay it only if the owner's words name it" in out
    with pytest.raises(approvals.Refused):
        approvals.relay(open_core(records), ["SR-010"], prompt=approvals.prompt_digest(text),
                        quote="ok")


def _fake_triage(records: Path, monkeypatch) -> list[dict]:
    from types import SimpleNamespace

    index = open_core(records).index()
    pinned = [{"id": i, "hash": index[i].hash} for i in ("SR-001", "SR-002")]
    items = tuple(SimpleNamespace(id=i, hash=index[i].hash, title=index[i].title)
                  for i in ("SR-001", "SR-002"))
    view = SimpleNamespace(available=True, low_risk=items, individual=(),
                           offer='plumb: approve the 2 records rated faithful to your words: '
                                 '"add", "divide"? say "ok" or see plumb triage')
    fake_capture(monkeypatch, triage=lambda core, ids: view,
                 stated_group=lambda v: {"group": "low-risk", "records": pinned})
    return pinned


@pytest.mark.parametrize("changes", [False, True], ids=["no-change", "with-change"])
def test_confirm_group_survives_the_stop_and_is_offered(records: Path, hook_input, capsys,
                                                        monkeypatch, changes) -> None:
    """R8 A, R13 Q2: the group plumb confirm pinned stays in the stated set through the
    turn's stop (with or without changes), its offer line is shown to the owner, and it
    is the only group (``plumb relay --group low-risk`` then finds exactly it)."""
    pinned = _fake_triage(records, monkeypatch)
    run_prompt(records, hook_input, "/plumb confirm")
    assert cli.main(["confirm", "--root", str(records)]) == 0
    capsys.readouterr()
    assert "groups" not in _stated(records)  # prepared, not yet offered
    if changes:
        touch(records, ".plumb/requirements/SR-002.md")
    message = run_stop(records, hook_input)["systemMessage"]
    assert "plumb: approve the 2 records rated faithful to your words" in message
    assert _stated(records)["groups"] == [{"group": "low-risk", "records": pinned}]


def test_blocked_stop_keeps_the_confirm_group_unoffered(records: Path, hook_input, capsys,
                                                        monkeypatch) -> None:
    """A blocked stop shows the owner nothing: the prepared group is kept for the turn's
    last stop but not relayable until then."""
    from present_helpers import FakeVerify

    _fake_triage(records, monkeypatch)
    run_prompt(records, hook_input, "/plumb confirm")
    assert cli.main(["confirm", "--root", str(records)]) == 0
    touch(records, ".plumb/requirements/SR-002.md")
    out = run_stop(records, hook_input, verify=FakeVerify(nodes=("tests/test_x.py::t",)))
    assert "reason" in out
    stated = _stated(records)
    assert "groups" not in stated and stated["confirm_groups"]
    assert not any(r["shown"] for r in stated["records"])


@pytest.mark.parametrize("changes", [False, True], ids=["no-change", "with-change"])
def test_card_off_pins_only_the_offer_the_owner_saw(records: Path, hook_input, capsys,
                                                    monkeypatch, changes) -> None:
    """R2 with ``present.card: off``, on both stop paths (no change and with changes): the
    group /plumb confirm prepared is still rendered (the owner asked for it) and so
    pinned; every pinned group's offer line is in the message the owner saw."""
    pinned = _fake_triage(records, monkeypatch)
    (records / ".plumb" / "config.yaml").write_text("present:\n  card: off\n", "utf-8")
    run_prompt(records, hook_input, "/plumb confirm")
    assert cli.main(["confirm", "--root", str(records)]) == 0
    capsys.readouterr()
    if changes:
        touch(records, ".plumb/requirements/SR-002.md")
    message = run_stop(records, hook_input)["systemMessage"]
    assert ('plumb: approve the 2 records rated faithful to your words: "add", "divide"? '
            'say "ok" or see plumb triage') in message.splitlines()
    assert _stated(records)["groups"] == [{"group": "low-risk", "records": pinned}]
