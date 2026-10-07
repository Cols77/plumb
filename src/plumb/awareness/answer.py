"""The owner's answer to an EARLY intent conflict: one choke point (ruling R17, SR-081).

R17: an early conflict card ("feat-x says A, this request says B: which one, or both?") is
asked at once, "the answer is recorded once (a DEC) and both lanes build on it". The card
tells the owner to say "keep feat-x's", "keep this one" or "both". This module turns those
words, and only those words, into the decision:

- ``relay``: the owner's words relayed from a logged prompt (``plumb conflict relay
  DEC-### [--take <branch>|both]``, the agent's path; the prompt hook's log, or a message
  the agent recorded itself on a host without one, labelled "self-recorded message");
- ``choose_owner``: the owner's own terminal (``plumb conflict choose DEC-###``);
- ``answer_from_conflict``: a merge-time conflict card the owner answered on a record an
  unanswered early decision decides (``conflicts.apply_choice``), so one answer settles
  both questions.

Each one ends in ``record_answer``: the decision's ``chosen`` becomes the option the
owner's words name, and an approval pinned to that new content records the owner's words
(``choice`` in the payload: the re-check of ``confirm.entry_problem`` accepts a quote that
names the chosen option in place of an affirmation term). The answer then reaches every
other branch at once (``inflight.sync_decisions``).

``settling`` and ``apply_settled`` are the merge side: a merge-time intent conflict whose two
versions are the ones a confirmed early decision chose between is settled by that answer,
never asked again (``premerge.check``, ``plumb conflicts``, the conflict card).

``plain_relay_problem`` keeps plain ``plumb relay`` honest: an "ok" that names another
version than the decision's chosen one is refused, never recorded as the opposite answer.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from plumb.present import owner_text as text

FIELD = "early"
BOTH = "both"
_VERSION = re.compile(r"(.+)'s version")
# words that name "this side" (the branch whose session shows the card); EARLY_RELATIVE's
# phrases, plus the card's own "keep this one"
_RELATIVE = ("this one", "this request", "this request's", "this request's version",
             "this work", "this work's", "this version", "mine", "ours", "my version",
             "my one", "the new one", "this lane", "this lane's")
_OTHER = ("theirs", "their version", "their one", "the other one", "the other version",
          "the other branch's", "that one", "that version", "that branch's")
# the merge-time card's own words for its two sides (``conflicts.named_takes``)
_IC_OURS = ("mine", "ours", "my version", "my one", "my side")
_IC_THEIRS = ("theirs", "their version", "their one", "their side", "the incoming one")
_BOTH = ("both", "both of them", "combined", "combine them", "combine both", "both, combined",
         "the combined one", "keep both")


class AnswerRefused(PermissionError):
    """The words do not ground this answer (exit 3); nothing is written."""


class AnswerError(ValueError):
    """No early decision matches, or an option that does not exist (exit 1 or 2)."""


@dataclass(frozen=True)
class Early:
    """An early-conflict decision: the record it decides, the branch that raised it, the
    other branch and, by branch, the hash of the version each held when it was asked (or
    answered)."""

    dec: str
    record: str
    raised_on: str
    other: str
    chosen: str
    hashes: Mapping[str, str] = field(default_factory=dict)

    @property
    def branches(self) -> tuple[str, str]:
        return self.raised_on, self.other

    def key_of(self, option: str) -> str | None:
        """The branch (or ``both``) an option's words name."""
        words = " ".join(str(option or "").split())
        if words.lower().startswith("both"):
            return BOTH
        match = _VERSION.fullmatch(words)
        if match and match.group(1) in self.branches:
            return match.group(1)
        return None

    @property
    def chosen_key(self) -> str | None:
        return self.key_of(self.chosen)


def option(key: str) -> str:
    return text.EARLY_BOTH if key == BOTH else text.EARLY_THEIRS.format(branch=key)


def early_of(record: Any) -> Early | None:
    """The early conflict a decision holds, or None for any other record. A decision
    written before the ``early`` field existed is recognised by its options (two
    "<branch>'s version" and "both, combined") and its one ``decides`` link."""
    if record is None or getattr(record, "kind", "") != "decision":
        return None
    fields = record.fields or {}
    chosen = " ".join(str(fields.get("chosen") or "").split())
    block = fields.get(FIELD)
    if isinstance(block, Mapping) and block.get("record") and block.get("raised_on"):
        hashes = block.get("hashes") if isinstance(block.get("hashes"), Mapping) else {}
        return Early(dec=record.id, record=str(block["record"]),
                     raised_on=str(block["raised_on"]), other=str(block.get("other") or ""),
                     chosen=chosen, hashes={str(k): str(v) for k, v in hashes.items()})
    alternatives = fields.get("alternatives") or []
    if isinstance(alternatives, str):
        alternatives = [alternatives]
    options = [chosen, *(" ".join(str(a).split()) for a in alternatives)]
    if text.EARLY_BOTH not in options:
        return None
    branches = [m.group(1) for o in options if (m := _VERSION.fullmatch(o))]
    decides = [link.target.record for link in record.links
               if link.kind == "decides" and link.target.record]
    if len(branches) != 2 or len(decides) != 1:
        return None
    return Early(dec=record.id, record=decides[0], raised_on=branches[0], other=branches[1],
                 chosen=chosen)


