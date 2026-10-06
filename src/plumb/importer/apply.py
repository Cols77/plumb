"""Applying an import plan in one pass (next-plan 9.4, fork plan K4).

Each created or updated record file is written exactly once, with its links already pinned:
record ends pin the planned hashes of the batch, file, symbol and test-node ends their
current hashes. Unchanged records are not touched, so applying the same source twice changes
no file. An ``import`` event is appended only when something changed; right after it, one
``approval`` entry ``by: import`` covers the requirements whose upstream human consent pins
their current content, written only after the owner confirms them in their own terminal
(``_owner_withholds``; ``recheck.py`` re-checks it). Nothing else is ever confirmed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plumb.contracts import Link, Pin, Target
from plumb.importer.pi_factory import REPO
from plumb.importer.plan import IMPORT_KINDS, ImportPlan, RecordPlan


def _write(core: Any, plan: RecordPlan, links: list[dict[str, Any]]) -> None:
    from plumb.store import dump_frontmatter, ordered_frontmatter

    fields = dict(plan.fields)
    if links:
        fields["links"] = links
    data = ordered_frontmatter(plan.kind, plan.record_id, fields)
    text = "---\n" + dump_frontmatter(data) + "---\n" + plan.body
    path = core.root / plan.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _links(core: Any, plan: RecordPlan, hashes: Mapping[str, str]) -> list[dict[str, Any]]:
    """The record's final links: the plan's imported links, then the existing links the
    import does not own (``derives_from`` and the like), every one re-pinned when its end
    exists."""
    from plumb.model import link_to_dict

    def end_hash(target: Target) -> str | None:
        if target.record is not None:
            return hashes.get(target.record)
        return core.hash_target(target)

    keys: list[tuple[str, Target, str | None, Pin | None]] = [
        (kind, target, example, None) for kind, target, example in plan.links]
    existing = core.index().get(plan.record_id)
    if existing is not None:
        owned = IMPORT_KINDS[plan.kind]
        keys += [(lk.kind, lk.target, lk.example, lk.pin) for lk in existing.links
                 if lk.kind not in owned]
    out: list[dict[str, Any]] = []
    for position, (kind, target, example, old_pin) in enumerate(keys):
        digest = end_hash(target)
        pin = Pin(plan.planned_hash, digest) if digest is not None else old_pin
        out.append(link_to_dict(Link(source=plan.record_id, index=position,
                                     kind=kind, target=target,  # type: ignore[arg-type]
                                     example=example, pin=pin)))
    return out


def _approval_item(core: Any, plan: RecordPlan, head: str | None) -> dict[str, Any] | None:
    from plumb.confirm import verified_end
    from plumb.trace import owning_ends

    record = core.index().get(plan.record_id)
    consent = plan.approval
    if record is None or consent is None or record.hash != plan.planned_hash:
        return None
    item: dict[str, Any] = {"id": record.id, "hash": record.hash}
    ends = owning_ends(record)
    if ends:
        item["ends"] = ends
    verified: dict[str, str] = {}
    for link in record.links:
        end = verified_end(link)
        digest = core.hash_target(link.target) if end else None
        if end and digest:
            verified[end] = digest
    if verified:
        item["verified"] = verified
    source = record.fields.get("source")
    item["upstream"] = {
        "repo": REPO, "repo_head": head, "consent_path": consent.path,
        "consent_digest": consent.digest, "requirement_sha256": consent.requirement_sha256,
        "run_id": consent.run_id,
        "upstream_hash": source.get("upstream_hash") if isinstance(source, Mapping) else None,
    }
    return item


def _owner_withholds(ids: list[str]) -> str | None:
    """None when the owner, in their own terminal, confirms the ``by: import`` approvals of
    ``ids``; otherwise why they are withheld (the records are then imported proposed).

    The guarantee (concept 10, R2): importing never manufactures a confirmation the owner did
    not give. A consent file in the source is only as trustworthy as whoever wrote the source
    tree, so the run's approvals go through ``approvals.require_owner``, the choke point of
    every owner-only write: refused under the agent session marker and outside an
    interactive terminal, written only after the owner's y/N."""
    from plumb.approvals import Declined, Refused, require_owner

    shown = ", ".join(ids[:5]) + (f", +{len(ids) - 5} more" if len(ids) > 5 else "")
    try:
        require_owner("import", f"Confirm {len(ids)} imported requirement(s) whose upstream "
                      f"human consent pins their current content ({shown})?")
    except Refused as exc:
        return (f"{exc} No by: import approval was written; the records stay proposed. "
                "Re-run the import in the owner's terminal to confirm them.")
    except Declined:
        return "the owner declined; no by: import approval, the records stay proposed"
    return None


