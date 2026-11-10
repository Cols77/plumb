"""VS6: ``iaso tests waive``: owner only, a ``waiver`` event pinned to a diff digest."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso import cli
from iaso.api import open_core

DIGEST = "sha256:" + "ab" * 32


def _waivers(root: Path) -> list:
    return list(open_core(root).log_read("events", ["waiver"]))


@pytest.mark.sr("SR-254")
def test_waiver_refused_under_marker(repo: Path, monkeypatch: pytest.MonkeyPatch,
                                     capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("IASO_AGENT_SESSION", "1")
    code = cli.main(["tests", "waive", "--diff-digest", DIGEST, "--reason", "flaky infra",
                     "--root", str(repo)])
    assert code == 3
    assert "refused" in capsys.readouterr().err
    assert _waivers(repo) == []


@pytest.mark.sr("SR-254")
def test_waiver_event_pinned_to_diff_digest(repo: Path,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    root = ["--root", str(repo)]
    assert cli.main(["tests", "waive", "--diff-digest", DIGEST, "--reason", "known",
                     *root]) == 0
    events = _waivers(repo)
    assert len(events) == 1
    assert events[0].payload["diff_digest"] == DIGEST
    from iaso import words

    assert "reason" not in events[0].payload     # DEC-116: the owner's words stay local
    assert words.joined(open_core(repo), events[0])["reason"] == "known"
    assert events[0].marker == "none"
    assert cli.main(["tests", "waive", "--diff-digest", "nope", "--reason", "x", *root]) == 2
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    assert cli.main(["tests", "waive", "--reason", "current diff", *root]) == 0
    computed = _waivers(repo)[-1].payload["diff_digest"]
    assert computed.startswith("sha256:") and computed != DIGEST
    assert computed in capsys.readouterr().out
