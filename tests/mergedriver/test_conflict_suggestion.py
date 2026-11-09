"""SR-158: the agent can suggest how to resolve a conflict; the suggestion chooses nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from mergedriver.mdhelpers import conflicted
from iaso import cli

pytestmark = pytest.mark.sr("SR-211")


def test_a_suggestion_needs_its_reason(repo: Path, capsys) -> None:
    ic = conflicted(repo)
    assert cli.main(["conflict", "propose", ic, "--take", "theirs", "--root", str(repo)]) == 2
    assert "--why" in capsys.readouterr().err
    assert cli.main(["conflict", "propose", ic, "--take", "theirs", "--why", "typo fix",
                     "--root", str(repo)]) == 0
