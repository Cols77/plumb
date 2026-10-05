"""The optional JEV adapter (spec 8.2): TypeSafe's fast typed-judgment model.

Active only when a key exists in ``TYPESAFE_API_KEY`` or in the user store
``~/.config/plumb/jev``; a key is never read from inside the repository. The client speaks
the wire shapes pinned by pi-agent-factory's vendor verification record
(``POST {base_url}/v1/systemone`` with ``{state, model, questions}``) through
``urllib.request``: hard timeout ``judgment.hook_timeout_ms`` in hooks, 10 s on the command
line, no retries. A missing key, a timeout or any error falls back to the heuristic with one
notice per session window. Every JEV judgment is logged as a ``judgment`` event carrying its
request fingerprint. Judgments stay advisory: they never confirm or freshen anything.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb import __version__
from plumb.contracts import FidelityPacket, Judgment, LinkState, Record
from plumb.judgment.model import (
    DEFAULT_MODEL_ALIAS,
    JudgmentAnswer,
    JudgmentQuestion,
    JudgmentRecord,
    JudgmentRequest,
    make_record,
)
from plumb.judgment.tiers import Thresholds, route

API_KEY_ENV = "TYPESAFE_API_KEY"
SYSTEM_ONE_PATH = "/v1/systemone"
CLI_TIMEOUT_S = 10.0
FIDELITY_LEVELS = ("drifts", "unsure", "fits")


# --------------------------------------------------------------------------- key


def user_store_path() -> Path:
    return Path.home() / ".config" / "plumb" / "jev"


def _valid_key(value: str) -> bool:
    return bool(value) and value.isascii() and value.isprintable() and not any(
        c.isspace() for c in value)


def _store_key(root: Path | None) -> str | None:
    store = user_store_path()
    try:
        resolved = store.resolve()
        if root is not None and resolved.is_relative_to(Path(root).resolve()):
            return None  # keys are never repository state
        value = store.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value if _valid_key(value) else None


def key_source(root: Path | None = None, env: Mapping[str, str] | None = None) -> str | None:
    """``env``, ``user-store`` or None. Never returns the key itself."""
    value = (os.environ if env is None else env).get(API_KEY_ENV, "").strip()
    if _valid_key(value):
        return "env"
    return "user-store" if _store_key(root) else None


def resolve_key(root: Path | None = None, env: Mapping[str, str] | None = None) -> str | None:
    value = (os.environ if env is None else env).get(API_KEY_ENV, "").strip()
    if _valid_key(value):
        return value
    return _store_key(root)


# --------------------------------------------------------------------------- client


def _answer(kind: str, raw: Mapping[str, Any]) -> JudgmentAnswer:
    if raw.get("type") != kind:
        raise ValueError(f"answer type {raw.get('type')!r} does not match {kind!r}")
    if kind == "noul":
        return JudgmentAnswer.from_noul(float(raw["noul"]))
    if kind == "choice":
        return JudgmentAnswer.from_vendor("choice", str(raw["choice"]),
                                          dict(raw.get("probabilities") or {}),
                                          float(raw["confidence"]))
    return JudgmentAnswer.from_vendor("score", float(raw["score"]),
                                      dict(raw.get("probabilities") or {}),
                                      float(raw["confidence"]))


class JevClient:
    """Minimal ``urllib`` client of ``/v1/systemone``. Never raises: it fails safe."""

    def __init__(self, *, base_url: str, key: str, timeout_s: float) -> None:
        self.url = base_url.rstrip("/") + SYSTEM_ONE_PATH
        self.key = key
        self.timeout_s = timeout_s
        self.last_error: str | None = None

    def judge(self, request: JudgmentRequest) -> JudgmentRecord:
        from plumb.normalize import utc_now

        body = json.dumps({"state": request.state, "model": request.model,
                           "questions": {name: q.to_wire() for name, q in request.questions}},
                          ensure_ascii=False).encode("utf-8")
        http = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": f"plumb/{__version__}"})
        self.last_error = None
        try:
            with urllib.request.urlopen(http, timeout=self.timeout_s) as response:  # noqa: S310
                raw = response.read()
        except urllib.error.HTTPError as exc:
            self.last_error = f"HTTP {exc.code}"
            return make_record(request, outcome="unavailable", timestamp=utc_now())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.last_error = "timeout" if "timed out" in str(exc) else type(exc).__name__
            return make_record(request, outcome="unavailable", timestamp=utc_now())
        try:
            data = json.loads(raw.decode("utf-8"))
            model = data["model"]
            if not isinstance(model, str) or not model:
                raise ValueError("no resolved model")
            answers_raw = data["answers"]
            answers = {name: _answer(q.kind, answers_raw[name]) for name, q in request.questions}
            usage = data.get("usage")
            usage = {k: int(v) for k, v in usage.items()} if isinstance(usage, Mapping) else None
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            self.last_error = f"malformed response ({type(exc).__name__})"
            return make_record(request, outcome="invalid", timestamp=utc_now())
        return make_record(request, outcome="ok", timestamp=utc_now(), resolved_version=model,
                           answers=answers, usage=usage)


# --------------------------------------------------------------------------- backend


class JevBackend:
    """``JudgmentBackend`` over JEV, with the heuristic as its fallback."""

    name = "jev"

    def __init__(self, core: Any, client: JevClient, *, model: str,
                 validated_against: str | None, thresholds: Thresholds) -> None:
        from plumb.judgment.heuristic import HeuristicBackend

        self.core = core
        self.root = Path(core.root)
        self.client = client
        self.model = model
        self.validated_against = validated_against
        self.thresholds = thresholds
        self.fallback = HeuristicBackend(thresholds)
        self.notices: tuple[str, ...] = ()
        self._down = False

    # -- plumbing
    def _ask(self, questions: Sequence[tuple[str, JudgmentQuestion]], prefix: str,
             paths: Sequence[str] = ()) -> JudgmentRecord | None:
        from plumb.judgment.state import assemble_state, context_limits

        if self._down or not questions:
            return None
        state = assemble_state(self.root, paths, questions, prefix=prefix,
                               tracked=None if paths else (),
                               limits=context_limits(self.validated_against))
        request = JudgmentRequest(state=state.text, questions=tuple(questions),
                                  model=self.model, truncation=state.truncation)
        record = self.client.judge(request)
        if record.outcome != "ok":
            self._down = True  # no retries: the rest of this process uses the heuristic
            self._notice(self.client.last_error or record.outcome)
            return None
        return record

    def _notice(self, reason: str) -> None:
        from plumb.judgment import notice_once

        note = notice_once(self.root, "jev-unavailable",
                           f"plumb: jev unavailable ({reason}); using the heuristic")
        if note:
            self.notices = (*self.notices, note)

    def _judgment(self, record: JudgmentRecord, name: str, action: str, subject: str,
                  verdict: str, **extra: Any) -> Judgment:
        answer = record.answers[name]
        tier = route(answer.confidence, self.thresholds,
                     resolved_version=record.resolved_version,
                     validated_against=self.validated_against)
        judgment = Judgment(action=action, subject=subject, verdict=verdict,  # type: ignore[arg-type]
                            confidence=round(answer.confidence, 6), tier=tier,
                            backend=f"jev:{record.resolved_version}",
                            fingerprint=record.request_fingerprint,
                            reasons=(f"{answer.kind} answer {answer.value}",))
        payload = {"subject": subject, "action": action, "verdict": verdict,
                   "confidence": judgment.confidence, "tier": tier,
                   "backend": judgment.backend, "fingerprint": judgment.fingerprint,
                   "version_drift": record.resolved_version != self.validated_against}
        payload.update(extra)
        try:
            self.core.log_append("events", "judgment", payload)
        except OSError:
            pass
        return judgment

    # -- JudgmentBackend
    def intent_change(self, prompt: str, records: Sequence[Record]) -> Sequence[Judgment]:
        from plumb.judgment.heuristic import record_text

        questions = [(r.id, JudgmentQuestion.noul(
            f"Does the user's request change, contradict or extend the confirmed "
            f"requirement {r.id}?", "the request changes, contradicts or extends it",
            "the request leaves it as it is")) for r in records]
        prefix = "Request:\n" + prompt + "\n\n" + "\n".join(
            f"{r.id}: {record_text(r)}" for r in records) + "\n"
        record = self._ask(questions, prefix)
        if record is None:
            return self.fallback.intent_change(prompt, records)
        return [self._judgment(record, r.id, "intent-change", r.id,
                               "change" if float(record.answers[r.id].value) >= 0.5
                               else "no-change") for r in records]

    def drift_triage(self, states: Sequence[LinkState],
                     texts: Mapping[str, tuple[str, str]]) -> Sequence[Judgment]:
        from plumb.hashing import target_path
        from plumb.judgment.state import is_secret_path

        chosen = [s for s in states if s.link.id in texts
                  and not is_secret_path(target_path(s.link.target) or "")]
        if not chosen:
            return self.fallback.drift_triage(states, texts)
        questions = [(s.link.id, JudgmentQuestion.noul(
            f"Is the change of link end {s.link.id} material (behaviour or meaning), rather "
            "than cosmetic (comments, docstrings, formatting)?", "material", "cosmetic"))
            for s in chosen]
        prefix = "".join(f"--- {s.link.id} before ---\n{texts[s.link.id][0]}\n"
                         f"--- {s.link.id} after ---\n{texts[s.link.id][1]}\n" for s in chosen)
        record = self._ask(questions, prefix)
        if record is None:
            return self.fallback.drift_triage(states, texts)
        return [self._judgment(record, s.link.id, "drift-triage", s.link.id,
                               "material" if float(record.answers[s.link.id].value) >= 0.5
                               else "cosmetic") for s in chosen]

    def fidelity(self, packet: FidelityPacket) -> Judgment:
        examples = "\n".join(
            f"{e.id}: {e.criterion}" if e.criterion
            else f"{e.id}: given {e.given}; when {e.when}; then {e.then}"
            for e in packet.examples)
        prefix = (f"Requirement {packet.requirement}: {packet.statement}\n{examples}\n"
                  "Evidence: " + ", ".join(f"{e.get('node_id')} {e.get('state')}"
                                           for e in packet.evidence) + "\n")
        paths = [str(e["path"]) for e in packet.ends if e.get("path") and not e.get("missing")]
        question = JudgmentQuestion.score(
            f"How well do the linked code and tests fit requirement {packet.requirement} and "
            "its examples?", list(FIDELITY_LEVELS))
        record = self._ask([("fidelity", question)], prefix, paths)
        if record is None:
            return self.fallback.fidelity(packet)
        level = max(0, min(len(FIDELITY_LEVELS) - 1,
                           round(float(record.answers["fidelity"].value))))
        hashes = {str(e["link"]): e.get("hash") for e in packet.ends}
        return self._judgment(record, "fidelity", "fidelity", packet.requirement,
                              FIDELITY_LEVELS[level], requirement_hash=packet.requirement_hash,
                              end_hashes=hashes, note="jev score (advisory)")


def open_jev(core: Any, config: Any, *, hook: bool, thresholds: Thresholds) -> Any:
    """The JEV backend when a key exists, else the heuristic with one notice."""
    from plumb.judgment import notice_once
    from plumb.judgment.heuristic import HeuristicBackend

    root = Path(core.root)
    key = resolve_key(root)
    if key is None:
        note = notice_once(root, "jev-no-key", "plumb: no JEV key (TYPESAFE_API_KEY or "
                           "~/.config/plumb/jev); using the heuristic")
        return HeuristicBackend(thresholds, [note] if note else [])
    jev = dict(config.judgment.jev or {})
    timeout = (max(0.05, float(config.judgment.hook_timeout_ms) / 1000.0) if hook
               else CLI_TIMEOUT_S)
    client = JevClient(base_url=str(jev.get("base_url") or "https://api.typesafe.ai"), key=key,
                       timeout_s=timeout)
    validated = jev.get("validated_against")
    return JevBackend(core, client, model=str(jev.get("model") or DEFAULT_MODEL_ALIAS),
                      validated_against=str(validated) if validated else None,
                      thresholds=thresholds)
