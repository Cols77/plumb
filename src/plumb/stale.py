"""Drift caught at the edit that causes it (SR-111).

``.plumb/cache/linkmap.json`` maps every pinned link end to the link, so the edit hook can
name the links an edit made stale from the hash cache alone: no YAML and no record index
(standard library plus ``plumb.hashing``). ``ensure_linkmap`` rewrites it only when the
record index digest changed. A missing or unreadable map says nothing; the stop hook is the
backstop.

The turn baseline, the hold-open and the stale cards (HA4, HA5) live below the link map.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from plumb.api import Core
    from plumb.contracts import LinkState

CACHE_REL = ".plumb/cache/linkmap.json"
VERSION = 2
DERIVING = frozenset({"derives_from", "decides", "upstream"})
MAX_NOTICES = 5

NOTICE = ("plumb: {record}'s link to {path} is stale: the file changed; rerun its tests and "
          "repin, reword {record}, or bring it to the owner as a card")
DERIVED = "{source} {verb} {target}, which was reworded: check that it still agrees"
_VERBS = {"derives_from": "derives from", "decides": "decides", "upstream": "rests on"}


class End(NamedTuple):
    """One pinned link end in a file: the record, the link id and the pinned target hash."""

    record: str
    link: str
    pin: str
    symbol: str | None = None
    test: str | None = None


class StaleLink(NamedTuple):
    record: str
    link: str
    path: str
    now: str | None   # the end's current hash; None when it no longer exists
    pin: str


def cache_path(root: Path | str) -> Path:
    return Path(root) / CACHE_REL


def _link_key(link: Any) -> list[Any]:
    target = link.target
    pin = link.pin
    return [link.kind, target.record, target.path, target.symbol, target.test, link.example,
            None if pin is None else [pin.source, pin.target]]


def index_digest(index: Mapping[str, Any]) -> str:
    """What the link map rests on: every record's hash, file and links with their pins."""
    items = [[r.id, r.hash, r.path, [_link_key(link) for link in r.links]]
             for r in (index[i] for i in sorted(index))]
    return hashlib.sha256(json.dumps(items, separators=(",", ":")).encode("utf-8")).hexdigest()


def _clean(raw: str) -> str | None:
    from plumb.hashing import clean_rel_path

    return clean_rel_path(raw)


def build_linkmap(index: Mapping[str, Any]) -> dict[str, Any]:
    from plumb.hashing import target_path
    from plumb.query import retired_ids

    ends: dict[str, list[list[Any]]] = {}
    derived: dict[str, list[list[Any]]] = {}
    records: dict[str, str] = {}
    retired = retired_ids(index)
    for record_id in sorted(index):
        record = index[record_id]
        records[record.path] = record.id
        if record_id in retired:  # SR-164: a superseded record's links are not tracked
            continue
        for link in record.links:
            if link.pin is None:
                continue
            target = link.target
            if target.record is not None:
                if link.kind in DERIVING:
                    derived.setdefault(target.record, []).append(
                        [record.id, link.id, link.pin.target, link.kind])
                continue
            raw = target_path(target)
            rel = _clean(raw) if raw else None
            if rel is None:
                continue
            ends.setdefault(rel, []).append(
                [record.id, link.id, link.pin.target, target.symbol, target.test])
    return {"v": VERSION, "digest": index_digest(index), "ends": ends, "derived": derived,
            "records": records}


