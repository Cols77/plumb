"""``plumb validate`` (spec 5.10): relation validation, log chains and approval re-checks.

Errors: unloadable or duplicate records, malformed IDs, link kinds not allowed between their
ends, dangling links and references, broken log chains, approvals failing their re-check.
Warnings: stale and unpinned links, unconfirmed edits, confirmed examples without a test, an
SR without a derives_from link to an INT, a matters-false DEC deciding a confirmed record, and
one summary line for proposed records awaiting the owner.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from plumb import log
from plumb.confirm import checked_entries
from plumb.links import kind_problem

if TYPE_CHECKING:
    from plumb.api import Core


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warning"
    code: str
    subject: str
    message: str

    def line(self) -> str:
        return f"{self.severity}: [{self.code}] {self.subject}: {self.message}"


def validate(core: Core) -> list[Finding]:
    findings: list[Finding] = []

    def add(severity: str, code: str, subject: str, message: str) -> None:
        findings.append(Finding(severity, code, subject, message))

    for problem in core.store.problems():
        code = "duplicate" if problem.startswith("duplicate id") else "load"
        add("error", code, problem.split(":", 1)[0], problem)
    index = core.index()

    # relations
    for record in index.values():
        for link in record.links:
            problem = kind_problem(link, record)
            if problem:
                add("error", "kind", link.id, problem)
        if record.kind == "requirement":
            feature = record.fields.get("feature")
            if feature is not None and str(feature) not in index:
                add("error", "feature", record.id, f"feature {feature} does not exist")
            examples = [e.id for e in record.examples]
            if len(examples) != len(set(examples)):
                add("error", "example", record.id, "duplicate example ids")
        if record.kind == "feature":
            for sr in record.fields.get("requirements") or []:
                if str(sr) not in index:
                    add("error", "feature", record.id, f"requirement {sr} does not exist")

    statuses = core.status()
    for status in statuses.values():
        for state in status.links:
            link = state.link
            target = link.target.record or link.target.test or link.target.path or "?"
            if state.state == "dangling":
                add("error", "dangling", link.id, f"{link.kind} target {target} does not exist")
            elif state.state == "stale":
                add("warning", "stale", link.id,
                    f"{link.kind} {target}: {state.moved} moved since pinned (plumb repin "
                    f"{link.id} once reviewed)")
            elif state.state == "unpinned":
                add("warning", "unpinned", link.id, f"{link.kind} {target} has no pin "
                    f"(plumb repin {link.id})")
        record = index[status.id]
        if status.confirmation == "unconfirmed-edit":
            add("warning", "unconfirmed-edit", status.id,
                "edited since its approval; awaits the owner's confirmation")
        if record.kind == "requirement":
            if status.confirmation == "confirmed" and status.uncovered_examples:
                add("warning", "uncovered", status.id, "confirmed examples without a "
                    "verified_by test: " + ", ".join(status.uncovered_examples))
            derives = [s for s in status.links if s.link.kind == "derives_from"
                       and s.state != "dangling"]
            if not derives:
                add("warning", "no-intent", status.id, "no derives_from link to an INT")
        if record.kind == "decision" and record.fields.get("matters") is False:
            for state in status.links:
                decided = state.link.target.record
                if state.link.kind == "decides" and decided in statuses and \
                        statuses[decided].confirmation == "confirmed":
                    add("warning", "dec-matters", status.id,
                        f"matters: false but decides confirmed {decided}; treated as mattering")
    proposed = sorted(s.id for s in statuses.values() if s.confirmation == "proposed")
    if proposed:
        shown = ", ".join(proposed[:8]) + (f", +{len(proposed) - 8} more" if len(proposed) > 8
                                           else "")
        add("warning", "proposed", f"{len(proposed)} records",
            f"proposed, awaiting the owner's confirmation: {shown}")

    # logs and approvals
    for stream in ("events", "evidence"):
        for problem in log.verify_chain(core.paths, stream):
            add("error", "log", f"{stream}.jsonl", problem)
    for entry, problem in checked_entries(core.events(), core.config.approve.affirmations):
        if problem:
            ids = ", ".join(str(r.get("id")) for r in entry.payload.get("records") or []
                            if isinstance(r, Mapping))
            add("error", "approval", ids or entry.digest[:19],
                f"{problem} (entry {entry.digest[:19]}); it confirms nothing")
    return findings


def report(core: Core, as_json: bool) -> tuple[int, list[Finding]]:
    """Print the findings; returns (exit code, findings)."""
    findings = validate(core)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    if as_json:
        import json

        print(json.dumps({"errors": [asdict(f) for f in errors],
                          "warnings": [asdict(f) for f in warnings]}, indent=2))
    else:
        for finding in errors + warnings:
            print(finding.line())
        print(f"plumb validate: {len(errors)} errors, {len(warnings)} warnings")
    return (1 if errors else 0), findings
