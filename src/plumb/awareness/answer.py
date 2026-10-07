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

``superseded`` is the losing lane's side (R17: "both lanes build on it"): a record of this
checkout whose words still differ from the version the owner chose in a confirmed early
decision (held here, or carried by another branch's claim) is named on every turn (the
prompt delta, the stop hook, status) until it matches, and no "ok" confirms it meanwhile.
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


class NoEarly(AnswerError):
    """No early decision matches the words (none raised yet, or none for that record)."""


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
    texts: Mapping[str, str] = field(default_factory=dict)  # each branch's words, as asked

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
        texts = block.get("texts") if isinstance(block.get("texts"), Mapping) else {}
        raised_on, other = str(block["raised_on"]), str(block.get("other") or "")
        return Early(dec=record.id, record=str(block["record"]), raised_on=raised_on,
                     other=other, chosen=chosen,
                     hashes={str(k): str(v) for k, v in hashes.items()},
                     texts={**_asked_texts(fields, raised_on, other),
                            **{str(k): str(v) for k, v in texts.items() if v}})
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
                 chosen=chosen, texts=_asked_texts(fields, branches[0], branches[1]))


_QUESTION = re.compile(r'Branch (?P<branch>.+?) says "(?P<theirs>.*)"; this request says '
                       r'"(?P<ours>.*)": which one, or both\?$', re.DOTALL)


def _asked_texts(fields: Mapping[str, Any], raised_on: str, other: str) -> dict[str, str]:
    """Each branch's words as the decision asked them (``owner_text.EARLY_QUESTION``: the
    other branch's version, then the raising request's), for a decision written before it
    kept them by branch."""
    match = _QUESTION.match(" ".join(str(fields.get("question") or "").split()))
    if match is None or match.group("branch") != other:
        return {}
    return {other: match.group("theirs"), raised_on: match.group("ours")}


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


def _here(early: Early, current: str | None) -> str | None:
    """The branch "this one" names: the session's own branch when it is one of the two
    sides, else None. On any other branch (the default branch after one side merged) the
    words "this one", "mine" or "theirs" name no version: the card labels both sides by
    branch and only a branch's name (or "both") answers it."""
    return current if current and current in early.branches else None


def _there(early: Early, here: str | None) -> str | None:
    if here is None:
        return None
    return early.other if here == early.raised_on else early.raised_on


def relative_words(quote: str) -> bool:
    """The words name a side relative to the reader ("this one", "mine", "theirs")."""
    return bool(_pattern(_RELATIVE).search(quote) or _pattern(_OTHER).search(quote))


def named_keys(early: Early, quote: str, current: str | None = None) -> set[str]:
    """The options the owner's words name: a branch (its name; on one of the two branches
    also "keep this one" for that branch and "theirs" for the other one) or ``both``."""
    here = _here(early, current)
    there = _there(early, here)
    found: set[str] = set()
    for branch in early.branches:
        if branch and _pattern([branch]).search(quote):
            found.add(branch)
    if here is not None and _pattern(_RELATIVE).search(quote):
        found.add(here)
    if there is not None and _pattern(_OTHER).search(quote):
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
    if wanted in ("both", "combined", "both, combined"):
        return BOTH
    mine = wanted in ("ours", "mine", "this", "this one", "here")
    other = wanted in ("theirs", "other", "the other one", "there")
    if (mine or other) and here is None:
        raise AnswerError(f"plumb: on {current or 'this checkout'}, which is neither side, "
                          f"--take names a branch: {early.raised_on}, {early.other} or both")
    if mine:
        return str(here)
    if other:
        return str(_there(early, here))
    raise AnswerError(f"plumb: --take is {early.raised_on}, {early.other} or both")


