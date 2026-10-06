"""CAPTURE C6: triage groups proposed records by faithfulness (R8 A, R13 Q2; sp2 8.1,
SR-040)."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import (
    agent_shell_setup,
    event_kinds,
    log_prompt,
    record_text,
    run,
    write_stated,
)

from plumb.api import open_core
from plumb.capture.triage import offer_line, stated_group, triage

pytestmark = pytest.mark.sr("SR-040")


def _prompt(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def faithful_intent(n: int) -> str:
    """An INT whose quote is verbatim in the owner's hook-logged prompt (``logged``)."""
    return record_text(f"INT-0{n}", f"multiply number {n}",
                       quote=f"add multiply number {n} next to add",
                       readback=f"add multiply number {n} next to add",
                       will=[f"multiply number {n}"],
                       prompt=_prompt(f"add multiply number {n} next to add"))


@pytest.fixture(autouse=True)
def logged(repo: Path) -> None:
    """The owner's prompts the INTs of these tests quote, logged by the prompt hook."""
    for n in range(10, 30):
        log_prompt(repo, f"add multiply number {n} next to add", at="2026-10-06T00:00:00Z")
    log_prompt(repo, "export to CSV", at="2026-10-06T00:00:00Z")


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, faithful_intent(17))
    write_record(repo, record_text("DEC-001", "floats?", question="floats too?",
                                   chosen="integers only", alternatives=["floats"],
                                   matters=True,
                                   links=[{"kind": "derives_from", "to": "INT-017"}]))
    write_record(repo, record_text("INT-018", "export redesign", quote="export to CSV",
                                   readback="rebuild every exporter with a plugin system",
                                   wont=["no PDF"], prompt=_prompt("export to CSV")))
    write_record(repo, record_text("FEAT-001", "calculator"))
    return repo


def ids(items) -> list[str]:
    return [i.id for i in items]


def test_groups_low_risk_first(project: Path, capsys) -> None:
    view = triage(open_core(project))
    assert view.available and view.backend == "heuristic"
    assert ids(view.low_risk) == ["INT-017"]
    assert "DEC-001" in ids(view.individual)
    assert run(project, "triage") == 0
    out = capsys.readouterr().out.splitlines()
    first = next(n for n, line in enumerate(out) if "INT-017" in line)
    later = next(n for n, line in enumerate(out) if "DEC-001" in line)
    assert first < later
    assert "triage" in event_kinds(project)


def test_exclusions_shown_individually(project: Path, write_record) -> None:
    from plumb.approvals import approve

    write_record(project, faithful_intent(19))
    approve(open_core(project), ["INT-019"])
    path = project / ".plumb" / "intents" / "INT-019.md"
    path.write_text(path.read_text(encoding="utf-8").replace("number 19 next",
                                                             "number 19 just next"),
                    encoding="utf-8")
    write_record(project, record_text("INT-020", "a set", quote="the set", readback="the set",
                                      mode="escalated", members=["INT-017"]))
    view = triage(open_core(project))
    why = {i.id: i.excluded for i in view.individual}
    assert why["DEC-001"] == "a decision that matters"
    assert why["INT-017"] == "a member of the escalated spec INT-020"
    assert why["INT-019"] == "an edit of a record you confirmed before"
    assert why["FEAT-001"] == "no owner words to compare"
    assert why["INT-018"] is None  # riskier on its own merits
    assert {i.id: i.rating for i in view.individual}["INT-018"] == "riskier"
    assert view.low_risk == ()


def test_approve_low_risk_exact_hashes_owner_only(project: Path, monkeypatch,
                                                  capsys) -> None:
    hashes = {i.id: i.hash for i in triage(open_core(project)).low_risk}
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "session-1")
    assert run(project, "triage", "--approve", "low-risk") == 3
    assert "approval" not in event_kinds(project)
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    assert run(project, "triage", "--approve", "low-risk") == 0  # the owner's terminal
    [entry] = list(open_core(project).log_read("events", ["approval"]))
    assert {r["id"]: r["hash"] for r in entry.payload["records"]} == hashes
    assert entry.payload["by"] == "owner"
    assert entry.payload["triage"]["group"] == "low-risk"
    assert open_core(project).status(["INT-017"])["INT-017"].confirmation == "confirmed"
    assert open_core(project).status(["DEC-001"])["DEC-001"].confirmation == "proposed"


