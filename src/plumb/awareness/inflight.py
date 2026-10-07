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
that work. A branch that only took the default branch's commits (a fast-forward to
``main``) keeps its claim: its intent is still in flight. Readers on a hook path read the ref
and the blob from git's files (a loose object) with no git process, through a cache keyed by
the blob's ID.

Entry shape::

    {"v": 1, "claims": [{"id": "feat-x:INT-022", "branch": "feat-x", "worktree": "...",
      "head": "<sha at the claim>", "base": "<fork point from the default branch>",
      "own": "<the branch's own newest commit, or empty>", "at": "...", "summary": "...",
      "intent": "INT-022",
      "records": {"SR-005": {"title": "...", "hash": "sha256:...", "text": "...",
                             "feature": "FEAT-002"}},
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
           deadline: Any = None) -> list[dict[str, Any]]:
    """The claims still in flight: a deleted branch's claims are gone (abandoned); a claim
    whose branch ``merged`` is gone; on the default branch itself a claim clears once a
    commit lands. The merged check runs only with ``allow_git``, cached by the claim's
    fork point and own commit and the two tips; without it an unknown case keeps its
    claim."""
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
    retry (jittered), at most ``retries`` times or ``retry_s`` seconds (``InflightBusy``).
    ``mutate`` returning None or an equal register writes nothing."""
    root = Path(root)
    start = time.monotonic()
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
        if time.monotonic() - start > retry_s:
            break
        time.sleep(random.uniform(0.005, 0.03) * (1 + min(attempt, 5)))
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

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        live = active(root, data, default=default, allow_git=True)
        for claim in live:          # every claim of this branch moves with its tip
            if claim.get("branch") == me.branch and me.branch != default:
                claim.update({"head": me.head, **where})
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


def refresh(core: Any, *, default: str | None = None) -> bool:
    """Move this branch's claims to its tip: ``head``, the fork point and its own newest
    commit, so a later merge of that commit clears them (``merged``). Writes only when a
    claim moved. Returns whether it wrote."""
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
    wrote = {"done": False}

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        live = active(root, data, default=default, allow_git=True)
        for claim in live:
            if claim.get("branch") == me.branch:
                claim.update({"head": me.head, **where})
                wrote["done"] = True
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


# ------------------------------------------------------------------ what other branches see


def others(core: Any, *, allow_git: bool = False, deadline: Any = None
           ) -> tuple[str | None, list[dict[str, Any]]]:
    """``(this branch, the active claims of every other branch)``."""
    from plumb.awareness.publish import default_branch

    root = Path(core.root)
    me = gitfiles.current(root)
    if me is None:
        return None, []
    _oid, data = read(root, allow_git=allow_git)
    if not data.get("claims"):
        return me.branch, []
    live = active(root, data, default=default_branch(core), allow_git=allow_git,
                  deadline=deadline)
    return me.branch, [c for c in live if c.get("branch") != me.branch]


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
                               worktree=str(claim.get("worktree") or ""), how="claimed",
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
