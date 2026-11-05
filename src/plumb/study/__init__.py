"""Studies and the understanding picture (SR-292, SR-293, SR-294; DEC-152, DEC-154, DEC-207).

A study is ``.plumb/studies/<slug>.md``: frontmatter ``title, topic, step, loop, why,
recommend, depth, status``, then the body in plain words with an optional mermaid diagram. It
starts as an idea (DEC-207): a title, one line of why and the depth the agent recommends, with
no body (``idea``). The owner's press in the band accepts it at a depth (``accepted``) or
declines it (``declined``, never proposed again); only an accepted idea is written (``new``),
at the chosen depth, then read (``opened``, ``known``, ``deeper``). A study proposed ahead of
the owner's waiting questions (SR-336) holds their keys in ``serves`` and belongs to no loop step.
A written study keeps the records it was written from (SR-360, DEC-335) in ``records``, each
with its content hash; when one changes, ``changed`` names it and the band offers a rewrite at
the same depth (DEC-336): ``refresh`` is ``asked`` on the owner's yes, ``no`` on 'not now'.

``.plumb/understanding.md`` is the picture of what the owner understands of the system:
plain lines ``- knows: <topic>`` and ``- needs: <topic>``, which the owner edits in the
browser room. 'I know this' and 'Go deeper' change a study's status and the picture only:
they are never an answer delivered to a session (DEC-152), and a study about an open conflict
chooses nothing (DEC-154).
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any

IDEAS = ("idea", "accepted", "declined")
WRITTEN = ("new", "opened", "known", "deeper")
STATUSES = (*IDEAS, *WRITTEN)
UNREAD = ("idea", "accepted", "new")    # proposed, accepted or written, not read yet
DEPTHS = ("md", "diagrams", "video")
OFFERED = DEPTHS
MARKS = {"opened": "opened", "known": "known", "deeper": "deeper"}
PICTURE_LIMIT = 65536
FIRST = "study_first.json"     # the session's 'Study it first' choice (SR-336)
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
    return {**{k: v if isinstance(v, (list, dict)) else _repr_dict(k, v)
               for k, v in fields.items()},
            "slug": path.stem, "body": body}


def _repr_dict(key: str, v: Any) -> Any:
    """A process still running code from before dicts were kept (its ``_parse`` made them
    ``str``) rewrote ``clips`` and ``progress`` as a quoted Python repr; read it back as the
    dict it was, and the next write puts JSON again. Any other value is text."""
    if key in ("clips", "progress") and isinstance(v, str):
        try:
            if isinstance(held := ast.literal_eval(v), dict):
                return held
        except (ValueError, SyntaxError):
            pass
    return str(v) if v is not None else ""


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


def _same(a: dict[str, Any], topic: str, title: str) -> bool:
    return _key(a.get("topic") or a.get("title", "")) == _key(topic) or (
        _key(a.get("title", "")) == _key(title))


def propose(root: Path, *, title: str, why: str, depth: str, loop: str, step: str,
            topic: str | None = None, serves: list[str] | None = None,
            asked: bool = False) -> str:
    """An idea of a study for ``loop``'s ``step`` (SR-293 EX-6): no page is written. At most
    one per step, ideas counted (EX-5); none on a topic the owner knows (SR-292 EX-1, SR-293
    EX-3) or on an idea the owner declined (EX-9). ``serves``: the keys of the waiting
    questions it is studied ahead of (SR-336), whatever the step, one idea waiting at a time.
    ``asked``: the owner asked for it (SR-355): none of those limits, which hold plumb's own
    proposals; the owner still picks the depth."""
    topic = (topic or title).strip()
    if not title.strip() or not why.strip():
        raise ValueError("a study idea needs a title and one line of why")
    if depth not in DEPTHS:
        raise ValueError(f"the recommended depth is one of {', '.join(DEPTHS)}")
    if serves and not asked:
        held = next((s for s in studies(root) if s["status"] == "idea"), None)
        if held:
            raise ValueError(f"the owner has still to choose on the study idea {held['title']}")
    elif not asked and (held := next((s for s in studies(root)
                       if s.get("loop") == loop and s.get("step") == step), None)):
        raise ValueError(f"the {step} step already has its study: {held['title']}")
    if not asked and knows(root, topic):
        raise ValueError(f"the owner knows {topic} (the understanding picture): no study")
    if not asked and any(s["status"] == "declined" and _same(s, topic, title)
                         for s in studies(root)):
        raise ValueError(f"the owner declined a study of {topic}: it is not proposed again")
    slug = slug_of(root, title)
    _write(folder(root) / f"{slug}.md", _front({
        "title": title.strip(), "topic": topic, "step": step, "loop": loop,
        "why": " ".join(why.split()), "recommend": depth, "depth": "", "status": "idea",
        **({"serves": list(serves)} if serves else {})}))
    return slug


def serving(root: Path, key: str) -> dict[str, Any] | None:
    """SR-336 EX-1: the study not read yet (proposed, accepted or written) that serves the
    waiting question ``key``, the newest."""
    return next((s for s in reversed(studies(root)) if s["status"] in UNREAD
                 and key in (s.get("serves") or ())), None)


def first_path(root: Path, session: str) -> Path:
    from plumb.understand import files

    return files.session_dir(Path(root), session) / FIRST


def study_first(root: Path, session: str, slug: str) -> None:
    """SR-336 EX-2: the owner chose 'Study it first': the band's new-study line names this study
    (its press opens the room on it, SR-294) and its questions wait until it is read."""
    from plumb.understand import files

    files.write_json_atomic(first_path(root, session), {"study": slug})


def first_keys(root: Path, session: str) -> set[str]:
    """The questions held back for the study the owner chose to read first, until it is read."""
    from plumb.understand import files

    raw = files.read_json(first_path(root, session))
    slug = raw.get("study") if isinstance(raw, dict) else None
    try:
        found = get(root, slug)
    except LookupError:
        return set()
    return set(found.get("serves") or ()) if found["status"] in UNREAD else set()


def _fields(found: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in found.items() if k not in ("slug", "body", "status")}


def progress(root: Path, slug: str, step: str = "", done: int = 0, total: int = 0, *,
             finish: bool = False) -> None:
    """The band's bar while a study is written, clips rendered and checked included: ``step``,
    ``done`` of ``total``. It goes with ``finish``, when the last clip passes its check, or at
    once when ``add`` writes a study with no clip."""
    found = get(root, slug)
    if found["status"] not in ("accepted", "new") or (
            found["status"] == "new" and not finish and "progress" not in found):
        raise ValueError(f"the study {found['title']} is not being written")
    fields = {k: v for k, v in _fields(found).items() if k != "progress"}
    if not finish:
        if not (0 <= done <= total and total > 0):
            raise ValueError("progress needs 0 <= done <= total and a total above 0")
        fields["progress"] = {"step": step, "done": done, "total": total}
    _write(folder(root) / f"{slug}.md", _front({**fields, "status": found["status"]})
           + found["body"])


def choose(root: Path, slug: str, depth: str | None) -> dict[str, Any]:
    """The owner's choice on an idea (SR-294 EX-7..EX-9): accepted at ``depth``, or declined
    when ``depth`` is None ('not now'). Only the panel's key-checked press calls this."""
    found = get(root, slug)
    if found["status"] != "idea":
        raise ValueError(f"the study {found['title']} is no longer an idea")
    if depth is not None and depth not in OFFERED:
        raise ValueError(f"the depth is one of {', '.join(OFFERED)}")
    _write(folder(root) / f"{slug}.md", _front({
        **_fields(found), "depth": depth or "",
        "status": "accepted" if depth else "declined"}) + found["body"])
    return get(root, slug)