def say_line(early: Early, current: str | None = None) -> str:
    """The card's answer line from the session's point of view: on one of the two branches
    "keep this one" names it; on any other branch both are named by branch."""
    here = _here(early, current)
    if here is None:
        return text.EARLY_CARD_SAY_NAMED.format(a=early.raised_on, b=early.other).strip()
    return text.EARLY_CARD_SAY.format(branch=_there(early, here)).strip()


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
        raise NoEarly(text.NO_CONFLICTS)
    if record_id:
        matches = [e for e in candidates if e.record == record_id]
    else:
        words = set(re.findall(r"\w+", wanted.lower()))
        matches = [e for e in candidates if words & set(
            re.findall(r"\w+", str(index[e.record].title if e.record in index else "").lower()))]
    if not matches and wanted:
        raise NoEarly(f"plumb: which conflict do you mean? "
                      f"{', '.join(e.dec for e in candidates)}")
    if len(matches) > 1:
        statuses = core.status([e.dec for e in matches])
        open_ = [e for e in matches if statuses[e.dec].confirmation != "confirmed"]
        matches = open_ if len(open_) == 1 else matches
    if len(matches) == 1:
        return matches[0]
    if not wanted and len(candidates) == 1:
        return candidates[0]
    raise AnswerError(f"plumb: which conflict do you mean? {', '.join(e.dec for e in candidates)}")


def shown_cards(core: Any, ref: str) -> list[Any]:
    """The early conflict cards the owner was shown (the stated set of the last reply) that
    ``ref`` names (a record ID, its title's words, or nothing for the only one) and that no
    decision holds yet: a card the clarify read-back showed before anything was written."""
    from plumb.awareness import early as early_mod

    data = _stated(core, "")
    items = [e for e in data.get("early") or [] if isinstance(e, Mapping)]
    if not items:
        return []
    cards = early_mod.requested(core.paths.session)
    index = core.index()
    wanted = " ".join(ref.split())
    words = set(re.findall(r"\w+", wanted.lower()))
    decided = {e.record for e in early_decisions(index)}
    out = []
    for item in items:
        conflict = early_mod.from_stated(item, cards)
        if conflict is None or conflict.record not in index or conflict.record in decided:
            continue
        title = set(re.findall(r"\w+", index[conflict.record].title.lower()))
        if not wanted or wanted.upper() == conflict.record or words & title:
            out.append(conflict)
    return out


def raise_shown(core: Any, ref: str) -> Early | None:
    """The one card shown and not decided yet that ``ref`` names, raised now as its
    decision (``early.raise_conflicts``, noted in this branch's claim), so the owner's
    answer to the card is recorded once like any other (R17: every card the owner sees has
    a decision the answer records). None when no card, or several, match."""
    from plumb.awareness import early as early_mod
    from plumb.awareness import inflight

    found = shown_cards(core, ref)
    if len(found) != 1:
        return None
    entries = early_mod.raise_conflicts(core, found, intent=None)
    if not entries:
        return None
    try:
        inflight.record_claim(core, records={}, summary=found[0].title, intent=None,
                              conflicts=entries)
    except Exception:  # noqa: BLE001 - the stop hook's sync carries it later
        pass
    return early_of(core.index().get(str(entries[0]["dec"])))


def find_or_raise(core: Any, ref: str) -> Early:
    """``find``, else the card the owner was shown and no decision holds yet
    (``raise_shown``)."""
    try:
        return find(core, ref)
    except NoEarly:
        raised = raise_shown(core, ref)
        if raised is None:
            raise
        return raised


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
    block: dict[str, Any] = {"record": early.record, "raised_on": early.raised_on,
                             "other": early.other, "hashes": _hashes(core, early, current)}
    if early.texts:
        block["texts"] = dict(early.texts)
    rewrite(core, record, {"chosen": chosen, "alternatives": alternatives, FIELD: block})
    from plumb.approvals import approval_items

    payload: dict[str, Any] = {
        "records": approval_items(core, [early.dec]), "by": by,
        "prompt_digest": None, "quote": None, "quote_digest": None, "affirmation": None,
        "stated_set": None, "note": note or "the owner's answer to the early conflict card",
        "choice": {"take": key, "option": chosen, "names": list(names),
                   "here": _here(early, current),
                   "there": _there(early, _here(early, current))}}
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

    early = find_or_raise(core, ref)
    current = _current(core)
    try:
        entry = owner_prompt(core, prompt)
    except Refused as exc:
        raise AnswerRefused(str(exc)) from exc
    said = normalize_text(quote)
    if not said or not quote_in_prompt(said, normalize_text(str(entry.get("text") or ""))):
        raise AnswerRefused("the quote is not a verbatim part of that prompt (whole words)")
    if _here(early, current) is None and relative_words(said):
        raise AnswerRefused(
            f"on {current or 'this checkout'}, which is neither {early.raised_on} nor "
            f"{early.other}, words like \"this one\" or \"theirs\" name no version; the "
            "owner answers with a branch's name ("
            + say_line(early, current).removeprefix("Say: ") + ")")
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

    early = find_or_raise(core, ref)
    key = normalize_take(early, take, _current(core))
    require_owner("conflict choose", f"Keep {option(key)} of {early.record}?")
    return early, record_answer(core, early, key, by="owner")


