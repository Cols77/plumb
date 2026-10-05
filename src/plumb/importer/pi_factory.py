"""Minimal, read-only pi-agent-factory importer (spec 8.1, F11).

Reads a pi-agent-factory checkout and writes plumb records into the current repository:

- ``requirements/SR-*.md`` -> requirements (``acceptance`` becomes ``AC-n`` examples;
  ``upstream``, ``relates_to``, ``implemented_by`` and ``verified_by`` become links, pinned
  when their ends exist here, otherwise reported); legacy ``checksum:`` values are verified
  with the extracted ``content_checksum`` and reported;
- ``docs/features/FEAT-*.md`` plus ``bundles/*.json`` -> features whose ``requirements`` are
  the union of both memberships, every difference reported;
- ``docs/nonconformances/NC-*.md`` -> nonconformances, read leniently.

The source is only ever opened for reading and no git command runs in it (``HEAD`` is read
from the ``.git`` files). Every imported record is proposed: the importer never manufactures
a confirmation. An ID already present here is reported and skipped.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.contracts import Target

KINDS = {"SR": "requirement", "FEAT": "feature", "NC": "nc"}
_SR_RE = re.compile(r"^SR-\d{3,}$")
_FEAT_RE = re.compile(r"^FEAT-\d{3,}$")
_NC_FILE_RE = re.compile(r"^(NC-\d{4,})")
_EXAMPLE_RE = re.compile(r"^AC-\d+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")


@dataclass
class Planned:
    """One record the import would write, with the links to add once all exist."""

    kind: str
    record_id: str
    fields: dict[str, Any]
    body: str
    source_path: str
    links: list[tuple[str, Target, str | None]] = field(default_factory=list)


class Report:
    def __init__(self) -> None:
        self.findings: list[dict[str, str]] = []

    def add(self, kind: str, record_id: str, detail: str) -> None:
        self.findings.append({"kind": kind, "id": record_id, "detail": detail})


# --------------------------------------------------------------------------- reading


def _read_text(path: Path) -> str:
    with open(path, "rb") as handle:  # read-only, never anything else
        return handle.read().decode("utf-8", errors="replace")


def _split(text: str) -> tuple[dict[str, Any] | None, str]:
    from plumb.model import RecordError, load_yaml, split_frontmatter

    try:
        yaml_text, body = split_frontmatter(text)
        data = load_yaml(yaml_text)
    except RecordError:
        return None, text
    return (data if isinstance(data, dict) else None), body


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def content_checksum(statement: str, binding: Mapping[str, Any]) -> str:
    """pi-agent-factory's legacy requirement checksum (``register.content_checksum``)."""
    harness = binding.get("harness")
    canonical = "\n".join([
        statement.strip(), str(harness) if harness else "", str(binding["experiment"]),
        str(binding["metric"]), str(binding["assert"]), str(int(binding.get("trials", 1))),
        repr(binding.get("window"))])
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _end_entries(raw: Any) -> list[tuple[str, str | None]]:
    """``[(path, symbol)]`` from ``implemented_by`` or ``verified_by`` entries."""
    out: list[tuple[str, str | None]] = []
    for item in _as_list(raw):
        if isinstance(item, str):
            out.append((item, None))
        elif isinstance(item, Mapping) and item.get("path"):
            symbol = item.get("symbol")
            out.append((str(item["path"]), str(symbol) if symbol else None))
    return out


def _plan_requirement(path: Path, rel: str, report: Report) -> Planned | None:
    meta, body = _split(_read_text(path))
    if meta is None:
        report.add("malformed", path.stem, f"{rel}: no readable frontmatter; skipped")
        return None
    record_id = str(meta.get("id") or "")
    missing = [k for k in ("id", "title", "statement") if not meta.get(k)]
    if missing or not _SR_RE.match(record_id):
        report.add("malformed", record_id or path.stem,
                   f"{rel}: missing {', '.join(missing) or 'a valid SR id'}; skipped")
        return None
    statement = str(meta["statement"])
    fields: dict[str, Any] = {"title": str(meta["title"]), "statement": statement}
    if meta.get("domain"):
        fields["domain"] = str(meta["domain"])
    examples: list[dict[str, str]] = []
    links: list[tuple[str, Target, str | None]] = []
    for item in _as_list(meta.get("acceptance")):
        if not isinstance(item, Mapping):
            continue
        ac_id = str(item.get("id") or "")
        criterion = " ".join(str(item.get("criterion") or "").split())
        if not _EXAMPLE_RE.match(ac_id) or not criterion:
            report.add("malformed", record_id, f"acceptance entry {ac_id!r} skipped")
            continue
        examples.append({"id": ac_id, "criterion": criterion})
        verification = item.get("verification")
        if isinstance(verification, Mapping) and verification.get("kind") == "test_marker":
            ref = str(verification.get("ref") or "").split("::", 1)[0]
            if ref:
                links.append(("verified_by", Target(path=ref), ac_id))
    if examples:
        fields["examples"] = examples
    if meta.get("source"):
        fields["source"] = str(meta["source"])
    fields["imported_from"] = f"pi-agent-factory:{rel}"
    for kind in ("implemented_by", "verified_by"):
        for end_path, symbol in _end_entries(meta.get(kind)):
            if symbol:
                report.add("symbol-narrowed", record_id,
                           f"{kind} {end_path} symbol {symbol} linked as the whole file")
            links.append((kind, Target(path=end_path), None))
    for upstream in _as_list(meta.get("upstream")):
        links.append(("upstream", Target(record=str(upstream)), None))
    for related in _as_list(meta.get("relates_to")):
        related = str(related)
        if _SR_RE.match(related):
            links.append(("relates_to", Target(record=related), None))
        else:
            report.add("relation-skipped", record_id,
                       f"relates_to {related}: only requirement targets are links in plumb")
    checksum = meta.get("checksum")
    binding = meta.get("binding")
    if checksum:
        if isinstance(binding, Mapping):
            try:
                ok = content_checksum(statement, binding) == str(checksum)
            except (KeyError, TypeError, ValueError):
                ok = False
            report.add("checksum-ok" if ok else "checksum-mismatch", record_id,
                       f"legacy checksum {str(checksum)[:19]}... "
                       + ("matches its content" if ok else "does not match its content"))
        else:
            report.add("checksum-mismatch", record_id, "legacy checksum without a binding")
    # implemented_by and verified_by first, then acceptance refs, then relations
    order = {"implemented_by": 0, "verified_by": 1, "upstream": 2, "relates_to": 3}
    links.sort(key=lambda link: (order[link[0]], link[2] is not None))
    return Planned("requirement", record_id, fields, body, rel, links)


