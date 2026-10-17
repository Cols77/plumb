"""Studies and the understanding picture (SR-292, SR-293; DEC-152, DEC-154).

A study is ``.plumb/studies/<slug>.md``: frontmatter ``title, topic, step, loop, why, status``
(``new``, ``opened``, ``known``, ``deeper``), then the body in plain words with an optional
mermaid diagram. ``.plumb/understanding.md`` is the picture of what the owner understands of
the system: plain lines ``- knows: <topic>`` and ``- needs: <topic>``, which the owner edits in
the browser room. 'I know this' and 'Go deeper' change a study's status and the picture only:
they are never an answer delivered to a session (DEC-152), and a study about an open conflict
chooses nothing (DEC-154).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

STATUSES = ("new", "opened", "known", "deeper")
MARKS = {"opened": "opened", "known": "known", "deeper": "deeper"}
PICTURE_LIMIT = 65536
_LINE = re.compile(r"^\s*-\s*(knows|needs)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,79}")


def folder(root: Path) -> Path:
    return Path(root) / ".plumb" / "studies"


def picture_path(root: Path) -> Path:
    return Path(root) / ".plumb" / "understanding.md"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _key(topic: str) -> str:
    return " ".join(topic.lower().removesuffix("(deeper)").split())


# --------------------------------------------------------------------------- the picture


def picture_text(root: Path) -> str:
    path = picture_path(root)
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def picture(root: Path) -> dict[str, list[str]]:
    """``{knows, needs}``: the picture's topics; both empty when there is none (SR-292 EX-4)."""
    out: dict[str, list[str]] = {"knows": [], "needs": []}
    for line in picture_text(root).splitlines():
        if match := _LINE.match(line):
            out[match.group(1).lower()].append(match.group(2))
    return out


def save_picture(root: Path, text: str) -> None:
    """The owner's edit of the picture in the room, kept as typed (SR-292 EX-3)."""
    if not isinstance(text, str) or len(text) > PICTURE_LIMIT:
        raise ValueError(f"the understanding is text of at most {PICTURE_LIMIT} characters")
    _write(picture_path(root), text if text.endswith("\n") or not text else text + "\n")


def _set_line(root: Path, kind: str, topic: str) -> None:
    """One line for ``topic``: any earlier knows/needs line of it goes, ``kind`` is added."""
    kept = [line for line in picture_text(root).splitlines()
            if not ((m := _LINE.match(line)) and _key(m.group(2)) == _key(topic))]
    save_picture(root, "\n".join([*kept, f"- {kind}: {topic}"]))


def knows(root: Path, topic: str) -> bool:
    return _key(topic) in {_key(t) for t in picture(root)["knows"]}


# --------------------------------------------------------------------------- studies


def _front(fields: dict[str, Any]) -> str:
    # JSON values are YAML too, and the mod reads them without a YAML parser
    return "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n"
                             for k, v in fields.items()) + "---\n"


def _parse(path: Path) -> dict[str, Any] | None:
    import yaml

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[3:]:
        return None
    head, body = text[4:].split("\n---\n", 1)
    try:
        fields = yaml.safe_load(head)
    except yaml.YAMLError:
        return None
    if not isinstance(fields, dict) or fields.get("status") not in STATUSES:
        return None
    return {**{k: str(v) if v is not None else "" for k, v in fields.items()},
            "slug": path.stem, "body": body}


def studies(root: Path) -> list[dict[str, Any]]:
    """Every study, oldest first (by slug's file time, then name)."""
    base = folder(root)
    paths = sorted(base.glob("*.md"), key=lambda p: (p.stat().st_mtime_ns, p.name)) \
        if base.is_dir() else []
    return [s for p in paths if (s := _parse(p))]


def get(root: Path, slug: str) -> dict[str, Any]:
    if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
        raise LookupError("Unknown study")
    path = folder(root) / f"{slug}.md"
    found = _parse(path) if path.is_file() else None
    if found is None:
        raise LookupError("Unknown study")
    return found


def slug_of(root: Path, title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-") or "study"
    slug, n = base, 2
    while (folder(root) / f"{slug}.md").exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def add(root: Path, *, title: str, why: str, body: str, loop: str, step: str,
        topic: str | None = None) -> str:
    """Write a new study of ``loop``'s ``step``; its slug. At most one per step (SR-293 EX-5),
    and none on a topic the picture says the owner knows (SR-292 EX-1, SR-293 EX-3)."""
    topic = (topic or title).strip()
    if not title.strip() or not body.strip():
        raise ValueError("a study needs a title and a body")
    held = next((s for s in studies(root) if s.get("loop") == loop and s.get("step") == step),
                None)
    if held:
        raise ValueError(f"the {step} step already has its study: {held['title']}")
    if knows(root, topic):
        raise ValueError(f"the owner knows {topic} (the understanding picture): no study")
    slug = slug_of(root, title)
    _write(folder(root) / f"{slug}.md", _front({
        "title": title.strip(), "topic": topic, "step": step, "loop": loop, "why": why.strip(),
        "status": "new"}) + "\n" + body.strip() + "\n")
    return slug


def mark(root: Path, slug: str, how: str) -> dict[str, Any]:
    """``opened`` (read in the room), ``known`` ('I know this') or ``deeper`` ('Go deeper'):
    the study's status and, for the last two, the picture. Nothing else is touched."""
    if how not in MARKS:
        raise ValueError("mark is one of opened, known, deeper")
    study = get(root, slug)
    if how == "opened" and study["status"] != "new":
        return study    # opening again changes nothing
    fields = {k: study.get(k, "") for k in ("title", "topic", "step", "loop", "why")}
    _write(folder(root) / f"{slug}.md",
           _front({**fields, "status": MARKS[how]}) + study["body"])
    if how == "known":
        _set_line(root, "knows", study["topic"] or study["title"])
    elif how == "deeper":
        _set_line(root, "needs", f"{study['topic'] or study['title']} (deeper)")
    return get(root, slug)
