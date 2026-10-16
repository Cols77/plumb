import dataclasses

import pytest
from mod.helpers import SESSION, sample_card
from understand.test_read_job import make_core, open_card, record_text

pytestmark = pytest.mark.sr("SR-177")


@pytest.fixture
def ui(repo, write_record):
    from plumb.browser.service import BrowserService

    core = make_core(repo, write_record, [record_text(1)])
    open_card(core, dataclasses.replace(sample_card(core, "SR-001"), diagram="diagram.html"))
    return BrowserService(repo)


def test_only_current_card_diagram_can_be_read(ui):
    (ui.root / "diagram.html").write_text("<html><svg><text>hello</text></svg></html>")
    result = ui.diagram(SESSION, "card:SR-001")
    assert result["source"] == "diagram.html"
    assert "<svg>" in result["text"]
    with pytest.raises(LookupError):
        ui.diagram(SESSION, "../diagram.html")


@pytest.mark.parametrize(
    "value,fragment", [(None, "missing"), ("x" * 131073, "large")], ids=["missing", "oversized"]
)
def test_missing_and_oversized_are_useful_errors(ui, value, fragment):
    if value:
        (ui.root / "diagram.html").write_text(value)
    result = ui.diagram(SESSION, "card:SR-001")
    assert fragment in result["error"].lower()
    assert result["text"] is None


def test_path_escape_is_rejected(ui):
    from plumb.understand import cardstore

    cards = cardstore.own_cards(ui.root, SESSION)
    cardstore.save(ui.root, SESSION, [dataclasses.replace(cards[0], diagram="../private.html")])
    (ui.root.parent / "private.html").write_text("secret")
    assert "outside" in ui.diagram(SESSION, "card:SR-001")["error"]


def test_symlink_escape_is_rejected(ui):
    outside = ui.root.parent / "private.html"
    outside.write_text("secret")
    try:
        (ui.root / "diagram.html").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    assert "outside" in ui.diagram(SESSION, "card:SR-001")["error"]