def early_decisions(index: Mapping[str, Any], record_id: str | None = None) -> list[Early]:
    out = []
    for record in index.values():
        found = early_of(record)
        if found is not None and (record_id is None or found.record == record_id):
            out.append(found)
    return sorted(out, key=lambda e: e.dec)


# --------------------------------------------------------------------------- the words


def _pattern(words: Iterable[str]) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))
    return re.compile(rf"(?<![\w-])(?:{alternatives})(?![\w-])", re.IGNORECASE)


def _here(early: Early, current: str | None) -> str:
    """The branch "this one" names: the session's own branch when it is a side, else the
    branch that raised the card (the one whose session showed it)."""
    return current if current in early.branches else early.raised_on


def named_keys(early: Early, quote: str, current: str | None = None) -> set[str]:
    """The options the owner's words name: a branch (its name, "keep this one" for the
    branch whose session shows the card, "theirs" for the other one) or ``both``."""
    here = _here(early, current)
    there = early.other if here == early.raised_on else early.raised_on
    found: set[str] = set()
    for branch in early.branches:
        if branch and _pattern([branch]).search(quote):
            found.add(branch)
    if _pattern(_RELATIVE).search(quote):
        found.add(here)
    if _pattern(_OTHER).search(quote):
        found.add(there)
    if _pattern(_BOTH).search(quote):
        found.add(BOTH)
    return found


def chosen_key(named: set[str]) -> str | None:
    """The one choice the words make: ``both`` when they say both (the branches they name
    then describe the combination), else exactly one branch."""
    if BOTH in named:
        return BOTH
    return next(iter(named)) if len(named) == 1 else None


def choice_named(quote: str, choice: Mapping[str, Any]) -> bool:
    """The re-check of an approval recorded from the owner's pick (``choice`` in its
    payload): the quote names the chosen option itself (``confirm.entry_problem``)."""
    take = str(choice.get("take") or "")
    if not take or not quote:
        return False
    if take == BOTH:
        return _pattern(_BOTH).search(quote) is not None
    names = [take, *(str(n) for n in choice.get("names") or [] if str(n).strip())]
    if _pattern(names).search(quote):
        return True
    if choice.get("here") == take and _pattern(_RELATIVE).search(quote):
        return True
    return bool(choice.get("there") == take and _pattern(_OTHER).search(quote))


def normalize_take(early: Early, take: str, current: str | None = None) -> str:
    wanted = " ".join(take.strip().lower().split()).removeprefix("keep ").removesuffix(
        "'s version").removesuffix("'s")
    here = _here(early, current)
    for branch in early.branches:
        if wanted == branch.lower():
            return branch
    if wanted in ("ours", "mine", "this", "this one", "here"):
        return here
    if wanted in ("theirs", "other", "the other one", "there"):
        return early.other if here == early.raised_on else early.raised_on
    if wanted in ("both", "combined", "both, combined"):
        return BOTH
    raise AnswerError(f"plumb: --take is {early.raised_on}, {early.other} or both")


def say_line(early: Early, current: str | None = None) -> str:
    """The card's answer line from the session's point of view: "keep this one" names the
    branch whose session shows it."""
    here = _here(early, current)
    there = early.other if here == early.raised_on else early.raised_on
    return text.EARLY_CARD_SAY.format(branch=there).strip()


# --------------------------------------------------------------------------- finding it


def _current(core: Any) -> str | None:
    from pathlib import Path

    from plumb.awareness import gitfiles

    me = gitfiles.current(Path(core.root))
    return me.branch if me is not None else None