def answer_line(core: Any, early: Early, key: str) -> str:
    title = core.index()[early.record].title if early.record in core.index() else ""
    return text.EARLY_ANSWERED.format(id=early.record, title=title, chosen=option(key))


@dataclass(frozen=True)
class Superseded:
    """A record of this checkout that still holds another version than the one the owner
    chose in a confirmed early decision (``dec``)."""

    record: str
    title: str
    dec: str
    chosen: str          # the owner's answer, branch-neutral ("feat-x's version")
    theirs: str          # the chosen version's words
    ours: str            # this checkout's words
    hash: str            # this checkout's version of the record


def _differs(record: Any, winner_hash: str, winner_text: str) -> bool:
    from plumb.awareness.inflight import record_entry

    if winner_hash and record.hash == winner_hash:
        return False
    if winner_text:
        return record_entry(record)["text"] != " ".join(winner_text.split())
    return bool(winner_hash)


def superseded(core: Any) -> dict[str, Superseded]:
    """``{record: Superseded}``: every record of this checkout whose words differ from the
    version the owner chose in a CONFIRMED early decision, the ONE place the losing lane is
    found (R17: the answer is recorded once and both lanes build on it). Two sources: the
    early decisions this checkout holds (it raised the question, or merged it), and the
    answers other branches carry in their claims for this branch's work
    (``inflight.sync_decisions``). An answer naming this branch's own version, "both", or
    words naming no branch supersedes nothing; a record that matches the chosen version
    (same hash or same words) is no longer named. No git process (hook path)."""
    from plumb.awareness import inflight

    index = core.index()
    current = _current(core)
    try:
        my_branch, claims = inflight.others(core)
    except Exception:  # noqa: BLE001 - the register is advisory here
        my_branch, claims = current, []

    def claimed(branch: str, record_id: str) -> Mapping[str, Any]:
        for claim in claims:
            entry = (claim.get("records") or {}).get(record_id)
            if claim.get("branch") == branch and isinstance(entry, Mapping):
                return entry
        return {}

    out: dict[str, Superseded] = {}
    earlies = early_decisions(index)
    statuses = core.status([e.dec for e in earlies]) if earlies else {}
    for early in earlies:
        status = statuses.get(early.dec)
        key = early.chosen_key
        record = index.get(early.record)
        if (status is None or status.confirmation != "confirmed" or key in (None, BOTH)
                or key == current or record is None):
            continue
        entry = claimed(key, early.record)
        winner_text = str(entry.get("text") or early.texts.get(key) or "")
        winner_hash = str(entry.get("hash") or early.hashes.get(key) or "")
        if _differs(record, winner_hash, winner_text):
            out[record.id] = Superseded(
                record=record.id, title=record.title, dec=early.dec, chosen=option(key),
                theirs=winner_text, ours=inflight.record_entry(record)["text"],
                hash=record.hash)
    for claim in claims:
        for conflict in claim.get("conflicts") or []:
            record = index.get(str(conflict.get("record") or ""))
            if (record is None or record.id in out or conflict.get("state") != "confirmed"
                    or conflict.get("branch") != my_branch):
                continue
            chosen = inflight.neutral_chosen(str(conflict.get("chosen") or ""),
                                             str(claim.get("branch") or ""))
            match = _VERSION.fullmatch(chosen)
            winner = match.group(1) if match else None
            if not winner or winner == my_branch:
                continue
            entry = claimed(winner, record.id)
            if _differs(record, str(entry.get("hash") or ""), str(entry.get("text") or "")):
                out[record.id] = Superseded(
                    record=record.id, title=record.title, dec=str(conflict.get("dec") or ""),
                    chosen=chosen, theirs=str(entry.get("text") or ""),
                    ours=inflight.record_entry(record)["text"], hash=record.hash)
    return out