def load_linkmap(root: Path | str) -> dict[str, Any] | None:
    try:
        data = json.loads(cache_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("v") != VERSION:
        return None
    if not all(isinstance(data.get(k), dict) for k in ("ends", "derived", "records")):
        return None
    return data


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def ensure_linkmap(core: Core, *, force: bool = False) -> bool:
    """Rewrite the link map when the record index digest changed; True when it was written."""
    index = core.index()
    digest = index_digest(index)
    current = load_linkmap(core.root)
    if not force and current is not None and current.get("digest") == digest:
        try:  # the records were rewritten without a change the map rests on: it is current
            os.utime(cache_path(core.root))
        except OSError:
            pass
        return False
    data = build_linkmap(index)
    try:
        _write_atomic(cache_path(core.root), json.dumps(data, separators=(",", ":")))
    except OSError:
        return False
    return True


RECORD_DIRS = ("intents", "requirements", "decisions", "features", "ncs")


def linkmap_outdated(root: Path | str) -> bool:
    """True when a record file is newer than the link map (a record or link was written
    since): a stat of the record files, no parsing. False without a map."""
    try:
        stamp = cache_path(root).stat().st_mtime_ns
    except OSError:
        return False
    for name in RECORD_DIRS:
        try:
            scan = os.scandir(Path(root) / ".plumb" / name)
        except OSError:
            continue
        with scan:
            for entry in scan:
                try:
                    if entry.name.endswith(".md") and entry.stat().st_mtime_ns > stamp:
                        return True
                except OSError:
                    continue
    return False


def links_touching(root: Path | str, rel: str) -> list[End]:
    """The pinned link ends inside the repository file ``rel`` (empty without a map)."""
    data = load_linkmap(root)
    key = _clean(rel)
    if data is None or key is None:
        return []
    out = []
    for item in data["ends"].get(key, ()):
        if isinstance(item, list) and len(item) == 5:
            out.append(End(*item))
    return out


def record_for_path(root: Path | str, rel: str) -> str | None:
    """The record whose file is ``rel`` (a direct edit of a record), or None."""
    data = load_linkmap(root)
    key = _clean(rel)
    if data is None or key is None:
        return None
    found = data["records"].get(key)
    return found if isinstance(found, str) else None


def current_hash(root: Path | str, rel: str, end: End) -> str | None:
    from plumb.contracts import Target
    from plumb.hashing import hash_target

    if end.test:
        target = Target(test=end.test)
    elif end.symbol:
        target = Target(path=rel, symbol=end.symbol)
    else:
        target = Target(path=rel)
    return hash_target(Path(root), {}, target)


def stale_after_edit(root: Path | str, rel: str) -> list[StaleLink]:
    """The links whose end inside ``rel`` no longer matches its pin."""
    out = []
    for end in links_touching(root, rel):
        now = current_hash(root, rel, end)
        if now != end.pin:
            out.append(StaleLink(end.record, end.link, rel, now, end.pin))
    return out


def notice(item: StaleLink) -> str:
    return NOTICE.format(record=item.record, path=item.path)


def notices(items: Sequence[StaleLink], limit: int = MAX_NOTICES) -> list[str]:
    """One line per stale link, at most ``limit``, then ``+N more``."""
    lines = [notice(item) for item in items[:limit]]
    if len(items) > limit:
        lines.append(f"plumb: +{len(items) - limit} more")
    return lines


def derived_stale(core: Core, ids: Iterable[str]) -> list[tuple[str, str, str, str]]:
    """``(source, target, link id, kind)`` of every link from a record to one of ``ids``
    whose pin no longer matches that record (it was reworded since the pin)."""
    from plumb.query import retired_ids

    wanted = set(ids)
    index = core.index()
    retired = retired_ids(index)
    out = []
    for record in index.values():
        if record.id in retired:
            continue
        for link in record.links:
            target = link.target.record
            if (target in wanted and target in index and link.kind in DERIVING
                    and link.pin is not None and link.pin.target != index[target].hash):
                out.append((record.id, target, link.id, link.kind))
    return sorted(out)


def derived_line(source: str, target: str, kind: str) -> str:
    return DERIVED.format(source=source, verb=_VERBS.get(kind, "relies on"), target=target)


def derived_lines(core: Core, ids: Iterable[str]) -> list[str]:
    """``SR-032 derives from INT-016, which was reworded: check that it still agrees``."""
    return [derived_line(source, target, kind)
            for source, target, _link, kind in derived_stale(core, ids)]


# --------------------------------------------------------------------------- the turn baseline


def session_path(root: Path | str, session: str) -> Path:
    return Path(root) / ".plumb" / "session" / session


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_baseline(root: Path | str, session: str) -> dict[str, dict[str, list[str]]]:
    """The links stale at the turn start: ``{link id: {"pin": [source, target], "now":
    [source, target]}}`` (empty without a baseline)."""
    data = _read_json(session_path(root, session) / "stale_baseline.json")
    links = data.get("links") if isinstance(data, dict) else None
    return links if isinstance(links, dict) else {}


def was_told(root: Path | str, session: str, key: str, state: str) -> bool:
    data = _read_json(session_path(root, session) / "stale_told.json")
    return isinstance(data, dict) and data.get(key) == state


def mark_told(root: Path | str, session: str, items: Mapping[str, str]) -> None:
    """Remember what the edit check said (one line per link state, said once)."""
    path = session_path(root, session) / "stale_told.json"
    data = _read_json(path)
    data = dict(data) if isinstance(data, dict) else {}
    data.update(items)
    try:
        _write_atomic(path, json.dumps(data))
    except OSError:
        pass


class Row(NamedTuple):
    """One stale link as the hooks see it."""

    link: str
    record: str
    what: str            # the file, test or record the link points to
    kind: str
    pin: tuple[str, str]
    now: tuple[str, str]


def stale_rows(core: Core, records: Iterable[str] | None = None,
               only: Collection[str] | None = None) -> list[Row]:
    """Every link (of ``records``, else of all; ``only``: of these link ids) that is stale
    now (an end moved), with its pinned and current hashes."""
    from plumb import links

    out = []
    chosen = None if records is None else list(records)
    states = core.link_states(chosen) if only is None else links.link_states(core, chosen, only)
    for state in states:
        if state.state != "stale" or state.current is None or state.link.pin is None:
            continue
        link = state.link
        target = link.target
        what = target.record or target.path or (target.test or "").split("::", 1)[0] or "?"
        out.append(Row(link.id, link.source, what, link.kind,
                       (link.pin.source, link.pin.target),
                       (state.current.source, state.current.target)))
    return out


BASE_RECORD_DIRS = (".plumb/decisions", ".plumb/features", ".plumb/intents", ".plumb/ncs",
                    ".plumb/requirements")


def stale_at(root: Path, base: str, rows: Sequence[Row]) -> set[str] | None:
    """Of ``rows``, the link ids that were already stale at ``base`` (a git ref): the records
    and the linked files are read from ``base`` into a temporary folder and judged there in
    one pass (SR-166: only new problems hold). None when ``base`` cannot be read."""
    import io
    import subprocess
    import tarfile
    import tempfile

    from plumb import links
    from plumb.api import open_core

    if not rows:
        return set()
    wanted = sorted({r.what for r in rows if "/" in r.what or "." in r.what})
    try:
        listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", base, "--",
                                 *BASE_RECORD_DIRS, *wanted], cwd=root, capture_output=True,
                                text=True, encoding="utf-8", timeout=30,
                                check=True).stdout.splitlines()
        tar = subprocess.run(["git", "archive", "--format=tar", base, "--",
                              *[p for p in listed if p]], cwd=root, capture_output=True,
                             timeout=60, check=True).stdout
        with tempfile.TemporaryDirectory(prefix="plumb-base-") as tmp:
            tarfile.open(fileobj=io.BytesIO(tar)).extractall(tmp, filter="data")
            core = open_core(Path(tmp))
            wanted_links = {r.link for r in rows}
            return {st.link.id for st in links.link_states(core, {r.record for r in rows})
                    if st.state == "stale" and st.link.id in wanted_links}
    except Exception:  # noqa: BLE001 - an unreadable base means "cannot tell"
        return None


