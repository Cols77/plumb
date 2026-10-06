"""Rewriting references for a renumber (sp6 5.3). Pure text functions, no git.

A reference is rewritten when the incoming side introduced it: it is in the incoming
(``theirs``) version of a file and not in the merge base's version. A reference our side
introduced still names the old ID. When both sides introduced the same reference, both stay:
the old ID for ours, the new ID for the incoming record. The places:

- the incoming record itself (``incoming_record``): every reference, since the whole file
  is the incoming side's;
- frontmatter references in records: ``links[].to``, ``feature``, ``requirements``,
  ``members``, ``supersedes``, ``decides`` and any other field holding an ID or a list of
  IDs, and example references ``SR-070/EX-2`` in any string field;
- body wikilinks ``[[SR-070]]`` and ``[[SR-070|title]]``;
- test markers ``@pytest.mark.sr("SR-070")`` (``markers``);
- ``.plumb/claims.yaml`` baseline entries naming an incoming NC (``claims``);
- ``SR:`` trailers of the pending commit message (``trailers``).

``mapping`` is ``{old ID: new ID}``. Every function returns ``(new text, references
rewritten)``.
"""

from __future__ import annotations

import ast
import copy
import re
from collections.abc import Iterator, Mapping
from typing import Any

from plumb.model import RecordError, load_yaml, split_frontmatter

_ID = r"(?:INT|SR|DEC|FEAT|NC|IC)-\d+"


def token(record_id: str) -> re.Pattern[str]:
    """``record_id`` as a whole token (``SR-070`` matches neither ``SR-0701`` nor
    ``XSR-070``)."""
    return re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(record_id)}(?![0-9])")


def _example_ref(record_id: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(record_id)}(?=/(?:EX|AC)-\d+)")


def _wikilink(record_id: str) -> re.Pattern[str]:
    return re.compile(rf"\[\[{re.escape(record_id)}(?=[\]|])")


def parse(text: str | None) -> tuple[dict[str, Any], str] | None:
    """``(frontmatter, body)`` of a record file's text, or None when absent or unparsable."""
    if text is None:
        return None
    try:
        yaml_text, body = split_frontmatter(text)
        data = load_yaml(yaml_text)
    except RecordError:
        return None
    return (data, body) if isinstance(data, dict) else None


def dump(data: Mapping[str, Any], body: str) -> str:
    from plumb.store import dump_frontmatter

    return "---\n" + dump_frontmatter(data) + "---\n" + body


# --------------------------------------------------------------------------- the record


def _swap_value(value: Any, mapping: Mapping[str, str]) -> tuple[Any, int]:
    """Every ID string and every example reference inside ``value``, mapped."""
    if isinstance(value, str):
        if value in mapping:
            return mapping[value], 1
        count = 0
        for old, new in mapping.items():
            value, n = _example_ref(old).subn(new, value)
            count += n
        return value, count
    if isinstance(value, list):
        out, total = [], 0
        for item in value:
            item, n = _swap_value(item, mapping)
            out.append(item)
            total += n
        return out, total
    if isinstance(value, dict):
        out_d, total = {}, 0
        for key, item in value.items():
            item, n = _swap_value(item, mapping)
            out_d[key] = item
            total += n
        return out_d, total
    return value, 0


def _swap_body(body: str, mapping: Mapping[str, str]) -> tuple[str, int]:
    count = 0
    for old, new in mapping.items():
        body, n = _wikilink(old).subn("[[" + new, body)
        count += n
    return body, count


def swap_record(data: Mapping[str, Any], body: str,
                mapping: Mapping[str, str]) -> tuple[dict[str, Any], str, int]:
    """The whole record with every reference mapped (its ``id`` included)."""
    new_data, count = _swap_value(dict(data), mapping)
    new_body, n = _swap_body(body, mapping)
    return new_data, new_body, count + n


def incoming_record(text: str, mapping: Mapping[str, str]) -> tuple[str, int]:
    """The incoming record's file under its new ID: every reference mapped, since the
    whole file is the incoming side's. The ``id`` change is not counted."""
    parsed = parse(text)
    if parsed is None:
        raise RecordError("the incoming record cannot be parsed")
    data, body = parsed
    new_data, new_body, count = swap_record(data, body, mapping)
    return dump(new_data, new_body), max(0, count - 1)


# --------------------------------------------------------------------------- other records


def _link_keys(data: Mapping[str, Any] | None) -> set[tuple[str, str]]:
    if not data:
        return set()
    return {(str(link.get("kind")), str(link.get("to"))) for link in data.get("links") or []
            if isinstance(link, dict) and link.get("to") is not None}


