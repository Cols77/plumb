"""Small, comment-preserving updates of ``.iaso/config.yaml`` (sp2 7.3, 8.2).

Only the named top-level section is rewritten (its other keys kept); every other line, the
commented template included, stays byte for byte.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _load(text: str) -> dict[str, Any]:
    import yaml

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        data = {}
    return data if isinstance(data, dict) else {}


def _merge(base: Any, changes: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base) if isinstance(base, Mapping) else {}
    for key, value in changes.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _without(base: Any, drop: Mapping[str, Any]) -> Any:
    """``base`` less the keys ``drop`` names: a mapping value recurses, a collection of
    names removes those keys of the nested mapping, anything else removes the key itself."""
    if not isinstance(base, Mapping):
        return base
    out = dict(base)
    for key, inner in drop.items():
        if isinstance(inner, Mapping):
            if key in out:
                out[key] = _without(out[key], inner)
        elif isinstance(inner, (list, tuple, set, frozenset)):
            if isinstance(out.get(key), Mapping):
                out[key] = {k: v for k, v in out[key].items() if k not in inner}
        else:
            out.pop(key, None)
    return out


def update_section(root: Path, section: str, changes: Mapping[str, Any], *,
                   drop: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Merge ``changes`` into the top-level ``section`` of ``.iaso/config.yaml`` and return
    the section's new value. ``drop`` names keys removed from the section before the merge
    (``{"jev": ["base_url"]}`` removes ``section.jev.base_url``)."""
    import yaml

    path = Path(root) / ".iaso" / "config.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    value = _merge(_without(_load(text).get(section), drop or {}), changes)
    lines = text.splitlines(keepends=True)
    start = next((n for n, line in enumerate(lines)
                  if re.match(rf"^{re.escape(section)}\s*:", line)), None)
    if start is not None:
        end = start + 1
        while end < len(lines) and (lines[end].startswith((" ", "\t"))
                                    or not lines[end].strip()):
            end += 1
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1  # keep the blank lines that separate the next section
        del lines[start:end]
        at = start
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        at = len(lines)
    block = yaml.safe_dump({section: value}, sort_keys=False, default_flow_style=False,
                           allow_unicode=True, width=100)
    lines[at:at] = [block]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8", newline="\n")
    return value
