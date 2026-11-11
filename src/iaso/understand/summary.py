"""The end-of-turn work of the understanding layer (JUDGE, SR-105): what the owner's words
confirmed, the turn's upkeep (``_upkeep``) and the jobs it queues, left to the background worker
after the stop (``queue_after_stop``). No card is drawn at a turn's end (SR-373, DEC-384); what
the owner must settle reaches the agent as the stop hook's one next action. Nothing here
confirms anything."""

from __future__ import annotations

from iaso.paths import state_dir

import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from iaso.present import owner_text
from iaso.understand import files

UNDER_BUDGET_S = 0.35        # the upkeep (the log's cards, the offers) needs this much left
CALIBRATE_S = 0.9            # rerunning the calibration needs this much left


# --------------------------------------------------------------------------- debug cases


def write_cases(core: Any, sha: str, cases: Sequence[Mapping[str, Any]]) -> None:
    """Write a landing's debug cases to ``.iaso/cache/debug/<sha>.json`` (SR-300): a list of
    ``{id, kind, target, detail, state}``, state ``open`` or ``resolved``. No cases, no file."""
    keys = ("id", "kind", "target", "detail", "state")
    rows = [{k: str(c.get(k) or ("open" if k == "state" else "")) for k in keys} for c in cases]
    if rows:
        files.write_json_atomic(state_dir(Path(core.root)) / "cache" / "debug" / f"{sha}.json",
                                rows)


def cases_text(cases: Sequence[Mapping[str, Any]], resolved: int = 0,
               workflow: str = "", models: Mapping[str, str] | None = None) -> str:
    """The text block that tells the agent its open cases (SR-300 EX-1); with ``workflow`` it
    names iaso's shipped workflow to run them with (SR-385)."""
    lines = [f"- {c['id']} ({c['kind']}) {c['target']}: {c['detail']}" for c in cases]
    run = (f"Run them with iaso's workflow {workflow} on Sonnet (a Workflow on Sonnet), "
           f"passing these case ids: {', '.join(str(c['id']) for c in cases)}"
           + (f" and models {json.dumps(dict(models))}" if models else "") + ": " if workflow
           else "Run them as a Workflow on Sonnet: ")
    return (f"iaso: {len(lines)} debug cases open, {resolved} resolved:\n" + "\n".join(lines)
            + "\n" + run + "repin after tests, relink, rerun; a changed "
            "meaning is one question to the owner through the question tool; "
            "`iaso understand debug done <case id>` marks one resolved.")


def open_cases(root: Path) -> tuple[list[dict[str, Any]], int]:
    """``(open cases, resolved count)`` of the debug files that still hold an open case."""
    rows: list[dict[str, Any]] = []
    for path in sorted((state_dir(Path(root)) / "cache" / "debug").glob("*.json")):
        found = files.read_json(path)
        if isinstance(found, list) and any(r.get("state") == "open" for r in found):
            rows += [r for r in found if isinstance(r, dict)]
    return [r for r in rows if r.get("state") == "open"], sum(
        1 for r in rows if r.get("state") == "resolved")


def resolve_cases(root: Path, ids: Sequence[str]) -> int:
    """Mark the cases ``ids`` resolved in every debug file (SR-300 EX-2); how many changed."""
    changed = 0
    for path in (state_dir(Path(root)) / "cache" / "debug").glob("*.json"):
        rows = files.read_json(path)
        if not isinstance(rows, list):
            continue
        hit = [r for r in rows if isinstance(r, dict) and r.get("id") in ids
               and r.get("state") == "open"]
        for row in hit:
            row["state"] = "resolved"
        if hit:
            files.write_json_atomic(path, rows)
            changed += len(hit)
    return changed


def run_debug(argv: Sequence[str]) -> int:
    """``iaso understand debug done <case id>...``."""
    import sys

    from iaso.cliutil import resolve_root

    if len(argv) < 2 or argv[0] != "done":
        print("usage: iaso understand debug done <case id>...", file=sys.stderr)
        return 2
    root = resolve_root(None)
    changed = resolve_cases(root, list(argv[1:]))
    left, resolved = open_cases(root)
    print(f"iaso: {changed} debug cases resolved; {len(left)} open, {resolved} resolved")
    return 0 if changed else 1


