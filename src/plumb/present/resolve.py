"""``plumb resolve``: the owner's words mapped to records, paths and tests (sp5 5, SR-064).

The owner does not necessarily know the code (R9): every owner-facing command takes plain
words and resolves them here, in this order:

1. record IDs named in the words (``SR-004``);
2. a test node (``tests/x.py::test_y``) or a repository path: the records that own it;
3. plain words: record titles first, then statements, examples, quotes, read-backs and the
   feature's title, by shared terms (light stemming: "added" matches "add"); then file names
   of the records' code and tests.

The best match wins only when it is clearly ahead: its score is at least
``resolve.min_score`` and more than ``resolve.margin`` ahead of the next candidate that is
not part of the same chain (a requirement and the intent it derives from are one answer).
Otherwise the resolution is ambiguous and the command lists the candidates in the owner's
terms and asks which one, instead of guessing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Resolution, Resolved

MAX_ITEMS = 5
_SUFFIXES = ("ings", "ing", "ers", "ed", "es", "s")
_ID = re.compile(r"(?<![A-Za-z0-9-])((?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})(?![0-9])")
_RANK = {"requirement": 0, "intent": 1, "decision": 2, "feature": 3, "nc": 4}
_KIND_ALIASES = {"SR": "requirement", "INT": "intent", "DEC": "decision", "FEAT": "feature",
                 "NC": "nc"}


def stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def stems(text: str) -> frozenset[str]:
    from plumb.text import terms

    return frozenset(stem(w) for w in terms(text))


def _flat(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(map(str, value))
    return str(value or "")


def _rest_text(record: Any, index: Mapping[str, Any]) -> str:
    fields = record.fields
    parts = [_flat(fields.get(k)) for k in ("statement", "readback", "description",
                                            "question", "chosen", "quote", "will", "wont")]
    for example in record.examples:
        parts.extend((example.given, example.when, example.then, example.criterion))
    feature = fields.get("feature")
    if feature in index:
        parts.append(index[feature].title)
    return " ".join(str(p) for p in parts)


def _path_stems(path: str) -> frozenset[str]:
    return stems(re.sub(r"[/_.\-:]+", " ", path))


def _linked(index: Mapping[str, Any], a: str, b: str) -> bool:
    """One chain: a derives from, decides, is upstream of or groups the other."""
    for x, y in ((a, b), (b, a)):
        record = index.get(x)
        if record is None:
            continue
        if any(link.target.record == y for link in record.links):
            return True
        if str(record.fields.get("feature")) == y:
            return True
        if y in [str(m) for m in record.fields.get("requirements") or []]:
            return True
    return False


def _kind_filter(kind: str | None) -> str | None:
    if not kind:
        return None
    return _KIND_ALIASES.get(kind.upper(), kind.lower())


def resolve(core: Any, words: str, *, kind: str | None = None) -> Resolution:
    """The owner's ``words`` as ranked records, paths or tests (see the module doc)."""
    from plumb.query import superseded_ids

    text = " ".join(str(words or "").split())
    index = core.index()
    wanted_kind = _kind_filter(kind)

    def title(record_id: str) -> str:
        return index[record_id].title if record_id in index else record_id

    named = [i for i in dict.fromkeys(_ID.findall(text)) if i in index]
    if named:
        return Resolution(text, "id", tuple(
            Resolved(i, "record", title(i), 1.0, f"named {i}") for i in named))
    token = text.strip("'\"")
    if token and " " not in token:
        if "::" in token:
            owners = _owners(core, index, token)
            items = [Resolved(i, "record", title(i), 1.0, f"{i} is verified by this test")
                     for i in owners] or [Resolved(token, "test", token, 1.0, "a test node")]
            return Resolution(text, "test", tuple(items))
        from plumb.hashing import clean_rel_path

        rel = clean_rel_path(token)
        if rel is not None:
            owners = list(core.records_for_paths([rel]).get(rel, ()))
            if owners or (Path(core.root) / rel).exists():
                requirements = [i for i in owners if index[i].kind == "requirement"]
                chosen = sorted(requirements or owners)
                items = [Resolved(i, "record", title(i), 1.0, f"{i} owns {rel}")
                         for i in chosen] or [Resolved(rel, "path", rel, 1.0,
                                                       "a file no requirement owns yet")]
                return Resolution(text, "path", tuple(items))
    query = stems(text)
    if not query:
        return Resolution(text, "none")
    superseded = superseded_ids(index)
    scored: list[Resolved] = []
    ends: dict[str, set[str]] = {}
    for record_id, record in index.items():
        if record_id in superseded or (wanted_kind and record.kind != wanted_kind):
            continue
        in_title = query & stems(record.title)
        in_rest = (query - in_title) & stems(_rest_text(record, index))
        score = (2 * len(in_title) + len(in_rest)) / (2 * len(query))
        if score > 0:
            where = "the title" if in_title else "the statement, examples or quote"
            scored.append(Resolved(record_id, "record", record.title, round(score, 4),
                                   f"matched {where} of {record_id}"))
        for link in record.links:
            end = link.target.path or link.target.test
            if end and link.kind in ("implemented_by", "verified_by"):
                ends.setdefault(end.split("::", 1)[0], set()).add(record_id)
    if not wanted_kind:
        for end in sorted(ends):
            hits = query & _path_stems(end)
            if hits:
                score = len(hits) / (2 * len(query))  # file names rank below the records
                scored.append(Resolved(end, "path", end, round(score, 4),
                                       f"matched the file name {end}"))
    if not scored:
        return Resolution(text, "none")
    scored.sort(key=lambda r: (-r.score, _RANK.get(getattr(index.get(r.ref), "kind", ""), 9)
                               if r.kind == "record" else 9, r.ref))
    items = tuple(scored[:MAX_ITEMS])
    if _ambiguous(core, index, items):
        return Resolution(text, "words", items, True)
    top = items[0]
    chain = tuple(i for i in items if i is top or (
        i.kind == "record" and top.kind == "record" and _linked(index, top.ref, i.ref)))
    return Resolution(text, "words", chain)


