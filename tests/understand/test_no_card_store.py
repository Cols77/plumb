"""SR-382 EX-1: plumb keeps no card store; nothing under src/plumb imports one."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.sr("SR-382")

SRC = Path(__file__).resolve().parents[2] / "src" / "plumb"


def test_ex1_no_card_store_module_exists_or_is_imported() -> None:
    assert not (SRC / "understand" / "cardstore.py").exists()
    importers = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                     [node.module or "", *(a.name for a in node.names)]
                     if isinstance(node, ast.ImportFrom) else [])
            if any(part == "cardstore" for name in names for part in name.split(".")):
                importers.append(str(path.relative_to(SRC)))
    assert importers == []
