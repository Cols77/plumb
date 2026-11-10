"""Recovering older records' words from past session transcripts (SR-118, INT-032).

An intent whose quote is in no prompt the hook logged ("quote not verified" in triage) may
still have its source in a past Claude Code session: ``~/.claude/projects/<project>/*.jsonl``
keeps every message the owner typed (``<project>`` is this project's folder, its name matched
exactly: never a worktree's or another project's). Recovery looks there with a cascade like
SR-114's repin:

1. a plain text comparison first: a message holding the record's quote verbatim (the same
   ``approvals.quote_in_prompt`` check triage uses, over normalized text) is the source, and
   no model is asked;
2. otherwise JEV ranks the owner's messages for the record (cheap: one choice question per
   batch of messages), and the best few go to
3. Sonnet (``understand.repin_model``), which picks the message and copies the exact span
   from it, and says whether the span supports the record. The span is checked to be in the
   message by text comparison; a span that is not is no answer;
4. when the span does not support the record, Opus (``understand.diagnose_model``) examines
   whether the record misreads the owner and, if so, proposes a rewording.

A model-picked span is shown only when it is long enough (``long_enough``), whether it
supports the record or Opus finds the record misreads it; a shorter one is reported as too
short to show.

What is found goes to a cache under ``.iaso/cache`` keyed by the record's hash (never the
log), and the record's card shows it marked "found in a transcript, not verified". A
transcript match never confirms anything and never counts as verified in triage: the owner's
press or logged words do. No model, no answer: an error is reported and nothing is decided
(INT-029); there is no rule-based ranking in a model's place.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from iaso.contracts import DispatchError, Job, NoModel

HERE = Path(__file__).resolve().parent
CACHE_NAME = "recovered_quotes.json"
TRANSCRIPTS_ENV = "IASO_TRANSCRIPTS_DIR"
NOT_VERIFIED = "found in a transcript, not verified"
NOT_FOUND = "your words were not found in any past session transcript"
TOO_SHORT = "the words found in a transcript are too short to show"
MIN_SPAN_WORDS = 4        # a model-picked span shorter than this (and not the whole message)
JEV_BATCH = 20            # messages per JEV choice question
JEV_MESSAGE_MAX = 1200    # characters of a message shown to JEV
TOP_K = 3                 # messages JEV ranks best that Sonnet reads
MESSAGE_MAX = 8000        # characters of a message shown to Sonnet and Opus
PICK_KIND, PICK_SCHEMA_ID = "recover", "recover.v1"
EXAMINE_KIND, EXAMINE_SCHEMA_ID = "recover_examine", "recover_examine.v1"
_HARNESS_STARTS = ("<command-", "<local-command", "<system-reminder>", "<task-notification>",
                   "<cross-session-message", "Another Claude session sent a message",
                   "This session is being continued from a previous conversation",
                   "[SYSTEM NOTIFICATION", "[Request interrupted", "Caveat: The messages below",
                   "<iaso-loop-brief>", "<iaso-loop-message>")
# entry flags of messages the harness wrote, never the owner: a compaction summary, a line
# shown in the transcript only, a skill or meta injection, a tool result, a subagent's turn
_SYNTHETIC_FLAGS = ("isCompactSummary", "isVisibleInTranscriptOnly", "isMeta", "isSidechain",
                    "toolUseResult", "sourceToolUseID")
# ``origin.kind`` of a message the owner typed; any other kind (task-notification, peer for a
# cross-session message, plugin for a mod's line) is not the owner's
_OWNER_ORIGINS = ("human",)


def _load(name: str, schema_id: str) -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"id": schema_id, **data}


pick_schema: Mapping[str, Any] = _load("recover.json", PICK_SCHEMA_ID)
examine_schema: Mapping[str, Any] = _load("recover_examine.json", EXAMINE_SCHEMA_ID)


class RecoveryError(Exception):
    """No model gave a usable answer: nothing is decided for the record."""


# --------------------------------------------------------------------------- transcripts


@dataclass(frozen=True)
class Message:
    """One message the owner typed in a past session."""

    text: str
    at: str          # ISO timestamp from the transcript
    session: str
    path: str


def project_dir_name(root: Path | str) -> str:
    """Claude Code's directory name for a project: every character of the absolute path that
    is not a letter or a digit becomes ``-`` (``C:\\coding\\iaso`` -> ``C--coding-iaso``)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(root).resolve()))


