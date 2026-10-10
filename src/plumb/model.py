"""Record parsing: Markdown with YAML frontmatter (spec 5.1 to 5.4).

Extracted and simplified from pi-agent-factory's ``coherence/register/register.py``: the
frontmatter split is done by hand (no ``python-frontmatter`` dependency) and the consent
fields are gone. Identity comes from the frontmatter ``id``, never from the filename.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from plumb.contracts import ID_RE, Example, Link, Pin, Record, Target
from plumb.normalize import canonical_json, normalize_text, sha256_bytes

ID_PATTERN = re.compile(ID_RE)
EXAMPLE_ID = re.compile(r"^(?:EX|AC)-\d+$")
PREFIX_KIND = {"INT": "intent", "SR": "requirement", "DEC": "decision", "FEAT": "feature",
               "NC": "nc"}
_ID_FIELDS = ("id", "title", "links")


class RecordError(ValueError):
    """A record file that cannot be parsed into a record."""


def kind_of(record_id: str) -> str | None:
    """The record kind of a well-formed ID, else None."""
    if not isinstance(record_id, str) or not ID_PATTERN.match(record_id):
        return None
    return PREFIX_KIND[record_id.split("-", 1)[0]]


def split_frontmatter(text: str) -> tuple[str, str]:
    """``(yaml_text, body)``; the frontmatter sits between the first two ``---`` lines."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n").rstrip() != "---":
        raise RecordError("no frontmatter: the file must start with a '---' line")
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n").rstrip() == "---":
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    raise RecordError("frontmatter is not closed by a '---' line")


def load_yaml(text: str) -> Any:
    import yaml

    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    try:
        return yaml.load(text, Loader=loader)
    except yaml.YAMLError as exc:
        raise RecordError(f"malformed frontmatter: {exc}".splitlines()[0]) from exc


def record_hash(frontmatter: Mapping[str, Any], body: str) -> str:
    """Spec 5.4: every frontmatter field except ``links``, plus the normalized body."""
    fields = {k: v for k, v in frontmatter.items() if k != "links"}
    return sha256_bytes(canonical_json({"fields": fields, "body": normalize_text(body)}))


def parse_target(entry: Mapping[str, Any]) -> Target:
    def text(key: str) -> str | None:
        value = entry.get(key)
        return None if value is None else str(value)

    return Target(record=text("to"), path=text("path"), symbol=text("symbol"), test=text("test"))


def parse_link(source: str, index: int, entry: Any) -> Link:
    if not isinstance(entry, Mapping):
        raise RecordError(f"link {source}#{index} is not a mapping")
    pin = None
    raw_pin = entry.get("pin")
    if isinstance(raw_pin, Mapping) and raw_pin.get("from") and raw_pin.get("to"):
        pin = Pin(source=str(raw_pin["from"]), target=str(raw_pin["to"]))
    example = entry.get("example")
    return Link(source=source, index=index, kind=str(entry.get("kind", "")),  # type: ignore[arg-type]
                target=parse_target(entry), example=None if example is None else str(example),
                pin=pin)


def link_to_dict(link: Link) -> dict[str, Any]:
    """The YAML shape of a link (spec 5.2), keys in a stable order."""
    out: dict[str, Any] = {"kind": link.kind}
    target = link.target
    if target.record is not None:
        out["to"] = target.record
    if target.path is not None:
        out["path"] = target.path
    if target.symbol is not None:
        out["symbol"] = target.symbol
    if target.test is not None:
        out["test"] = target.test
    if link.example is not None:
        out["example"] = link.example
    if link.pin is not None:
        out["pin"] = {"from": link.pin.source, "to": link.pin.target}
    return out


def parse_examples(record_id: str, raw: Any) -> tuple[Example, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise RecordError(f"{record_id}: examples must be a list")
    out: list[Example] = []
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping) or not EXAMPLE_ID.match(str(item.get("id", ""))):
            raise RecordError(f"{record_id}: example {i} needs an id of the form EX-n or AC-n")
        out.append(Example(id=str(item["id"]), given=str(item.get("given") or ""),
                           when=str(item.get("when") or ""), then=str(item.get("then") or ""),
                           criterion=str(item.get("criterion") or "")))
    return tuple(out)


def parse_record(text: str, path: str, data: Any = None) -> Record:
    """Parse one record file's text. Raises RecordError on any malformed part.

    ``data`` is the already parsed frontmatter (the store's index cache); YAML is parsed
    only when it is None."""
    yaml_text, body = split_frontmatter(text)
    if data is None:
        data = load_yaml(yaml_text)
    return record_from_parts(data, body, path)


def record_from_parts(data: Any, body: str, path: str, digest: str = "") -> Record:
    """The record of already parsed frontmatter and body (``digest``: its known hash, which
    the store's index cache keeps, else computed). Raises RecordError on any malformed part."""
    if not isinstance(data, dict):
        raise RecordError("frontmatter must be a mapping")
    record_id = data.get("id")
    kind = kind_of(record_id) if isinstance(record_id, str) else None
    if kind is None:
        raise RecordError(f"malformed id: {record_id!r}")
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise RecordError(f"{record_id}: missing title")
    raw_links = data.get("links") or []
    if not isinstance(raw_links, list):
        raise RecordError(f"{record_id}: links must be a list")
    links = tuple(parse_link(record_id, i, entry) for i, entry in enumerate(raw_links))
    examples = parse_examples(record_id, data.get("examples")) if kind == "requirement" else ()
    fields = {k: v for k, v in data.items() if k not in _ID_FIELDS}
    return Record(id=record_id, kind=kind, title=title, path=path,  # type: ignore[arg-type]
                  fields=fields, body=body, links=links, examples=examples,
                  hash=digest or record_hash(data, body))
