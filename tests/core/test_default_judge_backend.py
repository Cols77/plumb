"""An unset ``judgment.backend`` stays "no judge": judging says so, naming the setting (INT-029).

The eval's scratch repository is what must name a judge (case eval-8ba65c4a), not this default.
"""
from pathlib import Path

from plumb.config import load_config


def test_unset_backend_stays_unset(tmp_path: Path) -> None:
    (tmp_path / ".plumb").mkdir()
    assert load_config(tmp_path).judgment.backend == ""
