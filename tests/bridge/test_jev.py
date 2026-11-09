"""BRIDGE BS3: the optional JEV adapter against a local stub (spec 8.2). No network."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.contracts import Link, LinkState, Pin, Target
from plumb.judgment import JudgmentUnavailable, get_backend
from plumb.judgment import jev as jev_mod
from plumb.judgment.model import JudgmentQuestion, JudgmentRequest
from plumb.judgment.state import assemble_state, is_secret_path

pytestmark = pytest.mark.sr("SR-245")

KEY = "ts-test-key-abcdefghij"
SR_004 = """---
id: SR-004
title: Approvals pin exact content
statement: An approval pins the record hash.
links:
- kind: implemented_by
  path: src/mod.py
---
"""


class Stub:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.delay = 0.0
        self.noul = 0.95
        self.model = "jev-1.13.0"
        self.status = 200
        self.usage: dict = {"input_tokens": 10, "output_tokens": 2}


@pytest.fixture
def stub() -> Iterator[tuple[Stub, str]]:
    state = Stub()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet
            pass

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            state.requests.append({"path": self.path, "headers": dict(self.headers),
                                   "body": body})
            if state.delay:
                time.sleep(state.delay)
            answers = {}
            for name, q in body["questions"].items():
                if q["type"] == "noul":
                    answers[name] = {"type": "noul", "noul": state.noul}
                elif q["type"] == "choice":
                    label = next(iter(q["criteria"]))
                    answers[name] = {"type": "choice", "choice": label,
                                     "probabilities": {label: 0.88}, "confidence": 0.81}
                else:
                    answers[name] = {"type": "score", "score": 1.9,
                                     "legend": {"0": "drifts", "1": "unsure", "2": "fits"},
                                     "probabilities": {"0": 0.0, "1": 0.1, "2": 0.9},
                                     "confidence": 0.92}
            payload = json.dumps({"model": state.model, "answers": answers,
                                  "usage": state.usage}).encode()
            try:
                self.send_response(state.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except OSError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def jev_repo(repo: Path, write_record, stub, monkeypatch, tmp_path: Path):
    state, url = stub
    write_record(repo, SR_004)
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / ".plumb" / "config.yaml").write_text(
        "judgment:\n  backend: jev\n  hook_timeout_ms: 300\n"
        f"  jev: {{base_url: '{url}'}}\n", encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", KEY)
    monkeypatch.setattr(jev_mod, "user_store_path", lambda: tmp_path / "home" / "jev")
    return repo, state


def test_request_shape_matches_pinned_wire_format(jev_repo) -> None:
    repo, state = jev_repo
    core = open_core(repo)
    backend = get_backend(core, hook=True)
    assert backend.name == "jev"
    [j] = backend.intent_change("instead, SR-004 should change", [core.index()["SR-004"]])
    [request] = state.requests
    assert request["path"] == "/v1/systemone"
    headers = {k.lower(): v for k, v in request["headers"].items()}
    assert headers["authorization"] == f"Bearer {KEY}"
    assert headers["content-type"] == "application/json"
    assert headers["accept"] == "application/json"
    body = request["body"]
    assert set(body) == {"state", "model", "questions"}
    assert body["model"] == "jev-latest"
    assert isinstance(body["state"], str) and "SR-004" in body["state"]
    [question] = body["questions"].values()
    assert question["type"] == "noul"
    assert set(question["criteria"]) == {"true", "false"}
    assert KEY not in json.dumps(body)


def test_parses_noul_choice_score_answers(jev_repo) -> None:
    repo, state = jev_repo
    client = jev_mod.JevClient(base_url=jev_repo_url(state, repo), key=KEY, timeout_s=5)
    request = JudgmentRequest(state="s", questions=(
        ("n", JudgmentQuestion.noul("i", "t", "f")),
        ("c", JudgmentQuestion.choice("i", {"billing": None, "tech": None})),
        ("s", JudgmentQuestion.score("i", ["drifts", "unsure", "fits"]))))
    record = client.judge(request)
    assert record.outcome == "ok"
    assert record.resolved_version == "jev-1.13.0"
    assert record.answers["n"].confidence == pytest.approx(0.95)
    assert record.answers["n"].confidence_source == "derived"
    assert record.answers["c"].value == "billing"
    assert record.answers["c"].confidence == pytest.approx(0.81)
    assert record.answers["s"].value == pytest.approx(1.9)
    assert record.answers["s"].probabilities == {"0": 0.0, "1": 0.1, "2": 0.9}
    assert record.usage == {"input_tokens": 10, "output_tokens": 2}


def jev_repo_url(state: Stub, repo: Path) -> str:
    config = (repo / ".plumb" / "config.yaml").read_text(encoding="utf-8")
    return config.split("base_url: '", 1)[1].split("'", 1)[0]


def test_fidelity_score_with_version_drift(jev_repo) -> None:
    repo, state = jev_repo
    from plumb.judgment.fidelity import build_packet

    core = open_core(repo)
    backend = get_backend(core, hook=False)
    j = backend.fidelity(build_packet(core, None, "SR-004"))
    assert (j.action, j.verdict, j.backend) == ("fidelity", "fits", "jev:jev-1.13.0")
    assert j.tier == "accept"
    state.model = "jev-1.14.0"
    j = get_backend(open_core(repo), hook=False).fidelity(build_packet(core, None, "SR-004"))
    assert j.tier == "escalate-llm"  # accept suspended on version drift
    from plumb.judgment.fidelity import unjudged

    # only the accepted score covers the current hashes; the escalated one does not
    assert unjudged(open_core(repo), ["SR-004"]) == ()
    (repo / "src" / "mod.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    get_backend(open_core(repo), hook=False).fidelity(build_packet(open_core(repo), None,
                                                                   "SR-004"))
    assert unjudged(open_core(repo), ["SR-004"]) == ("SR-004",)


def test_timeout_raises_an_error_naming_jev_and_the_timeout(jev_repo) -> None:
    """SR-021 EX-2: nothing falls back to a rule-based answer."""
    repo, state = jev_repo
    state.delay = 1.5
    core = open_core(repo)
    backend = get_backend(core, hook=True)
    started = time.monotonic()
    with pytest.raises(JudgmentUnavailable) as caught:
        backend.intent_change("instead, SR-004 should change", [core.index()["SR-004"]])
    assert time.monotonic() - started < 1.2  # 300 ms hook timeout, no retry
    assert caught.value.judge == "JEV" and "timeout" in caught.value.cause
    with pytest.raises(JudgmentUnavailable):  # the rest of the process raises the same error
        backend.intent_change("instead, SR-004 should change", [core.index()["SR-004"]])
    assert len(state.requests) <= 2


def test_missing_key_raises_an_error_naming_jev_and_the_variable(jev_repo,
                                                                 monkeypatch) -> None:
    """SR-021 EX-1, SR-039 EX-1."""
    repo, state = jev_repo
    monkeypatch.delenv("TYPESAFE_API_KEY")
    with pytest.raises(JudgmentUnavailable) as caught:
        get_backend(open_core(repo), hook=True)
    assert caught.value.judge == "JEV" and "TYPESAFE_API_KEY" in caught.value.cause
    assert state.requests == []


def test_key_from_user_store(jev_repo, monkeypatch, tmp_path: Path) -> None:
    repo, _ = jev_repo
    monkeypatch.delenv("TYPESAFE_API_KEY")
    store = tmp_path / "home" / "jev"
    store.parent.mkdir(parents=True)
    store.write_text(KEY + "\n", encoding="utf-8")
    assert jev_mod.resolve_key(repo) == KEY
    assert jev_mod.key_source(repo) == "user-store"
    assert get_backend(open_core(repo), hook=True).name == "jev"


def test_key_never_read_from_repository(jev_repo, monkeypatch) -> None:
    repo, _ = jev_repo
    monkeypatch.delenv("TYPESAFE_API_KEY")
    inside = repo / ".config" / "plumb" / "jev"
    inside.parent.mkdir(parents=True)
    inside.write_text(KEY, encoding="utf-8")
    (repo / ".plumb" / "jev").write_text(KEY, encoding="utf-8")
    monkeypatch.setattr(jev_mod, "user_store_path", lambda: inside)
    assert jev_mod.resolve_key(repo) is None
    with pytest.raises(JudgmentUnavailable):
        get_backend(open_core(repo), hook=True)


def test_state_excludes_secret_paths_and_truncates(repo: Path) -> None:
    (repo / "a.py").write_text("print('a')\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    (repo / "keys").mkdir()
    (repo / "keys" / "server.pem").write_text("-----BEGIN-----\n", encoding="utf-8")
    (repo / "untracked.py").write_text("x\n", encoding="utf-8")
    tracked = {"a.py", ".env", "keys/server.pem"}
    state = assemble_state(repo, ["a.py", ".env", "keys/server.pem", "untracked.py",
                                  "../outside.py"], tracked=tracked,
                           env={"SECRET": "print('a')"})
    assert state.included == ("a.py",)
    assert state.excluded == {".env": "secret-path", "keys/server.pem": "secret-path",
                              "untracked.py": "untracked", "../outside.py": "outside-project"}
    assert "[redacted-env]" in state.text and state.redactions == 1
    assert is_secret_path("config/secrets/x.yaml") and not is_secret_path("src/plumb/a.py")
    from plumb.judgment.state import ContextLimits

    (repo / "big.py").write_text("x = 1\n" * 1000, encoding="utf-8")
    small = assemble_state(repo, ["big.py"], tracked={"big.py"},
                           limits=ContextLimits(100, 50), env={})
    again = assemble_state(repo, ["big.py"], tracked={"big.py"},
                           limits=ContextLimits(100, 50), env={})
    assert small.truncation.truncated and small.text == again.text
    assert len(small.text) == 50 * small.truncation.chars_per_token


def test_judgment_event_logged_with_fingerprint(jev_repo) -> None:
    repo, _ = jev_repo
    core = open_core(repo)
    backend = get_backend(core, hook=True)
    [j] = backend.intent_change("instead, SR-004 should change", [core.index()["SR-004"]])
    events = [e for e in open_core(repo).log_read("events") if e.kind == "judgment"]
    assert len(events) == 1
    payload = events[0].payload
    assert payload["subject"] == "SR-004"
    assert payload["action"] == "intent-change"
    assert payload["backend"] == "jev:jev-1.13.0"
    assert payload["fingerprint"] == j.fingerprint and j.fingerprint.startswith("sha256:")
    assert payload["verdict"] == "change" and payload["tier"] == "accept"


def test_drift_triage_through_jev(jev_repo) -> None:
    repo, state = jev_repo
    state.noul = 0.1
    link = Link(source="SR-004", index=0, kind="implemented_by", target=Target(path="src/mod.py"),
                pin=Pin("sha256:a", "sha256:b"))
    states = [LinkState(link=link, state="stale", moved="target")]
    backend = get_backend(open_core(repo), hook=False)
    [j] = backend.drift_triage(states, {"SR-004#0": ("a = 1\n", "a = 1  # c\n")})
    assert j.verdict == "cosmetic" and j.tier == "accept"


# -- sp2 7.2 and 11.2: the protocol additions over the stub; the credential's NAME (SR-039)


@pytest.mark.sr("SR-243")
def test_entailment_through_jev_carries_probability_and_label(jev_repo) -> None:
    repo, state = jev_repo
    core = open_core(repo)
    backend = get_backend(core, hook=False)
    j = backend.entailment("add multiply next to add", "multiply returns the product",
                           subject="INT-017", claim_kind="intent-readback")
    assert (j.action, j.verdict) == ("faithfulness", "entailed")
    assert j.probability == pytest.approx(0.95)
    assert j.confidence_label == "high"
    assert backend.version == "jev-1.13.0"
    [request] = state.requests
    assert "add multiply next to add" in request["body"]["state"]
    state.noul = 0.2
    j = backend.entailment("a", "b", subject="INT-017", claim_kind="intent-readback")
    assert j.verdict == "not-entailed" and j.probability == pytest.approx(0.8)
    events = [e for e in core.log_read("events", ["judgment"])]
    assert events and events[-1].payload["model_version"] == "jev-1.13.0"
    c = backend.contradiction("make add subtract", core.index()["SR-004"])
    assert c.action == "contradiction" and c.verdict == "contradicts"
    k = backend.choose("Which owns it?", ["SR-004"], subject="src/mod.py")
    assert k.verdict == "SR-004"
    a = backend.ask("Does it serve SR-004?", "diff", subject="SR-004", action="ownership")
    assert a.verdict == "no"


@pytest.mark.sr("SR-243")
def test_credential_read_from_the_named_variable(jev_repo, monkeypatch) -> None:
    repo, state = jev_repo
    monkeypatch.delenv("TYPESAFE_API_KEY")
    monkeypatch.setenv("MY_JEV_KEY", KEY)
    config = (repo / ".plumb" / "config.yaml").read_text(encoding="utf-8")
    (repo / ".plumb" / "config.yaml").write_text(
        config.replace("jev: {", "jev: {credential_env: MY_JEV_KEY, "), encoding="utf-8")
    backend = get_backend(open_core(repo), hook=True)
    assert backend.name == "jev"
    monkeypatch.delenv("MY_JEV_KEY")
    with pytest.raises(JudgmentUnavailable) as caught:
        get_backend(open_core(repo), hook=True)
    assert "MY_JEV_KEY" in str(caught.value)


@pytest.mark.sr("SR-243")
def test_the_new_methods_raise_when_jev_times_out(jev_repo) -> None:
    repo, state = jev_repo
    state.delay = 1.5
    core = open_core(repo)
    backend = get_backend(core, hook=True)
    with pytest.raises(JudgmentUnavailable) as caught:
        backend.entailment("add multiply", "add multiply", subject="INT-017",
                           claim_kind="intent-readback")
    assert caught.value.judge == "JEV"
    for call in (lambda: backend.contradiction("x", core.index()["SR-004"]),
                 lambda: backend.choose("Which?", ["SR-004"], subject="p"),
                 lambda: backend.ask("Q?", "c", subject="SR-004", action="ownership")):
        with pytest.raises(JudgmentUnavailable):
            call()


# -- OpenRouter: a provider preset, a configurable path, one version normalizer, the
#    credential read from a user-level env file (SR-039)

OR_KEY = "sk-or-test-key-0123456789abcdef"


def _or_config(repo: Path, url: str, extra: str = "") -> None:
    (repo / ".plumb" / "config.yaml").write_text(
        "judgment:\n  backend: jev\n  hook_timeout_ms: 2000\n"
        f"  jev: {{provider: openrouter, base_url: '{url}'{extra}}}\n", encoding="utf-8")


def _repo_bytes(repo: Path) -> bytes:
    return b"".join(p.read_bytes() for p in repo.rglob("*")
                    if p.is_file() and ".git" not in p.parts)


@pytest.mark.sr("SR-243")
def test_provider_preset_defaults_and_explicit_values_win() -> None:
    from plumb.config import config_from_mapping

    default = config_from_mapping({}).judgment.jev
    assert (default["provider"], default["base_url"], default["path"]) == (
        "typesafe", "https://api.typesafe.ai", "/v1/systemone")
    jev = config_from_mapping({"judgment": {"jev": {"provider": "openrouter"}}}).judgment.jev
    assert jev["base_url"] == "https://openrouter.ai"
    assert jev["path"] == "/api/alpha/decisions"
    assert jev["model"] == "typesafe/jev-1.13"
    assert jev["validated_against"] == "typesafe/jev-1.13"
    assert jev["credential_env"] == "OPENROUTER_API_KEY"
    assert jev["thresholds"] == {"accept": 0.9, "escalate_llm": 0.5}
    jev = config_from_mapping({"judgment": {"jev": {
        "provider": "openrouter", "model": "~typesafe/jev-latest", "credential_env": "MY_OR",
        "path": "/api/beta/decisions"}}}).judgment.jev
    assert (jev["model"], jev["credential_env"], jev["path"]) == (
        "~typesafe/jev-latest", "MY_OR", "/api/beta/decisions")
    assert jev["base_url"] == "https://openrouter.ai"


@pytest.mark.sr("SR-243")
def test_openrouter_request_path_model_and_dated_version(repo: Path, stub, monkeypatch) -> None:
    state, url = stub
    state.model = "typesafe/jev-1.13-20260917"
    state.usage = {"input_tokens": 63, "output_tokens": 1, "cost": 2.1e-05}
    _or_config(repo, url)
    monkeypatch.setenv("OPENROUTER_API_KEY", OR_KEY)
    core = open_core(repo)
    backend = get_backend(core, hook=False)
    assert backend.name == "jev"
    j = backend.entailment("ok", "ok", subject="probe", claim_kind="probe")
    [request] = state.requests
    assert request["path"] == "/api/alpha/decisions"
    headers = {k.lower(): v for k, v in request["headers"].items()}
    assert headers["authorization"] == f"Bearer {OR_KEY}"
    assert request["body"]["model"] == "typesafe/jev-1.13"
    assert j.tier == "accept"  # the dated snapshot is the validated version: no drift
    [event] = list(open_core(repo).log_read("events", ["judgment"]))
    assert event.payload["version_drift"] is False
    assert event.payload["model_version"] == "typesafe/jev-1.13-20260917"
    state.model = "typesafe/jev-1.14-20261001"
    j = get_backend(open_core(repo), hook=False).entailment("ok", "ok", subject="probe",
                                                             claim_kind="probe")
    assert j.tier == "escalate-llm"
    events = list(open_core(repo).log_read("events", ["judgment"]))
    assert events[-1].payload["version_drift"] is True
    assert OR_KEY.encode() not in _repo_bytes(repo)


@pytest.mark.sr("SR-243")
def test_explicit_path_and_float_usage(repo: Path, stub) -> None:
    state, url = stub
    state.usage = {"input_tokens": 63, "output_tokens": 1, "cost": 2.1e-05}
    client = jev_mod.JevClient(base_url=url + "/", path="/custom/decide", key=KEY, timeout_s=5)
    record = client.judge(JudgmentRequest(state="s", questions=(
        ("n", JudgmentQuestion.noul("i", "t", "f")),)))
    assert state.requests[0]["path"] == "/custom/decide"
    assert record.outcome == "ok"
    assert record.usage == {"input_tokens": 63, "output_tokens": 1, "cost": 2.1e-05}
    assert isinstance(record.usage["input_tokens"], int)


def _user_files(tmp_path: Path, monkeypatch, env_file: Path,
                name: str = "OPENROUTER_API_KEY") -> Path:
    home = tmp_path / "userhome"
    home.mkdir(exist_ok=True)
    config = home / "jev.json"
    config.write_text(json.dumps({"credential_env": name, "env_file": str(env_file)}),
                      encoding="utf-8")
    monkeypatch.setattr(jev_mod, "user_config_path", lambda: config)
    monkeypatch.setattr(jev_mod, "user_store_path", lambda: home / "jev")
    return home


ENV_FILE = f"""# local secrets
OTHER=1
export TYPESAFE_API_KEY='{KEY}'
OPENROUTER_API_KEY="{OR_KEY}"  # the gateway
EMPTY=
"""


@pytest.mark.sr("SR-243")
def test_key_from_the_user_env_file(repo: Path, tmp_path: Path, monkeypatch) -> None:
    outside = tmp_path / "elsewhere" / ".env"
    outside.parent.mkdir()
    outside.write_text(ENV_FILE, encoding="utf-8")
    home = _user_files(tmp_path, monkeypatch, outside)
    assert jev_mod.resolve_key(repo, env={}, name="OPENROUTER_API_KEY") == OR_KEY
    assert jev_mod.key_source(repo, env={}, name="OPENROUTER_API_KEY") == "env-file"
    assert jev_mod.resolve_key(repo, env={}, name="TYPESAFE_API_KEY") == KEY
    # the process environment wins over the file
    env = {"OPENROUTER_API_KEY": "sk-or-from-env-123456"}
    assert jev_mod.resolve_key(repo, env=env, name="OPENROUTER_API_KEY") == env[
        "OPENROUTER_API_KEY"]
    assert jev_mod.key_source(repo, env=env, name="OPENROUTER_API_KEY") == "env"
    # a name the file lacks falls back to the legacy raw-key store
    assert jev_mod.resolve_key(repo, env={}, name="MISSING_KEY") is None
    (home / "jev").write_text("legacy-raw-key-0123456789\n", encoding="utf-8")
    assert jev_mod.resolve_key(repo, env={}, name="MISSING_KEY") == "legacy-raw-key-0123456789"
    assert jev_mod.key_source(repo, env={}, name="MISSING_KEY") == "user-store"
    assert jev_mod.key_source(repo, env={}, name="EMPTY") == "user-store"


@pytest.mark.sr("SR-243")
def test_env_file_inside_the_repository_is_refused(repo: Path, tmp_path: Path,
                                                    monkeypatch) -> None:
    inside = repo / ".env"
    inside.write_text(ENV_FILE, encoding="utf-8")
    _user_files(tmp_path, monkeypatch, inside)
    assert jev_mod.resolve_key(repo, env={}, name="OPENROUTER_API_KEY") is None
    assert jev_mod.key_source(repo, env={}, name="OPENROUTER_API_KEY") is None
    _user_files(tmp_path, monkeypatch, Path("secrets.env"))  # relative: refused
    assert jev_mod.resolve_key(repo, env={}, name="OPENROUTER_API_KEY") is None


@pytest.mark.sr("SR-243")
def test_backend_through_the_env_file_never_writes_the_key(repo: Path, stub, tmp_path: Path,
                                                           monkeypatch) -> None:
    state, url = stub
    outside = tmp_path / "elsewhere" / ".env"
    outside.parent.mkdir()
    outside.write_text(ENV_FILE, encoding="utf-8")
    _user_files(tmp_path, monkeypatch, outside)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _or_config(repo, url)
    backend = get_backend(open_core(repo), hook=False)
    assert backend.name == "jev"
    backend.entailment("add multiply", "add multiply", subject="INT-001",
                       claim_kind="intent-readback")
    headers = {k.lower(): v for k, v in state.requests[0]["headers"].items()}
    assert headers["authorization"] == f"Bearer {OR_KEY}"
    assert OR_KEY not in json.dumps(state.requests[0]["body"])
    assert OR_KEY.encode() not in _repo_bytes(repo)
    assert not any(OR_KEY in n for n in backend.notices)


def _live_provider(repo: Path) -> str | None:
    """The provider whose credential resolves (environment, env file or user store), in plumb's order."""
    for provider, name in (("openrouter", "OPENROUTER_API_KEY"),
                           ("typesafe", "TYPESAFE_API_KEY")):
        source = jev_mod.key_source(repo, name=name)
        if source in ("env", "env-file", "user-store") or (source and provider == "typesafe"):
            return provider
    return None


