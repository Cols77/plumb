"""The merge boundary: ``plumb validate --merge <base>`` (spec 5.11, rulings R1 and R2).

Over ``<base>..HEAD`` plus uncommitted changes:

1. every touched requirement, the INT records it derives from, and each matters-true DEC that
   decides it must be confirmed at its current hash, and every changed source path must be
   owned by a requirement (``plumb.trace``: an untraced change skipped the read-back); what
   is not is listed, and never holds the merge (SR-260, DEC-252). Links are left out of a
   record's hash, so a requirement that gained an ``implemented_by`` or ``verified_by`` end in the
   range (by ``plumb link`` or a frontmatter edit) is an extension of it, listed until
   an approval of it lists that end. A requirement whose ``verified_by`` end (an acceptance
   test of an example the owner confirmed) changed since the approval pinned its content
   is listed as "acceptance test changed", shown with the example and the test's diff. A
   ``trace.exempt`` glob added in the range is
   honoured and listed: the judge accepts it unless it contradicts the owner (SR-288,
   SR-372), and a path that was
   source under the merge base's config stays source, so a config edit hides nothing;
2. the approvals and revocations added in the range are listed, agent-relayed ones marked with
   the prompt digest they cite;
3. fidelity (advisory) and 4. verification state, from the BRIDGE and VERIFY lanes when they
   are built, otherwise ``unavailable``: full verification pending, then for the touched
   requirements and every confirmed requirement whose acceptance tests cover a changed path,
   the acceptance tests that fail (with their example ids; a failure is kept until a run
   passes the test body that passed before it, so a test rewritten to pass still fails) or
   have no passing evidence on the current identity, and unresolved regressions (R3). Any of
   these, and a full verification pending that no owner waiver of this exact change covers
   (concept 7.4), makes the merge exit 5;
5. every log line present at the merge base of ``<base>`` and HEAD must still be present,
   unchanged (exit 1 otherwise).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.hashing import clean_rel_path, target_path

if TYPE_CHECKING:
    from plumb.api import Core

EXIT_MERGE_WAITS = 4
EXIT_REGRESSION = 5  # verification holds the merge: a failing or unverified acceptance test
CHANGED_TEST = "acceptance test changed"
DIFF_LINES = 12


class GitError(RuntimeError):
    pass


def _git(core: Core, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=core.root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout if result.returncode == 0 else ""


def changed_paths(core: Core, base: str) -> tuple[list[str], list[tuple[str, str]]]:
    """(paths changed between the merge base and the working tree, ``(sha, message)`` of
    each commit in the range)."""
    merge_base = _git(core, "merge-base", base, "HEAD").strip()
    diff = _git(core, "diff", "--relative", "--name-only", "-z", merge_base)
    untracked = _git(core, "ls-files", "--others", "--exclude-standard", "-z")
    paths = sorted({p for p in (diff + "\0" + untracked).split("\0") if p})
    log_out = _git(core, "log", "--format=%H%x1f%B%x00", f"{base}..HEAD")
    messages = []
    for chunk in log_out.split("\0"):
        sha, _, message = chunk.strip("\n").partition("\x1f")
        if sha and message.strip():
            messages.append((sha, message))
    return paths, messages


def touched_requirements(core: Core, paths: Sequence[str],
                         messages: Sequence[tuple[str, str]]) -> list[str]:
    """Requirements whose record or owning end changed, and those the range's ``SR:``
    trailers claim, read through every ``renumber`` (``claims.claimed_ids``, sp6 5.5): an
    incoming commit's ``SR-070`` means the renumbered ``SR-081``."""
    from plumb.claims import claimed_ids, trailer_aliases

    index = core.index()
    changed = {clean_rel_path(p) or p for p in paths}
    touched: set[str] = set()
    for record in index.values():
        if record.kind != "requirement":
            continue
        if record.path in changed:
            touched.add(record.id)
            continue
        for link in record.links:
            if link.kind in ("implemented_by", "verified_by"):
                end = target_path(link.target)
                if end and (clean_rel_path(end) or end) in changed:
                    touched.add(record.id)
                    break
    aliases = trailer_aliases(core) if messages else {}
    for sha, message in messages:
        for claimed in claimed_ids(aliases, sha, message):
            if claimed in index and index[claimed].kind == "requirement":
                touched.add(claimed)
    return sorted(touched)


def _show(core: Core, commit: str, rel: str) -> str | None:
    """``rel`` (relative to the root) as it was at ``commit``, or None when absent there."""
    result = subprocess.run(["git", "show", f"{commit}:./{rel}"], cwd=core.root,
                            capture_output=True)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace")


