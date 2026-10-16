"""R2 / decision 2: an \"ok\" beside a correction the agent cannot place confirms nothing.

Retired by SR-101 EX-9: an agent-run prose relay no longer exists, so the relay neither
confirms nor rejects anything, whatever the words around the owner's "ok". What these
examples were about (an "ok" beside a correction confirms nothing it corrects) is now the
reader's job on the owner's own message (tests/understand). The scenarios stay here as the
words that used to be judged by fixed rules: the relay is refused on each of them. The
owner decides when the examples above are retired from SR-005.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import log_prompt, record_text, run

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-208")

CASES = [
    ('ok, except 3 minus 5 should return 0, we clamp at zero', 'ok'),
    ('ok but 5 to the 0 should give 0 for us', 'ok'),
    ('sounds good, but b can be negative', 'sounds good'),
    ('yes, though negative exponents must be supported too', 'yes'),
]


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    write_record(repo, record_text("SR-001", "Add multiply", statement="multiply two numbers"))
    return repo


@pytest.mark.parametrize("words, quote", CASES)
def test_the_relay_is_refused_and_nothing_is_recorded(project: Path, capsys, words: str,
                                                      quote: str) -> None:
    digest = log_prompt(project, words)
    for extra in ([], ["--revoke"], ["--reject"]):
        assert run(project, "relay", "SR-001", "--prompt", digest, "--quote", quote,
                   *extra) == 3
    assert "no longer exists" in capsys.readouterr().err
    kinds = {e.kind for e in open_core(project).events()}
    assert not kinds & {"approval", "revocation", "rejection"}
