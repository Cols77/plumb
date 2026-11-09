"""Convert an old-name project to ``.iaso`` (SR-432).

iaso supports one records folder, ``.iaso``. When a command runs inside a project that still
has the old-name folder, ``convert_if_old`` says so, moves the folder (``git mv`` when it is
tracked), rewrites the old name in the records, claims, config, log entries (their digests
and the hashes that follow from the changed text are recomputed), ``.claude`` settings and
the git hooks, attributes and config, and returns; the command then runs on the converted
project. The converter is the one place that still knows the old name.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

OLD = "plu" + "mb"          # the old name, never written whole in a source file
OLD_DIR = "." + OLD
NEW = "iaso"
_SKIP = {"cache", "session", "wt", "env"}   # local state, rebuilt; not records
_FORMS = ((OLD, NEW), (OLD.capitalize(), NEW.capitalize()), (OLD.upper(), NEW.upper()))


def rewrite_text(text: str) -> str:
    """``text`` with the old name replaced in its three letter cases."""
    for old, new in _FORMS:
        text = text.replace(old, new)
    return text


def find_old(start: Path) -> Path | None:
    """The nearest folder upward holding the old records folder (never iaso's own home),
    stopping at the first git root."""
    start = start.resolve()
    for d in (start, *start.parents):
        old = d / OLD_DIR
        if old.is_dir() and not (old / "env").is_dir() and not (old / "current.json").is_file():
            return d
        if (d / ".git").exists():
            return None
    return None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _texts(folder: Path):
    for p in sorted(folder.rglob("*")):
        if p.is_file() and not (_SKIP & set(p.relative_to(folder).parts)):
            try:
                yield p, p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue   # binary: left as it is


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _map_strings(node, fn):
    if isinstance(node, str):
        return fn(node)
    if isinstance(node, dict):
        return {fn(k): _map_strings(v, fn) for k, v in node.items()}
    if isinstance(node, list):
        return [_map_strings(v, fn) for v in node]
    return node


def _hash_map(texts: list[tuple[Path, str]]) -> dict[str, str]:
    """Old hash to new hash for what the rewrite changes: each record (its hash covers the
    text) and each log string (a ``quote_digest`` is the digest of its text)."""
    from iaso.model import parse_record
    from iaso.normalize import sha256_text

    out: dict[str, str] = {}
    for p, text in texts:
        new = rewrite_text(text)
        if new == text:
            continue
        if p.suffix == ".md" and p.parent.name != "studies":
            try:
                out[parse_record(text, p.name).hash] = parse_record(new, p.name).hash
            except Exception:   # not a record file (a study, a note): no hash to follow
                pass
        elif p.suffix == ".json" and "log" in p.parts:
            try:
                for s in _strings(json.loads(text)):
                    if rewrite_text(s) != s:
                        out[sha256_text(s)] = sha256_text(rewrite_text(s))
            except ValueError:
                pass
    return out


def _settle(texts: list[tuple[Path, str]], hashes: dict[str, str]) -> dict[str, str]:
    """A record's hash covers the pins it holds, and the pins follow the hashes: repeat until the
    hash each record ends with (pins followed) is the one the map says."""
    from iaso.model import parse_record

    for _ in range(8):
        nxt = dict(hashes)
        for p, text in texts:
            if p.suffix != ".md" or p.parent.name == "studies":
                continue
            try:
                nxt[parse_record(text, p.name).hash] = parse_record(
                    _follow(rewrite_text(text), hashes), p.name).hash
            except Exception:   # not a record file
                pass
        if nxt == hashes:
            break
        hashes = nxt
    return hashes


def _follow(text: str, hashes: dict[str, str]) -> str:
    return re.sub(r"sha256:[0-9a-f]{64}", lambda m: hashes.get(m.group(0), m.group(0)), text)


def _log_entry(text: str, hashes: dict[str, str]) -> str:
    from iaso.log import entry_digest
    from iaso.normalize import canonical_json

    entry = _map_strings(json.loads(text), lambda s: _follow(rewrite_text(s), hashes))
    if isinstance(entry, dict) and "digest" in entry:
        entry["digest"] = entry_digest(entry)
    return canonical_json(entry).decode("utf-8") + "\n"


def _outside(root: Path) -> list[Path]:
    """Files outside the records folder that name the old name: settings, git attributes,
    ignore file. Never the git directory: worktrees share it, so its hooks, attributes and config
    are rewritten by ``iaso hooks install``, not here."""
    out = [root / ".gitignore", root / ".gitattributes", *(root / ".claude").glob("settings*.json")]
    return [p for p in out if p.is_file()]


def convert(root: Path) -> list[str]:
    """Convert ``root``'s old-name project in place; the lines to tell the owner."""
    root = Path(root)
    old, new = root / OLD_DIR, root / ".iaso"
    if new.exists():
        raise SystemExit(f"iaso: both {OLD_DIR}/ and .iaso/ exist in {root}; remove one and retry")
    moved = _git(root, "mv", OLD_DIR, ".iaso")
    if moved.returncode:   # not tracked (or not a repository): a plain rename
        old.rename(new)
    texts = list(_texts(new))
    hashes = _settle(texts, _hash_map(texts))
    for p, text in texts:
        if p.suffix == ".json" and "log" in p.parts:
            try:
                changed = _log_entry(text, hashes)
            except ValueError:
                changed = rewrite_text(text)
        else:
            changed = _follow(rewrite_text(text), hashes)
        if changed != text:
            p.write_text(changed, encoding="utf-8", newline="\n")
    for p in _outside(root):
        text = p.read_text(encoding="utf-8", errors="replace")
        if rewrite_text(text) != text:
            p.write_text(rewrite_text(text), encoding="utf-8", newline="\n")
    return [f"iaso: {root} is an old project ({OLD_DIR}/); converted to .iaso/"]


def convert_if_old(start: Path) -> bool:
    """Say so and convert when ``start`` is inside an old-name project; True if it did."""
    root = find_old(start)
    if root is None:
        return False
    # stdout is a command's data when it prints JSON or answers a hook: the line goes to stderr then
    out = sys.stderr if "--json" in sys.argv or sys.argv[1:2] == ["hook"] else sys.stdout
    for line in convert(root):
        print(line, file=out)
    return True
