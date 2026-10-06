"""The clone-collision scenario the IDS tests share (sp6 14 item 3, in small).

``origin`` and its ``clone`` both create SR-002 from the same base (SR-001, INT-001,
FEAT-001). The clone's SR-002 is "export csv" (approved by the clone's owner, with a test
marker, a body wikilink and an example reference in a decision); origin's SR-002 is "relay
checks", referenced by origin's DEC-002. Origin then merges the clone's ``main``: git stops
on the add/add of ``.plumb/requirements/SR-002.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ids.gitrepo import clone, commit_all, make_repo, run_git
from plumb.api import open_core
from plumb.contracts import Target


@dataclass
class Scenario:
    origin: Path
    clone: Path
    clone_commits: list[str]
    clone_log: str


def _requirement(root: Path, title: str, statement: str, body: str = "") -> str:
    core = open_core(root)
    record = core.write_record("requirement", {
        "title": title, "feature": "FEAT-001", "statement": statement,
        "examples": [{"id": "EX-1", "given": "g", "when": "w", "then": statement}]}, body)
    core.add_link(record.id, "derives_from", Target(record="INT-001"))
    return record.id


def build(tmp_path: Path, *, approve: bool = True, merge: bool = True,
          trailer_in_message: bool = True) -> Scenario:
    origin = make_repo(tmp_path / "origin")
    core = open_core(origin)
    core.write_record("intent", {"title": "csv and relays", "quote": "q", "readback": "r"},
                      "")
    core.write_record("feature", {"title": "io", "description": "d",
                                  "requirements": ["SR-001"]}, "")
    _requirement(origin, "add returns the sum", "add(a, b) is a + b")
    commit_all(origin, "base\n\nSR: SR-001")

    other = clone(origin, tmp_path / "clone")
    sr = _requirement(other, "export csv", "rows export as csv", "See [[SR-002]] too.\n")
    assert sr == "SR-002"
    ccore = open_core(other)
    dec = ccore.write_record("decision", {
        "title": "comma separator", "question": "which separator?", "chosen": "comma",
        "rationale": "SR-002/EX-1 shows commas"}, "Decides [[SR-002|export csv]].\n")
    ccore.add_link(dec.id, "decides", Target(record="SR-002"))
    tests = other / "tests"
    tests.mkdir()
    (tests / "test_export.py").write_text(
        'import pytest\n\n\n@pytest.mark.sr("SR-002")\ndef test_export():\n'
        '    assert "SR-002" != "data"\n', encoding="utf-8")
    if approve:
        from plumb import approvals

        approvals.approve(open_core(other), ["SR-002"])
    first = commit_all(other, "export csv\n\nSR: SR-002")
    (tests / "test_export.py").write_text(
        (tests / "test_export.py").read_text(encoding="utf-8") + "\n\n"
        '@pytest.mark.sr("SR-002")\ndef test_export_header():\n    assert True\n',
        encoding="utf-8")
    second = commit_all(other, "export header\n\nSR: SR-002")
    open_core(other).add_link("SR-002", "verified_by", Target(path="tests/test_export.py"))
    third = commit_all(other, "link the export tests\n\nSR: SR-002")
    clone_log = run_git(other, "log", "--format=%H %B", "main")

    sr = _requirement(origin, "relay checks", "relays are checked")
    assert sr == "SR-002"
    ocore = open_core(origin)
    odec = ocore.write_record("decision", {"title": "relay decision", "question": "q?",
                                           "chosen": "check"}, "", record_id="DEC-009")
    ocore.add_link(odec.id, "decides", Target(record="SR-002"))
    (origin / "tests").mkdir()
    (origin / "tests" / "test_relay.py").write_text(
        'import pytest\n\n\n@pytest.mark.sr("SR-002")\ndef test_relay():\n    assert True\n',
        encoding="utf-8")
    ocore.add_link("SR-002", "verified_by", Target(path="tests/test_relay.py"))
    commit_all(origin, "relay checks\n\nSR: SR-002")

    if merge:
        run_git(origin, "fetch", "-q", str(other), "main:incoming")
        result = run_git(origin, "merge", "--no-edit", "incoming", check=False)
        assert "CONFLICT" in result, result
        if trailer_in_message:
            msg = Path(run_git(origin, "rev-parse", "--git-path", "MERGE_MSG").strip())
            msg = msg if msg.is_absolute() else origin / msg
            msg.write_text(msg.read_text(encoding="utf-8") + "\nSR: SR-002\n",
                           encoding="utf-8")
    return Scenario(origin, other, [first, second, third], clone_log)
