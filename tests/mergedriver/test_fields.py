"""D1: ``merge_texts`` field rules (sp6 7.3), pure: no repository."""

from __future__ import annotations

import pytest

from mergedriver.mdhelpers import Counter, ex, link, parse, record
from plumb.mergedriver import merge_texts
from plumb.model import record_hash, split_frontmatter

LABELS = ("main", "feat-x")


def merge(base: str, ours: str, theirs: str):
    return merge_texts(base, ours, theirs, labels=LABELS, reserve_ic=Counter())


def fm(result) -> dict:
    return parse(result.text)[0]


BASE_LINK = link("derives_from", to="INT-001", pin="a")


@pytest.mark.sr("SR-075")
def test_links_added_on_both_sides_union() -> None:
    """SR-075 EX-1: verified_by on one side, implemented_by on the other: both kept."""
    base = record(statement="s", links=[BASE_LINK])
    ours = record(statement="s", links=[BASE_LINK, link("verified_by", path="tests/t.py")])
    theirs = record(statement="s", links=[BASE_LINK, link("implemented_by", path="src/a.py")])
    result = merge(base, ours, theirs)
    assert result.exit == 0 and result.conflict is None
    kinds = [x["kind"] for x in fm(result)["links"]]
    assert kinds == ["derives_from", "verified_by", "implemented_by"]


@pytest.mark.sr("SR-075")
def test_link_removed_on_one_side_removed() -> None:
    extra = link("implemented_by", path="src/a.py")
    base = record(statement="s", links=[BASE_LINK, extra])
    ours = record(statement="s", links=[BASE_LINK])
    theirs = record(statement="s", links=[BASE_LINK, extra, link("verified_by", path="t.py")])
    result = merge(base, ours, theirs)
    assert [x.get("path") for x in fm(result)["links"]] == [None, "t.py"]


@pytest.mark.sr("SR-075")
def test_pin_divergence_keeps_ours_no_conflict() -> None:
    base = record(statement="s", links=[link("derives_from", to="INT-001", pin="a")])
    ours = record(statement="s2", links=[link("derives_from", to="INT-001", pin="b")])
    theirs = record(statement="s", links=[link("derives_from", to="INT-001", pin="c"),
                                          link("verified_by", path="t.py")])
    result = merge(base, ours, theirs)
    assert result.conflict is None
    links = fm(result)["links"]
    assert links[0]["pin"]["from"] == "sha256:b" and len(links) == 2


@pytest.mark.sr("SR-075")
def test_pin_changed_on_one_side_only_taken() -> None:
    base = record(statement="s", links=[link("derives_from", to="INT-001", pin="a")])
    ours = record(statement="s", links=[link("derives_from", to="INT-001", pin="a"),
                                        link("verified_by", path="t.py")])
    theirs = record(statement="s", links=[link("derives_from", to="INT-001", pin="c")])
    links = fm(merge(base, ours, theirs))["links"]
    assert links[0]["pin"]["from"] == "sha256:c" and len(links) == 2


@pytest.mark.sr("SR-075")
def test_title_change_and_new_example_merge() -> None:
    """SR-075 EX-2: a new title on one side, EX-4 added on the other: both, no conflict."""
    examples = [ex(1), ex(2), ex(3)]
    base = record(statement="s", examples=examples)
    ours = record(title="relay checks, scoped", statement="s", examples=examples)
    theirs = record(statement="s", examples=[*examples, ex(4, then="four")])
    result = merge(base, ours, theirs)
    data = fm(result)
    assert result.exit == 0 and "conflict" not in data
    assert data["title"] == "relay checks, scoped"
    assert [e["id"] for e in data["examples"]] == ["EX-1", "EX-2", "EX-3", "EX-4"]


@pytest.mark.sr("SR-075")
def test_independent_fields_merge() -> None:
    base = record(statement="s", domain="d")
    ours = record(statement="s2", domain="d")
    theirs = record(statement="s", domain="d2")
    data = fm(merge(base, ours, theirs))
    assert (data["statement"], data["domain"]) == ("s2", "d2")


@pytest.mark.sr("SR-075")
def test_string_lists_set_merge() -> None:
    base = record("INT-001", "i", will=["a", "b"], wont=["x"])
    ours = record("INT-001", "i", will=["a", "b", "c"], wont=["x"])
    theirs = record("INT-001", "i", will=["b", "d"], wont=["x"])
    result = merge(base, ours, theirs)
    assert fm(result)["will"] == ["b", "c", "d"] and result.conflict is None


