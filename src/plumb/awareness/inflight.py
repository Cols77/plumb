"""Intent in flight: the ``refs/plumb/claims`` register every worktree shares (ruling R17,
SR-080).

When a worktree captures a change to an existing record, or new intent in a feature, it
records a lightweight CLAIM: the records (title, hash, the words of this version), their
features, the branch and a one-line summary. The register is one JSON blob that the ref
``refs/plumb/claims`` names. Like ``refs/plumb/ids`` it lives in the common git directory, so
every worktree of the clone sees it, and it is written only by git's own compare-and-swap
(``git update-ref <ref> <new> <old>``): two writers never lose each other's claim.

A claim is a signal, never a lock: nothing reads it to refuse anything. It clears when its
branch is deleted (abandoned), when its branch MERGED (its tip is reachable from the default
branch AND the branch has commits of its own there: see ``merged``), or when the owner drops
that work. Each RECORD of a claim also clears on its own once it landed (``_unlanded``): the
commit that wrote it (``commit``, stamped when the claim moves to a tip holding that version)
is reachable from the default branch, or the default branch holds exactly the claimed
version (same hash). So a branch merged and then continued never holds its merged records
against a later change on the default branch. A branch that only took the default
branch's commits (a fast-forward to ``main``) keeps its claim: its intent is still in
flight. Readers on a hook path read the ref and the blob from git's files (a loose object)
with no git process, through a cache keyed by the blob's ID.

Entry shape::

    {"v": 1, "claims": [{"id": "feat-x:INT-022", "branch": "feat-x", "worktree": "...",
      "head": "<sha at the claim>", "base": "<fork point from the default branch>",
      "own": "<the branch's own newest commit, or empty>", "at": "...", "summary": "...",
      "intent": "INT-022",
      "records": {"SR-005": {"title": "...", "hash": "sha256:...", "text": "...",
                             "feature": "FEAT-002", "path": ".plumb/requirements/SR-005.md",
                             "commit": "<the branch commit first holding this version>"}},
      "features": ["FEAT-002"],
      "conflicts": [{"record": "SR-005", "branch": "main", "with": "main:INT-030",
                     "dec": "DEC-031", "question": "...", "state": "proposed",
                     "chosen": ""}]}]}

``chosen`` is always branch-neutral ("feat-x's version", "both, combined" or the owner's own
words), never "this request's version": every branch reads the one answer the same way.
"""

from __future__ import annotations

import copy
import json
import os
import random
import subprocess
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from plumb.awareness import gitfiles
from plumb.contracts import Overlap

REF = "refs/plumb/claims"
VERSION = 1
CACHE = "inflight.json"
MERGED_CACHE = "inflight-merged.json"
LANDED_CACHE = "inflight-landed.json"
LANDED_MAX = 512
RETRIES = 50
RETRY_S = 3.0
GIT_TIMEOUT_S = 5.0
TEXT_WIDTH = 240


class InflightBusy(Exception):
    """The register kept moving under this writer (``RETRIES`` tries or ``RETRY_S``)."""


def empty() -> dict[str, Any]:
    return {"v": VERSION, "claims": []}


def _clip(text: str, width: int = TEXT_WIDTH) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return empty()
    if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
        return empty()
    data["claims"] = [c for c in data["claims"] if isinstance(c, dict) and c.get("branch")]
    return data


def _canonical(data: Mapping[str, Any]) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n").encode("utf-8")


