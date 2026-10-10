"""Commands ``plumb fidelity``, ``plumb judge`` and ``plumb judgment status`` (spec 8, 9)."""

from __future__ import annotations

import argparse
import dataclasses
import sys
from typing import Any

from plumb.cliutil import EXIT_FINDINGS, EXIT_USAGE, add_common, emit, resolve_root


def _parser(prog: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=description)
    add_common(parser)
    return parser


def _verify(core: Any) -> Any:
    try:
        from plumb.verify import open_verify
    except ImportError:
        return None
    try:
        return open_verify(core)
    except Exception:  # noqa: BLE001 - verification is optional in a packet
        return None


def packet_lines(packet: Any) -> list[str]:
    lines = [f"fidelity packet {packet.requirement} ({packet.requirement_hash[:19]})",
             f"statement: {packet.statement}"]
    for example in packet.examples:
        if example.criterion:
            lines.append(f"{example.id}: {example.criterion}")
        else:
            lines.append(f"{example.id}: given {example.given}; when {example.when}; "
                         f"then {example.then}")
    for end in packet.ends:
        ref = end.get("test") or end.get("symbol") or end.get("path")
        state = "missing" if end.get("missing") else (end.get("hash") or "")[:19]
        cut = ", truncated" if end.get("truncated") else ""
        lines.append(f"--- {end['kind']} {ref} ({state}{cut}) ---")
        lines.extend(str(end.get("content") or "").splitlines())
    if packet.evidence:
        lines.append("evidence: " + ", ".join(f"{e['node_id']} {e['state']}"
                                               for e in packet.evidence))
    else:
        lines.append("evidence: none recorded")
    return lines


def cmd_fidelity(argv: list[str]) -> int:
    from plumb.api import open_core
    from plumb.judgment import get_backend
    from plumb.judgment.fidelity import build_packet

    parser = _parser("plumb fidelity", "Build the advisory fidelity packet of a requirement.")
    parser.add_argument("sr", help="requirement ID, e.g. SR-003")
    args = parser.parse_args(argv)
    core = open_core(resolve_root(args.root))
    try:
        packet = build_packet(core, _verify(core), args.sr)
    except KeyError as exc:
        print(f"plumb: {exc.args[0]}", file=sys.stderr)
        return EXIT_FINDINGS
    from plumb.judgment import JudgmentUnavailable

    scored = None
    unavailable = None
    backend = None
    try:
        backend = get_backend(core, hook=False)
        if backend.name != "disabled":
            scored = backend.fidelity(packet)  # a JEV score logs its own judgment event
    except JudgmentUnavailable as exc:  # INT-029: the packet is still built; no score
        unavailable = str(exc)
    if args.as_json:
        data = dataclasses.asdict(packet)
        if scored is not None:
            data["score"] = dataclasses.asdict(scored)
        emit(data, True)
        return 0
    lines = packet_lines(packet)
    for notice in getattr(backend, "notices", ()):
        lines.append(notice)
    if unavailable is not None:
        lines.append(f"judging unavailable: {unavailable}")
    if scored is not None:
        lines.append(f"score ({scored.backend}): {scored.verdict}, confidence "
                     f"{scored.confidence:.2f}, tier {scored.tier} (advisory)")
    lines.append(f'answer: plumb judge {packet.requirement} --verdict fits|drifts|unsure '
                 f'--note "<one line>"')
    emit(lines, False)
    return 0


def cmd_judge(argv: list[str]) -> int:
    from plumb.api import open_core
    from plumb.judgment.fidelity import VERDICTS, judge

    parser = _parser("plumb judge", "Record the host agent's advisory fidelity verdict.")
    parser.add_argument("sr")
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if args.verdict not in VERDICTS:
        print(f"plumb judge: --verdict must be one of {', '.join(VERDICTS)}", file=sys.stderr)
        return EXIT_USAGE
    core = open_core(resolve_root(args.root))
    try:
        entry = judge(core, args.sr, args.verdict, args.note)
    except KeyError as exc:
        print(f"plumb: {exc.args[0]}", file=sys.stderr)
        return EXIT_FINDINGS
    if args.as_json:
        emit({"digest": entry.digest, "payload": dict(entry.payload)}, True)
    else:
        print(f"plumb: judgment recorded: {args.sr} {args.verdict} (advisory; it confirms "
              "nothing)")
    return 0


def judgment_status(core: Any) -> dict[str, Any]:
    """Backend in use and key state; never the key itself."""
    from plumb.judgment import JudgmentUnavailable, get_backend

    config = core.config.judgment
    try:
        backend = get_backend(core, hook=False)
        out: dict[str, Any] = {"configured": config.backend, "backend": backend.name,
                               "notices": list(getattr(backend, "notices", ()))}
    except JudgmentUnavailable as exc:
        out = {"configured": config.backend, "backend": "none",
               "notices": [f"judging unavailable: {exc}"]}
    try:
        from plumb.judgment.jev import credential_env, key_source
    except ImportError:
        out["jev"] = "not available in this build"
    else:
        source = key_source(core.root, name=credential_env(core.config))
        out["jev_key"] = "present" if source else "absent"
        if source:
            out["jev_key_source"] = source
    try:
        from plumb.judgment import get_cascade

        out["cascade"] = type(get_cascade(core)).__name__
    except ImportError:
        out["cascade"] = "not available in this build"
    return out


def cmd_judgment(argv: list[str]) -> int:
    from plumb.api import open_core

    parser = _parser("plumb judgment", "Show the judgment backend in use (never the key).")
    parser.add_argument("action", nargs="?", default="status", choices=["status"])
    args = parser.parse_args(argv)
    status = judgment_status(open_core(resolve_root(args.root)))
    emit(status if args.as_json else [f"{k}: {v}" for k, v in status.items()
                                       if v not in ([], None)], args.as_json)
    return 0


_COMMANDS = {"fidelity": cmd_fidelity, "judge": cmd_judge, "judgment": cmd_judgment}


def run(command: str, argv: list[str]) -> int:
    try:
        return _COMMANDS[command](argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
