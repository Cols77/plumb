"""VS3: the content-based environment identity, cached under the env key (spec 7.4)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from iaso.api import open_core
from iaso.verify import envid
from iaso.verify.evidence import apply_entry, single_evidence


@pytest.mark.sr("SR-255")
def test_identity_none_without_pyvenv(tmp_path: Path) -> None:
    assert envid.content_identity(tmp_path, prefix=str(tmp_path / "no-venv")) is None


@pytest.mark.sr("SR-255")
def test_identity_of_this_environment_is_stable(tmp_path: Path) -> None:
    first = envid.content_identity(tmp_path)
    if not (Path(sys.prefix) / "pyvenv.cfg").exists():
        assert first is None
        return
    assert first is not None and first.startswith("sha256:")
    assert envid.content_identity(tmp_path) == first


@pytest.mark.sr("SR-255")
def test_identity_cached_under_env_key(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake(root: Path, prefix: str | None = None) -> str:
        calls.append(root)
        return "sha256:" + "a" * 64

    monkeypatch.setattr(envid, "content_identity", fake)
    core = open_core(repo)
    assert envid.cached_identity(core, "K1") is None
    assert envid.cached_identity(core, "K1", compute=True) == "sha256:" + "a" * 64
    assert envid.cached_identity(open_core(repo), "K1") == "sha256:" + "a" * 64
    assert envid.cached_identity(open_core(repo), "K1", compute=True) == "sha256:" + "a" * 64
    assert len(calls) == 1
    assert envid.cached_identity(open_core(repo), "K2") is None


@pytest.mark.sr("SR-255")
def test_unknown_identity_never_reused() -> None:
    index: dict = {"nodes": {}, "full": None}
    apply_entry(index, {"run_id": "r1", "env": {"env_key": "E", "identity": "I"},
                        "nodes": [{"id": "t.py::a", "outcome": "passed", "closure": "C",
                                   "test_hash": "T"}]})
    same = {"closure": "C", "test_hash": "T", "env_key": "E"}
    assert single_evidence(index, "t.py::a", identity="I", **same).state == "fresh-pass"
    for current in (None, "J"):
        got = single_evidence(index, "t.py::a", identity=current, **same)
        assert (got.state, got.reuse_miss) == ("stale", "identity")
    apply_entry(index, {"run_id": "r2", "env": {"env_key": "E", "identity": None},
                        "nodes": [{"id": "t.py::a", "outcome": "passed", "closure": "C",
                                   "test_hash": "T"}]})
    got = single_evidence(index, "t.py::a", identity="I", **same)
    assert (got.state, got.reuse_miss) == ("stale", "identity")


@pytest.mark.sr("SR-255")
def test_env_key_reuses_the_cached_platform(tmp_path: Path, monkeypatch) -> None:
    """``platform.machine()`` costs a WMI query (about 0.2 s) on Windows: the env key caches
    it under .iaso/cache, keyed by the interpreter, and the key itself is unchanged."""
    (tmp_path / ".iaso").mkdir()
    first = envid.env_key(tmp_path)

    def no_wmi():
        raise AssertionError("platform.machine() called on a warm env key")

    monkeypatch.setattr(envid.platform, "machine", no_wmi)
    assert envid.env_key(tmp_path) == first


@pytest.mark.sr("SR-255")
def test_env_key_follows_the_test_interpreter_not_iasos(tmp_path: Path, monkeypatch) -> None:
    """Field: the pre-push hook reaches iaso through the plugin's interpreter, but the tests
    run in the project's .venv. The key (and so the evidence) must be the test venv's, whatever
    interpreter iaso itself runs in, or a hook never sees a direct run's passes."""
    venv = tmp_path / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    exe = venv / "Scripts" / "python.exe"
    exe.write_text("")
    (venv / "pyvenv.cfg").write_text(
        "home = C:/py\nimplementation = CPython\nversion_info = 3.12.1\n", encoding="utf-8")
    keys = set()
    for name in ("A", "B"):
        monkeypatch.setattr(sys, "prefix", str(tmp_path / name))
        monkeypatch.setattr(sys, "executable", str(tmp_path / name / "python.exe"))
        keys.add(envid.env_key(tmp_path, str(exe)))
    assert len(keys) == 1
    assert envid.env_parts(tmp_path, str(exe))["home"] == "C:/py"
    assert envid.env_parts(tmp_path, str(exe))["python"] == "CPython 3.12.1"
