"""Card data, and which cards the end-of-turn summary shows (sp5 4.2, 4.3; SR-061, SR-062).

The intent card appears only when it matters:

1. a new or changed intent awaits the owner (an INT or SR edited this turn, still proposed);
2. a trigger: a real intent change (trigger 1, a flag of this turn's prompt), an unconfirmed
   decision that matters or an escalated set awaiting approval (trigger 2), a regression
   (trigger 3);
3. the owner asked (``plumb explain``, ``review``, ``confirm``).

``present.card`` sets the rest: ``full`` adds a card for every record the turn touched,
``compact`` (default) shows only the cases above, ``off`` shows only the triggers. A card shows
its record in full, so a carded record counts as "shown" in the stated set; at most
``hooks.summary_proposed_cap`` non-trigger cards appear, the rest are named.

Card data is built here, in full (nothing clipped), from the records: CAPTURE's own card data
clips examples for the agent's reply, which would not count as shown.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.contracts import IntentCardData

BY = {"owner": "you", "agent-relayed": "you (relayed)", "auto-jev": "JEV", "import": "import"}
INTENT_FILE = "intent.json"


def _flat(value: Any) -> str:
    if isinstance(value, list):
        value = " / ".join(map(str, value))
    return " ".join(str(value or "").split())


def _items(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raw = [raw]
    out = []
    for item in raw:
        text = (item.get("text") or item.get("statement")) if isinstance(item, Mapping) \
            else item
        if _flat(text):
            out.append(_flat(text))
    return tuple(out)


def example_text(example: Any) -> str:
    if example.given or example.when or example.then:
        return f"given {_flat(example.given)}, when {_flat(example.when)}, then " \
               f"{_flat(example.then)}"
    return _flat(example.criterion)


def evidence_state(items: Iterable[Any]) -> str:
    """``passing``, ``regression``, ``not yet passing`` or ``not run`` for one test end."""
    states = [(e.state, bool(getattr(e, "regression", False))) for e in items]
    if not states:
        return "not run"
    if any(regression for _, regression in states):
        return "regression"
    if any(state == "fresh-fail" for state, _ in states):
        return "not yet passing"
    if all(state in ("fresh-pass", "flaky-pass") for state, _ in states):
        return "passing"
    return "not run"


def test_states(core: Any, ends: Sequence[str], *, evidence: Mapping[str, Any] | None = None,
                verify: Any = None) -> dict[str, str]:
    """``{test end: state}``: from ``evidence`` (the stop hook's selection) when given, else
    from VERIFY when it is built; ``not run`` when nothing is known."""
    out = dict.fromkeys(ends, "not run")
    if not ends:
        return out
    if evidence is not None:
        for end in ends:
            out[end] = evidence_state(e for node, e in evidence.items()
                                      if node == end or node.startswith(end + "::"))
        return out
    if verify is None:
        try:
            from plumb.verify import open_verify

            verify = open_verify(core)
        except Exception:  # noqa: BLE001 - VERIFY is optional for a card
            return out
    try:
        nodes = verify.tests_for(list(ends))
        flat = sorted({n for found in nodes.values() for n in found})
        found_evidence = verify.evidence(flat) if flat else {}
    except Exception:  # noqa: BLE001
        return out
    for end in ends:
        out[end] = evidence_state(found_evidence[n] for n in nodes.get(end, ())
                                  if n in found_evidence)
    return out


def _label(core: Any, record_id: str) -> str:
    """"self-recorded message" and the like, from CAPTURE when built (R13 Q4)."""
    try:
        from plumb.capture.api import confirmation_label
    except ImportError:
        return ""
    try:
        label = str(confirmation_label(core, record_id) or "")
    except Exception:  # noqa: BLE001
        return ""
    # CAPTURE's label repeats "confirmed by ..."; the card keeps only the extra words
    return label.split(", ", 1)[1] if label.startswith("confirmed by") and ", " in label \
        else ("" if label.startswith("confirmed by") else label)


def confirmed_label(core: Any, record_id: str, status: Any) -> str | None:
    """Who confirmed a confirmed record, in the owner's terms: "confirmed by you", "confirmed
    by you (relayed)", "confirmed by JEV", with CAPTURE's extra words such as "self-recorded
    message" (R8 B, R13 Q4); None for a record that is not confirmed. The one label every
    surface that states a record's confirmation uses: the cards, ``plumb show``, ``plumb
    explain`` and the vault."""
    if status is None or status.confirmation != "confirmed" or not status.approved_by:
        return None
    who = BY.get(str(status.approved_by), str(status.approved_by))
    extra = _label(core, record_id)
    return f"confirmed by {who}" + (f", {extra}" if extra else "")


def card_for(core: Any, record: Any, statuses: Mapping[str, Any], *,
             evidence: Mapping[str, Any] | None = None, verify: Any = None) -> IntentCardData:
    """One record's card data, in full."""
    index = core.index()
    status = statuses.get(record.id)
    state = status.confirmation if status is not None else "proposed"
    confirmed_by = None
    label = ""
    if status is not None and state == "confirmed" and status.approved_by:
        confirmed_by = BY.get(str(status.approved_by), str(status.approved_by))
        label = _label(core, record.id)
    fields = record.fields
    members = [record]
    if record.kind == "intent":
        members += [r for r in index.values() if r.kind == "requirement" and any(
            link.kind == "derives_from" and link.target.record == record.id
            for link in r.links)]
    examples = tuple((m.id, ex.id, example_text(ex)) for m in members for ex in m.examples)
    ends: list[str] = []
    for member in members:
        for link in member.links:
            end = link.target.test or link.target.path if link.kind == "verified_by" else None
            if end and end not in ends:
                ends.append(end)
    tests = test_states(core, ends, evidence=evidence, verify=verify) if ends else {}
    decisions = tuple(sorted(r.id for r in index.values() if r.kind == "decision" and any(
        link.kind == "decides" and link.target.record == record.id for link in r.links)))
    statement = ""
    assumed = _items(fields.get("assumptions"))
    alternatives: tuple[str, ...] = ()
    if record.kind == "requirement":
        statement = _flat(fields.get("statement") or record.title)
    elif record.kind == "intent":
        statement = _flat(fields.get("readback"))
    elif record.kind == "decision":
        chosen = _flat(fields.get("chosen"))
        assumed = (chosen,) if chosen else ()
        alternatives = _items(fields.get("alternatives"))
    return IntentCardData(
        id=record.id, title=_flat(record.title), state=state, confirmed_by=confirmed_by,
        label=label, quote=_flat(fields.get("quote")) if record.kind == "intent" else "",
        will=_items(fields.get("will")), wont=_items(fields.get("wont")), assumed=assumed,
        examples=examples, tests=tuple(tests.items()), decisions=decisions, kind=record.kind,
        statement=statement, alternatives=alternatives)


def card_data(core: Any, ids: Iterable[str], *, evidence: Mapping[str, Any] | None = None,
              verify: Any = None) -> list[IntentCardData]:
    index = core.index()
    wanted = [i for i in dict.fromkeys(ids) if i in index]
    if not wanted:
        return []
    statuses = core.status(wanted)
    return [card_for(core, index[i], statuses, evidence=evidence, verify=verify)
            for i in wanted]


# --------------------------------------------------------------------------- the session


def session_intent(core: Any, index: Mapping[str, Any], touched: Sequence[str],
                   session_path: Path) -> str:
    """The intent this session works on in plain words (sp5 4.1): the most recent INT touched
    this turn, else the INT a touched record derives from, else the last one named in this
    session. Remembered in ``<session>/intent.json``."""
    intents = [i for i in touched if i in index and index[i].kind == "intent"]
    if not intents:
        for record_id in touched:
            record = index.get(record_id)
            for link in getattr(record, "links", ()):
                target = link.target.record
                if link.kind == "derives_from" and target in index \
                        and index[target].kind == "intent":
                    intents.append(target)
    path = Path(session_path) / INTENT_FILE
    if intents:
        chosen = max(intents, key=lambda i: int(i.rsplit("-", 1)[-1]))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"id": chosen}), encoding="utf-8")
        except OSError:
            pass
    else:
        try:
            chosen = str(json.loads(path.read_text(encoding="utf-8")).get("id") or "")
        except (OSError, ValueError, AttributeError):
            return ""
    record = index.get(chosen)
    if record is None:
        return ""
    title = _flat(record.title) or _flat(record.fields.get("readback")).split(",")[0]
    return title


