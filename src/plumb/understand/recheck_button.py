"""Re-check of an ``approval`` with ``by: owner, via: button`` (sp7-realign-sp8 C6; SR-086
EX-9, SR-112 EX-7). Such an approval confirms only when, in the log it is in, before it:

- the session registered its panel (``mod-hello``, no marker) with the key digest the approval
  carries (and, where the session folder exists, ``mod.json`` holds that digest too);
- the offer it names was drawn in that session (an ``offer`` entry, no marker, same key digest)
  for this card and question, naming this record at this hash (or, for a request's read-back,
  listing it among its ``records``).

The marker is checked by the caller (``confirm.entry_problem``: an owner entry carries none). An
approval written any other way (by hand, without a drawn offer, for another record or version)
confirms nothing, and ``plumb validate`` reports it. Tamper-evident, not tamper-proof (SP7 5.7).
It is called with no log context by ``confirm.entry_problem`` when no Core is given, so it
then reads the log of the repository the process runs in (``ambient_core``)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plumb.contracts import LogEntry

_INDEX: dict[int, tuple[int, str, Any]] = {}


class _Index:
    """What the re-check reads from a log, built once per events list."""

    def __init__(self, events: list[LogEntry]) -> None:
        from plumb.mod.offers import OFFER_KIND
        from plumb.mod.session import HELLO_KIND

        self.position: dict[str, int] = {}
        # every registration of a session (a resumed one registers again, with a new key) and
        # every drawing of an offer (drawn again under that new key)
        self.hello: dict[str, list[tuple[int, str]]] = {}
        self.offers: dict[tuple[str, str], list[tuple[int, Mapping[str, Any]]]] = {}
        for n, entry in enumerate(events):
            self.position.setdefault(entry.digest, n)
            if entry.marker != "none":
                continue
            payload = entry.payload
            session = str(payload.get("session") or "")
            if entry.kind == HELLO_KIND:
                key = str(payload.get("key_digest") or "")
                self.hello.setdefault(session, []).append((n, key))
            elif entry.kind == OFFER_KIND:
                drawn = self.offers.setdefault((session, str(payload.get("offer") or "")), [])
                drawn.append((n, payload))


def _index_of(events: list[LogEntry]) -> _Index:
    last = events[-1].digest if events else ""
    held = _INDEX.get(id(events))
    if held is not None and held[0] == len(events) and held[1] == last:
        return held[2]
    built = _Index(events)
    _INDEX.clear()
    _INDEX[id(events)] = (len(events), last, built)
    return built


_AMBIENT: dict[str, tuple[Any, Any]] = {}


def ambient_core() -> Any:
    """The Core of the repository the process runs in, for a re-check called with no log
    context. Kept while the events do not change; None when there is no repository here."""
    try:
        from pathlib import Path

        from plumb.api import open_core
        from plumb.log import stream_stamp
        from plumb.paths import PlumbPaths, find_root

        root = find_root(Path.cwd())
        stamp = stream_stamp(PlumbPaths(root), "events")
        held = _AMBIENT.get(str(root))
        if held is not None and held[0] == stamp:
            return held[1]
        core = open_core(root)
        _AMBIENT[str(root)] = (stamp, core)
        return core
    except Exception:  # noqa: BLE001 - no repository here: the entry is refused, not trusted
        return None


def problem(entry: LogEntry, core: Any) -> str | None:
    """Why the button approval ``entry`` fails its re-check, or None."""
    payload = entry.payload
    session, offer = str(payload.get("session") or ""), str(payload.get("offer") or "")
    digest = str(payload.get("key_digest") or "")
    records = [r for r in payload.get("records") or () if isinstance(r, Mapping)]
    if not session or not offer or not digest or not records:
        return "button approval does not name its session, offer, key and records"
    if core is None:
        core = ambient_core()
    if core is None:
        return "button approval cannot be checked here (no repository log)"
    events = core.events()
    index = _index_of(events)
    at = index.position.get(entry.digest, len(events))
    if not any(n < at and key == digest for n, key in index.hello.get(session, ())):
        return "button approval: no panel registered that key for its session before it"
    from plumb.mod.session import accepted_digests, registration

    held = registration(core.root, session)
    if held is not None and digest not in accepted_digests(held):
        return "button approval: the key is not the one the session's panel holds"
    drawn = [(n, p) for n, p in index.offers.get((session, offer), ()) if n < at]
    if not drawn:
        return "button approval: its offer was not drawn in that session before it"
    # the drawing under the approval's key (a resumed session draws its offers again)
    same_key = [p for _, p in drawn if p.get("key_digest") == digest]
    shown = same_key[-1] if same_key else drawn[0][1]
    if shown.get("key_digest") != digest or shown.get("card") != payload.get("card") \
            or str(shown.get("question") or "") != str(payload.get("question") or ""):
        return "button approval: its offer was drawn for another card or key"
    # the record the offer asked about, or (a read-back) the request's records it named
    named = {(shown.get("record"), shown.get("hash")),
             *((r.get("id"), r.get("hash")) for r in shown.get("records") or ()
               if isinstance(r, Mapping))}
    for item in records:
        if (item.get("id"), item.get("hash")) not in named:
            return (f"button approval: the offer did not show {item.get('id')} at that "
                    "version")
    return None
