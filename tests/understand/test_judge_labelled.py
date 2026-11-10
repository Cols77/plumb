"""The judge calibration set built from the owner's real verdicts has the shape its readers expect
(src/iaso/understand/evalset/judge_labelled.json; SR-105)."""

from __future__ import annotations

import json
from pathlib import Path



PATH = Path(__file__).resolve().parents[2] / "src" / "iaso" / "understand" / "evalset" / "judge_labelled.json"
FIELDS = {"id": str, "record_id": str, "record_hash": str, "kind": str, "record_text": str,
          "owner_words": str, "owner_words_digest": str, "context_ids": list, "expected": str,
          "calibration": str, "source": str}
KINDS = {"intent-readback", "requirement", "example", "decision"}
EXPECTED = {"supported", "beyond", "contradicts"}
CALIBRATION = {"yes", "no", "none"}


def _items() -> list[dict]:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    assert data["v"] == 1
    return data["items"]


def test_every_item_has_every_field_with_a_valid_value() -> None:
    items = _items()
    assert 25 <= len(items) <= 40
    for item in items:
        assert set(item) == set(FIELDS), item.get("id")
        for name, typ in FIELDS.items():
            assert isinstance(item[name], typ), (item["id"], name)
        assert item["kind"] in KINDS, item["id"]
        assert item["expected"] in EXPECTED, item["id"]
        assert item["calibration"] in CALIBRATION, item["id"]
        assert all(isinstance(c, str) for c in item["context_ids"]), item["id"]
        assert item["record_text"].strip() and item["owner_words"].strip() and item["source"].strip()
        assert item["record_hash"] == "" or item["record_hash"].startswith("sha256:"), item["id"]
        digest = item["owner_words_digest"]
        assert digest == "" or (len(digest) == 16 and int(digest, 16) >= 0), item["id"]


def test_ids_are_unique() -> None:
    ids = [item["id"] for item in _items()]
    assert len(ids) == len(set(ids))


def test_at_least_six_items_are_not_supported() -> None:
    assert sum(item["expected"] != "supported" for item in _items()) >= 6


def test_labels_follow_the_owner_verdict() -> None:
    for item in _items():
        if item["calibration"] == "yes":
            assert item["expected"] == "supported", item["id"]
        if item["calibration"] == "no":
            assert item["expected"] != "supported", item["id"]
