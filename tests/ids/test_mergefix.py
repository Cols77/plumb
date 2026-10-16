"""IDS I5: ``plumb merge-fix`` renumbers the incoming record of a clone collision and
rewrites every reference the incoming side introduced, never history (sp6 5; SR-071).

The real-git tests run the shared clone scenario (``scenario.py``); the per-place tests of
5.3 run the pure rewrite functions on base / ours / theirs / merged texts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ids import scenario
from ids.gitrepo import record_text, run_git
from plumb import ids
from plumb.api import open_core
from plumb.ids import rewrite
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-257")

MAP = {"SR-070": "SR-081"}


def _status(root: Path) -> str:
    return run_git(root, "status", "--porcelain")


# --------------------------------------------------------------------------- real git


def test_clone_collision_renumbers_incoming(tmp_path: Path) -> None:
    s = scenario.build(tmp_path)
    core = open_core(s.origin)
    result = ids.merge_fix(core)
    assert result.remaining == ()
    [row] = result.renumbered
    assert (row["from"], row["title"]) == ("SR-002", "export csv")
    new = row["to"]
    assert new == "SR-003"  # the ref raised over every ID both sides hold, then reserved
    index = open_core(s.origin).index()
    assert index["SR-002"].title == "relay checks"
    assert index[new].title == "export csv"
    assert "[[" + new + "]]" in index[new].body
    dec = index["DEC-001"]
    assert dec.fields["rationale"] == f"{new}/EX-1 shows commas"
    assert f"[[{new}|export csv]]" in dec.body
    assert [lk.target.record for lk in dec.links if lk.kind == "decides"] == [new]
    marker = (s.origin / "tests" / "test_export.py").read_text(encoding="utf-8")
    assert marker.count(f'mark.sr("{new}")') == 2
    assert '"SR-002" != "data"' in marker  # a string that is not a marker is left alone
    states = open_core(s.origin).link_states([new, "DEC-001"])
    assert all(st.state == "current" for st in states), states
    assert ids.collisions(open_core(s.origin)) == ()


def test_our_side_reference_untouched(tmp_path: Path) -> None:
    s = scenario.build(tmp_path)
    ids.merge_fix(open_core(s.origin))
    index = open_core(s.origin).index()
    assert [lk.target.record for lk in index["DEC-009"].links] == ["SR-002"]
    relay = (s.origin / "tests" / "test_relay.py").read_text(encoding="utf-8")
    assert 'mark.sr("SR-002")' in relay


def test_history_unchanged(tmp_path: Path) -> None:
    s = scenario.build(tmp_path)
    ids.merge_fix(open_core(s.origin))
    assert run_git(s.origin, "log", "--format=%H %B", "incoming") == s.clone_log
    entry = [e for e in open_core(s.origin).events() if e.kind == "renumber"][0]
    assert sorted(entry.payload["commits"]) == sorted(s.clone_commits)


def test_rewrites_merge_msg_trailer(tmp_path: Path) -> None:
    s = scenario.build(tmp_path)
    [row] = ids.merge_fix(open_core(s.origin)).renumbered
    msg = Path(run_git(s.origin, "rev-parse", "--git-path", "MERGE_MSG").strip())
    msg = msg if msg.is_absolute() else s.origin / msg
    text = msg.read_text(encoding="utf-8")
    assert f"SR: {row['to']}" in text and "SR: SR-002" not in text


def test_stages_but_never_commits(tmp_path: Path) -> None:
    s = scenario.build(tmp_path)
    head = run_git(s.origin, "rev-parse", "HEAD").strip()
    result = ids.merge_fix(open_core(s.origin))
    assert run_git(s.origin, "rev-parse", "HEAD").strip() == head
    assert run_git(s.origin, "rev-parse", "-q", "--verify", "MERGE_HEAD").strip()
    assert run_git(s.origin, "ls-files", "-u").strip() == ""
    new_path = f".plumb/requirements/{result.renumbered[0]['to']}.md"
    assert new_path in result.staged
    staged = run_git(s.origin, "diff", "--cached", "--name-only").split()
    assert new_path in staged and "tests/test_export.py" in staged
    assert not [line for line in _status(s.origin).splitlines()
                if line[1] != " " and not line.startswith("??")]  # nothing left unstaged


def test_dry_run_writes_and_reserves_nothing(tmp_path: Path) -> None:
    s = scenario.build(tmp_path)
    before = _status(s.origin)
    ref = run_git(s.origin, "rev-parse", ids.REF).strip()
    files = {p: p.read_bytes() for p in (s.origin / ".plumb").rglob("*.md")}
    result = ids.merge_fix(open_core(s.origin), dry_run=True)
    assert result.dry_run and result.renumbered[0]["to"] == "SR-003"
    assert "would become SR-003" in result.lines[0]
    assert _status(s.origin) == before
    assert run_git(s.origin, "rev-parse", ids.REF).strip() == ref
    assert {p: p.read_bytes() for p in (s.origin / ".plumb").rglob("*.md")} == files


def test_second_run_is_a_no_op(tmp_path: Path) -> None:
    s = scenario.build(tmp_path)
    ids.merge_fix(open_core(s.origin))
    files = {p: p.read_bytes() for p in s.origin.rglob("*") if p.is_file()
             and ".git" not in p.parts}
    ref = run_git(s.origin, "rev-parse", ids.REF).strip()
    again = ids.merge_fix(open_core(s.origin))
    assert again.renumbered == () and again.remaining == ()
    assert "nothing to fix" in again.lines[0]
    assert run_git(s.origin, "rev-parse", ids.REF).strip() == ref
    assert {p: p.read_bytes() for p in s.origin.rglob("*") if p.is_file()
            and ".git" not in p.parts} == files


def test_pure_renumber_pins_repinned_other_stale_kept(tmp_path: Path) -> None:
    s = scenario.build(tmp_path, merge=False)
    # the clone also leaves one pin stale for its own reason: INT-001 edited after the pin
    core = open_core(s.clone)
    intent = core.index()["INT-001"]
    from plumb.capture.records import record_fields

    core.write_record("intent", {**record_fields(intent), "readback": "edited"}, "",
                      record_id="INT-001")
    from ids.gitrepo import commit_all

    commit_all(s.clone, "edit intent\n\nSR: SR-002")
    run_git(s.origin, "fetch", "-q", str(s.clone), "main:incoming")
    run_git(s.origin, "merge", "--no-edit", "incoming", check=False)
    result = ids.merge_fix(open_core(s.origin))
    new = result.renumbered[0]["to"]
    states = {(st.link.source, st.link.target.record): st.state
              for st in open_core(s.origin).link_states([new, "DEC-001"])}
    assert states[(new, "INT-001")] == "stale"           # moved for its own reason: kept
    assert states[("DEC-001", new)] == "current"         # only the ID changed: repinned


def test_duplicate_without_merge_renumbers_the_later_file(tmp_path: Path) -> None:
    from ids.gitrepo import commit_all, make_repo, write

    root = make_repo(tmp_path / "r")
    write(root, "SR-005", "first")
    commit_all(root, "first")
    path = root / ".plumb" / "requirements" / "SR-005-imported.md"
    path.write_text(record_text("SR-005", "second"), encoding="utf-8")
    commit_all(root, "second")
    result = ids.merge_fix(open_core(root))
    assert result.renumbered[0]["title"] == "second"
    index = open_core(root).index()
    assert index["SR-005"].title == "first" and index["SR-006"].title == "second"
    assert not path.exists()


def test_both_sides_add_tests_to_one_file(tmp_path: Path) -> None:
    from ids.gitrepo import commit_all, make_repo, write

    root = make_repo(tmp_path / "r")
    write(root, "SR-001", "base")
    shared = root / "tests" / "test_shared.py"
    shared.parent.mkdir()
    head = "import pytest\n\n\ndef test_a():\n    pass\n"
    tail = "\n\ndef test_b():\n    pass\n"
    shared.write_text(head + tail, encoding="utf-8")
    commit_all(root, "base")
    marked = '\n\n@pytest.mark.sr("SR-002")\ndef test_{}():\n    pass\n'
    run_git(root, "checkout", "-q", "-b", "side")
    write(root, "SR-002", "export csv")
    shared.write_text(head + tail + marked.format("export"), encoding="utf-8")
    commit_all(root, "export")
    run_git(root, "checkout", "-q", "main")
    write(root, "SR-002", "relay checks")
    shared.write_text(head + marked.format("relay") + tail, encoding="utf-8")
    commit_all(root, "relay")
    run_git(root, "merge", "--no-edit", "side", check=False)
    result = ids.merge_fix(open_core(root))
    assert [r["to"] for r in result.renumbered] == ["SR-003"]
    text = shared.read_text(encoding="utf-8")
    assert '@pytest.mark.sr("SR-002")\ndef test_relay' in text
    assert '@pytest.mark.sr("SR-003")\ndef test_export' in text
    assert "tests/test_shared.py" in result.staged


def test_from_ref_preview_names_the_coming_collision(tmp_path: Path) -> None:
    s = scenario.build(tmp_path, merge=False)
    run_git(s.origin, "fetch", "-q", str(s.clone), "main:incoming")
    result = ids.merge_fix(open_core(s.origin), from_ref="incoming")
    assert [c.id for c in result.remaining] == ["SR-002"]
    assert "export csv" in result.lines[0] and "relay checks" in result.lines[0]
    assert _status(s.origin) == ""


# --------------------------------------------------------------------------- the places


def _rec(record_id: str, title: str, body: str = "", **fields: object) -> str:
    return record_text(record_id, title, body=body, **fields)


def test_rewrites_links_to() -> None:
    base = _rec("DEC-001", "d")
    theirs = _rec("DEC-001", "d", links=[{"kind": "decides", "to": "SR-070"}])
    merged, count = rewrite.record(theirs, base, base, theirs, MAP)
    assert count == 1
    assert rewrite.parse(merged)[0]["links"] == [{"kind": "decides", "to": "SR-081"}]


def test_rewrites_feature_and_requirements() -> None:
    base_feat = _rec("FEAT-001", "f", requirements=["SR-001"])
    theirs_feat = _rec("FEAT-001", "f", requirements=["SR-001", "SR-070"])
    merged, count = rewrite.record(theirs_feat, base_feat, base_feat, theirs_feat, MAP)
    assert count == 1 and rewrite.parse(merged)[0]["requirements"] == ["SR-001", "SR-081"]
    theirs_sr = _rec("SR-071", "s", feature="FEAT-070")
    merged, count = rewrite.record(theirs_sr, None, None, theirs_sr, {"FEAT-070": "FEAT-081"})
    assert count == 1 and rewrite.parse(merged)[0]["feature"] == "FEAT-081"


def test_rewrites_members_supersedes_decides() -> None:
    base = _rec("INT-001", "i", members=["SR-001"])
    theirs = _rec("INT-001", "i", members=["SR-001", "SR-070"], supersedes="DEC-070",
                  decides=["SR-070"])
    merged, count = rewrite.record(theirs, base, base, theirs,
                                   {"SR-070": "SR-081", "DEC-070": "DEC-081"})
    data = rewrite.parse(merged)[0]
    assert count == 3
    assert data["members"] == ["SR-001", "SR-081"]
    assert data["supersedes"] == "DEC-081" and data["decides"] == ["SR-081"]


def test_rewrites_example_references() -> None:
    base = _rec("DEC-001", "d", rationale="none")
    theirs = _rec("DEC-001", "d", rationale="SR-070/EX-2 shows it", alternatives=[
        "as in SR-070/EX-1"])
    merged, count = rewrite.record(theirs, base, base, theirs, MAP)
    data = rewrite.parse(merged)[0]
    assert count == 2
    assert data["rationale"] == "SR-081/EX-2 shows it"
    assert data["alternatives"] == ["as in SR-081/EX-1"]


def test_rewrites_body_wikilinks() -> None:
    base = _rec("INT-001", "i", "Intro.\n")
    theirs = _rec("INT-001", "i", "Intro.\nSee [[SR-070]] and [[SR-070|export csv]].\n")
    merged, count = rewrite.record(theirs, base, base, theirs, MAP)
    assert count == 2
    assert "[[SR-081]] and [[SR-081|export csv]]" in rewrite.parse(merged)[1]


def test_rewrites_incoming_test_markers_only() -> None:
    base = "import pytest\n"
    ours = base + '\n@pytest.mark.sr("SR-070")\ndef test_ours():\n    pass\n'
    theirs = base + ('\n@pytest.mark.sr("SR-070")\ndef test_theirs():\n'
                     '    assert "SR-070"\n')
    merged = base + ('\n@pytest.mark.sr("SR-070")\ndef test_ours():\n    pass\n'
                     '\n@pytest.mark.sr("SR-070")\ndef test_theirs():\n'
                     '    assert "SR-070"\n')
    # the marker line is identical on both sides: it goes by the test it decorates
    out, count = rewrite.markers(merged, base, ours, theirs, MAP)
    assert count == 1
    assert '@pytest.mark.sr("SR-070")\ndef test_ours' in out
    assert '@pytest.mark.sr("SR-081")\ndef test_theirs' in out
    assert 'assert "SR-070"' in out  # a string that is not a marker is left alone
    theirs2 = base + "\npytestmark = pytest.mark.sr('SR-070')\n"
    out, count = rewrite.markers(theirs2, base, base, theirs2, MAP)
    assert count == 1 and "pytest.mark.sr('SR-081')" in out


def test_markers_same_test_name_on_both_sides_go_by_source() -> None:
    base = "import pytest\n"
    ours = base + '\n@pytest.mark.sr("SR-070")\ndef test_it():\n    assert relay()\n'
    theirs = base + '\n@pytest.mark.sr("SR-070")\ndef test_it():\n    assert export()\n'
    merged = ours + theirs[len(base):]
    out, count = rewrite.markers(merged, base, ours, theirs, MAP)
    assert count == 1
    assert '"SR-070")\ndef test_it():\n    assert relay()' in out
    assert '"SR-081")\ndef test_it():\n    assert export()' in out


def test_markers_on_classes_and_methods() -> None:
    base = "import pytest\n\n\nclass TestA:\n    def test_a(self):\n        pass\n"
    theirs = base + ('\n    @pytest.mark.sr("SR-070")\n    def test_b(self):\n        pass\n'
                     '\n\n@pytest.mark.sr("SR-070")\nclass TestC:\n    pass\n')
    ours = base.replace("class TestA:", '@pytest.mark.sr("SR-070")\nclass TestA:')
    merged = theirs.replace("class TestA:", '@pytest.mark.sr("SR-070")\nclass TestA:')
    out, count = rewrite.markers(merged, base, ours, theirs, MAP)
    assert count == 2
    assert '@pytest.mark.sr("SR-070")\nclass TestA:' in out
    assert '@pytest.mark.sr("SR-081")\n    def test_b' in out
    assert '@pytest.mark.sr("SR-081")\nclass TestC:' in out


def test_body_wikilink_line_added_on_both_sides_goes_by_place() -> None:
    base = _rec("INT-001", "i", "Intro.\n\n## Relays\n\n## Export\n")
    ours = _rec("INT-001", "i", "Intro.\n\n## Relays\nSee [[SR-070]].\n\n## Export\n")
    theirs = _rec("INT-001", "i", "Intro.\n\n## Relays\n\n## Export\nSee [[SR-070]].\n")
    merged = _rec("INT-001", "i",
                  "Intro.\n\n## Relays\nSee [[SR-070]].\n\n## Export\nSee [[SR-070]].\n")
    out, count = rewrite.record(merged, base, ours, theirs, MAP)
    assert count == 1
    body = rewrite.parse(out)[1]
    assert "## Relays\nSee [[SR-070]].\n\n## Export\nSee [[SR-081]].\n" in body


def test_rewrites_claims_baseline_nc() -> None:
    base = "require_trailer: true\nbaseline:\n- {commit: aaa, path: x.py, nc: NC-0001}\n"
    ours = base + "- {commit: bbb, path: y.py, nc: NC-0003}\n"
    theirs = base + "- {commit: ccc, path: z.py, nc: NC-0003}\n"
    merged = base + ("- {commit: bbb, path: y.py, nc: NC-0003}\n"
                     "- {commit: ccc, path: z.py, nc: NC-0003}\n")
    out, count = rewrite.claims(merged, base, ours, theirs, {"NC-0003": "NC-0004"})
    assert count == 1
    assert "{commit: bbb, path: y.py, nc: NC-0003}" in out
    assert "{commit: ccc, path: z.py, nc: NC-0004}" in out


def test_both_sides_reference_keeps_both() -> None:
    base = _rec("FEAT-001", "f", requirements=["SR-001"])
    ours = _rec("FEAT-001", "f", requirements=["SR-001", "SR-070"])
    theirs = ours
    merged, count = rewrite.record(ours, base, ours, theirs, MAP)
    assert count == 1
    assert rewrite.parse(merged)[0]["requirements"] == ["SR-001", "SR-070", "SR-081"]
    link = {"kind": "relates_to", "to": "SR-070"}
    base_l = _rec("SR-001", "s")
    both = _rec("SR-001", "s", links=[link])
    merged, count = rewrite.record(both, base_l, both, both, MAP)
    assert [lk["to"] for lk in rewrite.parse(merged)[0]["links"]] == ["SR-070", "SR-081"]


def test_trailers_rewrite_only_sr_lines() -> None:
    message = "Merge branch 'x'\n\nSR-070 is mentioned here\n\nSR: SR-001, SR-070\n"
    out, count = rewrite.trailers(message, MAP)
    assert count == 1
    assert "SR: SR-001, SR-081" in out and "SR-070 is mentioned here" in out


def test_renumber_entry_logged(tmp_path: Path) -> None:
    s = scenario.build(tmp_path)
    ids.merge_fix(open_core(s.origin))
    [entry] = [e for e in open_core(s.origin).events() if e.kind == "renumber"]
    payload = entry.payload
    assert (payload["from"], payload["to"], payload["kind"]) == ("SR-002", "SR-003",
                                                                 "requirement")
    assert payload["old_hash"] != payload["new_hash"]
    assert len(payload["approvals"]) == 1
    assert json.dumps(payload)  # plain JSON
    state = ids.state(PlumbPaths(s.origin))
    assert state.high["SR"] == 3
