"""The repin meaning check (SR-111 EX-4, INT-029): a model reads one stale link's change next to
the requirement it serves and says whether what the requirement relies on changed.

The question is about the requirement, not the file: most edits to a shared file change some
behaviour, which says nothing about this record. The model is ``understand.repin_model``
(Sonnet by default) through the one configured dispatcher. No rule-based answer: a model that
cannot be reached, or an answer that fails the schema, is no verdict, so nothing is repinned.

SR-114 makes it a cascade: JEV first, repinning alone above a calibrated threshold; then Sonnet;
and when Sonnet says the change matters, Opus (``understand.diagnose_model``) diagnoses which
way it goes (SR-113): reword the record, send the change back to development, or ask the
owner."""

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
    """Asks one model per link. The verdict alone decides: the model's self-reported
    confidence is kept on the answer but gates nothing."""

    def __init__(self, dispatcher: Any) -> None:
        self.dispatcher = dispatcher
        self.name = f"{getattr(dispatcher, 'name', 'model')}:{getattr(dispatcher, 'model', '')}"

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
        return Meaning(answer.get("verdict") == "unchanged", reason, confidence)


def judge_gap(core: Any) -> str:
    """Why no meaning judge can be reached (SR-174), for the line that says the check waits."""
    from plumb.understand.dispatch import configured

    try:
        gap = configured(core, model=core.config.understand.repin_model).available()
        return gap or "no model answered"
    except NoModel as exc:
        return str(exc)


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
    return ModelMeaningJudge(dispatcher)


# --------------------------------------------------------------------------- the JEV tier
# SR-114 EX-1, EX-6: before Sonnet, JEV is asked the requirement-aware yes/no question the
# repin eval scores (``evalrepin.JevRepinJudge`` asks this same one). Only a probability at or
# above ``understand.repin_jev_threshold`` (set from the labelled set, where it repins nothing
# changed) repins on JEV alone; below it, with JEV unreachable or with no threshold set,
# Sonnet judges. A low answer is never a "changed" verdict: JEV just does not clear the link.

JEV_QUESTION = ("Does the change leave everything the requirement and its examples rely on "
                "as it was?")


def jev_prompt(*, requirement: str, link_id: str, link_kind: str, path: str,
               change: str) -> str:
    return (f"Requirement:\n{requirement}\n\n"
            f"Link {link_id} ({link_kind}) to {path}\n\n"
            f"The change to the linked end since it was pinned (unified diff):\n"
            f"{change}\n")


def jev_probability(backend: Any, prompt: str) -> float:
    """JEV's probability of yes; ``JudgmentUnavailable`` when it cannot answer."""
    from plumb.judgment import JudgmentUnavailable
    from plumb.judgment.model import JudgmentQuestion

    question = JudgmentQuestion.noul(JEV_QUESTION, "unchanged", "changed")
    record = backend._ask([("yes_no", question)], prompt)
    if record is None:
        raise JudgmentUnavailable("JEV", "no answer")
    return float(record.answers["yes_no"].value)


class JevTier:
    """``clears`` is JEV's probability when it is at or above the threshold, else None (go
    on to Sonnet). It never raises: an unreachable JEV is skipped, nothing is guessed."""

    name = "jev"

    def __init__(self, backend: Any, threshold: float) -> None:
        self.backend, self.threshold = backend, float(threshold)

    def clears(self, *, requirement: str, link_id: str, link_kind: str, path: str,
               before: str, after: str) -> float | None:
        change = diff(before, after, path)
        if not change or len(change) > DIFF_MAX:
            return None
        try:
            p = jev_probability(self.backend, jev_prompt(
                requirement=requirement, link_id=link_id, link_kind=link_kind, path=path,
                change=change))
        except Exception:  # noqa: BLE001 - JEV unreachable or failing: Sonnet judges
            return None
        return p if p >= self.threshold else None


def open_jev_tier(core: Any) -> JevTier | None:
    """The JEV tier, or None when no threshold is set (EX-6) or JEV cannot be had."""
    threshold = core.config.understand.repin_jev_threshold
    if threshold is None:
        return None
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        return None
    from plumb.judgment.jev import JevBackend, open_jev
    from plumb.judgment.tiers import Thresholds

    try:
        backend = open_jev(core, core.config, hook=False,
                           thresholds=Thresholds.from_config(core.config.judgment.jev))
    except Exception:  # noqa: BLE001 - no key, or JEV not configured: the tier is off
        return None
    return JevTier(backend, threshold) if isinstance(backend, JevBackend) else None


# --------------------------------------------------------------------------- the Opus step
# SR-114 EX-3..EX-5, SR-113: when Sonnet says the change matters, Opus does not judge again;
# it checks the requirement against the intent it derives from and the change against the
# turn that made it, and says which way it goes: the record is reworded, the change goes back
# to development, or the owner gets a card. Unreachable, or an answer outside the schema or
# missing what its outcome needs: no diagnosis, nothing is guessed.