def find(core: Any, ref: str) -> Early:
    """The early decision a ``DEC-###``, the record it decides (``SR-###``) or the owner's
    plain words name; an unanswered one first."""
    index = core.index()
    wanted = " ".join(ref.split())
    if wanted.upper() in index:
        found = early_of(index[wanted.upper()])
        if found is not None:
            return found
        record_id = wanted.upper()
    else:
        record_id = ""
    candidates = early_decisions(index)
    if not candidates:
        raise AnswerError(text.NO_CONFLICTS)
    if record_id:
        matches = [e for e in candidates if e.record == record_id]
    else:
        words = set(re.findall(r"\w+", wanted.lower()))
        matches = [e for e in candidates if words & set(
            re.findall(r"\w+", str(index[e.record].title if e.record in index else "").lower()))]
    if len(matches) > 1:
        statuses = core.status([e.dec for e in matches])
        open_ = [e for e in matches if statuses[e.dec].confirmation != "confirmed"]
        matches = open_ if len(open_) == 1 else matches
    if len(matches) == 1:
        return matches[0]
    if not wanted and len(candidates) == 1:
        return candidates[0]
    raise AnswerError(f"plumb: which conflict do you mean? {', '.join(e.dec for e in candidates)}")


def is_early_ref(core: Any, ref: str) -> bool:
    """Whether ``ref`` names an early decision (a DEC, or a record with no open merge
    conflict that an early decision decides)."""
    index = core.index()
    wanted = ref.strip().upper()
    if wanted in index:
        if early_of(index[wanted]) is not None:
            return True
        if index[wanted].kind == "decision":
            return False
        block = index[wanted].fields.get("conflict")
        if isinstance(block, Mapping) and block.get("id"):
            return False
        return bool(early_decisions(index, wanted))
    return False


# --------------------------------------------------------------------------- recording it


def _hashes(core: Any, early: Early, current: str | None) -> dict[str, str]:
    """The version each branch holds now: this checkout's for its own branch, the other
    branch's claimed one (``refs/plumb/claims``), else what the decision kept."""
    hashes = dict(early.hashes)
    record = core.index().get(early.record)
    if record is not None and current in early.branches:
        hashes[current] = record.hash
    try:
        from plumb.awareness import inflight

        _me, claims = inflight.others(core, allow_git=True)
    except Exception:  # noqa: BLE001 - the register is advisory here
        claims = []
    for claim in claims:
        branch = claim.get("branch")
        entry = (claim.get("records") or {}).get(early.record)
        if branch in early.branches and branch != current and isinstance(entry, Mapping) \
                and entry.get("hash"):
            hashes[str(branch)] = str(entry["hash"])
    return hashes


def record_answer(core: Any, early: Early, key: str, *, by: str, quote: str | None = None,
                  prompt: Mapping[str, Any] | None = None, names: Sequence[str] = (),
                  note: str = "") -> dict[str, Any]:
    """Write the owner's choice into the decision and pin it with one approval."""
    from plumb.capture.records import rewrite
    from plumb.normalize import sha256_text

    current = _current(core)
    index = core.index()
    record = index[early.dec]
    keys = [early.raised_on, early.other, BOTH]
    chosen = option(key)
    alternatives = [option(k) for k in keys if k != key]
    block = {"record": early.record, "raised_on": early.raised_on, "other": early.other,
             "hashes": _hashes(core, early, current)}
    rewrite(core, record, {"chosen": chosen, "alternatives": alternatives, FIELD: block})
    from plumb.approvals import approval_items

    payload: dict[str, Any] = {
        "records": approval_items(core, [early.dec]), "by": by,
        "prompt_digest": None, "quote": None, "quote_digest": None, "affirmation": None,
        "stated_set": None, "note": note or "the owner's answer to the early conflict card",
        "choice": {"take": key, "option": chosen, "names": list(names),
                   "here": _here(early, current),
                   "there": early.other if _here(early, current) == early.raised_on
                   else early.raised_on}}
    if by == "agent-relayed":
        assert prompt is not None and quote is not None
        digest = str(prompt["digest"])
        known = {e.payload.get("digest") for e in core.log_read("events", ["prompt"])}
        if digest not in known:
            core.log_append("events", "prompt", {"digest": digest,
                                                 "session": prompt.get("session"),
                                                 "at": prompt.get("at")})
        payload.update({"prompt_digest": digest, "quote": quote,
                        "quote_digest": sha256_text(quote),
                        "self_recorded": prompt.get("via") != "hook"})
    core.log_append("events", "approval", payload)
    try:  # both lanes build on it: the other branches hear the answer now (R17)
        from plumb.awareness import inflight

        inflight.sync_decisions(core)
    except Exception:  # noqa: BLE001 - the register catches up at the next stop
        pass
    return payload


def _stated(core: Any, prompt_at: str) -> Mapping[str, Any]:
    try:
        data = json.loads(core.paths.stated.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, Mapping):
        return {}
    stated_at = str(data.get("at") or "")
    if stated_at and prompt_at and stated_at > prompt_at:
        return {}
    return data


