"""``merge_texts``: a record file merged field by field against the merge base (sp6 7.3).

Pure apart from ``git merge-file`` on the Markdown bodies (and on a whole file whose side
cannot be parsed): no repository, no record index, no log. The caller passes ``reserve_ic``,
called only when an intent conflict is written.

Rules (every field compared as parsed values, so formatting never conflicts):

- unchanged on both sides keeps the base; changed on one side takes it; changed identically
  on both takes it;
- changed differently on both: ``links`` three-way set merge (never a conflict);
  string lists three-way set merge (a conflict only when both sides rewrote one item);
  ``examples`` per example (a clashing new ``EX-n`` from theirs renumbered, with theirs's
  added links that name it); the body through ``git merge-file``; anything else is a
  conflict on that field. A conflict keeps ours's value and writes a ``conflict`` block.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from plumb.contracts import DriverResult
from plumb.model import RecordError, load_yaml, record_hash, split_frontmatter
from plumb.normalize import canonical_json, normalize_text
from plumb.present import owner_text

MISSING: Any = object()
STRING_LISTS = ("will", "wont", "assumptions", "alternatives", "requirements", "members")
LINK_KEY = ("kind", "to", "path", "symbol", "test", "example")
_EX_ID = re.compile(r"^([A-Z]+)-(\d+)$")
_PREFIX_KIND = {"INT": "intent", "SR": "requirement", "DEC": "decision", "FEAT": "feature",
                "NC": "nc"}


class _Unparsable(Exception):
    pass


def _parse(text: str) -> tuple[dict[str, Any], str]:
    try:
        yaml_text, body = split_frontmatter(text)
        data = load_yaml(yaml_text)
    except RecordError as exc:
        raise _Unparsable(str(exc)) from exc
    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
        raise _Unparsable("frontmatter is not a record")
    return data, body


def _same(a: Any, b: Any) -> bool:
    if a is MISSING or b is MISSING:
        return a is b
    try:
        return canonical_json(a) == canonical_json(b)
    except (TypeError, ValueError):
        return a == b


def _key(value: Any) -> bytes:
    try:
        return canonical_json(value)
    except (TypeError, ValueError):
        return repr(value).encode("utf-8")


# --------------------------------------------------------------------------- text merges


def text_merge(base: str, ours: str, theirs: str,
               labels: tuple[str, str]) -> tuple[str, bool]:
    """``(text, clean)`` of ``git merge-file -p`` on three texts (conflict markers labelled
    with the sides' names when not clean)."""
    with tempfile.TemporaryDirectory(prefix="plumb-merge-") as tmp:
        names = []
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = os.path.join(tmp, name)
            with open(path, "wb") as handle:
                handle.write(text.encode("utf-8"))
            names.append(path)
        result = subprocess.run(
            ["git", "merge-file", "-p", "-L", labels[0], "-L", "base", "-L", labels[1],
             *names], capture_output=True)
    if result.returncode < 0 or result.returncode > 127:
        raise RuntimeError("git merge-file failed: "
                           + result.stderr.decode("utf-8", "replace").strip())
    return result.stdout.decode("utf-8", "replace"), result.returncode == 0


# --------------------------------------------------------------------------- field rules


def _merge_links(base: list[Any], ours: list[Any], theirs: list[Any],
                 renamed: Mapping[str, str]) -> tuple[list[Any], int]:
    """Three-way set merge keyed by ``LINK_KEY``; theirs's added links that name a renumbered
    example are rewritten (``renamed``). Pins: three-way, ours on divergence. Returns the
    links and the number taken from theirs."""

    def keyed(items: list[Any]) -> dict[tuple[Any, ...], Any]:
        out: dict[tuple[Any, ...], Any] = {}
        for item in items:
            if isinstance(item, Mapping):
                out.setdefault(tuple(_key(item.get(k)) for k in LINK_KEY), item)
        return out

    def rename(item: Any) -> Any:
        if isinstance(item, Mapping) and str(item.get("example")) in renamed:
            return {**item, "example": renamed[str(item["example"])]}
        return item

    theirs = [rename(item) for item in theirs] if renamed else theirs
    b, o, t = keyed(base), keyed(ours), keyed(theirs)
    out: list[Any] = []
    taken = 0
    for key, item in o.items():
        if key in b and key not in t:
            continue  # removed on theirs
        if key in t:
            pin_b = (b.get(key) or {}).get("pin", MISSING) if key in b else MISSING
            pin_o, pin_t = item.get("pin", MISSING), t[key].get("pin", MISSING)
            if _same(pin_o, pin_b) and not _same(pin_t, pin_b):
                item = t[key]
        out.append(item)
    for key, item in t.items():
        if key in o or key in b:
            continue
        out.append(item)
        taken += 1
    return out, taken


def _merge_list(base: list[Any], ours: list[Any], theirs: list[Any]) -> tuple[list[Any], bool]:
    """Three-way set merge keeping the base order, then ours's additions, then theirs's.
    Conflict (``False``) only when both sides removed one item and each added a different
    one."""
    b = {_key(x): x for x in base}
    o = {_key(x): x for x in ours}
    t = {_key(x): x for x in theirs}
    removed_o, removed_t = set(b) - set(o), set(b) - set(t)
    added_o = [k for k in o if k not in b]
    added_t = [k for k in t if k not in b]
    if removed_o & removed_t and set(added_o) - set(added_t) and set(added_t) - set(added_o):
        return list(ours), False
    out = [b[k] for k in b if k not in removed_o and k not in removed_t]
    out += [o[k] for k in added_o]
    out += [t[k] for k in added_t if k not in o]
    return out, True


def _example_number(example_id: str) -> tuple[str, int] | None:
    match = _EX_ID.match(example_id)
    return (match.group(1), int(match.group(2))) if match else None


def _merge_examples(base: list[Any], ours: list[Any], theirs: list[Any],
                    label: str) -> tuple[list[Any], dict[str, dict[str, Any]], dict[str, str],
                                         list[str]]:
    """``(examples, conflicts, renamed, notes)`` per example keyed by ``id``."""

    def keyed(items: list[Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for item in items:
            if isinstance(item, Mapping) and item.get("id") is not None:
                out.setdefault(str(item["id"]), item)
        return out

    b, o, t = keyed(base), keyed(ours), keyed(theirs)
    conflicts: dict[str, dict[str, Any]] = {}
    renamed: dict[str, str] = {}
    notes: list[str] = []
    used = {n for i in (*b, *o, *t) if (n := _example_number(i))}

    def next_free(prefix: str) -> str:
        number = max((n for p, n in used if p == prefix), default=0) + 1
        used.add((prefix, number))
        return f"{prefix}-{number}"

    out: list[Any] = []
    for ex_id, item in o.items():
        in_b, in_t = ex_id in b, ex_id in t
        if in_b and in_t:
            bv, tv = b[ex_id], t[ex_id]
            if _same(item, tv) or _same(tv, bv):
                out.append(item)
            elif _same(item, bv):
                out.append(tv)
                notes.append(f"{ex_id} from {label}")
            else:
                conflicts[f"examples/{ex_id}"] = {"base": bv, "ours": item, "theirs": tv}
                out.append(item)
        elif in_b:  # removed on theirs
            if _same(item, b[ex_id]):
                continue
            conflicts[f"examples/{ex_id}"] = {"base": b[ex_id], "ours": item, "theirs": None}
            out.append(item)
        elif in_t and not _same(item, t[ex_id]):  # added on both, different content
            number = _example_number(ex_id)
            new_id = next_free(number[0]) if number else f"{ex_id}-{label}"
            renamed[ex_id] = new_id
            out.append(item)
        else:
            out.append(item)
    for ex_id, bv in b.items():
        if ex_id in o:
            continue
        if ex_id in t and not _same(t[ex_id], bv):  # removed on ours, changed on theirs
            conflicts[f"examples/{ex_id}"] = {"base": bv, "ours": None, "theirs": t[ex_id]}
    for ex_id, item in t.items():
        if ex_id in b:
            continue
        if ex_id in renamed:
            out.append({**item, "id": renamed[ex_id]})
            notes.append(f"{renamed[ex_id]} from {label} renumbered from {ex_id}")
        elif ex_id not in o:
            out.append(item)
            notes.append(f"{ex_id} from {label}")
    return out, conflicts, renamed, notes


# --------------------------------------------------------------------------- the driver


def _ordered(data: Mapping[str, Any]) -> dict[str, Any]:
    from plumb.store import ordered_frontmatter

    record_id = str(data.get("id", ""))
    kind = _PREFIX_KIND.get(record_id.split("-", 1)[0], "")
    out = ordered_frontmatter(kind, record_id, data)
    if "title" not in data:
        out.pop("title", None)
    if "conflict" in out:  # the conflict block sits last, after the links
        out["conflict"] = out.pop("conflict")
    return out


def render_record(data: Mapping[str, Any], body: str) -> str:
    """A record file's text in the stable key order of ``store.ordered_frontmatter``."""
    from plumb.store import dump_frontmatter

    return "---\n" + dump_frontmatter(_ordered(data)) + "---\n" + body


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _fallback(base: str, ours: str, theirs: str, labels: tuple[str, str],
              record: str, title: str) -> DriverResult:
    text, clean = text_merge(base, ours, theirs, labels)
    notes = () if clean else (owner_text.UNPARSABLE.format(record=record, title=title),)
    return DriverResult(text=text, exit=0 if clean else 1, notes=notes)


def _guess_id(*texts: str) -> tuple[str, str]:
    for text in texts:
        found = re.search(r"^id:\s*['\"]?([A-Z]+-\d+)", text, re.MULTILINE)
        if found:
            title = re.search(r"^title:\s*['\"]?(.*?)['\"]?\s*$", text, re.MULTILINE)
            return found.group(1), title.group(1) if title else ""
    return "this record", ""


def merge_texts(base: str, ours: str, theirs: str, *, labels: tuple[str, str],
                reserve_ic: Callable[[], str]) -> DriverResult:
    """Merge one record file (sp6 7.3 to 7.6). ``labels`` are (ours, theirs)."""
    ours_label, theirs_label = labels
    try:
        o_data, o_body = _parse(ours)
        t_data, t_body = _parse(theirs)
        b_data, b_body = _parse(base) if base.strip() else ({}, "")
    except _Unparsable:
        record, title = _guess_id(ours, theirs, base)
        return _fallback(base, ours, theirs, labels, record, title)
    record = str(o_data.get("id"))
    title = str(o_data.get("title") or t_data.get("title") or "")

    if not base.strip():  # add/add (7.5)
        if _same(o_data, t_data) and normalize_text(o_body) == normalize_text(t_body):
            return DriverResult(text=render_record(o_data, o_body), exit=0)
        return DriverResult(text=ours, exit=1,
                            notes=(owner_text.ADD_ADD.format(record=record),))

    result: dict[str, Any] = {}
    conflicts: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    renamed: dict[str, str] = {}
    keys = list(dict.fromkeys([*b_data, *o_data, *t_data]))
    # examples first: a renumbered example renames theirs's links that name it
    ordered_keys = [k for k in keys if k == "examples"] + [k for k in keys if k != "examples"]
    for key in ordered_keys:
        bv, ov, tv = (d.get(key, MISSING) for d in (b_data, o_data, t_data))
        if key == "links":
            merged_links, taken = _merge_links(
                bv if isinstance(bv, list) else [], ov if isinstance(ov, list) else [],
                tv if isinstance(tv, list) else [], renamed)
            if merged_links:
                result[key] = merged_links
            if taken:
                notes.insert(0, f"links +{taken} from {theirs_label}")
            continue
        if _same(ov, tv) or _same(tv, bv):
            if ov is not MISSING:
                result[key] = ov
            continue
        if _same(ov, bv):
            if tv is not MISSING:
                result[key] = tv
            notes.append(f"{key} from {theirs_label}")
            continue
        lists = all(v is MISSING or isinstance(v, list) for v in (bv, ov, tv))
        if key == "examples" and lists:
            merged, ex_conflicts, renamed, ex_notes = _merge_examples(
                [] if bv is MISSING else bv, [] if ov is MISSING else ov,
                [] if tv is MISSING else tv, theirs_label)
            result[key] = merged
            conflicts.update(ex_conflicts)
            notes.extend(ex_notes)
            continue
        if key in STRING_LISTS and lists:
            merged, clean = _merge_list([] if bv is MISSING else bv,
                                        [] if ov is MISSING else ov,
                                        [] if tv is MISSING else tv)
            result[key] = merged
            if clean:
                added = len([x for x in merged if _key(x) not in
                             {_key(y) for y in ([] if ov is MISSING else ov)}])
                if added:
                    notes.append(f"{key} +{added} from {theirs_label}")
            else:
                conflicts[key] = {"base": None if bv is MISSING else bv, "ours": ov,
                                  "theirs": tv}
            continue
        conflicts[key] = {"base": None if bv is MISSING else bv,
                          "ours": None if ov is MISSING else ov,
                          "theirs": None if tv is MISSING else tv}
        if ov is not MISSING:
            result[key] = ov

    body = o_body
    if normalize_text(o_body) == normalize_text(t_body) or \
            normalize_text(t_body) == normalize_text(b_body):
        body = o_body
    elif normalize_text(o_body) == normalize_text(b_body):
        body = t_body
        notes.append(f"the notes from {theirs_label}")
    else:
        merged_body, clean = text_merge(b_body, o_body, t_body, labels)
        if clean:
            body = merged_body
            notes.append("the notes from both sides")
        else:
            conflicts["body"] = {"base": b_body, "ours": o_body, "theirs": t_body}

    what = ", ".join(notes)
    if not conflicts:
        line = owner_text.MERGED_FIELDS.format(record=record, title=title,
                                               what=what or "no change")
        return DriverResult(text=render_record(result, body), exit=0, notes=(line,),
                            merged=tuple(notes))
    ic = reserve_ic()
    result.pop("conflict", None)
    result["conflict"] = {
        "id": ic,
        "base": record_hash(b_data, b_body),
        "ours": {"label": ours_label, "hash": record_hash(o_data, o_body)},
        "theirs": {"label": theirs_label, "hash": record_hash(t_data, t_body)},
        "fields": conflicts,
        "merged": list(notes),
    }
    line = owner_text.CONFLICT_WRITTEN.format(record=record, title=title, ours=ours_label,
                                              theirs=theirs_label)
    return DriverResult(text=render_record(result, body), exit=0, notes=(line,), conflict=ic,
                        merged=tuple(notes))


def conflicting_fields(result: DriverResult) -> Sequence[str]:
    """The conflicting field names of a driver result (tests and the CLI's ``--json``)."""
    try:
        data, _ = _parse(result.text)
    except _Unparsable:
        return ()
    block = data.get("conflict")
    return tuple((block or {}).get("fields") or ()) if isinstance(block, Mapping) else ()