def accepted(root: Path) -> list[dict[str, Any]]:
    """The ideas the owner accepted and the agent has still to write, oldest first."""
    return [s for s in studies(root) if s["status"] == "accepted"]


def _write_it(s: dict[str, Any]) -> str:
    return (f"write it now: plumb study gather {s['slug']}, then plumb study add {s['slug']} "
            "--records <the IDs you drew on> --file <body.md>")


def accepted_lines(root: Path) -> list[str]:
    """What the agent is told at its next turn (SR-294 EX-8): each accepted idea at its depth,
    and each study the owner asked to rewrite, at the same depth (SR-360 EX-2)."""
    return [f"plumb: the owner accepted the study idea '{s['title']}' at depth {s['depth']}"
            f"{' (no diagram)' if s['depth'] == 'md' else ''}: {_write_it(s)}"
            for s in accepted(root)] + [
        f"plumb: the owner asked to rewrite the study '{s['title']}' at depth {s['depth']}: "
        f"{s['changed']} changed; {_write_it(s)}"
        for s in studies(root) if s["status"] in WRITTEN and s.get("refresh") == "asked"] + [
        f"plumb: the clip {c} of '{s['title']}' rendered: have an independent reviewer agent "
        f"check it: plumb study frames {s['slug']} --clip {c}, then plumb study check "
        f"{s['slug']} --clip {c} --pass|--fail --finding '<severity>: ...' --reviewer <agent>"
        for s in studies(root) for c, held in (s.get("clips") or {}).items()
        if isinstance(held, dict) and held.get("state") == "checking"]


