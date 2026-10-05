"""Test evidence pinned to identity (spec 7.4) and its reuse index.

A ``test-run`` entry in ``evidence.jsonl`` pins every node to its import closure hash, its
own normalized source hash and the cheap environment key, and the run to the tree identity.
A node's evidence is fresh only when all three match now. The reuse index
(``.plumb/cache/evidence_index.json``) is derived from the log by byte offset, so deleting it
loses nothing. The index also keeps a digest of the log bytes just before its offset (the
first and last ``_GUARD_BYTES``): a rebase, branch switch or pull that rewrites the log under
the offset fails that check, and the index is rebuilt from byte 0. The regression rule (R3)
reads the same index (``policy.py``).
"""

from __future__ import annotations

import json
import secrets
import subprocess
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import NodeEvidence
from plumb.normalize import canonical_json, file_digest, sha256_bytes

INDEX_VERSION = 3  # 3: a full run must collect cleanly to count
_GUARD_BYTES = 65536
PASS_OUTCOMES = frozenset({"passed", "flaky"})
GOOD_OUTCOMES = frozenset({"passed", "flaky", "skipped", "xfailed"})
_CACHE_PARTS = frozenset({"__pycache__", ".pytest_cache"})


def new_run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(4)


def closure_digest(pairs: Iterable[tuple[str, str]]) -> str:
    return sha256_bytes(canonical_json(sorted(pairs)))


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=10,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", errors="replace")


def changed_paths_from_git(root: Path) -> list[str]:
    """Paths ``git status --porcelain -z --untracked-files=all`` reports (renames: both)."""
    out = _git(root, "status", "--porcelain", "-z", "--untracked-files=all")
    if not out:
        return []
    items = out.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(items):
        item = items[i]
        i += 1
        if len(item) < 4:
            continue
        status, path = item[:2], item[3:]
        paths.append(path)
        if "R" in status or "C" in status:
            if i < len(items) and items[i]:
                paths.append(items[i])
            i += 1
    return paths


def tree_identity(root: Path) -> dict[str, Any]:
    """``{head, head_tree, dirty}``; ``dirty`` hashes the changed paths outside ``.plumb/``."""
    root = Path(root)
    heads = _git(root, "rev-parse", "HEAD", "HEAD^{tree}")
    head = tree = None
    if heads:
        lines = heads.split()
        if len(lines) >= 2:
            head, tree = lines[0], lines[1]
    pairs = []
    for rel in sorted(set(changed_paths_from_git(root))):
        if rel.startswith(".plumb/") or _CACHE_PARTS & set(rel.split("/")):
            continue
        try:
            digest = file_digest(root / rel)
        except OSError:
            digest = "deleted"
        pairs.append((rel, digest))
    return {"head": head, "head_tree": tree, "dirty": sha256_bytes(canonical_json(pairs))}


def payload_checksum(payload: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json({k: v for k, v in payload.items() if k != "self"}))


# -- the reuse index -------------------------------------------------------------------


def _empty_index() -> dict[str, Any]:
    return {"v": INDEX_VERSION, "offset": 0, "prefix": None, "nodes": {}, "full": None,
            "removed": {}}


def prefix_digest(path: Path, offset: int) -> str | None:
    """A digest of the log's first and last ``_GUARD_BYTES`` before ``offset`` (bounded read,
    so the per-turn cost does not grow with the log)."""
    if offset <= 0:
        return None
    head_len = min(offset, _GUARD_BYTES)
    tail_start = max(head_len, offset - _GUARD_BYTES)
    try:
        with open(path, "rb") as handle:
            head = handle.read(head_len)
            handle.seek(tail_start)
            tail = handle.read(offset - tail_start)
    except OSError:
        return None
    if len(head) != head_len or len(tail) != offset - tail_start:
        return None
    return sha256_bytes(b"%d:" % offset + head + b":" + tail)


MAX_SCALE = 3.0
MIN_LEARN_S = 2.0  # a shorter run is mostly start-up time: its pace teaches nothing


