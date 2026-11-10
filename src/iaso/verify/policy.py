"""Failure policy (spec 7.5): the regression rule, exactly as ruling R3.

A failing node is a regression when an earlier ``test-run`` entry recorded the same node id
``passed`` or ``flaky``, whatever happened to its source since. A changed ``test_hash`` adds
the note ``test source changed since the pass`` and never clears the flag. Only a new test
that starts red (a node id with no recorded pass) is exempt: it is ``not yet passing``, never
a regression, and never interrupts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from iaso.contracts import NodeEvidence

NOTE_CHANGED = "test source changed since the pass"


def is_regression(index: Mapping[str, Any], node_id: str) -> bool:
    entry = index.get("nodes", {}).get(node_id) or {}
    last = entry.get("last") or {}
    return last.get("outcome") == "failed" and entry.get("last_pass") is not None


def pass_run(index: Mapping[str, Any], node_id: str) -> str | None:
    entry = index.get("nodes", {}).get(node_id) or {}
    last_pass = entry.get("last_pass") or {}
    return last_pass.get("run_id")


def regression_instruction(node_id: str, run_id: str | None, test_changed: bool) -> str:
    """The trigger-3 instruction (spec 6.4), with the note when the test source changed."""
    note = f" ({NOTE_CHANGED})" if test_changed else ""
    return (f"iaso: regression: {node_id} passed in run {run_id or '?'} and now fails{note}. "
            "Tell the owner, with a read-back, and ask how to proceed.")


def classify_failure(evidence: NodeEvidence) -> str:
    """``regression`` or ``not yet passing`` for a failing node (R3)."""
    return "regression" if evidence.regression else "not yet passing"


def same_tree(before: Mapping[str, Any], after: Mapping[str, Any], env_before: str,
              env_after: str) -> bool:
    """Whether a flaky rerun may run: tree identity and env key unchanged (spec 7.5)."""
    return (before.get("head_tree") == after.get("head_tree")
            and before.get("dirty") == after.get("dirty") and env_before == env_after)


# -- owner waiver (VS6) -------------------------------------------------------------------

DIGEST_RE = r"^sha256:[0-9a-f]{64}$"


class WaiverRefused(PermissionError):
    """A waiver attempted under the agent session marker (exit 3)."""


def current_diff_digest(root: Any) -> str:
    """sha256 of ``git diff HEAD`` (the working tree's change against the last commit)."""
    import subprocess

    from iaso.normalize import sha256_bytes

    out = subprocess.run(["git", "diff", "HEAD", "--no-color", "--no-ext-diff"], cwd=root,
                         capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
    return sha256_bytes(out.stdout.replace(b"\r\n", b"\n"))


def range_digest(root: Any, fork: str) -> str:
    """sha256 of ``git diff <fork>`` plus the untracked files, outside ``.iaso/``: the change
    a merge-boundary waiver covers (iaso's own records and logs are left out, so recording
    the waiver does not move the digest it pins; any other edit does)."""
    import subprocess
    from pathlib import Path

    from iaso.normalize import file_digest, sha256_bytes

    out = subprocess.run(["git", "diff", fork, "--no-color", "--no-ext-diff", "--", ".",
                          ":(exclude).iaso"], cwd=root, capture_output=True,
                         timeout=30,
                         stdin=subprocess.DEVNULL)
    others = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z", "--",
                             ".", ":(exclude).iaso"], cwd=root,
                            capture_output=True,
                            timeout=30, stdin=subprocess.DEVNULL)
    parts = [out.stdout.replace(b"\r\n", b"\n")]
    for rel in sorted(p for p in others.stdout.decode("utf-8", "replace").split("\0") if p):
        try:
            digest = file_digest(Path(root) / rel)
        except OSError:
            digest = "unreadable"
        parts.append(f"\0{rel}\0{digest}".encode())
    return sha256_bytes(b"".join(parts))


def waived(core: Any, digest: str) -> bool:
    """Whether an owner waiver (written outside the agent session marker) pins ``digest``."""
    for entry in core.events():
        if (entry.kind == "waiver" and entry.marker == "none"
                and entry.payload.get("by") == "owner"
                and entry.payload.get("diff_digest") == digest):
            return True
    return False


def waive(core: Any, diff_digest: str, reason: str) -> Any:
    """Append the owner's ``waiver`` event pinned to ``diff_digest``; refused under the
    agent session marker and outside an interactive terminal (``approvals.require_owner``).
    Using it in place of a full rerun belongs to sub-project 3."""
    from iaso.approvals import Refused, require_owner

    try:
        require_owner("tests waive", f"waive the full run for diff {diff_digest[:19]} "
                      f"({reason}), as yourself (by: owner)?")
    except Refused as exc:
        raise WaiverRefused(str(exc)) from exc
    return core.log_append("events", "waiver", {"diff_digest": diff_digest, "reason": reason,
                                               "by": "owner"})
