"""Fixtures of the understanding layer tests."""

import pytest

from understand.fakes import engine_standins  # noqa: F401


@pytest.fixture(autouse=True)
def loops_seams(monkeypatch: pytest.MonkeyPatch) -> None:
    """INT-123: no test runs `claude`, opens a window or messages a session. A command-level
    test gets the running sessions from ``loops.claude_sessions`` (none here); a test that needs
    some replaces it itself."""
    from plumb.understand import loops

    monkeypatch.setattr(loops, "claude_sessions", lambda: {})

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test opened a terminal window")

    monkeypatch.setattr(loops, "launch", refuse, raising=False)
