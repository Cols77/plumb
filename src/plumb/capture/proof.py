"""A requirement's proof (SR-127, DEC-037): how the owner will see it working, and the evidence
once it has run.

``proof`` is ``{plan, kind}``: the plan says, matched to what changed, how the owner will see
the change working (a UI change: a live session capture; a hook: the hook firing and its
output; a CLI change: the command and its output); ``kind`` is one of ``KINDS``. ``evidence``
is ``{at, summary, where, passed}``: when it ran, what it showed, the path or link of the
captured output, and whether it showed the change working.

Both are the agent's notes, never the owner's word: they stay out of the record hash
(``model.UNHASHED``), so recording them neither confirms nor unconfirms anything, and a
missing proof is named (``plumb show``, ``plumb merge-check``), never a hold.

``plumb proof SR-### [--plan TEXT] [--kind KIND]``
``plumb proof SR-### --evidence PATH_OR_LINK --summary TEXT (--passed | --failed)``
``plumb proof SR-###`` alone prints the proof.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from plumb.capture.records import CaptureError

if TYPE_CHECKING:
    from plumb.api import Core
    from plumb.contracts import Record

KINDS = ("live-session", "hook", "command", "other")
NOT_SHOWN = "not shown working yet"


def _flat(value: Any) -> str:
    return " ".join(str(value or "").split())


def proof_entry(raw: Any, name: str = "proof") -> dict[str, str]:
    """The checked ``{plan, kind}`` of a capture document's or a command's proof."""
    if not isinstance(raw, Mapping):
        raise CaptureError(f"{name} must be a mapping with plan and kind")
    plan = _flat(raw.get("plan"))
    kind = _flat(raw.get("kind")) or "other"
    if not plan:
        raise CaptureError(f"{name} needs a plan: how the owner will see it working")
    if kind not in KINDS:
        raise CaptureError(f"{name}.kind is one of {', '.join(KINDS)}")
    return {"plan": plan, "kind": kind}


def proof_of(record: Record) -> Mapping[str, Any] | None:
    raw = record.fields.get("proof")
    return raw if isinstance(raw, Mapping) else None


def evidence_of(record: Record) -> Mapping[str, Any] | None:
    raw = record.fields.get("evidence")
    return raw if isinstance(raw, Mapping) else None


def shown_working(record: Record) -> bool:
    """Whether the evidence recorded for ``record`` showed it working."""
    evidence = evidence_of(record)
    return evidence is not None and evidence.get("passed") is True


# SR-127 EX-1: code that changes what Claude Code draws (plumb's panel: the mod's modules). A
# requirement implemented there is shown working by a live session capture of the drawing.
DRAWN_UNDER = "plugin/hooks/"
DRAWN_SUFFIXES = (".tsx", ".ts")
DRAWN_NOT = ("guard.gen.ts",)     # the mod's guard table: no drawing


def draws(path: str) -> bool:
    """Whether the repository path ``path`` is code that changes what Claude Code draws."""
    path = path.replace("\\", "/")
    return (path.startswith(DRAWN_UNDER) and path.endswith(DRAWN_SUFFIXES)
            and not path.endswith(DRAWN_NOT))


def kind_hint(record: Record) -> str | None:
    """SR-127 EX-1: the line naming a requirement implemented by code that changes what Claude
    Code draws whose proof is not a live session capture (never a hold), or None."""
    if record.kind != "requirement":
        return None
    drawn = [link.target.path for link in record.links
             if link.kind == "implemented_by" and link.target.path and draws(link.target.path)]
    proof = proof_of(record)
    if not drawn or (proof is not None and proof.get("kind") == "live-session"):
        return None
    return (f"{record.id} changes what Claude Code draws ({drawn[0]}): its proof is a live "
            f"session capture showing the drawing (plumb proof {record.id} --plan ... "
            "--kind live-session)")


def proof_lines(record: Record) -> list[str]:
    """``plumb show``'s proof lines of a requirement (none for other kinds)."""
    if record.kind != "requirement":
        return []
    rid = record.id
    proof = proof_of(record)
    lines = [f"{rid} proof ({_flat(proof.get('kind')) or 'other'}): {_flat(proof.get('plan'))}"
             if proof else f"{rid} proof: none planned"]
    evidence = evidence_of(record)
    if evidence is None:
        lines.append(f"{rid} evidence: {NOT_SHOWN}")
    else:
        verdict = "shown working" if evidence.get("passed") is True else "did NOT show it working"
        lines.append(f"{rid} evidence ({verdict}, {_flat(evidence.get('at'))}): "
                     f"{_flat(evidence.get('summary'))}")
        lines.append(f"{rid} evidence at: {_flat(evidence.get('where'))}")
    return lines


