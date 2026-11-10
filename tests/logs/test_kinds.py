"""SR-321: which log kinds are committed (shared) and which stay on the machine (local)."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

from iaso import log
from iaso.api import open_core
from iaso.paths import IasoPaths

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
    assert ".iaso/log/approval/" in status
    assert ".iaso/log/verdict/" not in status


def test_ex2_status_reads_a_clone_without_local_kinds(tmp_path: Path) -> None:
    root = _scratch(tmp_path)
    core = open_core(root)
    core.log_append("events", "verdict", {"record": "SR-001"})
    assert {e.kind for e in log.read(IasoPaths(root), "events")} == {"verdict"}
    for d in (root / ".iaso" / "log" / "verdict").glob("*.json"):
        d.unlink()  # the other clone never had them
    assert list(log.read(IasoPaths(root), "events")) == []  # readers cope with none


def test_ex3_every_kind_is_in_exactly_one_set_and_ignored_exactly(tmp_path: Path) -> None:
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "iaso").rglob("*.py"))
    consts = dict(re.findall(r'^\s*([A-Z_]+)\s*=\s*"([a-z0-9-]+)"', src, re.M))
    used = set()
    for arg in re.findall(r'log_append\(\s*(?:"[a-z]+"|[\w.()]+),\s*("[a-z0-9-]+"|[A-Z_]+)', src):
        used.add(arg.strip('"') if arg.startswith('"') else consts.get(arg, arg))
    assert used, "no kind found"
    assert not log.SHARED_KINDS & log.LOCAL_KINDS
    unlisted = used - log.SHARED_KINDS - log.LOCAL_KINDS
    assert not unlisted, f"list these as shared or local: {sorted(unlisted)}"
    ignored = set(re.findall(r"^\.iaso/log/([a-z0-9-]+)/$",
                             (ROOT / ".gitignore").read_text(encoding="utf-8"), re.M))
    assert ignored == log.LOCAL_KINDS


def test_stage_never_stages_a_local_kind(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")  # no .gitignore lines: only stage's filter can hold it back
    for kind in ("verdict", "approval"):
        d = root / ".iaso" / "log" / kind
        d.mkdir(parents=True, exist_ok=True)
        (d / "x.json").write_text("{}", encoding="utf-8")
    log.stage(root, [".iaso/log/verdict/x.json", ".iaso/log/approval/x.json"])
    staged = run_git(root, "diff", "--cached", "--name-only").stdout
    assert ".iaso/log/approval/x.json" in staged
    assert "verdict" not in staged


OWNER_WORDS = ("pre-intent", "question-answer", "answer-bound", "prompt", "premise",
               "owner-words")


def _append(core, kind: str, payload: dict) -> None:
    """``pre-intent`` is a worker-only kind: write it with the worker's token."""
    from iaso import log as _log

    with patch.object(_log, "worker_token_problem", return_value=None):
        core.log_append("events", kind, payload)


def test_the_owners_words_kinds_are_local_never_committed(tmp_path: Path) -> None:
    """DEC-116 (2026-11-01): nothing the owner writes goes into the tracked log."""
    assert set(OWNER_WORDS) == set(log.OWNER_WORDS_KINDS)
    assert set(OWNER_WORDS) <= log.LOCAL_KINDS
    root = _scratch(tmp_path)
    core = open_core(root)
    for kind in OWNER_WORDS:
        _append(core, kind, {"text": "my words"})
    status = run_git(root, "status", "--porcelain", "-uall").stdout
    assert all(f".iaso/log/{kind}/" not in status for kind in OWNER_WORDS)


def test_init_ignore_list_is_exactly_the_local_kinds_and_judgment(tmp_path: Path) -> None:
    """SR-376#12, DEC-116: the .iaso/.gitignore init writes lists every local kind."""
    from iaso.commands import init_repo

    root = tmp_path / "fresh"
    root.mkdir()
    init_repo(root)
    lines = (root / ".iaso" / ".gitignore").read_text(encoding="utf-8").split()
    kinds = {m for line in lines for m in re.findall(r"^log/([a-z0-9-]+)/$", line)}
    assert kinds == log.LOCAL_KINDS
    assert "log/judgment/*.json" in lines


def test_a_worktree_reads_the_owners_words_the_main_checkout_logged(tmp_path: Path) -> None:
    """DEC-116: the readers find the entries through git's common directory."""
    root = _scratch(tmp_path)
    _append(open_core(root), "question-answer", {"answer": "yes", "session": "s"})
    wt = tmp_path / "wt"
    run_git(root, "worktree", "add", "-b", "side", str(wt))
    mine = open_core(wt)
    _append(mine, "question-answer", {"answer": "no", "session": "t"})
    got = sorted(e.payload["answer"] for e in mine.events() if e.kind == "question-answer")
    assert got == ["no", "yes"]
    again = sorted(e.payload["answer"] for e in open_core(wt).events()
                   if e.kind == "question-answer")
    assert again == ["no", "yes"]            # once, not twice
    assert sorted(e.payload["answer"] for e in open_core(root).events()
                  if e.kind == "question-answer") == ["no", "yes"]   # either way round