def _ambiguous(core: Any, index: Mapping[str, Any], items: tuple[Resolved, ...]) -> bool:
    config = getattr(core.config, "resolve", None)
    min_score = float(getattr(config, "min_score", 0.34))
    margin = float(getattr(config, "margin", 0.1))
    top = items[0]
    if top.score < min_score:
        return True
    for other in items[1:]:
        if other.kind == "record" and top.kind == "record" and _linked(index, top.ref,
                                                                      other.ref):
            continue  # the same chain: one answer
        return top.score - other.score <= margin
    return False


def _owners(core: Any, index: Mapping[str, Any], node: str) -> list[str]:
    path = node.split("::", 1)[0]
    out = []
    for record_id, record in sorted(index.items()):
        for link in record.links:
            end = link.target.test or link.target.path
            if link.kind == "verified_by" and end in (node, path):
                out.append(record_id)
                break
    return out


def chosen(resolution: Resolution) -> list[str]:
    """The record IDs a clear resolution names, in rank order; ``[]`` when ambiguous."""
    return list(resolution.ids)


def candidate_lines(resolution: Resolution) -> list[str]:
    """The candidates in the owner's terms, and the question (sp5 5)."""
    lines = [f"\"{resolution.query}\" could mean:"]
    for n, item in enumerate(resolution.items, start=1):
        what = f"{item.ref} \"{item.title}\"" if item.kind == "record" else item.ref
        lines.append(f"  {n}. {what} ({item.reason})")
    lines.append("which one do you mean? (answer with its words, its title or its ID)")
    return lines


def resolution_lines(resolution: Resolution) -> list[str]:
    if resolution.how == "none":
        return [f"nothing in plumb's records matches \"{resolution.query}\"; try other words, "
                "a file path or a record ID"]
    if resolution.ambiguous:
        return candidate_lines(resolution)
    lines = [f"\"{resolution.query}\" means:"]
    for item in resolution.items:
        what = f"{item.ref} \"{item.title}\"" if item.kind == "record" else item.ref
        lines.append(f"  {what} ({item.reason}, score {item.score:.2f})")
    return lines


def as_dict(resolution: Resolution) -> dict[str, Any]:
    return {"query": resolution.query, "how": resolution.how,
            "ambiguous": resolution.ambiguous, "ids": list(resolution.ids),
            "items": [{"ref": i.ref, "kind": i.kind, "title": i.title, "score": i.score,
                       "reason": i.reason} for i in resolution.items]}