def _bundle_members(source: Path, report: Report) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    directory = source / "bundles"
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(_read_text(path))
        except ValueError:
            report.add("malformed", path.stem, f"bundles/{path.name}: not JSON; skipped")
            continue
        bundle_id = str(data.get("id") or "") if isinstance(data, Mapping) else ""
        if not _FEAT_RE.match(bundle_id):
            continue  # not a feature bundle (for example a corrections batch)
        members = [str(m)[3:] for m in _as_list(data.get("members"))
                   if isinstance(m, str) and m.startswith("sr:")]
        out[bundle_id] = members
    return out


def _plan_features(source: Path, report: Report) -> list[Planned]:
    bundles = _bundle_members(source, report)
    planned: list[Planned] = []
    directory = source / "docs" / "features"
    seen: set[str] = set()
    for path in sorted(directory.glob("FEAT-*.md")) if directory.is_dir() else []:
        rel = path.relative_to(source).as_posix()
        meta, body = _split(_read_text(path))
        record_id = str((meta or {}).get("id") or "")
        if meta is None or not _FEAT_RE.match(record_id) or not meta.get("title"):
            report.add("malformed", record_id or path.stem, f"{rel}: skipped")
            continue
        seen.add(record_id)
        listed = [str(r) for r in _as_list(meta.get("requirements"))]
        bundled = bundles.get(record_id, [])
        union = list(dict.fromkeys(listed + bundled))
        only_feat = [r for r in listed if r not in bundled]
        only_bundle = [r for r in bundled if r not in listed]
        if record_id in bundles and (only_feat or only_bundle):
            report.add("membership-difference", record_id,
                       f"only in {rel}: {', '.join(only_feat) or '-'}; only in "
                       f"bundles/{record_id}.json: {', '.join(only_bundle) or '-'}")
        elif record_id not in bundles:
            report.add("membership-difference", record_id, f"no bundles/{record_id}.json")
        fields: dict[str, Any] = {"title": str(meta["title"])}
        if meta.get("description"):
            fields["description"] = str(meta["description"])
        fields["requirements"] = union
        fields["imported_from"] = f"pi-agent-factory:{rel}"
        planned.append(Planned("feature", record_id, fields, body, rel))
    for bundle_id in sorted(set(bundles) - seen):
        report.add("membership-difference", bundle_id,
                   f"bundles/{bundle_id}.json has no docs/features/{bundle_id}.md; skipped")
    return planned


