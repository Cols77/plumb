"""The owner questions filed about stale links (``stale.ask_owner``), for the tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plumb.understand import judge


def asked(root: Path, session: str) -> list[dict[str, Any]]:
    """The stale-link questions of ``session``, each as ``{link, record, topic, issue,
    options, by, question, descriptions}`` (the first option is the recommended one)."""
    return [{**q["stale"], "question": q["question"],
             "descriptions": [o["description"] for o in q["options"]]}
            for q in judge._logged_questions(root, session)
            if str(q.get("job") or "").startswith("stale:")]
