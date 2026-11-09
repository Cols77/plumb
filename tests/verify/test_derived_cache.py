"""The hooks' warm path skips the test-map build (spec 10: hooks well under 2 s).

``full_pending`` and the record-to-test map are cached in ``.iaso/cache/derived.json``
under a fingerprint of everything they are computed from (the scanned source files, the
records and their links, the evidence log, the config, the environment key and the shared
test infrastructure). A warm SessionStart on iaso's own repository used to rebuild the map
on every call (about 0.65 s of 1.37 s).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import SR_TEXT, make_project, write

import iaso.verify.testmap as testmap
from iaso.api import open_core
from iaso.verify import open_verify

pytestmark = [pytest.mark.sr("SR-310"), pytest.mark.sr("SR-255")]


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    make_project(repo)
    write_record(repo, SR_TEXT)
    return repo


def _forbid_build(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_build(*args, **kwargs):
        raise AssertionError("the test map was built on a warm call")

    monkeypatch.setattr(testmap, "build_map", no_build)


def test_warm_full_pending_and_record_tests_skip_the_map(project: Path, monkeypatch) -> None:
    cold = open_verify(open_core(project))
    pending = cold.full_pending()
    tests = cold.tests_for(["SR-001"])
    assert tests["SR-001"]
    _forbid_build(monkeypatch)
    warm = open_verify(open_core(project))
    assert warm.full_pending() == pending
    assert warm.tests_for(["SR-001"]) == tests


def test_a_source_change_invalidates_the_cache(project: Path, monkeypatch) -> None:
    open_verify(open_core(project)).full_pending()
    write(project, "src/pkg/brand_new.py", "VALUE = 2\n")
    calls: list[int] = []
    real = testmap.build_map

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(testmap, "build_map", counting)
    open_verify(open_core(project)).full_pending()
    assert calls, "a new source file must rebuild the map"


def test_a_new_link_invalidates_the_record_tests(project: Path) -> None:
    from iaso.contracts import Target

    open_verify(open_core(project)).tests_for(["SR-001"])
    open_core(project).add_link("SR-001", "verified_by",
                                Target(test="tests/test_helper.py::test_twice"))
    tests = open_verify(open_core(project)).tests_for(["SR-001"])["SR-001"]
    assert "tests/test_helper.py::test_twice" in tests
