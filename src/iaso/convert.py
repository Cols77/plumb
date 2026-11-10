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


def _git(root: Path, *args: str):
    import subprocess   # lazy: every command checks for an old project, and the hook fast path imports no subprocess

    from iaso.background import child_env

    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          env=child_env())   # a hook's git variables must not redirect root


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
    """Old hash to new hash for each record the rewrite changes (its hash covers the text). A log
    digest of an owner's message (``prompt_digest``, ``trail``) names what they typed: it stays."""
    from iaso.model import parse_record

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


def _pairs(old, new):
    """The (old, new) dicts holding both a ``quote`` and a ``quote_digest``."""
    if isinstance(old, dict) and isinstance(new, dict):
        if isinstance(old.get("quote"), str) and "quote_digest" in old and "quote_digest" in new:
            yield old, new
        for k, v in old.items():
            yield from _pairs(v, new.get(rewrite_text(k)))
    elif isinstance(old, list) and isinstance(new, list):
        for u, v in zip(old, new):
            yield from _pairs(u, v)


def _log_entry(text: str, hashes: dict[str, str]) -> str:
    from iaso.log import entry_digest
    from iaso.normalize import canonical_json, sha256_text

    old = json.loads(text)
    entry = _map_strings(old, lambda s: _follow(rewrite_text(s), hashes))
    if isinstance(old, dict) and old.get("kind") == "premise" and isinstance(old.get("payload"), dict):
        entry["payload"]["text"] = old["payload"].get("text")   # the owner's message, verbatim: its digest names it
    for was, now in _pairs(old, entry):   # a quote_digest is the digest of its own, rewritten, quote
        if was.get("quote_digest") == sha256_text(str(was.get("quote"))):
            now["quote_digest"] = sha256_text(str(now["quote"]))
    if isinstance(entry, dict) and "digest" in entry:
        entry["digest"] = entry_digest(entry)
    return canonical_json(entry).decode("utf-8") + "\n"


def _unrewrite(text: str) -> str:
    for old, new in _FORMS:
        text = text.replace(new, old)
    return text


def repair_messages(root: Path) -> list[str]:
    """Repair what a converter before this fix did to the untracked local log of ``root``: a
    premise (an owner's message) gets its verbatim text back, and a digest of a message that was
    remapped to the digest of the rewritten text gets its own back in every entry. Each change is
    checked: the old text's digest must be the entry's, or appear in the session files. Approval
    entries are never read or written."""
    from iaso.log import entry_digest
    from iaso.normalize import canonical_json, sha256_text

    from iaso.approvals import prompt_digest

    root = Path(root)
    log, session = root / ".iaso" / "log", root / ".iaso" / "session"
    tracked = set(_git(root, "ls-files", "-z", ".iaso/log").stdout.split("\0"))
    known: set[str] = set()   # every digest the (never rewritten) session files hold
    back: dict[str, str] = {}  # a remapped message digest -> its own, from the session's message texts
    for p in session.rglob("*") if session.is_dir() else ():
        if not p.is_file() or p.stat().st_size >= 50_000_000:
            continue
        raw = p.read_text(encoding="utf-8", errors="ignore")
        known.update(re.findall(r"sha256:[0-9a-f]{64}", raw))
        if p.suffix == ".json" and OLD in raw.lower():
            try:
                for text in _strings(json.loads(raw)):
                    if OLD in text.lower() and prompt_digest(text) in raw:
                        for remapped in (sha256_text(rewrite_text(text)), prompt_digest(rewrite_text(text))):
                            back[remapped] = prompt_digest(text)
            except ValueError:
                pass
    files = [p for p in log.rglob("*.json") if p.parent.name != "approval"
             and p.relative_to(root).as_posix() not in tracked]
    texts = 0
    for p in files:
        if p.parent.name != "premise":
            continue
        entry = json.loads(p.read_text(encoding="utf-8"))
        pay = entry.get("payload") or {}
        text, digest = pay.get("text"), pay.get("digest")
        if not isinstance(text, str) or not isinstance(digest, str) or _unrewrite(text) == text:
            continue
        old = _unrewrite(text)
        if digest == prompt_digest(old):
            pass                              # digest kept, text rewritten: give the text back
        elif digest in (sha256_text(text), prompt_digest(text)) and prompt_digest(old) in known:
            back[digest] = prompt_digest(old)  # digest remapped: give both back
        else:
            continue
        pay["text"], pay["digest"] = old, prompt_digest(old)
        entry["digest"] = entry_digest(entry)
        p.write_text(canonical_json(entry).decode("utf-8") + "\n", encoding="utf-8", newline="\n")
        texts += 1
    fixed = 0
    for p in files:
        if p.parent.name == "premise" or not back:
            continue
        raw = p.read_text(encoding="utf-8")
        if not any(k in raw for k in back):
            continue
        entry = _map_strings(json.loads(raw), lambda s: back.get(s, s))
        if isinstance(entry, dict) and "digest" in entry:
            entry["digest"] = entry_digest(entry)
        p.write_text(canonical_json(entry).decode("utf-8") + "\n", encoding="utf-8", newline="\n")
        fixed += 1
    _rename_migrated(root / ".iaso")
    return [f"iaso: repaired {texts} owner messages and {fixed} entries naming them"]


def _rename_migrated(new: Path) -> None:
    """A migrated entry's file name ends in characters of its digest, which the rewrite changed."""
    from iaso.log import is_migrated_name, parse_name

    for p in (new / "log").rglob("*.json"):
        if not is_migrated_name(p.name):
            continue
        digest = str(json.loads(p.read_text(encoding="utf-8")).get("digest", "")).split(":", 1)[-1]
        stamp, micros, suffix = parse_name(p.name)
        if digest[8:16] != suffix:
            p.rename(p.with_name(p.name.replace(f"-{suffix}.json", f"-{digest[8:16]}.json")))


