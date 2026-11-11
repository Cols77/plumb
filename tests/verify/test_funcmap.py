"""HB2: the function-to-tests map (SR-110): what each test executed, per function."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import write

from iaso.verify.funcmap import MODULE, FuncMap, file_functions

SRC = "src/pkg/mod.py"
BODY = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"


@pytest.fixture
def fm(tmp_path: Path) -> FuncMap:
    write(tmp_path, SRC, BODY)
    return FuncMap(tmp_path / "cache" / "funcmap.sqlite", tmp_path)


def _record(fm: FuncMap, node: str, executed, env: str = "env-a", digest: str = "d1") -> None:
    fm.register_file(SRC)
    fm.record_test(node, node.split("::")[0], digest, env, {(SRC, q) for q in executed})


@pytest.mark.sr("SR-255")
def test_roundtrip(fm: FuncMap, tmp_path: Path) -> None:
    _record(fm, "tests/test_mod.py::test_add", ["add"])
    _record(fm, "tests/test_mod.py::test_both", ["add", "sub"])
    fm.close()
    again = FuncMap(tmp_path / "cache" / "funcmap.sqlite", tmp_path)
    assert again.tests_executing(SRC, "add", "env-a") == [
        "tests/test_mod.py::test_add", "tests/test_mod.py::test_both"]
    assert again.tests_executing(SRC, "sub", "env-a") == ["tests/test_mod.py::test_both"]
    assert again.is_recorded(SRC, "env-a")
    assert again.entry("tests/test_mod.py::test_add") == ("tests/test_mod.py", "d1", "env-a")


@pytest.mark.sr("SR-255")
def test_function_hash_ignores_formatting(tmp_path: Path) -> None:
    write(tmp_path, SRC, "def add(a, b):\n    return a+b  # sum\n")
    before = file_functions(tmp_path, SRC)
    write(tmp_path, SRC, "def add(a,\n        b):\n    return (a + b)\n")
    assert file_functions(tmp_path, SRC) == before
    write(tmp_path, SRC, "def add(a, b):\n    return a - b\n")
    after = file_functions(tmp_path, SRC)
    assert after["add"] != before["add"]
    assert after[MODULE] == before[MODULE]


@pytest.mark.sr("SR-255")
def test_changed_function_found(fm: FuncMap, tmp_path: Path) -> None:
    _record(fm, "tests/test_mod.py::test_add", ["add"])
    assert fm.functions_changed([SRC]) == []
    write(tmp_path, SRC, BODY.replace("a + b", "b + a"))
    changed = fm.functions_changed([SRC])
    assert [(c.qualname, c.kind) for c in changed] == [("add", "changed")]
    # a change outside every function is the module part
    write(tmp_path, SRC, BODY + "LIMIT = 3\n")
    assert [(c.qualname, c.kind) for c in fm.functions_changed([SRC])] == [(MODULE, "changed")]


@pytest.mark.sr("SR-255")
def test_new_function_has_no_tests(fm: FuncMap, tmp_path: Path) -> None:
    _record(fm, "tests/test_mod.py::test_add", ["add"])
    write(tmp_path, SRC, BODY + "\n\ndef mul(a, b):\n    return a * b\n")
    changed = fm.functions_changed([SRC])
    assert [(c.qualname, c.kind) for c in changed] == [("mul", "new")]
    assert fm.tests_executing(SRC, "mul", "env-a") == []


@pytest.mark.sr("SR-255")
def test_env_key_change_invalidates(fm: FuncMap) -> None:
    _record(fm, "tests/test_mod.py::test_add", ["add"], env="env-a")
    assert fm.tests_executing(SRC, "add", "env-b") == []
    assert not fm.is_recorded(SRC, "env-b")
    assert fm.fresh_nodes({"tests/test_mod.py": "d1"}, "env-a") == {
        "tests/test_mod.py::test_add"}
    assert fm.fresh_nodes({"tests/test_mod.py": "d1"}, "env-b") == set()
    assert fm.fresh_nodes({"tests/test_mod.py": "d2"}, "env-a") == set()
