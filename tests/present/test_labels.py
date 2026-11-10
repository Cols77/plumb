"""Every surface that states a confirmed record says who confirmed it: you, you (relayed), a
judge with its model and score ("judge-approved (auto-jev, jev-1.13, 0.96)", SR-251), with the
"self-recorded message" label (R8 B, R13 Q4). One label path
(``iaso.present.cards.confirmed_label``); one test per surface."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from present_helpers import FEAT1, INT1, SR1, SR2, fake_capture, write_all

from iaso import api, cli
from iaso.api import open_core
from iaso.contracts import Target

SELF = "self-recorded message"
CASES = [("owner", "", "confirmed by you"),
         ("agent-relayed", "", "confirmed by you (relayed)"),
         ("auto-jev", "", "judge-approved (auto-jev, jev-1.13, 0.96)"),
         ("auto-model", "", "judge-approved (auto-model, haiku, 0.8)"),
         ("agent-relayed", SELF, f"confirmed by you (relayed), {SELF}")]
IDS = ["owner", "agent-relayed", "auto-jev", "auto-model", "self-recorded"]
AUTO = {"auto-jev": {"score": 0.96, "model_version": "jev-1.13"},
        "auto-model": {"model": "haiku", "confidence": 0.8}}


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    write_all(repo, write_record, SR1, SR2, INT1, FEAT1)
    open_core(repo).add_link("SR-002", "derives_from", Target(record="INT-001"))
    return repo


def _confirmed(monkeypatch, by: str, extra: str) -> None:
    """SR-002 and INT-001 confirmed by ``by``; CAPTURE (another lane) labels them."""
    real = api.Core.status

    def status(self, ids=None):
        out = dict(real(self, ids))
        for record_id in ("SR-002", "INT-001"):
            if record_id in out:
                out[record_id] = dataclasses.replace(out[record_id], confirmation="confirmed",
                                                     approved_by=by, auto=AUTO.get(by))
        return out

    monkeypatch.setattr(api.Core, "status", status)
    words = {"owner": "you", "agent-relayed": "you (relayed)", "auto-jev": "JEV",
             "auto-model": "auto-model"}[by]
    fake_capture(monkeypatch, confirmation_label=lambda core, record_id: (
        f"confirmed by {words}" + (f", {extra}" if extra else "")))


@pytest.mark.sr("SR-202")
@pytest.mark.parametrize(("by", "extra", "label"), CASES, ids=IDS)
def test_show_says_who_confirmed(records: Path, capsys, monkeypatch, by, extra,
                                 label) -> None:
    _confirmed(monkeypatch, by, extra)
    assert cli.main(["show", "--root", str(records), "SR-002"]) == 0
    assert capsys.readouterr().out.startswith(f"SR-002 (requirement, {label}) ")


@pytest.mark.sr("SR-202")
@pytest.mark.parametrize(("by", "extra", "label"), CASES, ids=IDS)
def test_explain_says_who_confirmed(records: Path, capsys, monkeypatch, by, extra,
                                    label) -> None:
    _confirmed(monkeypatch, by, extra)
    assert cli.main(["explain", "--root", str(records), "SR-002"]) == 0
    out = capsys.readouterr().out
    assert f'SR-002 "divide returns the quotient" ({label})' in out
    assert f'INT-001 "add multiply next to add" ({label})' in out
