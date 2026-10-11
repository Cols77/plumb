"""Everything the owner needs to choose on a stale-link card, as data (SR-116, INT-031).

A stale card (``stale_cards.json``, filed by ``plumb stale card`` or by the Opus diagnosis of
the repin cascade) stores what only the agent or the model can write: the topic, the issue,
the options, what each option does and leaves undone, and why the recommended one is
recommended. What plumb can derive is derived here, each time the card is shown, never typed
by the agent: the record as it now reads, the change with its evidence (the diff of the
linked end between the pinned version and now, or the earlier and current wording of a
linked record) and the owner's words the record traces to.

``card_content(core, entry)`` returns one plain dict per card, ready for ``present.json`` and
for text (``content_lines``). A long diff is kept whole and marked with its size and
``folded: true`` so a renderer folds it, openable in full; it is never cut (SR-116 EX-2). A
card filed before SR-116 (no consequences, no reason) is still shown, with the derived parts,
and says what is not written yet; it is never dropped or resolved here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

FOLD_AT = 4_000          # characters of diff above which a renderer folds it (never cuts it)
NOT_WRITTEN = "not written yet"
NO_WORDS = 'The words of yours "{title}" came from are not on file.'


def _record_text(record: Any) -> str:
    from plumb.understand.judge import record_text

    return record_text(record)


def _link_of(index: Mapping[str, Any], link_id: str) -> Any:
    record_id, _, position = link_id.partition("#")
    record = index.get(record_id)
    if record is None or not position.isdigit() or int(position) >= len(record.links):
        return None
    return record.links[int(position)]


def record_wording(record: Any) -> dict[str, Any]:
    """The record as it now reads: its title, its statement (or decision, or read-back) and
    its examples."""
    fields = record.fields
    if record.kind == "requirement":
        wording = str(fields.get("statement") or record.title)
    elif record.kind == "decision":
        wording = _record_text(record)
    elif record.kind == "intent":
        wording = str(fields.get("readback") or record.title)
    else:
        wording = _record_text(record)
    return {"id": record.id, "kind": record.kind, "title": record.title,
            "wording": " ".join(wording.split()) if record.kind != "decision" else wording,
            "examples": [f"{e.id}: given {e.given}, when {e.when}, then {e.then}"
                         for e in record.examples]}


def _git_text(root: Path, args: list[str]) -> str | None:
    from plumb.links import _git_text as git_text

    return git_text(root, args)


def _earlier_record(root: Path, target: Any, pin: str) -> Any:
    """The linked record as it read when the link was pinned (from git), or None."""
    from plumb.links import HISTORY_DEPTH
    from plumb.model import RecordError, parse_record

    rel = str(target.path).replace("\\", "/")
    listing = _git_text(root, ["log", f"-n{HISTORY_DEPTH}", "--format=%H", "--", rel])
    for sha in (listing or "").split():
        text = _git_text(root, ["show", f"{sha}:{rel}"])
        if text is None:
            continue
        try:
            earlier = parse_record(text, rel)
        except (RecordError, ValueError, TypeError):
            continue
        if earlier.hash == pin:
            return earlier
    return None


def _measure(change: str) -> dict[str, Any]:
    added = sum(1 for line in change.splitlines()
                if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in change.splitlines()
                  if line.startswith("-") and not line.startswith("---"))
    return {"size": len(change), "lines": len(change.splitlines()), "added": added,
            "removed": removed, "folded": len(change) > FOLD_AT}


def change_evidence(core: Any, link: Any, path: str) -> dict[str, Any]:
    """What changed, with its evidence: ``{path, diff, size, lines, added, removed, folded,
    note}``. ``diff`` is the whole unified diff (``None`` with a ``note`` when the pinned
    version could not be found)."""
    from plumb.links import end_texts
    from plumb.understand.repin import diff

    out: dict[str, Any] = {"path": path, "diff": None, "size": 0, "lines": 0, "added": 0,
                           "removed": 0, "folded": False, "note": ""}
    if link is None:
        out["note"] = "the link no longer exists, so there is no change to show"
        return out
    if link.target.record is not None:
        index = core.index()
        target = index.get(link.target.record)
        if target is None:
            out["note"] = f"{link.target.record} no longer exists"
            return out
        out["path"] = target.path
        earlier = (_earlier_record(Path(core.root), target, link.pin.target)
                   if link.pin is not None else None)
        if earlier is None:
            out["note"] = ("the wording it had when the link was pinned is not in the history "
                           "kept by git; its current wording is: " + _record_text(target))
            return out
        change = diff(_record_text(earlier) + "\n", _record_text(target) + "\n",
                      f"{target.id} wording")
    else:
        texts = end_texts(Path(core.root), link)
        if texts is None:
            out["note"] = ("the version pinned for this link was not found in git, so the "
                           "change cannot be shown as a diff")
            return out
        # a definition is cut without its last line break: give it one, or the last removed
        # and added lines run together on one diff line
        before, after = (t if not t or t.endswith("\n") else t + "\n" for t in texts)
        change = diff(before, after, path)
    out.update(_measure(change), diff=change)
    if not change:
        out["note"] = "the linked text is the same as when it was pinned"
    return out


def _prompts(core: Any) -> list[dict[str, Any]]:
    try:
        lines = Path(core.paths.prompts).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    out = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _prompt_for(prompts: list[dict[str, Any]], digest: str) -> dict[str, Any] | None:
    want = digest.removeprefix("sha256:").strip()
    if not want:
        return None
    for entry in prompts:
        if str(entry.get("digest") or "").removeprefix("sha256:").startswith(want):
            from plumb.hosts.claude_code.prompt import owner_text

            return {"text": owner_text(str(entry.get("text") or "")),
                    "at": str(entry.get("at") or "")}
    return None


def owner_words(core: Any, record: Any) -> dict[str, Any]:
    """The owner's words ``record`` traces to: for itself when it is an intent, and for each
    intent it derives from, the quote and the logged prompt it came from (where on file).
    ``{"items": [{id, title, quote, prompt, at}], "note": ""}``; ``note`` says plainly when
    none is on file."""
    index = core.index()
    sources = [record] if record.kind == "intent" else []
    sources += [index[link.target.record] for link in record.links
                if link.kind == "derives_from" and link.target.record in index]
    prompts = _prompts(core) if sources else []
    items = []
    for source in sources:
        raw = source.fields.get("quote") or ""
        parts = raw if isinstance(raw, (list, tuple)) else [raw]   # some intents quote twice
        quote = " / ".join(" ".join(str(p).split()) for p in parts if str(p).strip())
        prompt = _prompt_for(prompts, str(source.fields.get("prompt") or ""))
        if not quote and prompt is None:
            continue
        items.append({"id": source.id, "title": source.title, "quote": quote or None,
                      "prompt": prompt["text"] if prompt else None,
                      "at": prompt["at"] if prompt else None})
    return {"items": items, "note": "" if items else NO_WORDS.format(title=record.title)}


def _recommended(entry: Mapping[str, Any], count: int) -> int:
    try:
        first = int(entry.get("recommended") or 0)
    except (TypeError, ValueError):
        first = 0
    return first if 0 <= first < count else 0


def options(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The options, the recommended one first: ``{n, text, consequence, recommended,
    index}`` (``index`` is the option's place as filed; ``consequence`` is None when not
    written yet)."""
    texts = [str(o) for o in entry.get("options") or ()]
    raw = entry.get("consequences")
    consequences = [str(c) for c in raw] if isinstance(raw, (list, tuple)) else []
    first = _recommended(entry, len(texts))
    order = [first, *[i for i in range(len(texts)) if i != first]] if texts else []
    out = []
    for n, i in enumerate(order, start=1):
        said = consequences[i].strip() if i < len(consequences) else ""
        out.append({"n": n, "text": texts[i], "consequence": said or None,
                    "recommended": i == first, "index": i})
    return out


