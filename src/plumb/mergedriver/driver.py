"""``plumb merge-driver BASE OURS THEIRS PATH [OURS_LABEL THEIRS_LABEL]`` (sp6 7.2).

git calls it for a record file both sides changed (``merge=plumb-record`` in
``.plumb/.gitattributes``), in the top directory of the worktree, while it holds the index
lock: it reads the three temporary files, writes the result to ``OURS`` and exits 0 (merged,
possibly carrying an intent conflict) or 1 (git must stop: an add/add of one ID, a side
that is not a record and did not merge as text, or a record whose open intent conflict a
new one would replace). Import-light: the frontmatter helpers only,
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


def _numbers(text: str) -> set[int]:
    return {int(m.group(1)) for m in _IC.finditer(text)}


def known_ics(root: Path) -> set[int]:
    """Every IC number this worktree knows: open conflict blocks in record files, resolved
    ones in the log (both log layouts) and the last one this worktree handed out."""
    plumb = Path(root) / ".plumb"
    found: set[int] = set()
    for dirname in RECORD_DIRS:
        directory = plumb / dirname
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
        with open(plumb / "log" / "events.jsonl", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "conflict-resolution" in line:
                    found |= _numbers(line)
    except OSError:
        pass
    resolved = plumb / "log" / "conflict-resolution"
    if resolved.is_dir():
        for path in resolved.iterdir():
            try:
                found |= _numbers(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    try:
        cached = json.loads((plumb / "cache" / CACHE).read_text(encoding="utf-8"))
        found.add(int(cached.get("high", 0)))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return found


def _remember(root: Path, ic: str) -> None:
    match = _IC.search(ic)
    if match is None:
        return
    cache = Path(root) / ".plumb" / "cache"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        tmp = cache / f".{CACHE}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps({"high": int(match.group(1))}), encoding="utf-8")
        os.replace(tmp, cache / CACHE)
    except OSError:
        pass


def reserve_ic(root: Path) -> str:
    """A new ``IC-###``: through ``plumb.ids.reserve(kind="conflict")`` (``refs/plumb/ids``,
    unique across the clone's worktrees) when this build has it, else the highest number
    this worktree knows plus one."""
    root = Path(root)
    known = known_ics(root)
    ic: str | None = None
    try:
        from plumb import ids  # the IDS lane's allocator (sp6 4)
        from plumb.paths import PlumbPaths

        ic = ids.reserve(PlumbPaths(root), "conflict",
                         local=[f"IC-{n:03d}" for n in known])[0]
    except Exception:  # noqa: BLE001 - no allocator in this build, or it failed: local
        ic = None
    if ic is None:
        ic = f"IC-{max(known, default=0) + 1:03d}"
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
    if len(argv) < 3:
        print("usage: plumb merge-driver BASE OURS THEIRS [PATH [OURS_LABEL THEIRS_LABEL]]",
              file=sys.stderr)
        return 2
    base_path, ours_path, theirs_path = argv[:3]
    root = Path.cwd()
    from plumb.mergedriver.merge import merge_texts

    labels = labels_of(root, argv[4:6])
    result = merge_texts(_read(base_path), _read(ours_path), _read(theirs_path),
                         labels=labels, reserve_ic=lambda: reserve_ic(root))
    with open(ours_path, "wb") as handle:
        handle.write(result.text.encode("utf-8"))
    for note in result.notes:
        print(note, file=sys.stderr)
    return result.exit