def show_many(core: Core, commit: str, rels: Sequence[str]) -> dict[str, str | None]:
    """Each of ``rels`` as it was at ``commit`` (None when absent), with ONE ``git cat-file
    --batch`` process instead of one ``git show`` per path."""
    rels = list(dict.fromkeys(rels))
    if not rels:
        return {}
    prefix = _git(core, "rev-parse", "--show-prefix", check=False).strip()
    request = "".join(f"{commit}:{prefix}{rel}\n" for rel in rels).encode("utf-8")
    result = subprocess.run(["git", "cat-file", "--batch"], cwd=core.root, input=request,
                            capture_output=True)
    if result.returncode != 0:
        return {rel: _show(core, commit, rel) for rel in rels}
    out: dict[str, str | None] = {}
    data, pos = result.stdout, 0
    for rel in rels:
        end = data.index(b"\n", pos)
        header = data[pos:end].split()
        pos = end + 1
        if len(header) != 3 or header[1] in (b"missing", b"ambiguous"):
            out[rel] = None
            continue
        size = int(header[2])
        out[rel] = data[pos:pos + size].decode("utf-8", "replace")
        pos += size + 1
    return out


def base_config(core: Core, fork: str) -> Any:
    """The config at the merge base (defaults when it had no ``.plumb/config.yaml``)."""
    from plumb.config import Config, config_from_mapping

    text = _show(core, fork, ".plumb/config.yaml")
    if text is None:
        return Config()
    import yaml

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return Config()
    return config_from_mapping(data if isinstance(data, Mapping) else {})


def approved_ends(core: Core) -> dict[str, set[str]]:
    """``{SR: ends}``: the owning ends listed by valid approvals of each requirement at its
    current hash (what the owner confirmed it owns), an approval a renumber carried
    included (R17)."""
    from plumb.confirm import checked_entries, pinned_through_renumbers

    index = core.index()
    out: dict[str, set[str]] = {}
    pairs = checked_entries(core.events(), core.config.approve.affirmations)
    for entry, problem, items in pinned_through_renumbers(core, pairs):
        if problem is not None or entry.kind != "approval":
            continue
        for item in items:
            record = index.get(str(item.get("id")))
            if record is None or item.get("hash") != record.hash:
                continue
            out.setdefault(record.id, set()).update(str(e) for e in item.get("ends") or [])
    return out


def extended_requirements(core: Core, fork: str,
                          paths: Sequence[str]) -> dict[str, list[str]]:
    """``{SR: new ends}``: requirements that gained an owning end in the range that no
    approval of the requirement at its current hash lists.

    Links are left out of the record hash, so ``plumb link`` or a frontmatter edit widens a
    confirmed requirement without unconfirming it; this is where the owner sees it."""
    from plumb.model import RecordError, parse_record
    from plumb.trace import owning_ends

    changed = {clean_rel_path(p) or p for p in paths}
    approved: dict[str, set[str]] | None = None
    out: dict[str, list[str]] = {}
    candidates = [r for r in core.index().values()
                  if r.kind == "requirement" and r.path in changed and owning_ends(r)]
    texts = show_many(core, fork, [r.path for r in candidates])
    for record in candidates:
        now = owning_ends(record)
        before: list[str] = []
        text = texts.get(record.path)
        if text is not None:
            try:
                before = owning_ends(parse_record(text, record.path))
            except (RecordError, ValueError):
                before = []
        new = [e for e in now if e not in before]
        if not new:
            continue
        if approved is None:
            approved = approved_ends(core)
        new = [e for e in new if e not in approved.get(record.id, set())]
        if new:
            out[record.id] = new
    return out


def required_records(core: Core, touched: Sequence[str]) -> list[str]:
    """Touched SRs, the INTs they derive from, and matters-true DECs deciding them."""
    index = core.index()
    required: list[str] = []

    def need(record_id: str) -> None:
        if record_id in index and record_id not in required:
            required.append(record_id)

    for sr in touched:
        need(sr)
        for link in index[sr].links:
            if link.kind == "derives_from" and link.target.record:
                need(link.target.record)
    for record in index.values():
        if record.kind == "decision" and record.fields.get("matters") is True:
            for link in record.links:
                if link.kind == "decides" and link.target.record in touched:
                    need(record.id)
    return required


def _base_lines(core: Core, commit: str, stream: str) -> list[str]:
    """The legacy JSONL lines of ``stream`` at ``commit`` (the format before SP6)."""
    rel = f"./.plumb/log/{stream}.jsonl"
    result = subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=core.root,
                            capture_output=True)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.decode("utf-8", "replace").splitlines()
            if line.strip()]