@pytest.mark.jev_live
@pytest.mark.sr("SR-243")
def test_live_entailment(repo: Path, capsys) -> None:
    """One tiny synthetic request (no repository content) through whichever credential
    resolves, the env file included; skipped when none does."""
    from plumb.judgment.tiers import normalize_version, same_version

    provider = _live_provider(repo)
    if provider is None:
        pytest.skip("jev_live: no JEV credential resolves (OPENROUTER_API_KEY, "
                    "TYPESAFE_API_KEY, ~/.config/plumb/jev.json)")
    (repo / ".plumb" / "config.yaml").write_text(
        f"judgment:\n  backend: jev\n  jev: {{provider: {provider}}}\n", encoding="utf-8")
    backend = get_backend(open_core(repo), hook=False)
    assert backend.name == "jev"
    request = JudgmentRequest(state="Owner: add a multiply function next to add.", questions=(
        ("entailment", JudgmentQuestion.noul(
            "Does the claim 'a multiply function is added next to add' follow from the "
            "owner's words?", "it follows", "it does not follow")),), model=backend.model)
    started = time.monotonic()
    record = backend.client.judge(request)
    latency_ms = (time.monotonic() - started) * 1000
    assert record.outcome == "ok", backend.client.last_error
    assert normalize_version(record.resolved_version)
    with capsys.disabled():
        print(f"\njev_live: provider {provider}, resolved {record.resolved_version} "
              f"(normalized {normalize_version(record.resolved_version)}; drift "
              f"{not same_version(record.resolved_version, backend.validated_against)}), "
              f"latency {latency_ms:.0f} ms, usage {record.usage}, "
              f"answer {record.answers['entailment'].value}")