def was_shown(core: Any, early: Early, prompt_at: str, quote: str) -> bool:
    """The owner saw the question in the reply before the prompt: the decision's card, or
    the early conflict card of its record and branches (capture, the clarify read-back),
    or the owner's words name the decision or its record."""
    from plumb.approvals import _named

    if _named(early.dec, quote) or _named(early.record, quote):
        return True
    data = _stated(core, prompt_at)
    if any(isinstance(r, Mapping) and r.get("id") == early.dec
           for r in data.get("records") or []):
        return True
    return any(isinstance(c, Mapping) and c.get("record") == early.record
               and c.get("branch") in early.branches for c in data.get("early") or [])


def relay(core: Any, ref: str, take: str | None, *, prompt: str,
          quote: str) -> tuple[Early, dict[str, Any]]:
    """The owner's answer, relayed from their logged words (``plumb conflict relay``)."""
    from plumb.approvals import Refused, objection_clauses, owner_prompt, quote_in_prompt
    from plumb.normalize import normalize_text

    early = find(core, ref)
    current = _current(core)
    try:
        entry = owner_prompt(core, prompt)
    except Refused as exc:
        raise AnswerRefused(str(exc)) from exc
    said = normalize_text(quote)
    if not said or not quote_in_prompt(said, normalize_text(str(entry.get("text") or ""))):
        raise AnswerRefused("the quote is not a verbatim part of that prompt (whole words)")
    named = named_keys(early, said, current)
    key = chosen_key(named)
    if take:
        wanted = normalize_take(early, take, current)
        if key != wanted:
            raise AnswerRefused(f"the quote must name the one choice made ({option(wanted)}) "
                                "and no other")
    if key is None:
        raise AnswerRefused("the quote names no version: the owner answers with the card's "
                            f"words ({say_line(early, current).removeprefix('Say: ')})")
    if key != BOTH:
        held = objection_clauses(said)
        if held:
            raise AnswerRefused("the quote holds a reservation or asks for a change ("
                                + "; ".join(held) + "); an answer must be the owner's "
                                "plain pick")
    if not was_shown(core, early, str(entry.get("at") or ""), said):
        raise AnswerRefused(f"the conflict card of {early.record} was not shown in the reply "
                            "before that prompt; show it (/plumb conflicts) and let the owner "
                            "answer it")
    payload = record_answer(core, early, key, by="agent-relayed", quote=said, prompt=entry)
    return early, payload


def choose_owner(core: Any, ref: str, take: str) -> tuple[Early, dict[str, Any]]:
    """The owner's own terminal (``approvals.require_owner``: refused under the session
    marker and without an interactive terminal, exit 3, nothing written)."""
    from plumb.approvals import require_owner

    early = find(core, ref)
    key = normalize_take(early, take, _current(core))
    require_owner("conflict choose", f"Keep {option(key)} of {early.record}?")
    return early, record_answer(core, early, key, by="owner")


def answer_line(core: Any, early: Early, key: str) -> str:
    title = core.index()[early.record].title if early.record in core.index() else ""
    return text.EARLY_ANSWERED.format(id=early.record, title=title, chosen=option(key))


def plain_relay_problem(core: Any, ids: Iterable[str], quote: str) -> str | None:
    """Plain ``plumb relay`` of an early decision: refused when the owner's words name
    another version than the one the decision holds (their pick goes through ``conflict
    relay``, which records it); an "ok" naming no version confirms what was shown."""
    index = core.index()
    current = None
    for record_id in ids:
        early = early_of(index.get(record_id))
        if early is None:
            continue
        current = current or _current(core)
        key = chosen_key(named_keys(early, quote, current))
        if key is not None and key != early.chosen_key:
            return (f"the owner's words choose {option(key)} for {record_id}, which holds "
                    f"{early.chosen or 'another option'}; record the owner's pick with "
                    f"`plumb conflict relay {record_id} --prompt <digest> --quote "
                    '"<exact words>"`')
    return None


# --------------------------------------------------------------------------- the merge side


@dataclass(frozen=True)
class Settled:
    dec: str
    take: str            # ours | theirs (the merge conflict's side)
    chosen: str          # the decision's words