@pytest.mark.sr("SR-076")
def test_same_item_rewritten_both_sides_conflicts() -> None:
    base = record("INT-001", "i", will=["a", "b"])
    ours = record("INT-001", "i", will=["a", "b1"])
    theirs = record("INT-001", "i", will=["a", "b2"])
    result = merge(base, ours, theirs)
    data = fm(result)
    assert result.conflict == "IC-001"
    assert data["will"] == ["a", "b1"]
    assert data["conflict"]["fields"]["will"]["theirs"] == ["a", "b2"]


@pytest.mark.sr("SR-075")
def test_examples_added_both_sides_kept() -> None:
    base = record(statement="s", examples=[ex(1)])
    ours = record(statement="s", examples=[ex(1), ex(2, then="ours")])
    theirs = record(statement="s", examples=[ex(1), ex(3, then="theirs")])
    data = fm(merge(base, ours, theirs))
    assert [e["id"] for e in data["examples"]] == ["EX-1", "EX-2", "EX-3"]


@pytest.mark.sr("SR-075")
def test_same_new_ex_number_renumbered_with_links() -> None:
    """SR-075 EX-3: both add EX-3: the incoming one becomes EX-4, its link follows."""
    base = record(statement="s", examples=[ex(1), ex(2)])
    ours = record(statement="s", examples=[ex(1), ex(2), ex(3, then="ours")],
                  links=[link("verified_by", path="tests/a.py", example="EX-3")])
    theirs = record(statement="s", examples=[ex(1), ex(2), ex(3, then="theirs")],
                    links=[link("verified_by", path="tests/b.py", example="EX-3")])
    result = merge(base, ours, theirs)
    data = fm(result)
    assert result.conflict is None
    assert [(e["id"], e["then"]) for e in data["examples"][2:]] == [("EX-3", "ours"),
                                                                    ("EX-4", "theirs")]
    by_path = {x["path"]: x["example"] for x in data["links"]}
    assert by_path == {"tests/a.py": "EX-3", "tests/b.py": "EX-4"}
    assert any("EX-4 from feat-x renumbered from EX-3" in n for n in result.merged)


@pytest.mark.sr("SR-076")
def test_example_changed_both_sides_conflicts() -> None:
    base = record(statement="s", examples=[ex(1), ex(2)])
    ours = record(statement="s", examples=[ex(1), ex(2, then="ours")])
    theirs = record(statement="s", examples=[ex(1), ex(2, then="theirs")])
    data = fm(merge(base, ours, theirs))
    block = data["conflict"]["fields"]["examples/EX-2"]
    assert (block["ours"]["then"], block["theirs"]["then"]) == ("ours", "theirs")
    assert data["examples"][1]["then"] == "ours"


@pytest.mark.sr("SR-076")
def test_example_removed_one_side_changed_other_conflicts() -> None:
    base = record(statement="s", examples=[ex(1), ex(2)])
    ours = record(statement="s", examples=[ex(1)])
    theirs = record(statement="s", examples=[ex(1), ex(2, then="changed")])
    data = fm(merge(base, ours, theirs))
    block = data["conflict"]["fields"]["examples/EX-2"]
    assert block["ours"] is None and block["theirs"]["then"] == "changed"


@pytest.mark.sr("SR-076")
def test_scalar_conflict_block() -> None:
    """The block holds base, both versions, both labels and both hashes (spec 8.1)."""
    base = record(statement="A relay pins every stated record.")
    ours = record(statement="A relay pins only the records the owner's words affirm.")
    theirs = record(statement="A relay pins the stated group, named by its title.")
    result = merge(base, ours, theirs)
    data = fm(result)
    block = data["conflict"]
    assert block["id"] == "IC-001"
    assert block["ours"]["label"] == "main" and block["theirs"]["label"] == "feat-x"
    assert block["fields"]["statement"] == {
        "base": "A relay pins every stated record.",
        "ours": "A relay pins only the records the owner's words affirm.",
        "theirs": "A relay pins the stated group, named by its title."}
    assert data["statement"].startswith("A relay pins only")
    assert block["ours"]["hash"] == record_hash(*parse(ours))
    assert list(data)[-1] == "conflict"


@pytest.mark.sr("SR-075")
def test_body_clean_merge() -> None:
    body = "line one\n\nline two\n\nline three\n"
    base = record(statement="s", body=body)
    ours = record(statement="s", body=body.replace("one", "ONE"))
    theirs = record(statement="s", body=body.replace("three", "THREE"))
    result = merge(base, ours, theirs)
    assert split_frontmatter(result.text)[1] == "line ONE\n\nline two\n\nline THREE\n"
    assert result.conflict is None