def test_approve_low_risk_refused_without_terminal(project: Path, monkeypatch,
                                                   capsys) -> None:
    agent_shell_setup(monkeypatch)
    assert run(project, "triage", "--approve", "low-risk") == 3
    assert "not an interactive terminal" in capsys.readouterr().err
    assert "approval" not in event_kinds(project)


def test_relay_group_needs_group_in_stated_set(project: Path, write_record,
                                               monkeypatch) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "session-1")
    write_record(project, faithful_intent(21))
    view = triage(open_core(project))
    assert ids(view.low_risk) == ["INT-017", "INT-021"]
    digest = log_prompt(project, "ok")
    write_stated(project, [])  # the reply before offered no group
    assert run(project, "relay", "--group", "low-risk", "--prompt", digest, "--quote",
               "ok") == 3
    write_stated(project, [], groups=[stated_group(view)])
    assert run(project, "relay", "--group", "low-risk", "--prompt", digest, "--quote",
               "ok") == 0
    [entry] = list(open_core(project).log_read("events", ["approval"]))
    assert entry.payload["by"] == "agent-relayed"
    assert {r["id"]: r["hash"] for r in entry.payload["records"]} == {
        i.id: i.hash for i in view.low_risk}
    statuses = open_core(project).status()
    assert statuses["INT-017"].confirmation == statuses["INT-021"].confirmation == "confirmed"
    assert statuses["INT-018"].confirmation == "proposed"


def test_no_backend_reports_no_judgments(project: Path, capsys) -> None:
    (project / ".plumb" / "config.yaml").write_text("judgment:\n  backend: disabled\n",
                                                   encoding="utf-8")
    view = triage(open_core(project))
    assert not view.available and view.low_risk == ()
    assert set(ids(view.individual)) == {"INT-017", "INT-018", "DEC-001", "FEAT-001"}
    assert run(project, "triage") == 0
    assert "no judgments available" in capsys.readouterr().out


def test_offer_line_names_five_then_more(repo: Path, write_record) -> None:
    for n in range(11, 18):
        write_record(repo, faithful_intent(n))
    view = triage(open_core(repo))
    assert len(view.low_risk) == 7
    line = offer_line(view.low_risk)
    assert line == view.offer
    assert line.startswith("plumb: approve the 7 records rated faithful to your words: "
                           "\"multiply number 11\" (INT-011), ")
    assert "(INT-015)" in line and "(INT-016)" not in line
    assert line.endswith("+2 more (see plumb triage)? say \"ok\" or see plumb triage")
    assert len(stated_group(view)["records"]) == 7  # the ok pins the whole list


def test_relay_group_refused_when_the_ok_names_or_objects_to_records(
        project: Path, write_record, monkeypatch, capsys) -> None:
    """R2 / R13 Q2: the owner's ok to the offer approves exactly the pinned list; an ok
    that objects to one of them, or names records instead, does not confirm the group."""
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "session-1")
    write_record(project, faithful_intent(21))
    view = triage(open_core(project))
    write_stated(project, [], groups=[stated_group(view)])
    digest = log_prompt(project, "ok but INT-021 is wrong")
    assert run(project, "relay", "--group", "low-risk", "--prompt", digest, "--quote",
               "ok") == 3
    assert "INT-021" in capsys.readouterr().err
    digest = log_prompt(project, "ok INT-017", at="2026-10-06T10:00:01Z")
    assert run(project, "relay", "--group", "low-risk", "--prompt", digest, "--quote",
               "ok INT-017") == 3
    assert "approval" not in event_kinds(project)


def test_relay_group_after_an_earlier_identical_ok(project: Path, write_record,
                                                   monkeypatch) -> None:
    """The owner's "ok" to this offer resolves to the prompt just sent, even when an earlier
    session logged the same words before an earlier reply."""
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "session-1")
    log_prompt(project, "ok", at="2026-10-06T08:00:00Z", session="cap1")
    write_record(project, faithful_intent(21))
    view = triage(open_core(project))
    write_stated(project, [], at="2026-10-06T09:59:00Z", groups=[stated_group(view)])
    digest = log_prompt(project, "ok", at="2026-10-06T10:00:00Z", session="cap2")
    assert run(project, "relay", "--group", "low-risk", "--prompt", digest[7:19], "--quote",
               "ok") == 0
    assert open_core(project).status(["INT-021"])["INT-021"].confirmation == "confirmed"
