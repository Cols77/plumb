"""SR-321: which log kinds are committed (shared) and which stay on the machine (local)."""

from __future__ import annotations

import re
from pathlib import Path

from plumb import log
from plumb.api import open_core
from plumb.paths import PlumbPaths

from .gitrepo import commit_all, make_repo, run_git

ROOT = Path(__file__).resolve().parents[2]


def _scratch(tmp_path: Path) -> Path:
    root = make_repo(tmp_path / "r")
    (root / ".gitignore").write_text(
        (ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    commit_all(root, "ignore")
    return root


def test_ex1_status_lists_only_shared_entries(tmp_path: Path) -> None:
    root = _scratch(tmp_path)
    core = open_core(root)
    core.log_append("events", "verdict", {"record": "SR-001"})
    core.log_append("events", "approval", {"record": "SR-001"})
    status = run_git(root, "status", "--porcelain", "-uall").stdout
    assert ".plumb/log/approval/" in status
    assert ".plumb/log/verdict/" not in status


def test_ex2_status_reads_a_clone_without_local_kinds(tmp_path: Path) -> None:
    root = _scratch(tmp_path)
    core = open_core(root)
    core.log_append("events", "verdict", {"record": "SR-001"})
    assert {e.kind for e in log.read(PlumbPaths(root), "events")} == {"verdict"}
    for d in (root / ".plumb" / "log" / "verdict").glob("*.json"):
        d.unlink()  # the other clone never had them
    assert list(log.read(PlumbPaths(root), "events")) == []  # readers cope with none


def test_ex3_every_kind_is_in_exactly_one_set_and_ignored_exactly(tmp_path: Path) -> None:
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "plumb").rglob("*.py"))
    consts = dict(re.findall(r'^\s*([A-Z_]+)\s*=\s*"([a-z0-9-]+)"', src, re.M))
    used = set()
    for arg in re.findall(r'log_append\(\s*(?:"[a-z]+"|[\w.()]+),\s*("[a-z0-9-]+"|[A-Z_]+)', src):
        used.add(arg.strip('"') if arg.startswith('"') else consts.get(arg, arg))
    assert used, "no kind found"
    assert not log.SHARED_KINDS & log.LOCAL_KINDS
    unlisted = used - log.SHARED_KINDS - log.LOCAL_KINDS
    assert not unlisted, f"list these as shared or local: {sorted(unlisted)}"
    ignored = set(re.findall(r"^\.plumb/log/([a-z0-9-]+)/$",
                             (ROOT / ".gitignore").read_text(encoding="utf-8"), re.M))
    assert ignored == log.LOCAL_KINDS


def test_stage_never_stages_a_local_kind(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")  # no .gitignore lines: only stage's filter can hold it back
    for kind in ("verdict", "approval"):
        d = root / ".plumb" / "log" / kind
        d.mkdir(parents=True, exist_ok=True)
        (d / "x.json").write_text("{}", encoding="utf-8")
    log.stage(root, [".plumb/log/verdict/x.json", ".plumb/log/approval/x.json"])
    staged = run_git(root, "diff", "--cached", "--name-only").stdout
    assert ".plumb/log/approval/x.json" in staged
    assert "verdict" not in staged