def new_rows(root: Path, base: str, rows: Sequence[Row]) -> list[Row]:
    """``rows`` minus the ones already stale at ``base``; all of them when base cannot be read."""
    old = stale_at(root, base, rows)
    return list(rows) if old is None else [r for r in rows if r.link not in old]


def write_baseline(core: Core, session: str, turn_id: str) -> None:
    """The links stale at the turn start (``stale_baseline.json``): their ids and pins, and
    the hashes they had then. Written by the prompt hook; the stop hook compares against it."""
    links = {r.link: {"pin": list(r.pin), "now": list(r.now)} for r in stale_rows(core)}
    _write_atomic(session_path(core.root, session) / "stale_baseline.json",
                  json.dumps({"turn": turn_id, "links": links}))


class TurnState(NamedTuple):
    valid: bool          # a baseline of this very turn exists; without one nothing is held
    new: list[Row]       # stale now, not stale (in the same way) at the turn start
    before: list[Row]    # stale before the turn and not moved by it


def turn_state(core: Core, session: str, turn_id: str | None) -> TurnState:
    data = _read_json(session_path(core.root, session) / "stale_baseline.json")
    if not isinstance(data, dict) or not turn_id or data.get("turn") != turn_id:
        return TurnState(False, [], [])
    links = data.get("links") if isinstance(data.get("links"), dict) else {}
    new, before = [], []
    for row in stale_rows(core):
        if row.now[1] == row.pin[1]:
            continue  # only the requirement moved: the agent rewording it is its resolution
        old = links.get(row.link)
        if isinstance(old, dict) and old.get("now") == list(row.now):
            before.append(row)
        else:
            new.append(row)
    return TurnState(True, new, before)