# --------------------------------------------------------------------------- what was told


class Told:
    """What the owner was already told in this session (``told.json``): the notices said once
    and the owner-words confirmations."""

    def __init__(self, root: Any, session: str, now: str) -> None:
        self.path = files.session_dir(root, session) / "told.json"
        raw = files.read_json(self.path)
        data = raw if isinstance(raw, Mapping) else {}
        self.since = str(data.get("since") or now)
        self.notices = set(str(d) for d in data.get("notices") or ())
        self.confirmed = set(str(d) for d in data.get("confirmed") or ())
        self.dirty = not data

    def save(self) -> None:
        if self.dirty:
            files.write_json_atomic(self.path, {"since": self.since,
                                                "notices": sorted(self.notices),
                                                "confirmed": sorted(self.confirmed)})


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# --------------------------------------------------------------------------- the parts


def _confirmations(core: Any, turn: Any, told: Told | None = None) -> tuple[str, ...]:
    """What the owner's words confirmed for this turn's message, then what they confirmed for
    an earlier message whose read finished after that turn ended (told once)."""
    try:
        from iaso.understand import read

        lines = [str(line) for line in read.confirmation_lines(core, turn)]  # READ's wording
    except (ImportError, AttributeError):
        return ()
    if told is None:
        return tuple(lines)
    digest = turn.get("prompt_digest") if isinstance(turn, Mapping) else turn
    index = core.index()
    judged: set[str] = set()
    from iaso import words

    said_by = words.held(core)
    for entry in core.events():
        payload = entry.payload
        if (entry.kind != "approval" or payload.get("by") not in ("owner-words", "auto-model",
                                                                 "auto-jev")
                or entry.digest in told.confirmed):
            continue
        told.confirmed.add(entry.digest)
        told.dirty = True
        if payload["by"] != "owner-words":   # SR-251: judge approvals counted, once, no id
            if entry.at >= told.since:
                judged.update(str(r.get("id")) for r in payload.get("records") or ()
                              if isinstance(r, Mapping) and str(r.get("id")) in index)
            continue
        if payload.get("prompt_digest") == digest or entry.at < told.since:
            continue                      # this turn's own (above), or older than the session
        payload = words.joined(core, entry, said_by)   # DEC-116: the words are local
        said = owner_text.CONFIRM_YOU_SAID.format(evidence=payload.get("evidence", ""))
        for record in payload.get("records") or ():
            item = index.get(str(record.get("id")))
            lines.append(f"{item.title}: {said}" if item is not None else said)
    if judged:
        statuses = core.status(sorted(judged))
        n = sum(s.approved_by in ("auto-jev", "auto-model") for s in statuses.values())
        if n:
            lines.append(f"{n} {owner_text.JUDGE_APPROVED}")
    return tuple(lines)


def _labels_since_calibration(entries: Sequence[Any]) -> bool:
    """Whether an owner label (a trial answered, an owner-words confirmation, a rejection, an
    undo) came after the latest calibration from logged scores."""
    last = -1
    for position, entry in enumerate(entries):
        if entry.kind == "calibration" and entry.payload.get("source") == "logged":
            last = position
    return any(e.kind in ("trial", "rejection")
               or (e.kind == "approval" and e.payload.get("by") == "owner-words")
               or (e.kind == "revocation" and e.payload.get("by") == "undone")
               for e in entries[last + 1:])


def _upkeep(core: Any, session: str, recalibrate: bool) -> None:
    """The turn's upkeep, from the logs alone (no model): rerun the calibration from the logged
    scores after an owner label. No trial card is drawn (SR-252 EX-6)."""
    entries = core.events()
    if recalibrate and any(e.kind == "verdict" for e in entries) and _labels_since_calibration(
            entries):
        try:
            from iaso.capture import calibrate

            calibrate.calibrate(core)
        except Exception:  # noqa: BLE001 - upkeep never fails the turn
            pass


