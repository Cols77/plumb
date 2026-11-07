"""A requirement's proof (SR-127, DEC-037): how the owner will see it working, and the evidence
once it has run.

``proof`` is ``{plan, kind}``: the plan says, matched to what changed, how the owner will see
the change working (a UI change: a live session capture; a hook: the hook firing and its
output; a CLI change: the command and its output); ``kind`` is one of ``KINDS``. ``evidence``
is ``{at, summary, where, passed}``: when it ran, what it showed, the path or link of the
captured output, and whether it showed the change working.

Both are the agent's notes, never the owner's word: they stay out of the record hash
(``model.UNHASHED``), so recording them neither confirms nor unconfirms anything. A missing
proof is named (``plumb show``, ``plumb merge-check``); it holds only a merge into the default
branch that delivers the requirement (an incoming commit's SR trailer), until the agent has
shown it working and the owner confirmed it (SR-260, DEC-256, DEC-257).

The owner's confirmation (DEC-257): ``plumb proof SR-### --ask`` (the agent, once the evidence
passed) files a pending question in ``.plumb/session/<session>/proof_questions.json`` and
prints the question-tool JSON; the question-answer hook tags the owner's answer to it with
``proof: {record, hash, evidence_at}`` (``owner_confirmed`` reads it). The agent writes that
log entry only through the hook.

A proof that can only be shown once its branch is in the default branch (a live session of
the plugin reloaded from main) is agreed as post-merge when it is chosen (SR-341):
``post_merge: true`` in the proof. The merge check does not hold on it; the landing names it
and the next turn tells the agent to show it and ask the owner.

``plumb proof SR-### [--plan TEXT] [--kind KIND] [--post-merge | --no-post-merge]``
``plumb proof SR-### --evidence PATH_OR_LINK --summary TEXT (--passed | --failed)``
``plumb proof SR-### --ask`` puts "Did you see it working?" to the owner.
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
QUESTIONS_FILE = "proof_questions.json"
YES = "Yes, I saw it working"
NO = "No, not yet"


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
    entry: dict[str, Any] = {"plan": plan, "kind": kind}
    if raw.get("post_merge") is True:  # SR-341: shown only once the branch has landed
        entry["post_merge"] = True
    return entry


def post_merge(record: Record) -> bool:
    """SR-341: whether ``record``'s proof was agreed as shown only after its branch lands."""
    proof = proof_of(record)
    return proof is not None and proof.get("post_merge") is True


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
    lines = [f"{rid} proof ({_flat(proof.get('kind')) or 'other'}"
             f"{', post-merge' if proof.get('post_merge') is True else ''}): "
             f"{_flat(proof.get('plan'))}"
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


# --------------------------------------------------------------------------- the owner's yes


def questions_path(root: Any, session: str) -> Path:
    """The session's pending proof questions (DEC-257); ``--ask`` adds, the hook removes."""
    from plumb.understand import files

    return files.session_dir(Path(root), session) / QUESTIONS_FILE


def pending(root: Any, session: str) -> list[dict[str, Any]]:
    from plumb.understand import files

    raw = files.read_json(questions_path(root, session))
    return [dict(q) for q in raw if isinstance(q, Mapping)] if isinstance(raw, list) else []


def ask(core: Core, sr_id: str, session: str) -> dict[str, Any]:
    """DEC-257: file the owner's "Did you see it working?" for ``sr_id`` as a pending proof
    question ``{key, record, hash, evidence_at}`` and return the question-tool JSON; refused
    (``CaptureError``) unless its evidence passed."""
    from plumb.understand import files
    from plumb.understand.judge import question_key

    record = _requirement(core, sr_id)
    question = question_of(record)
    if question is None:
        raise CaptureError(f"{sr_id} is not shown working: record passing evidence first "
                           f"(plumb proof {sr_id} --evidence ... --summary ... --passed)")
    entry = {"key": question_key(question), "record": record.id, "hash": record.hash,
             "evidence_at": _flat(evidence_of(record).get("at"))}
    kept = [q for q in pending(core.root, session) if q.get("record") != record.id]
    files.write_json_atomic(questions_path(core.root, session), [*kept, entry])
    return {"questions": [{
        "question": question, "header": "Proof", "multiSelect": False,
        "options": [{"label": YES, "description": "you watched the proof show it working; a "
                     "merge into the default branch that delivers it no longer waits on it"},
                    {"label": NO, "description": "a merge into the default branch that "
                     "delivers it keeps waiting until you have seen it working"}]}]}


def question_of(record: Any) -> str | None:
    """The owner's question for ``record``'s current passing evidence (its title, what the
    evidence showed and where); None unless it is shown working."""
    evidence = evidence_of(record)
    if evidence is None or not shown_working(record):
        return None
    where = _flat(evidence.get("where"))
    return f"Did you see {record.title} working?\n\n{_flat(evidence.get('summary'))}" + (
        f" ({where})" if where else "")


def confirmation(core: Core, record_id: Any, question: str,
                 labels: Sequence[Any]) -> dict[str, Any] | None:
    """The ``proof`` the question-answer hook puts on an answer (DEC-257): ``{record, hash,
    evidence_at}`` only when the question asked is ``question_of`` that record now and YES was
    among the options shown, so a pending entry written by hand cannot point the owner's yes
    at another record, another question or evidence that did not pass."""
    record = core.index().get(str(record_id))
    if record is None or record.kind != "requirement" or YES not in labels \
            or question_of(record) != question:
        return None
    return {"record": record.id, "hash": record.hash,
            "evidence_at": _flat(evidence_of(record).get("at"))}


def owner_confirmed(core: Core, record_id: str) -> bool:
    """DEC-257, DEC-116: a ``proof-confirmed`` entry (committed: the outcome only) or a
    question-answer entry (local: the owner's words), both written by the question-answer hook,
    says the owner saw ``record_id`` working at its current hash and evidence (``record``,
    ``hash``, ``evidence_at``, answer ``YES``). A yes given under the old id of a
    renumber (``ids.approval_aliases``) counts while the words are still the ones it saw."""
    from plumb.ids import approval_aliases

    record = core.index().get(record_id)
    evidence = evidence_of(record) if record is not None else None
    if record is None or evidence is None:
        return False
    at = _flat(evidence.get("at"))
    seen = {(record_id, record.hash)}
    carried = approval_aliases(core).get((record_id, record.hash))
    if carried:
        seen.add(carried)
    for entry in core.events():
        # DEC-116: the committed ``proof-confirmed`` outcome; a ``question-answer`` carrying the
        # tag is the same yes on the machine that heard it
        proof = entry.payload.get("proof") if entry.kind == "question-answer" else (
            entry.payload if entry.kind == "proof-confirmed" else None)
        if isinstance(proof, Mapping) and (proof.get("record"), proof.get("hash")) in seen \
                and proof.get("evidence_at") == at \
                and entry.payload.get("answer") == YES:
            return True
    return False


def unconfirmed_proofs(core: Core, ids: Sequence[str]) -> list[dict[str, Any]]:
    """SR-260 (d), DEC-256: the requirements of ``ids`` (those a merge into the default
    branch delivers) whose proof is not shown working or not confirmed by the owner:
    ``{id, title, why}``, ``why`` ``not shown working`` or ``not confirmed by you``. A
    post-merge proof (SR-341) is none of them: it is shown after the landing."""
    index = core.index()
    rows: list[dict[str, Any]] = []
    for record_id in dict.fromkeys(ids):
        record = index.get(record_id)
        if record is None or record.kind != "requirement" or post_merge(record):
            continue
        if not shown_working(record):
            rows.append({"id": record_id, "title": record.title, "why": "not shown working"})
        elif not owner_confirmed(core, record_id):
            rows.append({"id": record_id, "title": record.title,
                         "why": "not confirmed by you"})
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


def set_plan(core: Core, sr_id: str, plan: str | None, kind: str | None,
             post: bool | None = None) -> tuple[Record, bool]:
    """Record the proof plan; returns the record and whether earlier evidence was dropped
    (evidence of another plan does not show this one)."""
    from plumb.capture.records import record_fields

    record = _requirement(core, sr_id)
    old = dict(proof_of(record) or {})
    entry = proof_entry({"plan": plan if plan is not None else old.get("plan"),
                         "kind": kind or old.get("kind"),
                         "post_merge": old.get("post_merge") if post is None else post})
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
    # report-d7f2612b: an open intent loop building this requirement redraws its band task
    # from the proofs now shown; the evidence stands even when no loop file could be written
    from contextlib import suppress

    from plumb.understand import cmd_intent

    with suppress(OSError):
        cmd_intent.on_evidence(core, record.id)
    return core.index()[record.id]


# --------------------------------------------------------------------------- command


def run(command: str, argv: list[str]) -> int:
    from plumb.api import open_core
    from plumb.cliutil import EXIT_USAGE, add_common, emit, resolve_root

    parser = argparse.ArgumentParser(
        prog=f"plumb {command}",
        description="Record how the owner will see a requirement working (--plan, --kind) "
                    "and, once run, the evidence (--evidence, --summary, --passed or "
                    "--failed); --ask puts 'Did you see it working?' to the owner once the "
                    "evidence passed. Never confirms a record; a proof holds only a merge "
                    "into the default branch that delivers it. With the ID alone, print the "
                    "proof.")
    parser.add_argument("sr", metavar="SR-###")
    parser.add_argument("--plan", default=None,
                        help="how the owner will see it working, matched to what changed")
    parser.add_argument("--kind", choices=KINDS, default=None)
    parser.add_argument("--post-merge", action=argparse.BooleanOptionalAction, default=None,
                        help="SR-341: the proof can only be shown once the branch has landed "
                             "(agreed when the proof is chosen); the merge check does not "
                             "hold on it and the next turn after the landing asks for it")
    parser.add_argument("--evidence", default=None, metavar="PATH_OR_LINK",
                        help="where the captured output is")
    parser.add_argument("--summary", default=None, help="what the evidence shows")
    outcome = parser.add_mutually_exclusive_group()
    outcome.add_argument("--passed", action="store_true", default=None)
    outcome.add_argument("--failed", action="store_false", dest="passed", default=None)
    parser.add_argument("--ask", action="store_true",
                        help="print the question-tool JSON asking the owner whether they saw "
                             "it working (refused unless the evidence passed)")
    add_common(parser)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    core = open_core(resolve_root(args.root))
    lines: list[str] = []
    try:
        record = _requirement(core, args.sr)
        if args.plan is not None or args.kind is not None or args.post_merge is not None:
            record, dropped = set_plan(core, args.sr, args.plan, args.kind, args.post_merge)
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
        if args.ask:
            from plumb.stale import current_session

            emit(ask(core, args.sr, current_session(core.root)), True)
            return 0
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
