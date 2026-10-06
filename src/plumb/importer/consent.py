"""pi-agent-factory's per-SR human consent records, read for ``by: import`` (next-plan 9.3).

pi-agent-factory records an owner's consent to one requirement in
``.factory/planning/<run_id>/consent/SR-###.json``: ``decision: approve``, ``reviewer:
human``, the fixed consent phrase, a ``reason``, and ``requirement_sha256``, the SHA-256 of
the SR file's LF form (its CRLF form is accepted too; ``coherence/planning/digest.py``).
Only such a record whose digest identifies the source file's CURRENT bytes lets the importer
write an approval; anything else is ignored and reported, so importing never manufactures a
confirmation the owner did not give (concept 10, R2).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONSENT_PHRASE = "I independently approve this SR for adoption."
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SR_ID = re.compile(r"^SR-[0-9]+$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 1_048_576


@dataclass(frozen=True)
class Consent:
    path: str                   # source-relative POSIX path of the consent file
    run_id: str
    sr_id: str
    requirement_sha256: str     # hex, as pi-agent-factory stored it
    digest: str                 # "sha256:" + hex of the consent file's bytes


def accepted_sha256s(data: bytes) -> frozenset[str]:
    """Every stored digest that identifies ``data``: its LF form and its CRLF form."""
    lf = data.replace(b"\r\n", b"\n")
    return frozenset({hashlib.sha256(lf).hexdigest(),
                      hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest()})


def _problem(data: Any, run_id: str, sr_id: str) -> str | None:
    """Why a consent record is not a human approval of one SR, or None."""
    if not isinstance(data, Mapping):
        return "not a JSON object"
    if data.get("schema") != 1:
        return "schema is not 1"
    if data.get("run_id") != run_id or not RUN_ID.match(run_id):
        return f"run_id {data.get('run_id')!r} does not match its directory {run_id!r}"
    if data.get("sr_id") != sr_id or not SR_ID.match(sr_id):
        return f"sr_id {data.get('sr_id')!r} does not match its file name {sr_id!r}"
    if not isinstance(data.get("requirement_sha256"), str) or \
            not SHA256_HEX.match(data["requirement_sha256"]):
        return "requirement_sha256 is not a SHA-256"
    if data.get("decision") != "approve":
        return f"decision is {data.get('decision')!r}, not approve"
    if data.get("reviewer") != "human":
        return f"reviewer is {data.get('reviewer')!r}, not human"
    if data.get("phrase") != CONSENT_PHRASE:
        return "the consent phrase is not the fixed one"
    if not isinstance(data.get("reason"), str) or not data["reason"].strip():
        return "no reason"
    return None


def read_consents(source: Path, report: Any) -> dict[str, list[Consent]]:
    """Every valid human consent in ``source``, per SR, in path order; each invalid file is
    a ``consent-ignored`` finding."""
    from plumb.importer.pi_factory import read_bytes

    out: dict[str, list[Consent]] = {}
    planning = source / ".factory" / "planning"
    if not planning.is_dir():
        return out
    for path in sorted(planning.glob("*/consent/*.json")):
        rel = path.relative_to(source).as_posix()
        run_id, sr_id = path.parent.parent.name, path.stem
        try:
            raw = read_bytes(path)
            if len(raw) > MAX_BYTES:
                raise ValueError("larger than 1 MiB")
            data = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            report.add("consent-ignored", sr_id, f"{rel}: unreadable ({exc}); ignored")
            continue
        problem = _problem(data, run_id, sr_id)
        if problem is not None:
            report.add("consent-ignored", sr_id, f"{rel}: {problem}; ignored")
            continue
        out.setdefault(sr_id, []).append(Consent(
            path=rel, run_id=run_id, sr_id=sr_id,
            requirement_sha256=str(data["requirement_sha256"]),
            digest="sha256:" + hashlib.sha256(raw).hexdigest()))
    return out


def matching(consents: list[Consent], sr_bytes: bytes) -> Consent | None:
    """The first consent whose digest identifies the SR file's current bytes, or None."""
    accepted = accepted_sha256s(sr_bytes)
    for consent in consents:
        if consent.requirement_sha256 in accepted:
            return consent
    return None
