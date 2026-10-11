"""The backlog pass (JUDGE, SR-107, spec 8).

The records proposed before SP8 are judged in **one background pass**: a series of judge jobs,
each covering the records of one intent as a capture does, queued together and never metered per
turn. A job already done is not run again unless its record changed (a job is its records at
their versions, so the same records are the same job), and a pass a failure interrupted resumes
on the next turn from where it stopped: ``start`` queues only the records that have no judgment
at their current version.

What the pass finds comes as cards when it ends: one **feature card** per feature ("these 18
about the merge check would be settled; right?"), with one record drawn from below the
threshold; a flagged record (beyond, contradicts) is an issue card and is on no feature card; a
decision is asked on its own; a record whose premise is only a fragment of the owner's words
says its original words are not on file and offers its read-back. The cards are offered a few per
turn (``summary``), the features with most records first.

While it runs the pass reports "judging the backlog" with the records judged and the total
(``progress.Reporter``); when it ends the last job writes the end line."""

from __future__ import annotations

import hashlib
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from plumb.contracts import Applied, CardState, ClarifyQuestion
from plumb.present import owner_text
from plumb.understand import cards, files

PASS = "backlog"
KINDS_JUDGED = ("intent", "requirement", "decision")
DRAWN_WORDS = 160


@dataclass
class Started:
    """What ``start`` queued: the job ids, the records they cover, the pass's total."""

    jobs: list[str] = field(default_factory=list)
    records: int = 0
    total: int = 0


@dataclass
class After:
    cards: list[CardState] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- the records


def marker_path(root: Any, session: str) -> Any:
    return files.session_dir(root, session) / "backlog.json"


def proposed(core: Any) -> list[Any]:
    """The records waiting for the owner that the judge covers: proposed, or edited since the
    owner confirmed them, and not superseded."""
    index = core.index()
    statuses = core.status()
    return [index[i] for i in sorted(index)
            if index[i].kind in KINDS_JUDGED and statuses[i].confirmation != "confirmed"
            and statuses[i].superseded_by is None]


def latest_verdicts(core: Any) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for entry in core.events():
        if entry.kind == "verdict":
            out[str(entry.payload.get("id"))] = entry.payload
    return out


def judged_ids(core: Any, records: Sequence[Any]) -> set[str]:
    """The records with a judgment of their current version."""
    verdicts = latest_verdicts(core)
    return {r.id for r in records if verdicts.get(r.id, {}).get("hash") == r.hash}


def group_of(index: Mapping[str, Any], record: Any) -> str:
    """The intent a record belongs to (itself for an intent or a record deriving from none)."""
    if record.kind == "intent":
        return record.id
    for link in record.links:
        if link.kind == "derives_from" and link.target.record in index \
                and index[link.target.record].kind == "intent":
            return link.target.record
    return record.id


def features(core: Any) -> dict[str, str]:
    """Record id -> the title of the feature it is about. A requirement says its feature; an
    intent takes the feature most of its requirements are in; a record in none has no entry."""
    index = core.index()
    own: dict[str, str] = {}
    for record in index.values():
        feature = record.fields.get("feature")
        if feature in index and index[str(feature)].kind == "feature":
            own[record.id] = str(feature)
    by_intent: dict[str, Counter[str]] = {}
    for record_id, feature in own.items():
        by_intent.setdefault(group_of(index, index[record_id]), Counter())[feature] += 1
    out: dict[str, str] = {i: index[f].title for i, f in own.items()}
    for intent_id, counts in by_intent.items():
        if intent_id not in out and intent_id in index and index[intent_id].kind == "intent":
            out[intent_id] = index[counts.most_common(1)[0][0]].title
    for record in index.values():          # a decision or a requirement without a feature
        if record.id not in out and record.kind != "intent":
            parent = group_of(index, record)
            if parent in out:
                out[record.id] = out[parent]
    for record in index.values():          # no feature on the way: grouped by the intent
        if record.id not in out and record.kind in KINDS_JUDGED:
            parent = group_of(index, record)
            if parent in index and index[parent].kind == "intent":
                out[record.id] = index[parent].title
    return out


# --------------------------------------------------------------------------- the pass