def unresolved(core: Core, session: str, state: TurnState) -> list[Row]:
    """This turn's stale links no card holds: a link the agent brought to the owner counts
    as resolved for the hold."""
    carded = carded_links(core.root, session)
    return [r for r in state.new if r.link not in carded]


HOLD_LINE = "plumb: {record}'s link to {what} is stale and unresolved ({link})"
HOLD_HOW = ("plumb: resolve each before ending the turn: rerun its tests and repin it "
            "(plumb repin --after-tests <link>), reword the record so it agrees and repin "
            "it, or bring it to the owner as a card (plumb stale card <link> --topic "
            "\"<requirement title>\" --issue \"<what changed, in words>\" --options \"a|b|c\" "
            "--consequences \"<what a does and leaves undone>|<b's>|<c's>\" --why \"<why the "
            "recommended one>\"). Held {n} of {max}.")
INCOMPLETE_LINE = ("plumb: the card for {link} is not offered to the owner until it is "
                   "complete (SR-116); it lacks: {missing}. Complete it with plumb stale card "
                   "{link} --consequences \"...\" --why \"...\" (its topic, issue and options "
                   "are kept)")
BEFORE_LINE = ("plumb: {n} links were already stale before this turn and are not held: "
               "{links}")


def hold_lines(rows: Sequence[Row], held: int, limit: int,
               missing: Mapping[str, Sequence[str]] | None = None) -> list[str]:
    """The hold's reasons; ``missing`` (``incomplete_cards``) adds, for a link whose card is
    incomplete, what that card still lacks (SR-116 EX-3)."""
    lines = []
    for r in rows[:MAX_NOTICES]:
        lines.append(HOLD_LINE.format(record=r.record, what=r.what, link=r.link))
        lacks = (missing or {}).get(r.link)
        if lacks:
            lines.append(INCOMPLETE_LINE.format(link=r.link, missing="; ".join(lacks)))
    if len(rows) > MAX_NOTICES:
        lines.append(f"plumb: +{len(rows) - MAX_NOTICES} more")
    lines.append(HOLD_HOW.format(n=held, max=limit))
    return lines


