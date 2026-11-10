"""SR-379 EX-6: the README is one page and names no retired command."""

from __future__ import annotations

from pathlib import Path

import pytest

README = Path(__file__).resolve().parents[2] / "README.md"


@pytest.mark.sr("SR-379")
def test_readme_is_one_page_and_names_no_retired_command() -> None:
    text = README.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 60
    for retired in ("iaso approve", "iaso revoke", "iaso relay", "settle", "pushback",
                    "triage --approve", "spec approve"):
        assert retired not in text, retired
    for kept in ("/iaso intent", "/iaso status", "/iaso go", "iaso --help"):
        assert kept in text, kept