def _values(data: Mapping[str, Any] | None, key: str) -> list[str]:
    if not data:
        return []
    value = data.get(key)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _strings(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], str]]:
    """``(path, string)`` of every string inside ``value``; list positions are ``*`` so a
    reordered list does not count as a change."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, (*path, "*"))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key != "links":
                yield from _strings(item, (*path, key))


def _introduced(theirs: set[Any], base: set[Any]) -> set[Any]:
    return theirs - base


class _Sides:
    """What each side introduced relative to the merge base, for one record file."""

    def __init__(self, base: Mapping[str, Any] | None, ours: Mapping[str, Any] | None,
                 theirs: Mapping[str, Any] | None) -> None:
        self.base, self.ours, self.theirs = base or {}, ours or {}, theirs or {}
        self.links_t = _introduced(_link_keys(theirs), _link_keys(base))
        self.links_o = _introduced(_link_keys(ours), _link_keys(base))
        self.strings_t = _introduced(set(_strings(dict(self.theirs))),
                                     set(_strings(dict(self.base))))
        self.strings_o = _introduced(set(_strings(dict(self.ours))),
                                     set(_strings(dict(self.base))))

    def value(self, key: str, old: str) -> tuple[bool, bool]:
        """Whether theirs, ours introduced ``old`` under ``key``."""
        base = old in _values(self.base, key)
        return (old in _values(self.theirs, key) and not base,
                old in _values(self.ours, key) and not base)

    def theirs_link(self, kind: str, old: str) -> Mapping[str, Any] | None:
        for link in self.theirs.get("links") or []:
            if isinstance(link, dict) and str(link.get("kind")) == kind and \
                    str(link.get("to")) == old:
                return link
        return None


_SKIP = {"id", "title", "links"}


def _rewrite_links(data: dict[str, Any], sides: _Sides, old: str, new: str) -> int:
    links = data.get("links")
    if not isinstance(links, list):
        return 0
    out: list[Any] = []
    count = 0
    owed: dict[tuple[str, str], Mapping[str, Any]] = {}  # both introduced: a new-ID copy
    for link in links:
        if not (isinstance(link, dict) and str(link.get("to")) == old):
            out.append(link)
            continue
        key = (str(link.get("kind")), old)
        if key not in sides.links_t:
            out.append(link)
            continue
        if key in sides.links_o:
            if key in owed:  # a second copy in the merged file: it is the incoming one
                moved = dict(link)
                moved["to"] = new
                out.append(moved)
                owed.pop(key)
                count += 1
            else:
                out.append(link)
                owed[key] = sides.theirs_link(*key) or link
            continue
        moved = dict(link)
        moved["to"] = new
        out.append(moved)
        count += 1
    for theirs in owed.values():
        added = copy.deepcopy(dict(theirs))
        added["to"] = new
        out.append(added)
        count += 1
    data["links"] = out
    return count


def _rewrite_fields(data: dict[str, Any], sides: _Sides, old: str, new: str) -> int:
    count = 0
    for key in list(data):
        if key in _SKIP:
            continue
        value = data[key]
        if value == old:
            theirs, ours = sides.value(key, old)
            if theirs and not ours:
                data[key] = new
                count += 1
        elif isinstance(value, list) and old in value:
            theirs, ours = sides.value(key, old)
            if not theirs:
                continue
            if ours:
                if new not in value:
                    position = value.index(old) + 1
                    data[key] = [*value[:position], new, *value[position:]]
                    count += 1
            else:
                data[key] = [new if v == old else v for v in value]
                count += 1
    return count


def _rewrite_strings(value: Any, sides: _Sides, old: str, new: str,
                     path: tuple[Any, ...] = ()) -> tuple[Any, int]:
    pattern = _example_ref(old)
    if isinstance(value, str):
        if not pattern.search(value):
            return value, 0
        if (path, value) in sides.strings_t and (path, value) not in sides.strings_o:
            return pattern.subn(new, value)
        return value, 0
    if isinstance(value, list):
        out, total = [], 0
        for item in value:
            item, n = _rewrite_strings(item, sides, old, new, (*path, "*"))
            out.append(item)
            total += n
        return out, total
    if isinstance(value, dict):
        out_d, total = {}, 0
        for key, item in value.items():
            if key in _SKIP and not path:
                out_d[key] = item
                continue
            item, n = _rewrite_strings(item, sides, old, new, (*path, key))
            out_d[key] = item
            total += n
        return out_d, total
    return value, 0


def _lines(text: str | None) -> set[str]:
    return set(text.splitlines()) if text else set()


def _rewrite_body(body: str, base: str | None, ours: str | None, theirs: str | None,
                  old: str, new: str) -> tuple[str, int]:
    pattern = _wikilink(old)
    if not pattern.search(body):
        return body, 0
    introduced_t = _lines(theirs) - _lines(base)
    introduced_o = _lines(ours) - _lines(base)
    out: list[str] = []
    count = 0
    for line in body.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if pattern.search(bare) and bare in introduced_t and bare not in introduced_o:
            line, n = pattern.subn("[[" + new, line)
            count += n
        out.append(line)
    return "".join(out), count


def record(merged: str, base: str | None, ours: str | None, theirs: str | None,
           mapping: Mapping[str, str]) -> tuple[str, int]:
    """A record file other than the renumbered one, merged: the references the incoming
    side introduced are mapped; ours and the base's stay."""
    parsed = parse(merged)
    if parsed is None:
        return merged, 0
    data, body = parsed
    b, o, t = parse(base), parse(ours), parse(theirs)
    if t is None:
        return merged, 0
    sides = _Sides(b[0] if b else None, o[0] if o else None, t[0])
    count = 0
    for old, new in mapping.items():
        count += _rewrite_links(data, sides, old, new)
        count += _rewrite_fields(data, sides, old, new)
        data, n = _rewrite_strings(data, sides, old, new)
        count += n
        body, n = _rewrite_body(body, b[1] if b else None, o[1] if o else None, t[1],
                                old, new)
        count += n
    if count == 0:
        return merged, 0
    return dump(data, body), count


