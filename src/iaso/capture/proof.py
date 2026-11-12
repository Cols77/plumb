"""A requirement's proof (SR-127, DEC-037): how the owner will see it working, and the evidence
once it has run.

``proof`` is ``{plan, kind}``: the plan says, matched to what changed, how the owner will see
the change working (a UI change: a live session capture; a hook: the hook firing and its
output; a CLI change: the command and its output); ``kind`` is one of ``KINDS``. ``evidence``
is ``{at, summary, where, passed}``: when it ran, what it showed, the path or link of the
captured output, and whether it showed the change working.

Both are the agent's notes, never the owner's word: they stay out of the record hash
(``model.UNHASHED``), so recording them neither confirms nor unconfirms anything. A missing
proof is named (``iaso show``, ``iaso merge-check``); it holds only a merge into the default
branch that delivers the requirement (an incoming commit's SR trailer), until the agent has
shown it working and the owner confirmed it (SR-260, DEC-256, DEC-257).

The owner's confirmation (DEC-257): ``iaso proof SR-### --ask`` (the agent, once the evidence
passed) files a pending question in ``.iaso/session/<session>/proof_questions.json`` and
prints the question-tool JSON; the question-answer hook tags the owner's answer to it with
``proof: {record, hash, evidence_at}`` (``owner_confirmed`` reads it). The agent writes that
log entry only through the hook.

A proof that can only be shown once its branch is in the default branch (a live session of
the plugin reloaded from main) is agreed as post-merge when it is chosen (SR-341):
``post_merge: true`` in the proof. The merge check does not hold on it; the landing names it
and the next turn tells the agent to show it and ask the owner.

``iaso proof SR-### [--plan TEXT] [--kind KIND] [--post-merge | --no-post-merge]``
``iaso proof SR-### --evidence PATH_OR_LINK --summary TEXT (--passed | --failed)``
``iaso proof SR-### --ask`` puts "Did you see it working?" to the owner.
``iaso proof SR-###`` alone prints the proof.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from iaso.capture.records import CaptureError

if TYPE_CHECKING:
    from iaso.api import Core
    from iaso.contracts import Record

KINDS = ("live-session", "hook", "command", "other")
NOT_SHOWN = "not shown working yet"
QUESTIONS_FILE = "proof_questions.json"
VERIFIED = "proof-verified"
NOT_VERIFIED = "proof-not-verified"
OVERRULED = "proof-overruled"
YES = "Yes, I saw it working"
NO = "No, not yet"
EVALUATOR_OPTION = "An independent evaluator checks it for me"   # the loop's proof question


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
    if raw.get("evaluator") is True:    # DEC-469: the owner's pick lives on this proof
        entry["evaluator"] = True
    return entry


def evaluator_picked(record: Record) -> bool:
    """SR-396: whether the owner picked the independent evaluator for ``record``'s proof."""
    proof = proof_of(record)
    return proof is not None and proof.get("evaluator") is True


def require_pick(core: Core) -> None:
    """SR-396 EX-3: a new evaluator pick is refused unless the owner, in this session and since
    its open loop opened, answered a question offering the evaluator. A loop opened in main
    keeps its answers in main's log, so that log is read too."""
    from iaso.api import open_core
    from iaso.stale import current_session
    from iaso.understand import cmd_intent

    root = Path(core.root)
    session = current_session(root)
    held = [d for _, d in cmd_intent.loops(root, session)
            if not d.get("handed_to") and not cmd_intent._passed(d, "build")]
    since = str(held[-1].get("opened_at") or "") if held else ""
    for n, checkout in enumerate(cmd_intent._checkouts(root)):
        for e in (core if n == 0 else open_core(checkout)).events():
            if e.kind != "question-answer" or e.payload.get("session") != session \
                    or e.payload.get("via") != "question-tool" or e.at < since:
                continue
            labels = [o.get("label") for o in e.payload.get("options") or []
                      if isinstance(o, Mapping)]
            # shortcut: a free-text answer counts as a pick unless it is another option's
            # label; judge the answer if a free-text "no" is ever taken as a pick
            if EVALUATOR_OPTION in labels and e.payload.get("answer") not in (
                    set(labels) - {EVALUATOR_OPTION}):
                return
    raise CaptureError("the owner did not pick the evaluator in this loop: offer it at the "
                       f'proof question (first option "{EVALUATOR_OPTION}") and set it only '
                       "on their answer; a pick of an earlier loop does not carry over")


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


# SR-127 EX-1: code that changes what Claude Code draws (iaso's panel: the mod's modules). A
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
            f"session capture showing the drawing (iaso proof {record.id} --plan ... "
            "--kind live-session)")


