"""IDS: every path that creates a record ID goes through ``Store.next_id`` -> ``ids.reserve``
(sp6 4.5), one test each, plus the conformance scan."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from ids.gitrepo import make_repo, run_git, write
from plumb import ids
from plumb.cli import main
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-070")

SRC = Path(__file__).resolve().parents[2] / "src" / "plumb"


def recent(root: Path) -> list[str]:
    oid = run_git(root, "rev-parse", "-q", "--verify", ids.REF, check=False).strip()
    if not oid:
        return []
    return [r["id"] for r in json.loads(run_git(root, "cat-file", "blob", oid))["recent"]]


def cli(root: Path, *argv: str) -> int:
    return main([*argv, "--root", str(root)])


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = make_repo(tmp_path / "r")
    # another worktree already reserved SR-001 to SR-004, INT-001 and DEC-001 to DEC-002:
    # this worktree has none of those files, so only the ref can say so
    ids.observe(PlumbPaths(root), ["SR-004", "INT-001", "DEC-002", "FEAT-001", "NC-0001"])
    write(root, "INT-001", "an intent", quote="q", readback="r")
    return root


@pytest.mark.parametrize(("kind", "args", "expected"), [
    ("intent", ["--quote", "add it", "--readback", "add it"], "INT-002"),
    ("requirement", ["--statement", "s"], "SR-005"),
    ("decision", ["--question", "q?", "--chosen", "a"], "DEC-003"),
    ("feature", ["--description", "d"], "FEAT-002"),
    ("nc", [], "NC-0002"),
])
def test_plumb_new_reserves_each_kind(root: Path, kind: str, args: list[str],
                                      expected: str) -> None:
    assert cli(root, "new", kind, "--title", f"a {kind}", *args) == 0
    assert recent(root)[-1] == expected
    assert (root / ".plumb").rglob(f"{expected}.md")


def test_plumb_intent_reserves(root: Path) -> None:
    assert cli(root, "intent", "--quote", "add multiply", "--readback", "add multiply") == 0
    assert recent(root)[-1] == "INT-002"


def test_plumb_decide_reserves(root: Path) -> None:
    assert cli(root, "decide", "--question", "floats?", "--chosen", "integers",
               "--derives-from", "INT-001") == 0
    assert recent(root)[-1] == "DEC-003"


def test_plumb_decide_supersede_reserves(root: Path) -> None:
    write(root, "DEC-002", "integers", question="floats?", chosen="integers")
    assert cli(root, "decide", "--question", "floats?", "--chosen", "floats too",
               "--supersede", "DEC-002") == 0
    assert recent(root)[-1] == "DEC-003"


DOC = {"intent": "INT-001",
       "requirements": [{"title": "multiply", "statement": "multiply(a, b) is a * b"},
                        {"title": "divide", "statement": "divide(a, b) is a / b"}],
       "decisions": [{"question": "floats?", "chosen": "integers", "alternatives": ["floats"]}]}


def test_plumb_capture_reserves(root: Path, tmp_path: Path) -> None:
    doc = tmp_path / "doc.json"
    doc.write_text(json.dumps(DOC), encoding="utf-8")
    assert cli(root, "capture", "--file", str(doc)) == 0
    assert recent(root)[-3:] == ["SR-005", "SR-006", "DEC-003"]


def test_plumb_capture_dry_run_reserves_nothing(root: Path, tmp_path: Path) -> None:
    doc = tmp_path / "doc.json"
    doc.write_text(json.dumps(DOC), encoding="utf-8")
    before = run_git(root, "rev-parse", ids.REF).strip()
    assert cli(root, "capture", "--file", str(doc), "--dry-run") == 0
    assert run_git(root, "rev-parse", ids.REF).strip() == before
    assert not (root / ".plumb" / "requirements" / "SR-005.md").exists()


def test_importer_observes_kept_ids(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "importer"))
    try:
        from importer_helpers import make_source
    finally:
        sys.path.pop(0)
    from plumb.api import open_core
    from plumb.importer.pi_factory import import_pi_factory

    root = make_repo(tmp_path / "r")
    source = make_source(tmp_path)
    report = import_pi_factory(open_core(root), source)
    created = [i for i in open_core(root).index() if i.startswith("SR-")]
    assert report["actions"]["create"] >= 1 and created
    top = max(int(i.split("-")[1]) for i in created)
    assert ids.state(PlumbPaths(root)).high["SR"] >= top
    assert ids.reserve(PlumbPaths(root), "requirement") == [f"SR-{top + 1:03d}"]


def test_intent_conflict_ids_reserve(root: Path) -> None:
    assert ids.reserve(PlumbPaths(root), "conflict") == ["IC-001"]
    assert recent(root)[-1] == "IC-001"


# a new record number is computed by formatting a zero-padded number: only store.py (which
# calls ids.reserve) and the ids package may do that; examples (EX-n) are numbered inside
# their requirement and never use the ref (sp6 4.3)
_NUMBERING = re.compile(r":0(?:3|4|\{[^}]*\})d\}|max\(numbers\)")


def test_no_module_computes_record_numbers_outside_store_and_ids() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel == "store.py" or rel.startswith("ids/"):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _NUMBERING.search(line) and "EX-" not in line:
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert offenders == []


def test_plumb_capture_reserves_once_per_prefix(root: Path, tmp_path: Path,
                                                monkeypatch) -> None:
    from plumb.ids import ref as ref_mod

    messages: list[str] = []
    real = ref_mod.update

    def counting(r, data, old, message):
        messages.append(message)
        return real(r, data, old, message)

    monkeypatch.setattr(ref_mod, "update", counting)
    doc = tmp_path / "doc.json"
    doc.write_text(json.dumps(DOC), encoding="utf-8")
    assert cli(root, "capture", "--file", str(doc)) == 0
    assert messages == ["plumb: reserve SR-005, SR-006", "plumb: reserve DEC-003"]