def settling(core: Any, conflict: Any, *, statuses: Mapping[str, Any] | None = None
             ) -> Settled | None:
    """The confirmed early decision that already chose between exactly these two versions
    (by hash) of the conflicting record, as the merge-time side it picks; None when no
    decision, or decisions that disagree."""
    index = core.index()
    candidates = early_decisions(index, conflict.record)
    if not candidates:
        return None
    statuses = statuses if statuses is not None else core.status([e.dec for e in candidates])
    sides = {"ours": conflict.hashes.get("ours"), "theirs": conflict.hashes.get("theirs")}
    found: list[Settled] = []
    for early in candidates:
        status = statuses.get(early.dec)
        if status is None or status.confirmation != "confirmed":
            continue
        key = early.chosen_key
        if key in (None, BOTH):
            continue
        loser = early.other if key == early.raised_on else early.raised_on
        win, lose = early.hashes.get(key), early.hashes.get(loser)
        if not win or not lose:
            continue
        for side, other in (("ours", "theirs"), ("theirs", "ours")):
            if sides[side] == win and sides[other] == lose:
                found.append(Settled(dec=early.dec, take=side, chosen=early.chosen))
    takes = {s.take for s in found}
    return found[0] if len(takes) == 1 else None


def apply_settled(core: Any) -> list[str]:
    """Settle every open merge-time conflict the owner already answered before work began
    (``settling``); returns one line per record settled."""
    from plumb.mergedriver.conflicts import apply_choice, open_conflicts

    lines: list[str] = []
    for conflict in open_conflicts(core):
        settled = settling(core, conflict)
        if settled is None:
            continue
        apply_choice(core, conflict, settled.take, by="owner-decision",
                     decision=settled.dec)
        lines.append(text.EARLY_APPLIED.format(
            id=conflict.record, title=conflict.title, chosen=settled.chosen))
    return lines


def answer_from_conflict(core: Any, conflict: Any, take: str, *, by: str,
                         quote: str | None, prompt: str | None,
                         self_recorded: bool = False) -> list[str]:
    """The owner chose a side of a merge-time conflict on a record that unanswered early
    decisions decide: the same pick answers them (by hash, else by branch name), so the
    owner is never asked the same question twice. Returns the decisions answered."""
    if take not in ("ours", "theirs") or by not in ("owner", "agent-relayed"):
        return []
    index = core.index()
    candidates = early_decisions(index, conflict.record)
    if not candidates:
        return []
    statuses = core.status([e.dec for e in candidates])
    label = conflict.labels[0 if take == "ours" else 1]
    side_hash = conflict.hashes.get(take)
    answered: list[str] = []
    for early in candidates:
        if statuses[early.dec].confirmation == "confirmed":
            continue
        key = next((b for b in early.branches if side_hash and early.hashes.get(b) == side_hash),
                   None) or (label if label in early.branches else None)
        if key is None:
            continue
        prompt_entry = None
        if by == "agent-relayed":
            if not quote or not prompt:
                continue
            prompt_entry = {"digest": prompt, "via": "turn" if self_recorded else "hook"}
        words = [label, *(_IC_OURS if take == "ours" else _IC_THEIRS)]
        record_answer(core, early, key, by=by, quote=quote, prompt=prompt_entry,
                      names=words, note=f"the owner's answer to the merge conflict card "
                                         f"{conflict.ic}")
        answered.append(early.dec)
    return answered


def waiting_on_conflict(index: Mapping[str, Any], dec: str) -> bool:
    """An early decision whose record carries an open merge-time conflict: the conflict card
    asks that one question (and its answer answers the decision)."""
    early = early_of(index.get(dec))
    if early is None or early.record not in index:
        return False
    block = index[early.record].fields.get("conflict")
    return isinstance(block, Mapping) and bool(block.get("id"))


def card_conflict(core: Any, early: Early) -> Any:
    """The early conflict card of an unanswered decision, from this session's branch: the
    other branch's version (its claim's words, else the decision's question) beside this
    checkout's version of the record."""
    from plumb.awareness.early import EarlyConflict

    index = core.index()
    current = _current(core)
    here = _here(early, current)
    there = early.other if here == early.raised_on else early.raised_on
    theirs = ""
    try:
        from plumb.awareness import inflight

        _me, claims = inflight.others(core, allow_git=True)
        for claim in claims:
            entry = (claim.get("records") or {}).get(early.record)
            if claim.get("branch") == there and isinstance(entry, Mapping):
                theirs = str(entry.get("text") or "")
    except Exception:  # noqa: BLE001 - the question still names both versions
        theirs = ""
    record = index.get(early.record)
    question = str(index[early.dec].fields.get("question") or "") if early.dec in index else ""
    ours = str(record.fields.get("statement") or record.title) if record is not None else ""
    return EarlyConflict(record=early.record, title=record.title if record is not None else "",
                         branch=there, claim="", theirs=theirs or question, ours=ours)
