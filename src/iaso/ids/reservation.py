"""``reserve``, ``peek``, ``observe``, ``state`` and ``sync`` (sp6 4.2 to 4.4; SR-070).

``reserve`` is the one allocation function: every writer of a new record calls it through
``Store.next_id``. A number is handed out only after the compare-and-swap of
``refs/iaso/ids`` succeeded, so two worktrees never receive one ID. Outside git it falls
back to the highest local number plus one and says the ID is not reserved.
"""

from __future__ import annotations

import random
import re
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from iaso.contracts import IdState
from iaso.ids import ref as _ref
from iaso.paths import IasoPaths, state_dir

PREFIX = {"intent": "INT", "requirement": "SR", "decision": "DEC", "feature": "FEAT",
          "nc": "NC", "conflict": "IC"}
DIRS = {"INT": "intents", "SR": "requirements", "DEC": "decisions", "FEAT": "features",
        "NC": "ncs"}
RETRIES = 50
RETRY_S = 3.0
PAUSE_S = (0.005, 0.05)
_NUMBERED = re.compile(r"^(INT|SR|DEC|FEAT|NC|IC)-(\d+)$")
_FILE = re.compile(r"(?:^|/)(INT|SR|DEC|FEAT|NC|IC)-(\d+)\.md$")
_BRANCH: dict[str, str] = {}


class IdBusy(RuntimeError):
    """The ref kept moving for the whole retry budget (exit 2)."""

    exit_code = 2


def prefix_of(kind: str) -> str:
    if kind in PREFIX:
        return PREFIX[kind]
    if kind in PREFIX.values():
        return kind
    raise ValueError(f"unknown record kind {kind!r}")


def width(prefix: str) -> int:
    return 4 if prefix == "NC" else 3


def fmt(prefix: str, number: int) -> str:
    return f"{prefix}-{number:0{width(prefix)}d}"


def split(record_id: str) -> tuple[str, int] | None:
    match = _NUMBERED.match(str(record_id))
    return (match.group(1), int(match.group(2))) if match else None


