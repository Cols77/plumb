"""Argument helpers shared by every routed command module (spec 12.3)."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3
EXIT_MERGE_WAITS = 4


def add_common(parser: Any) -> None:
    """Add ``--root`` and ``--json`` to an argparse parser."""
    parser.add_argument("--root", default=None, help="repository root (default: walk up to "
                        "the first directory holding .plumb/, else .git)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="machine-readable output")


def resolve_root(arg: str | None) -> Path:
    from plumb.paths import find_root

    if arg:
        return Path(arg).resolve()
    return find_root(Path.cwd())


def emit(obj: Any, as_json: bool) -> None:
    """Print ``obj`` as JSON or as plain lines."""
    if as_json:
        sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n")
        return
    if obj is None:
        return
    if isinstance(obj, str):
        print(obj)
    elif isinstance(obj, Mapping):
        for key, value in obj.items():
            print(f"{key}: {value}")
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            print(item)
    else:
        print(obj)
