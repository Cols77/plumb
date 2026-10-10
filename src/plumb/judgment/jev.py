"""The optional JEV adapter (spec 8.2): TypeSafe's fast typed-judgment model.

Active only when a key resolves for the variable ``judgment.jev.credential_env`` names
(``TYPESAFE_API_KEY``, or ``OPENROUTER_API_KEY`` with ``provider: openrouter``): from the
process environment, then from the env file the user-level ``~/.config/plumb/jev.json``
names (read in place, never copied), then from the legacy raw-key store
``~/.config/plumb/jev``. A key is never read from inside the repository, and never written to
a log, record, notice or output. The client speaks the Decisions wire shapes pinned by
pi-agent-factory's vendor verification record (``POST {base_url}{path}`` with
``{state, model, questions}``; ``/v1/systemone`` at TypeSafe, ``/api/alpha/decisions`` at
OpenRouter) through
``urllib.request``: hard timeout ``judgment.hook_timeout_ms`` in hooks, 10 s on the command
line, no retries. A missing key, a timeout or any error falls back to the heuristic with one
notice per session window. Every JEV judgment is logged as a ``judgment`` event carrying its
request fingerprint. Judgments stay advisory: they never confirm or freshen anything.
"""

from __future__ import annotations

import json
import os
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
from plumb.judgment.tiers import Thresholds, route, same_version

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


def credential_env(config: Any) -> str:
    """The NAME of the environment variable holding the JEV credential (sp2 C7)."""
    jev = getattr(getattr(config, "judgment", None), "jev", None) or {}
    name = str(jev.get("credential_env") or API_KEY_ENV).strip()
    return name if name and name.replace("_", "").isalnum() else API_KEY_ENV


def user_config_path() -> Path:
    """The user-level ``jev.json``: ``{"credential_env": NAME, "env_file": PATH}``. It names
    where the credential lives; it never holds the credential."""
    return Path.home() / ".config" / "plumb" / "jev.json"


def _inside(path: Path, root: Path | None) -> bool:
    return root is not None and path.resolve().is_relative_to(Path(root).resolve())


def user_env_file(root: Path | None = None) -> Path | None:
    """The env file ``jev.json`` names: absolute, outside the repository, else None."""
    config = user_config_path()
    try:
        if _inside(config, root):
            return None
        data = json.loads(config.read_text(encoding="utf-8"))
        raw = data.get("env_file") if isinstance(data, dict) else None
        if not isinstance(raw, str) or not raw.strip():
            return None
        path = Path(raw.strip()).expanduser()
        if not path.is_absolute() or _inside(path, root):
            return None  # keys are never repository state
        return path.resolve()
    except (OSError, ValueError):
        return None


def parse_env_value(text: str, name: str) -> str | None:
    """The value of ``name`` in env-file text (``KEY=VALUE`` lines, an optional ``export``,
    optional quotes; comments and blank lines ignored). The last assignment wins."""
    found: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep or key.strip() != name:
            continue
        value = value.strip()
        if value[:1] in ("'", '"'):
            end = value.find(value[0], 1)
            value = value[1:end] if end > 0 else value[1:]
        else:
            value = value.split(" #", 1)[0].split("\t#", 1)[0].strip()
        found = value
    return found


def _env_file_key(root: Path | None, name: str) -> str | None:
    path = user_env_file(root)
    if path is None:
        return None
    try:
        value = parse_env_value(path.read_text(encoding="utf-8-sig"), name)
    except (OSError, UnicodeDecodeError):
        return None
    return value if value is not None and _valid_key(value) else None


def _lookup(root: Path | None, env: Mapping[str, str] | None,
            name: str) -> tuple[str, str] | None:
    """``(source label, key)``: the process environment, then the user env file, then the
    legacy raw-key store."""
    value = (os.environ if env is None else env).get(name, "").strip()
    if _valid_key(value):
        return "env", value
    value = _env_file_key(root, name) or ""
    if value:
        return "env-file", value
    value = _store_key(root) or ""
    return ("user-store", value) if value else None


