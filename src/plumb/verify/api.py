"""``Verify``: the VerifyAPI (spec 12.1) plus the run flow behind ``plumb tests run``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from plumb.contracts import FullPending, NodeEvidence, Selection

DERIVED_VERSION = 2
# A hook parses at most this many files of a stale or missing test map inline (about 20 ms
# a file); a larger build runs outside the hook (``spawn_map_build``), R5.
HOOK_PARSE_MAX = 25
COVERAGE_UNKNOWN = ("coverage unknown: the test map is not built yet (it is being built "
                    "outside the hook; plumb map builds it now)")
MAP_BUILD_LOCK_S = 300.0


def spawn_map_build(root: Path) -> bool:
    """Start ``plumb map`` detached, so a cold test map is built outside every hook's budget
    (R5; at most one start per ``MAP_BUILD_LOCK_S``). Never raises; False when not started
    (``PLUMB_NO_BACKGROUND_MAP`` set, a recent start, or no process could start)."""
    import os
    import subprocess
    import sys
    import time

    if os.environ.get("PLUMB_NO_BACKGROUND_MAP"):
        return False
    lock = Path(root) / ".plumb" / "cache" / "map.building"
    try:
        if time.time() - lock.stat().st_mtime < MAP_BUILD_LOCK_S:
            return False
    except OSError:
        pass
    from plumb.background import popen_options

    options = popen_options(root)   # no console window for it or for its git and pytest calls
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(os.getpid()), encoding="utf-8")
        subprocess.Popen([sys.executable, "-m", "plumb", "map", "--root", str(root)],
                         **options)
    except OSError:
        return False
    return True


def _pending_dict(pending: FullPending) -> dict[str, Any]:
    return {"pending": pending.pending, "reasons": list(pending.reasons)}


@dataclass
class CoverageReport:
    """What ``plumb tests map --coverage`` did (SR-110)."""

    ran: list[str] = field(default_factory=list)       # nodes that ran to record
    recorded: list[str] = field(default_factory=list)  # nodes whose record was written
    failed: list[str] = field(default_factory=list)    # nodes that failed: no record
    fresh: int = 0                                      # recorded nodes left as they were
    workers: int = 0
    absent: bool = False                                # coverage is not installed
    discarded: str | None = None
    notes: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    stats: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ran": self.ran, "recorded": self.recorded, "failed": self.failed,
                "fresh": self.fresh, "workers": self.workers, "absent": self.absent,
                "discarded": self.discarded, "notes": self.notes,
                "elapsed_s": self.elapsed_s, "stats": self.stats}


@dataclass
class RunReport:
    """What one ``plumb tests run`` did, for printing and for ``--json``."""

    run_id: str | None = None
    full: bool = False
    selection: Selection | None = None
    outcomes: dict[str, str] = field(default_factory=dict)
    regressions: list[dict[str, Any]] = field(default_factory=list)
    not_yet_passing: list[str] = field(default_factory=list)
    flaky: list[str] = field(default_factory=list)
    removed_after_passing: list[str] = field(default_factory=list)
    collection_errors: list[str] = field(default_factory=list)
    discarded: str | None = None
    aborted: str | None = None
    timed_out: bool = False
    timeout_s: float | None = None
    exit_status: int | None = None
    elapsed_s: float = 0.0
    full_pending: FullPending | None = None
    notes: list[str] = field(default_factory=list)  # lines the run says (SR-110)
    workers: int = 0                                 # xdist workers the run used (0: serial)

    @property
    def failed(self) -> list[str]:
        return sorted(n for n, o in self.outcomes.items() if o == "failed")

    @property
    def ok(self) -> bool:
        return (not self.failed and not self.collection_errors and not self.discarded
                and not self.aborted and not self.timed_out)

    def as_dict(self) -> dict[str, Any]:
        sel = self.selection
        return {
            "run_id": self.run_id, "full": self.full, "outcomes": self.outcomes,
            "failed": self.failed, "regressions": self.regressions,
            "not_yet_passing": self.not_yet_passing, "flaky": self.flaky,
            "removed_after_passing": self.removed_after_passing,
            "collection_errors": self.collection_errors, "discarded": self.discarded,
            "aborted": self.aborted, "timed_out": self.timed_out, "exit_status": self.exit_status,
            "elapsed_s": self.elapsed_s, "notes": self.notes, "workers": self.workers,
            "selection": None if sel is None else {
                "nodes": list(sel.nodes), "deferred": list(sel.deferred),
                "sampled": list(sel.sampled), "unknown_coverage": list(sel.unknown_coverage),
                "infra_changed": list(sel.infra_changed), "doc_only": sel.doc_only,
                "unrecorded": list(sel.unrecorded), "notes": list(sel.notes)},
            "full_pending": None if self.full_pending is None else {
                "pending": self.full_pending.pending,
                "reasons": list(self.full_pending.reasons)},
        }


class Verify:
    """VerifyAPI over one CoreAPI. Map, index and env key are cached per instance."""

    def __init__(self, core: Any, *, hook: bool = False) -> None:
        self.core = core
        self.root = Path(core.root)
        self.hook = hook
        self.map_missing: str | None = None  # hook mode: why the map was not built inline
        self._map: Any = None
        self._index: dict[str, Any] | None = None
        self._env_key: str | None = None
        self._funcmap: Any = None

    # -- cached state
    def test_map(self) -> Any:
        """The test map. In hook mode, ``MapUnavailable`` instead of a build that would take
        longer than a hook may spend (more than ``HOOK_PARSE_MAX`` files to parse); the
        build is then started outside the hook (``spawn_map_build``)."""
        if self._map is None:
            from plumb.verify.testmap import MapUnavailable, build_map

            if self.map_missing is not None:
                raise MapUnavailable(self.map_missing)
            try:
                self._map = build_map(self.core,
                                      max_parse=HOOK_PARSE_MAX if self.hook else None)
            except MapUnavailable as exc:
                self.map_missing = str(exc)
                spawn_map_build(self.root)
                raise
        return self._map

    def index(self) -> dict[str, Any]:
        if self._index is None:
            from plumb.verify.evidence import load_index

            self._index = load_index(self.core)
        return self._index

    def env_key(self) -> str:
        if self._env_key is None:
            from plumb.verify.envid import env_key

            self._env_key = env_key(self.root)
        return self._env_key

    # -- the function-to-tests record (SR-110)
    def funcmap(self) -> Any:
        if self._funcmap is None:
            from plumb.verify.funcmap import FuncMap

            self._funcmap = FuncMap.open(self.core)
        return self._funcmap

    def coverage_mode(self) -> str:
        """``off`` (verify.coverage is off), ``absent`` (the coverage package is missing) or
        ``auto``."""
        from plumb.verify.runner import coverage_available
        from plumb.verify.select import coverage_off

        if coverage_off(self.core.config.verify):
            return "off"
        return "auto" if coverage_available() else "absent"

    def _cov_sources(self) -> tuple[str, ...]:
        config = self.core.config
        tests = {d.strip("/") for d in config.test_dirs}
        return tuple(str(self.root / d) for d in config.source_dirs
                     if d.strip("/") not in tests and (self.root / d).is_dir())

    def _cov_begin(self, tmap: Any, *, deselect: bool = False,
                   rebuild: bool = False) -> tuple[Any, Path, int]:
        """The coverage spec of a run: stale tests are measured, fresh ones are not (and are
        not run at all when ``deselect``). Returns ``(spec, temp dir, fresh count)``."""
        import tempfile

        from plumb.verify.runner import CovSpec

        fm = self.funcmap()
        if rebuild:
            fm.clear()
        digests = {f: tmap.closure_hash(f) for f in tmap.test_files}
        fresh = fm.fresh_nodes(digests, self.env_key())
        tmp = Path(tempfile.mkdtemp(prefix="plumb-cov-"))
        spec = CovSpec(data_base=str(tmp / "cov"), sources=self._cov_sources(),
                       skip=frozenset(fresh), deselect=deselect)
        return spec, tmp, len(fresh)

    def _cov_end(self, outcome: Any, tmap: Any, tmp: Path, spec: Any, *,
                 refresh: bool = False) -> list[str]:
        """Write the record of the nodes that passed with coverage on; returns them."""
        import shutil

        from plumb.verify.funcmap import combine_data_files, ingest_coverage
        from plumb.verify.testmap import is_test_file

        try:
            files = outcome.result.cov_files
            if not files or outcome.discarded or outcome.result.timed_out:
                return []
            nodes = {n: n.split("::", 1)[0] for n, d in outcome.result.nodes.items()
                     if d.get("outcome") == "passed" and n not in spec.skip}
            if not nodes:
                return []
            data = combine_data_files(files, str(tmp / "combined"))
            digests = {f: tmap.closure_hash(f) for f in set(nodes.values())}
            test_dirs = tuple(self.core.config.test_dirs)
            return ingest_coverage(self.funcmap(), data, nodes, digests, self.env_key(),
                                   skip_file=lambda rel: is_test_file(rel, test_dirs),
                                   refresh=refresh)
        except Exception as exc:  # noqa: BLE001 - a recording failure never fails a run
            outcome.result.notes.append(f"coverage record not written: {exc}")
            return []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def map_coverage(self, *, rebuild: bool = False) -> CoverageReport:
        """``plumb tests map --coverage``: run the tests whose record is missing or stale
        (every test the first time) once under coverage contexts, on ``verify.workers``
        workers, and record the functions each executed."""
        import shutil

        from plumb.verify.runner import run_selection

        report = CoverageReport()
        mode = self.coverage_mode()
        if mode == "absent":
            report.absent = True
            report.notes.append("coverage is not installed: tests are selected by their "
                                "import closure (install the dev dependency 'coverage')")
            return report
        if mode == "off":
            report.notes.append("verify.coverage is off: tests are selected by their import "
                                "closure")
            return report
        tmap = self.test_map()
        spec, tmp, fresh = self._cov_begin(tmap, deselect=True, rebuild=rebuild)
        report.fresh = fresh
        try:
            outcome = run_selection(self.core, [], full=True, tmap=tmap, cov=spec)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        result = outcome.result
        report.workers = result.workers
        report.notes += result.notes
        report.elapsed_s = result.elapsed_s
        report.discarded = outcome.discarded
        report.ran = sorted(result.nodes)
        report.failed = sorted(n for n, d in result.nodes.items()
                               if d.get("outcome") == "failed")
        report.recorded = self._cov_end(outcome, tmap, tmp, spec, refresh=True)
        if not outcome.discarded and not result.timed_out:
            self.funcmap().refresh_all()  # what changed has now been recorded: new baseline
        if outcome.discarded:
            report.notes.append(f"record discarded ({outcome.discarded} during the run)")
        report.stats = self.funcmap().stats() if self.funcmap().exists() else {}
        return report

    # -- VerifyAPI
    def select(self, changed: Sequence[str], *, budget_s: float | None = None) -> Selection:
        """The covering tests of ``changed`` (spec 7.2). The one choke point of R5 for every
        host: when the test map is not available within a hook's budget, the bounded
        unknown-coverage sample (``unknown_selection``) with ``full_pending`` set, never
        nothing."""
        from plumb.verify.evidence import durations
        from plumb.verify.select import select_tests
        from plumb.verify.testmap import MapUnavailable

        index = self.index()
        try:
            tmap = self.test_map()
        except MapUnavailable:
            return self.unknown_selection(changed)
        funcmap = None
        extra: tuple[str, ...] = ()
        if self.coverage_mode() == "auto":
            candidate = self.funcmap()
            if candidate.exists():
                funcmap = candidate
        if funcmap is not None and not funcmap.is_recorded_anywhere(self.env_key()):
            funcmap = None
            if self.funcmap().stats()["tests"]:
                extra = ("the function record is for another environment: tests are selected "
                         "by their import closure (plumb tests map --coverage records it again)",)
        sel = select_tests(self.core, tmap, changed, budget_s=budget_s,
                           durations=durations(index), scale=float(index.get("scale") or 1.0),
                           funcmap=funcmap, env_key=self.env_key() if funcmap else None)
        return replace(sel, notes=sel.notes + extra) if extra else sel

    def unknown_selection(self, changed: Sequence[str]) -> Selection:
        """R5 without a test map: the changed test files themselves plus a bounded,
        deterministic sample of the tests nearest each changed source file (at most
        ``verify.sample_size``), every source file reported as unknown coverage."""
        from plumb.trace import is_code_path
        from plumb.verify.select import (
            is_documentation,
            matches_infra,
            nearest_tests,
            normalize_path,
        )
        from plumb.verify.testmap import is_test_file, scan_files

        config = self.core.config
        vcfg = config.verify
        norm = list(dict.fromkeys(p for p in (normalize_path(c) for c in changed) if p))
        docs = [p for p in norm if is_documentation(p)]
        infra = sorted(p for p in norm if p not in docs and matches_infra(p, vcfg.infra_globs))
        rest = [p for p in norm if p not in docs and p not in infra
                and not (self.root / p).is_dir()]
        tests = sorted(r for r in scan_files(self.root, config)
                       if is_test_file(r, config.test_dirs))
        test_set = set(tests)
        reasons: dict[str, Any] = {p: "import" for p in rest if p in test_set}
        unknown = tuple(p for p in rest if p not in test_set and is_code_path(config, p))
        sampled: list[str] = []
        for path in unknown:
            pool = [t for t in tests if t not in reasons]
            for test in nearest_tests(path, pool, config.source_dirs, config.test_dirs,
                                      vcfg.sample_size):
                if len(sampled) >= vcfg.sample_size:
                    break
                reasons[test] = "sample"
                sampled.append(test)
        nodes = tuple(reasons)
        return Selection(changed=tuple(norm), nodes=nodes, reasons=reasons, deferred=(),
                         sampled=tuple(sampled), unknown_coverage=unknown,
                         infra_changed=tuple(infra),
                         doc_only=bool(norm) and len(docs) == len(norm),
                         expected_s=float(len(nodes)) * float(vcfg.default_test_s))

    def recorded_regressions(self, since: str = "") -> dict[str, NodeEvidence]:
        """Trigger 3 without a test map (R3): the nodes whose last recorded run, at or after
        ``since`` (ISO time), failed after a recorded pass. Read from the evidence index
        alone, so the regression check never waits for the map."""
        out: dict[str, NodeEvidence] = {}
        for node_id, entry in sorted(self.index().get("nodes", {}).items()):
            last = entry.get("last") or {}
            passed = entry.get("last_pass")
            if last.get("outcome") != "failed" or not passed:
                continue
            if since and str(last.get("at") or "") < since:
                continue
            out[node_id] = NodeEvidence(
                node_id=node_id, state="fresh-fail", regression=True,
                test_changed_since_pass=last.get("test_hash") != passed.get("test_hash"),
                last_run=last.get("run_id"))
        return out

    def expected_s(self, targets: Iterable[str]) -> float:
        """The unscaled estimate of ``targets`` (recorded durations, defaults otherwise)."""
        from plumb.verify.evidence import durations
        from plumb.verify.select import expected_duration

        known = durations(self.index())
        default = float(self.core.config.verify.default_test_s)
        tmap = self.test_map()
        return round(sum(expected_duration(t, tmap.nodes_of, known, default)
                         for t in targets), 6)

    def evidence(self, nodes: Iterable[str]) -> Mapping[str, NodeEvidence]:
        from plumb.verify.evidence import node_evidence
        from plumb.verify.testmap import MapUnavailable

        nodes = list(nodes)
        try:
            tmap = self.test_map()
        except MapUnavailable:  # no closure to check freshness against: not yet run
            return {n: NodeEvidence(node_id=n, state="none") for n in nodes}
        index, key = self.index(), self.env_key()
        identity = self.identity()
        return {n: node_evidence(index, tmap, n, key, identity) for n in nodes}

    def identity(self, *, compute: bool = False) -> str | None:
        """The content identity cached under the env key (VS3); computed only on record."""
        from plumb.verify.envid import cached_identity

        return cached_identity(self.core, self.env_key(), compute=compute)

    def fingerprint(self) -> str:
        """A digest of everything the map-derived answers come from: the scanned Python
        files (size and mtime, as the map's own cache), the records and their links, the
        evidence log, the config, the environment key and the shared test infrastructure
        outside the scanned directories. Never memoized: a run appends evidence."""
        import json
        import os

        from plumb.log import stream_stamp
        from plumb.model import link_to_dict
        from plumb.normalize import sha256_text
        from plumb.verify.testmap import scan_files

        def stat(path: Path) -> str:
            try:
                st = os.stat(path)
            except OSError:
                return "-"
            return f"{st.st_size}:{st.st_mtime_ns}"

        core = self.core
        records = [[r.id, r.path, r.hash, [link_to_dict(link) for link in r.links]]
                   for _, r in sorted(core.index().items())]
        infra = {p: stat(self.root / p) for p in core.config.verify.infra_globs
                 if not any(ch in p for ch in "*?[")}
        parts = {"v": DERIVED_VERSION, "scan": scan_files(self.root, core.config),
                 "map": stat(core.paths.test_map_json),
                 "records": records,
                 "evidence": stream_stamp(core.paths, "evidence"),  # SP6 6.3
                 "config": stat(core.paths.config), "env": self.env_key(),
                 "identity": stat(core.paths.env_identity), "infra": infra}
        return sha256_text(json.dumps(parts, sort_keys=True, default=str))

    def derived(self, name: str, compute: Any) -> Any:
        """``compute()``, cached in ``.plumb/cache/derived.json`` under ``fingerprint()``."""
        import json
        import os

        path = self.core.paths.cache / "derived.json"
        fp = self.fingerprint()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        values = data.get("values") if isinstance(data, dict) and data.get("fp") == fp \
            else None
        values = values if isinstance(values, dict) else {}
        if name in values:
            return values[name]
        value = compute()
        after = self.fingerprint()  # computing may have built the map (a new map stat)
        if after != fp:
            fp, values = after, {}
        values[name] = value
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps({"fp": fp, "values": values}), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass
        return value

    def full_pending(self) -> FullPending:
        """Whether a full run is due (R5), cached by ``fingerprint()`` for the hooks. Pending
        ("coverage unknown") while the test map is not built (hook mode)."""
        from plumb.verify.testmap import MapUnavailable

        try:
            data = self.derived("full_pending",
                                lambda: _pending_dict(self._full_pending()))
        except MapUnavailable:
            return FullPending(pending=True, reasons=(COVERAGE_UNKNOWN,))
        return FullPending(pending=bool(data["pending"]), reasons=tuple(data["reasons"]))

    def _full_pending(self) -> FullPending:
        from plumb.verify.select import matches_infra

        tmap = self.test_map()
        full = self.index().get("full")
        if not full:
            if not tmap.test_files:  # no test to run: a full run has nothing to verify
                return FullPending(pending=False, reasons=())
            return FullPending(pending=True, reasons=("no full run recorded",))
        reasons: list[str] = []
        current = self.infra_hashes()
        recorded = full.get("infra") or {}
        for path in sorted(set(current) | set(recorded)):
            if current.get(path) != recorded.get(path):
                reasons.append(f"{path} changed")
        still_failing = self._full_failures(full)
        if still_failing:
            reasons.append(f"{len(still_failing)} test(s) failed in the last full run and "
                           f"have not passed since ({', '.join(still_failing[:3])}"
                           + (" ..." if len(still_failing) > 3 else "") + ")")
        files = full.get("files") or {}
        globs = self.core.config.verify.infra_globs
        for path in self.uncovered_sources():
            if matches_infra(path, globs):
                continue
            if tmap.files.get(path, {}).get("hash") != files.get(path):
                reasons.append(f"{path} has no covering test")
        return FullPending(pending=bool(reasons), reasons=tuple(reasons))

    def _full_failures(self, full: Mapping[str, Any]) -> list[str]:
        """Nodes that failed in the last full run, still exist, and have not passed since:
        a full run with a failing test is no full verification (R5)."""
        from plumb.verify.evidence import GOOD_OUTCOMES
        from plumb.verify.markers import strip_param

        tmap = self.test_map()
        nodes = self.index().get("nodes", {})
        out = []
        for node_id in full.get("failed") or []:
            test_file = node_id.split("::", 1)[0]
            if test_file in tmap.files and strip_param(node_id) not in tmap.nodes_of(test_file):
                continue  # deleted from the source since: nothing left to pass
            last = (nodes.get(node_id) or {}).get("last") or {}
            if last.get("outcome") not in GOOD_OUTCOMES:
                out.append(node_id)
        return out

    def tests_for(self, refs: Iterable[str]) -> Mapping[str, tuple[str, ...]]:
        from plumb.verify.testmap import MapUnavailable

        refs = list(refs)
        try:
            return self._tests_for(refs)
        except MapUnavailable:  # hook mode, no map yet: nothing mapped
            return {ref: () for ref in refs}

    def _tests_for(self, refs: list[str]) -> Mapping[str, tuple[str, ...]]:
        from plumb.model import ID_PATTERN
        from plumb.verify.select import normalize_path

        if refs and all(ID_PATTERN.match(ref) for ref in refs):
            # record ids only (the prompt hook, the brief): no map build on a warm call
            records = self.derived("record_tests", lambda: {
                k: list(v) for k, v in self.test_map().records.items()})
            return {ref: tuple(records.get(ref, ())) for ref in refs}
        tmap = self.test_map()
        out: dict[str, tuple[str, ...]] = {}
        for ref in refs:
            if ID_PATTERN.match(ref):
                out[ref] = tuple(tmap.records.get(ref, ()))
                continue
            rel = normalize_path(ref) or ref
            if rel in tmap.test_files:
                out[ref] = (rel,)
                continue
            tests: list[str] = []
            for test in [*tmap.verified_tests(rel), *tmap.mentions(rel), *tmap.covering(rel)]:
                if test not in tests:
                    tests.append(test)
            out[ref] = tuple(tests)
        return out

    def requirement_failures(self, ids: Iterable[str] | None = None,
                             ) -> dict[str, list[dict[str, Any]]]:
        """Requirements whose acceptance tests fail: ``{SR: [{test, examples, state,
        regression, stale, last_run}]}``.

        A requirement's tests are its ``verified_by`` ends (with the example ids each link
        names) plus the tests the map ties to it by marker. A test fails when its last
        recorded run failed, whatever changed after it, until a run passes it: a test that
        never passed (not yet passing) as much as a regression (R3). ``stale`` marks a
        failure recorded on another identity (code, test or environment changed since)."""
        return {record_id: [item for item in items if item["failing"]]
                for record_id, items in self.acceptance(ids).items()
                if any(item["failing"] for item in items)}

    def unverified_acceptance(self, ids: Iterable[str] | None = None,
                              ) -> dict[str, list[dict[str, Any]]]:
        """Acceptance tests with no recorded failure and no passing evidence on the current
        identity (never run, or stale since their last pass): ``{SR: [items]}``."""
        return {record_id: [item for item in items if item["unverified"]]
                for record_id, items in self.acceptance(ids).items()
                if any(item["unverified"] for item in items)}

    def acceptance(self, ids: Iterable[str] | None = None,
                   ) -> dict[str, list[dict[str, Any]]]:
        """Every acceptance test of the requirements ``ids`` (default: all) with its state:
        ``{SR: [{test, examples, state, regression, masked, stale, failing, unverified,
        last_run}]}``; ``failing`` and ``unverified`` are exclusive, both false only for a
        test passing on the current identity. ``masked``: the test passes only after it was
        changed since it regressed, and the owner has not confirmed the change; it counts
        as a failing regression (``masked_regressions``)."""
        index = self.core.index()
        wanted = list(ids) if ids is not None else sorted(
            i for i, r in index.items() if r.kind == "requirement")
        wanted = [i for i in wanted if i in index and index[i].kind == "requirement"]
        per_record: dict[str, dict[str, list[str]]] = {}
        for record_id in wanted:
            tests: dict[str, list[str]] = {}
            for link in index[record_id].links:
                if link.kind != "verified_by":
                    continue
                ref = link.target.test or link.target.path
                if not ref:
                    continue
                examples = tests.setdefault(ref, [])
                if link.example and link.example not in examples:
                    examples.append(link.example)
            per_record[record_id] = tests
        if wanted:
            for record_id, mapped in self.tests_for(wanted).items():
                tests = per_record.setdefault(record_id, {})
                for test in mapped:
                    if test not in tests and test.split("::", 1)[0] not in tests:
                        tests[test] = []
        refs = list(dict.fromkeys(t for tests in per_record.values() for t in tests))
        evidence = self.evidence(refs) if refs else {}
        masked: dict[str, set[str]] = {}  # test file -> SRs whose changed test hid a regression
        for item in self.masked_regressions() if refs else ():
            masked.setdefault(item["node"].split("::", 1)[0], set()).update(item["requirements"])
        out: dict[str, list[dict[str, Any]]] = {}
        for record_id, tests in per_record.items():
            items = []
            for ref, examples in tests.items():
                ev = evidence[ref]
                hidden = record_id in masked.get(ref.split("::", 1)[0], ())
                failing = ev.state == "fresh-fail" or ev.last_failed or ev.regression or hidden
                passing = ev.state in ("fresh-pass", "flaky-pass")
                items.append({"test": ref, "examples": examples, "state": ev.state,
                              "regression": ev.regression or hidden, "masked": hidden,
                              "stale": ev.state in ("stale", "none"), "failing": failing,
                              "unverified": not failing and not passing,
                              "last_run": ev.last_run})
            if items:
                out[record_id] = items
        return out

    def unresolved_regressions(self) -> list[str]:
        """Test nodes that passed with recorded evidence, failed in their last run, and still
        exist (R3): no later run has passed them."""
        from plumb.verify.markers import strip_param
        from plumb.verify.policy import is_regression

        tmap = self.test_map()
        index = self.index()
        out = []
        for node_id in sorted(index.get("nodes", {})):
            if "::" not in node_id or not is_regression(index, node_id):
                continue
            test_file = node_id.split("::", 1)[0]
            info = tmap.files.get(test_file)
            if info is None or strip_param(node_id) not in info.get("nodes", {}):
                continue
            out.append(node_id)
        return out

    def masked_regressions(self, files: Iterable[str] | None = None,
                           statuses: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """Regressions of owner-confirmed acceptance tests that a change to the test hid:
        ``[{node, passed_in, failed_in, masked_by, requirements: {SR: [EX ids]}}]``.

        A node counts while its recorded regression has had no pass on the test body that
        passed before it (``evidence._track_regression``: a pass after the test body changed
        marks it ``masked_by`` that run; a deleted node counts too) and its file is a
        ``verified_by`` end of a requirement the owner has approved (confirmed or an
        unconfirmed edit) whose current content no standing approval pinned
        (``confirm.approved_test_pins``). Rerunning the original test, or the owner confirming
        the requirement with the changed test (``plumb approve``), resolves it. ``files``
        limits it to those test files."""
        from plumb.confirm import approved_test_pins, verified_end
        from plumb.verify.markers import strip_param

        core = self.core
        index = core.index()
        statuses = core.status() if statuses is None else statuses
        pins = approved_test_pins(core.events(), core.config.approve.affirmations, index)
        changed: dict[str, dict[str, list[str]]] = {}
        for record_id, status in statuses.items():
            confirmation = getattr(status, "confirmation", "proposed")
            if record_id not in index or confirmation == "proposed":
                continue
            pinned = pins.get(record_id, {})
            for link in index[record_id].links:
                end = verified_end(link)
                if end is None:
                    continue
                now = core.hash_target(link.target)
                if now is not None and now in pinned.get(end, ()):
                    continue  # the owner confirmed this exact test content
                examples = changed.setdefault(end.split("::", 1)[0], {}).setdefault(
                    record_id, [])
                if link.example and link.example not in examples:
                    examples.append(link.example)
        if not changed:
            return []
        wanted = None if files is None else {f.split("::", 1)[0] for f in files}
        tmap = self.test_map()
        out = []
        for node_id, entry in sorted(self.index().get("nodes", {}).items()):
            regressed = entry.get("regressed") or {}
            test_file = node_id.split("::", 1)[0]
            if not regressed or test_file not in changed:
                continue
            if wanted is not None and test_file not in wanted:
                continue
            info = tmap.files.get(test_file)
            deleted = info is None or strip_param(node_id) not in info.get("nodes", {})
            if not regressed.get("masked_by") and not deleted:
                continue  # still failing: an ordinary regression (unresolved_regressions)
            out.append({"node": node_id, "passed_in": regressed.get("passed_in"),
                        "failed_in": regressed.get("failed_in"),
                        "masked_by": regressed.get("masked_by"),
                        "requirements": changed[test_file]})
        return out

    def affected_requirements(self, paths: Iterable[str]) -> list[str]:
        """Confirmed requirements (confirmed or an unconfirmed edit) whose acceptance tests
        (``verified_by`` ends and marker-mapped tests) cover one of ``paths``: a changed test
        file itself, or a test whose import closure, mention or ``verified_by`` link reaches a
        changed source path. The merge boundary checks their evidence, so a change to one
        requirement's code that breaks another requirement's acceptance test cannot pass
        unrerun."""
        paths = [p for p in paths if p]
        if not paths:
            return []
        covering: set[str] = set()
        for tests in self.tests_for(paths).values():
            covering.update(t.split("::", 1)[0] for t in tests)
        if not covering:
            return []
        index = self.core.index()
        statuses = self.core.status()
        out = []
        for record_id, items in self.acceptance(
                [i for i, s in statuses.items() if index[i].kind == "requirement"
                 and s.confirmation != "proposed"]).items():
            if any(str(item["test"]).split("::", 1)[0] in covering for item in items):
                out.append(record_id)
        return sorted(out)

    def impact(self, ref: str) -> dict[str, Any]:
        """Downstream of a record or a path: records, code ends, covering tests (VS4)."""
        from plumb.hashing import clean_rel_path, target_path
        from plumb.model import ID_PATTERN

        index = self.core.index()
        if ID_PATTERN.match(ref):
            seen = {ref}
            frontier = [ref]
            while frontier:
                nxt = []
                for record in index.values():
                    if record.id in seen:
                        continue
                    if any(link.target.record in frontier for link in record.links):
                        seen.add(record.id)
                        nxt.append(record.id)
                frontier = nxt
            records = sorted(seen - {ref})
            refs = [ref, *records]
        else:
            ref = clean_rel_path(ref) or ref
            records = list(self.core.records_for_paths([ref]).get(ref, ()))
            refs = [ref]
        paths: list[str] = []
        for rid in ([ref, *records] if ID_PATTERN.match(ref) else []):
            record = index.get(rid)
            for link in record.links if record else ():
                if link.kind == "implemented_by":
                    path = target_path(link.target)
                    if path and path not in paths:
                        paths.append(path)
        tests: list[str] = []
        for group in self.tests_for([*refs, *paths]).values():
            for test in group:
                if test not in tests:
                    tests.append(test)
        evidence = self.evidence(tests)
        return {"ref": ref, "records": records, "paths": paths,
                "tests": [{"test": t, "state": evidence[t].state,
                           "regression": evidence[t].regression} for t in tests]}

    # -- helpers
    def infra_hashes(self) -> dict[str, str]:
        """Current hashes of every shared test infrastructure file present."""
        from plumb.normalize import file_digest
        from plumb.verify.select import matches_infra

        globs = tuple(self.core.config.verify.infra_globs)
        candidates = {p for p in self.test_map().files if matches_infra(p, globs)}
        for pattern in globs:
            if not any(ch in pattern for ch in "*?[") and (self.root / pattern).is_file():
                candidates.add(pattern)
        out: dict[str, str] = {}
        for rel in sorted(candidates):
            try:
                out[rel] = file_digest(self.root / rel)
            except OSError:
                continue
        return out

    def uncovered_sources(self) -> list[str]:
        """Non-test Python files no test covers by any rule of the map."""
        tmap = self.test_map()
        out = []
        for path, info in sorted(tmap.files.items()):
            if info.get("test"):
                continue
            if tmap.importers.get(path) or tmap.naming.get(path) or tmap.verified_tests(path):
                continue
            if tmap.mentions(path):
                continue
            out.append(path)
        return out

    def changed_paths(self) -> list[str]:
        """``git status`` paths plus every session's touched list (spec 12.5)."""
        from plumb.verify.evidence import changed_paths_from_git

        paths = list(changed_paths_from_git(self.root))
        session = self.core.paths.session
        try:
            dirs = [d for d in session.iterdir() if d.is_dir()]
        except OSError:
            dirs = []
        for d in dirs:
            try:
                lines = (d / "touched.txt").read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            paths.extend(line.strip() for line in lines if line.strip())
        return list(dict.fromkeys(paths))

    # -- the run flow
    def run(self, *, changed: Sequence[str] | None = None, nodes: Sequence[str] | None = None,
            full: bool = False, budget_s: float | None = None) -> RunReport:
        from plumb.verify import evidence as ev
        from plumb.verify.runner import run_selection

        core = self.core
        vcfg = core.config.verify
        tmap = self.test_map()
        report = RunReport(full=full)
        budget = float(vcfg.turn_budget_s if budget_s is None else budget_s)
        if full:
            args: list[str] = []
            timeout = None if budget_s is None else budget * float(vcfg.hard_limit_factor)
        elif nodes:
            args = self.runnable_targets(nodes)
            report.selection = Selection(changed=(), nodes=tuple(args),
                                         reasons=dict.fromkeys(args, "literal"))
            timeout = budget * float(vcfg.hard_limit_factor)
        else:
            selection = self.select(changed if changed is not None
                                    else self.changed_paths(), budget_s=budget)
            args = self.runnable_targets(selection.nodes)
            if tuple(args) != selection.nodes:
                reasons = dict(selection.reasons)
                for target in args:
                    if target not in reasons:
                        first = next(n for n in selection.nodes
                                     if n.split("::", 1)[0] == target)
                        reasons[target] = selection.reasons[first]
                selection = replace(selection, nodes=tuple(args), reasons=reasons)
            report.selection = selection
            timeout = budget * float(vcfg.hard_limit_factor)
        report.timeout_s = timeout
        if not full and not args:
            report.full_pending = self.full_pending()
            return report
        key = self.env_key()
        tree = ev.tree_identity(self.root)
        infra = self.infra_hashes() if full else None
        files = {p: i["hash"] for p, i in tmap.files.items()} if full else None
        expected = None if full else self.expected_s(args)
        cov_spec = cov_tmp = None
        if self.coverage_mode() == "auto":
            cov_spec, cov_tmp, _ = self._cov_begin(tmap)
        outcome = run_selection(core, args, full=full, timeout_s=timeout, tmap=tmap,
                                cov=cov_spec)
        result = outcome.result
        if cov_spec is not None:
            self._cov_end(outcome, tmap, cov_tmp, cov_spec)
        report.notes = list(result.notes)
        report.workers = result.workers
        targets = tmap.test_files if full else args
        aborted = None
        if not outcome.discarded and not result.timed_out:
            aborted = self._abort_reason(result, targets, full=full)
        if vcfg.flaky_rerun and not outcome.discarded and not result.timed_out and not aborted:
            self._flaky_rerun(outcome, tree=tree, key=key, timeout=timeout)
        if not outcome.discarded and not result.timed_out:
            self._collection_failures(result, targets, aborted=aborted is not None)
        payload = self._payload(outcome, tree=tree, key=key, full=full, budget=budget,
                                selection=report.selection, infra=infra, files=files,
                                identity=self.identity(compute=True), aborted=aborted,
                                expected=expected)
        entry = core.log_append("evidence", "test-run", payload)
        report.run_id = payload["run_id"]
        report.discarded = outcome.discarded
        report.aborted = aborted
        report.timed_out = result.timed_out
        report.exit_status = result.exit_status
        report.elapsed_s = result.elapsed_s
        report.collection_errors = list(result.collection_errors)
        report.outcomes = {n: str(d.get("outcome")) for n, d in result.nodes.items()}
        report.flaky = sorted(n for n, o in report.outcomes.items() if o == "flaky")
        self._index = None
        index = self.index()
        if not outcome.discarded and entry is not None:
            from plumb.verify.policy import pass_run

            for node in report.failed:
                evid = ev.node_evidence(index, tmap, node, key, payload["env"]["identity"])
                if evid.regression:
                    report.regressions.append({
                        "node": node, "passed_in": pass_run(index, node),
                        "test_changed_since_pass": evid.test_changed_since_pass})
                else:
                    report.not_yet_passing.append(node)
        ran_files = {n.split("::", 1)[0] for n in report.outcomes}
        report.removed_after_passing = [n for n in self.removed_after_passing()
                                        if (full or n.split("::", 1)[0] in ran_files)
                                        and n not in report.outcomes]
        report.full_pending = self.full_pending()
        return report

    def _flaky_rerun(self, outcome: Any, *, tree: Mapping[str, Any], key: str,
                     timeout: float | None) -> None:
        """Rerun failed nodes once when the tree and env key are unchanged (spec 7.5)."""
        from plumb.verify.envid import env_key
        from plumb.verify.evidence import tree_identity
        from plumb.verify.policy import same_tree
        from plumb.verify.runner import run_selection

        result = outcome.result
        failed = sorted(n for n, d in result.nodes.items() if d.get("outcome") == "failed")
        if not failed:
            return
        if not same_tree(tree, tree_identity(self.root), key, env_key(self.root)):
            return
        again = run_selection(self.core, failed, timeout_s=timeout, tmap=self.test_map())
        if again.discarded or again.result.timed_out:
            return
        for node in failed:
            second = again.result.nodes.get(node, {}).get("outcome")
            if second is None:
                continue
            data = result.nodes[node]
            data["attempts"] = ["failed", str(second)]
            if second == "passed":
                data["outcome"] = "flaky"

    def runnable_targets(self, targets: Iterable[str]) -> list[str]:
        """Selection targets pytest can resolve: a node id the map does not know in its
        (mapped) file falls back to the file, because one unknown id (a test renamed under a
        ``verified_by`` link) makes pytest abort the whole selection. A file absorbs its
        node ids."""
        from plumb.verify.markers import strip_param

        tmap = self.test_map()
        out: list[str] = []
        for target in targets:
            test_file, sep, _ = target.partition("::")
            if sep and test_file in tmap.files:
                base = strip_param(target)
                known = tmap.nodes_of(test_file)
                if base not in known and not any(k.startswith(base + "::") for k in known):
                    target = test_file
            if target not in out:
                out.append(target)
        files = {t for t in out if "::" not in t}
        return [t for t in out if "::" not in t or t.split("::", 1)[0] not in files]

    def _abort_reason(self, result: Any, targets: Sequence[str], *, full: bool) -> str | None:
        """Why a pytest run that did not time out is still no clean run, or None.

        No plugin report, an unfinished session, or an exit status other than 0 (passed) or
        1 (tests failed) means pytest stopped before running the selection (a broken
        ``conftest.py``, a usage error, an internal error). Exit 5 (nothing collected) counts
        only when the selection, or the full suite, had known test nodes."""
        status = result.exit_status
        if not result.finished:
            return f"pytest stopped before the session finished (exit status {status})"
        if status in (0, 1):
            return None
        if status == 5:
            tmap = self.test_map()
            if not any(tmap.nodes_of(t.split("::", 1)[0]) for t in targets):
                return None  # nothing known to collect: no evidence, never full verification
            what = "the full suite" if full else "a selection"
            return f"pytest collected no tests from {what} with known tests (exit status 5)"
        return f"pytest exit status {status}"

    def _collection_failures(self, result: Any, targets: Sequence[str], *,
                             aborted: bool = False) -> None:
        """Known nodes of selected files that failed to collect count as failed (R3); in an
        aborted run, every selected file failed to collect."""
        from plumb.verify.markers import strip_param
        from plumb.verify.runner import mark_collection_failures

        if not result.collection_errors and not aborted:
            return
        tmap = self.test_map()
        recorded: dict[str, list[str]] = {}
        for node_id in self.index().get("nodes", {}):
            if "::" in node_id:
                recorded.setdefault(node_id.split("::", 1)[0], []).append(node_id)
        known: dict[str, list[str]] = {}
        for target in targets:
            test_file = target.split("::", 1)[0]
            if test_file in known:
                continue
            ids = sorted(recorded.get(test_file, []))
            covered = {strip_param(n) for n in ids}
            known[test_file] = ids + [n for n in tmap.nodes_of(test_file) if n not in covered]
        mark_collection_failures(result, targets, known, everything=aborted)

    def removed_after_passing(self) -> list[str]:
        """Nodes that passed with recorded evidence and are no longer in their existing
        file (VS1): shown, never an interruption."""
        from plumb.verify.markers import strip_param

        tmap = self.test_map()
        out = []
        for node_id, entry in sorted(self.index().get("nodes", {}).items()):
            if not entry.get("last_pass") or "::" not in node_id:
                continue
            test_file = node_id.split("::", 1)[0]
            if test_file not in tmap.files or not (self.root / test_file).is_file():
                continue
            if strip_param(node_id) not in tmap.files[test_file].get("nodes", {}):
                out.append(node_id)
        return out

    def _payload(self, outcome: Any, *, tree: Mapping[str, Any], key: str, full: bool,
                 budget: float, selection: Selection | None, infra: Mapping[str, str] | None,
                 files: Mapping[str, str] | None, identity: str | None,
                 aborted: str | None = None,
                 expected: float | None = None) -> dict[str, Any]:
        from plumb.verify.evidence import closure_digest, new_run_id, payload_checksum

        tmap = self.test_map()
        result = outcome.result
        inputs = outcome.inputs
        nodes = []
        for node_id, data in sorted(result.nodes.items()):
            test_file = node_id.split("::", 1)[0]
            depths = tmap.closures.get(test_file)
            closure = None
            if depths is not None:
                closure = closure_digest((p, inputs.get(p, "missing")) for p in depths
                                         if p in tmap.files)
            nodes.append({"id": node_id, "outcome": data.get("outcome"),
                          "duration_s": data.get("duration_s"), "closure": closure,
                          "test_hash": tmap.node_hash(node_id),
                          **({"failed_phase": data["failed_phase"]}
                             if data.get("failed_phase") == "collect" else {}),
                          "attempts": list(data.get("attempts") or [data.get("outcome")])})
        payload: dict[str, Any] = {
            "run_id": new_run_id(), "full": full, "tree": dict(tree),
            "env": {"env_key": key, "identity": identity},
            "selection": {
                "changed": list(selection.changed) if selection else [],
                "deferred": list(selection.deferred) if selection else [],
                "sampled": list(selection.sampled) if selection else [],
                "unknown_coverage": list(selection.unknown_coverage) if selection else [],
                "budget_s": budget},
            "nodes": nodes, "exit_status": result.exit_status,
            "collection_errors": list(result.collection_errors),
        }
        if infra is not None:
            payload["infra"] = dict(infra)
        if files is not None:
            payload["files"] = dict(files)
        if expected is not None:
            payload["timing"] = {"expected_s": expected, "elapsed_s": result.elapsed_s}
        if result.timed_out:
            payload["timeout"] = True
        if outcome.discarded:
            payload["discarded"] = outcome.discarded
        if aborted:
            payload["aborted"] = aborted
        payload["self"] = payload_checksum(payload)
        return payload
