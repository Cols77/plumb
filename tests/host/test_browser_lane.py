"""The browser workspace lane (tests/browser) runs only when asked for (SR-184)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _ignored(config: pytest.Config, path: Path) -> bool | None:
    return config.hook.pytest_ignore_collect(collection_path=path, config=config)


@pytest.mark.sr("SR-268")
def test_browser_lane_is_left_out_unless_asked(request: pytest.FixtureRequest,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    config = request.config
    monkeypatch.setattr(config.option, "browser", False)
    assert _ignored(config, ROOT / "tests" / "browser") is True
    assert not _ignored(config, ROOT / "tests" / "host")
    monkeypatch.setattr(config.option, "browser", True)
    assert not _ignored(config, ROOT / "tests" / "browser")


@pytest.mark.sr("SR-268")
def test_browser_lane_is_a_package() -> None:
    # Its basenames (test_server.py, test_cli.py) exist in other lanes too; without the package
    # marker a full run fails at collection with an import file mismatch.
    assert (ROOT / "tests" / "browser" / "__init__.py").is_file()
