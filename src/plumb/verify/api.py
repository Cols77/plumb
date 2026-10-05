"""``Verify``: the VerifyAPI (spec 12.1) plus the run flow behind ``plumb tests run``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.contracts import FullPending, NodeEvidence, Selection


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
    timed_out: bool = False
    timeout_s: float | None = None
    exit_status: int | None = None
    elapsed_s: float = 0.0
    full_pending: FullPending | None = None

    @property
    def failed(self) -> list[str]:
        return sorted(n for n, o in self.outcomes.items() if o == "failed")

    @property
    def ok(self) -> bool:
        return (not self.failed and not self.collection_errors and not self.discarded
                and not self.timed_out)

    def as_dict(self) -> dict[str, Any]:
        sel = self.selection
        return {
            "run_id": self.run_id, "full": self.full, "outcomes": self.outcomes,
            "failed": self.failed, "regressions": self.regressions,
            "not_yet_passing": self.not_yet_passing, "flaky": self.flaky,
            "removed_after_passing": self.removed_after_passing,
            "collection_errors": self.collection_errors, "discarded": self.discarded,
            "timed_out": self.timed_out, "exit_status": self.exit_status,
            "elapsed_s": self.elapsed_s,
            "selection": None if sel is None else {
                "nodes": list(sel.nodes), "deferred": list(sel.deferred),
                "sampled": list(sel.sampled), "unknown_coverage": list(sel.unknown_coverage),
                "infra_changed": list(sel.infra_changed), "doc_only": sel.doc_only},
            "full_pending": None if self.full_pending is None else {
                "pending": self.full_pending.pending,
                "reasons": list(self.full_pending.reasons)},
        }


class Verify:
    """VerifyAPI over one CoreAPI. Map, index and env key are cached per instance."""

    def __init__(self, core: Any) -> None:
        self.core = core
        self.root = Path(core.root)
        self._map: Any = None
        self._index: dict[str, Any] | None = None
        self._env_key: str | None = None

    # -- cached state
    def test_map(self) -> Any:
        if self._map is None:
            from plumb.verify.testmap import build_map

            self._map = build_map(self.core)
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

    # -- VerifyAPI
    def select(self, changed: Sequence[str], *, budget_s: float | None = None) -> Selection:
        from plumb.verify.evidence import durations
        from plumb.verify.select import select_tests

        return select_tests(self.core, self.test_map(), changed, budget_s=budget_s,
                            durations=durations(self.index()))

    def evidence(self, nodes: Iterable[str]) -> Mapping[str, NodeEvidence]:
        from plumb.verify.evidence import node_evidence

        index, tmap, key = self.index(), self.test_map(), self.env_key()
        return {n: node_evidence(index, tmap, n, key) for n in nodes}

    def full_pending(self) -> FullPending:
        from plumb.verify.select import matches_infra

        tmap = self.test_map()
        full = self.index().get("full")
        if not full:
            return FullPending(pending=True, reasons=("no full run recorded",))
        reasons: list[str] = []
        current = self.infra_hashes()
        recorded = full.get("infra") or {}
        for path in sorted(set(current) | set(recorded)):
            if current.get(path) != recorded.get(path):
                reasons.append(f"{path} changed")
        files = full.get("files") or {}
        globs = self.core.config.verify.infra_globs
        for path in self.uncovered_sources():
            if matches_infra(path, globs):
                continue
            if tmap.files.get(path, {}).get("hash") != files.get(path):
                reasons.append(f"{path} has no covering test")
        return FullPending(pending=bool(reasons), reasons=tuple(reasons))

    def tests_for(self, refs: Iterable[str]) -> Mapping[str, tuple[str, ...]]:
        from plumb.model import ID_PATTERN
        from plumb.verify.select import normalize_path

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
            args = list(dict.fromkeys(nodes))
            report.selection = Selection(changed=(), nodes=tuple(args),
                                         reasons=dict.fromkeys(args, "literal"))
            timeout = budget * float(vcfg.hard_limit_factor)
        else:
            report.selection = self.select(changed if changed is not None
                                           else self.changed_paths(), budget_s=budget)
            args = list(report.selection.nodes)
            timeout = budget * float(vcfg.hard_limit_factor)
        report.timeout_s = timeout
        if not full and not args:
            report.full_pending = self.full_pending()
            return report
        key = self.env_key()
        tree = ev.tree_identity(self.root)
        infra = self.infra_hashes() if full else None
        files = {p: i["hash"] for p, i in tmap.files.items()} if full else None
        outcome = run_selection(core, args, full=full, timeout_s=timeout, tmap=tmap)
        result = outcome.result
        payload = self._payload(outcome, tree=tree, key=key, full=full, budget=budget,
                                selection=report.selection, infra=infra, files=files)
        entry = core.log_append("evidence", "test-run", payload)
        report.run_id = payload["run_id"]
        report.discarded = outcome.discarded
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
                evid = ev.node_evidence(index, tmap, node, key)
                if evid.regression:
                    report.regressions.append({
                        "node": node, "passed_in": pass_run(index, node),
                        "test_changed_since_pass": evid.test_changed_since_pass})
                else:
                    report.not_yet_passing.append(node)
        report.full_pending = self.full_pending()
        return report

    def _payload(self, outcome: Any, *, tree: Mapping[str, Any], key: str, full: bool,
                 budget: float, selection: Selection | None, infra: Mapping[str, str] | None,
                 files: Mapping[str, str] | None) -> dict[str, Any]:
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
                          "attempts": list(data.get("attempts") or [data.get("outcome")])})
        payload: dict[str, Any] = {
            "run_id": new_run_id(), "full": full, "tree": dict(tree),
            "env": {"env_key": key},
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
        if result.timed_out:
            payload["timeout"] = True
        if outcome.discarded:
            payload["discarded"] = outcome.discarded
        payload["self"] = payload_checksum(payload)
        return payload
