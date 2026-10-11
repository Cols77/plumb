"""Shared helpers of the mod's Python-side tests: run ``plumb mod`` in process with a JSON
object on stdin (never a key in argv), and read what it wrote."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

from plumb import cli

SESSION = "s1"
KEY = "a1" * 32                       # the mod's 32-byte key, as 64 hex characters
OTHER_KEY = "b2" * 32
DIGEST = hashlib.sha256(bytes.fromhex(KEY)).hexdigest()


def run_mod(monkeypatch: Any, capsys: Any, root: Path, *args: str,
            stdin: Any = None) -> tuple[int, Any, str]:
    """``plumb mod <args> --root <root> --session s1 --json`` with ``stdin`` (a mapping, sent
    as JSON); returns the exit code, the parsed answer (or None) and stderr."""
    capsys.readouterr()
    text = "" if stdin is None else json.dumps(stdin)
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    argv = ["mod", *args, "--root", str(root), "--json"]
    if "--session" not in args:
        argv += ["--session", SESSION]
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, json.loads(out) if out.strip() else None, err


def kinds(root: Path) -> list[str]:
    """The kinds of the events log entries, in order."""
    from plumb.api import open_core

    return [e.kind for e in open_core(root).events()]


def mod_json(root: Path, session: str = SESSION) -> Path:
    return root / ".plumb" / "session" / session / "mod.json"