def _outside(root: Path) -> list[Path]:
    """Files outside the records folder that name the old name: settings, git attributes,
    ignore file. Never the git directory: worktrees share it, so its hooks, attributes and config
    are rewritten by ``iaso hooks install``, not here."""
    out = [root / ".gitignore", root / ".gitattributes", *(root / ".claude").glob("settings*.json")]
    return [p for p in out if p.is_file()]


def _merge_dirs(src: Path, dst: Path, left: list[str]) -> None:
    """Move what ``src`` holds into ``dst``: a path ``dst`` lacks is renamed over, folders merge,
    a file both hold stays in ``src`` (named in ``left``)."""
    for child in sorted(src.iterdir()):
        target = dst / child.name
        if not target.exists() and not target.is_symlink():
            child.rename(target)
        elif child.is_dir() and target.is_dir() and not child.is_symlink():
            _merge_dirs(child, target, left)
        else:
            left.append(str(child))
    try:
        src.rmdir()
    except OSError:
        pass


def _adopt_leftovers(root: Path, old: Path, new: Path) -> tuple[dict[str, str], list[str]]:
    """A merge into a checkout that keeps untracked state (sessions, local log kinds, caches,
    work copies) put the tracked ``.iaso`` files beside the old folder: move each registered
    work copy of ``old/wt`` with ``git worktree move``, then the rest into ``new``. Returns the
    old-hash to new-hash map of the records the old folder tracked at HEAD (an untracked record
    pins them) and the lines to tell the owner."""
    import io
    import tarfile

    notes: list[str] = []
    wt_old = (old / "wt").resolve()
    listing = _git(root, "worktree", "list", "--porcelain").stdout
    for line in listing.splitlines():
        if not line.startswith("worktree "):
            continue
        path = Path(line[9:])
        if path.resolve().parent != wt_old:
            continue
        (new / "wt").mkdir(parents=True, exist_ok=True)
        moved = _git(root, "worktree", "move", str(path), str(new / "wt" / path.name))
        if moved.returncode:
            notes.append(f"iaso: could not move the work copy {path}: {moved.stderr.strip()}")
    seed: dict[str, str] = {}
    import subprocess

    from iaso.background import child_env

    archive = subprocess.run(["git", "-C", str(root), "archive", "HEAD", OLD_DIR],
                             capture_output=True, env=child_env())
    if archive.returncode == 0:
        texts = []
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            for member in tar:
                if member.isfile() and member.name.endswith((".md", ".json")):
                    try:
                        texts.append((Path(member.name), tar.extractfile(member).read().decode("utf-8")))
                    except (UnicodeDecodeError, OSError):
                        continue
        seed = _hash_map(texts)
    left: list[str] = []
    _merge_dirs(old, new, left)
    if left:
        notes.append(f"iaso: {len(left)} files stayed in {OLD_DIR}/ because .iaso/ holds one: {left[:3]}")
    return seed, notes


def _carry_user_config() -> list[str]:
    """Copy the user-level files (the judge's key store and settings) from the old config folder to
    iaso's, keeping their modes and never reading or printing them; one that exists is kept."""
    import os
    import shutil

    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    old, new = base / OLD, base / "iaso"
    if not old.is_dir():
        return []
    carried = 0
    for src in sorted(p for p in old.rglob("*") if p.is_file()):
        dst = new / src.relative_to(old)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            carried += 1
    return [f"iaso: copied {carried} user-level settings files from {old} to {new}"] if carried else []


def convert(root: Path) -> list[str]:
    """Convert ``root``'s old-name project in place; the lines to tell the owner."""
    root = Path(root)
    old, new = root / OLD_DIR, root / ".iaso"
    seed: dict[str, str] = {}
    notes: list[str] = []
    if new.exists():   # a merge placed the tracked .iaso files; the old folder keeps the untracked rest
        seed, notes = _adopt_leftovers(root, old, new)
    else:
        moved = _git(root, "mv", OLD_DIR, ".iaso")
        if moved.returncode:   # not tracked (or not a repository): a plain rename
            old.rename(new)
    texts = list(_texts(new))
    hashes = _settle(texts, {**seed, **_hash_map(texts)})
    for p, text in texts:
        if p.suffix == ".jsonl" and "log" in p.parts:   # an archive segment: one entry a line
            changed = "".join(_log_entry(line, hashes) for line in text.splitlines() if line.strip())
        elif p.suffix == ".json" and "log" in p.parts:
            try:
                changed = _log_entry(text, hashes)
            except ValueError:
                changed = rewrite_text(text)
        else:
            changed = _follow(rewrite_text(text), hashes)
        if changed != text:
            p.write_text(changed, encoding="utf-8", newline="\n")
    _rename_migrated(new)
    for p in sorted(new.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        if OLD in p.name and not _SKIP & set(p.relative_to(new).parts):   # file names follow the text
            p.rename(p.with_name(rewrite_text(p.name)))
    for p in _outside(root):
        text = p.read_text(encoding="utf-8", errors="replace")
        if rewrite_text(text) != text:
            p.write_text(rewrite_text(text), encoding="utf-8", newline="\n")
    return [f"iaso: {root} is an old project ({OLD_DIR}/); converted to .iaso/", *notes,
            *_carry_user_config(),
            "iaso: if Claude Code lists the old plugin, run /plugin marketplace remove " + OLD
            + ", then /plugin marketplace add <this repository> and /plugin install iaso@iaso"]


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