def before_line(rows: Sequence[Row]) -> str:
    names = [f"{r.record} ({r.what})" for r in rows[:MAX_NOTICES]]
    more = f", +{len(rows) - MAX_NOTICES} more" if len(rows) > MAX_NOTICES else ""
    return BEFORE_LINE.format(n=len(rows), links=", ".join(names) + more)


def once_per_session(root: Path | str, session: str, key: str) -> bool:
    """True the first time ``key`` is asked in this session (and remembers it)."""
    path = session_path(root, session) / "stale_listed.json"
    data = _read_json(path)
    data = dict(data) if isinstance(data, dict) else {}
    if key in data:
        return False
    data[key] = True
    try:
        _write_atomic(path, json.dumps(data))
    except OSError:
        pass
    return True


def listed(root: Path | str, session: str, key: str) -> bool:
    """Whether ``key`` was already listed in this session (``once_per_session``), unmarked."""
    data = _read_json(session_path(root, session) / "stale_listed.json")
    return isinstance(data, dict) and key in data


def queue_before(root: Path | str, session: str, key: str, line: str) -> None:
    """SR-111: a stop that holds nothing cannot reach the agent, so the before-the-turn line
    waits for the next prompt hook (``take_before``), which lists it."""
    try:
        _write_atomic(session_path(root, session) / "stale_before.json",
                      json.dumps({"key": key, "line": line}))
    except OSError:
        pass


def take_before(root: Path | str, session: str) -> str | None:
    """The queued before-the-turn line, read once and marked listed as it is handed over;
    None when none waits or it was listed already."""
    path = session_path(root, session) / "stale_before.json"
    data = _read_json(path)
    try:
        path.unlink()
    except OSError:
        pass
    if not isinstance(data, dict) or not data.get("line"):
        return None
    return str(data["line"]) if once_per_session(root, session, str(data.get("key"))) else None


