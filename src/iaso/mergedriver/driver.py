"""``iaso merge-driver BASE OURS THEIRS PATH [OURS_LABEL THEIRS_LABEL]`` (sp6 7.2).

git calls it for a record file both sides changed (``merge=iaso-record`` in
``.iaso/.gitattributes``), in the top directory of the worktree, while it holds the index
lock: it reads the three temporary files, writes the result to ``OURS`` and exits 0 (merged,
possibly carrying an intent conflict) or 1 (git must stop: an add/add of one ID, a side
that is not a record and did not merge as text, or a record whose open intent conflict a
new one would replace). An intent conflict exits 0 only under ``git merge`` (and ``git
pull``), whose commit the quick merge check holds; under a rebase, a cherry-pick, a revert or
any other merge it exits 1, so git stops on the record instead of committing the block
(R17). Import-light: the frontmatter helpers only,
never the record index. git runs only to reserve an ``IC`` ID (and, with a git older than
2.44, to name the two sides).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_IC = re.compile(r"(?<![\w-])IC-(\d{3,})(?!\d)")
RECORD_DIRS = ("intents", "requirements", "decisions", "features", "ncs")
CACHE = "ic-reserved.json"
SIDE_HEADS = ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def under_git_merge() -> bool:
    """True inside ``git merge`` (``git pull`` included): it names each incoming head in a
    ``GITHEAD_<sha>`` variable; rebase, cherry-pick, revert and stash set none."""
    return any(re.fullmatch(r"GITHEAD_[0-9a-fA-F]{40,64}", key) for key in os.environ)


def git_operation(root: Path) -> str | None:
    """The git operation in progress that records another line's work: ``merge``,
    ``rebase``, ``cherry-pick`` or ``revert``; None outside one. One git call."""
    if under_git_merge():
        return "merge"
    found = _git(Path(root), "rev-parse", "--absolute-git-dir")
    if not found:
        return None
    gitdir = Path(found)
    if (gitdir / "rebase-merge").is_dir() or (gitdir / "rebase-apply").is_dir():
        return "rebase"
    for name, operation in (("MERGE_HEAD", "merge"), ("CHERRY_PICK_HEAD", "cherry-pick"),
                            ("REVERT_HEAD", "revert")):
        if (gitdir / name).is_file():
            return operation
    return None


def _numbers(text: str) -> set[int]:
    return {int(m.group(1)) for m in _IC.finditer(text)}


def known_ics(root: Path) -> set[int]:
    """Every IC number this worktree knows: open conflict blocks in record files, resolved
    ones in the log (both log layouts) and the last one this worktree handed out."""
    iaso = Path(root) / ".iaso"
    found: set[int] = set()
    for dirname in RECORD_DIRS:
        directory = iaso / dirname
        if not directory.is_dir():
            continue
        for path in directory.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "IC-" in text:
                found |= _numbers(text)
    try:
        with open(iaso / "log" / "events.jsonl", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "conflict-resolution" in line:
                    found |= _numbers(line)
    except OSError:
        pass
    resolved = iaso / "log" / "conflict-resolution"
    if resolved.is_dir():
        for path in resolved.iterdir():
            try:
                found |= _numbers(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    try:
        cached = json.loads((iaso / "cache" / CACHE).read_text(encoding="utf-8"))
        found.add(int(cached.get("high", 0)))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return found


def _remember(root: Path, ic: str) -> None:
    match = _IC.search(ic)
    if match is None:
        return
    cache = Path(root) / ".iaso" / "cache"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        tmp = cache / f".{CACHE}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps({"high": int(match.group(1))}), encoding="utf-8")
        os.replace(tmp, cache / CACHE)
    except OSError:
        pass


def reserve_ic(root: Path) -> str:
    """A new ``IC-###``: through ``iaso.ids.reserve(kind="conflict")`` (``refs/iaso/ids``,
    unique across the clone's worktrees); when the ref cannot be updated, the number after
    the highest this worktree knows (``ids.local_next``), so a merge never fails on it."""
    from iaso import ids  # the one allocator (sp6 4)
    from iaso.paths import IasoPaths

    root = Path(root)
    local = [ids.format_id("conflict", n) for n in known_ics(root)]
    try:
        ic = ids.reserve(IasoPaths(root), "conflict", local=local)[0]
    except Exception:  # noqa: BLE001 - the ref is busy or unreadable: a merge never fails
        ic = ids.local_next("conflict", local)
    _remember(root, ic)
    return ic


def _branch_name(root: Path, label: str) -> str:
    if label in ("", "HEAD"):
        name = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
        if name:
            return name
        short = _git(root, "rev-parse", "--short", "HEAD")
        return short or "ours"
    return label


def _theirs_name(root: Path, label: str) -> str:
    if label and not re.fullmatch(r"[0-9a-f]{7,40}(?: .*)?", label):
        return label
    for head in SIDE_HEADS:
        sha = _git(root, "rev-parse", "-q", "--verify", head)
        if sha:
            name = _git(root, "name-rev", "--name-only", "--exclude=refs/tags/*", sha)
            if name and name != "undefined":
                return re.sub(r"[~^].*$", "", name).removeprefix("remotes/")
            return sha[:12]
    return label.split(" ")[0] if label else "theirs"


def labels_of(root: Path, argv_labels: list[str]) -> tuple[str, str]:
    ours = argv_labels[0] if argv_labels else ""
    theirs = argv_labels[1] if len(argv_labels) > 1 else ""
    if "%" in ours:  # a git older than 2.44 passes the placeholders through
        ours = ""
    if "%" in theirs:
        theirs = ""
    return _branch_name(root, ours.strip()), _theirs_name(root, theirs.strip())


def _read(path: str) -> str:
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8", errors="replace")


def main(argv: list[str]) -> int:
    usage = "usage: iaso merge-driver BASE OURS THEIRS [PATH [OURS_LABEL THEIRS_LABEL]]"
    if argv[:1] in (["-h"], ["--help"]):
        print(usage)
        print(__doc__.split("\n\n", 1)[1].strip())
        return 0
    if len(argv) < 3:
        print(usage, file=sys.stderr)
        return 2
    base_path, ours_path, theirs_path = argv[:3]
    root = Path.cwd()
    from iaso.mergedriver.merge import merge_texts

    labels = labels_of(root, argv[4:6])
    result = merge_texts(_read(base_path), _read(ours_path), _read(theirs_path),
                         labels=labels, reserve_ic=lambda: reserve_ic(root))
    with open(ours_path, "wb") as handle:
        handle.write(result.text.encode("utf-8"))
    for note in result.notes:
        print(note, file=sys.stderr)
    if result.conflict and result.exit == 0 and not under_git_merge():
        return 1  # no merge commit to hold: git stops on the record (R17)
    return result.exit
