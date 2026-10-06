"""``plumb confirm`` (``/plumb confirm``): prepare a confirmation the owner's own words then
give (sp5 6.3, SR-065; rulings R1, R2, R8 A, R9).

It never writes an approval. It shows records as intent cards (the "shown" form: each card
shows its record in full) and puts them in the stated set, so the owner's next affirming
prompt can confirm exactly them through ``plumb relay`` with the R2 checks:

- no words: CAPTURE's triage offer (the low-risk group, every ID named, pinned in the stated
  set as a group) and each riskier record as a card; without CAPTURE, the proposed records
  as cards;
- plain words: the records they resolve to, as cards;
- IDs typed by the owner (``/plumb confirm SR-034``): the prompt itself names the IDs and
  affirms, so the agent relays it at once; the cards still show what it confirms.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

HEADER = ("plumb confirm: this approves nothing; the owner's own \"ok\" (or \"ok SR-034\") "
          "on the next prompt confirms what is shown below")


def _proposed(core: Any) -> list[str]:
    from plumb.query import superseded_ids

    index = core.index()
    superseded = superseded_ids(index)
    statuses = core.status()
    order = {"INT": 0, "SR": 1, "DEC": 2, "FEAT": 3, "NC": 4}
    ids = [i for i, s in statuses.items() if s.confirmation != "confirmed"
           and i not in superseded]
    return sorted(ids, key=lambda i: (order.get(i.split("-")[0], 9),
                                      int(i.rsplit("-", 1)[-1])))


def _triage(core: Any) -> Any:
    try:
        from plumb.capture import api
    except ImportError:
        return None
    try:
        view = api.triage(core, None)
    except Exception:  # noqa: BLE001 - an advisory lane never fails the command
        return None
    return view if getattr(view, "available", False) else None


def _group(view: Any) -> dict[str, Any] | None:
    try:
        from plumb.capture import api

        return api.stated_group(view)
    except Exception:  # noqa: BLE001
        return None


def write_stated(core: Any, shown: Sequence[str], group: dict[str, Any] | None) -> None:
    """The stated set of this reply: the carded records, ``shown`` and ``via: confirm``
    (the stop hook keeps them for the owner's next prompt)."""
    from plumb.hosts.claude_code.hookio import write_json_atomic
    from plumb.normalize import utc_now

    index = core.index()
    data: dict[str, Any] = {"at": utc_now(), "session": None, "reply_after_prompt": None,
                            "via": "confirm",
                            "records": [{"id": i, "hash": index[i].hash, "shown": True,
                                         "via": "confirm"} for i in shown]}
    if group is not None:
        data["groups"] = [group]
    write_json_atomic(core.root / ".plumb" / "session" / "stated.json", data)


def confirm(core: Any, ids: Sequence[str] | None = None, *, limit: int = 5,
            named: bool = False) -> dict[str, Any]:
    """The confirmation flow's lines and what it put in the stated set."""
    from plumb.present.cards import card_data
    from plumb.present.render import intent_card

    index = core.index()
    present = getattr(core.config, "present", None)
    ascii_only = bool(getattr(present, "ascii", False))
    lines = [HEADER]
    group = None
    offer = None
    if ids is None:
        view = _triage(core)
        if view is not None:
            offer = getattr(view, "offer", None)
            group = _group(view) if offer else None
            candidates = [item.id for item in getattr(view, "individual", ())]
        else:
            candidates = _proposed(core)
    else:
        candidates = [i for i in dict.fromkeys(ids) if i in index]
    if offer:
        lines.append(str(offer))
    statuses = core.status(candidates) if candidates else {}
    wanted = [i for i in candidates if ids is not None
              or statuses[i].confirmation != "confirmed"]
    shown = wanted[:max(limit, 0)]
    for data in card_data(core, shown):
        lines.extend(intent_card(data, mode="full", ascii=ascii_only))
    rest = wanted[len(shown):]
    if rest:
        more = ", ".join(rest[:8]) + (f" +{len(rest) - 8} more" if len(rest) > 8 else "")
        lines.append(f"plumb: {len(rest)} more await you, not shown: {more} (plumb confirm "
                     "<words or IDs> shows them; a confirmation must name them)")
    if not shown and not offer:
        lines.append("nothing awaits your confirmation" if ids is None else
                     "nothing to confirm in those words")
    if named and shown:
        lines.append(f"the owner's words name {', '.join(shown)}: relay them at once with "
                     f"plumb relay {' '.join(shown)} --prompt <digest> --quote \"<the "
                     "owner's exact words>\"")
    write_stated(core, shown, group)
    return {"lines": lines, "shown": shown, "not_shown": rest, "group": group,
            "approved": []}