@pytest.mark.sr("SR-076")
def test_body_conflict() -> None:
    base = record(statement="s", body="text\n")
    ours = record(statement="s", body="ours text\n")
    theirs = record(statement="s", body="theirs text\n")
    result = merge(base, ours, theirs)
    data, body = parse(result.text)
    assert body == "ours text\n"
    assert data["conflict"]["fields"]["body"]["theirs"] == "theirs text\n"


@pytest.mark.sr("SR-075")
def test_formatting_only_difference_clean() -> None:
    base = record(statement="s", domain="d")
    ours = "---\nid: SR-005\ntitle: 'relay checks'\ndomain: d\nstatement: \"s\"\n---\n"
    theirs = "---\ntitle: relay checks\nid: SR-005\nstatement: s\ndomain: d\n---\n"
    result = merge(base, ours, theirs)
    assert result.exit == 0 and result.conflict is None
    assert record_hash(*parse(result.text)) == record_hash(*parse(base))


@pytest.mark.sr("SR-076")
def test_result_hash_matches_neither_side_on_conflict() -> None:
    base = record(statement="a")
    ours, theirs = record(statement="b"), record(statement="c")
    merged = record_hash(*parse(merge(base, ours, theirs).text))
    assert merged not in (record_hash(*parse(ours)), record_hash(*parse(theirs)))


@pytest.mark.sr("SR-076")
def test_no_ic_reserved_without_a_conflict() -> None:
    counter = Counter()
    merge_texts(record(statement="a"), record(statement="b"), record(statement="a"),
                labels=LABELS, reserve_ic=counter)
    assert counter.n == 0


def _with_open_block(statement_ours: str, statement_theirs: str) -> str:
    """SR-005 after main merged feat-x: IC-001 open on the statement (ours B, theirs C)."""
    first = merge(record(statement="A", title="relay checks"),
                  record(statement=statement_ours, title="relay checks"),
                  record(statement=statement_theirs, title="relay checks"))
    assert fm(first)["conflict"]["id"] == "IC-001"
    return first.text


def _assert_held(result, *kept: str) -> None:
    """Exit 1 (git leaves the file unmerged), every earlier version still in the file, no
    new IC reserved, and the owner told in plain words."""
    assert result.exit == 1 and result.conflict is None
    for text in kept:
        assert text in result.text
    assert "IC-001" in result.text and "IC-002" not in result.text
    assert result.notes and "still waits for your choice on an earlier conflict" in \
        result.notes[0]


@pytest.mark.sr("SR-076")
def test_open_block_on_ours_is_never_replaced() -> None:
    """ours carries IC-001 (statement B vs C); feat-y changes the title while main did too:
    the merge never drops IC-001 or feat-x's C for a new IC-002."""
    ours = _with_open_block("B", "C").replace("title: relay checks", "title: relay pins")
    theirs = record(statement="A", title="relay guards")
    counter = Counter()
    result = merge_texts(record(statement="A"), ours, theirs, labels=("main", "feat-y"),
                         reserve_ic=counter)
    _assert_held(result, "theirs: C", "relay guards")
    assert counter.n == 0


@pytest.mark.sr("SR-076")
def test_open_block_on_theirs_is_never_replaced() -> None:
    """theirs carries IC-001 and ours changed the same field again: held, nothing lost."""
    theirs = _with_open_block("B", "C")
    ours = record(statement="D", title="relay checks")
    counter = Counter()
    result = merge_texts(record(statement="A"), ours, theirs, labels=("main", "feat-x"),
                         reserve_ic=counter)
    _assert_held(result, "theirs: C", "statement: D")
    assert counter.n == 0


@pytest.mark.sr("SR-076")
def test_different_open_blocks_on_both_sides_are_held() -> None:
    """Both sides carry their own open block: neither is folded into a new one."""
    ours = _with_open_block("B", "C")
    theirs = _with_open_block("B", "E").replace("IC-001", "IC-009")
    result = merge(record(statement="A"), ours, theirs)
    assert result.exit == 1 and "IC-009" in result.text and "IC-001" in result.text
    assert "theirs: C" in result.text and "theirs: E" in result.text


@pytest.mark.sr("SR-076")
def test_open_block_kept_when_the_merge_is_otherwise_clean() -> None:
    """A block on one side and an unrelated clean change on the other: the block stays."""
    ours = _with_open_block("B", "C")
    theirs = record(statement="A", domain="relay")
    result = merge(record(statement="A"), ours, theirs)
    assert result.exit == 0 and fm(result)["conflict"]["id"] == "IC-001"
    assert fm(result)["domain"] == "relay"
