"""Advisory fidelity without JEV (spec 8.3, ruling R4).

``build_packet`` gathers what a judge needs to say whether a requirement's code and tests
still fit it: the statement, the examples, each ``implemented_by`` and ``verified_by`` end at
its current content (truncated deterministically) with its hash, and the covering tests'
evidence state. The packet carries no procedure. The host agent judges it and answers with
``plumb judge``, which appends a ``judgment`` event. A judgment is advisory: it never
confirms a record and never freshens evidence; ``drifts`` and ``unsure`` are drift signals,
never questions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import FidelityPacket, LogEntry
from plumb.normalize import canonical_json, normalize_text, sha256_bytes

MAX_END_CHARS = 4000
END_KINDS = ("implemented_by", "verified_by")
VERDICTS = ("fits", "drifts", "unsure")


def _end_content(root: Path, path: str | None) -> tuple[str, bool, bool]:
    """``(content, truncated, missing)`` of a file end, normalized and cut at the cap."""
    from plumb.hashing import clean_rel_path

    rel = clean_rel_path(path or "")
    if rel is None:
        return "", False, True
    try:
        text = (root / rel).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return "", False, True
    text = normalize_text(text)
    if len(text) > MAX_END_CHARS:
        return text[:MAX_END_CHARS], True, False
    return text, False, False


def _requirement(core: Any, sr: str) -> Any:
    record = core.index().get(sr)
    if record is None or record.kind != "requirement":
        raise KeyError(f"{sr} is not a requirement in this repository")
    return record


def end_hashes(core: Any, record: Any) -> dict[str, str | None]:
    return {link.id: core.hash_target(link.target) for link in record.links
            if link.kind in END_KINDS}


def build_packet(core: Any, verify: Any, sr: str) -> FidelityPacket:
    """The fidelity packet of requirement ``sr`` (spec 12.2)."""
    from plumb.hashing import target_path

    record = _requirement(core, sr)
    root = Path(core.root)
    ends: list[dict[str, Any]] = []
    for link in record.links:
        if link.kind not in END_KINDS:
            continue
        path = target_path(link.target)
        content, truncated, missing = _end_content(root, path)
        end: dict[str, Any] = {"link": link.id, "kind": link.kind, "path": path,
                               "hash": core.hash_target(link.target), "content": content,
                               "truncated": truncated}
        if link.target.symbol:
            end["symbol"] = link.target.symbol
        if link.target.test:
            end["test"] = link.target.test
        if link.example:
            end["example"] = link.example
        if missing:
            end["missing"] = True
        ends.append(end)
    evidence: list[dict[str, Any]] = []
    if verify is not None:
        try:
            nodes = sorted({n for ns in verify.tests_for([sr]).values() for n in ns})
            states = verify.evidence(nodes)
            evidence = [{"node_id": n, "state": states[n].state if n in states else "none"}
                        for n in nodes]
        except Exception as exc:  # noqa: BLE001 - a lane failure degrades the packet only
            evidence = [{"node_id": "", "state": "unknown", "error": str(exc)}]
    statement = str(record.fields.get("statement") or "")
    examples = tuple(record.examples)
    fingerprint = sha256_bytes(canonical_json({
        "requirement": sr, "requirement_hash": record.hash, "statement": statement,
        "examples": [[e.id, e.given, e.when, e.then, e.criterion] for e in examples],
        "ends": [[e["link"], e["hash"], e["content"]] for e in ends],
        "evidence": evidence}))
    return FidelityPacket(requirement=sr, requirement_hash=record.hash, statement=statement,
                          examples=examples, ends=tuple(ends), evidence=tuple(evidence),
                          fingerprint=fingerprint)


def judge(core: Any, sr: str, verdict: str, note: str, *, backend: str = "host-agent",
          confidence: float | None = None, tier: str | None = None,
          fingerprint: str | None = None) -> LogEntry:
    """Append a fidelity ``judgment`` event for ``sr`` at its current hashes."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
    record = _requirement(core, sr)
    hashes = end_hashes(core, record)
    if fingerprint is None:
        fingerprint = sha256_bytes(canonical_json([record.hash, sorted(hashes.items())]))
    payload = {"subject": sr, "action": "fidelity", "verdict": verdict,
               "confidence": confidence, "tier": tier or "accept", "backend": backend,
               "fingerprint": fingerprint, "requirement_hash": record.hash,
               "end_hashes": hashes, "note": " ".join(str(note).split())}
    return core.log_append("events", "judgment", payload)


def latest_judgments(core: Any) -> dict[str, Mapping[str, Any]]:
    """The latest fidelity judgment payload per requirement, in log order."""
    events = core.events() if hasattr(core, "events") else core.log_read("events",
                                                                          ["judgment"])
    latest: dict[str, Mapping[str, Any]] = {}
    for entry in events:
        if entry.kind != "judgment":
            continue
        payload = entry.payload
        if payload.get("action") == "fidelity" and isinstance(payload.get("subject"), str):
            latest[payload["subject"]] = payload
    return latest


def fidelity_state(core: Any, record: Any,
                   latest: Mapping[str, Mapping[str, Any]]) -> str | None:
    """``fits``, ``drifts``, ``unsure``, ``unjudged``, or None when there is nothing to judge."""
    hashes = end_hashes(core, record)
    if not hashes:
        return None
    payload = latest.get(record.id)
    if payload is None:
        return "unjudged"
    if (payload.get("requirement_hash") != record.hash
            or dict(payload.get("end_hashes") or {}) != hashes):
        return "unjudged"
    verdict = payload.get("verdict")
    return verdict if verdict in VERDICTS else "unjudged"


def unjudged(core: Any, ids: Iterable[str] | None = None) -> tuple[str, ...]:
    """Requirements whose fidelity is unjudged at current hashes, ``drifts`` or ``unsure``."""
    index = core.index()
    selected = sorted(index) if ids is None else [i for i in ids if i in index]
    latest = latest_judgments(core)
    out: list[str] = []
    for record_id in selected:
        record = index[record_id]
        if record.kind != "requirement":
            continue
        if fidelity_state(core, record, latest) in ("unjudged", "drifts", "unsure"):
            out.append(record_id)
    return tuple(out)