def transcripts_root() -> Path:
    """Where Claude Code keeps its transcripts (``IASO_TRANSCRIPTS_DIR`` overrides it)."""
    override = os.environ.get(TRANSCRIPTS_ENV)
    return Path(override) if override else Path.home() / ".claude" / "projects"


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text") or "") for part in content
                         if isinstance(part, Mapping) and part.get("type") == "text")
    return ""


def _owner(text: str) -> str:
    from iaso.hosts.claude_code.prompt import owner_text

    text = owner_text(text).strip()
    return "" if not text or text.startswith(_HARNESS_STARTS) else text


def _synthetic(entry: Mapping[str, Any]) -> bool:
    """Whether a ``user`` entry was written by the harness rather than typed by the owner."""
    if any(entry.get(flag) for flag in _SYNTHETIC_FLAGS):
        return True
    origin = entry.get("origin")
    return isinstance(origin, Mapping) and origin.get("kind") not in _OWNER_ORIGINS


def owner_messages(project_root: Path | str, base: Path | None = None) -> list[Message]:
    """The owner's own messages in this project's past sessions, oldest first, each text
    once (its earliest time): user messages only (``type == "user"``, text parts), no
    tool results, compaction summaries, transcript-only lines, task notifications,
    cross-session messages or other harness-injected or sidechain messages. Only the folder
    named exactly for this project is read (no worktree's, no other project's)."""
    base = transcripts_root() if base is None else Path(base)
    folder = base / project_dir_name(project_root)
    found: dict[str, Message] = {}
    try:
        files = sorted(folder.glob("*.jsonl")) if folder.is_dir() else []
    except OSError:
        return []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("type") != "user" or _synthetic(entry):
                continue
            message = entry.get("message")
            text = _owner(_text_of(message.get("content") if isinstance(message, Mapping)
                                   else None))
            if not text:
                continue
            at = str(entry.get("timestamp") or "")
            known = found.get(text)
            if known is None or (at and at < known.at):
                found[text] = Message(text=text, at=at,
                                      session=str(entry.get("sessionId") or path.stem),
                                      path=str(path))
    return sorted(found.values(), key=lambda m: m.at)


def _flat(text: str) -> str:
    from iaso.normalize import normalize_text

    return " ".join(normalize_text(text).split())


def holds(text: str, quote: str) -> bool:
    """Whether ``quote`` is verbatim in ``text``: ``approvals.quote_in_prompt`` over
    normalized text (line breaks and runs of spaces count as one space)."""
    from iaso.approvals import quote_in_prompt

    return bool(quote.strip()) and quote_in_prompt(_flat(quote), _flat(text))


# --------------------------------------------------------------------------- records


def quote_parts(record: Any) -> list[str]:
    raw = record.fields.get("quote") or ""
    parts = raw if isinstance(raw, (list, tuple)) else [raw]
    return [" ".join(str(p).split()) for p in parts if str(p).strip()]


def record_view(record: Any) -> dict[str, Any]:
    return {"id": record.id, "title": record.title, "quote": quote_parts(record),
            "readback": " ".join(str(record.fields.get("readback") or "").split())}


def targets(core: Any, ids: Sequence[str] | None = None) -> tuple[list[Any], list[str]]:
    """The intents to recover words for, and why each other named ID is skipped. With no
    IDs: every intent not confirmed whose quote is in no prompt the hook logged. A named
    requirement or decision stands for the intents it derives from. A confirmed intent is
    skipped either way: the owner already confirmed it."""
    from iaso.understand.claim import _Prompts, _verified_intent

    index = core.index()
    statuses = core.status()
    prompts = _Prompts(core)
    skipped: list[str] = []
    wanted: list[Any] = []
    if ids:
        for rid in ids:
            record = index.get(rid)
            if record is None:
                skipped.append(f"{rid}: no such record")
                continue
            if record.kind == "intent":
                sources = [record]
            else:
                sources = [index[link.target.record] for link in record.links
                           if link.kind == "derives_from" and link.target.record in index
                           and index[link.target.record].kind == "intent"]
                if not sources:
                    skipped.append(f"{rid}: it derives from no intent")
            for source in sources:
                if statuses[source.id].confirmation == "confirmed":
                    skipped.append(f"{source.id}: the owner already confirmed it")
                elif _verified_intent(prompts, source) is not None:
                    skipped.append(f"{source.id}: its words are in a prompt the hook logged")
                elif source not in wanted:
                    wanted.append(source)
        return wanted, skipped
    for rid in sorted(index):
        record = index[rid]
        if (record.kind == "intent" and statuses[rid].confirmation != "confirmed"
                and _verified_intent(prompts, record) is None):
            wanted.append(record)
    return wanted, skipped


