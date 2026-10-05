"""Command-line entry point for plumb.

Kept import-light on purpose: hooks call this every turn, so start-up must stay fast.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from plumb import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plumb",
        description="Keep agent work aligned with the owner's intent.",
    )
    parser.add_argument("--version", action="version", version=f"plumb {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits for --version/--help/errors
        return int(exc.code or 0)
    parser.print_help()
    return 0
