"""H0: the two config keys the hooks-first lanes read."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.config import load_config

pytestmark = pytest.mark.sr("SR-198", "SR-255")


def test_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.hooks.stale_holds_max == 3
    assert config.verify.coverage == "auto"


def test_config_yaml_overrides_each_key(tmp_path: Path) -> None:
    (tmp_path / ".plumb").mkdir()
    (tmp_path / ".plumb" / "config.yaml").write_text(
        "hooks:\n  stale_holds_max: 1\nverify:\n  coverage: 'off'\n", encoding="utf-8")
    config = load_config(tmp_path)
    assert config.hooks.stale_holds_max == 1
    assert config.verify.coverage == "off"
    assert config.verify.sample_size == 10
    assert config.hooks.brief_lines == 30