_LOG_PREFIX = ".plumb/log/"


def log_integrity(core: Core, base: str) -> tuple[list[str], dict[str, set[str]]]:
    """Problems (log entries present at the merge base and since modified or deleted) and the
    digests present there (SP6 6.4).

    Entry files: one ``git diff --name-status --no-renames <fork> -- .plumb/log/`` reports
    every entry file modified or deleted since the fork, in the working tree. Legacy JSONL
    lines at the fork must still be present, as a line or as a migrated entry file with the
    same verified digest. The fork is ``git merge-base <base> HEAD``, not the tip of ``base``:
    entries the base appended after the branch diverged are not part of this branch's
    history, so their absence is not tampering.
    """
    from plumb import log

    fork = _git(core, "merge-base", base, "HEAD").strip()
    problems: list[str] = []
    diff = _git(core, "diff", "--relative", "--name-status", "--no-renames", "-z", fork,
                "--", _LOG_PREFIX)
    fields = [f for f in diff.split("\0") if f]
    gone: set[str] = set()
    for status, path in zip(fields[0::2], fields[1::2], strict=False):
        name = path[len(_LOG_PREFIX):] if path.startswith(_LOG_PREFIX) else path
        if "/" not in name or not name.endswith(".json"):
            continue  # the legacy files are checked line by line below
        if status[:1] in ("M", "T"):
            problems.append(f"{path}: entry modified since merge-base {fork[:12]}")
            gone.add(name)
        elif status[:1] == "D":
            problems.append(f"{path}: entry deleted since merge-base {fork[:12]}")
            gone.add(name)
    listed = _git(core, "ls-tree", "-r", "--name-only", "-z", fork, "--", _LOG_PREFIX,
                  check=False)
    at_fork = {p[len(_LOG_PREFIX):] for p in listed.split("\0")
               if p.startswith(_LOG_PREFIX) and p.endswith(".json")}
    base_digests: dict[str, set[str]] = {}
    for stream in ("events", "evidence"):
        path = core.paths.log_path(stream)
        try:
            current = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
        except OSError:
            current = set()
        files = log.valid_entries(core.paths, stream)  # type: ignore[arg-type]
        migrated = set(files.values())
        digests = {d for name, d in files.items() if name in at_fork and name not in gone}
        for number, line in enumerate(_base_lines(core, fork, stream), start=1):
            try:
                digest = str(json.loads(line).get("digest"))
            except (ValueError, AttributeError):
                digest = ""
            if digest:
                digests.add(digest)
            if line not in current and digest not in migrated:
                problems.append(f"{path.name}: line {number} at merge-base {fork[:12]} is "
                                "missing or changed")
        base_digests[stream] = digests
    return problems, base_digests


def _describe(core: Core, record_id: str, state: str,
              new_ends: Sequence[str] = ()) -> list[str]:
    record = core.index()[record_id]
    fields = record.fields
    text = (fields.get("statement") or fields.get("readback") or fields.get("chosen")
            or fields.get("description") or "")
    quote = fields.get("quote")
    lines = [f"  {record_id} ({state}) {record.title}" + (f": {text}" if text else "")]
    for end in new_ends:
        lines.append(f"    new link in this range: {end} (now owned by {record_id})")
    if record.kind == "intent" and quote:
        quoted = quote if isinstance(quote, str) else " / ".join(map(str, quote))
        lines.append(f"    owner's words: \"{quoted}\"")
    if record.kind == "decision" and fields.get("question"):
        lines.append(f"    question: {fields.get('question')}")
    for example in record.examples:
        if example.criterion:
            lines.append(f"    {example.id}: {example.criterion}")
        else:
            lines.append(f"    {example.id}: given {example.given}, when {example.when}, "
                         f"then {example.then}")
    return lines


