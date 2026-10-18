"""``merge_report``, ``render`` and ``exit_code`` (sp3 3 to 7, 9; SR-047 to SR-050, SR-052).

One process in the working tree over ``BASE..HEAD`` plus uncommitted changes. It reads the
committed records and logs, runs the full suite at most once (``fullrun``), and writes nothing
but one ``merge-evidence`` entry on a green report. No candidate checkouts, transactions,
admission or coordination locks, manifests or guarded publish: it reports and exits.

Exit precedence: 1 (log integrity, validation errors, stale or dangling links of a touched
requirement, links the range leaves stale or adds to untested
files) before 5 (verification, and for work landing on the default branch a delivered
requirement whose proof is not shown working or not confirmed by the owner) before 4 (an open
intent conflict, a sure contradiction, a question waiting for the owner on a required record);
0 is green. Records waiting on a judge, extensions, exemptions added in the range and
undeclared or untraced paths are listed and never hold (SR-260, DEC-252, DEC-255 to DEC-257).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any

from plumb.boundary.fullrun import Runner

CAP = 10
MORE = "+{n} more (plumb merge-check --json)"
SET_UNCONFIRMED = "set unconfirmed"


@dataclass(frozen=True)
class MergeReport:
    """Every section of the merge boundary as data (sp3 9). ``exit`` is ``exit_code``."""

    base: str = ""
    fork: str = ""
    head: str = ""
    changed: tuple[str, ...] = ()
    touched: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    awaiting: tuple[Mapping[str, Any], ...] = ()   # {id, state, new_ends, changed_tests, set}
    untraced: tuple[str, ...] = ()
    new_exempt: tuple[str, ...] = ()
    glance: tuple[Mapping[str, Any], ...] = ()
    repinned_unjudged: tuple[str, ...] = ()
    full_run: Mapping[str, Any] = field(default_factory=dict)
    claims: Mapping[str, Any] = field(default_factory=dict)
    links: tuple[Mapping[str, Any], ...] = ()
    failing: Mapping[str, Any] = field(default_factory=dict)
    unverified: Mapping[str, Any] = field(default_factory=dict)
    regressions: tuple[str, ...] = ()
    fidelity: tuple[Mapping[str, Any], ...] | None = ()   # None: the judgment lane is absent
    integrity: tuple[str, ...] = ()
    # sp6 10: two records holding one ID ({id, paths, sides, how}); exit 1
    id_collisions: tuple[Mapping[str, Any], ...] = ()
    verification: Mapping[str, Any] = field(default_factory=dict)
    run_full: bool = False
    evidence: str | None = None      # digest of the merge-evidence entry (green, run_full)
    error: str | None = None         # the range could not be read (exit 2)
    # sp6 10: record paths git left unmerged (exit 1) and open intent conflicts as their
    # cards (exit 4), on the merge result, so the report can run in the middle of a merge
    unmerged: tuple[Mapping[str, Any], ...] = ()          # {path, record, title, how, line}
    intent_conflicts: tuple[Mapping[str, Any], ...] = ()  # {ic, record, title, card}
    exit: int = 0
    legacy_log_lines: int = 0        # SP6 6.5: legacy JSONL lines not migrated (a warning)
    # SR-127, DEC-037: touched requirements whose proof was not shown working ({id, title,
    # why}: no proof, not run, failed); information for the owner, never a hold
    not_shown: tuple[Mapping[str, Any], ...] = ()
    # SR-165, SR-166: the sections the pre-merge hook prints (``premerge.drift_problems``):
    # new stale links and links to untested files hold (exit 1), contradictions wait (exit 4)
    stale_links: tuple[str, ...] = ()
    untested_links: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    contradiction_notes: tuple[str, ...] = ()
    judge_note: str = ""
    # SR-260 EX-30: the judge's questions waiting for the owner on a required record (exit 4)
    questions: tuple[Mapping[str, Any], ...] = ()     # {key, question, records, titles}
    # SR-260 EX-28, DEC-256: work landing on the default branch delivers a requirement (an SR
    # trailer in the range) whose proof is not shown working or not confirmed (exit 5)
    proofs: tuple[Mapping[str, Any], ...] = ()        # {id, title, why}


def as_dict(report: MergeReport) -> dict[str, Any]:
    """The report as plain JSON-ready data (``--json``)."""
    return {f.name: getattr(report, f.name) for f in fields(report)}


def exit_code(report: MergeReport) -> int:
    """1 (integrity, links) before 5 (verification, proofs) before 4 (conflicts, questions).

    Fails closed: green needs verification evidence, so a verification that could not be
    read (``available`` false or absent: the lane is missing, or reading the evidence, the
    tree identity or the test map raised) holds the merge with 5, like a pending full run.
    This is the one choke point for every entry (``merge-check``, ``validate --merge``, the
    pre-push hook): each takes its exit from here, and the quick check takes its test hold
    from ``verification_holds`` too (SR-260 EX-10). ``not_shown`` never counts (DEC-037);
    ``awaiting``, ``untraced``, ``new_exempt`` and the claims are listed and never count
    (SR-260)."""
    if report.error:
        return 2
    if report.integrity or report.links or report.id_collisions or report.unmerged or \
            report.stale_links or report.untested_links:
        return 1
    if verification_holds(report.verification) or report.regressions or report.failing or \
            report.unverified or report.proofs:
        return 5
    if report.intent_conflicts or report.contradictions or report.questions:
        return 4
    return 0


def verification_holds(verification: Mapping[str, Any]) -> bool:
    """SR-254, SR-260 (c): ``merge._verification`` holds the merge (exit 5) on a failing or
    regressed acceptance test, one with no passing run on the current code, a full
    verification pending and not waived, or a verification that could not be read (fails
    closed). The one rule of both forms of the check (EX-10)."""
    full_held = bool(verification.get("full_pending") and not verification.get("full_waived"))
    return not verification.get("available") or full_held or bool(
        verification.get("failing") or verification.get("unverified")
        or verification.get("regressions"))


# --------------------------------------------------------------------------- gathering


def _escalated_sets(index: Mapping[str, Any]) -> dict[str, list[str]]:
    """``{member: [anchor INT, ...]}`` of the escalated sets (sp2 6.2)."""
    out: dict[str, list[str]] = {}
    for record in index.values():
        members = record.fields.get("members")
        if record.kind == "intent" and record.fields.get("mode") == "escalated" \
                and isinstance(members, list):
            for member in members:
                out.setdefault(str(member), []).append(record.id)
    return out


def _set_confirmed(core: Any, members: Sequence[str]) -> bool:
    """Whether a valid approval, not revoked since, pins every member's current hash (an
    approval a renumber carried pins the renumbered member: R17)."""
    from plumb.confirm import checked_entries, pinned_through_renumbers

    index = core.index()
    want = {m: index[m].hash for m in members if m in index}
    if len(want) != len(set(members)):
        return False
    confirmed = False
    pairs = checked_entries(core.events(), core.config.approve.affirmations, core=core)
    for entry, problem, items in pinned_through_renumbers(core, pairs):
        if problem is not None:
            continue
        pinned = {str(r.get("id")): str(r.get("hash")) for r in items}
        if entry.kind == "approval" and all(pinned.get(m) == h for m, h in want.items()):
            confirmed = True
        elif entry.kind == "revocation" and any(pinned.get(m) == h for m, h in want.items()):
            confirmed = False
    return confirmed


def _awaiting(core: Any, fork: str, paths: Sequence[str],
              required: Sequence[str]) -> list[dict[str, Any]]:
    from plumb.merge import CHANGED_TEST, _describe, changed_test_lines, extended_requirements

    statuses = core.status(required)
    extended = extended_requirements(core, fork, paths)
    index = core.index()
    sets = _escalated_sets(index)
    rows: list[dict[str, Any]] = []
    for record_id in required:
        status = statuses[record_id]
        row: dict[str, Any] = {"id": record_id, "new_ends": extended.get(record_id, [])}
        if status.confirmation != "confirmed":
            row["state"] = CHANGED_TEST if status.changed_tests else status.confirmation
            if status.changed_tests:
                row["changed_tests"] = list(status.changed_tests)
        elif record_id in extended:
            row["state"] = "extended"
        else:
            anchors = [a for a in sets.get(record_id, ())
                       if not _set_confirmed(core, index[a].fields.get("members") or [])]
            if not anchors:
                continue
            row["state"] = SET_UNCONFIRMED
            row["set"] = anchors[0]
        lines = _describe(core, record_id, row["state"], row["new_ends"])
        if status.changed_tests and row["state"] == CHANGED_TEST:
            lines += changed_test_lines(core, fork, record_id, status.changed_tests)
        if row["state"] == SET_UNCONFIRMED:
            lines.append(f"    member of the escalated set {row['set']}: confirm the whole set "
                         f"(plumb spec show {row['set']})")
        row["lines"] = lines
        rows.append(row)
    return rows


def _waived(core: Any, fork: str) -> bool:
    from plumb.verify.policy import range_digest, waived

    try:
        return bool(waived(core, range_digest(core.root, fork)))
    except Exception:
        return False


def _id_collisions(core: Any, fork: str) -> list[dict[str, Any]]:
    """Two records holding one ID in the merge result (sp6 5.1, 10; SR-072)."""
    from dataclasses import asdict

    from plumb import ids

    return [asdict(c) for c in ids.collisions(core, fork)]


def _validation_errors(core: Any) -> list[str]:
    from plumb.validate import validate

    return [f"validate: {f.line()}" for f in validate(core) if f.severity == "error"]


def _legacy_log_lines(core: Any) -> int:
    from plumb.log import legacy_count

    return legacy_count(core.paths)


def _not_shown(core: Any, touched: Sequence[str]) -> list[dict[str, Any]]:
    """SR-127: the touched requirements not shown working; advisory, so an error reading
    them names nothing rather than failing the report."""
    try:
        from plumb.capture.proof import not_shown

        return not_shown(core, touched)
    except Exception:  # noqa: BLE001 - information only, never a hold
        return []


def _merge_state(core: Any, hook: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(unmerged, intent_conflicts)`` of the working tree (sp6 10); inside a git hook the
    cards use logged judgments only (``conflict_rows``)."""
    from plumb.mergedriver.conflicts import conflict_rows
    from plumb.mergedriver.unmerged import unmerged_rows

    return unmerged_rows(core), conflict_rows(core, hook=hook)