def learn_scale(index: dict[str, Any], payload: Mapping[str, Any]) -> None:
    """Fold a run's pace (wall clock over the estimate of what it was asked to run) into
    ``index["scale"]``: halfway toward a finished run's pace, and at once up to a timed-out
    run's pace (a lower bound), within [1, ``MAX_SCALE``]."""
    timing = payload.get("timing")
    run_id = str(payload.get("run_id", ""))
    if not isinstance(timing, Mapping) or payload.get("aborted"):
        return
    if run_id and index.get("scale_run") == run_id:
        return  # the same entry folded twice
    try:
        expected = float(timing.get("expected_s") or 0)
        elapsed = float(timing.get("elapsed_s") or 0)
    except (TypeError, ValueError):
        return
    timed_out = bool(payload.get("timeout"))
    if expected <= 0 or elapsed <= 0 or (expected < MIN_LEARN_S and not timed_out):
        return
    current = float(index.get("scale") or 1.0)
    pace = min(max(elapsed / expected, 1.0), MAX_SCALE)
    scale = max(current, pace) if timed_out else (current + pace) / 2
    index["scale"] = round(min(max(scale, 1.0), MAX_SCALE), 4)
    index["scale_run"] = run_id


def apply_entry(index: dict[str, Any], payload: Mapping[str, Any], at: str = "") -> None:
    """Fold one ``test-run`` payload into the index (idempotent for a repeated entry)."""
    if payload.get("discarded"):
        return
    if not payload.get("full"):
        learn_scale(index, payload)
    run_id = str(payload.get("run_id", ""))
    env = payload.get("env") or {}
    nodes = index["nodes"]
    for node in payload.get("nodes") or []:
        node_id = str(node.get("id", ""))
        if not node_id:
            continue
        rec = {"run_id": run_id, "outcome": node.get("outcome"),
               "closure": node.get("closure"), "test_hash": node.get("test_hash"),
               "env_key": env.get("env_key"), "duration_s": node.get("duration_s"), "at": at}
        if "identity" in env:
            rec["identity"] = env.get("identity")
        entry = nodes.setdefault(node_id, {"last": None, "last_pass": None})
        entry["last"] = rec
        if rec["outcome"] in PASS_OUTCOMES:
            entry["last_pass"] = rec
    # only a full run that collected cleanly and ran tests satisfies ``full pending`` (R5): no
    # tests collected (exit 5), a collection error or an empty run is no full verification
    if (payload.get("full") and not payload.get("timeout") and not payload.get("aborted")
            and payload.get("exit_status") in (0, 1) and not payload.get("collection_errors")
            and payload.get("nodes")):
        index["full"] = {"run_id": run_id, "infra": dict(payload.get("infra") or {}),
                         "files": dict(payload.get("files") or {})}


def load_index(core: Any) -> dict[str, Any]:
    """The reuse index, brought up to date with ``evidence.jsonl`` from its byte offset."""
    paths = core.paths
    log_path = paths.log_evidence
    try:
        size = log_path.stat().st_size
    except OSError:
        size = 0
    index: dict[str, Any]
    try:
        index = json.loads(paths.evidence_index.read_text(encoding="utf-8"))
        if not isinstance(index, dict) or index.get("v") != INDEX_VERSION:
            raise ValueError
    except (OSError, ValueError):
        index = _empty_index()
    start = int(index.get("offset", 0))
    if start > size or (start > 0 and index.get("prefix") != prefix_digest(log_path, start)):
        index = _empty_index()  # the log under the offset was rewritten: rebuild from 0
        start = 0
    if start == size:
        return index
    for entry in core.log_read("evidence", kinds=["test-run"], since_offset=start):
        if entry.offset >= size:
            break
        apply_entry(index, entry.payload, entry.at)
    index["offset"] = size
    index["prefix"] = prefix_digest(log_path, size)
    try:
        paths.cache.mkdir(parents=True, exist_ok=True)
        paths.evidence_index.write_text(json.dumps(index), encoding="utf-8")
    except OSError:
        pass
    return index