def key_source(root: Path | None = None, env: Mapping[str, str] | None = None,
               name: str = API_KEY_ENV) -> str | None:
    """``env``, ``env-file``, ``user-store`` or None. Never returns the key itself."""
    found = _lookup(root, env, name)
    return found[0] if found else None


def resolve_key(root: Path | None = None, env: Mapping[str, str] | None = None,
                name: str = API_KEY_ENV) -> str | None:
    found = _lookup(root, env, name)
    return found[1] if found else None


# --------------------------------------------------------------------------- client


def _usage(raw: Mapping[str, Any]) -> dict[str, int | float]:
    """The numeric usage fields as sent: token counts stay integers, a gateway's ``cost``
    stays a float."""
    return {str(k): v for k, v in raw.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


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


def endpoint_url(base_url: str, path: str | None = None) -> str:
    """``base_url`` joined with the Decisions ``path`` (one slash between them)."""
    return base_url.rstrip("/") + "/" + (path or SYSTEM_ONE_PATH).lstrip("/")


class JevClient:
    """Minimal ``urllib`` client of the Decisions endpoint (``/v1/systemone`` at TypeSafe,
    ``/api/alpha/decisions`` at OpenRouter). Never raises: it fails safe."""

    def __init__(self, *, base_url: str, key: str, timeout_s: float,
                 path: str = SYSTEM_ONE_PATH) -> None:
        self.url = endpoint_url(base_url, path)
        self.key = key
        self.timeout_s = timeout_s
        self.last_error: str | None = None

    def judge(self, request: JudgmentRequest) -> JudgmentRecord:
        import urllib.error  # imported here: the hooks only look for the credential, and
        import urllib.request  # the network modules cost import time

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
            usage = _usage(usage) if isinstance(usage, Mapping) else None
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
        self.resolved_version: str | None = None

    @property
    def version(self) -> str:
        """The resolved model version of the last answer, else the configured alias."""
        return self.resolved_version or self.model

    @property
    def available(self) -> bool:
        """False once a call failed: the rest of this process uses the heuristic."""
        return not self._down

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
        self.resolved_version = record.resolved_version
        return record

    def _notice(self, reason: str) -> None:
        from plumb.judgment import notice_once

        note = notice_once(self.root, "jev-unavailable",
                           f"plumb: jev unavailable ({reason}); using the heuristic")
        if note:
            self.notices = (*self.notices, note)

    def _judgment(self, record: JudgmentRecord, name: str, action: str, subject: str,
                  verdict: str, **extra: Any) -> Judgment:
        from plumb.judgment.heuristic import confidence_label

        answer = record.answers[name]
        tier = route(answer.confidence, self.thresholds,
                     resolved_version=record.resolved_version,
                     validated_against=self.validated_against)
        judgment = Judgment(action=action, subject=subject, verdict=verdict,  # type: ignore[arg-type]
                            confidence=round(answer.confidence, 6), tier=tier,
                            backend=f"jev:{record.resolved_version}",
                            fingerprint=record.request_fingerprint,
                            reasons=(f"{answer.kind} answer {answer.value}",),
                            probability=_probability(answer, verdict),
                            confidence_label=confidence_label(  # type: ignore[arg-type]
                                answer.confidence))
        payload = {"subject": subject, "action": action, "verdict": verdict,
                   "confidence": judgment.confidence, "tier": tier,
                   "backend": judgment.backend, "fingerprint": judgment.fingerprint,
                   "version_drift": (self.validated_against is not None and not same_version(
                       record.resolved_version, self.validated_against)),
                   "model_version": record.resolved_version,
                   "probability": judgment.probability,
                   "confidence_label": judgment.confidence_label}
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

    # -- sp2 11.2
    def entailment(self, premise: str, hypothesis: str, *, subject: str,
                   claim_kind: str) -> Judgment:
        """Do the owner's words (the premise) support every part of the claim? A Noul; the
        judgment's probability is the vendor's probability of its verdict (sp2 8.2)."""
        question = JudgmentQuestion.noul(
            "Do the owner's words support every part of the claim, with nothing added, "
            "dropped or changed?", "the owner's words support the whole claim",
            "the claim adds, drops or changes something the owner did not say")
        prefix = (f"Owner's words:\n{premise}\n\nClaim ({claim_kind}, {subject}):\n"
                  f"{hypothesis}\n")
        record = self._ask([("entailment", question)], prefix)
        if record is None:
            return self.fallback.entailment(premise, hypothesis, subject=subject,
                                            claim_kind=claim_kind)
        p = float(record.answers["entailment"].value)
        verdict = "entailed" if p >= 0.5 else "not-entailed"
        return self._judgment(record, "entailment", "faithfulness", subject, verdict,
                              claim_kind=claim_kind)

    def contradiction(self, prompt: str, record: Record) -> Judgment:
        from plumb.judgment.heuristic import record_text

        question = JudgmentQuestion.choice(
            f"Does the request contradict the confirmed requirement {record.id} (negate, "
            "replace or reverse a confirmed example or its statement), extend it (add "
            "behaviour beside it), or leave it as it is?",
            {"contradicts": "it negates, replaces or reverses confirmed behaviour",
             "extends": "it adds behaviour beside the confirmed behaviour",
             "benign": "a mention, a question or a tidy-up; the behaviour stays"})
        prefix = f"Request:\n{prompt}\n\n{record.id}: {record_text(record)}\n"
        answer = self._ask([("contradiction", question)], prefix)
        if answer is None:
            return self.fallback.contradiction(prompt, record)
        return self._judgment(answer, "contradiction", "contradiction", record.id,
                              str(answer.answers["contradiction"].value))

    def choose(self, question: str, options: Sequence[str], *, subject: str,
               context: str = "") -> Judgment:
        choices: dict[str, str | None] = {str(o): None for o in list(options)[:254]}
        choices["none"] = "none of these"
        record = self._ask([("choose", JudgmentQuestion.choice(question, choices))],
                           f"Context:\n{context}\n")
        if record is None:
            return self.fallback.choose(question, options, subject=subject, context=context)
        return self._judgment(record, "choose", "ownership", subject,
                              str(record.answers["choose"].value))

    def ask(self, question: str, context: str, *, subject: str, action: str) -> Judgment:
        record = self._ask([("ask", JudgmentQuestion.noul(question, "yes", "no"))],
                           f"Context:\n{context}\n")
        if record is None:
            return self.fallback.ask(question, context, subject=subject, action=action)
        p = float(record.answers["ask"].value)
        return self._judgment(record, "ask", action, subject, "yes" if p >= 0.5 else "no")


def _probability(answer: JudgmentAnswer, verdict: str) -> float:
    """The probability of the verdict: a Noul's ``true`` probability for a positive verdict
    and its ``false`` probability otherwise; a choice's probability of its label."""
    if answer.kind == "noul":
        p = float(answer.value)
        positive = verdict in ("entailed", "yes", "change", "material")
        return round(p if positive else 1 - p, 6)
    try:
        return round(float(answer.probabilities.get(str(answer.value), answer.confidence)), 6)
    except (TypeError, ValueError):
        return round(float(answer.confidence), 6)


def open_jev(core: Any, config: Any, *, hook: bool, thresholds: Thresholds) -> Any:
    """The JEV backend when a key exists, else the heuristic with one notice."""
    from plumb.judgment import notice_once
    from plumb.judgment.heuristic import HeuristicBackend

    root = Path(core.root)
    name = credential_env(config)
    key = resolve_key(root, name=name)
    if key is None:
        note = notice_once(root, "jev-no-key", f"plumb: no JEV key ({name} in the "
                           "environment, or the env file ~/.config/plumb/jev.json names); "
                           "using the heuristic")
        return HeuristicBackend(thresholds, [note] if note else [])
    jev = dict(config.judgment.jev or {})
    timeout = (max(0.05, float(config.judgment.hook_timeout_ms) / 1000.0) if hook
               else CLI_TIMEOUT_S)
    client = JevClient(base_url=str(jev.get("base_url") or "https://api.typesafe.ai"), key=key,
                       timeout_s=timeout, path=str(jev.get("path") or SYSTEM_ONE_PATH))
    validated = jev.get("validated_against")
    return JevBackend(core, client, model=str(jev.get("model") or DEFAULT_MODEL_ALIAS),
                      validated_against=str(validated) if validated else None,
                      thresholds=thresholds)