def changed_test_lines(core: Core, fork: str, record_id: str,
                       ends: Sequence[str]) -> list[str]:
    """For each confirmed acceptance test that changed since the owner's approval: the
    examples it verifies and its diff from the merge base (at most ``DIFF_LINES`` lines), so
    the owner sees what the test now asserts against the example they confirmed."""
    record = core.index()[record_id]
    examples = {e.id: e for e in record.examples}
    lines: list[str] = []
    for end in ends:
        verifies = [link.example for link in record.links
                    if link.kind == "verified_by" and (link.target.test or link.target.path)
                    == end and link.example]
        names = ", ".join(verifies) if verifies else "the requirement"
        lines.append(f"    acceptance test changed since you confirmed it: {end} "
                     f"(verifies {names})")
        for example_id in verifies:
            example = examples.get(example_id)
            if example is not None:
                text = example.criterion or (f"given {example.given}, when {example.when}, "
                                             f"then {example.then}")
                lines.append(f"      {example_id} you confirmed: {text}")
        path = end.split("::", 1)[0]
        diff = _git(core, "diff", fork, "--no-color", "--no-ext-diff", "--", path,
                    check=False).splitlines()
        body = [d for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---"))]
        for row in body[:DIFF_LINES]:
            lines.append(f"      {row}")
        if len(body) > DIFF_LINES:
            lines.append(f"      ... {len(body) - DIFF_LINES} more changed lines "
                         f"(git diff {fork[:12]} -- {path})")
    return lines


def live_verification(core: Core, found: Mapping[str, Any]) -> dict[str, Any]:
    """``found`` (``failing``, ``unverified``, ``regressions``) without any test of a frozen
    part (SR-380, DEC-404): such a test counts in no merge hold, whatever the verify lane hands
    over."""
    from plumb.frozen import is_frozen

    def awake(ref: Any) -> bool:
        return not is_frozen(core.config, str(ref))

    def by_record(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
        kept = {rid: [i for i in items if awake(i.get("test"))] for rid, items in rows.items()}
        return {rid: items for rid, items in kept.items() if items}

    return {"failing": by_record(found.get("failing") or {}),
            "unverified": by_record(found.get("unverified") or {}),
            "regressions": [t for t in found.get("regressions") or () if awake(t)]}


def _verification(core: Core, touched: Sequence[str], paths: Sequence[str],
                  fork: str) -> dict[str, Any]:
    """The verification part of the boundary. Its guarantee: the merge is never green unless
    every acceptance test the change can affect has passing evidence on the current identity
    and the full run R5 deferred to this boundary was done (or the owner waived it).

    The acceptance tests checked are those of the touched requirements and of every
    confirmed requirement whose acceptance tests cover a changed path (``affected``): a
    change to one requirement's code that breaks another's acceptance test is held too.
    ``full_pending`` holds the merge until a full run satisfies it or an owner waiver pins
    this exact change (``plumb tests waive --merge <base>``, concept 7.4)."""
    statuses = core.status(touched)
    not_covered = [i for i, s in statuses.items() if s.confirmation == "confirmed"
                   and not s.covered]
    out: dict[str, Any] = {"confirmed_not_covered": not_covered}
    try:
        from plumb.verify import open_verify
        from plumb.verify.policy import range_digest, waived
    except ImportError:
        out["available"] = False
        return out
    try:
        verify = open_verify(core)
        pending = verify.full_pending()
        affected = [i for i in verify.affected_requirements(paths) if i not in touched]
        scope = sorted({*touched, *affected})
        waiver = None
        if pending.pending:
            digest = range_digest(core.root, fork)
            waiver = digest if waived(core, digest) else None
        out.update({"available": True, "full_pending": pending.pending,
                    "full_pending_reasons": list(pending.reasons),
                    "full_waived": waiver,
                    "affected": affected,
                    **live_verification(core, {
                        "failing": verify.requirement_failures(scope),
                        "unverified": verify.unverified_acceptance(scope),
                        "regressions": verify.unresolved_regressions()})})
    except Exception as exc:  # a lane failure degrades, never blocks the boundary
        out.update({"available": False, "error": str(exc)})
    return out


def failing_line(record_id: str, item: Mapping[str, Any]) -> str:
    """``SR-001 EX-1 tests/test_x.py (regression)``: one failing acceptance test; a failure
    recorded on another identity reads ``(failing, stale: not rerun since the change)``."""
    examples = " ".join(item.get("examples") or ())
    kind = "regression" if item.get("regression") else "failing"
    if item.get("masked"):
        kind += ", hidden: the test was changed to pass and you have not confirmed the change"
    elif item.get("stale"):
        kind += ", stale: not rerun since the change"
    return " ".join(p for p in (record_id, examples, str(item.get("test")), f"({kind})") if p)


def merge_check(core: Core, base: str, *, as_json: bool) -> int:
    """``plumb validate --merge BASE``: the report-only form of ``plumb merge-check`` (sp3 9).

    It is ``plumb.boundary.merge_report(run_full=False)`` printed by ``render`` (or as JSON),
    so the two commands never disagree on the same tree. Returns the exit code."""
    from plumb.boundary import as_dict, merge_report, render

    report = merge_report(core, base, run_full=False)
    if as_json:
        print(json.dumps(as_dict(report), indent=2, default=str))
    else:
        for line in render(report):
            print(line)
    return report.exit