DIAGNOSE_KIND = "diagnose"
DIAGNOSE_SCHEMA_ID = "diagnose.v1"
OUTCOMES = ("reword", "back-to-development", "owner")
TURN_NOTE = ("best effort: the latest owner prompt logged before the file last changed; it "
             "is context, not proof that this turn made the change")
TURN_MAX = 4000


def _load_diagnose_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "diagnose.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"id": DIAGNOSE_SCHEMA_ID, **data}


diagnose_schema: Mapping[str, Any] = _load_diagnose_schema()


@dataclass(frozen=True)
class Diagnosis:
    """What Opus found for one link whose change Sonnet says matters."""

    outcome: str                         # reword | back-to-development | owner
    explanation: str
    topic: str
    proposed_wording: str = ""
    options: tuple[str, ...] = ()
    broken_example: str = ""
    consequences: tuple[str, ...] = ()   # SR-116: one per option, when the answer gives them
    why: str = ""                        # SR-116: why the first option is recommended


def _diagnosis(answer: Mapping[str, Any]) -> Diagnosis | None:
    outcome = answer.get("outcome")
    explanation = str(answer.get("explanation") or "").strip()
    wording = str(answer.get("proposed_wording") or "").strip()
    options = tuple(str(o).strip() for o in answer.get("options") or () if str(o).strip())
    if outcome not in OUTCOMES or not explanation:
        return None
    if outcome == "reword" and not wording:
        return None
    if outcome == "owner" and not 2 <= len(options) <= 4:
        return None
    raw = answer.get("consequences")
    consequences = tuple(str(c).strip() for c in raw) if isinstance(raw, (list, tuple)) else ()
    if len(consequences) != len(options) or not all(consequences):
        consequences = ()                # partial consequences are none: the card asks for them
    return Diagnosis(outcome=str(outcome), explanation=explanation,
                     topic=str(answer.get("topic") or "").strip(), proposed_wording=wording,
                     options=options if outcome == "owner" else (),
                     broken_example=str(answer.get("broken_example") or "").strip(),
                     consequences=consequences if outcome == "owner" else (),
                     why=str(answer.get("why") or "").strip() if outcome == "owner" else "")


class ModelDiagnoser:
    """Asks ``understand.diagnose_model`` (Opus by default) once per link. ``diagnose``
    returns ``(Diagnosis, "")`` or ``(None, why there is none)``."""

    def __init__(self, dispatcher: Any) -> None:
        self.dispatcher = dispatcher
        self.name = f"{getattr(dispatcher, 'name', 'model')}:{getattr(dispatcher, 'model', '')}"

    def diagnose(self, *, requirement: str, intents: list[dict[str, str]], link_id: str,
                 path: str, change: str, reason: str,
                 turn: Mapping[str, str] | None) -> tuple[Diagnosis | None, str]:
        from plumb.understand import agents
        from plumb.understand import schema as schema_check

        inputs = {"requirement": requirement, "intents": intents, "link": link_id,
                  "path": path, "diff": change[:DIFF_MAX], "sonnet_reason": reason,
                  "turn": dict(turn) if turn else None}
        digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode("utf-8")).hexdigest()
        job = Job(id=f"diagnose-{digest[:16]}", kind=DIAGNOSE_KIND, schema=DIAGNOSE_SCHEMA_ID,
                  inputs=inputs)
        try:
            answer = dict(self.dispatcher.run(
                job, system=agents.load(DIAGNOSE_KIND),
                user=json.dumps(inputs, ensure_ascii=False, indent=1),
                schema=diagnose_schema, on_step=lambda step: None))
        except DispatchError as exc:
            return None, f"no answer from {self.name} ({exc.step}: {exc.message})"
        if schema_check.problems(answer, diagnose_schema):
            return None, f"{self.name} gave an answer outside the schema"
        found = _diagnosis(answer)
        if found is None:
            return None, f"{self.name} gave an answer missing what its outcome needs"
        return found, ""


def open_diagnoser(core: Any) -> ModelDiagnoser | None:
    """The configured diagnoser, or None when no model can be reached."""
    from plumb.understand.dispatch import configured

    try:
        dispatcher = configured(core, model=core.config.understand.diagnose_model)
    except NoModel:
        return None
    if dispatcher.available() is not None:
        return None
    return ModelDiagnoser(dispatcher)


def turn_before(core: Any, path: str) -> dict[str, str] | None:
    """The latest owner prompt logged before ``path`` last changed (best effort), or None."""
    import os
    from datetime import UTC, datetime

    try:
        changed = os.stat(Path(core.root) / path).st_mtime
        lines = Path(core.paths.prompts).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    best: dict[str, Any] | None = None
    for line in lines:
        try:
            entry = json.loads(line)
            at = datetime.strptime(str(entry["at"]), "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        if at <= changed and (best is None or at >= best["_at"]):
            best = {**entry, "_at": at}
    if best is None:
        return None
    from plumb.hosts.claude_code.prompt import owner_text

    text = owner_text(str(best.get("text") or ""))
    if len(text) > TURN_MAX:
        text = text[:TURN_MAX - 3] + "..."
    return {"at": str(best["at"]), "text": text, "note": TURN_NOTE}