def durations(index: Mapping[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for node_id, entry in index.get("nodes", {}).items():
        last = entry.get("last") or {}
        if isinstance(last.get("duration_s"), (int, float)):
            out[node_id] = float(last["duration_s"])
    return out


# -- freshness ---------------------------------------------------------------------------


def _state_of(rec: Mapping[str, Any]) -> str:
    outcome = rec.get("outcome")
    if outcome == "flaky":
        return "flaky-pass"
    if outcome in GOOD_OUTCOMES:
        return "fresh-pass"
    return "fresh-fail"


_NO_CHECK: Any = object()


def single_evidence(index: Mapping[str, Any], node_id: str, *, closure: str | None,
                    test_hash: str | None, env_key: str,
                    identity: Any = _NO_CHECK) -> NodeEvidence:
    """Evidence of one recorded node id against the current closure, source and env key."""
    entry = index.get("nodes", {}).get(node_id)
    if not entry or not entry.get("last"):
        return NodeEvidence(node_id=node_id, state="none")
    last = entry["last"]
    last_pass = entry.get("last_pass")
    regression = last.get("outcome") == "failed" and last_pass is not None
    changed = False
    if regression:
        then = last_pass.get("test_hash")
        changed = test_hash is None or then is None or then != test_hash
    miss = None
    if test_hash is None or last.get("test_hash") != test_hash:
        miss = "test"
    elif closure is None or last.get("closure") != closure:
        miss = "closure"
    elif last.get("env_key") != env_key:
        miss = "env"
    elif identity is not _NO_CHECK and (identity is None or last.get("identity") != identity):
        miss = "identity"  # an unknown identity is never reused (VS3)
    state = "stale" if miss else _state_of(last)
    return NodeEvidence(node_id=node_id, state=state, regression=regression,  # type: ignore[arg-type]
                        test_changed_since_pass=changed, last_run=last.get("run_id"),
                        reuse_miss=miss)  # type: ignore[arg-type]


_RANK = {"none": 0, "stale": 1, "fresh-fail": 2, "flaky-pass": 3, "fresh-pass": 4}


def aggregate(node_id: str, parts: list[NodeEvidence]) -> NodeEvidence:
    """One file's (or parametrized node's) evidence: the weakest part decides the state."""
    if not parts:
        return NodeEvidence(node_id=node_id, state="none")
    worst = min(parts, key=lambda e: _RANK[e.state])
    state = worst.state
    runs = sorted((e.last_run for e in parts if e.last_run), reverse=True)
    return NodeEvidence(node_id=node_id, state=state,
                        regression=any(e.regression for e in parts),
                        test_changed_since_pass=any(e.test_changed_since_pass for e in parts
                                                    if e.regression),
                        last_run=runs[0] if runs else None, reuse_miss=worst.reuse_miss)


def node_evidence(index: Mapping[str, Any], tmap: Any, node_id: str,
                  env_key: str, identity: Any = _NO_CHECK) -> NodeEvidence:
    """Evidence for a node id, a parametrized family, or a whole test file."""
    from plumb.verify.markers import strip_param

    test_file = node_id.split("::", 1)[0]
    closure = tmap.closure_hash(test_file)
    recorded = index.get("nodes", {})
    if "::" in node_id:
        if node_id in recorded:
            return single_evidence(index, node_id, closure=closure,
                                   test_hash=tmap.node_hash(node_id), env_key=env_key,
                                   identity=identity)
        family = [n for n in recorded if strip_param(n) == node_id]
        if not family:
            return NodeEvidence(node_id=node_id, state="none")
        return aggregate(node_id, [single_evidence(index, n, closure=closure,
                                                   test_hash=tmap.node_hash(n),
                                                   env_key=env_key, identity=identity)
                                   for n in family])
    prefix = test_file + "::"
    members = {n for n in recorded if n.startswith(prefix)}
    known = {strip_param(n) for n in members}
    parts = [single_evidence(index, n, closure=closure, test_hash=tmap.node_hash(n),
                             env_key=env_key, identity=identity) for n in sorted(members)]
    for node in tmap.nodes_of(test_file):
        if node not in known:
            parts.append(NodeEvidence(node_id=node, state="none"))
    return aggregate(node_id, parts)
