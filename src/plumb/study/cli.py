"""``plumb study add|list|candidates|mark`` (SR-292, SR-293).

``add --title --why --file [--topic]`` writes a study of the session's open intent loop, for its
current step, refusing a second one for that step; ``list`` prints the studies; ``candidates``
prints what the agent picks a study from: the understanding picture, the owner's prompts so far,
the open conflicts, the loop's records and the decisions that matter; ``mark <slug>
opened|known|deeper`` is the room's own action, also open to the owner's terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from plumb import study
from plumb.cliutil import EXIT_FINDINGS, EXIT_USAGE, add_common, emit, resolve_root

PROMPTS = 20


def _open_loop(root: Path, args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    from plumb.understand import cmd_intent

    session = cmd_intent._session(args, root)
    found = [(p, d) for p, d in cmd_intent.loops(root, session) if d.get("step") != "proven"]
    if not session or not found:
        raise LookupError("no open intent loop in this session: studies belong to a loop")
    return found[-1]


def _prompts(core: Any) -> list[str]:
    """The owner's prompts so far, newest last (the picture starts from them, SR-292 EX-4)."""
    import json

    from plumb.approvals import is_owner_entry

    out = []
    for line in core.paths.prompt_lines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and is_owner_entry(entry) and entry.get("text"):
            out.append(str(entry["text"]))
    # shortcut: the newest PROMPTS only; read the transcripts if the picture needs older ones
    return out[-PROMPTS:]


def _conflicts(core: Any) -> list[dict[str, Any]]:
    """The intent conflicts waiting for the owner's choice: a study may lay out both sides,
    choosing nothing (DEC-154)."""
    from plumb.mergedriver import conflicts

    out = [{"ic": c.ic, "record": c.record, "title": c.title, "sides": list(c.labels)}
           for c in conflicts.open_conflicts(core)]
    try:
        from plumb.awareness.answer import early_decisions

        index = core.index()
        out += [{"ic": None, "record": e.record, "decision": e.dec,
                 "title": index[e.record].title} for e in early_decisions(index)
                if e.record in index and core.status([e.dec])[e.dec].confirmation != "confirmed"]
    except ImportError:
        pass
    return out


def candidates(core: Any, root: Path, loop: dict[str, Any], loop_id: str) -> dict[str, Any]:
    from plumb.understand import cmd_intent

    index = core.index()
    intent = loop.get("intent")
    ids = {intent, *(cmd_intent.requirements_of(core, intent) if intent in index else [])} - {None}
    picture = study.picture(root)
    held = study.studies(root)
    return {
        "loop": {"id": loop_id, "intent": intent, "step": loop.get("step"),
                 "has_study": any(s["loop"] == loop_id and s["step"] == loop.get("step")
                                  for s in held)},
        "picture": picture,
        "known": picture["knows"],       # propose nothing on these (SR-292 EX-1, SR-293 EX-3)
        "deeper": picture["needs"],      # a deeper study is a candidate (EX-2)
        "prompts": _prompts(core),
        "conflicts": _conflicts(core),
        "records": [{"id": i, "title": index[i].title} for i in sorted(ids) if i in index],
        "matters": [{"id": r.id, "title": r.title} for r in index.values()
                    if r.kind == "decision" and r.fields.get("matters") is True
                    and any(link.target.record in ids for link in r.links)],
        "studies": [{k: s.get(k, "") for k in ("slug", "title", "topic", "step", "status")}
                    for s in held],
    }


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="plumb study",
        description="Studies the owner reads in the browser room, at most one per step of an "
                    "intent loop, and the understanding picture they correct. Approves nothing.")
    verbs = parser.add_subparsers(dest="verb", required=True)
    adder = verbs.add_parser("add", help="a study of the open loop's current step")
    adder.add_argument("--title", required=True)
    adder.add_argument("--why", required=True, help="why it is worth reading now")
    adder.add_argument("--file", required=True, help="the body: plain words, optional mermaid")
    adder.add_argument("--topic", default=None, help="what it is about (default: the title)")
    verbs.add_parser("list")
    verbs.add_parser("candidates", help="what to pick this step's study from")
    marker = verbs.add_parser("mark")
    marker.add_argument("slug")
    marker.add_argument("how", choices=tuple(study.MARKS))
    for sub in verbs.choices.values():
        add_common(sub)
        sub.add_argument("--session", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    root = resolve_root(args.root)
    try:
        if args.verb == "add":
            path, loop = _open_loop(root, args)
            body = Path(args.file).read_text(encoding="utf-8")
            slug = study.add(root, title=args.title, why=args.why, body=body, loop=path.stem,
                             step=str(loop.get("step")), topic=args.topic)
            emit({"slug": slug} if args.as_json else f"plumb: new study: {args.title}",
                 args.as_json)
        elif args.verb == "list":
            held = study.studies(root)
            emit([{k: v for k, v in s.items() if k != "body"} for s in held] if args.as_json
                 else [f"{s['status']:7} {s['step']:8} {s['title']} ({s['slug']})" for s in held]
                 or ["plumb: no study yet"], args.as_json)
        elif args.verb == "candidates":
            from plumb.api import open_core

            path, loop = _open_loop(root, args)
            found = candidates(open_core(root), root, loop, path.stem)
            if args.as_json:
                emit(found, True)
            else:
                for key, value in found.items():
                    print(f"{key}: {value}")
        else:
            study.mark(root, args.slug, args.how)
            print(f"plumb: study {args.slug}: {args.how}")
    except (LookupError, ValueError, OSError) as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_FINDINGS if isinstance(exc, LookupError) else EXIT_USAGE
    return 0
