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


@pytest.mark.sr("SR-432")
def test_conversion_keeps_the_log_digests_valid(tmp_path: Path) -> None:
    """Archive segments (one entry a line) and migrated names follow the rewritten text."""
    import json

    from iaso.log import entry_digest

    repo = _old_project(tmp_path)
    segment = repo / OLD_DIR / "log" / "approval"
    segment.mkdir(parents=True, exist_ok=True)
    entry = {"at": "2026-10-07T23:10:04Z", "kind": "approval", "payload": {"quote": f"{OLD} ok"}}
    entry["digest"] = entry_digest(entry)
    (segment / "archive.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "log")
    assert _run("iaso", ["status"], repo).returncode == 0
    for line in (repo / ".iaso" / "log" / "approval" / "archive.jsonl").read_text().splitlines():
        got = json.loads(line)
        assert OLD not in line.lower() and got["digest"] == entry_digest(got)


@pytest.mark.sr("SR-432")
def test_a_merge_into_a_checkout_with_untracked_state_is_finished_by_the_converter(
        tmp_path: Path) -> None:
    """The landing: the branch holds the converted .iaso; main's checkout keeps untracked
    sessions, caches, local log kinds, a new record and registered work copies in the old folder."""
    repo = _old_project(tmp_path / "main")
    base = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    _git(repo, "worktree", "add", "-q", "-b", "conv", str(tmp_path / "conv"))
    assert _run("iaso", ["status"], tmp_path / "conv").returncode == 0
    _git(tmp_path / "conv", "add", "-A")
    _git(tmp_path / "conv", "commit", "-qm", "converted")
    old = repo / OLD_DIR
    (old / "session" / "s1").mkdir(parents=True)
    (old / "session" / "s1" / "state.json").write_text(f'{{"p": "{OLD_DIR}"}}', encoding="utf-8")
    (old / "cache").mkdir()
    (old / "cache" / "c.json").write_text("{}", encoding="utf-8")
    (old / "decisions").mkdir(exist_ok=True)
    (old / "decisions" / "DEC-900.md").write_text(
        f"---\nid: DEC-900\n---\n{OLD} decides\n", encoding="utf-8")
    (old / "wt").mkdir()
    _git(repo, "worktree", "add", "-q", "-b", "w1", str(old / "wt" / "w1"))
    _git(repo, "merge", "--no-commit", "--no-ff", "conv")
    assert (repo / OLD_DIR).is_dir() and (repo / ".iaso").is_dir()
    assert _run("iaso", ["status"], repo).returncode == 0
    assert not (repo / OLD_DIR).exists()
    assert (repo / ".iaso" / "session" / "s1" / "state.json").is_file()
    assert (repo / ".iaso" / "cache" / "c.json").is_file()
    assert OLD not in (repo / ".iaso" / "decisions" / "DEC-900.md").read_text().lower()
    assert str(repo / ".iaso" / "wt" / "w1") in _git(repo, "worktree", "list")
    assert (repo / ".iaso" / "wt" / "w1" / ".git").exists() and base


@pytest.mark.sr("SR-432")
def test_log_digests_of_the_owners_message_stay_and_quote_digests_follow_the_quote() -> None:
    from iaso.convert import _log_entry
    from iaso.log import entry_digest
    from iaso.normalize import sha256_text

    quote = f"rename {OLD} now"
    prompt = sha256_text(f"please rename {OLD} now")
    entry = {"kind": "approval", "payload": {"quote": quote, "quote_digest": sha256_text(quote),
                                             "prompt_digest": prompt, "trail": [prompt]}}
    entry["digest"] = entry_digest(entry)
    import json

    got = json.loads(_log_entry(json.dumps(entry), {}))
    assert got["payload"]["prompt_digest"] == prompt and got["payload"]["trail"] == [prompt]
    assert got["payload"]["quote"] == "rename iaso now"
    assert got["payload"]["quote_digest"] == sha256_text("rename iaso now")
    assert got["digest"] == entry_digest(got)


@pytest.mark.sr("SR-432")
def test_the_user_level_settings_are_carried_over_untouched(tmp_path: Path, monkeypatch) -> None:
    from iaso.convert import _carry_user_config

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / OLD).mkdir()
    key = tmp_path / OLD / "jev"
    key.write_text("secret", encoding="utf-8")
    key.chmod(0o600)
    (tmp_path / "iaso").mkdir()
    (tmp_path / "iaso" / "kept").write_text("mine", encoding="utf-8")
    (tmp_path / OLD / "kept").write_text("old", encoding="utf-8")
    lines = _carry_user_config()
    assert (tmp_path / "iaso" / "jev").read_text() == "secret"
    assert (tmp_path / "iaso" / "jev").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "iaso" / "kept").read_text() == "mine"   # one that exists is kept
    assert all("secret" not in line for line in lines) and lines


@pytest.mark.sr("SR-432")
def test_repair_gives_owner_messages_and_their_digests_back(tmp_path: Path) -> None:
    """A converter before the fix rewrote premise texts and remapped message digests in the
    untracked local log; the repair restores both, checked against the session files."""
    import json

    from iaso.convert import repair_messages
    from iaso.log import entry_digest
    from iaso.normalize import sha256_text

    repo = _repo(tmp_path)
    said = f"please fix {OLD} today"
    new = said.replace(OLD, "iaso")
    log = repo / ".iaso" / "log"

    def put(kind: str, name: str, payload: dict) -> Path:
        entry = {"at": "2026-10-19T03:35:42Z", "kind": kind, "payload": payload}
        entry["digest"] = entry_digest(entry)
        path = log / kind / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry), encoding="utf-8")
        return path

    premise = put("premise", "20261019T033542.442887Z-01345d00.json",
                  {"text": new, "digest": sha256_text(new)})  # the old converter remapped with sha256_text
    gate = put("gate", "20261019T033206.458414Z-09383d0a.json",
               {"digest": sha256_text(new), "state": "open"})
    approval = put("approval", "20261019T033206.458414Z-0000aaaa.json",
                   {"prompt_digest": sha256_text(new)})
    before = approval.read_bytes()
    session = repo / ".iaso" / "session" / "s1"
    session.mkdir(parents=True)
    from iaso.approvals import prompt_digest

    (session / "gate").write_text(json.dumps({"message_digest": prompt_digest(said)}),
                                  encoding="utf-8")
    assert repair_messages(repo)
    got = json.loads(premise.read_text())
    assert got["payload"] == {"text": said, "digest": prompt_digest(said)}
    assert got["digest"] == entry_digest(got)
    opened = json.loads(gate.read_text())
    assert opened["payload"]["digest"] == prompt_digest(said) and opened["digest"] == entry_digest(opened)
    assert approval.read_bytes() == before
