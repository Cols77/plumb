"""What a stale card shows the owner, and where the owner's own words come from (SR-116).

A stale card (``stale_cards.json``, filed by ``plumb stale card`` or by the Opus diagnosis of
the repin cascade) stores what only the agent or the model can write: the topic, the issue,
the options, what each option does and why the recommended one is recommended. ``options`` reads
them, the recommended one first; ``fullcard.stale_content`` draws the card from them.
``owner_words`` finds the words of the owner a record traces to (the quote, the logged message,
what a transcript search found) for a trial card."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

NO_WORDS = 'The words of yours "{title}" came from are not on file.'


def _record_text(record: Any) -> str:
    from plumb.understand.judge import record_text

    return record_text(record)


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


def recovered(core: Any, source: Any) -> dict[str, Any] | None:
    """What ``plumb quotes recover`` found for ``source`` in past transcripts (SR-118), or
    None: ``{status, span, at, session, reason, proposed_wording, note}``. Shown, never
    trusted: ``note`` says it was found in a transcript and is not verified."""
    from plumb.understand.recover import finding_for

    try:
        finding = finding_for(core, source)
    except Exception:  # noqa: BLE001 - an unreadable cache shows nothing, it never breaks a card
        return None
    if finding is None:
        return None
    keys = ("status", "span", "at", "session", "reason", "proposed_wording", "note", "by")
    return {key: finding.get(key) for key in keys}


def found_lines(found: Mapping[str, Any] | None) -> list[str]:
    """What a transcript search found (``recovered``) in plain words, or [] when nothing."""
    if not found:
        return []
    from plumb.understand.recover import finding_lines

    return finding_lines(found)


def owner_words(core: Any, record: Any) -> dict[str, Any]:
    """The owner's words ``record`` traces to: for itself when it is an intent, and for each
    intent it derives from, the quote and the logged prompt it came from (where on file).
    ``{"items": [{id, title, quote, prompt, at, found, found_lines}], "note": ""}``; ``note``
    says plainly when none is on file. ``found`` is what a transcript search found
    (``recovered``): shown as found, not verified, it never stands for the owner's logged
    words."""
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
        found = recovered(core, source)
        if not quote and prompt is None and found is None:
            continue
        items.append({"id": source.id, "title": source.title, "quote": quote or None,
                      "prompt": prompt["text"] if prompt else None,
                      "at": prompt["at"] if prompt else None, "found": found,
                      "found_lines": found_lines(found)})
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