# --------------------------------------------------------------------------- the stop cards


@dataclass
class Plan:
    """The cards of one summary: trigger cards first, then the others up to the cap."""

    cards: list[tuple[str, str | None]] = field(default_factory=list)  # (id, why)
    loose: list[str] = field(default_factory=list)      # trigger lines with no record
    cut: list[str] = field(default_factory=list)        # named, not shown

    @property
    def shown(self) -> list[str]:
        return [i for i, _ in self.cards]


def regression_owners(index: Mapping[str, Any], node: str) -> list[str]:
    """The requirements a failing node verifies (its ``verified_by`` ends)."""
    out = []
    for record_id, record in sorted(index.items()):
        if record.kind != "requirement":
            continue
        for link in record.links:
            end = link.target.test or link.target.path if link.kind == "verified_by" else None
            if end and (node == end or node.startswith(end + "::")):
                out.append(record_id)
                break
    return out


def plan_cards(*, mode: str, index: Mapping[str, Any], statuses: Mapping[str, Any],
               stated: Sequence[str], decisions: Sequence[str], regressions: Sequence[str],
               flagged: Sequence[str], escalated: Sequence[str], touched: Sequence[str],
               cap: int) -> Plan:
    """Which cards the summary shows in ``mode`` (sp5 4.2, 4.3)."""
    plan = Plan()
    seen: set[str] = set()

    def add(record_id: str, why: str | None) -> None:
        if record_id in index and record_id not in seen:
            seen.add(record_id)
            plan.cards.append((record_id, why))

    for node in regressions:
        owners = regression_owners(index, node)
        for owner in owners:
            add(owner, "Regression")
        if not owners:
            plan.loose.append(f"▸ Regression  {node}   (it passed before and fails now)")
    for record_id in decisions:
        add(record_id, "Question")
    for record_id in escalated:
        add(record_id, "Question")
    for record_id in flagged:
        add(record_id, "Intent change")
    if mode == "off":
        return plan
    others = [i for i in stated if i not in seen]
    if mode == "full":
        others += [i for i in touched if i not in seen and i not in others
                   and index.get(i) is not None and index[i].kind in ("intent", "requirement")]
    room = max(cap, 0)
    for record_id in others:
        if room > 0:
            add(record_id, None)
            room -= 1
        elif record_id not in seen:
            plan.cut.append(record_id)
    return plan


def card_mode(config: Any) -> str:
    """``present.card``: ``full``, ``compact`` (default) or ``off``. YAML reads a bare
    ``off`` as false, so false means off."""
    value = getattr(getattr(config, "present", None), "card", "compact")
    if value is False or str(value).strip().lower() in ("off", "false", "no", "none"):
        return "off"
    value = str(value).strip().lower()
    return value if value in ("full", "compact") else "compact"