NO_RECORD = "No record in plumb covers this topic."

# report-604e5ebf: the room's text column is about 580 px wide; a flowchart past this many
# boxes is drawn far wider or taller and shrinks to unreadable text. Split it instead.
DIAGRAM_NODES = 12
_MERMAID = re.compile(r"```mermaid[^\n]*\n(.*?)```", re.S)
_SHAPE = re.compile(r"[\[\(\{][^\[\]\(\)\{\}]*[\]\)\}]")
_ARROW = re.compile(r"<?(?:-{2,}|={2,}|-\.+-?|~{3,})(?:>|[ox](?=[\s\[(]|$))?")
# shortcut: an edge text written '-- text -->' counts its words as boxes (overcounts);
# '-->|text|' is read right
_KEYWORDS = {"subgraph", "end", "direction", "classDef", "class", "style", "linkStyle",
             "click", "flowchart", "graph", "%%"}


def diagram_nodes(code: str) -> int:
    """The boxes of a mermaid flowchart (0 for other kinds), read from its node ids."""
    lines = code.strip().splitlines()
    if not lines or lines[0].split()[0] not in ("flowchart", "graph"):
        return 0
    ids: set[str] = set()
    for line in lines[1:]:
        text = re.sub(r'"[^"]*"', "", line.split("%%")[0]).strip()
        if not text or text.split()[0] in _KEYWORDS:
            continue
        while (shorter := _SHAPE.sub("", text)) != text:
            text = shorter
        text = re.sub(r"\|[^|]*\|", " ", text)
        text = re.sub(r":::[\w-]+", "", _ARROW.sub(" & ", text))
        ids.update(t for t in re.split(r"[\s&;]+", text) if re.fullmatch(r"[\w$][\w$-]*", t))
    return len(ids)


def _check_diagrams(body: str) -> None:
    for n, block in enumerate(_MERMAID.findall(body), 1):
        if (count := diagram_nodes(block)) > DIAGRAM_NODES:
            raise ValueError(
                f"diagram {n} has {count} boxes: the room shrinks a flowchart past "
                f"{DIAGRAM_NODES} boxes to unreadable text; split it into smaller diagrams")