def card_content(core: Any, entry: Mapping[str, Any], *, session: str = "") -> dict[str, Any]:
    """One stale card with everything the owner needs to choose (SR-116):

    ``{id, kind, session, link, record, path, topic, issue, by, turn, status,
    record_now: {id, kind, title, wording, examples} | None,
    change: {path, diff, size, lines, added, removed, folded, note},
    owner_words: {items: [{id, title, quote, prompt, at}], note},
    options: [{n, text, consequence, recommended, index}], why, missing, complete, notes}``.

    The stored parts come from ``entry``; the record, the change and the owner's words are
    derived now. ``missing`` names what the card still lacks (``stale.card_missing``)."""
    from plumb import stale

    index = core.index()
    link_id = str(entry.get("link") or "")
    record_id = str(entry.get("record") or link_id.partition("#")[0])
    record = index.get(record_id)
    link = _link_of(index, link_id)
    path = str(entry.get("path") or "")
    missing = stale.card_missing(entry)
    shown = options(entry)
    notes = []
    if any(o["consequence"] is None for o in shown):
        notes.append(f"what each option does and leaves undone is {NOT_WRITTEN}")
    why = str(entry.get("why") or "").strip() or None
    if why is None:
        notes.append(f"why the recommended option is recommended is {NOT_WRITTEN}")
    return {
        "id": f"stale:{link_id}", "kind": "stale_link", "session": session, "link": link_id,
        "record": record_id, "path": path, "topic": str(entry.get("topic") or ""),
        "issue": str(entry.get("issue") or ""), "by": str(entry.get("by") or "agent"),
        "turn": int(entry.get("turn") or 0), "status": str(entry.get("status") or "open"),
        "record_now": record_wording(record) if record is not None else None,
        "change": change_evidence(core, link, path),
        "owner_words": (owner_words(core, record) if record is not None
                        else {"items": [], "note": f"{record_id} no longer exists"}),
        "options": shown, "why": why, "missing": missing, "complete": not missing,
        "notes": notes,
    }