def apply_plan(core: Any, plan: ImportPlan) -> dict[str, Any]:
    """Write the plan's created and updated records, then its event and approval."""
    index = core.index()
    hashes = {rid: record.hash for rid, record in index.items()}
    changed = [r for r in plan.records if r.action in ("create", "update")]
    for item in plan.records:
        if item.action in ("create", "update", "unchanged"):
            hashes[item.record_id] = item.planned_hash
    for item in changed:
        _write(core, item, _links(core, item, hashes))
    core.store.invalidate()

    findings: list[dict[str, str]] = []
    approvals: list[dict[str, Any]] = []
    for item in plan.approvals():
        approval = _approval_item(core, item, plan.head)
        if approval is None:
            findings.append({"kind": "approval-skipped", "id": item.record_id,
                             "detail": "the written record does not match the planned content"
                                       "; no by: import approval"})
        else:
            approvals.append(approval)
    if approvals:
        withheld = _owner_withholds([a["id"] for a in approvals])
        if withheld is not None:
            findings.append({"kind": "approval-withheld",
                             "id": ", ".join(a["id"] for a in approvals), "detail": withheld})
            approvals = []
    claims_changed = False
    if plan.claims is not None:
        from plumb.importer.claims import apply_claims

        claims_changed = apply_claims(core, plan.claims)
    if not changed and not approvals and not claims_changed:
        return {"event": None, "approved": [], "findings": findings}

    from plumb.normalize import canonical_json, sha256_bytes

    all_findings = list(plan.findings) + findings
    counts = plan.report(dry_run=False, applied=None, with_diff=False)["counts"]
    event = core.log_append("events", "import", {
        "source": plan.source, "head": plan.head, "counts": counts,
        "actions": plan.actions(), "findings": len(all_findings),
        "findings_digest": sha256_bytes(canonical_json(all_findings)),
        "records": [r.record_id for r in changed],
        "created": [r.record_id for r in changed if r.action == "create"],
        "updated": [r.record_id for r in changed if r.action == "update"],
        "claims": None if plan.claims is None else {
            "policy": plan.claims.action, "added_exempt": plan.claims.added_exempt,
            "added_baseline": plan.claims.added_baseline,
            "ingest": None if plan.claims.ingest is None else plan.claims.ingest["digest"]},
        "approved": [{"id": a["id"], "hash": a["hash"]} for a in approvals]})
    approved: list[str] = []
    if approvals:
        from plumb.importer.recheck import event_copy

        upstream =(approvals[0]["upstream"] if len(approvals) == 1 else
                    {"repo": REPO, "repo_head": plan.head,
                     "consent_path": f"{len(approvals)} consent records (see each record)"})
        entry = core.log_append("events", "approval", {
            "records": approvals, "by": "import", "upstream": upstream,
            "import_event": event.digest, "import_entry": event_copy(event),
            "prompt_digest": None, "quote": None,
            "note": "upstream human consent pinning the imported content (next-plan 9.3)"})
        if entry.prev == event.digest:
            approved = [a["id"] for a in approvals]
        else:  # another writer slipped in between: the approval confirms nothing
            findings.append({"kind": "approval-skipped", "id": ", ".join(
                a["id"] for a in approvals), "detail": "another log entry was written between "
                "the import event and its approval; re-run the import"})
    return {"event": event.digest, "approved": approved, "findings": findings}
