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

from collections.abc import Callable, Mapping, Sequence
from typing import Any

Runner = Callable[[Any], Any]

# SR-108: the steps a merge check says it is on
STEP_DECIDE = "checking the earlier full run"
STEP_RUN = "running the full suite"
STEP_DELTA = "running the tests the change since the last green full run affects"


def _say(core: Any, step: str) -> None:
    """Name the step on the merge check's progress line (nothing outside a progress scope
    changes: the reporter is the enclosing execution's, or a new quiet one)."""
    from iaso import progress

    reporter, owned = progress.acquire(core.root, "merge-check")
    reporter.update(step)
    if owned:
        reporter.done()


def default_runner(core: Any) -> Any:
    """``iaso tests run --full``, in this process (its pytest runs as one child)."""
    from iaso.verify import open_verify

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
    from iaso.frozen import is_frozen

    return [i for i in ids if not is_frozen(core.config, i)]


def _live_nodes(payload: Mapping[str, Any], core: Any | None) -> list[Mapping[str, Any]]:
    nodes = payload.get("nodes") or []
    if core is None:
        return list(nodes)
    from iaso.frozen import is_frozen

    return [n for n in nodes
            if not is_frozen(core.config, str(n.get("id") or n.get("nodeid") or ""))]


def clean_pass(payload: Mapping[str, Any], core: Any | None = None) -> bool:
    """A full run that collected cleanly, ran tests, and passed every one of them (a test in a
    frozen part counts for nothing: DEC-404)."""
    from iaso.verify.evidence import GOOD_OUTCOMES

    nodes = _live_nodes(payload, core)
    return bool(nodes and payload.get("exit_status") in (0, 1)
                and not payload.get("collection_errors") and not payload.get("aborted")
                and not payload.get("timeout") and not payload.get("discarded")
                and all(n.get("outcome") in GOOD_OUTCOMES for n in nodes))


def completed_red(payload: Mapping[str, Any], core: Any | None = None) -> bool:
    """A full run that collected cleanly and finished, with at least one failing test outside
    the frozen parts (DEC-404)."""
    from iaso.verify.evidence import GOOD_OUTCOMES

    nodes = _live_nodes(payload, core)
    return bool(nodes and not payload.get("collection_errors") and not payload.get("aborted")
                and not payload.get("timeout") and not payload.get("discarded")
                and any(n.get("outcome") not in GOOD_OUTCOMES for n in nodes))


def current_identity(core: Any, verify: Any) -> dict[str, Any]:
    from iaso.verify.evidence import tree_identity

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
    """Whether a working file outside ``.iaso/`` differs from the index (unknown: yes): the
    index is then not what this checkout holds."""
    from iaso.verify.evidence import _CACHE_PARTS, _git

    listed = [_git(root, "diff", "--name-only", "-z"),
              _git(root, "ls-files", "--others", "--exclude-standard", "-z")]
    if None in listed:
        return True
    return any(path and not path.startswith(".iaso/")
               and not _CACHE_PARTS & set(path.split("/"))
               for out in listed for path in str(out).split("\0"))


def _without_records(root: Any, tree: Any) -> str | None:
    """The top of ``tree`` without ``.iaso``, as ``tree_identity``'s ``dirty`` leaves it out:
    records repinned after the tests passed are the same code."""
    from iaso.verify.evidence import _git

    if not tree:
        return None
    listing = _git(root, "ls-tree", str(tree))
    if listing is None:
        return None
    return "\n".join(line for line in listing.splitlines()
                     if line.split("\t", 1)[-1] != ".iaso")


# --------------------------------------------------------------------------- after main moves

DELTA_MARK = rb'"extends"\s*:'   # a covering run that brings a green full run up to date
DELTA_BUDGET_S = 86400.0         # every covering test: such a run is never cut to a turn budget
_ANCESTORS = 400                 # how far back in HEAD's history a full run's tree is looked for


def _paths_between(root: Any, tree: Any, other: Any) -> list[str] | None:
    """The paths that differ between two trees, outside ``.iaso/`` (records repinned after the
    tests passed are the same code); None when git cannot tell."""
    from iaso.verify.evidence import _git

    out = _git(root, "diff", "--name-only", "--no-renames", "-z", str(tree), str(other))
    if out is None:
        return None
    return sorted(p for p in out.split("\0") if p and not p.startswith(".iaso/"))


def _delta_selection(verify: Any, paths: Sequence[str]) -> Any:
    """The covering tests of ``paths``, every one of them, or None when only a full run will do:
    shared test infrastructure changed, a source file has no covering test, or nothing is
    selected. shortcut: a change only to files no test covers (docs) needs a full run; let it
    count with no run once such a change is common after main moves."""
    selection = verify.select(list(paths), budget_s=DELTA_BUDGET_S)
    if selection.infra_changed or selection.unknown_coverage or selection.deferred \
            or not selection.nodes:
        return None
    return selection


def _same_env(verify: Any, payload: Mapping[str, Any], env_now: dict[str, Any] | None
              ) -> tuple[bool, dict[str, Any]]:
    if env_now is None:
        env_now = {"env_key": verify.env_key(), "identity": verify.identity(compute=True)}
    env = payload.get("env") or {}
    return all(env.get(k) == v for k, v in env_now.items()), env_now


