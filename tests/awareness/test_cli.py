"""``plumb inflight``: list, check, drop, sync (R17, SR-080, SR-081)."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from awareness.scenario import change, setup
from plumb.cli import main as cli_main


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli_main(list(argv))
    return code, out.getvalue()


@pytest.mark.sr("SR-080")
def test_list_and_drop(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    assert _run("inflight", "--root", str(main)) == (
        0, "intent in flight on other branches: none\n")
    change(other, "feat-x's version")
    code, text = _run("inflight", "--root", str(main))
    assert code == 0
    assert '  feat-x: "relay intent" (SR-005 "relay checks")' in text
    code, raw = _run("inflight", "--json", "--root", str(main))
    assert json.loads(raw)["claims"][0]["branch"] == "feat-x"
    code, text = _run("inflight", "drop", "feat-x", "--root", str(main))
    assert code == 0 and "feat-x:INT-001" in text
    assert _run("inflight", "--root", str(main))[1] == (
        "intent in flight on other branches: none\n")


@pytest.mark.sr("SR-081")
def test_check_exits_1_with_the_card(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    code, text = _run("inflight", "check", "make", "SR-005", "stricter", "--root", str(main))
    assert code == 1
    assert '"relay checks" waits as a card' in text
    code, text = _run("inflight", "check", "nothing", "related", "--root", str(main))
    assert (code, text) == (0, "")


@pytest.mark.sr("SR-080")
def test_sync_claims_plain_edits(tmp_path: Path) -> None:
    from awareness.gitrepo import requirement
    from plumb.awareness import inflight

    main, other = setup(tmp_path)
    requirement(other, "SR-006", "status card", "edited by hand", feature="FEAT-002")
    from plumb.api import open_core
    from plumb.awareness.publish import publish

    publish(open_core(other), [".plumb/requirements/SR-006.md"])
    code, text = _run("inflight", "sync", "--root", str(other))
    assert code == 0 and "updated" in text
    _oid, data = inflight.read(main, allow_git=True)
    assert set(data["claims"][0]["records"]) == {"SR-006"}
    assert _run("inflight", "sync", "--root", str(other))[1] == (
        "plumb: intent in flight already current\n")


def test_unknown_action_is_usage(tmp_path: Path) -> None:
    main, _other = setup(tmp_path)
    assert _run("inflight", "frobnicate", "--root", str(main))[0] == 2
