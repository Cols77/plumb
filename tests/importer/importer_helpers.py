"""Shared helpers for the importer completion tests (next-plan 9).

The source tree is a copy of real pi-agent-factory files (``tests/bridge/fixtures/pi_factory``,
read once from the pi-agent-factory checkout), so a test may edit its copy freely.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "bridge" / "fixtures" / "pi_factory"
HEAD = "0123456789abcdef0123456789abcdef01234567"
CONSENT_DIR = ".factory/planning/JEV-REVIEW-INTEGRATION/consent"


def make_source(tmp_path: Path) -> Path:
    """A pi-agent-factory-shaped source tree with a ``.git`` HEAD file."""
    source = tmp_path / "pi-src"
    shutil.copytree(FIXTURES, source)
    git = source / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text(HEAD + "\n", encoding="utf-8")
    return source


def snapshot(root: Path, skip: tuple[str, ...] = ()) -> dict[str, str]:
    """``{relative path: sha256}`` of every file under ``root`` (bytes and mtimes)."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(s) for s in skip):
            continue
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest() + f":{path.stat().st_mtime_ns}"
    return out


def plumb_files(repo: Path) -> dict[str, str]:
    """The target's ``.plumb`` tree, without the rebuildable caches."""
    return snapshot(repo / ".plumb", skip=("cache/", "session/"))


def rewrite(path: Path, old: str, new: str) -> None:
    data = path.read_bytes()
    assert old.encode() in data, f"{old!r} not in {path}"
    path.write_bytes(data.replace(old.encode(), new.encode()))


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