def delta_plan(core: Any, verify: Any, now: Mapping[str, Any]
               ) -> tuple[Mapping[str, Any], list[str]] | None:
    """SR-254 (owner, 2026-11-12, DEC-549): ``(base, paths)`` when a green full run of an earlier
    tree of this branch (any checkout, same environment, the newest such run) can count for the
    current clean tree once the covering tests of ``paths``, what differs since, pass; else None
    (a full run is needed)."""
    from iaso.log import full_runs_of_every_checkout
    from iaso.normalize import canonical_json, sha256_bytes
    from iaso.verify.evidence import _git

    root = core.root
    tree = now["tree"]
    if tree.get("dirty") != sha256_bytes(canonical_json([])) or not tree.get("head_tree"):
        return None
    trees = set((_git(root, "log", "--format=%T", f"-n{_ANCESTORS}", "HEAD") or "").split())
    env_now = None
    for entry in full_runs_of_every_checkout(core.paths):
        payload = entry.payload
        run_tree = payload.get("tree") or {}
        if run_tree.get("head_tree") not in trees or run_tree.get("head_tree") == \
                tree["head_tree"] or run_tree.get("dirty") != tree["dirty"]:
            continue
        same, env_now = _same_env(verify, payload, env_now)
        if not same:
            continue
        if not clean_pass(payload, core):
            return None                      # the newest full run of this branch decides
        paths = _paths_between(root, run_tree["head_tree"], tree["head_tree"])
        if not paths or _delta_selection(verify, paths) is None:
            return None
        return payload, paths
    return None


def run_delta(core: Any, verify: Any, base: Mapping[str, Any], paths: Sequence[str]) -> Any:
    """Run the covering tests of ``paths`` once, every one, recorded as extending ``base``."""
    import sys

    print(f"iaso: running the tests that {len(paths)} changed path(s) since the green full run "
          f"{base.get('run_id')} affect (main moved; no new full run)", file=sys.stderr,
          flush=True)
    return verify.run(changed=list(paths), budget_s=DELTA_BUDGET_S, extends={
        "run_id": base.get("run_id"), "tree": (base.get("tree") or {}).get("head_tree"),
        "changed": list(paths)})


def _delta_of_merged_tree(core: Any, verify: Any, merged: str, clean: str,
                          env_now: dict[str, Any] | None) -> Mapping[str, Any] | None:
    """A green covering run of the merged tree that extends a green full run (``run_delta``),
    recorded in any checkout: it counts as that tree's full run when the paths it was given are
    still exactly what differs since the full run's tree and it ran every covering test of
    them. The newest such run decides."""
    from iaso.log import full_runs_of_every_checkout

    root = core.root
    for entry in full_runs_of_every_checkout(core.paths, DELTA_MARK):
        payload = entry.payload
        extends, tree = payload.get("extends") or {}, payload.get("tree") or {}
        if not extends or tree.get("dirty") != clean \
                or _without_records(root, tree.get("head_tree")) != merged:
            continue
        same, env_now = _same_env(verify, payload, env_now)
        if not same:
            continue
        if not clean_pass(payload, core):
            return None
        paths = _paths_between(root, extends.get("tree"), tree.get("head_tree"))
        if paths is None or paths != sorted(extends.get("changed") or ()):
            continue
        base = next((e.payload for e in full_runs_of_every_checkout(core.paths)
                     if e.payload.get("run_id") == extends.get("run_id")), None)
        if base is None or not clean_pass(base, core) \
                or (base.get("tree") or {}).get("head_tree") != extends.get("tree"):
            continue
        selection = _delta_selection(verify, paths)
        ran = {str(n.get("id") or n.get("nodeid") or "").split("::", 1)[0]
               for n in payload.get("nodes") or ()}
        if selection is None or any(n.split("::", 1)[0] not in ran for n in selection.nodes):
            continue
        return payload
    return None


def run_of_merged_tree(core: Any, verify: Any) -> Mapping[str, Any] | None:
    """The green full run of the tree being merged that any checkout of this machine recorded,
    or None (SR-254, report-d188e19d). Each checkout logs its own runs, so main cannot otherwise
    see the one a branch's worktree recorded before it lands.

    The merged tree is the index: the staged result during a merge, the commit after a
    fast-forward. The run counts on an exact match outside ``.iaso/``: a clean checkout and
    the same environment. The newest finished run of that tree decides: a later red one
    withdraws an earlier green one."""
    from iaso.normalize import canonical_json, sha256_bytes
    from iaso.verify.evidence import _git

    root = core.root
    if _differs_from_index(root):
        return None
    merged = _without_records(root, (_git(root, "write-tree") or "").strip())
    if merged is None:
        return None
    clean = sha256_bytes(canonical_json([]))  # tree_identity's ``dirty`` with nothing changed
    env_now = None
    from iaso.log import full_runs_of_every_checkout

    for entry in full_runs_of_every_checkout(core.paths):
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
    # SR-254, DEC-549: main moved since the branch's green full run; its covering run counts
    return _delta_of_merged_tree(core, verify, merged, clean, env_now)


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
        from iaso.verify.evidence import GOOD_OUTCOMES as GOOD

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
    plan = delta_plan(core, verify, now)
    if plan is not None:     # SR-254, DEC-549: only what changed since a green full run
        _say(core, STEP_DELTA)
        result = run_delta(core, verify, *plan)
        out.update({"ran": True, "delta": plan[0].get("run_id"),
                    "run_id": getattr(result, "run_id", None),
                    "verdict": verdict_of(result, core),
                    "failed": live_failures(list(getattr(result, "failed", None) or []),
                                            core)[:50]})
        return out
    _say(core, STEP_RUN)
    import sys
    print(f"iaso: {STEP_RUN} (no earlier passing run matches this tree; this can take "
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
