"""K5: owner approvals, agent-relayed approvals and the self-approval guard (spec 5.6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import approvals, cli
from plumb.api import open_core
from plumb.normalize import sha256_text

pytestmark = pytest.mark.sr("SR-005")

SR1 = "---\nid: SR-001\ntitle: Links pin both ends\nstatement: s1\n---\n"
SR2 = "---\nid: SR-002\ntitle: Hashes ignore format\nstatement: s2\n---\n"
INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\n---\n"


@pytest.fixture
def setup(repo: Path, write_record) -> Path:
    for text in (SR1, SR2, INT):
        write_record(repo, text)
    return repo


def log_prompt(root: Path, text: str, at: str = "2026-10-06T03:00:00Z",
               session: str = "s1") -> str:
    digest = approvals.prompt_digest(text)
    prompts = root / ".plumb" / "session" / "prompts.jsonl"
    prompts.parent.mkdir(parents=True, exist_ok=True)
    with prompts.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"digest": digest, "session": session, "at": at,
                                 "text": text, "via": "hook"}) + "\n")
    return digest


def state_set(root: Path, ids: list[str], at: str = "2026-10-06T02:59:00Z") -> None:
    index = open_core(root).index()
    stated = root / ".plumb" / "session" / "stated.json"
    stated.parent.mkdir(parents=True, exist_ok=True)
    stated.write_text(json.dumps({"at": at, "session": "s1", "reply_after_prompt": None,
                                  "records": [{"id": i, "hash": index[i].hash} for i in ids]}),
                      encoding="utf-8")


def _confirmation(root: Path, record_id: str) -> str:
    return open_core(root).status([record_id])[record_id].confirmation


def test_approve_refused_under_marker(setup: Path, monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    with pytest.raises(approvals.Refused):
        approvals.approve(open_core(setup), ["SR-001"])
    with pytest.raises(approvals.Refused):
        approvals.revoke(open_core(setup), ["SR-001"])
    root = ["--root", str(setup)]
    assert cli.main(["approve", "SR-001", *root]) == 3
    assert cli.main(["approve", "--proposed", *root]) == 3
    assert cli.main(["revoke", "SR-001", *root]) == 3
    assert "refused" in capsys.readouterr().err
    assert list(open_core(setup).log_read("events")) == []


def test_approve_proposed_pins_all_listed(setup: Path,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    root = ["--root", str(setup)]
    assert cli.main(["approve", "--proposed", *root]) == 0  # y/N answered in the terminal
    out = capsys.readouterr().out
    assert "SR-001" in out and "INT-001" in out
    entries = list(open_core(setup).log_read("events", kinds=["approval"]))
    assert len(entries) == 1
    pinned = {r["id"]: r["hash"] for r in entries[0].payload["records"]}
    index = open_core(setup).index()
    assert pinned == {i: index[i].hash for i in ("INT-001", "SR-001", "SR-002")}
    assert entries[0].payload["by"] == "owner" and entries[0].marker == "none"
    assert all(_confirmation(setup, i) == "confirmed" for i in pinned)
    assert cli.main(["approve", "SR-404", *root]) == 1


def test_relay_accepts_affirming_quote_from_logged_prompt(
        setup: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    state_set(setup, ["SR-001", "INT-001"])
    digest = log_prompt(setup, "Looks right to me, ok go on with the links.")
    approvals.relay(open_core(setup), ["SR-001", "INT-001"], prompt=digest[7:19],
                    quote="ok go on")
    assert _confirmation(setup, "SR-001") == "confirmed"
    assert _confirmation(setup, "INT-001") == "confirmed"
    assert open_core(setup).status(["SR-001"])["SR-001"].approved_by == "agent-relayed"


def test_relay_records_quote_and_prompt_digest(setup: Path) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, "yes, that read-back is right")
    approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="yes, that read-back")
    entry = list(open_core(setup).log_read("events", kinds=["approval"]))[0]
    payload = entry.payload
    assert payload["by"] == "agent-relayed"
    assert payload["prompt_digest"] == digest
    assert payload["quote"] == "yes, that read-back"
    assert payload["quote_digest"] == sha256_text("yes, that read-back")
    assert payload["affirmation"] == "yes"
    assert payload["stated_set"] == ["SR-001"]
    assert payload["records"] == [{"id": "SR-001",
                                   "hash": open_core(setup).index()["SR-001"].hash}]


def test_relay_rejects_quote_not_in_prompt(setup: Path) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, "hmm, not sure yet")
    with pytest.raises(approvals.Refused, match="verbatim"):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="ok")
    assert list(open_core(setup).log_read("events")) == []


def test_relay_rejects_unknown_or_short_digest(setup: Path) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, "ok")
    with pytest.raises(approvals.Refused):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest[7:15], quote="ok")
    with pytest.raises(approvals.Refused):
        approvals.relay(open_core(setup), ["SR-001"], prompt="sha256:" + "0" * 64, quote="ok")


def test_relay_rejects_quote_without_affirmation(setup: Path) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, "please book a meeting tomorrow")
    with pytest.raises(approvals.Refused, match="affirm"):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="book a meeting")
    # a substring of a longer word is not an affirmation ("token" holds "ok")
    digest = log_prompt(setup, "the token expired")
    with pytest.raises(approvals.Refused, match="affirm"):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="the token")


def test_relay_rejects_record_outside_stated_set_unless_named(setup: Path) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, "ok, go on")
    with pytest.raises(approvals.Refused, match="SR-002"):
        approvals.relay(open_core(setup), ["SR-002"], prompt=digest, quote="ok, go on")
    digest = log_prompt(setup, "SR-002 is approved too")
    approvals.relay(open_core(setup), ["SR-002"], prompt=digest, quote="SR-002 is approved")
    assert _confirmation(setup, "SR-002") == "confirmed"


def test_relay_requires_naming_records_the_reply_did_not_show(setup: Path) -> None:
    """A record cut from the summary (``shown: false``) is confirmed only when named."""
    index = open_core(setup).index()
    stated = setup / ".plumb" / "session" / "stated.json"
    stated.parent.mkdir(parents=True, exist_ok=True)
    stated.write_text(json.dumps({"at": "2026-10-06T02:59:00Z", "session": "s1",
                                  "reply_after_prompt": None, "records": [
                                      {"id": "SR-001", "hash": index["SR-001"].hash,
                                       "shown": True},
                                      {"id": "SR-002", "hash": index["SR-002"].hash,
                                       "shown": False}]}), encoding="utf-8")
    digest = log_prompt(setup, "ok")
    with pytest.raises(approvals.Refused, match="SR-002 was not shown in full"):
        approvals.relay(open_core(setup), ["SR-001", "SR-002"], prompt=digest, quote="ok")
    assert _confirmation(setup, "SR-001") == "proposed"  # nothing was written
    approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="ok")
    assert _confirmation(setup, "SR-001") == "confirmed"
    digest = log_prompt(setup, "SR-002 ok too", at="2026-10-06T03:00:01Z")
    approvals.relay(open_core(setup), ["SR-002"], prompt=digest, quote="SR-002 ok")
    assert _confirmation(setup, "SR-002") == "confirmed"


def test_relay_rejects_stated_set_written_after_prompt(setup: Path) -> None:
    digest = log_prompt(setup, "ok", at="2026-10-06T03:00:00Z")
    state_set(setup, ["SR-001"], at="2026-10-06T03:05:00Z")
    with pytest.raises(approvals.Refused):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="ok")


def test_relay_writes_prompt_event_before_approval(setup: Path) -> None:
    state_set(setup, ["SR-001", "SR-002"])
    digest = log_prompt(setup, "ok, both fine", at="2026-10-06T03:01:02Z")
    approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="ok")
    approvals.relay(open_core(setup), ["SR-002"], prompt=digest, quote="ok")
    entries = list(open_core(setup).log_read("events"))
    assert [e.kind for e in entries] == ["prompt", "approval", "approval"]
    assert entries[0].payload == {"digest": digest, "session": "s1",
                                  "at": "2026-10-06T03:01:02Z"}
    assert "text" not in entries[0].payload


def test_no_approval_from_non_affirming_prompt(setup: Path) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, "carry on with the tests")
    with pytest.raises(approvals.Refused):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="carry on")
    assert _confirmation(setup, "SR-001") == "proposed"


def test_relay_revoke_needs_quote_but_no_affirmation(setup: Path) -> None:
    approvals.approve(open_core(setup), ["SR-001"])
    digest = log_prompt(setup, "actually SR-001 is wrong, take it back")
    approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="SR-001 is wrong",
                    revoke=True)
    assert _confirmation(setup, "SR-001") == "proposed"
    entry = list(open_core(setup).log_read("events", kinds=["revocation"]))[0]
    assert entry.payload["by"] == "agent-relayed"


def test_relay_cli(setup: Path, monkeypatch: pytest.MonkeyPatch,
                   capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, "lgtm")
    root = ["--root", str(setup)]
    assert cli.main(["relay", "SR-001", "--prompt", digest, "--quote", "nope", *root]) == 3
    assert cli.main(["relay", "SR-001", "--prompt", digest, "--quote", "lgtm", *root]) == 0
    assert _confirmation(setup, "SR-001") == "confirmed"


@pytest.mark.parametrize("prompt, quote", [
    ("the build looks broken, please fix SR-001 tests", "ok"),
    ("I saw that yesterday, fix it", "yes"),
    ("SR-001 is still unconfirmed", "confirm"),
    ("the build looks broken", "oks bro"),
])
def test_relay_rejects_quote_cut_from_inside_a_word(setup: Path, prompt: str,
                                                    quote: str) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, prompt)
    with pytest.raises(approvals.Refused, match="verbatim"):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote=quote)
    assert list(open_core(setup).log_read("events")) == []
    assert _confirmation(setup, "SR-001") != "confirmed"


def test_relay_accepts_whole_word_quote_with_edge_punctuation(setup: Path) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, "Fine. ok, go ahead!")
    approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="ok,")
    assert _confirmation(setup, "SR-001") == "confirmed"


@pytest.mark.parametrize("prompt, quote", [
    ("no, do not approve SR-001 yet", "approve SR-001"),
    ("SR-001 is not ok yet", "SR-001 is not ok"),
    ("SR-001 is not ok yet", "ok"),
    ("Don't approve SR-001 until the tests pass.", "approve SR-001"),
    ("wait, SR-001 ok later", "SR-001 ok"),
    ("I never said SR-001 was approved", "approved"),
    ("I don’t think SR-001 is ok", "SR-001 is ok"),
])
def test_relay_rejects_negated_affirmation(setup: Path, prompt: str, quote: str) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, prompt)
    with pytest.raises(approvals.Refused, match="negat"):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote=quote)
    assert list(open_core(setup).log_read("events")) == []
    assert _confirmation(setup, "SR-001") != "confirmed"


@pytest.mark.parametrize("prompt, quote", [
    ("is SR-001 ok?", "SR-001 ok"),
    ("Thanks. Should I approve SR-001? Let me think.", "approve SR-001"),
])
def test_relay_rejects_question(setup: Path, prompt: str, quote: str) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, prompt)
    with pytest.raises(approvals.Refused, match="question"):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote=quote)
    assert list(open_core(setup).log_read("events")) == []


@pytest.mark.parametrize("prompt, quote", [
    ("Is the build green? Yes, approve SR-001.", "approve SR-001"),
    ("No objections, approve SR-001.", "approve SR-001"),
])
def test_relay_accepts_affirmation_outside_negation_and_question(setup: Path, prompt: str,
                                                                 quote: str) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, prompt)
    approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote=quote)
    assert _confirmation(setup, "SR-001") == "confirmed"


@pytest.mark.parametrize("prompt, quote", [
    ("Not that one. ok for SR-001", "ok for SR-001"),
    ("ok for SR-001, but do not touch the docs", "ok for SR-001"),
])
def test_relay_refuses_beside_an_objection_it_cannot_place(setup: Path, prompt: str,
                                                           quote: str) -> None:
    """An objection or change clause that names no record (by ID or in plain words) may be
    about any record the owner was shown: the ok confirms nothing (R2; audit round 3)."""
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, prompt)
    with pytest.raises(approvals.Refused, match="object"):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote=quote)
    assert _confirmation(setup, "SR-001") == "proposed"


def test_relay_revoke_accepts_negated_quote(setup: Path) -> None:
    state_set(setup, ["SR-001"])
    digest = log_prompt(setup, "yes, approve SR-001")
    approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="approve SR-001")
    digest = log_prompt(setup, "no, do not approve SR-001 after all",
                        at="2026-10-06T03:05:00Z")
    approvals.relay(open_core(setup), ["SR-001"], prompt=digest,
                    quote="do not approve SR-001", revoke=True)
    assert _confirmation(setup, "SR-001") != "confirmed"


@pytest.mark.sr("SR-028")
def test_relay_confirms_trace_exempt_only_when_the_quote_names_it(setup: Path) -> None:
    (setup / ".plumb" / "config.yaml").write_text('trace:\n  exempt: ["src/gen/*"]\n', "utf-8")
    core = open_core(setup)
    digest = log_prompt(setup, "ok, go on")
    with pytest.raises(approvals.Refused, match="does not name the exemption"):
        approvals.relay(core, [], prompt=digest, quote="ok", exempt=True)
    assert approvals.approved_exempt(open_core(setup)) == set()
    digest = log_prompt(setup, "ok, exempt src/gen/* from requirements",
                        at="2026-10-06T03:01:00Z")
    entry = approvals.relay(open_core(setup), [], prompt=digest,
                            quote="ok, exempt src/gen/*", exempt=True)
    assert entry.payload["exempt"] == ["src/gen/*"] and entry.payload["records"] == []
    assert approvals.approved_exempt(open_core(setup)) == {"src/gen/*"}


@pytest.mark.sr("SR-028")
def test_approval_records_the_ends_a_requirement_owns(setup: Path) -> None:
    from plumb.contracts import Target

    (setup / "src").mkdir()
    (setup / "src" / "a.py").write_text("x = 1\n", "utf-8")
    open_core(setup).add_link("SR-001", "implemented_by", Target(path="src/a.py"))
    entry = approvals.approve(open_core(setup), ["SR-001", "INT-001"])
    items = {r["id"]: r for r in entry.payload["records"]}
    assert items["SR-001"]["ends"] == ["implemented_by src/a.py"]
    assert "ends" not in items["INT-001"]


# -- an ok confirms only what the owner's words affirm (R2; concept 6.6) --------------------

MIXED = "SR-001 is ok but INT-001 is wrong, use floats"


def test_relay_ok_naming_records_confirms_only_those(setup: Path, monkeypatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    """The owner's words name SR-001 as ok and INT-001 as wrong: relaying every stated ID,
    with the named quote or a bare "ok" cut from it, is refused; SR-001 alone is confirmed."""
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    state_set(setup, ["SR-001", "SR-002", "INT-001"])
    digest = log_prompt(setup, MIXED)
    for quote in ("SR-001 is ok", "ok"):
        with pytest.raises(approvals.Refused, match="INT-001"):
            approvals.relay(open_core(setup), ["INT-001", "SR-001", "SR-002"],
                            prompt=digest, quote=quote)
    root = ["--root", str(setup)]
    assert cli.main(["relay", "INT-001", "SR-001", "SR-002", "--prompt", digest, "--quote",
                     "SR-001 is ok", *root]) == 3
    assert "relay only SR-001" in capsys.readouterr().err
    # not objected to, but not named by the ok either
    with pytest.raises(approvals.Refused, match="SR-002"):
        approvals.relay(open_core(setup), ["SR-001", "SR-002"], prompt=digest, quote="ok")
    assert list(open_core(setup).log_read("events")) == []
    assert cli.main(["relay", "SR-001", "--prompt", digest, "--quote", "SR-001 is ok",
                     *root]) == 0
    assert _confirmation(setup, "SR-001") == "confirmed"
    assert _confirmation(setup, "INT-001") == "proposed"


@pytest.mark.parametrize("prompt, quote", [
    ("yes I know SR-001 is wrong, rewrite it", "yes"),
    ("ok. SR-001, SR-002 are wrong", "ok"),
    ("ok except SR-001", "ok"),
    ("SR-002 ok, but SR-001 should change", "SR-002 ok"),
])
def test_relay_refuses_a_record_the_prompt_objects_to(setup: Path, prompt: str,
                                                      quote: str) -> None:
    state_set(setup, ["SR-001", "SR-002"])
    digest = log_prompt(setup, prompt)
    with pytest.raises(approvals.Refused, match="object"):
        approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote=quote)
    assert _confirmation(setup, "SR-001") == "proposed"


def test_relay_after_an_earlier_identical_ok(setup: Path) -> None:
    """R13 Q2: the owner's "ok" resolves to the prompt just sent, not to the first prompt
    with the same words (the prompt log keeps every session's prompts)."""
    state_set(setup, ["SR-001"], at="2026-10-06T02:59:00Z")
    digest = log_prompt(setup, "ok", at="2026-10-06T03:00:00Z", session="cap1")
    approvals.relay(open_core(setup), ["SR-001"], prompt=digest, quote="ok")
    state_set(setup, ["SR-002", "INT-001"], at="2026-10-06T03:10:00Z")
    again = log_prompt(setup, "ok", at="2026-10-06T03:11:00Z", session="cap2")
    assert again == digest
    approvals.relay(open_core(setup), ["SR-002", "INT-001"], prompt=digest[7:19], quote="ok")
    assert _confirmation(setup, "SR-002") == _confirmation(setup, "INT-001") == "confirmed"


def test_turn_start_relay_line_and_relay_follow_the_owners_words(
        setup: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI-only fallback: ``plumb turn start`` logs the owner's message and suggests the
    relay of the named records only; that suggestion is what ``plumb relay`` accepts."""
    import io

    state_set(setup, ["SR-001", "SR-002", "INT-001"], at="2000-01-01T00:00:00Z")
    monkeypatch.setattr("sys.stdin", io.StringIO(MIXED))
    root = ["--root", str(setup)]
    assert cli.main(["turn", "start", "--session", "s1", *root]) == 0
    out = capsys.readouterr().out
    [line] = [x for x in out.splitlines() if "awaiting confirmation" in x]
    assert "run plumb relay SR-001 --prompt" in line
    assert "objects to or asks to change INT-001" in line
    digest = approvals.prompt_digest(MIXED)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "cli")
    assert cli.main(["relay", "SR-001", "SR-002", "INT-001", "--prompt", digest[7:19],
                     "--quote", "ok", *root]) == 3
    assert cli.main(["relay", "SR-001", "--prompt", digest[7:19], "--quote", "SR-001 is ok",
                     *root]) == 0
    assert _confirmation(setup, "SR-001") == "confirmed"
    assert _confirmation(setup, "INT-001") == "proposed"
