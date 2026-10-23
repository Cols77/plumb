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

from collections.abc import Callable, Mapping
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


def clean_pass(payload: Mapping[str, Any]) -> bool:
    """A full run that collected cleanly, ran tests, and passed every one of them."""
    from plumb.verify.evidence import GOOD_OUTCOMES

    nodes = payload.get("nodes") or []
    return bool(nodes and payload.get("exit_status") in (0, 1)
                and not payload.get("collection_errors") and not payload.get("aborted")
                and not payload.get("timeout") and not payload.get("discarded")
                and all(n.get("outcome") in GOOD_OUTCOMES for n in nodes))


def completed_red(payload: Mapping[str, Any]) -> bool:
    """A full run that collected cleanly and finished, with at least one failing test."""
    from plumb.verify.evidence import GOOD_OUTCOMES

    nodes = payload.get("nodes") or []
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


def verdict_of(result: Any) -> str:
    if result is None:
        return "not-run"
    if getattr(result, "discarded", None):
        return "discarded"
    if getattr(result, "timed_out", False):
        return "timed out"
    if getattr(result, "aborted", None) or getattr(result, "collection_errors", None):
        return "aborted"
    return "failed" if getattr(result, "failed", None) else "passed"


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
    if latest is not None and clean_pass(latest) and identical(latest, now):
        out.update({"reused": True, "run_id": latest.get("run_id"), "verdict": "passed"})
        return out
    if latest is not None and completed_red(latest) and identical(latest, now):
        # the same tree and environment already failed: repeating it only delays the same
        # answer (a push must not rerun a multi-minute suite to fail again)
        from plumb.verify.evidence import GOOD_OUTCOMES as GOOD

        out.update({"reused": True, "run_id": latest.get("run_id"), "verdict": "failed",
                    "needed": bool((pending or unverified) and not waived),
                    "failed": [n.get("id") or n.get("nodeid") or "" for n in latest.get("nodes") or []
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
                "verdict": verdict_of(result),
                "failed": list(getattr(result, "failed", None) or [])[:50]})
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