def start(core: Any, session: str) -> Started:
    """Queue the judge jobs of the pass: one per intent, covering the records that have no
    judgment of their current version. Idempotent: a job is its records, so jobs already
    queued or done are the same jobs. Marks the pass as started so ``resume`` continues it."""
    from plumb.understand import judge, queue

    records = proposed(core)
    done = judged_ids(core, records)
    index = core.index()
    groups: dict[str, list[str]] = {}
    for record in records:
        if record.id not in done:
            groups.setdefault(group_of(index, record), []).append(record.id)
    out = Started(records=sum(len(v) for v in groups.values()), total=len(records))
    for key in sorted(groups):
        job = judge.build(core, session, records=groups[key], **{"pass": PASS,
                                                                  "total": len(records)})
        if job is not None:
            queue.enqueue(core, job)
            out.jobs.append(job.id)
    files.write_json_atomic(marker_path(core.root, session), {
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "total": len(records)})
    return out


def resume(core: Any, session: str) -> Started:
    """Continue a pass that was started (a failed job is queued again by the queue); nothing
    when no pass was started or nothing is left."""
    if not marker_path(core.root, session).exists():
        return Started()
    return start(core, session)


def holding(core: Any, session: str) -> set[str]:
    """The records a started pass that is not finished keeps back from the trial: their
    cards come when the pass ends."""
    if not marker_path(core.root, session).exists():
        return set()
    records = proposed(core)
    if len(judged_ids(core, records)) >= len(records):
        return set()
    return {r.id for r in records}


# --------------------------------------------------------------------------- cards


def fragment_card(record: Any) -> CardState:
    """The card of a record whose original words are not on file: it offers the record's own
    read-back for the owner to accept or correct."""
    fields = record.fields
    readback = " ".join(str(fields.get("readback") or fields.get("statement")
                            or record.title).split())
    quote = fields.get("quote")
    fragment = " ".join(str(q) for q in quote) if isinstance(quote, (list, tuple)) \
        else str(quote or "")
    cid = f"backlog:words:{record.id}"
    options = (owner_text.NO_ORIGINAL_ACCEPT, owner_text.NO_ORIGINAL_CORRECT)
    issue = owner_text.NO_ORIGINAL_WORDS.format(readback=readback)
    return CardState(
        id=cid, kind="backlog", topic=record.title, issue=issue,
        evidence=cards.clip(fragment, DRAWN_WORDS), resolutions=options,
        questions=(ClarifyQuestion(id=f"{cid}#1", text=record.title, resolutions=options,
                                   record=record.id, hash=record.hash,
                                   choices=cards.choices_for("backlog", options)),))


def feature_card(topic: str, above: Sequence[Any], drawn: Any | None) -> CardState:
    """One card for a feature: the records the judge would settle, and one drawn from below
    the threshold, asked as such."""
    items = [*above, *([drawn] if drawn is not None else [])]
    key = "\n".join(sorted(f"{i.record.id}@{i.record.hash}" for i in items))
    cid = "backlog:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    options = (owner_text.BACKLOG_YES, owner_text.BACKLOG_EXCEPT, owner_text.BACKLOG_NO)
    choices = cards.choices_for("backlog", options)
    questions = [ClarifyQuestion(id=f"{cid}#{n}", text=i.record.title, resolutions=options,
                                 record=i.record.id, hash=i.record.hash, choices=choices)
                 for n, i in enumerate(above, start=1)]
    if drawn is not None:
        questions.append(ClarifyQuestion(
            id=f"{cid}#{len(above) + 1}", resolutions=options, record=drawn.record.id,
            hash=drawn.record.hash, text=f"{owner_text.TRIAL_BELOW} {drawn.record.title}",
            choices=choices))
    sample: list[str] = []
    for item in above:
        words = cards.words_of(item.premise)
        if words and words not in sample:
            sample.append(words)
        if len(sample) == 3:
            break
    return CardState(
        id=cid, kind="backlog", topic=topic,
        issue=owner_text.BACKLOG_FEATURE.format(n=len(above), topic=topic),
        evidence=" | ".join(cards.clip(w, DRAWN_WORDS) for w in sample), resolutions=options,
        questions=tuple(questions))


