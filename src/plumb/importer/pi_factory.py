"""Read-only reading of a pi-agent-factory register (concept 10, next-plan 9.1).

Reads a pi-agent-factory checkout and turns it into planned plumb records:

- ``requirements/SR-*.md`` -> requirements (``acceptance`` becomes ``AC-n`` examples, each
  ``verification.ref`` a ``verified_by`` link naming its ``AC-n``; structured
  ``implemented_by`` and ``verified_by`` bindings become symbol, test-node or file ends;
  ``upstream`` and ``relates_to`` become record links; a ``spec:<id>`` relation becomes a
  ``relates_to`` link to the document declaring that id); legacy ``checksum:`` values are
  verified with the extracted ``content_checksum`` and reported;
- ``docs/features/FEAT-*.md`` plus ``bundles/*.json`` -> features whose ``requirements`` are
  the union of both memberships, every difference reported;
- ``docs/nonconformances/NC-*.md`` -> nonconformances, read leniently, with a ``corrects``
  link to each SR the NC names.

Every record carries ``source: {repo: pi-agent-factory, path, upstream_hash}`` (the LF-form
SHA-256 of the source file), which makes a re-import an update of the same record. The
source is only ever opened for reading and no git command runs in it (``HEAD`` is read from
the ``.git`` files). Planning against the target and applying live in ``plan.py`` and
``apply.py``; ``import_pi_factory`` here is the entry point.
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
REPO = "pi-agent-factory"
_SR_RE = re.compile(r"^SR-\d{3,}$")
_SR_MENTION = re.compile(r"(?<![\w-])SR-\d{3,}(?!\d)")
_FEAT_RE = re.compile(r"^FEAT-\d{3,}$")
_NC_FILE_RE = re.compile(r"^(NC-\d{4,})")
_EXAMPLE_RE = re.compile(r"^AC-\d+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
SPEC_DIRS = ("docs/coherence/specs",)


@dataclass(frozen=True)
class LinkSpec:
    """A link the source asks for, before it is resolved against the target."""

    kind: str
    target: Target
    example: str | None = None
    spec_id: str | None = None      # a ``spec:<id>`` relation (``target`` is its document)


@dataclass
class Planned:
    """One record read from the source, with the links to add once all records exist."""

    kind: str
    record_id: str
    fields: dict[str, Any]
    body: str
    source_path: str
    links: list[LinkSpec] = field(default_factory=list)
    raw: bytes = b""


class Report:
    def __init__(self) -> None:
        self.findings: list[dict[str, str]] = []
        self._seen: set[tuple[str, str, str]] = set()

    def add(self, kind: str, record_id: str, detail: str) -> None:
        key = (kind, record_id, detail)
        if key in self._seen:  # two links to one missing end: one finding
            return
        self._seen.add(key)
        self.findings.append({"kind": kind, "id": record_id, "detail": detail})


# --------------------------------------------------------------------------- reading


def read_bytes(path: Path) -> bytes:
    with open(path, "rb") as handle:  # read-only, never anything else
        return handle.read()


def _read_text(path: Path) -> str:
    return read_bytes(path).decode("utf-8", errors="replace")


def lf_sha256(data: bytes) -> str:
    """pi-agent-factory's canonical content digest: SHA-256 of the LF form (hex)."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def source_field(rel: str, raw: bytes) -> dict[str, str]:
    return {"repo": REPO, "path": rel, "upstream_hash": "sha256:" + lf_sha256(raw)}


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


def _end(kind: str, path: str, symbol: str | None) -> Target:
    """A binding's end: a symbol (implemented_by) or test node (verified_by) when named."""
    from plumb.hashing import clean_rel_path
    from plumb.links import end_for

    rel = clean_rel_path(path) or path
    if not symbol:
        return Target(path=rel)
    return end_for(kind, Target(path=rel, symbol=symbol))


def _ref_end(ref: str) -> Target:
    """An acceptance ``verification.ref``: a test node when it names one, else the file."""
    from plumb.hashing import clean_rel_path, split_test_node

    path, sep, _ = ref.partition("::")
    rel = clean_rel_path(path) or path
    if not sep:
        return Target(path=rel)
    _, qualname = split_test_node(ref)
    if not qualname:
        return Target(path=rel)
    return Target(test=f"{rel}::" + "::".join(qualname.split(".")))


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


def spec_documents(source: Path) -> dict[str, str]:
    """``{spec id: source-relative path}`` of every spec document declaring an ``id``."""
    out: dict[str, str] = {}
    for directory in SPEC_DIRS:
        folder = source / directory
        for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
            try:
                meta, _ = _split(_read_text(path))
            except OSError:
                continue
            spec_id = (meta or {}).get("id")
            if isinstance(spec_id, str) and spec_id.strip():
                out.setdefault(spec_id.strip(), path.relative_to(source).as_posix())
    return out


