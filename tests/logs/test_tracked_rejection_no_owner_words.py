"""SR-376, DEC-116 (report-a0ad55c8): the owner's words stay out of git. A tracked rejection
entry, in its own file or in the kind's archive segment, keeps the premise the judge read only as
``premise_digest``, never its text."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.sr("SR-376")


def test_no_tracked_rejection_entry_holds_the_owners_premise() -> None:
    tracked = subprocess.run(["git", "ls-files", ".iaso/log/rejection"], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout.split()
    holding = []
    for rel in tracked:
        for number, line in enumerate((ROOT / rel).read_bytes().splitlines(), 1):
            if not line.strip():
                continue
            records = json.loads(line).get("payload", {}).get("records") or ()
            if any(isinstance(r, dict) and r.get("premise") for r in records):
                holding.append(f"{rel}:{number}")
    assert holding == []
