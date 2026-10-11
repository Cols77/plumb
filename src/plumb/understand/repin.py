"""The repin meaning check (SR-111 EX-4, INT-029): a model reads one stale link's change next to
the requirement it serves and says whether what the requirement relies on changed.

The question is about the requirement, not the file: most edits to a shared file change some
behaviour, which says nothing about this record. The model is ``understand.repin_model``
(Sonnet by default) through the one configured dispatcher. No rule-based answer: a model that
cannot be reached, or an answer that fails the schema, is no verdict, so nothing is repinned."""

from __future__ import annotations

import difflib
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plumb.contracts import DispatchError, Job, NoModel

kind = "repin"
SCHEMA_ID = "repin.v1"
HERE = Path(__file__).resolve().parent
CONTEXT_LINES = 12
DIFF_MAX = 60_000


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "repin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"id": SCHEMA_ID, **data}


schema: Mapping[str, Any] = _load_schema()


@dataclass(frozen=True)
class Meaning:
    """``unchanged`` is True or False, or None when no model gave a usable answer."""

    unchanged: bool | None
    reason: str
    confidence: float = 0.0


def diff(before: str, after: str, path: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"{path} (pinned)", tofile=f"{path} (now)", n=CONTEXT_LINES))


class ModelMeaningJudge:
    """Asks one model per link; ``min_confidence`` is the least confidence that repins."""

    def __init__(self, dispatcher: Any, *, min_confidence: float = 0.8) -> None:
        self.dispatcher = dispatcher
        self.name = f"{getattr(dispatcher, 'name', 'model')}:{getattr(dispatcher, 'model', '')}"
        self.min_confidence = min_confidence

    def same_meaning(self, *, requirement: str, link_id: str, link_kind: str, path: str,
                     before: str, after: str) -> Meaning:
        from plumb.understand import agents
        from plumb.understand import schema as schema_check

        change = diff(before, after, path)
        if not change:
            return Meaning(True, "the linked text is identical", 1.0)
        if len(change) > DIFF_MAX:
            return Meaning(None, f"the change is too large to judge ({len(change)} characters "
                                 "of diff)")
        inputs = {"requirement": requirement, "link": link_id, "link_kind": link_kind,
                  "path": path, "diff": change}
        digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode("utf-8")).hexdigest()
        job = Job(id=f"repin-{digest[:16]}", kind=kind, schema=SCHEMA_ID, inputs=inputs)
        try:
            answer = dict(self.dispatcher.run(
                job, system=agents.load(kind),
                user=json.dumps(inputs, ensure_ascii=False, indent=1),
                schema=schema, on_step=lambda step: None))
        except DispatchError as exc:
            return Meaning(None, f"no answer from {self.name} ({exc.step}: {exc.message})")
        if schema_check.problems(answer, schema):
            return Meaning(None, f"{self.name} gave an answer outside the schema")
        reason = str(answer.get("reason") or "").strip()
        confidence = float(answer.get("confidence") or 0.0)
        if answer.get("verdict") == "changed":
            return Meaning(False, reason, confidence)
        if confidence < self.min_confidence:
            return Meaning(None, f"{self.name} leaned unchanged but only at {confidence:.2f}: "
                                 f"{reason}", confidence)
        return Meaning(True, reason, confidence)


def open_judge(core: Any) -> ModelMeaningJudge | None:
    """The configured meaning judge, or None when no model can be reached."""
    from plumb.understand.dispatch import configured

    settings = core.config.understand
    try:
        dispatcher = configured(core, model=settings.repin_model)
    except NoModel:
        return None
    if dispatcher.available() is not None:
        return None
    return ModelMeaningJudge(dispatcher, min_confidence=settings.repin_min_confidence)
