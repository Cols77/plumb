"""SR-260: an owner's yes to a proof stays on the checkout that heard it (DEC-116)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ids.test_carried_readers import _renumbered
from plumb.api import open_core
from plumb.capture import proof


@pytest.mark.sr("SR-260")
def test_proof_confirmed_on_another_clone_before_the_renumber_is_not_carried(
        tmp_path: Path, hook_input: Any) -> None:
    # DEC-116 (owner, 2026-11-01): the owner's answer stays on the machine and checkout that
    # heard it, so a yes given in a separate clone never reaches the merge; the renumbered
    # record's proof is asked again, and the old id's is not confirmed either
    origin = _renumbered(tmp_path, hook_input, early=True)
    core = open_core(origin)
    assert not proof.owner_confirmed(core, "SR-002")
    assert not proof.owner_confirmed(core, "SR-001")
    assert [row["id"] for row in proof.unconfirmed_proofs(core, ["SR-002"])] == ["SR-002"]
