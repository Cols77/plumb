"""K6: the merge boundary, ``plumb validate --merge <base>`` (spec 5.11, R1, R2)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from logutil import legacy_relay, tamper

from plumb import approvals, cli
from plumb.api import open_core
from plumb.contracts import Target
from plumb.merge import merge_check

pytestmark = pytest.mark.sr("SR-260")

INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\nreadback: Ground the work.\n---\n"
SR1 = """---
id: SR-001
title: Links pin both ends
statement: Both ends are pinned.
examples:
  - {id: EX-1, given: a link, when: an end moves, then: it is stale}
---
"""
SR2 = "---\nid: SR-002\ntitle: Other\nstatement: Something else.\n---\n"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout


def _commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


@pytest.fixture
def base(repo: Path, write_record) -> tuple[Path, str]:
    for text in (INT, SR1, SR2):
        write_record(repo, text)
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    return repo, _commit(repo, "base")


def _repin(root: Path) -> None:
    """The reviewed link ends pinned again: a stale link of a touched requirement holds the
    merge with exit 1 (sp3 5, tests/merge/test_gates.py), before what these tests check."""
    from plumb.links import repin

    repin(open_core(root), all_stale=True)


def _check(root: Path, sha: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    _repin(root)
    code = merge_check(open_core(root), sha, as_json=False)
    return code, capsys.readouterr().out


def test_merge_refuses_unconfirmed_touched_requirement(base, capsys) -> None:
    root, sha = base
    path = root / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Both ends", "Each end"),
                    encoding="utf-8")
    _commit(root, "edit SR-001")
    code, out = _check(root, sha, capsys)
    assert code == 4
    assert "SR-001" in out and "INT-001" in out and "SR-002" not in out
    assert "plumb: merge waits for 2 records to be approved" in out   # counted (SR-267)
    assert "given a link" in out


def test_merge_touch_via_implemented_by_end(base, capsys) -> None:
    root, sha = base
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")  # uncommitted
    code, out = _check(root, sha, capsys)
    assert code == 4
    assert "touched requirements: SR-001" in out


def test_merge_touch_via_sr_trailer(base, capsys) -> None:
    root, sha = base
    (root / "docs").mkdir()
    (root / "docs" / "notes.md").write_text("n\n", encoding="utf-8")  # exempt from claims
    _commit(root, "notes\n\nSR: SR-002")
    code, out = _check(root, sha, capsys)
    assert code == 4
    assert "touched requirements: SR-002" in out


def test_merge_passes_after_approval(base, capsys) -> None:
    root, sha = base
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    approvals.approve(open_core(root), ["SR-001", "INT-001"])
    code, out = _check(root, sha, capsys)
    assert code == 0, out
    assert cli.main(["validate", "--merge", sha, "--root", str(root)]) == 0
    assert cli.main(["validate", "--merge", "no-such-ref", "--root", str(root)]) == 2


def test_merge_with_nothing_touched_passes(base, capsys) -> None:
    root, sha = base
    code, out = _check(root, sha, capsys)
    assert code == 0
    assert "touched requirements: none" in out


def test_merge_lists_approvals_in_range_with_relayed_marked(base, capsys) -> None:
    root, sha = base
    approvals.approve(open_core(root), ["INT-001"])
    prompts = root / ".plumb" / "session" / "prompts.jsonl"
    prompts.parent.mkdir(parents=True, exist_ok=True)
    text = "SR-001 looks good, approved"
    digest = approvals.prompt_digest(text)
    prompts.write_text(json.dumps({"digest": digest, "session": "s", "at": "t",
                                   "text": text, "via": "hook"}) + "\n", encoding="utf-8")
    legacy_relay(root, ["SR-001"], digest, "SR-001 looks good, approved")
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    code, out = _check(root, sha, capsys)
    assert code == 0, out
    section = out[out.index("approvals in range"):]
    assert "owner" in section and "INT-001" in section
    assert "AGENT-RELAYED" in section and digest[:19] in section
    assert "SR-001 looks good, approved" in section
    data_code = merge_check(open_core(root), sha, as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert data_code == 0
    assert [a["by"] for a in data["glance"]] == ["agent-relayed", "owner"]


def test_merge_requires_deciding_matters_dec(base, capsys, write_record) -> None:
    root, sha = base
    write_record(root, "---\nid: DEC-001\ntitle: Deny rules\nquestion: q\nchosen: a\n"
                 "matters: true\n---\n")
    open_core(root).add_link("DEC-001", "decides", Target(record="SR-001"))
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    approvals.approve(open_core(root), ["SR-001", "INT-001"])
    code, out = _check(root, sha, capsys)
    assert code == 4 and "DEC-001" in out
    approvals.approve(open_core(root), ["DEC-001"])
    assert _check(root, sha, capsys)[0] == 0


def test_merge_detects_rewritten_log_line(base, capsys) -> None:
    root, _ = base
    approvals.approve(open_core(root), ["INT-001"])
    sha = _commit(root, "approval")
    name = tamper(root, "events", -1, lambda t: t.replace("INT-001", "SR-002"))
    code, out = _check(root, sha, capsys)
    assert code == 1
    assert "log integrity" in out and name in out


def test_merge_reports_fidelity_and_verification_unavailable(base, capsys, monkeypatch) -> None:
    root, sha = base
    monkeypatch.setitem(sys.modules, "plumb.judgment.fidelity", None)
    monkeypatch.setitem(sys.modules, "plumb.verify", None)
    _, out = _check(root, sha, capsys)
    assert "fidelity: unavailable" in out
    assert "verification: unavailable" in out


def test_validate_merge_json_is_one_document(base, capsys) -> None:
    root, sha = base
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    _repin(root)
    assert cli.main(["validate", "--merge", sha, "--json", "--root", str(root)]) == 4
    data = json.loads(capsys.readouterr().out)
    assert data["merge"]["awaiting"][0]["id"] == "SR-001"
    assert data["validate"]["errors"] == []


def test_merge_log_integrity_reads_merge_base_not_base_tip(base, capsys) -> None:
    root, _ = base
    git(root, "branch", "trunk")
    git(root, "checkout", "-q", "-b", "feat")
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    _commit(root, "feat change")
    git(root, "checkout", "-q", "trunk")
    approvals.approve(open_core(root), ["SR-002"])  # main receives a log entry meanwhile
    _commit(root, "approval on trunk")
    git(root, "checkout", "-q", "feat")
    code, out = _check(root, "trunk", capsys)
    assert "log integrity: ok" in out, out
    assert code == 4  # SR-001 touched and unconfirmed, but no false tamper alarm
    assert "SR-002" not in out[out.index("approvals in range"):]


def test_merge_log_integrity_still_catches_edit_of_merge_base_line(base, capsys) -> None:
    root, _ = base
    approvals.approve(open_core(root), ["INT-001"])
    _commit(root, "approval")
    git(root, "branch", "trunk")
    git(root, "checkout", "-q", "-b", "feat")
    tamper(root, "events", -1, lambda t: t.replace("INT-001", "SR-002"))
    _commit(root, "tamper")
    git(root, "checkout", "-q", "trunk")
    (root / "notes.txt").write_text("n\n", encoding="utf-8")
    _commit(root, "trunk moves on")
    git(root, "checkout", "-q", "feat")
    code, out = _check(root, "trunk", capsys)
    assert code == 1
    assert "log integrity: FAILED" in out


@pytest.mark.sr("SR-200")
def test_merge_puts_untraced_changes_to_the_owner(base, capsys) -> None:
    """A changed source path no requirement owns escaped the read-back: the merge waits."""
    root, sha = base
    (root / "src" / "mul.py").write_text("def mul(a, b):\n    return a * b\n", "utf-8")
    _commit(root, "add mul")
    code, out = _check(root, sha, capsys)
    assert code == 4, out
    assert "touched requirements: none" in out
    assert "untraced changes (no requirement owns them): src/mul.py" in out
    assert "confirmation: every touched requirement is confirmed" not in out
    waits = out[out.index("merge waits for approval:"):]
    assert "untraced src/mul.py" in waits and "trace.exempt" in waits
    assert merge_check(open_core(root), sha, as_json=True) == 4
    assert json.loads(capsys.readouterr().out)["untraced"] == ["src/mul.py"]


@pytest.mark.sr("SR-200")
def test_merge_untraced_change_cleared_by_a_link_or_an_exemption(base, capsys) -> None:
    root, sha = base
    (root / "src" / "mul.py").write_text("x = 1\n", "utf-8")
    (root / "src" / "gen.py").write_text("x = 1\n", "utf-8")
    (root / ".plumb" / "config.yaml").write_text("trace:\n  exempt: [src/gen.py]\n", "utf-8")
    open_core(root).add_link("SR-002", "implemented_by", Target(path="src/mul.py"))
    approvals.approve(open_core(root), ["SR-002", "INT-001"], exempt=True)
    code, out = _check(root, sha, capsys)
    assert code == 0, out
    assert "untraced" not in out
    assert "trace.exempt src/gen.py" in out[out.index("approvals in range"):]




# -- a requirement widened by a link, or a path exempted, in the range (SR-028) -----------


@pytest.fixture
def confirmed_base(base) -> tuple[Path, str]:
    """SR-001 and INT-001 confirmed at the merge base, which also holds src/z.py; z.py then
    changes with no requirement owning it."""
    root, _ = base
    (root / "src" / "z.py").write_text("def wipe():\n    return None\n", "utf-8")
    approvals.approve(open_core(root), ["SR-001", "INT-001"])
    sha = _commit(root, "confirmed base")
    (root / "src" / "z.py").write_text("def wipe():\n    return 'all user data'\n", "utf-8")
    return root, sha


def _untraced_waits(root: Path, sha: str, capsys) -> None:
    code, out = _check(root, sha, capsys)
    assert code == 4, out
    assert "untraced changes (no requirement owns them): src/z.py" in out


@pytest.mark.sr("SR-260")
def test_link_command_widening_a_confirmed_requirement_waits_for_the_owner(
        confirmed_base, capsys, monkeypatch) -> None:
    root, sha = confirmed_base
    _untraced_waits(root, sha, capsys)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    assert cli.main(["link", "SR-001", "implemented_by", "src/z.py", "--root",
                     str(root)]) == 0
    capsys.readouterr()
    assert open_core(root).status(["SR-001"])["SR-001"].confirmation == "confirmed"
    code, out = _check(root, sha, capsys)
    assert code == 4, out
    assert "untraced" not in out
    assert "SR-001 (extended)" in out
    assert "new link in this range: implemented_by src/z.py (now owned by SR-001)" in out
    assert "confirmation: every touched requirement is confirmed" not in out
    assert merge_check(open_core(root), sha, as_json=True) == 4
    data = json.loads(capsys.readouterr().out)
    assert [{k: a[k] for k in ("id", "state", "new_ends")} for a in data["awaiting"]] == [
        {"id": "SR-001", "state": "extended", "new_ends": ["implemented_by src/z.py"]}]
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    approvals.approve(open_core(root), ["SR-001"])  # the owner confirms the wider scope
    code, out = _check(root, sha, capsys)
    assert code == 0, out


@pytest.mark.sr("SR-260")
def test_frontmatter_edit_adding_a_link_waits_for_the_owner(confirmed_base, capsys) -> None:
    root, sha = confirmed_base
    path = root / ".plumb" / "requirements" / "SR-001.md"
    text = path.read_text(encoding="utf-8")
    head, _, rest = text.partition("links:\n")
    path.write_text(head + "links:\n- kind: implemented_by\n  path: src/z.py\n" + rest,
                    encoding="utf-8")
    assert open_core(root).status(["SR-001"])["SR-001"].confirmation == "confirmed"
    code, out = _check(root, sha, capsys)
    assert code == 4, out
    assert "new link in this range: implemented_by src/z.py (now owned by SR-001)" in out


@pytest.mark.sr("SR-260", "SR-288")
def test_trace_exempt_added_in_range_waits_for_the_owner(confirmed_base, capsys,
                                                         monkeypatch) -> None:
    root, sha = confirmed_base
    (root / ".plumb" / "config.yaml").write_text('trace:\n  exempt: ["src/**"]\n', "utf-8")
    code, out = _check(root, sha, capsys)
    assert code == 4, out
    assert "untraced changes (no requirement owns them): src/z.py" in out
    assert "trace.exempt src/**: added in this range" in out
    assert "nothing can approve a new trace.exempt glob yet" in out           # SR-288 EX-1
    assert "remove it to merge" in out and "plumb approve" not in out
    assert cli.main(["approve", "--exempt", "--root", str(root)]) == 3        # SR-288 EX-2
    assert "approve no longer exists" in capsys.readouterr().err
    assert _check(root, sha, capsys)[0] == 4
    assert merge_check(open_core(root), sha, as_json=True) == 4
    assert json.loads(capsys.readouterr().out)["new_exempt"] == ["src/**"]
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    with pytest.raises(approvals.Refused):                    # owner only
        approvals.approve(open_core(root), [], exempt=True)
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    approvals.approve(open_core(root), [], exempt=True)
    capsys.readouterr()
    code, out = _check(root, sha, capsys)
    assert code == 0, out
    assert "owner trace.exempt src/**" in out


@pytest.mark.sr("SR-260")
def test_narrowing_the_layout_in_the_range_hides_no_change(confirmed_base, capsys) -> None:
    root, sha = confirmed_base
    (root / ".plumb" / "config.yaml").write_text("test_dirs: [src, tests]\n", "utf-8")
    _untraced_waits(root, sha, capsys)


@pytest.mark.sr("SR-200")
def test_merge_puts_untraced_flat_layout_and_root_files_to_the_owner(repo, capsys) -> None:
    """No source_dirs configured: a flat package and a root module are source too."""
    (repo / "mypkg").mkdir()
    (repo / "mypkg" / "core.py").write_text("x = 1\n", "utf-8")
    sha = _commit(repo, "flat base")
    (repo / "mypkg" / "extra.py").write_text("def power(a):\n    return a ** 2\n", "utf-8")
    (repo / "tool.py").write_text("print('tool')\n", "utf-8")
    (repo / "NOTES.txt").write_text("notes\n", "utf-8")
    code, out = _check(repo, sha, capsys)
    assert code == 4, out
    assert "untraced changes (no requirement owns them): mypkg/extra.py, tool.py" in out
