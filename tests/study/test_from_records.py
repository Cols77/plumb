"""A study built from the records and traced to them (SR-360; DEC-335, DEC-336): ``iaso study
gather`` collects the records on the topic, ``iaso study add --records`` keeps them with
their hashes, a changed record marks the study out of date and the band offers a rewrite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mod.helpers import DIGEST, KEY, run_mod
from understand.test_intent_loop import SESSION

from iaso import study
from iaso.api import open_core
from iaso.browser.service import BrowserService
from iaso.study import cli

pytestmark = pytest.mark.sr("SR-360")

MERGES = """---
id: SR-901
title: A merge is held until the owner confirms its records
statement: The merge check holds a merge that touches unconfirmed records.
examples:
- id: EX-1
  given: a branch changes an unconfirmed record
  when: it is merged
  then: the merge is held
links: []
---
"""
HOLD = """---
id: DEC-901
title: Should a held merge wait for the owner?
question: Should a held merge wait for the owner?
chosen: it waits for the owner
alternatives:
- it lands anyway
links:
- kind: decides
  to: SR-901
---
"""


def _study(repo: Path, *argv: str) -> int:
    return cli.run("study", [*argv, "--root", str(repo), "--session", SESSION])


def _gather(repo: Path, capsys: pytest.CaptureFixture, topic: str) -> dict[str, Any]:
    capsys.readouterr()
    assert _study(repo, "gather", topic, "--json") == 0
    return json.loads(capsys.readouterr().out)


def _written(repo: Path, tmp_path: Path, title: str, records: list[str]) -> str:
    """Asked for, accepted with diagrams, written from ``records``."""
    assert _study(repo, "propose", "--title", title, "--why", "the owner asked",
                  "--depth", "diagrams", "--asked") == 0
    slug = next(s["slug"] for s in study.studies(repo) if s["status"] == "idea")
    study.choose(repo, slug, "diagrams")
    body = tmp_path / "body.md"
    body.write_text("A merge waits for the owner.\n", encoding="utf-8")
    assert _study(repo, "add", slug, "--file", str(body), "--records", *records) == 0
    return slug


@pytest.fixture
def merges(repo: Path, write_record: Any) -> Path:
    write_record(repo, MERGES)
    write_record(repo, HOLD)
    return repo


def test_ex1_written_from_the_gathered_records_and_lists_them(
        merges: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    found = _gather(merges, capsys, "how merges are held")
    ids = [r["id"] for r in found["records"]]
    assert ids[0] == "SR-901" and "DEC-901" in ids     # the decisions on it come with it
    sr = found["records"][0]
    assert sr["examples"] == ["given a branch changes an unconfirmed record, when it is merged,"
                              " then the merge is held"]
    assert sr["hash"] == open_core(merges).index()["SR-901"].hash
    slug = _written(merges, tmp_path, "How merges are held", ids)
    held = study.get(merges, slug)
    assert [r["id"] for r in held["records"]] == ids
    assert held["records"][0]["hash"] == sr["hash"]
    assert "SR-901" in held["body"]          # the study lists the records it was written from


def test_ex2_a_reworded_requirement_marks_it_out_of_date_and_the_band_offers_a_refresh(
        merges: Path, tmp_path: Path, write_record: Any, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    from types import SimpleNamespace

    from iaso.understand.hooks import on_prompt

    slug = _written(merges, tmp_path, "How merges are held", ["SR-901", "DEC-901"])
    assert study.out_of_date(merges, open_core(merges).index()) == []
    write_record(merges, MERGES.replace("holds a merge", "keeps back a merge"))
    assert study.out_of_date(merges, open_core(merges).index()) == [slug]
    [shown] = BrowserService(merges).studies()["studies"]
    assert shown["changed"] == "A merge is held until the owner confirms its records"
    assert study.get(merges, slug)["status"] == "new"      # nothing rewritten on its own
    assert on_prompt(SimpleNamespace(root=merges, session_id=SESSION), None, {}) == []
    # the owner's yes in the band: the agent is told to rewrite it at the same depth
    assert run_mod(monkeypatch, capsys, merges, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, answer, _ = run_mod(monkeypatch, capsys, merges, "study", "--study", slug,
                              "--refresh", "yes", stdin={"key": KEY})
    assert code == 0 and answer["refresh"] == "asked"
    [line] = on_prompt(SimpleNamespace(root=merges, session_id=SESSION), None, {})
    assert "rewrite the study 'How merges are held' at depth diagrams" in line
    assert f"iaso study gather {slug}" in line and "--records" in line
    body = tmp_path / "again.md"
    body.write_text("A merge is kept back until the owner says yes.\n", encoding="utf-8")
    assert _study(merges, "add", slug, "--file", str(body), "--records", "SR-901") == 0
    again = study.get(merges, slug)
    assert (again["status"], again["depth"], again["changed"]) == ("new", "diagrams", "")
    assert study.out_of_date(merges, open_core(merges).index()) == []


def test_ex2_not_now_leaves_it_marked_and_rewrites_nothing(
        merges: Path, tmp_path: Path, write_record: Any, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    slug = _written(merges, tmp_path, "How merges are held", ["SR-901"])
    write_record(merges, MERGES.replace("holds a merge", "keeps back a merge"))
    study.out_of_date(merges, open_core(merges).index())
    assert run_mod(monkeypatch, capsys, merges, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, answer, _ = run_mod(monkeypatch, capsys, merges, "study", "--study", slug,
                              "--refresh", "no", stdin={"key": KEY})
    assert code == 0 and answer["refresh"] == "no"
    held = study.get(merges, slug)
    assert held["changed"] and held["body"].strip().startswith("A merge waits for the owner.")
    assert study.accepted_lines(merges) == []


def test_ex3_a_topic_no_record_covers_says_so(repo: Path, tmp_path: Path,
                                             capsys: pytest.CaptureFixture) -> None:
    found = _gather(repo, capsys, "how the coffee machine descales")
    assert found["records"] == [] and "no record covers" in found["line"]
    capsys.readouterr()
    assert _study(repo, "gather", "how the coffee machine descales") == 0
    assert "no record covers" in capsys.readouterr().out
    slug = _written(repo, tmp_path, "How the coffee machine descales", [])
    held = study.get(repo, slug)
    assert held["records"] == [] and "No record in iaso covers this topic" in held["body"]


def test_ex3_a_covered_topic_without_records_is_refused(
        merges: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """EX-3 is gather's finding: a forgotten --records on a covered topic writes no false
    'no record covers it'."""
    with pytest.raises(AssertionError):
        _written(merges, tmp_path, "How merges are held", [])
    assert "pass --records" in capsys.readouterr().err
    [held] = study.studies(merges)
    assert held["status"] == "accepted" and "No record in iaso" not in held["body"]


def test_ex2_a_failing_out_of_date_check_keeps_the_accepted_lines(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The out-of-date check failing never drops what the agent is told (SR-294 EX-8)."""
    from types import SimpleNamespace

    from iaso.understand.hooks import on_prompt

    study.choose(repo, study.propose(repo, title="How merges are held", why="asked",
                                     depth="md", loop="", step="", asked=True), "md")

    def broken(*_: Any) -> list[str]:
        raise OSError("the study file is not writable")

    monkeypatch.setattr(study, "out_of_date", broken)
    lines = on_prompt(SimpleNamespace(root=repo, session_id=SESSION), open_core(repo), {})
    assert any("accepted the study idea 'How merges are held'" in line for line in lines)
