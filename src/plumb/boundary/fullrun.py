"""Exactly one full-suite run per merge-check (sp3 4, SR-048; R5; KEEP failure policy).

The decision comes before anything runs:

- a passing full run whose tree identity (``head_tree`` plus the dirty digest) and
  environment (key and identity) equal the current ones is reused: nothing runs;
- otherwise a run is needed when ``full verification pending`` holds or a touched acceptance
  test is unverified, unless an owner waiver pins this exact change;
- when needed and allowed (``run_full``), the runner is called ONCE. Its own failure policy
  reruns a failed node once on the same tree (flaky); nothing else is rerun, and a red run is
  never repeated in this invocation.

On a green report, ``record_merge_evidence`` appends one ``merge-evidence`` entry pinning the
run, the tree and the environment (concept 7.5 evidence promotion).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

Runner = Callable[[Any], Any]

# SR-108: the steps a merge check says it is on
STEP_DECIDE = "checking the earlier full run"
STEP_RUN = "running the full suite"


def _say(core: Any, step: str) -> None:
    """Name the step on the merge check's progress line (nothing outside a progress scope
    changes: the reporter is the enclosing execution's, or a new quiet one)."""
    from plumb import progress

    reporter, owned = progress.acquire(core.root, "merge-check")
    reporter.update(step)
    if owned:
        reporter.done()


def default_runner(core: Any) -> Any:
    """``plumb tests run --full``, in this process (its pytest runs as one child)."""
    from plumb.verify import open_verify

    return open_verify(core).run(full=True)


def latest_full_run(core: Any) -> Mapping[str, Any] | None:
    """The latest full ``test-run`` payload that was not discarded, or None."""
    latest = None
    for entry in core.log_read("evidence", kinds=["test-run"]):
        payload = entry.payload
        if payload.get("full") and not payload.get("discarded"):
            latest = payload
    return latest


def live_failures(ids: Sequence[str], core: Any) -> list[str]:
    """``ids`` without those of a frozen part (SR-380, DEC-404): a test there counts in no hold."""
    from plumb.frozen import is_frozen

    return [i for i in ids if not is_frozen(core.config, i)]


def _live_nodes(payload: Mapping[str, Any], core: Any | None) -> list[Mapping[str, Any]]:
    nodes = payload.get("nodes") or []
    if core is None:
        return list(nodes)
    from plumb.frozen import is_frozen

    return [n for n in nodes
            if not is_frozen(core.config, str(n.get("id") or n.get("nodeid") or ""))]


def clean_pass(payload: Mapping[str, Any], core: Any | None = None) -> bool:
    """A full run that collected cleanly, ran tests, and passed every one of them (a test in a
    frozen part counts for nothing: DEC-404)."""
    from plumb.verify.evidence import GOOD_OUTCOMES

    nodes = _live_nodes(payload, core)
    return bool(nodes and payload.get("exit_status") in (0, 1)
                and not payload.get("collection_errors") and not payload.get("aborted")
                and not payload.get("timeout") and not payload.get("discarded")
                and all(n.get("outcome") in GOOD_OUTCOMES for n in nodes))


def completed_red(payload: Mapping[str, Any], core: Any | None = None) -> bool:
    """A full run that collected cleanly and finished, with at least one failing test outside
    the frozen parts (DEC-404)."""
    from plumb.verify.evidence import GOOD_OUTCOMES

    nodes = _live_nodes(payload, core)
    return bool(nodes and not payload.get("collection_errors") and not payload.get("aborted")
                and not payload.get("timeout") and not payload.get("discarded")
                and any(n.get("outcome") not in GOOD_OUTCOMES for n in nodes))


def current_identity(core: Any, verify: Any) -> dict[str, Any]:
    from plumb.verify.evidence import tree_identity

    return {"tree": tree_identity(core.root),
            "env": {"env_key": verify.env_key(), "identity": verify.identity(compute=True)}}


def identical(payload: Mapping[str, Any], now: Mapping[str, Any]) -> bool:
    tree, env = payload.get("tree") or {}, payload.get("env") or {}
    return (bool(tree.get("head_tree")) and tree.get("head_tree") == now["tree"]["head_tree"]
            and tree.get("dirty") == now["tree"]["dirty"]
            and env.get("env_key") == now["env"]["env_key"]
            and env.get("identity") == now["env"]["identity"])


def verdict_of(result: Any, core: Any | None = None) -> str:
    if result is None:
        return "not-run"
    if getattr(result, "discarded", None):
        return "discarded"
    if getattr(result, "timed_out", False):
        return "timed out"
    if getattr(result, "aborted", None) or getattr(result, "collection_errors", None):
        return "aborted"
    failed = list(getattr(result, "failed", None) or ())
    return "failed" if (live_failures(failed, core) if core is not None else failed) else "passed"


def _differs_from_index(root: Any) -> bool:
    """Whether a working file outside ``.plumb/`` differs from the index (unknown: yes): the
    index is then not what this checkout holds."""
    from plumb.verify.evidence import _CACHE_PARTS, _git

    listed = [_git(root, "diff", "--name-only", "-z"),
              _git(root, "ls-files", "--others", "--exclude-standard", "-z")]
    if None in listed:
        return True
    return any(path and not path.startswith(".plumb/") and not _CACHE_PARTS & set(path.split("/"))
               for out in listed for path in str(out).split("\0"))


def _without_records(root: Any, tree: Any) -> str | None:
    """The top of ``tree`` without ``.plumb``, as ``tree_identity``'s ``dirty`` leaves it out:
    records repinned after the tests passed are the same code."""
    from plumb.verify.evidence import _git

    if not tree:
        return None
    listing = _git(root, "ls-tree", str(tree))
    if listing is None:
        return None
    return "\n".join(line for line in listing.splitlines()
                     if line.split("\t", 1)[-1] != ".plumb")


