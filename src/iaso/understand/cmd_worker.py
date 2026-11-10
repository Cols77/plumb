"""``iaso understand worker --session <id> [--root PATH] [--once]``: the worker in the
foreground (for tests and a terminal); ``start_detached`` starts the same command detached."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from iaso.present.owner_text import NOT_AVAILABLE


def run(command: str, argv: list[str]) -> int:
    if not argv or argv[0] != "worker":
        print(f"iaso: {command}: {NOT_AVAILABLE}; the part that is: "
              "iaso understand worker --session ID, iaso understand eval", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(prog="iaso understand worker")
    parser.add_argument("action", choices=["worker"])
    parser.add_argument("--session", required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--once", action="store_true", help="run what is queued, then stop")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    from iaso.api import open_core
    from iaso.paths import find_root
    from iaso.understand import worker

    core = open_core(find_root(Path(args.root or ".")))
    if args.once:
        worker.run_once(core, args.session)
    else:
        worker.run_loop(core, args.session)
    return 0


if __name__ == "__main__":
    sys.exit(run("understand", sys.argv[1:]))