def merge_report(core: Any, base: str, *, run_full: bool = True,
                 runner: Runner | None = None, hook: bool = False) -> MergeReport:
    """Every section of the merge boundary against ``base``; runs the full suite at most once
    (only with ``run_full``) and records the merge evidence on green (only with
    ``run_full``). ``hook`` (the pre-push hook): intent-conflict cards use logged judgments
    only, never a live backend call."""
    from plumb.approvals import approved_exempt
    from plumb.boundary.fidelity import fidelity_rows, jev_scores, repinned_unjudged
    from plumb.boundary.fullrun import full_run, record_merge_evidence
    from plumb.boundary.gates import claims_gate, link_rows
    from plumb.boundary.glance import glance_rows
    from plumb.boundary.premerge import (
        default_branch_of,
        delivered_proofs,
        merged_messages,
        open_questions_on,
    )
    from plumb.merge import (
        GitError,
        _git,
        _verification,
        base_config,
        changed_paths,
        log_integrity,
        required_records,
        touched_requirements,
    )
    from plumb.trace import untraced_paths

    try:
        _git(core, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
        paths, messages = changed_paths(core, base)
        fork = _git(core, "merge-base", base, "HEAD").strip()
        head = _git(core, "rev-parse", "HEAD").strip()
    except (GitError, OSError) as exc:
        return MergeReport(base=base, error=f"cannot read the range {base}..HEAD: {exc}",
                           exit=2, run_full=run_full)

    touched = touched_requirements(core, paths, messages)
    required = required_records(core, touched)
    awaiting = _awaiting(core, fork, paths, required)
    # the owner's exemptions: those at the merge base and those the owner confirmed; a glob
    # added in the range waits for the owner, and the base config's layout still counts
    before = base_config(core, fork)
    seen = set(before.trace.exempt) | approved_exempt(core)
    current_globs = [str(g) for g in core.config.trace.exempt]
    new_exempt = [g for g in current_globs if g not in seen]
    honoured = [g for g in current_globs if g in seen]
    untraced = untraced_paths(core, paths, configs=[core.config, before], exempt=honoured)

    problems, base_digests = log_integrity(core, base)
    integrity = list(problems) + _validation_errors(core)
    id_collisions = _id_collisions(core, fork)
    glance = glance_rows(core, base_digests.get("events", set()))
    claims = claims_gate(core, fork)
    links = link_rows(core, touched)

    verification = _verification(core, touched, paths, fork)
    run: dict[str, Any] = {"needed": None, "ran": False, "reused": False, "run_id": None,
                           "verdict": "unavailable", "reasons": []}
    if verification.get("available"):
        from plumb.verify import open_verify

        pending = bool(verification.get("full_pending"))
        unverified = bool(verification.get("unverified"))
        waived = bool(verification.get("full_waived")) or (
            (pending or unverified) and _waived(core, fork))
        run = full_run(core, open_verify(core), pending=pending,
                       reasons=list(verification.get("full_pending_reasons") or []),
                       unverified=unverified, waived=waived, run_full=run_full,
                       runner=runner)
        if run["ran"]:  # the state after the one run, from a fresh view of the evidence
            verification = _verification(core, touched, paths, fork)
    identity = run.pop("identity", None)

    fidelity = fidelity_rows(core, touched)
    if fidelity:
        jev_scores(core, fidelity)
    repinned = repinned_unjudged(core, touched, paths)
    # DEC-256: a proof holds only what a merge brings into the default branch (EX-29)
    try:
        here = _git(core, "symbolic-ref", "--short", "-q", "HEAD").strip()
    except (GitError, OSError):
        here = ""
    proofs = delivered_proofs(core, merged_messages(core.root, base)) \
        if here == default_branch_of(core.root) else []

    report = MergeReport(
        base=base, fork=fork, head=head, changed=tuple(paths), touched=tuple(touched),
        required=tuple(required), awaiting=tuple(awaiting), untraced=tuple(untraced),
        new_exempt=tuple(new_exempt), glance=tuple(glance),
        repinned_unjudged=tuple(repinned), full_run=run, claims=claims, links=tuple(links),
        failing=verification.get("failing") or {},
        unverified=verification.get("unverified") or {},
        regressions=tuple(verification.get("regressions") or ()),
        fidelity=None if fidelity is None else tuple(fidelity),
        integrity=tuple(integrity), id_collisions=tuple(id_collisions),
        verification=verification, run_full=run_full,
        legacy_log_lines=_legacy_log_lines(core),
        not_shown=tuple(_not_shown(core, touched)),
        questions=tuple(open_questions_on(core, required)), proofs=tuple(proofs))
    unmerged, conflicts = _merge_state(core, hook)
    report = _replace(report, unmerged=tuple(unmerged), intent_conflicts=tuple(conflicts))
    if not hook:   # the pre-push hook makes no live judge call; the pre-merge hook did these
        from plumb.boundary.premerge import drift_problems

        report = _replace(report, **drift_problems(core, fork, paths))
    code = exit_code(report)
    evidence = None
    if code == 0 and run_full and identity is not None:
        index = core.index()
        evidence = record_merge_evidence(core, {
            "base": base, "fork": fork, "head": head,
            "head_tree": identity["tree"].get("head_tree"),
            "dirty": identity["tree"].get("dirty"), "full_run": run.get("run_id"),
            "reused": bool(run.get("reused")), "env": identity["env"],
            "touched": list(touched),
            "confirmed": [{"id": i, "hash": index[i].hash} for i in required],
            "verdict": "green"})
    return _replace(report, evidence=evidence, exit=code)


def _replace(report: MergeReport, **changes: Any) -> MergeReport:
    from dataclasses import replace

    return replace(report, **changes)


# --------------------------------------------------------------------------- rendering


def _capped(rows: Sequence[str]) -> list[str]:
    out = list(rows[:CAP])
    if len(rows) > CAP:
        out.append("  " + MORE.format(n=len(rows) - CAP))
    return out


def _names(items: Sequence[str]) -> str:
    shown = ", ".join(items[:CAP])
    return shown + (" " + MORE.format(n=len(items) - CAP) if len(items) > CAP else "")


def _full_run_line(run: Mapping[str, Any], verification: Mapping[str, Any]) -> str:
    reasons = ", ".join(run.get("reasons") or []) or "touched acceptance tests unverified"
    if run.get("verdict") == "unavailable":
        return "full run: unavailable"
    if run.get("reused"):
        return (f"full run reused (run {run.get('run_id')}): passed on this tree and "
                "environment")
    if run.get("ran"):
        line = f"full run: ran once (run {run.get('run_id')}): {run.get('verdict')}"
        failed = run.get("failed") or []
        if failed:
            line += f" ({len(failed)} failed: {', '.join(failed[:3])}" + (
                " ...)" if len(failed) > 3 else ")")
        return line + "; never repeated in this check"
    if run.get("waived"):
        return f"full run: waived by the owner for this exact change ({reasons})"
    if run.get("needed"):
        return (f"full run: needed ({reasons}); not run (--no-run or validate --merge): "
                "plumb merge-check runs it once")
    latest = run.get("run_id")
    return "full run: not needed" + (f" (latest full run {latest} holds)" if latest else "")


def render(report: MergeReport) -> list[str]:
    """The one-screen report: at most about 12 lines outside the lists, each list capped at
    10 rows with the rest in ``--json``."""
    from plumb.boundary.gates import claims_lines, link_line
    from plumb.boundary.glance import glance_line
    from plumb.merge import failing_line

    if report.error:
        return [f"plumb: {report.error}"]
    out = [f"plumb merge-check: {report.base}..HEAD plus uncommitted changes"]
    out.append("touched requirements: " + (_names(report.touched) if report.touched
                                           else "none"))
    if report.untraced:
        out.append("untraced changes (no requirement owns them): " + _names(report.untraced))
    from plumb.boundary.premerge import hold_lines

    out.extend(hold_lines(report, "the default branch"))
    if report.awaiting or report.untraced or report.new_exempt:
        out.append("listed for you (none of this holds the merge):")
        out.extend(_awaiting_lines(report))
        out.extend(_capped([f"  untraced {p}: no read-back or example covers this change"
                            for p in report.untraced]))
        out.extend(_capped([f"  trace.exempt {g}: added in this range; it exempts paths from "
                            "any requirement and is not honoured until it is approved"
                            for g in report.new_exempt]))
        if report.awaiting:     # counted, no id and no command (SR-260 EX-8, EX-31, SR-267)
            n = len(report.awaiting)
            out.append(f"plumb: waiting on a judge: {n} record{'s' if n > 1 else ''}; the "
                       "judge approves them on your behalf or asks you a question with the "
                       "question tool")
        if report.new_exempt:
            # shortcut: no route approves a glob since plumb approve went, until SR-288 picks one
            out.append("plumb: nothing can approve a new trace.exempt glob yet (the judge "
                       "approves records only); until then it is not honoured")
        if report.untraced:
            out.append("plumb: for the untraced changes, ask the agent to read them back and "
                       "record a requirement linked implemented_by them; or, if they need no "
                       "requirement, list them under trace.exempt in .plumb/config.yaml")
    else:
        out.append("confirmation: every touched requirement is confirmed")
    if report.glance:
        out.append("approvals in range (for a glance; to undo one you did not mean, say so "
                   "in conversation):")
        out.extend(_capped([glance_line(row) for row in report.glance]))
    else:
        out.append("approvals in range: none")
    if report.repinned_unjudged:
        out.append("repinned without a judgment: " + ", ".join(
            f"{i} (plumb fidelity {i})" for i in report.repinned_unjudged[:CAP]))
    out.extend(_fidelity_lines(report))
    out.extend(_not_shown_lines(report))
    out.extend(_verification_lines(report, failing_line))
    out.extend(collision_lines(report.id_collisions))
    claims = claims_lines(dict(report.claims))
    if claims:
        out.append("claims (listed; they do not hold the merge):")
        out.extend(_capped([f"  {row}: {fix}" for row, fix in claims]))
    if report.links:
        out.append("links of touched requirements hold the merge:")
        out.extend(_capped([link_line(dict(row)) for row in report.links]))
    from plumb.boundary.premerge import drift_lines

    out.extend(drift_lines(report))
    if report.unmerged:
        from plumb.mergedriver.unmerged import unmerged_lines

        out.extend(unmerged_lines([dict(r) for r in report.unmerged]))
    if report.intent_conflicts:
        from plumb.present.owner_text import CONFLICTS_HEADER

        out.append(CONFLICTS_HEADER)
        for conflict in report.intent_conflicts:
            out.extend(str(line) for line in conflict.get("card") or [])
    if report.integrity:
        out.append("log integrity: FAILED")
        out.extend(_capped([f"  {problem}" for problem in report.integrity]))
    else:
        out.append("log integrity: ok")
    if report.legacy_log_lines:
        from plumb.present.owner_text import LEGACY_LOG

        out.append(LEGACY_LOG.format(n=report.legacy_log_lines))
    if report.evidence:
        out.append(f"merge evidence: recorded ({report.evidence[:19]})")
    return out


def collision_lines(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The ``id_collisions`` section in the owner's terms (titles, and the fix to say)."""
    if not rows:
        return []
    from plumb.present.owner_text import COLLISION, COLLISIONS_HEADER

    lines = []
    for row in rows:
        sides = list(row.get("sides") or ()) + ["", ""]
        where = ", ".join(row.get("paths") or ())
        if row.get("how") == "add/add":
            where += " (both branches added it)"
        elif row.get("how") == "kept-one":
            where += " (both branches added it; the merge kept only one)"
        lines.append(COLLISION.format(id=row.get("id"), ours=sides[0], theirs=sides[1],
                                      where=where))
    return [COLLISIONS_HEADER, *_capped(lines)]


def _awaiting_lines(report: MergeReport) -> list[str]:
    lines: list[str] = []
    for row in report.awaiting[:CAP]:
        lines.extend(row.get("lines") or [f"  {row['id']} ({row['state']})"])
    if len(report.awaiting) > CAP:
        lines.append("  " + MORE.format(n=len(report.awaiting) - CAP))
    return lines


NOT_SHOWN_WHY = {"no proof": "no proof planned", "not run": "proof planned, not run",
                 "failed": "its evidence did not show it working"}


def _not_shown_lines(report: MergeReport) -> list[str]:
    """SR-127: named for the owner, who decides (DEC-037); the hold is ``proofs`` (DEC-256)."""
    if not report.not_shown:
        return (["shown working: every touched requirement"] if report.touched else [])
    rows = [f"  {row['id']} {row.get('title', '')}: "
            f"{NOT_SHOWN_WHY.get(str(row.get('why')), str(row.get('why')))} "
            f"(plumb show {row['id']})" for row in report.not_shown]
    return ["not shown working yet (information; a proof holds only work landing on the default "
            "branch that delivers it):", *_capped(rows)]


def _fidelity_lines(report: MergeReport) -> list[str]:
    if report.fidelity is None:
        return ["fidelity: unavailable"]
    if not report.fidelity:
        return ["fidelity: every touched requirement judged"]
    rows = []
    for row in report.fidelity:
        line = f"  {row['id']} {row['state']}: {row['command']}"
        jev = row.get("jev")
        if jev:
            line += f" | jev: {jev['verdict']} ({jev['confidence']}), advisory"
        rows.append(line)
    return ["fidelity (advisory, never holds the merge):", *_capped(rows)]


def _verification_lines(report: MergeReport, failing_line: Any) -> list[str]:
    verification = report.verification
    out = [_full_run_line(report.full_run, verification)]
    if not verification.get("available"):
        error = verification.get("error")
        out.append("verification: unavailable" + (f" ({error})" if error else "")
                   + "; it holds the merge: green needs test evidence (fix the cause and "
                     "rerun plumb merge-check)")
        return out
    if verification.get("full_pending"):
        reasons = ", ".join(verification.get("full_pending_reasons") or [])
        if verification.get("full_waived"):
            out.append(f"verification: full verification pending ({reasons}); waived by the "
                       "owner for this exact change")
        else:
            out.append(f"verification: full verification pending ({reasons}); it holds the "
                       "merge until a full run passes (plumb merge-check runs it once), or the "
                       "owner waives it for this change in their own terminal (plumb tests "
                       f"waive --merge {report.base} --reason ...)")
    else:
        out.append("verification: no full verification pending")
    if verification.get("confirmed_not_covered"):
        out.append("confirmed but not covered: "
                   + _names(list(verification["confirmed_not_covered"])))
    rows = [failing_line(record_id, item) for record_id, items in report.failing.items()
            for item in items]
    out.extend(_capped([f"failing acceptance tests: {row}" for row in rows]))
    rows = []
    for record_id, items in report.unverified.items():
        for item in items:
            examples = " ".join(item.get("examples") or ())
            what = "never run" if item.get("state") == "none" else "stale since its last pass"
            rows.append(" ".join(p for p in (record_id, examples, str(item.get("test")),
                                             f"({what})") if p))
    out.extend(_capped([f"unverified acceptance tests: {row}" for row in rows]))
    affected = verification.get("affected") or []
    if affected:
        out.append("acceptance tests this change can affect (other requirements): "
                   + _names(list(affected)))
    if report.failing or report.unverified:
        out.append("verification holds the merge: every acceptance test the change can affect "
                   "needs a passing run on the current code (plumb tests run --nodes <test>)")
    if report.regressions:
        regressions = list(report.regressions)
        out.append(f"regression: {_names(regressions)} passed in an earlier run and now fails; "
                   "the merge waits until a run passes them (plumb tests run --nodes <id>), or "
                   "the owner decides")
    return out
