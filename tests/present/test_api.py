"""PRESENT's provided interface, ``plumb.present.api`` (sp5 9, plan 3.5; SR-064 EX-5): the
read-only views HOSTS (the MCP server, adapters) and CAPTURE call, the same as the CLI."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from present_helpers import FEAT1, FEAT2, INT1, SR1, SR2, SR3, write_all

from plumb import cli
from plumb.api import open_core
from plumb.contracts import Resolution, Target
from plumb.present import api

pytestmark = pytest.mark.sr("SR-064")

LOGIN = """---
id: SR-010
title: the login form checks the password
feature: FEAT-002
statement: Logging in with a wrong password shows an error and keeps the user out.
---
"""


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    write_all(repo, write_record, SR1, SR2, SR3, LOGIN, INT1, FEAT1, FEAT2)
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "src" / "app" / "login.py").write_text("def login():\n    pass\n", "utf-8")
    open_core(repo).add_link("SR-010", "implemented_by", Target(path="src/app/login.py"))
    return repo


def _snapshot(repo: Path) -> dict[str, bytes]:
    root = repo / ".plumb"
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and "cache" not in p.relative_to(root).parts
            and p.name != "test_map.txt"}


def test_the_frozen_signatures() -> None:
    """The seven functions of sp5 9 exist with their contract's parameters."""
    params = {name: list(inspect.signature(getattr(api, name)).parameters)
              for name in ("brief", "relevant", "show", "explain", "impact", "drift",
                           "resolve")}
    assert params["brief"][:2] == ["core", "full"]
    assert params["relevant"] == ["core", "text", "limit"]
    assert params["show"] == ["core", "ids"]
    assert params["explain"] == ["core", "query"]
    assert params["impact"] == ["core", "ref"]
    assert params["drift"] == ["core"]
    assert params["resolve"] == ["core", "words", "kind"]


def test_resolve_names_the_best_match_or_none(records: Path) -> None:
    """HOSTS reads ``Resolution.best``: the one clear match, None when ambiguous."""
    core = open_core(records)
    result = api.resolve(core, "the login thing")
    assert isinstance(result, Resolution) and result.best == "SR-010"
    assert api.resolve(core, "zebra quantum").best is None


def test_views_answer_in_the_owners_terms_and_write_nothing(records: Path, capsys) -> None:
    core = open_core(records)
    before = _snapshot(records)
    assert api.relevant(core, "login password")[0] == {
        "id": "SR-010", "state": "proposed", "title": "the login form checks the password"}
    assert any("SR-010" in line for line in api.show(core, ["the", "login", "thing"]))
    explained = api.explain(core, "the login thing")
    assert explained["ids"] == ["SR-010"] and explained["lines"]
    assert explained["resolved"]["how"] == "words"
    impact = api.impact(core, "the login thing")
    assert impact["resolved"]["how"] == "words"
    assert [i["ref"] for i in impact["impacts"]][:1] == ["SR-010"] or not impact["available"]
    drift = api.drift(core)
    assert "clean" in drift and drift["hints"] == []
    assert _snapshot(records) == before


def test_brief_is_what_the_cli_prints(records: Path, capsys) -> None:
    lines = api.brief(open_core(records))
    capsys.readouterr()
    assert cli.main(["brief", "--root", str(records)]) == 0
    assert capsys.readouterr().out.splitlines() == lines
    assert lines[0].startswith("plumb brief")