def _turn_upkeep(core: Any, session: str, turn: Mapping[str, Any], transcript: Any, *,
                 roomy: bool = True, calibrate: bool = True) -> tuple[str, ...]:
    """What the owner's words confirmed (told once), then the upkeep and the queued jobs."""
    started = float(turn.get("turn_start") or 0) or time.time()
    told = Told(core.root, session, _iso(started))
    confirmations = _confirmations(core, turn, told)
    told.save()
    if roomy:
        try:
            _upkeep(core, session, calibrate)
        except Exception:  # noqa: BLE001 - the upkeep never costs the owner their summary
            pass
        try:
            from iaso.understand import backlog, question, tidy

            backlog.resume(core, session)    # a pass a failure interrupted goes on (spec 8)
            tidy.enqueue(core, session)      # SR-162: the model reads the open questions after this turn
            question.enqueue(core, session, transcript)   # SR-167: a question to raise
        except Exception:  # noqa: BLE001 - queueing never costs the owner their summary
            pass
    return confirmations


AFTER_STOP = "after_stop.json"   # the turn whose end left work for the worker (SR-375)


def queue_after_stop(root: Any, session: str, turn: Mapping[str, Any],
                     transcript: Any = None) -> None:
    """SR-375: the stop hook's work its reader does not need before the next step (the
    owner-words confirmations, the upkeep, the jobs to queue) is left to the background
    worker, started now. Never raises (a hook calls this)."""
    try:
        files.write_json_atomic(files.session_dir(Path(root), session) / AFTER_STOP,
                                {"turn": dict(turn), "transcript": transcript})
        from iaso.understand import worker

        worker.start_detached(Path(root), session)
    except Exception:  # noqa: BLE001 - the next turn end queues it again
        pass


def after_stop(core: Any, session: str) -> None:
    """In the worker: the work a turn end left (``queue_after_stop``); its lines reach the
    agent at the next prompt (``worker.say``)."""
    import os

    path = files.session_dir(Path(core.root), session) / AFTER_STOP
    # claimed by an atomic rename, so one worker does it and an ``after_stop.json*`` file
    # means its lines are not all said yet
    claimed = path.with_name(f"{AFTER_STOP}.{os.getpid()}")
    try:
        os.replace(path, claimed)
    except OSError:
        return
    try:
        data = files.read_json(claimed)
        if not isinstance(data, Mapping):
            return
        turn = data.get("turn") if isinstance(data.get("turn"), Mapping) else {}
        from iaso.understand import worker

        for line in _turn_upkeep(core, session, turn, data.get("transcript")):
            worker.say(core.root, session, line)
        from iaso.hosts.claude_code.snapshot import refresh_counts

        refresh_counts(core)   # the status line's record-wide counts the stop hook left as is
    finally:
        claimed.unlink(missing_ok=True)


ASK_OWNER = ("iaso: only the owner can settle this; ask the owner now with the question tool, "
             "in plain words with options and no id; choose nothing yourself:")


def owner_line(core: Any, session: str, *, regression: str = "") -> str:
    """SR-373: the owner's one plain line at a turn end, only when something needs them: a
    regression on confirmed behaviour (worded by the stop hook), else a merge that waits for
    their decision. Nothing inside an open intent loop (the band shows its step) and nothing
    already said in the session; the judge's questions reach the owner through the agent's
    question tool (SR-361), never here."""
    from iaso.understand.cmd_intent import loops

    if any(d.get("step") != "proven" and not d.get("handed_to")
           for _, d in loops(core.root, session)):
        return ""
    line = regression
    if not line:
        try:
            from iaso.mergedriver.conflicts import open_conflicts

            n = len(open_conflicts(core))
        except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
            n = 0
        line = (f"iaso: a merge waits for your decision on {n} conflicting "
                f"record{'s' if n > 1 else ''}") if n else ""
    told = Told(core.root, session, _iso(time.time()))
    if not line or line in told.notices:
        return ""
    told.notices.add(line)
    told.dirty = True
    told.save()
    return line
