"""pi-agent-factory's claims policy and ingest checkpoint (concept 10, next-plan 9.1 IS1).

- ``.factory/trace-claims.yaml`` becomes ``.plumb/claims.yaml``: its ``exempt`` globs join
  the target's, ``require_trailer`` becomes true, ``epoch`` is kept, and each NC-backed
  baseline pair ``{sr, path, nc}`` becomes plumb's ``{commit, path, nc}`` for every ingested
  commit that claimed that SR and changed that path (a pair no ingested commit explains is a
  ``baseline-unmapped`` finding, never invented);
- the ``commits[]`` of ``evidence/runs/ingest-*.json`` become one ``claims-ingest`` event
  (the checkpoint: the latest ``result_commit`` and every ingested commit's SR IDs and paths),
  appended only when it differs from the last one.

Read-only on the source; idempotent on the target (an unchanged policy is not rewritten).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.importer.pi_factory import Report, read_bytes


@dataclass
class ClaimsPlan:
    action: str = "unchanged"             # create | update | unchanged
    text: str = ""                        # the new .plumb/claims.yaml
    added_exempt: list[str] = field(default_factory=list)
    added_baseline: int = 0
    ingest: dict[str, Any] | None = None  # the claims-ingest payload, when new

    def lines(self) -> list[str]:
        out: list[str] = []
        if self.action != "unchanged":
            out.append(f"{self.action} .plumb/claims.yaml: +{len(self.added_exempt)} exempt "
                       f"glob(s) {', '.join(self.added_exempt) or '-'}; "
                       f"+{self.added_baseline} baseline entr(y/ies)")
        if self.ingest is not None:
            out.append(f"claims-ingest: {len(self.ingest['commits'])} ingested commit(s), "
                       f"checkpoint {str(self.ingest['checkpoint'])[:12]}")
        return out


def _ingest(source: Path, report: Report) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    """Every ingested commit (first seen wins), the latest checkpoint, the files read."""
    commits: dict[str, dict[str, Any]] = {}
    checkpoint: str | None = None
    names: list[str] = []
    directory = source / "evidence" / "runs"
    for path in sorted(directory.glob("ingest-*.json")) if directory.is_dir() else []:
        try:
            data = json.loads(read_bytes(path).decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            report.add("malformed", path.name, "ingest checkpoint unreadable; skipped")
            continue
        if not isinstance(data, Mapping):
            continue
        names.append(path.name)
        if isinstance(data.get("result_commit"), str) and data.get("outcome") == "completed":
            checkpoint = data["result_commit"]
        for item in data.get("commits") or []:
            if not isinstance(item, Mapping) or not isinstance(item.get("sha"), str):
                continue
            commits.setdefault(item["sha"], {
                "sha": item["sha"],
                "sr_ids": sorted({str(s) for s in item.get("sr_ids") or []}),
                "paths": sorted({str(p) for p in item.get("changed_files") or []})})
    return sorted(commits.values(), key=lambda c: c["sha"]), checkpoint, names


def plan_claims(core: Any, source: Path, report: Report) -> ClaimsPlan | None:
    """What importing the claims policy and checkpoint would change, or None (no policy and
    no checkpoint in the source)."""
    import yaml

    from plumb.claims import DEFAULT_EXEMPT

    commits, checkpoint, names = _ingest(source, report)
    policy_path = source / ".factory" / "trace-claims.yaml"
    upstream: Mapping[str, Any] = {}
    if policy_path.is_file():
        try:
            loaded = yaml.safe_load(read_bytes(policy_path).decode("utf-8")) or {}
            upstream = loaded if isinstance(loaded, Mapping) else {}
        except (yaml.YAMLError, UnicodeDecodeError):
            report.add("malformed", ".factory/trace-claims.yaml", "unreadable; skipped")
    if not upstream and not commits:
        return None
    plan = ClaimsPlan()

    target_path = core.root / ".plumb" / "claims.yaml"
    try:
        current_text = target_path.read_text(encoding="utf-8")
        current = yaml.safe_load(current_text) or {}
    except (OSError, yaml.YAMLError):
        current_text, current = "", {}
    current = dict(current) if isinstance(current, Mapping) else {}

    if upstream:
        exempt = [str(g) for g in current.get("exempt") or []]
        for glob in upstream.get("exempt") or []:
            glob = str(glob)
            if glob not in exempt and glob not in DEFAULT_EXEMPT:
                exempt.append(glob)
                plan.added_exempt.append(glob)
        baseline = [dict(b) for b in current.get("baseline") or [] if isinstance(b, Mapping)]
        have = {(str(b.get("commit")), str(b.get("path"))) for b in baseline}
        for pair in upstream.get("baseline") or []:
            if not isinstance(pair, Mapping):
                continue
            sr, path, nc = str(pair.get("sr")), str(pair.get("path")), pair.get("nc")
            shas = [c["sha"] for c in commits if sr in c["sr_ids"] and path in c["paths"]]
            if not shas:
                report.add("baseline-unmapped", sr, f"{path} ({nc}): no ingested commit claims "
                           "this pair; not added to .plumb/claims.yaml")
                continue
            for sha in shas:
                if (sha, path) not in have:
                    have.add((sha, path))
                    baseline.append({"commit": sha, "path": path, "nc": str(nc)})
                    plan.added_baseline += 1
        data = dict(current)
        data["require_trailer"] = True
        data["exempt"] = exempt
        if upstream.get("epoch"):
            data["epoch"] = str(upstream["epoch"])
        data["baseline"] = baseline
        text = ("# SR: trailer policy (plumb trailers check-msg, plumb claims check), merged by "
                "plumb import from\n# pi-agent-factory's .factory/trace-claims.yaml.\n"
                + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))
        if yaml.safe_load(text) != (yaml.safe_load(current_text) if current_text else None):
            plan.action = "update" if current_text else "create"
            plan.text = text

    if commits:
        from plumb.normalize import canonical_json, sha256_bytes

        digest = sha256_bytes(canonical_json({"checkpoint": checkpoint, "commits": commits}))
        last = None
        for entry in core.events():
            if entry.kind == "claims-ingest":
                last = entry.payload.get("digest")
        if last != digest:
            plan.ingest = {"source": "pi-agent-factory", "files": names,
                           "checkpoint": checkpoint, "commits": commits, "digest": digest}
    return plan


def apply_claims(core: Any, plan: ClaimsPlan) -> bool:
    """Write the policy and append the checkpoint; True when anything changed."""
    changed = False
    if plan.action in ("create", "update"):
        path = core.root / ".plumb" / "claims.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plan.text.encode("utf-8"))
        changed = True
    if plan.ingest is not None:
        core.log_append("events", "claims-ingest", plan.ingest)
        changed = True
    return changed