def hold_count(root: Path | str, session: str, turn_id: str | None) -> int:
    data = _read_json(session_path(root, session) / "stale_holds.json")
    if isinstance(data, dict) and data.get("turn") == turn_id:
        try:
            return int(data.get("holds") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def set_hold_count(root: Path | str, session: str, turn_id: str | None, holds: int) -> None:
    try:
        _write_atomic(session_path(root, session) / "stale_holds.json",
                      json.dumps({"turn": turn_id, "holds": holds}))
    except OSError:
        pass


# --------------------------------------------------------------------------- stale cards
# ``.plumb/session/<id>/stale_cards.json``: a JSON list, written here alone (atomically).
# ``cardstore`` reads the open entries as ``stale_link`` cards; ``understand.fullcard`` draws them.


def cards_path(root: Path | str, session: str) -> Path:
    return session_path(root, session) / "stale_cards.json"


def read_cards(root: Path | str, session: str) -> list[dict[str, Any]]:
    data = _read_json(cards_path(root, session))
    return [dict(c) for c in data if isinstance(c, dict)] if isinstance(data, list) else []


def _write_cards(root: Path | str, session: str, cards: list[dict[str, Any]]) -> None:
    _write_atomic(cards_path(root, session), json.dumps(cards, ensure_ascii=False, indent=1))


def card_basis(core: Core, entry: Mapping[str, Any]) -> str:
    """Meaning and link versions a decision concerns, excluding evaluation bookkeeping."""
    from dataclasses import asdict

    from plumb.understand import files

    meaning = {k: v for k, v in entry.items() if k not in ("turn", "status", "decision")}
    versions = [asdict(s.current) if s.current is not None else None
                for s in core.link_states([str(entry.get("record") or "")])
                if s.link.id == entry.get("link")]
    return files.digest_of([meaning, versions])


def save_decision(core: Core, session: str, card: Any) -> None:
    """Persist the owner's answer separately from whether the stale link is resolved."""
    from plumb.understand import files

    entries = read_cards(core.root, session)
    for entry in entries:
        if entry.get("link") == card.id.removeprefix("stale:") \
                and entry.get("status", "open") == "open":
            entry["decision"] = {"status": card.status,
                                 "answers": [files.answer_to_json(a) for a in card.answers],
                                 "basis": card_basis(core, entry)}
            _write_cards(core.root, session, entries)
            return


def add_card(root: Path | str, session: str, *, link: str, record: str, path: str,
             topic: str, issue: str, options: Sequence[str], recommended: int = 0,
             turn: int = 0, consequences: Sequence[str] | None = None, why: str = "",
             by: str = "") -> dict[str, Any]:
    """Record a stale card for an owner-intent question (one open card per link).

    SR-116: ``consequences`` (one per option: what it does and leaves undone) and ``why``
    (the reason for the recommended option) are written when given; a card without them is
    kept but incomplete (``card_missing``). ``by`` names who filed it (``diagnosis`` for
    Opus). The record's wording, the diff and the owner's words are derived when the card is
    shown (``plumb.understand.fullcard``), never stored here."""
    entry: dict[str, Any] = {"link": link, "record": record, "path": path, "topic": topic,
                             "issue": issue, "options": [str(o) for o in options],
                             "recommended": int(recommended), "turn": int(turn),
                             "status": "open"}
    if consequences:
        entry["consequences"] = [str(c) for c in consequences]
    if why:
        entry["why"] = str(why)
    if by:
        entry["by"] = str(by)
    previous = open_card(root, session, link)
    if previous and isinstance(previous.get("decision"), Mapping):
        from plumb.api import open_core

        decision = previous["decision"]
        if decision.get("basis") == card_basis(open_core(root), entry):
            entry["decision"] = dict(decision)
    cards = [c for c in read_cards(root, session)
             if not (c.get("link") == link and c.get("status") == "open")]
    cards.append(entry)
    _write_cards(root, session, cards)
    return entry


def card_missing(card: Mapping[str, Any]) -> list[str]:
    """SR-116 EX-3: what a stale card still lacks before it may be offered to the owner, in
    words the agent can act on (empty when complete). A card written before SR-116 has no
    consequences and no reason: it is kept open and reported here, never dropped."""
    options = [str(o) for o in card.get("options") or ()]
    raw = card.get("consequences")
    consequences = [str(c) for c in raw] if isinstance(raw, (list, tuple)) else []
    missing: list[str] = []
    if not str(card.get("topic") or "").strip():
        missing.append("the topic")
    if not str(card.get("issue") or "").strip():
        missing.append("the issue")
    if len(options) < 2:
        missing.append("at least two options")
    for n, option in enumerate(options):
        if n >= len(consequences) or not consequences[n].strip():
            missing.append(f'what option {n + 1} ("{option}") does and leaves undone')
    if not str(card.get("why") or "").strip():
        missing.append("why the recommended option is recommended")
    return missing


def card_complete(card: Mapping[str, Any]) -> bool:
    return not card_missing(card)


def open_card(root: Path | str, session: str, link: str) -> dict[str, Any] | None:
    """The open card of ``link`` in ``session``, or None."""
    for card in read_cards(root, session):
        if card.get("link") == link and card.get("status", "open") == "open":
            return card
    return None


def incomplete_cards(root: Path | str, session: str) -> dict[str, list[str]]:
    """``{link: what it lacks}`` for the open cards of ``session`` that are not complete."""
    out: dict[str, list[str]] = {}
    for card in read_cards(root, session):
        if card.get("status", "open") == "open":
            missing = card_missing(card)
            if missing:
                out[str(card.get("link"))] = missing
    return out


def sessions(root: Path | str) -> list[str]:
    """Every session directory under ``.plumb/session`` (sorted)."""
    try:
        return sorted(e.name for e in os.scandir(Path(root) / ".plumb" / "session")
                      if e.is_dir())
    except OSError:
        return []


def close_card(root: Path | str, session: str, link: str) -> bool:
    """Mark the open card of ``link`` resolved; False when there is none."""
    cards = read_cards(root, session)
    found = False
    for card in cards:
        if card.get("link") == link and card.get("status") == "open":
            card["status"] = "resolved"
            found = True
    if found:
        _write_cards(root, session, cards)
    return found


def withdraw_card(core: Core, session: str, link: str, why: str) -> bool:
    """SR-161, SR-162: withdraw the open card of ``link`` in ``session``, logged with its
    reason. A withdrawal answers and confirms nothing; False when there is no open card."""
    cards = read_cards(core.root, session)
    found = False
    for card in cards:
        if card.get("link") == link and card.get("status", "open") == "open":
            card["status"] = "withdrawn"
            found = True
    if found:
        _write_cards(core.root, session, cards)
        core.log_append("events", "card-withdrawn",
                        {"card": f"stale:{link}", "session": session, "topic": link,
                         "reason": why})
    return found


def reopen_card(root: Path | str, session: str, link: str) -> None:
    """Put the latest withdrawn card of ``link`` back open (the undo of a settlement)."""
    cards = read_cards(root, session)
    for card in reversed(cards):
        if card.get("link") == link and card.get("status") == "withdrawn":
            card["status"] = "open"
            _write_cards(root, session, cards)
            return


def withdraw_settled(core: Core, only: Sequence[str] | None = None) -> None:
    """SR-161: withdraw the open stale cards whose link is current again or no longer exists,
    in the ``only`` sessions (default every session folder)."""
    from plumb.present import owner_text as words

    held = {s: [str(c.get("link")) for c in read_cards(core.root, s)
                if c.get("status", "open") == "open"]
            for s in (sessions(core.root) if only is None else only)}
    wanted = sorted({link.partition("#")[0] for links in held.values() for link in links})
    states = {s.link.id: s.state for s in core.link_states(wanted)} if wanted else {}
    for session, links in held.items():
        for link in links:
            state = states.get(link, "gone")
            if state in ("current", "gone"):
                withdraw_card(core, session, link, words.WITHDRAWN_LINK_GONE if state == "gone"
                              else words.WITHDRAWN_LINK_CURRENT)


def carded_links(root: Path | str, session: str) -> set[str]:
    """The links an open, complete card holds (SR-116: an incomplete card does not count as
    bringing the link to the owner; the hold names what it lacks)."""
    return {str(c.get("link")) for c in read_cards(root, session)
            if c.get("status", "open") == "open" and card_complete(c)}


def default_card(row: Row, record_title: str, other_title: str = "") -> dict[str, Any]:
    """The card the hold-open files when it lets a turn go with ``row`` unresolved."""
    from plumb.present import owner_text as words

    if row.what.startswith(("INT-", "SR-", "DEC-", "FEAT-", "NC-")):
        issue = words.STALE_ISSUE_RECORD.format(title=record_title, other=other_title or "it")
    else:
        issue = words.STALE_ISSUE_CODE.format(path=row.what, title=record_title)
    return {"link": row.link, "record": row.record, "path": row.what, "topic": record_title,
            "issue": issue, "options": [words.STALE_OPTION_KEEP, words.STALE_OPTION_REWORD,
                                        words.STALE_OPTION_UNDO], "recommended": 0,
            "consequences": [words.STALE_CONSEQUENCE_KEEP, words.STALE_CONSEQUENCE_REWORD,
                             words.STALE_CONSEQUENCE_UNDO],
            "why": words.STALE_WHY_KEEP}


# Where a shell command learns its session: plumb's own variable, then the id Claude Code
# gives every command it runs (the same id its hooks receive as ``session_id``).
SESSION_ENV = ("PLUMB_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")
_NOT_A_TURN = frozenset({"default", "cli"})
_SESSION_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_session(value: str) -> str:
    """As ``hookio.safe_session_id``: the directory name the hooks use for this id."""
    cleaned = _SESSION_CHARS.sub("-", value).strip("-")
    return cleaned[:80] or "default"


def current_session(root: Path | str) -> str:
    """The session whose turn is in progress for this agent: ``PLUMB_SESSION_ID``, else the
    session id the host exposes to commands (``CLAUDE_CODE_SESSION_ID``), else the session
    with the newest turn file that holds a live ``turn_id`` and is not ``default``, ``cli``
    or a ``perf-*`` probe, else ``cli``. A card filed here is the one the stop hook of that
    session sees."""
    for name in SESSION_ENV:
        named = (os.environ.get(name) or "").strip()
        if named:
            return _safe_session(named)
    best, newest = "cli", -1
    try:
        entries = list(os.scandir(Path(root) / ".plumb" / "session"))
    except OSError:
        return best
    for entry in entries:
        if entry.name in _NOT_A_TURN or entry.name.startswith("perf-"):
            continue
        turn_file = Path(entry.path) / "turn.json"
        try:
            stamp = turn_file.stat().st_mtime_ns
        except OSError:
            continue
        data = _read_json(turn_file)
        if not isinstance(data, dict) or not data.get("turn_id"):
            continue
        if stamp > newest:
            best, newest = entry.name, stamp
    return best


def turn_number(root: Path | str, session: str) -> int:
    """The turn's start time in seconds: the number a card is ordered by."""
    data = _read_json(session_path(root, session) / "turn.json")
    try:
        return int(float(data.get("turn_start") or 0)) if isinstance(data, dict) else 0
    except (TypeError, ValueError):
        return 0


def settle_drift(core: Core, session: str, rows: Sequence[Row],
                 waiting: set[str] | None = None) -> list[str]:
    """SR-175, DEC-061: check the requirement of each stale link is still covered before any
    card: its tests run, a model judges the meaning kept, and the link is repinned with a
    logged note (a wording-only change is recorded as an unconfirmed edit). A card is filed
    only when the model says the requirement should change fundamentally; a failure, an
    unreachable model or a change to send back stays unresolved (SR-174: with one line saying
    the check waits, returned; ``waiting`` collects the records it waits on). Never fails
    the stop."""
    from plumb.judgment import waiting_line
    from plumb.links import repin_after_tests

    said: list[str] = []
    for record in sorted({r.record for r in rows}):
        try:
            cause = repin_after_tests(core, record, session=session, auto=True).unreachable
        except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
            continue
        if cause and waiting is not None:
            waiting.add(record)
        line = waiting_line(core.root, "the stale check", cause) if cause else None
        if line:
            said.append(line)
    return said


def card_lost_tests(core: Core, session: str) -> None:
    """SR-175 EX-2: a confirmed example whose every verified_by test is gone has lost its
    proof, so the owner is asked once whether the requirement should change."""
    from plumb.present import owner_text as words

    states = core.link_states()
    status = core.status(sorted({s.link.source for s in states}))
    proof: dict[tuple[str, str], list[LinkState]] = {}
    for s in states:
        if s.link.kind == "verified_by" and s.link.example:
            proof.setdefault((s.link.source, s.link.example), []).append(s)
    index = core.index()
    asked = {str(c.get("link")) for c in read_cards(core.root, session)}
    for (source, example), found in sorted(proof.items()):
        link = found[0].link.id
        if (any(s.state != "dangling" for s in found) or link in asked
                or status[source].confirmation != "confirmed"):
            continue
        title = index[source].title
        add_card(core.root, session, link=link, record=source, path="", by="drift",
                 turn=turn_number(core.root, session), topic=title,
                 issue=words.STALE_ISSUE_LOST_TEST.format(title=title, example=example),
                 options=[words.STALE_OPTION_KEEP, words.STALE_OPTION_REWORD,
                          words.STALE_OPTION_UNDO],
                 consequences=[words.STALE_CONSEQUENCE_KEEP, words.STALE_CONSEQUENCE_REWORD,
                               words.STALE_CONSEQUENCE_UNDO], why=words.STALE_WHY_KEEP)
