"""The intent card's data and a plain rendering (R9; sp2 5.1, 11.1 ``card_data``).

PRESENT owns how cards are shown (``plumb.present.render``); CAPTURE provides the data and
this plain text form, which ``plumb capture`` prints for the agent to put in its reply:

    ▸ Intent  INT-016 "add multiply"   (proposed — say "ok" to confirm)
      Will: ... · Won't: ... · Assumed: ...
      Examples  EX-1 ...  EX-2 ...   (proposed)
      Tests  ...  ✓ passing
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.contracts import IntentCardData, Record, example_groups

if TYPE_CHECKING:
    from plumb.api import Core

WIDTH = 60
LABELS = {"owner": "you", "agent-relayed": "you (relayed)", "auto-jev": "JEV",
          "import": "import", "owner-words": "you", "settled": "settled from your words"}


def _flat(value: Any) -> str:
    return " ".join(str(value or "").split())


def _list(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raw = [raw]
    out = []
    for item in raw:
        text = item.get("text") or item.get("statement") if isinstance(item, Mapping) else item
        if _flat(text):
            out.append(_flat(text))
    return tuple(out)


def _clip(text: str, width: int = WIDTH) -> str:
    text = _flat(text)
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def example_text(example: Any) -> str:
    given, when, then = (getattr(example, k, "") or "" for k in ("given", "when", "then"))
    if given or when or then:
        return f"given {given}, when {when}, then {then}"
    return str(getattr(example, "criterion", "") or "")


def _derived(index: Mapping[str, Record], intent_id: str) -> list[Record]:
    return [r for r in index.values() if any(
        link.kind == "derives_from" and link.target.record == intent_id for link in r.links)]


def _test_states(core: Core, ends: Sequence[str]) -> dict[str, str]:
    """``{test end: passing|failing|not run}`` from VERIFY when built, else ``not run``."""
    states = dict.fromkeys(ends, "not run")
    if not ends:
        return states
    try:
        from plumb.verify import open_verify

        verify = open_verify(core)
        nodes = verify.tests_for(ends)
        flat = sorted({n for found in nodes.values() for n in found})
        evidence = verify.evidence(flat) if flat else {}
    except Exception:  # noqa: BLE001 - optional lane; the card degrades
        return states
    for end, found in nodes.items():
        kinds = {evidence[n].state for n in found if n in evidence}
        if kinds & {"fresh-fail"}:
            states[end] = "failing"
        elif kinds and kinds <= {"fresh-pass", "flaky-pass"}:
            states[end] = "passing"
    return states


def data_for(core: Core, record: Record, statuses: Mapping[str, Any],
             labels: Mapping[str, str] | None = None) -> IntentCardData:
    index = core.index()
    status = statuses.get(record.id)
    state = status.confirmation if status is not None else "proposed"
    confirmed_by = None
    if status is not None and status.approved_by and state == "confirmed":
        confirmed_by = LABELS.get(str(status.approved_by), str(status.approved_by))
    members: list[Record] = [record]
    if record.kind == "intent":
        members += [r for r in _derived(index, record.id) if r.kind == "requirement"]
    examples: list[tuple[str, str, str]] = []
    ends: list[str] = []
    for member in members:
        for example in member.examples:
            examples.append((member.id, example.id, _clip(example_text(example))))
        for link in member.links:
            if link.kind == "verified_by":
                end = link.target.test or link.target.path
                if end and end not in ends:
                    ends.append(end)
    decisions = tuple(sorted(r.id for r in index.values() if r.kind == "decision" and any(
        link.kind in ("decides", "derives_from") and link.target.record == record.id
        for link in r.links)))
    tests = _test_states(core, ends)
    fields = record.fields
    return IntentCardData(
        id=record.id, title=record.title, state=state, confirmed_by=confirmed_by,
        label=(labels or {}).get(record.id, ""),
        quote=_flat(fields.get("quote") or fields.get("statement") or ""),
        will=_list(fields.get("will")), wont=_list(fields.get("wont")),
        assumed=_list(fields.get("assumptions")), examples=tuple(examples),
        tests=tuple(tests.items()), decisions=decisions,
        member_states=_member_states(members, statuses),
        say=early_say(core, record) if record.kind == "decision" else "")


def _member_states(members: Sequence[Record], statuses: Mapping[str, Any]
                   ) -> tuple[tuple[str, str], ...]:
    """Each card member's own confirmation state (``IntentCardData.member_states``)."""
    out = []
    for member in members:
        status = statuses.get(member.id)
        out.append((member.id, status.confirmation if status is not None else "proposed"))
    return tuple(out)


def early_say(core: Core, record: Record) -> str:
    from plumb.present.cards import early_say as say

    return say(core, record)


def card_data(core: Core, ids: Iterable[str]) -> list[IntentCardData]:
    index = core.index()
    wanted = [i for i in dict.fromkeys(ids) if i in index]
    if not wanted:
        return []
    statuses = core.status()
    from plumb.capture.confirmations import labels_for

    labels = labels_for(core, wanted)
    return [data_for(core, index[i], statuses, labels) for i in wanted]


def _state_text(data: IntentCardData) -> str:
    if data.state == "confirmed":
        text = f"confirmed by {data.confirmed_by or 'you'}"
        return text + (f", {data.label}" if data.label else "")
    if getattr(data, "say", ""):
        from plumb.present.owner_text import EARLY_DEC_STATE

        return EARLY_DEC_STATE.format(say=data.say)
    if data.state == "unconfirmed-edit":
        return "edited since you confirmed it — say \"ok\" to confirm"
    return "proposed — say \"ok\" to confirm"


def render(cards: Sequence[IntentCardData], *, ascii_only: bool = False) -> str:
    """The plain intent card text, one block per card."""
    arrow, dot, tick, cross = (">", "|", "ok", "x") if ascii_only else ("▸", "·", "✓", "✗")
    blocks: list[str] = []
    for data in cards:
        kind = {"INT": "Intent", "SR": "Requirement", "DEC": "Decision"}.get(
            data.id.split("-")[0], "Record")
        lines = [f"{arrow} {kind}  {data.id} \"{_clip(data.title, 50)}\"   "
                 f"({_state_text(data)})"]
        parts = []
        if data.will:
            parts.append("Will: " + "; ".join(data.will))
        if data.wont:
            parts.append("Won't: " + "; ".join(data.wont))
        if data.assumed:
            parts.append("Assumed: " + "; ".join(data.assumed))
        if parts:
            lines.append("  " + f" {dot} ".join(parts))
        if data.examples:
            shown = "  ".join(
                "  ".join(f"{ex} {text}" if sr == data.id else f"{sr}/{ex} {text}"
                          for sr, ex, text in group) + f"   ({state})"
                for state, group in example_groups(data, 4))
            more = f"  +{len(data.examples) - 4} more" if len(data.examples) > 4 else ""
            lines.append(f"  Examples  {shown}{more}")
        if data.decisions:
            lines.append("  Decisions  " + ", ".join(data.decisions))
        if data.tests:
            marks = {"passing": f"{tick} passing", "failing": f"{cross} failing"}
            lines.append("  Tests  " + "  ".join(f"{end} {marks.get(state, state)}"
                                                 for end, state in data.tests[:4]))
        blocks.append("\n".join(lines))
    return "\n".join(blocks)
