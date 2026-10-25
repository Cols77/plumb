"""``plumb study propose|gather|progress|add|list|candidates|mark`` (SR-292..SR-294, SR-360; DEC-207).

``propose --title --why --depth md|diagrams|video [--topic]`` records an idea of a study for
the session's open intent loop's current step (no page), refusing a second one for that step;
the owner accepts it at a depth or declines it in the band (``plumb mod study``); with ``--for
<question key>...`` it is studied ahead of those waiting judge questions, loop or not (SR-336),
and while questions wait no other study is proposed. ``gather <slug|topic>`` prints the
records on the topic, with their examples and test states, that the study is written from
(SR-360); ``add <slug> --file --records <IDs>`` writes an accepted idea's study at the chosen
depth, keeping those records and their hashes; ``list`` prints the studies and
ideas; ``candidates``
prints what the agent picks a study from: the understanding picture, the judge questions
waiting on a topic the owner does not know, the owner's prompts so far, the open conflicts, the
loop's records and the decisions that matter; ``mark <slug>
opened|known|deeper`` is the room's own action, also open to the owner's terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from plumb import study
from plumb.cliutil import EXIT_FINDINGS, EXIT_USAGE, add_common, emit, resolve_root
from plumb.study import video

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


def _waiting(core: Any, root: Path, session: str | None) -> list[dict[str, Any]]:
    """SR-336 EX-1: the session's judge questions waiting for the owner on a topic (their
    principle, else their header) the picture does not say they know."""
    from plumb.understand import judge

    asked = judge.open_questions(core, session) if session else []
    out = [{"key": q.get("key"), "question": q.get("question"),
            "topic": q.get("principle") or q.get("header") or ""} for q in asked]
    return [q for q in out if not study.knows(root, q["topic"])]


def gather(core: Any, root: Path, words: str) -> dict[str, Any]:
    """SR-360 EX-1, EX-3: the records on a study's topic (a study's slug reads as its topic),
    matched as ``plumb resolve`` does, with the decisions on them: each with its statement,
    examples, test states and hash; ``line`` says when no record covers it."""
    from plumb.present.cards import example_text, test_states
    from plumb.present.resolve import resolve

    try:
        found = study.get(root, words)
        words = found.get("topic") or found["title"]
    except LookupError:
        pass
    index = core.index()
    ids = [i.ref for i in resolve(core, words).items if i.kind == "record"]
    ids += [r.id for r in index.values() if r.kind == "decision" and r.id not in ids
            and any(link.kind == "decides" and link.target.record in ids for link in r.links)]
    out = []
    for i in ids:
        record = index[i]
        ends = [link.target.test or link.target.path for link in record.links
                if link.kind == "verified_by" and (link.target.test or link.target.path)]
        out.append({"id": i, "kind": record.kind, "title": record.title, "hash": record.hash,
                    "statement": str(record.fields.get("statement") or record.fields.get(
                        "chosen") or ""),
                    "examples": [example_text(e) for e in record.examples],
                    "tests": test_states(core, ends) if ends else {}})
    return {"topic": words, "records": out,
            "line": "" if out else f"no record covers {words}: the study says so"}


def candidates(core: Any, root: Path, loop: dict[str, Any], loop_id: str,
               session: str | None = None) -> dict[str, Any]:
    from plumb.understand import cmd_intent

    index = core.index()
    intent = loop.get("intent")
    ids = {intent, *(cmd_intent.requirements_of(core, intent) if intent in index else [])} - {None}
    picture = study.picture(root)
    held = study.studies(root)
    return {
        "loop": {"id": loop_id, "intent": intent, "step": loop.get("step"),
                 "has_study": any(s["loop"] == loop_id and s["step"] == loop.get("step")
                                  for s in held)},     # an idea counts (SR-293 EX-5)
        "picture": picture,
        "known": picture["knows"],       # propose nothing on these (SR-292 EX-1, SR-293 EX-3)
        "deeper": picture["needs"],      # a deeper study is a candidate (EX-2)
        # SR-336: study ahead of these first (propose --for their keys)
        "waiting": _waiting(core, root, session),
        "prompts": _prompts(core),
        "conflicts": _conflicts(core),
        "records": [{"id": i, "title": index[i].title} for i in sorted(ids) if i in index],
        "matters": [{"id": r.id, "title": r.title} for r in index.values()
                    if r.kind == "decision" and r.fields.get("matters") is True
                    and any(link.target.record in ids for link in r.links)],
        "studies": [{k: s.get(k, "") for k in ("slug", "title", "topic", "step", "status",
                                                "depth")} for s in held],
        # the owner said 'not now' to these: never propose them again (SR-293 EX-9)
        "declined": [s.get("topic") or s["title"] for s in held if s["status"] == "declined"],
        # accepted ideas still to write, at the owner's depth (SR-294 EX-8)
        "accepted": [{k: s.get(k, "") for k in ("slug", "title", "depth")}
                     for s in study.accepted(root)],
    }


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="plumb study",
        description="Studies the owner reads in the browser room, at most one per step of an "
                    "intent loop, and the understanding picture they correct. Approves nothing.")
    verbs = parser.add_subparsers(dest="verb", required=True)
    proposer = verbs.add_parser("propose", help="an idea of a study for the open loop's step")
    proposer.add_argument("--title", required=True)
    proposer.add_argument("--why", required=True, help="one line: why it is worth reading now")
    proposer.add_argument("--depth", required=True, choices=study.DEPTHS,
                          help="the depth you recommend; the owner chooses")
    proposer.add_argument("--topic", default=None, help="what it is about (default: the title)")
    proposer.add_argument("--for", dest="serves", nargs="+", default=[], metavar="KEY",
                          help="the keys of the waiting questions it is studied ahead of")
    proposer.add_argument("--asked", action="store_true",
                          help="the owner asked for it: any time, outside every limit (SR-355)")
    adder = verbs.add_parser("add", help="write the study of an idea the owner accepted")
    adder.add_argument("slug")
    adder.add_argument("--file", required=True,
                       help="the body: plain words; mermaid from depth diagrams, ```video clips at video")
    adder.add_argument("--records", nargs="*", default=[], metavar="ID",
                       help="the records it is written from (plumb study gather)")
    progresser = verbs.add_parser("progress", help="the band's bar while an accepted study is written")
    progresser.add_argument("slug")
    progresser.add_argument("--step", default="", help="what you are doing, in a few words")
    progresser.add_argument("--done", type=int, default=0)
    progresser.add_argument("--total", type=int, default=0)
    progresser.add_argument("--finish", action="store_true", help="the study is done: end the bar")
    gatherer = verbs.add_parser("gather", help="the records a study on a topic is written from")
    gatherer.add_argument("topic", help="the study's slug, or the topic in plain words")
    boarder = verbs.add_parser("storyboard", help="keep a video study's storyboard (SR-364)")
    boarder.add_argument("slug")
    boarder.add_argument("--file", required=True, help="JSON: question, goals, context, beats")
    renderer = verbs.add_parser("render", help="start the background render of a scene")
    renderer.add_argument("slug")
    renderer.add_argument("--scene", required=True, help="the Manim Community scene file")
    job = verbs.add_parser("render-job")     # the background process of render
    job.add_argument("slug")
    framer = verbs.add_parser("frames", help="what the reviewer checks: storyboard, cues, PNGs")
    framer.add_argument("slug")
    checker = verbs.add_parser("check", help="the independent reviewer's verdict (SR-366)")
    checker.add_argument("slug")
    verdict = checker.add_mutually_exclusive_group(required=True)
    verdict.add_argument("--pass", dest="ok", action="store_true")
    verdict.add_argument("--fail", dest="ok", action="store_false")
    checker.add_argument("--reason", default="", help="one medium finding (kept for compatibility)")
    checker.add_argument("--finding", action="append", default=[], metavar="SEVERITY: TEXT",
                         help="critical|high|medium|low: what is wrong; repeatable")
    checker.add_argument("--reviewer", required=True)
    verbs.add_parser("list")
    verbs.add_parser("candidates", help="what to pick this step's study from")
    marker = verbs.add_parser("mark")
    marker.add_argument("slug")
    marker.add_argument("how", choices=tuple(study.MARKS))
    for sub in (boarder, renderer, job, framer, checker):
        sub.add_argument("--clip", required=True,
                         help="the clip's name, as its ```video block in the body names it")
    for sub in verbs.choices.values():
        add_common(sub)
        sub.add_argument("--session", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    root = resolve_root(args.root)
    try:
        if args.verb == "propose":
            from plumb.api import open_core
            from plumb.understand import cmd_intent

            if args.serves or args.asked:   # SR-336, SR-355: inside a loop step or not
                path, loop = Path(""), {"step": ""}
            elif _waiting(open_core(root), root, cmd_intent._session(args, root)):
                raise ValueError("questions wait for the owner: propose a study with --for "
                                 "their keys (plumb study candidates), or nothing")
            else:
                path, loop = _open_loop(root, args)
            slug = study.propose(root, title=args.title, why=args.why, depth=args.depth,
                                 loop=path.stem, step=str(loop.get("step")), topic=args.topic,
                                 serves=args.serves, asked=args.asked)
            emit({"slug": slug} if args.as_json else
                 f"plumb: study idea: {args.title} ({slug}); write nothing until the owner "
                 "accepts it in the band", args.as_json)
        elif args.verb == "add":
            from plumb.api import open_core

            body = Path(args.file).read_text(encoding="utf-8")
            core = open_core(root)
            index = core.index()
            unknown = [i for i in args.records if i not in index]
            if unknown:
                raise LookupError(f"no such record: {', '.join(unknown)}")
            # SR-360 EX-3: 'no record covers it' is gather's finding, never a forgotten flag
            if not args.records and (held := gather(core, root, args.slug)["records"]):
                raise ValueError(f"records cover this topic ({', '.join(r['id'] for r in held)}):"
                                 " pass --records with the IDs you drew on")
            slug = study.add(root, args.slug, body, [
                {"id": i, "title": index[i].title, "hash": index[i].hash}
                for i in dict.fromkeys(args.records)])
            emit({"slug": slug} if args.as_json else
                 f"plumb: new study: {study.get(root, slug)['title']}", args.as_json)
        elif args.verb == "progress":
            study.progress(root, args.slug, args.step, args.done, args.total, finish=args.finish)
            print(f"plumb: study {args.slug}: " + ("progress ended" if args.finish else
                  f"{args.step} {args.done}/{args.total}"))
        elif args.verb == "gather":
            from plumb.api import open_core

            found = gather(open_core(root), root, args.topic)
            emit(found if args.as_json else found["line"] or [
                f"{r['id']} {r['title']}: {r['statement']}"
                + "".join(f"\n  {e}" for e in r["examples"])
                + "".join(f"\n  test {t}: {state}" for t, state in r["tests"].items())
                for r in found["records"]], args.as_json)
        elif args.verb == "storyboard":
            video.storyboard(root, args.slug, args.clip,
                             Path(args.file).read_text(encoding="utf-8"))
            print(f"plumb: storyboard kept for {args.slug} {args.clip}")
        elif args.verb == "render":
            video.render(root, args.slug, args.clip, Path(args.scene))
            print(f"plumb: clip {args.clip} of {args.slug} rendering; the check follows when "
                  "it ends")
        elif args.verb == "render-job":
            video.job(root, args.slug, args.clip)
        elif args.verb == "frames":
            emit(video.frames(root, args.slug, args.clip), True)
        elif args.verb == "check":
            video.check(root, args.slug, args.clip, args.ok, args.reason, args.reviewer,
                        args.finding)
            print(f"plumb: clip {args.clip} of {args.slug}: {'ready' if args.ok else 'failed'}")
        elif args.verb == "list":
            held = study.studies(root)
            emit([{k: v for k, v in s.items() if k != "body"} for s in held] if args.as_json
                 else [f"{s['status']:8} {s.get('depth') or '-':8} {s['step']:8} {s['title']} "
                       f"({s['slug']})" for s in held]
                 or ["plumb: no study yet"], args.as_json)
        elif args.verb == "candidates":
            from plumb.api import open_core
            from plumb.understand import cmd_intent

            session = cmd_intent._session(args, root)
            try:
                path, loop = _open_loop(root, args)
            except LookupError:     # SR-336: questions may wait outside a loop
                if not session:
                    raise
                path, loop = Path(""), {}
            found = candidates(open_core(root), root, loop, path.stem, session)
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