def session_contents(core: Any, session: str, *, open_only: bool = True,
                     incomplete_only: bool = False) -> list[dict[str, Any]]:
    """``card_content`` for each stale card of ``session`` (open ones by default)."""
    from plumb import stale

    out = []
    for entry in stale.read_cards(core.root, session):
        if open_only and entry.get("status", "open") != "open":
            continue
        if incomplete_only and stale.card_complete(entry):
            continue
        out.append(card_content(core, entry, session=session))
    return out


def all_contents(core: Any, *, sessions: list[str] | None = None, open_only: bool = True,
                 incomplete_only: bool = False) -> list[dict[str, Any]]:
    """``session_contents`` over ``sessions`` (every session directory by default)."""
    from plumb import stale

    out = []
    for session in sessions if sessions is not None else stale.sessions(core.root):
        out += session_contents(core, session, open_only=open_only,
                                incomplete_only=incomplete_only)
    return out


def content_lines(content: Mapping[str, Any], *, fold: bool = True) -> list[str]:
    """The card as plain text, every part in turn. With ``fold``, a diff over ``FOLD_AT``
    characters is replaced by a line giving its size (the data keeps it whole); without,
    it is printed in full."""
    lines = [f'"{content["topic"]}": {content["issue"]}']
    now = content.get("record_now")
    if now:
        lines.append(f"  As it now reads ({now['title']}): {now['wording']}")
        lines += [f"    {example}" for example in now.get("examples") or ()]
    change = content["change"]
    if change.get("diff"):
        head = (f"  What changed in {change['path']} (+{change['added']}/-{change['removed']} "
                f"lines, {change['size']} characters):")
        lines.append(head)
        if change.get("folded") and fold:
            lines.append(f"    [folded: {change['size']} characters, {change['lines']} lines; "
                         "open it to read it in full]")
        else:
            lines += [f"    {line}" for line in str(change["diff"]).splitlines()]
    if change.get("note"):
        lines.append(f"  About the change: {change['note']}")
    words = content["owner_words"]
    for item in words.get("items") or ():
        said = item.get("quote") or item.get("prompt") or ""
        lines.append(f'  Your words ({item["title"]}): "{said}"')
        if item.get("prompt") and item.get("quote") and item["prompt"] != item["quote"]:
            lines.append(f'    from your message: "{item["prompt"]}"')
    if words.get("note"):
        lines.append(f"  {words['note']}")
    for option in content["options"]:
        mark = " (recommended)" if option["recommended"] else ""
        lines.append(f"  {option['n']}. {option['text']}{mark}")
        lines.append(f"     does and leaves undone: {option['consequence'] or NOT_WRITTEN}")
    lines.append(f"  Why the recommended one: {content.get('why') or NOT_WRITTEN}")
    return lines
