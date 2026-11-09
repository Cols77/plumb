"""SR-386: the landing queue, one shared file for every session and worktree.

``<git common dir>/iaso-landing.json`` is a list of {branch, session, state, waits, at}; state
is waiting, landing or owner (waits on the owner, ``waits`` says for what). iaso never merges
into main itself: ``next`` only says which branch is to land, one at a time.
shortcut: a read-modify-write of the file by two sessions at the same instant can lose one
change; take a lock around it if that bites.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from iaso.heavy import common_dir

USAGE = ("usage: iaso landing [add <branch> [--session ID] | wait <branch> --on WHAT | "
         "ready <branch> | next | done <branch>]")


def _file(cwd: Path) -> Path:
    return common_dir(cwd) / "iaso-landing.json"


def load(cwd: Path) -> list[dict]:
    try:
        return json.loads(_file(cwd).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(cwd: Path, queue: list[dict]) -> None:
    path = _file(cwd)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(queue, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def board_lines(cwd: Path) -> list[str]:
    queue = load(cwd)
    if not queue:
        return []
    out = ["landing queue:"]
    for q in queue:
        state = "waits on the owner" if q["state"] == "owner" else q["state"]
        out.append(f"  {q['branch']}: {state}" + (f" ({q['waits']})" if q["waits"] else "")
                   + f", session {q['session'] or '-'}")
    return out


def run(command: str, argv: list[str]) -> int:
    cwd = Path.cwd()
    if not argv:
        print("\n".join(board_lines(cwd) or ["landing queue: empty"]))
        return 0
    if argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    verb, rest = argv[0], argv[1:]
    session, waits = "", ""
    for flag in ("--session", "--on"):
        if flag in rest:
            i = rest.index(flag)
            value = rest[i + 1] if i + 1 < len(rest) else ""
            session, waits = (value, waits) if flag == "--session" else (session, value)
            del rest[i:i + 2]
    queue = load(cwd)
    if verb == "next" and not rest:
        landing = next((q for q in queue if q["state"] == "landing"), None)
        if landing:
            print(f"iaso: {landing['branch']} is landing; one branch lands at a time",
                  file=sys.stderr)
            return 1
        if (common_dir(cwd) / "MERGE_HEAD").exists():
            print("iaso: the main checkout is in the middle of a merge; finish or abort it",
                  file=sys.stderr)
            return 1
        first = next((q for q in queue if q["state"] == "waiting"), None)
        if first is None:
            print("iaso: no branch in the queue is ready to land", file=sys.stderr)
            return 1
        first["state"] = "landing"
        _save(cwd, queue)
        print(first["branch"])
        return 0
    if verb not in ("add", "wait", "ready", "done") or len(rest) != 1 \
            or (verb == "wait" and not waits):
        print(USAGE, file=sys.stderr)
        return 2
    branch = rest[0]
    entry = next((q for q in queue if q["branch"] == branch), None)
    if verb == "add":
        if entry is None:
            queue.append({"branch": branch, "session": session, "state": "waiting",
                          "waits": "", "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
            _save(cwd, queue)
        return 0
    if entry is None:
        print(f"iaso: {branch} is not in the landing queue", file=sys.stderr)
        return 1
    if verb == "done":
        queue.remove(entry)
    else:
        entry["state"], entry["waits"] = ("owner", waits) if verb == "wait" else ("waiting", "")
    _save(cwd, queue)
    return 0
