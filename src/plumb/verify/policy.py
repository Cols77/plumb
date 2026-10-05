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

from plumb.contracts import NodeEvidence

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
    return (f"plumb: regression: {node_id} passed in run {run_id or '?'} and now fails{note}. "
            "Tell the owner, with a read-back, and ask how to proceed.")


def classify_failure(evidence: NodeEvidence) -> str:
    """``regression`` or ``not yet passing`` for a failing node (R3)."""
    return "regression" if evidence.regression else "not yet passing"


def same_tree(before: Mapping[str, Any], after: Mapping[str, Any], env_before: str,
              env_after: str) -> bool:
    """Whether a flaky rerun may run: tree identity and env key unchanged (spec 7.5)."""
    return (before.get("head_tree") == after.get("head_tree")
            and before.get("dirty") == after.get("dirty") and env_before == env_after)