def _full_runs_of_every_checkout(paths: Any) -> Iterator[Any]:
    """The full runs in the test-run logs of this checkout and the repository's others, newest
    first by entry name, read-only. An entry's bytes are tried before it is parsed, as these
    logs run to hundreds of megabytes; an entry two checkouts share is read once, and one whose
    digest does not hold is left out."""
    import os
    import re
    from pathlib import Path

    from plumb.log import _parse_entry, _read_file, _to_entry, _worktree_roots, entry_digest
    from plumb.paths import PlumbPaths

    is_full = re.compile(rb'"full"\s*:\s*true')
    names: dict[str, Path] = {}
    for root in (paths.root, *_worktree_roots(paths)):
        folder = PlumbPaths(root).log_kind_dir("test-run")
        try:
            found = [name for name in os.listdir(folder) if name.endswith(".json")]
        except OSError:
            continue
        for name in found:
            names.setdefault(name, folder)
    for name in sorted(names, reverse=True):
        try:
            data = _read_file(str(names[name] / name))
        except OSError:
            continue
        if not is_full.search(data):
            continue
        raw = _parse_entry(data)
        if raw is not None and raw.get("digest") == entry_digest(raw):
            yield _to_entry("evidence", raw, -1, f"test-run/{name}")


def run_of_merged_tree(core: Any, verify: Any) -> Mapping[str, Any] | None:
    """The green full run of the tree being merged that any checkout of this machine recorded,
    or None (SR-254, report-d188e19d). Each checkout logs its own runs, so main cannot otherwise
    see the one a branch's worktree recorded before it lands.

    The merged tree is the index: the staged result during a merge, the commit after a
    fast-forward. The run counts on an exact match outside ``.plumb/``: a clean checkout and
    the same environment. The newest finished run of that tree decides: a later red one
    withdraws an earlier green one."""
    from plumb.normalize import canonical_json, sha256_bytes
    from plumb.verify.evidence import _git

    root = core.root
    if _differs_from_index(root):
        return None
    merged = _without_records(root, (_git(root, "write-tree") or "").strip())
    if merged is None:
        return None
    clean = sha256_bytes(canonical_json([]))  # tree_identity's ``dirty`` with nothing changed
    env_now = None
    for entry in _full_runs_of_every_checkout(core.paths):
        payload = entry.payload
        tree = payload.get("tree") or {}
        if (not payload.get("full") or tree.get("dirty") != clean
                or _without_records(root, tree.get("head_tree")) != merged):
            continue
        if env_now is None:
            env_now = {"env_key": verify.env_key(), "identity": verify.identity(compute=True)}
        env = payload.get("env") or {}
        if any(env.get(key) != value for key, value in env_now.items()):
            continue
        if clean_pass(payload, core):
            return payload
        if completed_red(payload, core):
            return None
    return None


def full_run(core: Any, verify: Any, *, pending: bool, reasons: list[str], unverified: bool,
             waived: bool, run_full: bool, runner: Runner | None) -> dict[str, Any]:
    """Decide, reuse or run once. Returns ``{needed, ran, reused, run_id, verdict, reasons,
    identity}``; ``identity`` is the current tree and environment."""
    _say(core, STEP_DECIDE)
    now = current_identity(core, verify)
    out: dict[str, Any] = {"needed": False, "ran": False, "reused": False, "run_id": None,
                           "verdict": "not-run", "reasons": list(reasons),
                           "waived": waived, "identity": now}
    latest = latest_full_run(core)
    if latest is not None and clean_pass(latest, core) and identical(latest, now):
        out.update({"reused": True, "run_id": latest.get("run_id"), "verdict": "passed"})
        return out
    if latest is not None and completed_red(latest, core) and identical(latest, now):
        # the same tree and environment already failed: repeating it only delays the same
        # answer (a push must not rerun a multi-minute suite to fail again)
        from plumb.verify.evidence import GOOD_OUTCOMES as GOOD

        out.update({"reused": True, "run_id": latest.get("run_id"), "verdict": "failed",
                    "needed": bool((pending or unverified) and not waived),
                    "failed": [n.get("id") or n.get("nodeid") or ""
                               for n in _live_nodes(latest, core)
                               if n.get("outcome") not in GOOD][:50]})
        return out
    out["needed"] = bool((pending or unverified) and not waived)
    if latest is not None and not out["needed"]:
        out["run_id"] = latest.get("run_id")  # the run that satisfied full verification
    if not out["needed"] or not run_full:
        return out
    _say(core, STEP_RUN)
    import sys
    print(f"plumb: {STEP_RUN} (no earlier passing run matches this tree; this can take "
          "minutes)", file=sys.stderr, flush=True)
    result = (runner or default_runner)(core)  # the ONE run: never repeated below
    out.update({"ran": True, "run_id": getattr(result, "run_id", None),
                "verdict": verdict_of(result, core),
                "failed": live_failures(list(getattr(result, "failed", None) or []), core)[:50]})
    return out


def record_merge_evidence(core: Any, payload: Mapping[str, Any]) -> str | None:
    """Append one ``merge-evidence`` entry unless the latest one pins the same merge.
    Returns the entry digest (the existing one when it is a repeat)."""
    keys = ("base", "fork", "head", "head_tree", "dirty", "full_run", "touched", "confirmed")
    last = None
    for entry in core.log_read("evidence", kinds=["merge-evidence"]):
        last = entry
    if last is not None and all(last.payload.get(k) == payload.get(k) for k in keys):
        return last.digest
    entry = core.log_append("evidence", "merge-evidence", dict(payload))
    return getattr(entry, "digest", None)