def highest(ids: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for record_id in ids:
        parts = split(record_id)
        if parts is not None:
            out[parts[0]] = max(out.get(parts[0], 0), parts[1])
    return out


def _local_ids(paths: IasoPaths) -> list[str]:
    """The record IDs of this worktree, from the record files' names (no YAML)."""
    out: list[str] = []
    for directory in DIRS.values():
        folder = paths.iaso / directory
        if folder.is_dir():
            out += [f.stem for f in folder.glob("*.md")]
    return out


def _local_high(paths: IasoPaths, local: Iterable[str] | None) -> dict[str, int]:
    ids = list(local) if local is not None else []
    return highest([*ids, *_local_ids(paths)])


def _settings(paths: IasoPaths) -> tuple[int, float]:
    """``ids.retries`` and ``ids.retry_s`` from the config when it has them (sp6 12)."""
    try:
        from iaso.config import load_config

        section = getattr(load_config(paths.root), "ids", None)
    except Exception:  # noqa: BLE001 - the defaults hold
        section = None
    retries = getattr(section, "retries", None) if section is not None else None
    retry_s = getattr(section, "retry_s", None) if section is not None else None
    return (int(retries) if isinstance(retries, int) else RETRIES,
            float(retry_s) if isinstance(retry_s, (int, float)) else RETRY_S)


def branch_tips_high(root: Path) -> dict[str, int]:
    """The highest number per prefix among the record files of every local branch tip
    (``for-each-ref`` once, one ``ls-tree`` per distinct tip): the seed of 4.3."""
    tips = _ref.git(root, "for-each-ref", "--format=%(objectname)", "refs/heads")
    if tips.returncode != 0:
        return {}
    out: dict[str, int] = {}
    for tip in dict.fromkeys(tips.stdout.decode().split()):
        listed = _ref.git(root, "ls-tree", "-r", "--name-only", "-z", tip, "--",
                             f"{state_dir(root).name}/")
        if listed.returncode != 0:
            continue
        for name in listed.stdout.decode("utf-8", "replace").split("\0"):
            match = _FILE.search(name)
            if match:
                prefix, number = match.group(1), int(match.group(2))
                out[prefix] = max(out.get(prefix, 0), number)
    return out


def _merge_high(*highs: Mapping[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for high in highs:
        for prefix, number in high.items():
            out[prefix] = max(out.get(prefix, 0), int(number))
    return out


def _start(paths: IasoPaths, oid: str | None, data: dict[str, Any]) -> dict[str, Any]:
    """The ref's data, seeded from every local branch tip when the ref does not exist."""
    if oid is not None:
        return data
    seeded = _ref.empty()
    seeded["high"] = _merge_high(branch_tips_high(paths.root), highest(_local_ids(paths)))
    return seeded


def _branch(root: Path) -> str:
    key = str(root)
    if key not in _BRANCH:
        _BRANCH[key] = _ref.branch(root)
    return _BRANCH[key]


def _swap(paths: IasoPaths, change: Any, message: Any) -> Any:
    """The compare-and-swap loop: ``change(oid, data) -> (new data | None, result)``; None
    means nothing to write. Retries a moved ref after a 5 to 50 ms pause, within the budget."""
    retries, budget = _settings(paths)
    deadline = time.monotonic() + budget
    for _attempt in range(max(1, retries)):
        oid, data = _ref.read(paths.root)
        data = _start(paths, oid, data)
        new, result = change(oid, data)
        if new is None:
            return result
        try:
            _ref.update(paths.root, new, oid, message(result))
            return result
        except _ref.Moved:
            if time.monotonic() >= deadline:
                break
            time.sleep(random.uniform(*PAUSE_S))
    from iaso.present.owner_text import ID_BUSY

    raise IdBusy(ID_BUSY)


def reserve(paths: IasoPaths, kind: str, count: int = 1, *,
            local: Iterable[str] | None = None) -> list[str]:
    """Reserve ``count`` new IDs of ``kind`` (a record kind, or "conflict" for ``IC``) in
    one compare-and-swap; ``local`` are IDs the caller already knows in this worktree."""
    prefix = prefix_of(kind)
    count = max(1, int(count))
    local_high = _local_high(paths, local).get(prefix, 0)
    try:
        _ref.read(paths.root)
    except _ref.NoGit:
        ids = [fmt(prefix, local_high + i + 1) for i in range(count)]
        from iaso.present.owner_text import ID_UNRESERVED

        print(ID_UNRESERVED.format(ids=", ".join(ids)), file=sys.stderr)
        return ids
    root = paths.root
    branch = _branch(root)

    def change(_oid: str | None, data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        start = max(int(data["high"].get(prefix, 0)), local_high)
        ids = [fmt(prefix, start + i + 1) for i in range(count)]
        new = {"v": _ref.SCHEMA, "high": {**data["high"], prefix: start + count},
               "recent": (list(data["recent"]) + [
                   {"id": i, "branch": branch, "worktree": root.as_posix(), "at": _now()}
                   for i in ids])[-_ref.RECENT_MAX:]}
        return new, ids

    return _swap(paths, change, lambda ids: f"iaso: reserve {', '.join(ids)}")


def peek(paths: IasoPaths, kind: str, *, local: Iterable[str] | None = None) -> str:
    """The ID ``reserve`` would hand out now, without writing anything (previews)."""
    prefix = prefix_of(kind)
    local_high = _local_high(paths, local).get(prefix, 0)
    try:
        oid, data = _ref.read(paths.root)
    except _ref.NoGit:
        return fmt(prefix, local_high + 1)
    data = _start(paths, oid, data)
    return fmt(prefix, max(int(data["high"].get(prefix, 0)), local_high) + 1)


def observe(paths: IasoPaths, ids: Iterable[str]) -> None:
    """Raise the ref's ``high`` to cover ``ids`` kept from elsewhere (the importer, a
    merge, ``iaso ids sync``). Nothing is written when ``high`` already covers them, and
    nothing at all outside git."""
    wanted = highest(ids)
    if not wanted:
        return
    try:
        _ref.read(paths.root)
    except _ref.NoGit:
        return
    _observe(paths, wanted)


def _observe(paths: IasoPaths, wanted: Mapping[str, int]) -> None:
    def change(oid: str | None, data: dict[str, Any]) -> tuple[dict[str, Any] | None, None]:
        high = _merge_high(data["high"], wanted)
        if oid is not None and high == data["high"]:
            return None, None
        return {"v": _ref.SCHEMA, "high": high, "recent": list(data["recent"])}, None

    _swap(paths, change, lambda _: "iaso: observe")


def sync(paths: IasoPaths) -> IdState:
    """``iaso ids sync``: re-run the seed scan (every local branch tip and this worktree)
    and raise ``high`` to cover it."""
    try:
        _ref.read(paths.root)
    except _ref.NoGit:
        return state(paths)
    _observe(paths, _merge_high(branch_tips_high(paths.root), highest(_local_ids(paths))))
    return state(paths)


def state(paths: IasoPaths) -> IdState:
    try:
        oid, data = _ref.read(paths.root)
    except _ref.NoGit:
        return IdState(high=highest(_local_ids(paths)), reserved=False)
    return IdState(high=dict(data["high"]), recent=tuple(data["recent"]), reserved=True,
                   oid=oid)


def _now() -> str:
    from iaso.normalize import utc_now

    return utc_now()
