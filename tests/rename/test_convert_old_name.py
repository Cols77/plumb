"""SR-432: only .iaso is supported; an old-name project is detected and converted (INT-131).

The old name is spelled in pieces so that this file itself names nothing (SR-430)."""

import subprocess
from pathlib import Path

import pytest

from tests.rename.test_rename_iaso import ROOT, _repo, _run

OLD = "plum" + "b"
OLD_DIR = "." + OLD


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout


def _old_project(tmp_path: Path) -> Path:
    """A committed repository whose records folder, record text and settings use the old name."""
    repo = _repo(tmp_path)
    assert _run("iaso", ["init"], repo).returncode == 0
    record = repo / ".iaso" / "requirements" / "SR-001.md"
    record.write_text(f"---\nid: SR-001\n---\n{OLD} keeps {OLD_DIR}/requirements/SR-001.md\n",
                      encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "records")
    _git(repo, "mv", ".iaso", OLD_DIR)
    for path in (repo / OLD_DIR).rglob("*"):
        if path.is_file() and path.suffix in {".md", ".yaml", ".yml", ""}:
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("iaso", OLD).replace(".iaso", OLD_DIR), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "old name")
    return repo


def _files_naming_old(repo: Path) -> list[str]:
    """Files naming the old name, outside git and the local caches (``.iaso/cache`` and
    ``.iaso/session`` are rebuilt and hold machine paths, such as the interpreter's)."""
    local = {".git", "cache", "session"}
    return [p.relative_to(repo).as_posix() for p in repo.rglob("*")
            if p.is_file() and not local & set(p.relative_to(repo).parts)
            and OLD in p.read_bytes().decode("utf-8", "ignore").lower()]


@pytest.mark.sr("SR-432")
def test_ex1_status_detects_and_converts_old_project(tmp_path: Path) -> None:
    repo = _old_project(tmp_path)
    result = _run("iaso", ["status"], repo)
    assert result.returncode == 0, result.stderr
    assert "old" in result.stdout.lower() and "convert" in result.stdout.lower()
    assert (repo / ".iaso").is_dir() and not (repo / OLD_DIR).exists()
    assert (repo / ".iaso" / "requirements" / "SR-001.md").is_file()


@pytest.mark.sr("SR-432")
def test_ex1_conversion_is_a_git_rename_and_rewrites_text_and_links(tmp_path: Path) -> None:
    repo = _old_project(tmp_path)
    assert _run("iaso", ["status"], repo).returncode == 0
    staged = _git(repo, "diff", "--cached", "--name-status", "-M")
    assert f"{OLD_DIR}/requirements/SR-001.md" in staged  # a rename, so history follows
    text = (repo / ".iaso" / "requirements" / "SR-001.md").read_text(encoding="utf-8")
    assert OLD not in text.lower()
    assert ".iaso/requirements/SR-001.md" in text
    assert _files_naming_old(repo) == []


@pytest.mark.sr("SR-432")
def test_ex1_same_status_after_conversion(tmp_path: Path) -> None:
    repo = _old_project(tmp_path)
    first = _run("iaso", ["status"], repo)
    second = _run("iaso", ["status"], repo)
    assert first.returncode == second.returncode == 0
    assert "convert" not in second.stdout.lower()  # converting happens once
    assert second.stdout.strip()


@pytest.mark.sr("SR-432")
def test_ex2_init_in_empty_repo_makes_only_dot_iaso(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert _run("iaso", ["init"], repo).returncode == 0
    assert (repo / ".iaso").is_dir() and not (repo / OLD_DIR).exists()
    assert _files_naming_old(repo) == []


@pytest.mark.sr("SR-432")
def test_state_dir_never_reads_the_old_folder_in_place(tmp_path: Path) -> None:
    from iaso.paths import find_root, state_dir

    (tmp_path / OLD_DIR).mkdir()
    sub = tmp_path / "sub"
    sub.mkdir()
    assert state_dir(tmp_path) == tmp_path / ".iaso"
    assert find_root(sub) == sub.resolve()  # the old folder above marks no root


@pytest.mark.sr("SR-432")
def test_no_code_reads_or_writes_the_old_folder() -> None:
    bad = [str(p.relative_to(ROOT)) for top in ("src", "plugin", "scripts")
           for p in (ROOT / top).rglob("*")
           if p.is_file() and p.suffix in {".py", ".ts", ".js", ".sh", ""}
           and OLD in p.read_text(encoding="utf-8", errors="ignore").lower()]
    assert not bad, bad


@pytest.mark.sr("SR-432")
def test_ex3_this_repository_holds_dot_iaso_and_no_old_folder() -> None:
    tracked = _git(ROOT, "ls-files").splitlines()
    assert any(t.startswith(".iaso/") for t in tracked)
    assert not any(t.startswith(OLD_DIR + "/") for t in tracked)


@pytest.mark.sr("SR-430")
@pytest.mark.sr("SR-432")
def test_no_tracked_file_mentions_the_old_name() -> None:
    skip = {"uv.lock"}
    bad = []
    for name in _git(ROOT, "ls-files").splitlines():
        path = ROOT / name
        if name in skip or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        if OLD in name.lower() or OLD.encode() in data.lower():
            bad.append(name)
    assert not bad, f"{len(bad)} files: {bad[:15]}"


@pytest.mark.sr("SR-432")
def test_conversion_leaves_the_shared_git_directory_untouched(tmp_path: Path) -> None:
    host = _old_project(tmp_path)
    work = tmp_path / "wt"
    _git(host, "worktree", "add", "-q", "-b", "b", str(work))
    shared = host / ".git"
    (shared / "hooks").mkdir(exist_ok=True)
    (shared / "hooks" / "pre-commit").write_text(f"#!/bin/sh\n# {OLD}\n", encoding="utf-8")
    (shared / "info").mkdir(exist_ok=True)
    (shared / "info" / "attributes").write_text(f"x merge={OLD}-record\n", encoding="utf-8")
    watched = [shared / "config", shared / "hooks" / "pre-commit", shared / "info" / "attributes"]
    before = [p.read_bytes() for p in watched]
    assert _run("iaso", ["status"], work).returncode == 0
    assert [p.read_bytes() for p in watched] == before


@pytest.mark.sr("SR-432")
def test_conversion_renames_files_that_name_the_old_name(tmp_path: Path) -> None:
    repo = _old_project(tmp_path)
    study = repo / OLD_DIR / "studies" / f"what-{OLD}-does.md"
    study.parent.mkdir(exist_ok=True)
    study.write_text("a study\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "study")
    assert _run("iaso", ["status"], repo).returncode == 0
    assert (repo / ".iaso" / "studies" / "what-iaso-does.md").is_file()
    assert not list((repo / ".iaso" / "studies").glob(f"*{OLD}*"))
