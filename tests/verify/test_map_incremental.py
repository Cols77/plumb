"""The test map stays cheap when a file is added (spec 10: hooks well under 2 s).

Adding or removing one Python file changes the file set, so every import edge must be
resolved again (a new file can satisfy an import). That re-resolution answers from the
scanned file set, not from the filesystem: on plumb's own repository it used to stat and
resolve every edge again and cost about 1.7 s, which pushed SessionStart past its budget.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import SR_TEXT, make_project, write

from plumb.api import open_core
from plumb.verify import imports
from plumb.verify.testmap import build_map


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    make_project(repo)
    write_record(repo, SR_TEXT)
    return repo


def _count_fs_checks(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    calls: list[Path] = []
    original = imports._is_file

    def counting(path: Path) -> bool:
        calls.append(path)
        return original(path)

    monkeypatch.setattr(imports, "_is_file", counting)
    return calls


@pytest.mark.sr("SR-255")
@pytest.mark.sr("SR-310")
def test_adding_a_file_resolves_edges_from_the_scanned_set(project: Path, monkeypatch) -> None:
    build_map(open_core(project))
    write(project, "tests/test_new.py", "from pkg.helper import twice\nimport json\n\n\n"
          "def test_new():\n    assert twice(1) == 2\n")
    calls = _count_fs_checks(monkeypatch)
    tmap = build_map(open_core(project))
    # nothing under the scanned directories is looked up on disk
    scanned = [p for p in calls if Path(p).relative_to(project).parts[0] in ("src", "tests")]
    assert scanned == []
    assert "tests/test_new.py" in tmap.covering("src/pkg/helper.py")
    assert "tests/test_new.py" in tmap.covering("src/pkg/mod.py")  # transitively


@pytest.mark.sr("SR-255")
def test_new_module_satisfies_an_existing_import(project: Path) -> None:
    write(project, "tests/test_later.py", "from pkg.later import VALUE\n\n\n"
          "def test_later():\n    assert VALUE == 2\n")
    tmap = build_map(open_core(project))
    assert tmap.covering("src/pkg/later.py") == []
    write(project, "src/pkg/later.py", "VALUE = 2\n")
    tmap = build_map(open_core(project))
    assert tmap.covering("src/pkg/later.py") == ["tests/test_later.py"]


@pytest.mark.sr("SR-255")
def test_cached_map_equals_a_full_rebuild(project: Path) -> None:
    build_map(open_core(project))
    write(project, "tests/test_extra.py", "from pkg import mod\n\n\ndef test_x():\n"
          "    assert mod.add(1, 1) == 2\n")
    warm = build_map(open_core(project))
    cold = build_map(open_core(project), rebuild=True)
    assert warm.direct == cold.direct
    assert warm.as_dict() == cold.as_dict()


@pytest.mark.sr("SR-255")
def test_string_resolver_agrees_with_the_filesystem_resolver(project: Path) -> None:
    write(project, "src/pkg/sub/__init__.py", "")
    write(project, "src/pkg/sub/deep.py", "from .. import mod\nfrom ...pkg import helper\n"
          "from . import missing\nimport pkg.sub.deep\nfrom pkg import mod, lonely\n")
    tmap = build_map(open_core(project))
    exists = imports.known_files(project, tmap.files, ("src", "tests"))
    for rel, info in tmap.files.items():
        for raw in info.get("edges", ()):
            edge = (raw[0], raw[1], tuple(raw[2]))
            assert imports.resolve_edge_rel(rel, edge, ("src",), exists) == \
                imports.resolve_edge(project, rel, edge, ("src",)), (rel, edge)