def _plan_requirement(path: Path, rel: str, report: Report,
                      specs: Mapping[str, str]) -> Planned | None:
    raw = read_bytes(path)
    meta, body = _split(raw.decode("utf-8", errors="replace"))
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
    links: list[LinkSpec] = []
    for kind in ("implemented_by", "verified_by"):
        for end_path, symbol in _end_entries(meta.get(kind)):
            links.append(LinkSpec(kind, _end(kind, end_path, symbol)))
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
            ref = str(verification.get("ref") or "").strip()
            if ref:
                links.append(LinkSpec("verified_by", _ref_end(ref), ac_id))
    if examples:
        fields["examples"] = examples
    if meta.get("source"):
        fields["upstream_source"] = str(meta["source"])
    fields["source"] = source_field(rel, raw)
    for upstream in _as_list(meta.get("upstream")):
        links.append(LinkSpec("upstream", Target(record=str(upstream))))
    for related in _as_list(meta.get("relates_to")):
        related = str(related)
        if _SR_RE.match(related):
            links.append(LinkSpec("relates_to", Target(record=related)))
        elif related.startswith("spec:"):
            spec_id = related[len("spec:"):].strip()
            document = specs.get(spec_id)
            if document is None:
                report.add("relation-skipped", record_id,
                           f"relates_to {related}: no document in the source declares it")
            else:
                links.append(LinkSpec("relates_to", Target(path=document), spec_id=spec_id))
        else:
            report.add("relation-skipped", record_id,
                       f"relates_to {related}: only requirements and spec documents are "
                       "relation targets in plumb")
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
    return Planned("requirement", record_id, fields, body, rel, links, raw)


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
        raw = read_bytes(path)
        meta, body = _split(raw.decode("utf-8", errors="replace"))
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
        fields["source"] = source_field(rel, raw)
        planned.append(Planned("feature", record_id, fields, body, rel, [], raw))
    for bundle_id in sorted(set(bundles) - seen):
        report.add("membership-difference", bundle_id,
                   f"bundles/{bundle_id}.json has no docs/features/{bundle_id}.md; skipped")
    return planned


def _first_heading(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or None
    return None


def _named_requirements(meta: Mapping[str, Any], body: str) -> list[str]:
    """Every SR the NC names, frontmatter first, in order of appearance."""
    text = "\n".join(str(v) for k, v in meta.items() if k != "id") + "\n" + body
    return list(dict.fromkeys(_SR_MENTION.findall(text)))


def _plan_ncs(source: Path, report: Report) -> list[Planned]:
    planned: list[Planned] = []
    directory = source / "docs" / "nonconformances"
    for path in sorted(directory.glob("NC-*.md")) if directory.is_dir() else []:
        rel = path.relative_to(source).as_posix()
        raw = read_bytes(path)
        meta, body = _split(raw.decode("utf-8", errors="replace"))
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
        fields["source"] = source_field(rel, raw)
        links = [LinkSpec("corrects", Target(record=sr))
                 for sr in _named_requirements(meta, body)]
        planned.append(Planned("nc", record_id, fields, body, rel, links, raw))
    return planned


def read_source(source: Path, wanted: set[str],
                report: Report) -> tuple[list[Planned], list[Planned]]:
    """``(records of the wanted kinds, every feature)`` read from ``source``."""
    planned: list[Planned] = []
    if "SR" in wanted:
        specs = spec_documents(source)
        directory = source / "requirements"
        for path in sorted(directory.glob("SR-*.md")) if directory.is_dir() else []:
            item = _plan_requirement(path, path.relative_to(source).as_posix(), report, specs)
            if item is not None:
                planned.append(item)
    features = _plan_features(source, Report() if "FEAT" not in wanted else report)
    if "FEAT" in wanted:
        planned.extend(features)
    if "NC" in wanted:
        planned.extend(_plan_ncs(source, report))
    return planned, features


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


class ImportRefused(ValueError):
    """The import would write somewhere it must never write (exit 2)."""


def import_pi_factory(core: Any, source: Path, *, dry_run: bool = False,
                      only: Iterable[str] | None = None, diff: bool = False) -> dict[str, Any]:
    """Plan the import of ``source`` into ``core``'s repository and, unless ``dry_run``,
    apply it. Returns the report (with the plan's diff lines when ``dry_run`` or ``diff``)."""
    from plumb.importer.apply import apply_plan
    from plumb.importer.plan import plan_import

    plan = plan_import(core, source, only=only)
    applied = None if dry_run else apply_plan(core, plan)
    return plan.report(dry_run=dry_run, applied=applied, with_diff=True)