def proof_lines(record: Record) -> list[str]:
    """``iaso show``'s proof lines of a requirement (none for other kinds)."""
    if record.kind != "requirement":
        return []
    rid = record.id
    proof = proof_of(record)
    lines = [f"{rid} proof ({_flat(proof.get('kind')) or 'other'}"
             f"{', post-merge' if proof.get('post_merge') is True else ''}"
             f"{', evaluator' if proof.get('evaluator') is True else ''}): "
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
    from iaso.understand import files

    return files.session_dir(Path(root), session) / QUESTIONS_FILE


def pending(root: Any, session: str) -> list[dict[str, Any]]:
    from iaso.understand import files

    raw = files.read_json(questions_path(root, session))
    return [dict(q) for q in raw if isinstance(q, Mapping)] if isinstance(raw, list) else []


def ask(core: Core, sr_id: str, session: str) -> dict[str, Any]:
    """DEC-257: file the owner's "Did you see it working?" for ``sr_id`` as a pending proof
    question ``{key, record, hash, evidence_at}`` and return the question-tool JSON; refused
    (``CaptureError``) unless its evidence passed."""
    from iaso.understand import files
    from iaso.understand.judge import question_key

    record = _requirement(core, sr_id)
    if evaluator_confirmed(core, sr_id):   # SR-397: the owner is told, not asked
        raise CaptureError(f"{sr_id} is verified by the evaluator the owner picked: tell the "
                           "owner the verdict and where the evidence is; ask nothing (they "
                           f"overrule it by saying so: iaso proof {sr_id} --overrule)")
    question = question_of(record)
    if question is None:
        raise CaptureError(f"{sr_id} is not shown working: record passing evidence first "
                           f"(iaso proof {sr_id} --evidence ... --summary ... --passed)")
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
    from iaso.ids import approval_aliases

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


def unverified(core: Core, ids: Sequence[str]) -> list[dict[str, Any]]:
    """SR-397 EX-5: the requirements of ``ids`` whose proof has the evaluator picked, is shown
    working and is not post-merge, yet no evaluator run confirmed it (nor the owner)."""
    index = core.index()
    rows: list[dict[str, Any]] = []
    for record_id in ids:
        record = index.get(record_id)
        if record is None or record.kind != "requirement" or not evaluator_picked(record) \
                or post_merge(record) or not shown_working(record) or confirmed(core, record_id):
            continue
        rows.append({"id": record_id, "title": record.title,
                     "why": "not verified by the evaluator the owner picked"})
    return rows


def evaluator_confirmed(core: Core, record_id: str) -> bool:
    """SR-397: the last ``proof-verified`` / ``proof-overruled`` entry for ``record_id`` at its
    current hash (or the one a renumber carries) and current evidence is ``proof-verified``.
    Hand-recorded evidence changes ``at`` and a reword the hash: both end it."""
    from iaso.ids import approval_aliases

    record = core.index().get(record_id)
    evidence = evidence_of(record) if record is not None else None
    if record is None or evidence is None:
        return False
    at = _flat(evidence.get("at"))
    seen = {(record_id, record.hash)}
    carried = approval_aliases(core).get((record_id, record.hash))
    if carried:
        seen.add(carried)
    last = None
    for entry in core.events():
        p = entry.payload
        if entry.kind in (VERIFIED, OVERRULED) and (p.get("record"), p.get("hash")) in seen \
                and p.get("evidence_at") == at:
            last = entry.kind
    return last == VERIFIED


def confirmed(core: Core, record_id: str) -> bool:
    """Confirmed by the owner's yes or by the evaluator's verdict (SR-397)."""
    return owner_confirmed(core, record_id) or evaluator_confirmed(core, record_id)


def record_verdict(core: Core, sr_id: str, verdict: str, summary: str,
                   where: str) -> dict[str, Any]:
    """SR-397, SR-398: the only writer of an evaluator's verdict (the evaluator run calls it).
    ``verified`` records passing evidence and logs ``proof-verified``; ``not verified`` records
    failing evidence and logs ``proof-not-verified`` (``retry_left`` only on the first);
    ``could not check`` writes nothing."""
    if verdict == "could not check":
        return {"verdict": verdict}
    if verdict not in ("verified", "not verified"):
        raise CaptureError(f"unknown verdict {verdict!r}")
    ok = verdict == "verified"
    first = not ok and not _failures_since_verified(core, sr_id)
    record = set_evidence(core, sr_id, where, summary, passed=ok)
    payload = {"record": record.id, "hash": record.hash,
               "evidence_at": _flat(evidence_of(record).get("at"))}
    core.log_append("events", VERIFIED if ok else NOT_VERIFIED,
                    {**payload, "where": where} if ok else payload)
    return {"verdict": verdict} if ok else {"verdict": verdict, "retry_left": first}


def _failures_since_verified(core: Core, sr_id: str) -> int:
    count = 0
    for entry in core.events():
        if entry.payload.get("record") == sr_id:
            if entry.kind == VERIFIED:
                count = 0
            elif entry.kind == NOT_VERIFIED:
                count += 1
    return count


def overrule(core: Core, sr_id: str) -> None:
    """SR-397 EX-4: the owner does not accept the evaluator's verdict; the proof is open again."""
    if not evaluator_confirmed(core, sr_id):
        raise CaptureError(f"{sr_id} has no evaluator verdict to overrule")
    record = core.index()[sr_id]
    core.log_append("events", OVERRULED, {
        "record": sr_id, "hash": record.hash,
        "evidence_at": _flat(evidence_of(record).get("at"))})


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
        elif not confirmed(core, record_id):
            rows.append({"id": record_id, "title": record.title,
                         "why": "not confirmed by you"})
    return rows


def _where(core: Core, where: str) -> str:
    """A link as given; a path as a repository-relative path that exists; a file outside the
    repository by its name only, marked not kept: its absolute path names the machine and,
    in a session scratchpad, the repository folder (which tripped SR-430's old-name check)."""
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
        return f"{path.name} (not kept)"


def _requirement(core: Core, sr_id: str) -> Record:
    record = core.index().get(sr_id)
    if record is None or record.kind != "requirement":
        raise CaptureError(f"no requirement {sr_id}")
    return record


def set_plan(core: Core, sr_id: str, plan: str | None, kind: str | None,
             post: bool | None = None, evaluator: bool | None = None
             ) -> tuple[Record, bool]:
    """Record the proof plan; returns the record and whether earlier evidence was dropped
    (evidence of another plan does not show this one)."""
    from iaso.capture.records import record_fields

    record = _requirement(core, sr_id)
    old = dict(proof_of(record) or {})
    entry = proof_entry({"plan": plan if plan is not None else old.get("plan"),
                         "kind": kind or old.get("kind"),
                         "post_merge": old.get("post_merge") if post is None else post,
                         "evaluator": old.get("evaluator") if evaluator is None else evaluator})
    fields = record_fields(record)
    fields["proof"] = entry
    dropped = bool(old) and old.get("plan") != entry["plan"] and "evidence" in fields
    if dropped:
        fields.pop("evidence")
    core.write_record("requirement", fields, record.body, record_id=record.id)
    return core.index()[record.id], dropped


def set_evidence(core: Core, sr_id: str, where: str, summary: str, passed: bool,
                 at: str | None = None) -> Record:
    from iaso.capture.records import record_fields

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

    from iaso.understand import cmd_intent

    with suppress(OSError):
        cmd_intent.on_evidence(core, record.id)
    return core.index()[record.id]


# --------------------------------------------------------------------------- command


def run(command: str, argv: list[str]) -> int:
    from iaso.api import open_core
    from iaso.cliutil import EXIT_USAGE, add_common, emit, resolve_root

    parser = argparse.ArgumentParser(
        prog=f"iaso {command}",
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
    parser.add_argument("--evaluator", action=argparse.BooleanOptionalAction, default=None,
                        help="the owner picked the independent evaluator for this proof at "
                             "the proof question")
    parser.add_argument("--overrule", action="store_true",
                        help="the owner said they do not accept the evaluator's verdict; the "
                             "proof is open again")
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
        if args.evaluator is False and any(
                e.kind in (VERIFIED, NOT_VERIFIED) and e.payload.get("record") == args.sr
                for e in core.events()):
            # shortcut: clearing a pick is the agent's note, as post-merge is; tie it to the
            # owner's logged answer if a pick is ever found cleared without them
            raise CaptureError(f"the evaluator already gave a verdict on {args.sr}: the pick "
                               f"stays; the owner's yes still confirms it (iaso proof "
                               f"{args.sr} --ask)")
        if args.evaluator and not evaluator_picked(record):
            require_pick(core)
        if args.plan is not None or args.kind is not None or args.post_merge is not None \
                or args.evaluator is not None:
            record, dropped = set_plan(core, args.sr, args.plan, args.kind, args.post_merge,
                                       args.evaluator)
            lines.append(f"iaso: {record.id} proof recorded")
            hint = kind_hint(record)
            if hint:
                lines.append(f"iaso: {hint}")
            if dropped:
                lines.append(f"iaso: {record.id}: the plan changed; its earlier evidence was "
                             "dropped (it showed another plan)")
        if args.evidence is not None:
            if args.summary is None or args.passed is None:
                raise CaptureError("--evidence needs --summary and --passed or --failed")
            record = set_evidence(core, args.sr, args.evidence, args.summary, args.passed)
            lines.append(f"iaso: {record.id} evidence recorded ("
                         + ("shown working" if args.passed else "did NOT show it working")
                         + ")")
            if proof_of(record) is None:
                lines.append(f"iaso: {record.id} has no proof plan: iaso proof {record.id} "
                             "--plan ... --kind ...")
        elif args.summary is not None or args.passed is not None:
            raise CaptureError("--summary, --passed and --failed go with --evidence")
        if args.overrule:
            overrule(core, args.sr)
            lines.append(f"iaso: {args.sr} verdict overruled: the proof is open again")
        if args.ask:
            from iaso.stale import current_session

            emit(ask(core, args.sr, current_session(core.root)), True)
            return 0
    except CaptureError as exc:
        print(f"iaso: {exc}", file=sys.stderr)
        return EXIT_USAGE
    lines += proof_lines(record)
    if args.as_json:
        emit({"id": record.id, "proof": proof_of(record), "evidence": evidence_of(record),
              "shown_working": shown_working(record), "lines": lines}, True)
    else:
        emit(lines, False)
    return 0