# --------------------------------------------------------------------------- the cascade


@dataclass(frozen=True)
class Finding:
    """What recovery found for one record. ``status``: ``found`` (the span supports the
    record), ``misreads`` (the best message does not support it; Opus proposes a rewording),
    ``too_short`` (the span a model picked is under ``MIN_SPAN_WORDS`` words and not the
    whole message: not shown) or ``not_found``."""

    id: str
    hash: str
    status: str
    by: str = ""                     # text | sonnet | opus
    span: str = ""
    message: str = ""
    at: str = ""
    session: str = ""
    transcript: str = ""
    reason: str = ""
    proposed_wording: str = ""
    candidates: int = 0
    note: str = NOT_VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Pick:
    message: str        # an id given to the model, or "none"
    span: str
    supports: bool
    reason: str


@dataclass(frozen=True)
class Examination:
    misreads: bool
    explanation: str
    proposed_wording: str = ""


def _job(kind: str, schema_id: str, inputs: Mapping[str, Any]) -> Job:
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode("utf-8")).hexdigest()
    return Job(id=f"{kind}-{digest[:16]}", kind=kind, schema=schema_id, inputs=dict(inputs))


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 3] + "..."


class JevRanker:
    """Ranks messages for a record with JEV: one choice question per batch of messages,
    the probability JEV gives each message is its score. ``RecoveryError`` when JEV
    cannot answer (nothing is ranked by rules in its place)."""

    QUESTION = ("Which of the owner's messages is the one where the owner said what this "
                "record records? Answer none when no message says it.")

    def __init__(self, backend: Any) -> None:
        self.backend = backend

    def rank(self, record: Mapping[str, Any],
             messages: Sequence[Message]) -> list[tuple[float, int]]:
        from iaso.judgment.model import JudgmentQuestion

        scored: list[tuple[float, int]] = []
        for start in range(0, len(messages), JEV_BATCH):
            batch = list(enumerate(messages[start:start + JEV_BATCH], start=start))
            options: dict[str, str | None] = {f"m{i}": None for i, _ in batch}
            options["none"] = None
            lines = [f"[m{i}] ({m.at[:10]}) {_clip(m.text, JEV_MESSAGE_MAX)}" for i, m in batch]
            prompt = (f"Record:\n{json.dumps(record, ensure_ascii=False)}\n\n"
                      "The owner's messages:\n" + "\n\n".join(lines) + "\n")
            question = JudgmentQuestion.choice(self.QUESTION, options)
            try:
                answer = self.backend._ask([("source", question)], prompt).answers["source"]
            except Exception as exc:  # noqa: BLE001 - JEV unreachable: nothing is ranked
                raise RecoveryError(f"no answer from JEV ({exc})") from exc
            probabilities = dict(getattr(answer, "probabilities", None) or {})
            for i, _ in batch:
                p = probabilities.get(f"m{i}")
                if p is None:
                    p = 1.0 if str(getattr(answer, "value", "")) == f"m{i}" else 0.0
                scored.append((float(p), i))
        return sorted(scored, key=lambda s: (-s[0], s[1]))


class ModelPicker:
    """Sonnet (``understand.repin_model``) picks the message and the exact span."""

    def __init__(self, dispatcher: Any) -> None:
        self.dispatcher = dispatcher
        self.name = f"{getattr(dispatcher, 'name', 'model')}:{getattr(dispatcher, 'model', '')}"

    def pick(self, record: Mapping[str, Any], messages: Sequence[Mapping[str, str]]) -> Pick:
        from iaso.understand import agents
        from iaso.understand import schema as schema_check

        inputs = {"record": dict(record), "messages": list(messages)}
        try:
            answer = dict(self.dispatcher.run(
                _job(PICK_KIND, PICK_SCHEMA_ID, inputs), system=agents.load(PICK_KIND),
                user=json.dumps(inputs, ensure_ascii=False, indent=1), schema=pick_schema,
                on_step=lambda step: None))
        except DispatchError as exc:
            raise RecoveryError(f"no answer from {self.name} ({exc.step}: {exc.message})") from exc
        if schema_check.problems(answer, pick_schema):
            raise RecoveryError(f"{self.name} gave an answer outside the schema")
        return Pick(message=str(answer["message"]).strip(), span=str(answer["span"]),
                    supports=bool(answer["supports"]), reason=str(answer["reason"]).strip())


