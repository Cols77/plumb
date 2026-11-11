"""``iaso validate`` (spec 5.10): relation validation, log chains and approval re-checks.

Errors: unloadable or duplicate records, malformed IDs, link kinds not allowed between their
ends, dangling links and references, broken log chains, approvals failing their re-check.
Warnings: a judge approval failing its re-check (inert, SR-251), stale and unpinned links,
unconfirmed edits, confirmed examples without a test, an SR without a derives_from link to an
INT, a matters-false DEC deciding a confirmed record, and one summary line for proposed
records awaiting the owner.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from iaso import log
from iaso.confirm import checked
from iaso.links import kind_problem

if TYPE_CHECKING:
    from iaso.api import Core


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warning"
    code: str
    subject: str
    message: str

    def line(self) -> str:
        return f"{self.severity}: [{self.code}] {self.subject}: {self.message}"


def _text_merged(core: Core, rel: str) -> str | None:
    """sp6 7.6: a record file holding both versions of a text merge, in the owner's terms."""
    try:
        text = (core.root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if not any(line.startswith("<<<<<<< ") for line in lines) or \
            not any(line.startswith(">>>>>>> ") for line in lines):
        return None
    from iaso.mergedriver.merge import _guess_id
    from iaso.present.owner_text import UNPARSABLE

    record, title = _guess_id(text)
    if record == "this record":
        record = rel.rsplit("/", 1)[-1].removesuffix(".md")
    return UNPARSABLE.format(record=record, title=title)


def proof_problems(fields: Mapping[str, object]) -> list[str]:
    """What is malformed in a requirement's optional ``proof`` ({plan, kind}) and
    ``evidence`` ({at, summary, where, passed}) (SR-127); a record without them is valid."""
    from iaso.capture.proof import KINDS

    problems: list[str] = []
    proof = fields.get("proof")
    if proof is not None:
        if not isinstance(proof, Mapping):
            problems.append("proof must be a mapping with plan and kind")
        else:
            if not str(proof.get("plan") or "").strip():
                problems.append("proof has no plan")
            if proof.get("kind") not in KINDS:
                problems.append(f"proof kind {proof.get('kind')!r} is not one of "
                                + ", ".join(KINDS))
    evidence = fields.get("evidence")
    if evidence is not None:
        if not isinstance(evidence, Mapping):
            problems.append("evidence must be a mapping with at, summary, where and passed")
        else:
            missing = [k for k in ("at", "summary", "where")
                       if not str(evidence.get(k) or "").strip()]
            if missing:
                problems.append("evidence has no " + ", ".join(missing))
            if not isinstance(evidence.get("passed"), bool):
                problems.append("evidence passed must be true or false")
    return problems


def validate(core: Core) -> list[Finding]:
    findings: list[Finding] = []

    rec = core.paths.iaso.name  # the records folder in use

    def add(severity: str, code: str, subject: str, message: str) -> None:
        findings.append(Finding(severity, code, subject, message))

    for problem in core.store.problems():
        code = "duplicate" if problem.startswith("duplicate id") else "load"
        subject = problem.split(":", 1)[0]
        add("error", code, subject, _text_merged(core, subject) or problem)
    index = core.index()

    # relations
    for record in index.values():
        for link in record.links:
            problem = kind_problem(link, record)
            if problem:
                add("error", "kind", link.id, problem)
            # shortcut: IDs are allocated in order; use the record's first commit date if renumbering breaks that
            elif link.kind == "supersedes" and link.target.record:
                old, new = link.target.record, record.id
                if old.split("-")[0] == new.split("-")[0] and int(old.split("-")[1]) > int(new.split("-")[1]):
                    add("warning", "supersedes", link.id, f"supersedes a newer record {old}: "
                        "the newer one is usually the owner's current intent")
                from iaso.links import live_examples  # SR-164: a retired record's tests

                for ex, test in live_examples(core, old, record.id):
                    add("warning", "retired-example", link.id,  # DEC-065: retired means gone
                        f"{old}/{ex} is retired by {record.id} but still verified by {test}: "
                        f"retire the test too: unlink it, and drop it when it covers nothing else")
        if record.kind == "requirement":
            feature = record.fields.get("feature")
            if feature is not None and str(feature) not in index:
                add("error", "feature", record.id, f"feature {feature} does not exist")
            examples = [e.id for e in record.examples]
            if len(examples) != len(set(examples)):
                add("error", "example", record.id, "duplicate example ids")
            # SR-127, DEC-037: a malformed proof is named, never an error (it never holds)
            for problem in proof_problems(record.fields):
                add("warning", "proof", record.id, problem)
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
                    f"{link.kind} {target}: {state.moved} moved since pinned (iaso repin "
                    f"{link.id} once reviewed)")
            elif state.state == "unpinned":
                add("warning", "unpinned", link.id, f"{link.kind} {target} has no pin "
                    f"(iaso repin {link.id})")
        record = index[status.id]
        if status.confirmation == "unconfirmed-edit":
            add("warning", "unconfirmed-edit", status.id,
                ("acceptance test changed since its approval: "
                 + ", ".join(status.changed_tests)) if status.changed_tests else
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

    # SP8: the understanding layer's own checks (stubs report none)
    try:
        from iaso.understand import gate, premise

        for problem in (*premise.problems(core), *gate.problems(core)):
            add("error", "understand", "understand", problem)
    except ImportError:
        pass

    # auto-approval (sp2 C4): config.yaml is a mirror; only the owner's config event counts
    try:
        from iaso.capture.autoapprove import auto_approve_state

        state = auto_approve_state(core)
    except Exception:  # noqa: BLE001 - an optional lane never fails validate
        state = None
    if state is not None and state.mirror_mismatch:
        add("warning", "auto-approve-mirror", f"{rec}/config.yaml",
            "auto_approve says enabled, but no owner config event turned it on: it is off "
            "(iaso config auto-approve on, in the owner's own terminal)")

    # logs and approvals
    for stream in ("events", "evidence"):
        for problem in log.verify_chain(core.paths, stream):
            add("error", "log", f"{rec}/log ({stream})", problem)
    legacy = log.legacy_count(core.paths)
    if legacy:  # SP6 6.5: a warning, never a hold
        from iaso.present.owner_text import LEGACY_LOG

        add("warning", "legacy-log", f"{rec}/log", LEGACY_LOG.format(n=legacy))
    for entry, problem in checked(core):
        if problem:
            named = [str(r.get("id")) for r in entry.payload.get("records") or []
                     if isinstance(r, Mapping)]
            if named and not any(i in index for i in named):
                continue        # DEC-145: every record it names left the tree; history only
            ids = ", ".join(named)
            if entry.kind == "approval" and entry.payload.get("by") in ("auto-jev",
                                                                      "auto-model"):
                add("warning", "inert-approval", ids or entry.digest[:19],  # SR-251
                    f"{problem} (entry {entry.digest[:19]}); it approves nothing")
                continue
            add("error", "approval", ids or entry.digest[:19],
                f"{problem} (entry {entry.digest[:19]}); it confirms nothing")
    # renumber entries (sp6 5.4): the approvals they carry exist and pin the incoming words
    if any(e.kind == "renumber" for e in core.events()):
        from iaso import ids

        for problem in ids.renumber_problems(core):
            subject, _, message = problem.partition(": ")
            add("error", "renumber", subject, message)
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
        print(f"iaso validate: {len(errors)} errors, {len(warnings)} warnings")
    return (1 if errors else 0), findings