def _git(root: Path, *args: str, stdin: bytes | None = None) -> tuple[int, bytes]:
    try:
        result = subprocess.run(["git", *args], cwd=root, input=stdin, capture_output=True,
                                timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return 1, b""
    return result.returncode, result.stdout


# ------------------------------------------------------------------ reading


def _cache_path(root: Path, name: str = CACHE) -> Path:
    return Path(root) / ".plumb" / "cache" / name


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except OSError:
        pass


def read(root: Path, *, allow_git: bool = False) -> tuple[str | None, dict[str, Any]]:
    """``(blob id, register)``. Without ``allow_git`` (a hook path) only git's files are
    read: the ref file, then the cache or the loose object; a packed blob not in the cache
    reads as the last cached register."""
    root = Path(root)
    common = gitfiles.common_dir(root)
    if common is None:
        return None, empty()
    oid = gitfiles.resolve_ref(common, REF)
    if oid is None:
        return None, empty()
    cached = _read_json(_cache_path(root))
    if isinstance(cached, dict) and cached.get("oid") == oid \
            and isinstance(cached.get("data"), dict):
        return oid, cached["data"]
    loose = gitfiles.read_loose_object(common, oid)
    raw: bytes | None = loose[1] if loose and loose[0] == "blob" else None
    if raw is None and allow_git:
        code, out = _git(root, "cat-file", "blob", oid)
        raw = out if code == 0 else None
    if raw is None:
        data = cached.get("data") if isinstance(cached, dict) else None
        return oid, data if isinstance(data, dict) else empty()
    data = _parse(raw)
    _write_json(_cache_path(root), {"oid": oid, "data": data})
    return oid, data


def _merged_cache(root: Path) -> dict[str, bool]:
    data = _read_json(_cache_path(root, MERGED_CACHE))
    return {str(k): bool(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _expired(deadline: Any) -> bool:
    try:
        return bool(deadline is not None and deadline.expired())
    except Exception:  # noqa: BLE001
        return False


def _first_parents(root: Path, lower: str, tip: str) -> list[str] | None:
    code, out = _git(root, "rev-list", "--first-parent", f"{lower}..{tip}")
    return out.decode().split() if code == 0 else None


def merged(root: Path, claim: Mapping[str, Any], tip: str, default_tip: str) -> bool:
    """Whether ``claim``'s branch (now at ``tip``) MERGED into the default branch (now at
    ``default_tip``): its tip is reachable from the default tip AND the branch has commits of
    its own there. Its own commits are ``own`` (recorded when the claim was written on a
    commit the default branch did not hold), else the commits on the branch's first-parent
    line since its fork point (``base``; ``head`` for an older claim) that are not on the
    default branch's first-parent line: a branch that only fast-forwarded to the default
    branch has none, and keeps its claim. At most four git calls."""
    root = Path(root)
    code, _ = _git(root, "merge-base", "--is-ancestor", tip, default_tip)
    if code != 0:
        return False
    own = str(claim.get("own") or "")
    if own:
        code, _ = _git(root, "merge-base", "--is-ancestor", own, default_tip)
        if code == 0:
            return True
    lower = str(claim.get("base") or claim.get("head") or "")
    if not lower:
        return True
    branch_line = _first_parents(root, lower, tip)
    if not branch_line:
        return False
    default_line = set(_first_parents(root, lower, default_tip) or ())
    return any(commit not in default_line for commit in branch_line)


def _merged_key(claim: Mapping[str, Any], tip: str, default_tip: str | None) -> str:
    return ":".join([tip, str(default_tip), str(claim.get("base") or claim.get("head") or ""),
                     str(claim.get("own") or "")])


def _nothing_own(claim: Mapping[str, Any], tip: str) -> bool:
    """Known without git: the branch has no commit of its own since the claim (its tip is
    its fork point, or it has not moved and held none when the claim was written)."""
    if "base" not in claim:
        return False                # an older claim: only git can tell
    return tip == claim.get("base") or (tip == claim.get("head") and not claim.get("own"))


def active(root: Path, data: Mapping[str, Any], *, default: str, allow_git: bool = False,
           deadline: Any = None, paths: Mapping[str, str] | None = None
           ) -> list[dict[str, Any]]:
    """The claims still in flight: a deleted branch's claims are gone (abandoned); a claim
    whose branch ``merged`` is gone; on the default branch itself a claim clears once a
    commit lands; and each record of a claim that landed on the default branch is gone
    (``_unlanded``; a claim left with no record and no raised conflict goes). The ONE
    reader every surface uses (capture, the clarify read-back, the stop hook's claim, the
    brief, status, the writers' pruning). The git checks run only with ``allow_git``,
    cached; without it an unknown case keeps its claim. ``paths``: record ID -> file, for
    an older claim whose records do not name their file."""
    common = gitfiles.common_dir(Path(root))
    if common is None:
        return []
    tips = gitfiles.branch_tips(common)
    default_tip = tips.get(default)
    known = _merged_cache(Path(root))
    learned = False
    out: list[dict[str, Any]] = []
    for claim in data.get("claims") or []:
        branch = str(claim.get("branch") or "")
        tip = tips.get(branch)
        if tip is None:
            continue  # the branch was deleted: the work was abandoned (or merged and removed)
        if branch == default:
            if tip != claim.get("head"):
                continue
            out.append(claim)
            continue
        if default_tip is None or _nothing_own(claim, tip):
            out.append(claim)
            continue
        key = _merged_key(claim, tip, default_tip)
        if key not in known and allow_git and not _expired(deadline):
            known[key] = merged(Path(root), claim, tip, default_tip)
            learned = True
        if known.get(key):
            continue
        out.append(claim)
    if learned:
        _write_json(_cache_path(Path(root), MERGED_CACHE), known)
    return _unlanded(Path(root), out, default=default, default_tip=default_tip,
                     allow_git=allow_git, deadline=deadline, paths=paths or {})


def _entry_path(record_id: str, entry: Mapping[str, Any], paths: Mapping[str, str]) -> str:
    return str(entry.get("path") or paths.get(record_id) or "")


def _records_at(root: Path, wanted: Iterable[tuple[str, str]]
                ) -> dict[tuple[str, str], Any] | None:
    """``{(rev, path): the parsed record of that file at rev, or None}`` (one ``git cat-file
    --batch``; a missing or unparsable file is None). None when git could not answer."""
    from plumb.model import parse_record

    specs = sorted({(rev, p) for rev, p in wanted if rev and p})
    if not specs:
        return {}
    code, out = _git(Path(root), "cat-file", "--batch",
                     stdin="".join(f"{rev}:{p}\n" for rev, p in specs).encode("utf-8"))
    if code != 0:
        return None
    found: dict[tuple[str, str], Any] = {}
    pos = 0
    for rev, path in specs:
        end = out.find(b"\n", pos)
        if end < 0:
            break
        header = out[pos:end].decode("utf-8", "replace").split(" ")
        pos = end + 1
        if len(header) != 3 or header[1] != "blob" or not header[2].isdigit():
            found[(rev, path)] = None
            continue
        size = int(header[2])
        body = out[pos:pos + size]
        pos += size + 1
        try:
            found[(rev, path)] = parse_record(body.decode("utf-8"), path)
        except Exception:  # noqa: BLE001 - not a record there
            found[(rev, path)] = None
    return found


def versions(root: Path, rev: str, paths: Iterable[str]) -> dict[str, str | None]:
    """``{path: the record hash of that file at rev, or None}`` (one ``git cat-file
    --batch``; a missing or unparsable file is None)."""
    if not rev:
        return {}
    found = _records_at(root, ((rev, p) for p in paths)) or {}
    return {path: (record.hash if record is not None else None)
            for (_rev, path), record in found.items()}


def _unlanded(root: Path, claims: list[dict[str, Any]], *, default: str,
              default_tip: str | None, allow_git: bool, deadline: Any,
              paths: Mapping[str, str]) -> list[dict[str, Any]]:
    """``claims`` without the records that LANDED on the default branch (R17: a claim
    clears when its branch merges): the commit stamped as writing that version
    (``commit``) is reachable from the default tip, or the default tip holds exactly the
    claimed version (same hash). Cached by the default tip, the file and the hash
    (``LANDED_CACHE``) and by the two commits (``publish.contains``); learned with
    ``allow_git`` (one ``git cat-file --batch``, one ``merge-base --is-ancestor`` per
    stamped commit). Claims of the default branch itself are left as they are."""
    if not default_tip or not claims:
        return claims
    from plumb.awareness.publish import contains

    cache = _cache_path(root, LANDED_CACHE)
    raw = _read_json(cache)
    known: dict[str, bool] = ({str(k): bool(v) for k, v in raw.items()}
                              if isinstance(raw, dict) else {})
    learn = allow_git and not _expired(deadline)

    def key(path: str, digest: str) -> str:
        return f"{default_tip}:{path}:{digest}"

    todo: dict[str, tuple[str, str]] = {}
    for claim in claims:
        if claim.get("branch") == default:
            continue
        for record_id, entry in (claim.get("records") or {}).items():
            if not isinstance(entry, Mapping):
                continue
            path, digest = _entry_path(record_id, entry, paths), str(entry.get("hash") or "")
            if path and digest and key(path, digest) not in known:
                todo[key(path, digest)] = (path, digest)
    if todo and learn:
        held = versions(root, default_tip, {path for path, _digest in todo.values()})
        if held:
            for k, (path, digest) in todo.items():
                known[k] = held.get(path) == digest
            _write_json(cache, dict(list(known.items())[-LANDED_MAX:]))
    out: list[dict[str, Any]] = []
    for claim in claims:
        records = claim.get("records") or {}
        if claim.get("branch") == default or not records:
            out.append(claim)
            continue
        kept: dict[str, Any] = {}
        for record_id, entry in records.items():
            if isinstance(entry, Mapping):
                path = _entry_path(record_id, entry, paths)
                digest = str(entry.get("hash") or "")
                if path and digest and known.get(key(path, digest)):
                    continue            # the default branch holds exactly this version
                commit = str(entry.get("commit") or "")
                if commit and contains(root, commit, default_tip, allow_git=learn):
                    continue            # the commit that wrote this version merged
            kept[record_id] = entry
        if len(kept) == len(records):
            out.append(claim)
            continue
        if not kept and not claim.get("conflicts"):
            continue
        out.append({**claim, "records": kept,
                    "features": sorted({str(e["feature"]) for e in kept.values()
                                        if isinstance(e, Mapping) and e.get("feature")})})
    return out


def fork(root: Path, head: str | None, branch: str | None, default: str
         ) -> dict[str, str]:
    """``{"base": fork point, "own": head when it holds commits the default branch does
    not, else ""}`` for a claim written at ``head`` (one git call)."""
    if not head:
        return {"base": "", "own": ""}
    common = gitfiles.common_dir(Path(root))
    default_tip = gitfiles.branch_tips(common).get(default) if common is not None else None
    if branch == default or not default_tip:
        return {"base": head, "own": ""}
    code, out = _git(Path(root), "merge-base", head, default_tip)
    base = out.decode().strip() if code == 0 else ""
    if not base:
        return {"base": head, "own": head}
    return {"base": base, "own": head if base != head else ""}


# ------------------------------------------------------------------ writing


def update(root: Path, mutate: Callable[[dict[str, Any]], dict[str, Any] | None], *,
           retries: int = RETRIES, retry_s: float = RETRY_S) -> dict[str, Any]:
    """Apply ``mutate`` to the register with compare-and-swap: read the ref, write the new
    blob, move the ref only if it still names the blob read; otherwise read again and
    retry (jittered), at most ``retries`` times or ``retry_s`` seconds of waiting between
    tries (``InflightBusy``).
    ``mutate`` returning None or an equal register writes nothing."""
    root = Path(root)
    waited = 0.0  # only the backoff counts: slow git under load must not end the tries
    for attempt in range(max(int(retries), 1)):
        code, out = _git(root, "rev-parse", "-q", "--verify", REF)
        old = out.decode().strip() if code == 0 and out.strip() else None
        current = empty()
        if old is not None:
            code, raw = _git(root, "cat-file", "blob", old)
            if code != 0:
                raise InflightBusy(f"cannot read {REF}")
            current = _parse(raw)
        changed = mutate(copy.deepcopy(current))
        if changed is None or _canonical(changed) == _canonical(current):
            return current
        code, blob = _git(root, "hash-object", "-w", "--stdin", stdin=_canonical(changed))
        new = blob.decode().strip()
        if code != 0 or not new:
            raise InflightBusy("cannot write the register blob")
        code, _ = _git(root, "update-ref", "-m", "plumb: intent in flight", REF, new,
                       old or gitfiles.ZERO_OID)
        if code == 0:
            _write_json(_cache_path(root), {"oid": new, "data": changed})
            return changed
        if waited > retry_s:
            break
        pause = random.uniform(0.005, 0.03) * (1 + min(attempt, 5))
        waited += pause
        time.sleep(pause)
    raise InflightBusy(f"{REF} kept moving")


def claim_id(branch: str, intent: str | None) -> str:
    return f"{branch}:{intent or '-'}"


def record_entry(record: Any) -> dict[str, str]:
    """What a claim keeps of one record: enough for another branch's card."""
    fields = getattr(record, "fields", {}) or {}
    text = (fields.get("statement") or fields.get("readback") or fields.get("chosen")
            or getattr(record, "title", ""))
    entry = {"title": str(getattr(record, "title", "")), "hash": str(getattr(record, "hash", "")),
             "text": _clip(str(text))}
    if fields.get("feature"):
        entry["feature"] = str(fields["feature"])
    if getattr(record, "path", ""):
        entry["path"] = str(record.path)
    return entry


def _one_holder(live: list[dict[str, Any]], mine: Mapping[str, Any],
                records: Iterable[str]) -> list[dict[str, Any]]:
    """A branch holds each record in ONE claim, at the version it wrote last: the records
    ``mine`` just wrote leave the branch's other claims (a capture claims under its intent,
    the stop hook under none, so one record could otherwise sit in two claims at two
    versions and be asked about twice, or against a stale version). A claim left with no
    record and no raised conflict goes."""
    written = set(records)
    out: list[dict[str, Any]] = []
    for claim in live:
        if claim is not mine and claim.get("branch") == mine.get("branch") and written:
            held = {k: v for k, v in (claim.get("records") or {}).items() if k not in written}
            if len(held) != len(claim.get("records") or {}):
                if not held and not claim.get("conflicts"):
                    continue
                claim["records"] = held
                claim["features"] = sorted({str(e["feature"]) for e in held.values()
                                            if isinstance(e, Mapping) and e.get("feature")})
        out.append(claim)
    return out


def record_claim(core: Any, *, records: Mapping[str, Mapping[str, str]], summary: str,
                 intent: str | None, conflicts: Iterable[Mapping[str, Any]] = (),
                 default: str | None = None) -> dict[str, Any] | None:
    """Add (or merge into) this branch's claim for ``intent``, pruning cleared claims in the
    same write. None on a detached HEAD or outside git (nothing to name the work by)."""
    from plumb.awareness.publish import default_branch

    root = Path(core.root)
    me = gitfiles.current(root)
    if me is None or not me.branch:
        return None
    default = default or default_branch(core)
    features = sorted({str(r["feature"]) for r in records.values() if r.get("feature")})
    key = claim_id(me.branch, intent)
    new_conflicts = [dict(c) for c in conflicts]
    where = fork(root, me.head, me.branch, default)
    paths = record_paths(core)
    at_tip = _tip_versions(root, me.branch, me.head, default, paths)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        live = active(root, data, default=default, allow_git=True, paths=paths)
        for claim in live:          # every claim of this branch moves with its tip
            if claim.get("branch") == me.branch and me.branch != default:
                claim.update({"head": me.head, **where})
                _stamp(claim, me.head, at_tip, paths)
        mine = next((c for c in live if c.get("id") == key), None)
        if mine is None:
            mine = {"id": key, "branch": me.branch, "intent": intent, "records": {},
                    "features": [], "conflicts": []}
            live.append(mine)
        mine.update({"worktree": root.resolve().as_posix(), "head": me.head, **where,
                     "at": _now(), "summary": _clip(summary, 120) or mine.get("summary", "")})
        mine["records"] = {**(mine.get("records") or {}), **{k: dict(v)
                                                             for k, v in records.items()}}
        mine["features"] = sorted(set(mine.get("features") or []) | set(features))
        live = _one_holder(live, mine, records)
        known = {(c.get("record"), c.get("with")) for c in mine.get("conflicts") or []}
        mine["conflicts"] = list(mine.get("conflicts") or []) + [
            c for c in new_conflicts if (c.get("record"), c.get("with")) not in known]
        data["claims"] = sorted(live, key=lambda c: str(c.get("id")))
        return data

    data = update(root, mutate)
    return next((c for c in data["claims"] if c.get("id") == key), None)


def moved_claims(register: Mapping[str, Any], branch: str | None, head: str | None,
                 default: str) -> bool:
    """Whether a claim of ``branch`` (not the default branch) was written at another commit
    than ``head`` (no git process)."""
    if not branch or not head or branch == default:
        return False
    return any(c.get("branch") == branch and c.get("head") != head
               for c in register.get("claims") or [])


def record_paths(core: Any) -> dict[str, str]:
    """Record ID -> file, from this checkout's index (for claims whose records do not name
    their file)."""
    try:
        return {i: str(r.path) for i, r in core.index().items() if getattr(r, "path", "")}
    except Exception:  # noqa: BLE001 - the claims' own paths still serve
        return {}


def _branch_paths(register: Mapping[str, Any], branch: str,
                  paths: Mapping[str, str]) -> set[str]:
    return {_entry_path(i, e, paths) for c in register.get("claims") or []
            if c.get("branch") == branch
            for i, e in (c.get("records") or {}).items() if isinstance(e, Mapping)} - {""}


def _tip_versions(root: Path, branch: str | None, head: str | None, default: str,
                  paths: Mapping[str, str]) -> dict[str, str | None]:
    """The version of each record this branch claims, as its tip ``head`` holds it (one git
    call, and only when one of its claims was written at another commit)."""
    if not branch or not head or branch == default:
        return {}
    _oid, register = read(root)
    if not moved_claims(register, branch, head, default):
        return {}
    return versions(root, head, _branch_paths(register, branch, paths))


def _stamp(claim: dict[str, Any], head: str | None, at_tip: Mapping[str, str | None],
           paths: Mapping[str, str], changing: Mapping[str, Any] | None = None) -> None:
    """A claim moved to ``head``: each record whose claimed version the tip holds is
    stamped with the commit that first held it (``commit``, kept when already stamped), so
    a merge of that commit clears it even after the branch moves on (``_unlanded``). With
    ``changing`` (the branch's ``changing.json``), a committed record the branch no longer
    changes since its merge base (the default branch holds that version: it landed, or was
    never changed) leaves the claim: the claim's records are rebuilt from what the branch
    still changes, never carried forward."""
    if not head or not at_tip:
        return
    still = None
    if changing is not None:
        still = {str(i) for i, item in (changing.get("records") or {}).items()
                 if isinstance(item, Mapping) and item.get("how") in ("edited", "new")}
    kept: dict[str, Any] = {}
    for record_id, entry in (claim.get("records") or {}).items():
        if isinstance(entry, Mapping):
            path = _entry_path(record_id, entry, paths)
            if path in at_tip and at_tip[path] == entry.get("hash"):
                if still is not None and record_id not in still:
                    continue                    # committed, and unchanged since the base
                if not entry.get("commit"):
                    entry = {**entry, "commit": head}
        kept[record_id] = entry
    claim["records"] = kept
    claim["features"] = sorted({str(e["feature"]) for e in kept.values()
                                if isinstance(e, Mapping) and e.get("feature")})


def refresh(core: Any, *, default: str | None = None,
            changing: Mapping[str, Any] | None = None) -> bool:
    """Move this branch's claims to its tip: ``head``, the fork point and its own newest
    commit, so a later merge of that commit clears them (``merged``); stamp each record the
    tip holds with its commit and drop the ones the branch no longer changes (``_stamp``,
    with ``changing``: this worktree's ``changing.json``). Writes only when a claim moved.
    Returns whether it wrote."""
    from plumb.awareness.publish import default_branch

    root = Path(core.root)
    me = gitfiles.current(root)
    if me is None or not me.branch:
        return False
    default = default or default_branch(core)
    _oid, register = read(root)
    if not moved_claims(register, me.branch, me.head, default):
        return False
    where = fork(root, me.head, me.branch, default)
    paths = record_paths(core)
    at_tip = versions(root, str(me.head), _branch_paths(register, me.branch, paths))
    if changing is not None and (changing.get("branch") != me.branch
                                 or changing.get("head") != me.head):
        changing = None                 # not this tip's: stamp only
    wrote = {"done": False}

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        live = active(root, data, default=default, allow_git=True, paths=paths)
        for claim in live:
            if claim.get("branch") == me.branch:
                claim.update({"head": me.head, **where})
                _stamp(claim, me.head, at_tip, paths, changing)
                wrote["done"] = True
        live = [c for c in live if c.get("branch") != me.branch or c.get("records")
                or c.get("conflicts")]
        data["claims"] = sorted(live, key=lambda c: str(c.get("id")))
        return data

    update(root, mutate)
    return wrote["done"]


def drop(core: Any, what: str) -> list[str]:
    """Remove the claims named by ``what`` (a claim ID or a branch): the owner dropped that
    work. Returns the removed claim IDs."""
    removed: list[str] = []

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        keep = []
        for claim in data.get("claims") or []:
            if what in (claim.get("id"), claim.get("branch")):
                removed.append(str(claim.get("id")))
            else:
                keep.append(claim)
        data["claims"] = keep
        return data

    update(Path(core.root), mutate)
    return removed


def neutral_chosen(chosen: str, raised_on: str | None) -> str:
    """The owner's answer in words every branch reads the same way: words naming "this
    side" (``owner_text.EARLY_RELATIVE``, as an older register or a relayed "keep this one"
    holds them) become ``"<raising branch>'s version"``. The one translation of an answer,
    used where it is written to the register and where any surface shows it."""
    from plumb.present import owner_text as text

    words = " ".join(str(chosen or "").split())
    if raised_on and words.strip(" .\"'").lower() in text.EARLY_RELATIVE:
        return text.EARLY_THEIRS.format(branch=raised_on)
    return words


def sync_decisions(core: Any) -> bool:
    """Carry the state of the decisions this branch raised (proposed, confirmed; the chosen
    option) into its claims, so every other branch hears the owner's answer. Reads git's
    files first; writes (git) only when something changed. Returns whether it wrote."""
    root = Path(core.root)
    me = gitfiles.current(root)
    if me is None or not me.branch:
        return False
    _oid, data = read(root)
    index = core.index()
    pending: dict[tuple[str, str], dict[str, str]] = {}
    for claim in data.get("claims") or []:
        if claim.get("branch") != me.branch:
            continue
        for conflict in claim.get("conflicts") or []:
            dec = str(conflict.get("dec") or "")
            if dec not in index:
                continue
            status = core.status([dec]).get(dec)
            state = getattr(status, "confirmation", "proposed")
            chosen = neutral_chosen(str(index[dec].fields.get("chosen") or ""), me.branch)
            if conflict.get("state") != state or conflict.get("chosen") != chosen:
                pending[(str(claim.get("id")), dec)] = {"state": state, "chosen": chosen}
    if not pending:
        return False

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        for claim in data.get("claims") or []:
            for conflict in claim.get("conflicts") or []:
                change = pending.get((str(claim.get("id")), str(conflict.get("dec") or "")))
                if change:
                    conflict.update(change)
        return data

    update(root, mutate)
    return True


# ------------------------------------------------------------------ the default branch since


SINCE_FORK = "since-fork"
SINCE_FORK_CACHE = "inflight-since-fork.json"
CLAIMED_KINDS = ("requirement", "intent", "feature")


def _changed_since_fork(core: Any, head: str, default_tip: str
                        ) -> tuple[str, dict[str, dict[str, str]]] | None:
    """``(merge base, records)``: each record the default branch changed since this
    branch's merge base with it (its version there differs from the base's), as a claim
    entry of the default branch's version plus ``base`` (the base's hash). Three git calls
    at most (merge-base, diff, one ``cat-file --batch`` for both versions); None when git
    could not answer."""
    root = Path(core.root)
    code, out = _git(root, "merge-base", head, default_tip)
    base = out.decode().strip() if code == 0 else ""
    if not base:
        return None
    if base == default_tip:
        return base, {}                 # this branch holds every default-branch commit
    try:
        dirs = sorted({Path(r.path).parent.as_posix() for r in core.index().values()
                       if getattr(r, "path", "")})
    except Exception:  # noqa: BLE001 - fall back on plumb's own directory
        dirs = []
    code, out = _git(root, "diff", "--name-only", "--no-renames", "-z", base, default_tip,
                     "--", *(dirs or [".plumb"]))
    if code != 0:
        return None
    paths = [p for p in out.decode("utf-8", "replace").split("\0") if p.endswith(".md")]
    found = _records_at(root, [(rev, p) for p in paths for rev in (base, default_tip)])
    if found is None:
        return None
    records: dict[str, dict[str, str]] = {}
    for path in paths:
        old, new = found.get((base, path)), found.get((default_tip, path))
        if old is None or new is None or old.id != new.id or old.hash == new.hash \
                or new.kind not in CLAIMED_KINDS:
            continue                    # new there, removed there, or not changed
        records[new.id] = {**record_entry(new), "path": path, "base": str(old.hash)}
    return base, records


def since_fork(core: Any, *, allow_git: bool = False, deadline: Any = None
               ) -> dict[str, dict[str, str]]:
    """The records the DEFAULT branch changed since this branch started from it (R17): a
    claim clears once its version lands on the default branch, yet a branch that started
    before still builds on the replaced words, so the landed change stays in flight for
    every branch that has not taken it. ``{record ID: claim entry}`` (the default branch's
    version, and ``base``: the version this branch started from). Empty on the default
    branch itself and once this branch holds the default branch's tip. Cached by this
    branch's tip and the default branch's (``SINCE_FORK_CACHE``); learned only with
    ``allow_git``. Without it (a hook path) a cache of the same default tip still serves
    after this branch committed, minus the records this checkout already holds at the
    default branch's version."""
    from plumb.awareness.publish import default_branch

    root = Path(core.root)
    me = gitfiles.current(root)
    if me is None or not me.branch or not me.head:
        return {}
    default = default_branch(core)
    if me.branch == default:
        return {}
    common = gitfiles.common_dir(root)
    default_tip = gitfiles.branch_tips(common).get(default) if common is not None else None
    if not default_tip:
        return {}
    path = _cache_path(root, SINCE_FORK_CACHE)
    cached = _read_json(path)
    same = (isinstance(cached, dict) and cached.get("branch") == me.branch
            and cached.get("default_tip") == default_tip
            and isinstance(cached.get("records"), dict))
    if same and cached.get("head") == me.head:
        return {str(k): dict(v) for k, v in cached["records"].items() if isinstance(v, dict)}
    if not allow_git or _expired(deadline):
        if not same:
            return {}
        index = core.index()
        return {str(k): dict(v) for k, v in cached["records"].items()
                if isinstance(v, dict) and not (k in index and index[k].hash == v.get("hash"))}
    learned = _changed_since_fork(core, me.head, default_tip)
    if learned is None:
        return {}
    base, records = learned
    _write_json(path, {"branch": me.branch, "head": me.head, "default_tip": default_tip,
                       "base": base, "records": records})
    return records


def fork_claim(core: Any, default: str, records: Mapping[str, Mapping[str, str]]
               ) -> dict[str, Any]:
    """The default branch's changes since this branch started, as one claim of the default
    branch (``since_fork: True``): every reader of other branches' intent (the capture
    check, the clarify read-back, the stop hook's claim, the brief, status, the prompt
    delta, the owner's answer) sees them as intent this branch has not taken. Only the
    same record is checked against it (no feature, so nothing is judged)."""
    from plumb.present import owner_text as text

    worktree = next((wt.path.as_posix() for wt in gitfiles.worktrees(Path(core.root))
                     if wt.branch == default), "")
    return {"id": f"{default}:{SINCE_FORK}", "branch": default, "since_fork": True,
            "worktree": worktree, "summary": text.SINCE_FORK_SUMMARY,
            "records": {k: dict(v) for k, v in records.items()}, "features": [],
            "conflicts": []}


# ------------------------------------------------------------------ what other branches see


def others(core: Any, *, allow_git: bool = False, deadline: Any = None
           ) -> tuple[str | None, list[dict[str, Any]]]:
    """``(this branch, the active claims of every other branch)``, the default branch's
    changes since this branch started included (``fork_claim``)."""
    from plumb.awareness.publish import default_branch

    root = Path(core.root)
    me = gitfiles.current(root)
    if me is None:
        return None, []
    _oid, data = read(root, allow_git=allow_git)
    default = default_branch(core)
    live = (active(root, data, default=default, allow_git=allow_git, deadline=deadline,
                   paths=record_paths(core)) if data.get("claims") else [])
    out = [c for c in live if c.get("branch") != me.branch]
    landed = since_fork(core, allow_git=allow_git, deadline=deadline)
    if landed:
        # a record the default branch still claims (an edit not committed yet) is read
        # from that claim, its newest version
        held = {i for c in out if c.get("branch") == default for i in c.get("records") or {}}
        records = {i: e for i, e in landed.items() if i not in held}
        if records:
            out.append(fork_claim(core, default, records))
    return me.branch, out


def claim_overlaps(core: Any, mine: Iterable[str], my_branch: str | None) -> list[Overlap]:
    """Overlaps from other branches' claims on records of ``mine`` (no git process)."""
    mine_set = set(mine)
    _me, claims = others(core)
    out: list[Overlap] = []
    for claim in claims:
        if claim.get("branch") == my_branch:
            continue
        for record_id, entry in sorted((claim.get("records") or {}).items()):
            if record_id not in mine_set or not isinstance(entry, Mapping):
                continue
            out.append(Overlap(record=record_id, title=str(entry.get("title") or ""),
                               branch=str(claim.get("branch")),
                               worktree=str(claim.get("worktree") or ""),
                               how=SINCE_FORK if claim.get("since_fork") else "claimed",
                               other_hash=str(entry.get("hash") or claim.get("at") or ""),
                               at=str(claim.get("at") or ""),
                               summary=str(claim.get("summary") or "")))
    return out


def raised_for(core: Any, my_branch: str | None, claims: Iterable[Mapping[str, Any]]
               ) -> list[dict[str, Any]]:
    """The conflicts other branches raised against this branch's work (each with the
    raising branch), so this branch builds on the same answer."""
    out: list[dict[str, Any]] = []
    if not my_branch:
        return out
    for claim in claims:
        for conflict in claim.get("conflicts") or []:
            if conflict.get("branch") == my_branch:
                out.append({**conflict, "raised_on": claim.get("branch")})
    return out