def _first_heading(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or None
    return None


def _plan_ncs(source: Path, report: Report) -> list[Planned]:
    planned: list[Planned] = []
    directory = source / "docs" / "nonconformances"
    for path in sorted(directory.glob("NC-*.md")) if directory.is_dir() else []:
        rel = path.relative_to(source).as_posix()
        meta, body = _split(_read_text(path))
        from_name = _NC_FILE_RE.match(path.name)
        record_id = str((meta or {}).get("id") or (from_name.group(1) if from_name else ""))
        if not re.match(r"^NC-\d{4,}$", record_id):
            report.add("malformed", path.stem, f"{rel}: no NC id; skipped")
            continue
        lenient: list[str] = []
        if meta is None:
            meta = {}
            lenient.append("no frontmatter")
        title = meta.get("title") or _first_heading(body) or path.stem
        if not meta.get("title"):
            lenient.append("title taken from the body or file name")
        status = meta.get("status") or "open"
        if not meta.get("status"):
            lenient.append("status defaulted to open")
        if lenient:
            report.add("lenient", record_id, f"{rel}: " + "; ".join(lenient))
        fields: dict[str, Any] = {"title": str(title), "status": str(status)}
        for key in ("detected_by", "corrected_by", "external_ref"):
            if key in meta:
                fields[key] = meta[key]
        fields["imported_from"] = f"pi-agent-factory:{rel}"
        planned.append(Planned("nc", record_id, fields, body, rel))
    return planned


def read_head(source: Path) -> str | None:
    """The source's ``HEAD`` commit, read from ``.git`` files (never by running git)."""
    dot = Path(source) / ".git"
    try:
        if dot.is_file():
            line = _read_text(dot).strip()
            if not line.startswith("gitdir:"):
                return None
            gitdir = Path(line.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = Path(source) / gitdir
        elif dot.is_dir():
            gitdir = dot
        else:
            return None
        head = _read_text(gitdir / "HEAD").strip()
    except OSError:
        return None
    if _SHA_RE.match(head):
        return head
    if not head.startswith("ref:"):
        return None
    ref = head.split(":", 1)[1].strip()
    dirs = [gitdir]
    try:
        common = _read_text(gitdir / "commondir").strip()
        dirs.append((gitdir / common) if not Path(common).is_absolute() else Path(common))
    except OSError:
        pass
    for directory in dirs:
        try:
            value = _read_text(directory / ref).strip()
            if _SHA_RE.match(value):
                return value
        except OSError:
            pass
        try:
            for line in _read_text(directory / "packed-refs").splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref and _SHA_RE.match(parts[0]):
                    return parts[0]
        except OSError:
            pass
    return None


# --------------------------------------------------------------------------- importing


def import_pi_factory(core: Any, source: Path, *, dry_run: bool = False,
                      only: Iterable[str] | None = None) -> dict[str, Any]:
    """Import ``source`` into ``core``'s repository; returns the findings report."""
    from plumb.normalize import canonical_json, sha256_bytes

    source = Path(source)
    if not source.is_dir():
        raise FileNotFoundError(f"{source} is not a directory")
    wanted = {k.strip().upper() for k in (only or KINDS)} & set(KINDS)
    report = Report()
    planned: list[Planned] = []
    if "SR" in wanted:
        directory = source / "requirements"
        for path in sorted(directory.glob("SR-*.md")) if directory.is_dir() else []:
            item = _plan_requirement(path, path.relative_to(source).as_posix(), report)
            if item is not None:
                planned.append(item)
    features = _plan_features(source, Report() if "FEAT" not in wanted else report)
    if "FEAT" in wanted:
        planned.extend(features)
    if "NC" in wanted:
        planned.extend(_plan_ncs(source, report))

    index = core.index()
    batch: list[Planned] = []
    seen: set[str] = set()
    for item in planned:
        if item.record_id in index:
            report.add("collision", item.record_id,
                       f"{item.record_id} already exists here; {item.source_path} skipped")
            continue
        if item.record_id in seen:
            report.add("collision", item.record_id, f"duplicate id in the source "
                       f"({item.source_path}); skipped")
            continue
        seen.add(item.record_id)
        batch.append(item)
    present_features = {i for i in index if i.startswith("FEAT-")} | {
        p.record_id for p in batch if p.kind == "feature"}
    membership: dict[str, str] = {}
    for feature in features:
        if feature.record_id not in present_features:
            continue
        for sr in feature.fields["requirements"]:
            membership.setdefault(sr, feature.record_id)
    for item in batch:
        if item.kind == "requirement" and item.record_id in membership:
            item.fields["feature"] = membership[item.record_id]

    known = set(index) | {p.record_id for p in batch}
    if not dry_run:
        for item in batch:
            core.write_record(item.kind, item.fields, item.body, record_id=item.record_id)
    for item in batch:
        for kind, target, example in item.links:
            exists = (target.record in known if target.record is not None
                      else core.hash_target(target) is not None)
            if not exists:
                end = target.record or target.path
                report.add("missing-end", item.record_id,
                           f"{kind} {end} does not exist here; link not added")
                continue
            if dry_run:
                continue
            from plumb.links import LinkError

            try:
                core.add_link(item.record_id, kind, target, example)
            except LinkError as exc:
                report.add("link-skipped", item.record_id, str(exc))

    counts = {KINDS[k]: sum(1 for p in batch if p.kind == KINDS[k])
              for k in ("SR", "FEAT", "NC") if k in wanted}
    findings_digest = sha256_bytes(canonical_json(report.findings))
    head = read_head(source)
    result = {"source": str(source), "head": head, "dry_run": dry_run, "counts": counts,
              "imported": [p.record_id for p in batch], "findings": report.findings,
              "findings_digest": findings_digest}
    if not dry_run:
        core.log_append("events", "import", {
            "source": str(source), "head": head, "counts": counts,
            "findings": len(report.findings), "findings_digest": findings_digest,
            "records": [p.record_id for p in batch]})
    return result
