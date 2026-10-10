"""Check an answer against a job kind's schema (ENGINE). A small subset of JSON Schema is
enough for the answers plumb asks for: ``type``, ``properties``, ``required``, ``items``,
``enum``, ``minimum``, ``maximum``, ``additionalProperties`` and ``minItems``. A schema with
none of these (the kinds' placeholders) accepts any mapping. Standard library only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_TYPES: dict[str, tuple[type, ...]] = {
    "object": (Mapping,), "array": (list, tuple), "string": (str,),
    "boolean": (bool,), "null": (type(None),),
}


def _is(value: Any, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES.get(name, ()))


def problems(value: Any, schema: Mapping[str, Any] | None, path: str = "answer") -> list[str]:
    """Plain sentences naming what in ``value`` the ``schema`` does not allow (empty = fine)."""
    found: list[str] = []
    if not schema:
        return found
    wanted = schema.get("type")
    if wanted is not None:
        names = [wanted] if isinstance(wanted, str) else list(wanted)
        if not any(_is(value, n) for n in names):
            return [f"{path} must be {' or '.join(names)}"]
    if "enum" in schema and value not in list(schema["enum"]):
        found.append(f"{path} must be one of {list(schema['enum'])}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            found.append(f"{path} must be at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            found.append(f"{path} must be at most {schema['maximum']}")
    if isinstance(value, Mapping):
        props = schema.get("properties") or {}
        for name in schema.get("required") or ():
            if name not in value:
                found.append(f"{path} lacks {name}")
        for name, sub in props.items():
            if name in value and isinstance(sub, Mapping):
                found.extend(problems(value[name], sub, f"{path}.{name}"))
        if schema.get("additionalProperties") is False:
            found.extend(f"{path} has an unexpected {name}" for name in value
                         if name not in props)
    elif isinstance(value, Sequence) and not isinstance(value, str):
        if "minItems" in schema and len(value) < schema["minItems"]:
            found.append(f"{path} needs at least {schema['minItems']} items")
        items = schema.get("items")
        if isinstance(items, Mapping):
            for n, item in enumerate(value):
                found.extend(problems(item, items, f"{path}[{n}]"))
    return found