def pass_cards(core: Any, session: str, extra: Sequence[Any]) -> list[CardState]:
    """The cards of a finished pass: a feature card per feature, an individual card for each
    record that never settles. ``extra`` are the supported records of the last job, whose
    judgments are not in the log yet."""
    from plumb.understand import trial

    fragments = {c.questions[0].record for c in cardstore_cards(core, session)
                 if c.id.startswith("backlog:words:")}
    held = trial._open_records(core, session)
    now = {c.record.id: c for c in extra}
    pool = [*now.values(), *trial.from_log(core, held | set(now) | fragments)]
    pool = [c for c in pool if c.premise.get("messages")
            and not all(m.get("partial") for m in c.premise["messages"])]
    out = [trial.individual_card(c) for c in pool if c.reason]
    titles = features(core)
    by_feature: dict[str, list[Any]] = {}
    for item in pool:
        if not item.reason:
            by_feature.setdefault(titles.get(item.record.id, item.record.title), []).append(item)
    for topic in sorted(by_feature):
        group = by_feature[topic]
        above = sorted((i for i in group if i.score >= trial.threshold(core, i.record.kind)),
                       key=lambda i: i.record.id)
        below = sorted((i for i in group if i.score < trial.threshold(core, i.record.kind)),
                       key=lambda i: (-i.score, i.record.id))
        if above:
            out.append(feature_card(topic, above, below[0] if below else None))
    return out


def cardstore_cards(core: Any, session: str) -> list[CardState]:
    from plumb.understand import cardstore

    return [c for c in cardstore.own_cards(core.root, session) if c.status == "open"]


def after_job(core: Any, job: Any, *, supported: Sequence[Any], waiting: Sequence[Any],
              verdicts: Sequence[Mapping[str, Any]], fragments: Sequence[Any],
              flagged: Sequence[CardState]) -> After:
    """Called by ``judge.apply`` for a job of the pass: report the progress; when this job
    finishes the pass, build the cards and write the end line. ``fragments`` are the records
    of this job whose original words are not on file (their cards are made here)."""
    from plumb.progress import Reporter
    from plumb.understand import trial

    result = After(cards=[fragment_card(r) for r in fragments])
    records = proposed(core)
    judged = judged_ids(core, records) | {str(v["id"]) for v in verdicts}
    waiting_for = [r for r in records if r.id not in judged]
    total = max(int(job.inputs.get("total") or 0), len(records))
    done = total - len(waiting_for)
    reporter = Reporter(core.root, job.session, "judge")
    if waiting_for:
        reporter.update(owner_text.STEP_JUDGING_BACKLOG, done, total)
        return result
    extra = [trial.Candidate(w.item.record, w.item.score, w.item.premise, w.reason)
             for w in waiting]
    built = pass_cards(core, job.session, extra)
    result.cards.extend(c for c in built
                        if c.id not in {x.id for x in result.cards})
    waiting_now = [c for c in cardstore_cards(core, job.session)
                   if c.kind in ("trial", "backlog", "beyond", "contradicts", "show_first")]
    seen = {c.id for c in waiting_now}
    count = len(waiting_now) + len([c for c in [*result.cards, *flagged] if c.id not in seen])
    reporter.done(final=owner_text.BACKLOG_DONE.format(judged=done, cards=count))
    return result


# --------------------------------------------------------------------------- the answer


def effect(*, core: Any = None, card: CardState | None = None, question: Any = None,
           entry: Mapping[str, Any] | None = None, accepted: bool = False,
           confirm: Any = None, **_: Any) -> Applied | None:
    """A backlog card answered. A yes that is the card's as a whole confirms every record on
    it, each labelled yes (calibration reads the label) and each at the version the card
    showed; a record changed since is shown again instead. An answer to one record is applied
    by the reader, which maps the exceptions the owner names ("yes, except ...") per record."""
    if card is None or core is None or confirm is None or not accepted or question:
        return None
    from plumb.understand import read

    entry = entry or {}
    index = core.index()
    answered = {a.question for a in card.answers}
    fresh: list[CardState] = []
    for q in card.questions:
        if q.record not in index or q.id in answered:
            continue
        if index[q.record].hash != q.hash:      # changed since the card showed it: show it again
            fresh.append(read.show_first_card(index[q.record], str(entry.get("evidence") or "")))
            continue
        confirm(q.record, q.hash, str(entry.get("evidence") or ""),
                float(entry.get("confidence") or 0), label="yes")
    return Applied(cards=tuple(fresh)) if fresh else None


def run(command: str, argv: list[str]) -> int:
    """``plumb understand backlog``: start (or continue) the pass from a shell."""
    import argparse

    from plumb.api import open_core
    from plumb.cliutil import add_common, resolve_root

    parser = argparse.ArgumentParser(prog="plumb understand backlog")
    add_common(parser)
    parser.add_argument("--session", default=files.CLI_SESSION)
    args = parser.parse_args(argv)
    core = open_core(resolve_root(args.root))
    started = start(core, args.session)
    print(owner_text.BACKLOG_STARTED.format(records=started.records, jobs=len(started.jobs))
          if started.jobs else owner_text.BACKLOG_NOTHING)
    return 0