def add(root: Path, slug: str, body: str, records: list[dict[str, str]] | None = None) -> str:
    """Write the study of an idea the owner accepted, at the depth they chose (SR-293 EX-7,
    EX-8): never before acceptance, and 'Markdown only' has no diagram. ``records``: the
    records it is written from, ``{id, title, hash}`` (SR-360 EX-1), listed at its end; with
    none it says no record covers the topic (EX-3). A study the owner asked to rewrite is
    written again at its depth."""
    found = get(root, slug)
    if found["status"] != "accepted" and found.get("refresh") != "asked":
        raise ValueError(f"the study {found['title']} is not accepted by the owner"
                         + (" yet: propose it and wait" if found["status"] == "idea" else ""))
    if not body.strip():
        raise ValueError("a study needs a body")
    from plumb.study import video

    # SR-370: the depth is a ceiling on the mix the agent composes (DEC-362)
    if found.get("depth") == "md" and "```mermaid" in body:
        raise ValueError("the owner chose Markdown only: the study has no diagram")
    _check_diagrams(body)
    clips = video.clips_in(body)
    if clips and found.get("depth") != "video":
        raise ValueError(f"the owner chose {found.get('depth')}: the study has no video block "
                         f"(```video {clips[0]})")
    for c in clips:
        if not video.CLIP.fullmatch(c) or clips.count(c) > 1:
            raise ValueError("each video block names one clip once, in lower-case letters, "
                             f"digits and dashes: {c!r}")
    records = list(records or [])
    head = "" if records or NO_RECORD in body else NO_RECORD + "\n\n"
    tail = ("\n\nWritten from: " + ", ".join(f"{r['id']} {r['title']}" for r in records)
            if records else "")
    fields = {**_fields(found), "records": records, "changed": "", "refresh": ""}
    if not clips:      # with clips the bar goes when the last passes its check (video.check)
        fields.pop("progress", None)
    _write(folder(root) / f"{slug}.md",
           _front({**fields, "status": "new"}) + "\n" + head + body.strip() + tail + "\n")
    return slug


def out_of_date(root: Path, index: Any) -> list[str]:
    """SR-360 EX-2: the written studies one of whose records changed or went, by slug; their
    ``changed`` names those records' titles for the room and the band. A new change asks the
    owner again (``refresh`` cleared); nothing is rewritten here (DEC-336)."""
    out = []
    for s in studies(root):
        held = [r for r in s.get("records") or () if isinstance(r, dict)]
        if s["status"] not in WRITTEN or not held:
            continue
        changed = ", ".join(str(r.get("title") or r.get("id")) for r in held
                            if r.get("id") not in index or index[r["id"]].hash != r.get("hash"))
        if changed:
            out.append(s["slug"])
        if changed != s.get("changed", ""):
            _write(folder(root) / f"{s['slug']}.md", _front({
                **_fields(s), "changed": changed, "refresh": "", "status": s["status"]})
                + s["body"])
    return out


def refresh(root: Path, slug: str, yes: bool) -> dict[str, Any]:
    """The owner's press on an out-of-date study (DEC-336): yes asks the agent to rewrite it
    at the same depth; 'not now' leaves it marked. Only the band's key-checked press."""
    found = get(root, slug)
    if not found.get("changed"):
        raise ValueError(f"the study {found['title']} is not out of date")
    _write(folder(root) / f"{slug}.md", _front({
        **_fields(found), "refresh": "asked" if yes else "no", "status": found["status"]})
        + found["body"])
    return get(root, slug)


def mark(root: Path, slug: str, how: str) -> dict[str, Any]:
    """``opened`` (read in the room), ``known`` ('I know this') or ``deeper`` ('Go deeper'):
    the study's status and, for the last two, the picture. Nothing else is touched."""
    if how not in MARKS:
        raise ValueError("mark is one of opened, known, deeper")
    study = get(root, slug)
    if study["status"] not in WRITTEN:
        raise LookupError(f"the study {study['title']} is not written yet")
    if how == "opened" and study["status"] != "new":
        return study    # opening again changes nothing
    _write(folder(root) / f"{slug}.md",
           _front({**_fields(study), "status": MARKS[how]}) + study["body"])
    if how == "known":
        _set_line(root, "knows", study["topic"] or study["title"])
    elif how == "deeper":
        _set_line(root, "needs", f"{study['topic'] or study['title']} (deeper)")
    return get(root, slug)