class ModelExaminer:
    """Opus (``understand.diagnose_model``) examines a record its best message does not
    support."""

    def __init__(self, dispatcher: Any) -> None:
        self.dispatcher = dispatcher
        self.name = f"{getattr(dispatcher, 'name', 'model')}:{getattr(dispatcher, 'model', '')}"

    def examine(self, record: Mapping[str, Any], message: Mapping[str, str], span: str,
                reason: str) -> Examination:
        from iaso.understand import agents
        from iaso.understand import schema as schema_check

        inputs = {"record": dict(record), "message": dict(message), "span": span,
                  "why_not_supported": reason}
        try:
            answer = dict(self.dispatcher.run(
                _job(EXAMINE_KIND, EXAMINE_SCHEMA_ID, inputs), system=agents.load(EXAMINE_KIND),
                user=json.dumps(inputs, ensure_ascii=False, indent=1), schema=examine_schema,
                on_step=lambda step: None))
        except DispatchError as exc:
            raise RecoveryError(f"no answer from {self.name} ({exc.step}: {exc.message})") from exc
        if schema_check.problems(answer, examine_schema):
            raise RecoveryError(f"{self.name} gave an answer outside the schema")
        explanation = str(answer.get("explanation") or "").strip()
        wording = " ".join(str(answer.get("proposed_wording") or "").split())
        misreads = answer.get("verdict") == "misreads"
        if not explanation or (misreads and not wording):
            raise RecoveryError(f"{self.name} gave an answer missing what its verdict needs")
        return Examination(misreads=misreads, explanation=explanation, proposed_wording=wording)


def _dispatcher(core: Any, model: str) -> Any:
    from iaso.understand.dispatch import configured

    try:
        dispatcher = configured(core, model=model)
    except NoModel as exc:
        raise RecoveryError(str(exc)) from exc
    problem = dispatcher.available()
    if problem is not None:
        raise RecoveryError(str(problem))
    return dispatcher


@dataclass
class Cascade:
    """The three models, opened on first need from the configuration unless given."""

    core: Any
    jev: Any = None
    picker: Any = None
    examiner: Any = None
    _opened: dict[str, Any] = field(default_factory=dict)

    def ranker(self) -> JevRanker:
        if self.jev is None:
            from iaso.judgment.jev import JevBackend, open_jev
            from iaso.judgment.tiers import Thresholds

            config = self.core.config
            try:
                backend = open_jev(self.core, config, hook=False,
                                   thresholds=Thresholds.from_config(config.judgment.jev))
            except Exception as exc:  # noqa: BLE001 - no key, not configured: say so
                raise RecoveryError(f"JEV cannot be reached ({exc})") from exc
            if not isinstance(backend, JevBackend):
                raise RecoveryError("JEV is not the configured judgment backend")
            self.jev = backend
        return JevRanker(self.jev)

    def sonnet(self) -> Any:
        if self.picker is None:
            self.picker = ModelPicker(
                _dispatcher(self.core, self.core.config.understand.repin_model))
        return self.picker

    def opus(self) -> Any:
        if self.examiner is None:
            self.examiner = ModelExaminer(
                _dispatcher(self.core, self.core.config.understand.diagnose_model))
        return self.examiner


def _shown(i: int, message: Message) -> dict[str, str]:
    return {"id": f"m{i}", "at": message.at, "session": message.session,
            "text": _clip(message.text, MESSAGE_MAX)}


def exact_match(record: Any, messages: Sequence[Message]) -> Message | None:
    """The earliest message holding every part of the record's quote verbatim, or None."""
    parts = quote_parts(record)
    if not parts:
        return None
    for message in messages:
        if all(holds(message.text, part) for part in parts):
            return message
    return None


def long_enough(span: str, message: str) -> bool:
    """A span worth showing: at least ``MIN_SPAN_WORDS`` words, or the whole message."""
    return len(span.split()) >= MIN_SPAN_WORDS or _flat(span) == _flat(message)