# --------------------------------------------------------------------------- test markers


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _marker_positions(text: str, old: str) -> list[tuple[int, int, int]]:
    """``(line, start col, end col)`` of every ``mark.sr("<old>")`` argument."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    out: list[tuple[int, int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        if not (name == "mark.sr" or name.endswith(".mark.sr")):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value == old and \
                    arg.end_col_offset is not None and arg.lineno == arg.end_lineno:
                out.append((arg.lineno, arg.col_offset, arg.end_col_offset))
    return out


def markers(merged: str, base: str | None, ours: str | None, theirs: str | None,
            mapping: Mapping[str, str]) -> tuple[str, int]:
    """Test markers on lines the incoming side introduced (and ours did not)."""
    introduced_t = _lines(theirs) - _lines(base)
    introduced_o = _lines(ours) - _lines(base)
    lines = merged.splitlines(keepends=True)
    count = 0
    for old, new in mapping.items():
        positions = _marker_positions("".join(lines), old)
        for lineno, start, end in sorted(positions, key=lambda p: (p[0], -p[1])):
            line = lines[lineno - 1]
            bare = line.rstrip("\r\n")
            if bare not in introduced_t or bare in introduced_o:
                continue
            # ast columns count UTF-8 bytes
            raw = line.encode("utf-8")
            quote = raw[start:start + 1].decode()
            raw = raw[:start] + f"{quote}{new}{quote}".encode() + raw[end:]
            lines[lineno - 1] = raw.decode("utf-8")
            count += 1
    return "".join(lines), count


# --------------------------------------------------------------------------- claims.yaml


def _baseline(text: str | None) -> set[tuple[str, str, str]]:
    if not text:
        return set()
    import yaml

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return set()
    items = data.get("baseline") if isinstance(data, dict) else None
    return {(str(i.get("commit")), str(i.get("path")), str(i.get("nc")))
            for i in items or [] if isinstance(i, dict)}


_FIELD = re.compile(r"\b(commit|path|nc)\s*:\s*['\"]?([^,'\"}\s]+)")


def claims(merged: str, base: str | None, ours: str | None, theirs: str | None,
           mapping: Mapping[str, str]) -> tuple[str, int]:
    """Baseline entries the incoming side added that name an incoming NC."""
    introduced = (_baseline(theirs) - _baseline(base)) - (_baseline(ours) - _baseline(base))
    if not introduced:
        return merged, 0
    lines = merged.splitlines(keepends=True)
    count = 0
    # each baseline item: a "- " line and its continuation lines (more indented)
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("- "):
            i += 1
            continue
        indent = len(lines[i]) - len(lines[i].lstrip())
        j = i + 1
        while j < len(lines) and lines[j].strip() and \
                len(lines[j]) - len(lines[j].lstrip()) > indent and \
                not lines[j].lstrip().startswith("- "):
            j += 1
        item = dict(_FIELD.findall("".join(lines[i:j])))
        key = (item.get("commit", ""), item.get("path", ""), item.get("nc", ""))
        old = key[2]
        if key in introduced and old in mapping:
            pattern = token(old)
            for k in range(i, j):
                lines[k], n = pattern.subn(mapping[old], lines[k])
                count += n
        i = j
    return "".join(lines), count


# --------------------------------------------------------------------------- trailers


_TRAILER = re.compile(r"^SR:.*$", re.MULTILINE)


def trailers(message: str, mapping: Mapping[str, str]) -> tuple[str, int]:
    """``SR:`` trailer lines of the pending commit message, mapped to the new IDs."""
    count = 0

    def swap(match: re.Match[str]) -> str:
        nonlocal count
        line = match.group(0)
        for old, new in mapping.items():
            line, n = token(old).subn(new, line)
            count += n
        return line

    return _TRAILER.sub(swap, message), count