def superseded_line(item: Superseded) -> str:
    return text.EARLY_SUPERSEDED.format(id=item.record, title=item.title,
                                        ours=_short(item.ours), chosen=item.chosen,
                                        theirs=_short(item.theirs) or "its words")


def _short(words: str, width: int = 120) -> str:
    words = " ".join(str(words or "").split())
    return words if len(words) <= width else words[: width - 3].rstrip() + "..."


def plain_relay_problem(core: Any, ids: Iterable[str], quote: str) -> str | None:
    """Plain ``plumb relay`` of an early decision: refused when the owner's words name
    another version than the one the decision holds (their pick goes through ``conflict
    relay``, which records it); an "ok" naming no version confirms what was shown. And
    any relayed "ok" of a record that still holds the version the owner turned down in a
    confirmed early decision (``superseded``) is refused, naming that answer: an "ok"
    never confirms the rejected words over the owner's recorded choice."""
    ids = list(ids)
    try:
        lost = superseded(core)
    except Exception:  # noqa: BLE001 - the pick check below still runs
        lost = {}
    for record_id in ids:
        item = lost.get(record_id)
        if item is not None:
            return text.EARLY_SUPERSEDED_RELAY.format(
                id=item.record, title=item.title, dec=item.dec, chosen=item.chosen,
                theirs=_short(item.theirs) or "its words")
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
    """The early conflict card of an unanswered decision, the one place every surface
    builds it (/plumb conflicts, the stop hook's card): each branch's version from its live
    claim, else the words the decision pinned when it asked. On one of the two branches the
    session's own side is "this work" (this checkout's version); on any other branch (the
    default branch after one side merged, which is neither) both sides are labelled by
    branch and never by this checkout's content, so "this one" can never point at the
    opposite version."""
    from plumb.awareness.early import EarlyConflict

    index = core.index()
    current = _current(core)
    here = _here(early, current)
    live: dict[str, str] = {}
    try:
        from plumb.awareness import inflight

        _me, claims = inflight.others(core, allow_git=True)
        for claim in claims:
            entry = (claim.get("records") or {}).get(early.record)
            branch = str(claim.get("branch") or "")
            if branch in early.branches and isinstance(entry, Mapping) and entry.get("text"):
                live[branch] = str(entry["text"])
    except Exception:  # noqa: BLE001 - the decision's own words still name both versions
        live = {}
    question = str(index[early.dec].fields.get("question") or "") if early.dec in index else ""

    def words(branch: str) -> str:
        return live.get(branch) or early.texts.get(branch) or question

    record = index.get(early.record)
    title = record.title if record is not None else ""
    if here is None:
        return EarlyConflict(record=early.record, title=title, branch=early.raised_on,
                             claim="", theirs=words(early.raised_on), ours=words(early.other),
                             ours_label=early.other)
    there = str(_there(early, here))
    ours = (str(record.fields.get("statement") or record.title) if record is not None
            else words(here))
    return EarlyConflict(record=early.record, title=title, branch=there, claim="",
                         theirs=words(there), ours=ours)


def merge_conflict_of(core: Any, ref: str) -> str | None:
    """The open merge-time conflict (``IC-###``) that asks the question of the early
    decision ``ref`` names (the decision or its record): when a merge left one on the same
    record, its card is the one question shown, and its answer answers the decision
    (``answer_from_conflict``)."""
    index = core.index()
    wanted = " ".join(ref.split()).upper()
    early = early_of(index.get(wanted))
    record_id = early.record if early is not None else wanted
    if record_id not in index or (early is None and not early_decisions(index, record_id)):
        return None
    block = index[record_id].fields.get("conflict")
    if isinstance(block, Mapping) and block.get("id"):
        return str(block["id"])
    return None
