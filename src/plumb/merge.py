"""The merge boundary: ``plumb validate --merge <base>`` (spec 5.11, rulings R1 and R2).

Over ``<base>..HEAD`` plus uncommitted changes:

1. every touched requirement, the INT records it derives from, and each matters-true DEC that
   decides it must be confirmed at its current hash, and every changed source path must be
   owned by a requirement (``plumb.trace``: an untraced change skipped the read-back), or the
   merge waits (exit 4): one trigger-2 question lists both;
2. the approvals and revocations added in the range are listed, agent-relayed ones marked with
   the prompt digest they cite;
3. fidelity (advisory) and 4. verification state, from the BRIDGE and VERIFY lanes when they
   are built, otherwise ``unavailable``: full verification pending, touched requirements
   whose acceptance tests fail (with their example ids), and unresolved regressions (R3),
   which make the merge exit 5 until a run passes them again;
5. every log line present at the merge base of ``<base>`` and HEAD must still be present,
   unchanged (exit 1 otherwise).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.hashing import clean_rel_path, target_path
from plumb.trailers import parse_sr_trailer

if TYPE_CHECKING:
    from plumb.api import Core

EXIT_MERGE_WAITS = 4
EXIT_REGRESSION = 5


class GitError(RuntimeError):
    pass


def _git(core: Core, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=core.root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout if result.returncode == 0 else ""


def changed_paths(core: Core, base: str) -> tuple[list[str], list[str]]:
    """(paths changed between the merge base and the working tree, commit messages)."""
    merge_base = _git(core, "merge-base", base, "HEAD").strip()
    diff = _git(core, "diff", "--relative", "--name-only", "-z", merge_base)
    untracked = _git(core, "ls-files", "--others", "--exclude-standard", "-z")
    paths = sorted({p for p in (diff + "\0" + untracked).split("\0") if p})
    log_out = _git(core, "log", "--format=%B%x00", f"{base}..HEAD")
    messages = [m for m in log_out.split("\0") if m.strip()]
    return paths, messages


def touched_requirements(core: Core, paths: Sequence[str],
                         messages: Sequence[str]) -> list[str]:
    index = core.index()
    changed = {clean_rel_path(p) or p for p in paths}
    touched: set[str] = set()
    for record in index.values():
        if record.kind != "requirement":
            continue
        if record.path in changed:
            touched.add(record.id)
            continue
        for link in record.links:
            if link.kind in ("implemented_by", "verified_by"):
                end = target_path(link.target)
                if end and (clean_rel_path(end) or end) in changed:
                    touched.add(record.id)
                    break
    for message in messages:
        for claimed in parse_sr_trailer(message):
            if claimed in index and index[claimed].kind == "requirement":
                touched.add(claimed)
    return sorted(touched)


def required_records(core: Core, touched: Sequence[str]) -> list[str]:
    """Touched SRs, the INTs they derive from, and matters-true DECs deciding them."""
    index = core.index()
    required: list[str] = []

    def need(record_id: str) -> None:
        if record_id in index and record_id not in required:
            required.append(record_id)

    for sr in touched:
        need(sr)
        for link in index[sr].links:
            if link.kind == "derives_from" and link.target.record:
                need(link.target.record)
    for record in index.values():
        if record.kind == "decision" and record.fields.get("matters") is True:
            for link in record.links:
                if link.kind == "decides" and link.target.record in touched:
                    need(record.id)
    return required


def _base_lines(core: Core, commit: str, stream: str) -> list[str]:
    rel = f"./.plumb/log/{stream}.jsonl"
    result = subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=core.root,
                            capture_output=True)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.decode("utf-8", "replace").splitlines()
            if line.strip()]


def log_integrity(core: Core, base: str) -> tuple[list[str], dict[str, set[str]]]:
    """Problems (merge-base lines missing or changed) and the digests present there.

    Lines are read at ``git merge-base <base> HEAD``, not at the tip of ``base``: entries the
    base appended after the branch diverged are not part of this branch's history, so their
    absence is not tampering.
    """
    fork = _git(core, "merge-base", base, "HEAD").strip()
    problems: list[str] = []
    base_digests: dict[str, set[str]] = {}
    for stream in ("events", "evidence"):
        path = core.paths.log_path(stream)
        try:
            current = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
        except OSError:
            current = set()
        digests: set[str] = set()
        for number, line in enumerate(_base_lines(core, fork, stream), start=1):
            try:
                digests.add(str(json.loads(line).get("digest")))
            except ValueError:
                pass
            if line not in current:
                problems.append(f"{path.name}: line {number} at merge-base {fork[:12]} is "
                                "missing or changed")
        base_digests[stream] = digests
    return problems, base_digests


def _describe(core: Core, record_id: str, state: str) -> list[str]:
    record = core.index()[record_id]
    fields = record.fields
    text = (fields.get("statement") or fields.get("readback") or fields.get("chosen")
            or fields.get("description") or "")
    quote = fields.get("quote")
    lines = [f"  {record_id} ({state}) {record.title}" + (f": {text}" if text else "")]
    if record.kind == "intent" and quote:
        quoted = quote if isinstance(quote, str) else " / ".join(map(str, quote))
        lines.append(f"    owner's words: \"{quoted}\"")
    if record.kind == "decision" and fields.get("question"):
        lines.append(f"    question: {fields.get('question')}")
    for example in record.examples:
        if example.criterion:
            lines.append(f"    {example.id}: {example.criterion}")
        else:
            lines.append(f"    {example.id}: given {example.given}, when {example.when}, "
                         f"then {example.then}")
    return lines


def _approval_rows(core: Core, base_digests: set[str]) -> list[dict[str, Any]]:
    rows = []
    for entry in core.events():
        if entry.kind not in ("approval", "revocation") or entry.digest in base_digests:
            continue
        payload: Mapping[str, Any] = entry.payload
        rows.append({"kind": entry.kind, "by": payload.get("by"), "at": entry.at,
                     "records": [r.get("id") for r in payload.get("records") or []
                                 if isinstance(r, Mapping)],
                     "quote": payload.get("quote"), "prompt_digest": payload.get("prompt_digest"),
                     "marker": entry.marker})
    return rows


def _fidelity(core: Core, touched: Sequence[str]) -> list[str] | None:
    try:
        from plumb.judgment.fidelity import unjudged
    except ImportError:
        return None
    return list(unjudged(core, touched))


def _verification(core: Core, touched: Sequence[str]) -> dict[str, Any]:
    statuses = core.status(touched)
    not_covered = [i for i, s in statuses.items() if s.confirmation == "confirmed"
                   and not s.covered]
    out: dict[str, Any] = {"confirmed_not_covered": not_covered}
    try:
        from plumb.verify import open_verify
    except ImportError:
        out["available"] = False
        return out
    try:
        verify = open_verify(core)
        pending = verify.full_pending()
        out.update({"available": True, "full_pending": pending.pending,
                    "full_pending_reasons": list(pending.reasons),
                    "failing": verify.requirement_failures(touched),
                    "regressions": verify.unresolved_regressions()})
    except Exception as exc:  # a lane failure degrades, never blocks the boundary
        out.update({"available": False, "error": str(exc)})
    return out


def failing_line(record_id: str, item: Mapping[str, Any]) -> str:
    """``SR-001 EX-1 tests/test_x.py (regression)``: one failing acceptance test."""
    examples = " ".join(item.get("examples") or ())
    kind = "regression" if item.get("regression") else "failing"
    return " ".join(p for p in (record_id, examples, str(item.get("test")), f"({kind})") if p)


def merge_check(core: Core, base: str, *, as_json: bool) -> int:
    """Run the merge-boundary checks against ``base``; prints a report; returns the exit."""
    try:
        _git(core, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
        paths, messages = changed_paths(core, base)
    except (GitError, OSError) as exc:
        print(f"plumb: cannot read the range {base}..HEAD: {exc}")
        return 2
    from plumb.trace import untraced_paths

    touched = touched_requirements(core, paths, messages)
    required = required_records(core, touched)
    statuses = core.status(required)
    awaiting = [(i, statuses[i].confirmation) for i in required
                if statuses[i].confirmation != "confirmed"]
    untraced = untraced_paths(core, paths)
    integrity, base_digests = log_integrity(core, base)
    approvals = _approval_rows(core, base_digests.get("events", set()))
    fidelity = _fidelity(core, touched)
    verification = _verification(core, touched)
    regressions = verification.get("regressions") or []
    failing = verification.get("failing") or {}
    if integrity:
        code = 1
    elif regressions:
        code = EXIT_REGRESSION
    else:
        code = EXIT_MERGE_WAITS if awaiting or untraced else 0

    if as_json:
        print(json.dumps({
            "base": base, "changed": paths, "touched": touched, "required": required,
            "awaiting": [{"id": i, "state": s} for i, s in awaiting],
            "untraced": untraced,
            "approvals": approvals,
            "fidelity": "unavailable" if fidelity is None else fidelity,
            "verification": verification, "log_integrity": integrity, "exit": code,
        }, indent=2, default=str))
        return code

    print(f"plumb merge boundary: {base}..HEAD plus uncommitted changes")
    print("touched requirements: " + (", ".join(touched) if touched else "none"))
    if untraced:
        print("untraced changes (no requirement owns them): " + ", ".join(untraced))
    if awaiting or untraced:
        print("merge waits for your confirmation:")
        for record_id, state in awaiting:
            for line in _describe(core, record_id, state):
                print(line)
        for path in untraced:
            print(f"  untraced {path}: no read-back or example covers this change")
        if awaiting:
            ids = " ".join(i for i, _ in awaiting)
            print(f"plumb: merge waits for your confirmation: `plumb approve {ids}`, or say ok "
                  "in the session")
        if untraced:
            print("plumb: for the untraced changes, ask the agent to read them back and record "
                  "a proposed SR linked implemented_by them, then confirm it; or, if they need "
                  "no requirement, list them under trace.exempt in .plumb/config.yaml")
    else:
        print("confirmation: every touched requirement is confirmed")
    if approvals:
        print("approvals in range (for a glance):")
        for row in approvals:
            records = ", ".join(map(str, row["records"]))
            line = f"  {row['kind']} {row['by']} {records} at {row['at']}"
            if row["by"] == "agent-relayed":
                line += (f" | AGENT-RELAYED quote \"{row['quote']}\" prompt "
                         f"{str(row['prompt_digest'])[:19]}")
            print(line)
    else:
        print("approvals in range: none")
    if fidelity is None:
        print("fidelity: unavailable")
    elif fidelity:
        for sr in fidelity:
            print(f"fidelity (advisory): {sr} unjudged, drifts or unsure: plumb fidelity {sr}")
    else:
        print("fidelity: every touched requirement judged")
    if not verification.get("available"):
        print("verification: unavailable")
    elif verification.get("full_pending"):
        reasons = ", ".join(verification.get("full_pending_reasons") or [])
        print(f"verification: full verification pending ({reasons}); run plumb tests run --full")
    else:
        print("verification: no full verification pending")
    if verification["confirmed_not_covered"]:
        print("confirmed but not covered: " + ", ".join(verification["confirmed_not_covered"]))
    for record_id, items in failing.items():
        for item in items:
            print("failing acceptance tests: " + failing_line(record_id, item))
    if regressions:
        shown = ", ".join(regressions[:5]) + (f" +{len(regressions) - 5} more"
                                              if len(regressions) > 5 else "")
        print(f"regression: {shown} passed in an earlier run and now fails; the merge waits "
              "until a run passes them (plumb tests run --nodes <id>), or the owner decides")
    if integrity:
        print("log integrity: FAILED")
        for problem in integrity:
            print(f"  {problem}")
    else:
        print("log integrity: ok")
    return code