def not_shown(core: Core, ids: Sequence[str]) -> list[dict[str, Any]]:
    """The requirements of ``ids`` not shown working: ``{id, title, why}``, ``why`` one of
    ``no proof`` (none planned), ``not run`` (planned, no evidence), ``failed``."""
    index = core.index()
    rows: list[dict[str, Any]] = []
    for record_id in ids:
        record = index.get(record_id)
        if record is None or record.kind != "requirement" or shown_working(record):
            continue
        why = ("failed" if evidence_of(record) is not None
               else "not run" if proof_of(record) is not None else "no proof")
        rows.append({"id": record_id, "title": record.title, "why": why})
    return rows


def _where(core: Core, where: str) -> str:
    """A link as given; a path as a repository-relative path that exists."""
    where = where.strip()
    if "://" in where:
        return where
    path = Path(where)
    if not path.is_absolute():
        path = Path(core.root) / path
    if not path.exists():
        raise CaptureError(f"--evidence {where}: no such file; give the captured output's "
                           "path or a link")
    try:
        return path.resolve().relative_to(Path(core.root).resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _requirement(core: Core, sr_id: str) -> Record:
    record = core.index().get(sr_id)
    if record is None or record.kind != "requirement":
        raise CaptureError(f"no requirement {sr_id}")
    return record


def set_plan(core: Core, sr_id: str, plan: str | None, kind: str | None) -> tuple[Record, bool]:
    """Record the proof plan; returns the record and whether earlier evidence was dropped
    (evidence of another plan does not show this one)."""
    from plumb.capture.records import record_fields

    record = _requirement(core, sr_id)
    old = dict(proof_of(record) or {})
    entry = proof_entry({"plan": plan if plan is not None else old.get("plan"),
                         "kind": kind or old.get("kind")})
    fields = record_fields(record)
    fields["proof"] = entry
    dropped = bool(old) and old.get("plan") != entry["plan"] and "evidence" in fields
    if dropped:
        fields.pop("evidence")
    core.write_record("requirement", fields, record.body, record_id=record.id)
    return core.index()[record.id], dropped


def set_evidence(core: Core, sr_id: str, where: str, summary: str, passed: bool,
                 at: str | None = None) -> Record:
    from plumb.capture.records import record_fields

    record = _requirement(core, sr_id)
    summary = _flat(summary)
    if not summary:
        raise CaptureError("--summary says what the evidence shows")
    fields = record_fields(record)
    fields["evidence"] = {
        "at": at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": summary, "where": _where(core, where), "passed": bool(passed)}
    core.write_record("requirement", fields, record.body, record_id=record.id)
    return core.index()[record.id]


# --------------------------------------------------------------------------- command


def run(command: str, argv: list[str]) -> int:
    from plumb.api import open_core
    from plumb.cliutil import EXIT_USAGE, add_common, emit, resolve_root

    parser = argparse.ArgumentParser(
        prog=f"plumb {command}",
        description="Record how the owner will see a requirement working (--plan, --kind) "
                    "and, once run, the evidence (--evidence, --summary, --passed or "
                    "--failed). Never confirms anything; a missing proof is named, never a "
                    "hold. With the ID alone, print the proof.")
    parser.add_argument("sr", metavar="SR-###")
    parser.add_argument("--plan", default=None,
                        help="how the owner will see it working, matched to what changed")
    parser.add_argument("--kind", choices=KINDS, default=None)
    parser.add_argument("--evidence", default=None, metavar="PATH_OR_LINK",
                        help="where the captured output is")
    parser.add_argument("--summary", default=None, help="what the evidence shows")
    outcome = parser.add_mutually_exclusive_group()
    outcome.add_argument("--passed", action="store_true", default=None)
    outcome.add_argument("--failed", action="store_false", dest="passed", default=None)
    add_common(parser)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    core = open_core(resolve_root(args.root))
    lines: list[str] = []
    try:
        record = _requirement(core, args.sr)
        if args.plan is not None or args.kind is not None:
            record, dropped = set_plan(core, args.sr, args.plan, args.kind)
            lines.append(f"plumb: {record.id} proof recorded")
            hint = kind_hint(record)
            if hint:
                lines.append(f"plumb: {hint}")
            if dropped:
                lines.append(f"plumb: {record.id}: the plan changed; its earlier evidence was "
                             "dropped (it showed another plan)")
        if args.evidence is not None:
            if args.summary is None or args.passed is None:
                raise CaptureError("--evidence needs --summary and --passed or --failed")
            record = set_evidence(core, args.sr, args.evidence, args.summary, args.passed)
            lines.append(f"plumb: {record.id} evidence recorded ("
                         + ("shown working" if args.passed else "did NOT show it working")
                         + ")")
            if proof_of(record) is None:
                lines.append(f"plumb: {record.id} has no proof plan: plumb proof {record.id} "
                             "--plan ... --kind ...")
        elif args.summary is not None or args.passed is not None:
            raise CaptureError("--summary, --passed and --failed go with --evidence")
    except CaptureError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_USAGE
    lines += proof_lines(record)
    if args.as_json:
        emit({"id": record.id, "proof": proof_of(record), "evidence": evidence_of(record),
              "shown_working": shown_working(record), "lines": lines}, True)
    else:
        emit(lines, False)
    return 0
