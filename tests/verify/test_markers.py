"""V1: ``sr`` marker collection without importing the test module (spec 7.1)."""

from __future__ import annotations

import pytest

from plumb.verify.markers import collect_markers, test_nodes

SOURCE = '''
import pytest

pytestmark = pytest.mark.sr("SR-009")


@pytest.mark.sr("SR-001")
@pytest.mark.parametrize("x", [1, 2])
def test_one(x):
    assert x


@pytest.mark.sr("SR-002")
class TestThing:
    @pytest.mark.sr("SR-003")
    def test_two(self):
        pass

    def helper(self):
        pass


def test_three():
    pass


@pytest.mark.skip
def not_a_test():
    pass
'''


@pytest.mark.sr("SR-016")
def test_collects_sr_markers_on_functions_and_classes() -> None:
    nodes = collect_markers(SOURCE, "tests/test_x.py")
    assert nodes["tests/test_x.py::test_one"] == {"SR-001", "SR-009"}
    assert nodes["tests/test_x.py::TestThing::test_two"] == {"SR-002", "SR-003", "SR-009"}
    assert nodes["tests/test_x.py::test_three"] == {"SR-009"}
    assert "tests/test_x.py::not_a_test" not in nodes


@pytest.mark.sr("SR-016")
def test_test_nodes_hash_their_own_source() -> None:
    nodes = test_nodes(SOURCE, "tests/test_x.py")
    assert set(nodes) == {"tests/test_x.py::test_one", "tests/test_x.py::TestThing::test_two",
                          "tests/test_x.py::test_three"}
    edited = SOURCE.replace("def test_three():\n    pass", "def test_three():\n    assert 0")
    again = test_nodes(edited, "tests/test_x.py")
    assert again["tests/test_x.py::test_one"] == nodes["tests/test_x.py::test_one"]
    assert again["tests/test_x.py::test_three"] != nodes["tests/test_x.py::test_three"]
    crlf = test_nodes(SOURCE.replace("\n", "\r\n"), "tests/test_x.py")
    assert crlf == nodes


@pytest.mark.sr("SR-016")
def test_unparsable_source_yields_nothing() -> None:
    assert collect_markers("def broken(:\n", "tests/t.py") == {}
    assert test_nodes("def broken(:\n", "tests/t.py") == {}