def recover_one(record: Any, messages: Sequence[Message], cascade: Cascade) -> Finding:
    """The cascade for one record. Raises ``RecoveryError`` when a model it needs gives no
    usable answer: nothing is decided then."""
    view = record_view(record)
    base = {"id": record.id, "hash": record.hash, "candidates": len(messages)}

    def found(message: Message, status: str, by: str, span: str, **more: Any) -> Finding:
        return Finding(**base, status=status, by=by, span=span,
                       message=_clip(message.text, MESSAGE_MAX), at=message.at,
                       session=message.session, transcript=message.path, **more)

    exact = exact_match(record, messages)
    if exact is not None:
        return found(exact, "found", "text", " / ".join(view["quote"]),
                     reason="the record's quote is word for word in this message")
    if not messages:
        return Finding(**base, status="not_found", by="text", note=NOT_FOUND)
    ranked = cascade.ranker().rank(view, messages)
    best = [i for _, i in ranked[:TOP_K]]
    shown = {f"m{i}": (i, messages[i]) for i in best}
    pick = cascade.sonnet().pick(view, [_shown(i, messages[i]) for i in best])
    if pick.message == "none":
        return Finding(**base, status="not_found", by="sonnet", reason=pick.reason,
                       note=NOT_FOUND)
    if pick.message not in shown:
        raise RecoveryError(f"the model named a message it was not shown ({pick.message})")
    i, message = shown[pick.message]
    if not holds(message.text, pick.span):
        raise RecoveryError("the span the model picked is not word for word in the message")
    span = " ".join(pick.span.split())

    def shown_span(status: str, by: str, reason: str, **more: Any) -> Finding:
        if not long_enough(span, message.text):
            return Finding(**base, status="too_short", by=by, at=message.at,
                           session=message.session, transcript=message.path, reason=reason,
                           note=TOO_SHORT)
        return found(message, status, by, span, reason=reason, **more)

    if pick.supports:
        return shown_span("found", "sonnet", pick.reason)
    verdict = cascade.opus().examine(view, _shown(i, message), span, pick.reason)
    if verdict.misreads:
        return shown_span("misreads", "opus", verdict.explanation,
                          proposed_wording=verdict.proposed_wording)
    return shown_span("found", "opus", verdict.explanation)


# --------------------------------------------------------------------------- the cache


def cache_path(core: Any) -> Path:
    return Path(core.paths.cache) / CACHE_NAME


def load_cache(core: Any) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(cache_path(core).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)} if isinstance(
        data, dict) else {}


def save_findings(core: Any, findings: Iterable[Finding]) -> None:
    cache = load_cache(core)
    for finding in findings:
        cache[finding.hash] = finding.to_dict()
    path = cache_path(core)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, sort_keys=True, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)


def finding_for(core: Any, record: Any) -> dict[str, Any] | None:
    """What recovery found for ``record`` at its current content, or None. A record changed
    since has a new hash and so no finding."""
    entry = load_cache(core).get(str(record.hash))
    return entry if entry is not None and entry.get("id") == record.id else None


# --------------------------------------------------------------------------- the run


@dataclass
class Outcome:
    findings: list[Finding] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    planned: list[dict[str, Any]] = field(default_factory=list)   # --dry-run


def recover(core: Any, ids: Sequence[str] | None = None, *, dry_run: bool = False,
            transcripts: Path | None = None, cascade: Cascade | None = None) -> Outcome:
    """Recover the words of ``ids`` (or every unverified intent). ``dry_run`` asks no model
    and writes nothing: it lists each record, how many messages it would be matched
    against, and any word-for-word match found by text."""
    out = Outcome()
    records, out.skipped = targets(core, ids)
    if not records:
        return out
    messages = owner_messages(core.root, transcripts)
    cascade = cascade or Cascade(core)
    for record in records:
        if dry_run:
            exact = exact_match(record, messages)
            out.planned.append({"id": record.id, "candidates": len(messages),
                                "word_for_word": bool(exact), "at": exact.at if exact else ""})
            continue
        try:
            out.findings.append(recover_one(record, messages, cascade))
        except RecoveryError as exc:
            out.errors.append((record.id, str(exc)))
    if out.findings:
        save_findings(core, out.findings)
    return out


def finding_lines(finding: Mapping[str, Any]) -> list[str]:
    """One finding in plain words (the CLI and the card text share them)."""
    status = finding.get("status")
    if status == "not_found":
        return [str(finding.get("note") or NOT_FOUND)]
    if status == "too_short":
        return [str(finding.get("note") or TOO_SHORT)]
    when = str(finding.get("at") or "")[:10] or "an unknown date"
    session = str(finding.get("session") or "")[:8]
    lines = [f'found in a transcript of {when} (session {session}), not verified: '
             f'"{finding.get("span")}"']
    if status == "misreads":
        lines.append(f"the record may misread you: {finding.get('reason')}")
        lines.append(f'proposed rewording: "{finding.get("proposed_wording")}"')
    return lines
