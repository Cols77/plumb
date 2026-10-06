"""The import plan: what an import would do to the target, record by record (next-plan 9.4).

``plan_import`` reads the source (``pi_factory.read_source``), resolves every link against
the target, and gives each source record one action:

- ``create``: the target has no record with that ID;
- ``update``: the target holds the record from an earlier import of the same source
  (``source.repo: pi-agent-factory``, or the sub-project 1 ``imported_from``) and its fields,
  body or imported links differ; the plan names each changed field and link;
- ``unchanged``: same content and same imported links (pins are not compared);
- ``skip``: the ID belongs to a record of another origin (a ``collision`` finding) or
  appears twice in the source.

A requirement whose upstream consent pins its current bytes gets a planned ``by: import``
approval (``consent.py``), unless one was already written for that content (even if the
owner revoked it since: a re-import never resurrects a revoked approval); applying writes it
only after the owner confirms it in their own terminal (``apply._owner_withholds``). Planning writes
nothing; ``apply.py`` applies a plan.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.contracts import KIND_DIR, Record, Target
from plumb.importer.consent import Consent, matching, read_consents
from plumb.importer.pi_factory import (
    KINDS,
    REPO,
    ImportRefused,
    LinkSpec,
    Planned,
    Report,
    read_head,
    read_source,
)

# the link kinds an import owns, per record kind; other links (derives_from, ...) are kept
IMPORT_KINDS: Mapping[str, frozenset[str]] = {
    "requirement": frozenset({"implemented_by", "verified_by", "upstream", "relates_to"}),
    "feature": frozenset(),
    "nc": frozenset({"corrects"}),
}
LinkKey = tuple[str, Target, str | None]


@dataclass(frozen=True)
class FieldChange:
    field: str
    old: Any
    new: Any


@dataclass
class RecordPlan:
    action: str                       # create | update | unchanged | skip
    kind: str
    record_id: str
    source_path: str
    fields: dict[str, Any]
    body: str
    path: str = ""                    # target-relative record file
    planned_hash: str = ""
    links: list[LinkKey] = field(default_factory=list)
    changes: list[FieldChange] = field(default_factory=list)
    links_added: list[LinkKey] = field(default_factory=list)
    links_removed: list[LinkKey] = field(default_factory=list)
    reason: str = ""
    approval: Consent | None = None


@dataclass
class ImportPlan:
    source: str
    head: str | None
    wanted: tuple[str, ...]
    records: list[RecordPlan]
    findings: list[dict[str, str]]
    claims: Any = None                # claims.ClaimsPlan when CLAIMS is imported

    def by_action(self, action: str) -> list[RecordPlan]:
        return [r for r in self.records if r.action == action]

    def approvals(self) -> list[RecordPlan]:
        return [r for r in self.records if r.approval is not None and r.action != "skip"]

    def actions(self) -> dict[str, int]:
        return {a: len(self.by_action(a)) for a in ("create", "update", "unchanged", "skip")}

    def lines(self) -> list[str]:
        """The plan as a diff: one block per created, updated or skipped record."""
        out: list[str] = []
        for item in self.records:
            if item.action == "create":
                names = ", ".join(k for k in item.fields if k != "title")
                out.append(f"create {item.record_id} {item.source_path}: {names}; "
                           f"{len(item.links)} link(s)")
            elif item.action == "update":
                out.append(f"update {item.record_id} {item.source_path}")
                for change in item.changes:
                    out.append(f"  ~ {change.field}: {_excerpt(change.old, change.new)}")
                out.extend(f"  + link {describe(key)}" for key in item.links_added)
                out.extend(f"  - link {describe(key)}" for key in item.links_removed)
            elif item.action == "skip":
                out.append(f"skip {item.record_id} {item.source_path}: {item.reason}")
        if self.claims is not None:
            out.extend(self.claims.lines())
        for item in self.approvals():
            assert item.approval is not None
            out.append(f"approve {item.record_id} by import: upstream consent "
                       f"{item.approval.path} pins its current content")
        counts = self.actions()
        out.append(f"plan: {counts['create']} create, {counts['update']} update, "
                   f"{counts['unchanged']} unchanged, {counts['skip']} skip, "
                   f"{len(self.approvals())} by: import approval(s)")
        return out

    def report(self, *, dry_run: bool, applied: Mapping[str, Any] | None,
               with_diff: bool = True) -> dict[str, Any]:
        from plumb.normalize import canonical_json, sha256_bytes

        findings = list(self.findings) + list((applied or {}).get("findings") or [])
        finding_counts: dict[str, int] = {}
        for finding in findings:
            finding_counts[finding["kind"]] = finding_counts.get(finding["kind"], 0) + 1
        kept = [r for r in self.records if r.action != "skip"]
        counts = {KINDS[k]: sum(1 for r in kept if r.kind == KINDS[k])
                  for k in ("SR", "FEAT", "NC") if k in self.wanted}
        changed = [r.record_id for r in self.records if r.action in ("create", "update")]
        out: dict[str, Any] = {
            "source": self.source, "head": self.head, "dry_run": dry_run, "counts": counts,
            "actions": self.actions(), "imported": changed, "diff_records": changed,
            "approved": [r.record_id for r in self.approvals()],
            "findings": findings, "finding_counts": dict(sorted(finding_counts.items())),
            "findings_digest": sha256_bytes(canonical_json(findings)),
        }
        if with_diff:
            out["diff"] = self.lines()
        if applied is not None:
            out["event"] = applied.get("event")
            out["approved"] = list(applied.get("approved") or [])
        return out


def describe(key: LinkKey) -> str:
    from plumb.hashing import symbol_qualname

    kind, target, example = key
    if target.path and target.symbol and not target.test:
        end = f"{target.path}::{symbol_qualname(target.symbol)}"
    else:
        end = target.record or target.test or target.path or "?"
    return f"{kind} {end}" + (f" ({example})" if example else "")


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _excerpt(old: Any, new: Any, width: int = 60) -> str:
    """Both values around their first difference, so a long statement shows its change."""
    a, b = _text(old), _text(new)
    if old is None:
        return f"(none) -> {b[:width * 2]}" + ("..." if len(b) > width * 2 else "")
    if new is None:
        return f"{a[:width * 2]}" + ("..." if len(a) > width * 2 else "") + " -> (none)"
    start = 0
    while start < min(len(a), len(b)) and a[start] == b[start]:
        start += 1
    lo = max(0, start - width // 2)

    def cut(s: str) -> str:
        piece = s[lo:lo + width + width // 2]
        return ("..." if lo else "") + piece + ("..." if lo + len(piece) < len(s) else "")

    return f"{cut(a)!r} -> {cut(b)!r}"


def same_origin(record: Record) -> bool:
    """True when ``record`` came from an earlier pi-agent-factory import."""
    source = record.fields.get("source")
    if isinstance(source, Mapping) and source.get("repo") == REPO:
        return True
    return str(record.fields.get("imported_from") or "").startswith(f"{REPO}:")


def refuse_plumb_itself(root: Path) -> None:
    """pi-agent-factory's register is never imported into plumb's own repository: both
    number their requirements from SR-001 (fork plan 2)."""
    import tomllib

    try:
        data = tomllib.loads((Path(root) / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    project = data.get("project")
    if isinstance(project, Mapping) and project.get("name") == "plumb":
        raise ImportRefused(f"{root} is plumb's own repository; pi-agent-factory's register "
                            "is never imported into it (fork plan 2: the SR IDs collide). "
                            "Import into a scratch copy or into pi-agent-factory itself.")


def _resolve(core: Any, spec: LinkSpec, record_id: str, known: set[str],
             report: Report) -> Target | None:
    """The end to link in the target, a narrower fallback, or None (with a finding)."""
    from plumb.hashing import hash_path

    target = spec.target
    if target.record is not None:
        if target.record in known:
            return target
        report.add("missing-end", record_id,
                   f"{spec.kind} {target.record} does not exist here; link not added")
        return None
    if core.hash_target(target) is not None:
        return target
    if spec.spec_id is not None:
        report.add("relation-skipped", record_id,
                   f"relates_to spec:{spec.spec_id}: its document {target.path} does not "
                   "exist here")
        return None
    file = target.path or (target.test or "").split("::", 1)[0]
    if (target.symbol or target.test) and hash_path(core.root, file) is not None:
        name = target.symbol or target.test
        report.add("symbol-narrowed", record_id,
                   f"{spec.kind} {name}: not defined in {file}; linked as the whole file")
        return Target(path=file)
    report.add("missing-end", record_id,
               f"{spec.kind} {describe((spec.kind, target, None)).split(' ', 1)[1]} does not "
               "exist here; link not added")
    return None


def _changes(existing: Record, fields: Mapping[str, Any], body: str) -> list[FieldChange]:
    from plumb.normalize import normalize_text

    old: dict[str, Any] = {"title": existing.title, **existing.fields}
    old.pop("links", None)
    out = [FieldChange(key, old.get(key), fields.get(key))
           for key in sorted(set(old) | set(fields)) if old.get(key) != fields.get(key)]
    if normalize_text(existing.body) != normalize_text(body):
        out.append(FieldChange("body", existing.body.strip(), body.strip()))
    return out


def _approved_before(core: Any) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """``(records with a by: import approval ever written at a hash, records whose standing
    approvals include a hash)``, as ``(id, hash)`` pairs."""
    from plumb.confirm import checked_entries, remaining_approvals

    ever: set[tuple[str, str]] = set()
    for entry, problem in checked_entries(core.events(), core.config.approve.affirmations):
        if problem is None and entry.kind == "approval" \
                and entry.payload.get("by") == "import":
            for item in entry.payload.get("records") or []:
                if isinstance(item, Mapping):
                    ever.add((str(item.get("id")), str(item.get("hash"))))
    standing = {(rid, h) for rid, approvals in
                remaining_approvals(core.events(), core.config.approve.affirmations).items()
                for h, _ in approvals}
    return ever, standing


def plan_import(core: Any, source: Path, *, only: Iterable[str] | None = None) -> ImportPlan:
    """What importing ``source`` into ``core``'s repository would do. Writes nothing."""
    from plumb.links import kind_allowed, target_category
    from plumb.model import record_hash
    from plumb.store import ordered_frontmatter

    source = Path(source)
    if not source.is_dir():
        raise FileNotFoundError(f"{source} is not a directory")
    refuse_plumb_itself(core.root)
    every = set(KINDS) | {"CLAIMS"}
    wanted = {k.strip().upper() for k in (only or every)} & every
    report = Report()
    planned, features = read_source(source, wanted, report)
    consents = read_consents(source, report) if "SR" in wanted else {}

    index = core.index()
    batch: list[Planned] = []
    plans: list[RecordPlan] = []
    seen: set[str] = set()
    skipped: set[str] = set()
    for item in planned:
        existing = index.get(item.record_id)
        reason = ""
        if existing is not None and not same_origin(existing):
            reason = "a record of another origin already has this ID"
            report.add("collision", item.record_id,
                       f"{item.record_id} already exists here; {item.source_path} skipped")
        elif item.record_id in seen:
            reason = "duplicate ID in the source"
            report.add("collision", item.record_id,
                       f"duplicate id in the source ({item.source_path}); skipped")
        if reason:
            skipped.add(item.record_id)
            plans.append(RecordPlan("skip", item.kind, item.record_id, item.source_path,
                                    item.fields, item.body, reason=reason))
            continue
        seen.add(item.record_id)
        batch.append(item)
    skipped -= seen

    known = (set(index) - skipped) | {p.record_id for p in batch}
    present_features = {i for i in known if i.startswith("FEAT-")}
    membership: dict[str, str] = {}
    for feature in features:
        if feature.record_id in present_features and feature.record_id not in skipped:
            for sr in feature.fields["requirements"]:
                membership.setdefault(sr, feature.record_id)

    ever, standing = _approved_before(core)
    for item in batch:
        fields = dict(item.fields)
        if item.kind == "requirement" and item.record_id in membership:
            fields = {"feature": membership[item.record_id], **fields}
        planned_hash = record_hash(ordered_frontmatter(item.kind, item.record_id, fields),
                                   item.body)
        links: list[LinkKey] = []
        for spec in item.links:
            target = _resolve(core, spec, item.record_id, known, report)
            if target is not None and not kind_allowed(spec.kind, item.kind,
                                                       target_category(target) or ""):
                report.add("link-skipped", item.record_id, f"{describe((spec.kind, target, None))}"
                           f": {spec.kind} is not allowed from {item.kind} to that end")
                target = None
            key = (spec.kind, target, spec.example) if target is not None else None
            if key is not None and key not in links:
                links.append(key)  # type: ignore[arg-type]
        existing = index.get(item.record_id)
        plan = RecordPlan("create", item.kind, item.record_id, item.source_path, fields,
                          item.body, planned_hash=planned_hash, links=links)
        if existing is None:
            plan.path = (Path(".plumb") / KIND_DIR[item.kind] / f"{item.record_id}.md"
                         ).as_posix()
        else:
            plan.path = existing.path
            owned = IMPORT_KINDS[item.kind]
            current = [(lk.kind, lk.target, lk.example) for lk in existing.links
                       if lk.kind in owned]
            if planned_hash == existing.hash and current == links:
                plan.action = "unchanged"
            else:
                plan.action = "update"
                plan.changes = _changes(existing, fields, item.body)
                plan.links_added = [k for k in links if k not in current]
                plan.links_removed = [k for k in current if k not in links]
        if item.kind == "requirement" and item.record_id in consents:
            consent = matching(consents[item.record_id], item.raw)
            if consent is None:
                report.add("consent-stale", item.record_id,
                           f"{len(consents[item.record_id])} upstream consent record(s) pin "
                           "other content than the current source file; stays proposed")
            elif (item.record_id, planned_hash) not in ever | standing:
                plan.approval = consent
        plans.append(plan)
    plans.sort(key=lambda p: (list(KINDS.values()).index(p.kind), p.record_id))
    claims = None
    if "CLAIMS" in wanted:
        from plumb.importer.claims import plan_claims

        claims = plan_claims(core, source, report)
    return ImportPlan(source=str(source), head=read_head(source),
                      wanted=tuple(k for k in KINDS if k in wanted), records=plans,
                      findings=report.findings, claims=claims)
