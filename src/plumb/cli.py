"""Command-line entry point for plumb (spec 12.3).

Kept import-light on purpose: hooks call this every turn, so start-up imports nothing beyond
``sys`` and the dispatcher until it knows the command. Each routed module exposes
``run(command: str, argv: list[str]) -> int``.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from plumb import __version__

ROUTES: dict[str, str] = {
    # CORE
    "init": "plumb.commands", "show": "plumb.commands",
    "link": "plumb.commands", "repin": "plumb.commands", "validate": "plumb.commands",
    "check": "plumb.commands", "status": "plumb.commands", "drift": "plumb.commands",
    "brief": "plumb.commands", "explain": "plumb.commands", "why": "plumb.commands",
    "approve": "plumb.commands", "relay": "plumb.commands", "revoke": "plumb.commands",
    # VERIFY
    "tests": "plumb.verify.cli", "map": "plumb.verify.cli", "verify": "plumb.verify.cli",
    "impact": "plumb.verify.cli",
    # HOST
    "hook": "plumb.hosts.claude_code.cli", "hooks": "plumb.hosts.claude_code.cli",
    "install": "plumb.hosts.claude_code.cli", "statusline": "plumb.hosts.claude_code.cli",
    # BRIDGE (trailers and claims, judgment, importer)
    "trailers": "plumb.claims", "claims": "plumb.claims",
    "import": "plumb.importer.cli", "fidelity": "plumb.judgment.cli",
    "judge": "plumb.judgment.cli", "judgment": "plumb.judgment.cli",
    # MERGE (sub-project 3)
    "merge-check": "plumb.boundary.cli",
}

_HELP = """usage: plumb <command> [options]

Keep agent work aligned with the owner's intent.

records and integrity:
  init         adopt this repository (.plumb/)
  show         print records in full (read-back, examples, assumptions, alternatives)
  link         add a hash-pinned link between a record and a record, file or test
  repin        refresh link pins (never confirms)
  validate     check records, links and logs (--merge BASE: the merge boundary); alias check
  status       counts, drift and records awaiting your confirmation
  brief        the short intent brief
  explain      why a behaviour, file or record exists, in plain terms (plain words, a path
               or an ID); alias why
  approve      owner approval of records at their current content (owner's terminal only)
  relay        record an owner approval the agent relays, with the owner's quote
  revoke       owner revocation
  drift        drift signals only

verification:  tests (map | select | run), map, verify, impact
host:          hook, hooks, install, statusline
bridge:        trailers, claims, fidelity, judge, judgment, import
merge:         merge-check (the merge boundary: one full run, claims, links, the glance;
               --install-pre-push for the optional git hook)

Run `plumb <command> --help` for a command's options. Exit codes: 0 ok, 1 findings,
2 usage, 3 refused by the guard, 4 merge waits for the owner's confirmation, 5 verification
holds the merge.
"""


def _not_available(command: str) -> int:
    print(f"plumb: '{command}' is not available in this build", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    """`plumb <command> ...`: import ROUTES[command] lazily and return its run()."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        sys.stdout.write(_HELP)
        return 0
    if args[0] == "--version":
        print(f"plumb {__version__}")
        return 0
    command = args[0]
    module_name = ROUTES.get(command)
    if module_name is None:
        print(f"plumb: unknown command '{command}' (see plumb --help)", file=sys.stderr)
        return 2
    import importlib

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing and (module_name == missing or module_name.startswith(missing + ".")):
            return _not_available(command)
        raise
    run = getattr(module, "run", None)
    if run is None:
        return _not_available(command)
    return int(run(command, args[1:]) or 0)
