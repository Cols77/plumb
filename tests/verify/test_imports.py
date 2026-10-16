"""V1: import edges and the transitive import closure (spec 7.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.verify.imports import closure, direct_imports, import_edges


def _write(root: Path, rel: str, text: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "p"
    _write(root, "src/pkg/__init__.py")
    _write(root, "src/pkg/a.py", "from pkg import b\nimport os\n")
    _write(root, "src/pkg/b.py", "from .c import thing\n")
    _write(root, "src/pkg/c.py", "thing = 1\n")
    _write(root, "src/pkg/sub/__init__.py")
    _write(root, "src/pkg/sub/d.py", "from .. import a\nfrom . import e\n")
    _write(root, "src/pkg/sub/e.py", "")
    _write(root, "tests/test_a.py", "import pkg.a\nimport missing_mod\n")
    return root


@pytest.mark.sr("SR-255")
def test_import_edges_absolute_and_relative() -> None:
    edges = import_edges("import x.y\nfrom a import b\nfrom . import c\nfrom ..d import e\n")
    assert ("x.y", 0, ()) in edges
    assert ("a", 0, ("b",)) in edges
    assert ("", 1, ("c",)) in edges
    assert ("d", 2, ("e",)) in edges
    assert import_edges("def broken(:\n") == []


@pytest.mark.sr("SR-255")
def test_relative_and_from_imports_resolve_to_files(project: Path) -> None:
    sources = ("src", "tests")
    assert direct_imports(project, "src/pkg/a.py", sources) == {"src/pkg/__init__.py",
                                                                 "src/pkg/b.py"}
    assert direct_imports(project, "src/pkg/b.py", sources) == {"src/pkg/c.py"}
    assert direct_imports(project, "src/pkg/sub/d.py", sources) == {
        "src/pkg/__init__.py", "src/pkg/a.py", "src/pkg/sub/__init__.py", "src/pkg/sub/e.py"}


@pytest.mark.sr("SR-255")
def test_transitive_closure(project: Path) -> None:
    depths = closure(project, "tests/test_a.py", ("src", "tests"))
    assert depths["tests/test_a.py"] == 0
    assert depths["src/pkg/a.py"] == 1
    assert depths["src/pkg/b.py"] == 2
    assert depths["src/pkg/c.py"] == 3
    assert "src/pkg/sub/d.py" not in depths


@pytest.mark.sr("SR-255")
def test_unresolvable_imports_ignored(project: Path) -> None:
    depths = closure(project, "tests/test_a.py", ("src", "tests"))
    assert all(not key.startswith("missing") for key in depths)
    assert "os" not in depths
