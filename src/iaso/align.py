"""``iaso align [scope]``: edge alignment from intent to evidence (R12.2, sp5 8, SR-067).

1. **Collect, deterministically.** The scope (records resolved from the owner's words; by
   default every record touched since ``merge.default_base``, else every record) is expanded
   along existing links only: intent -> feature -> requirement -> example -> test -> code ->
   evidence. The collection has a fingerprint (sorted node hashes and edges). Empty families
   are named gaps ("SR-034/EX-2 has no test").
2. **Judge each edge once**, with one question phrased for its edge class (Noul, the
   backend's ``ask``). With no judge (none configured, no key, unreachable) the edges are
   listed unjudged under "judging unavailable: <cause>" (INT-029: no rule-based score).
3. **Edges stay deterministic.** Whether an edge exists comes from the links only: a judgment
   never creates or removes an edge, never marks staleness and never confirms.

Results are cached by fingerprint (``.iaso/cache/align-<fp>.json``); judgments from JEV are
logged as ``judgment`` events. ``/iaso review`` and the Obsidian vault show the edges
weakest first and as badges.
"""

from __future__ import annotations

from iaso.paths import state_dir

import hashlib
import json
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

QUESTIONS: Mapping[tuple[str, str], str] = {
    ("intent", "requirement"): "Does this requirement serve this intent?",
    ("feature", "requirement"): "Does this requirement belong to this feature?",
    ("requirement", "example"): "Does this example illustrate this requirement?",
    ("example", "test"): "Does this test check this example?",
    ("requirement", "test"): "Does this test check this requirement?",
    ("requirement", "code"): "Does this code realize this requirement?",
}
WEAK = 0.34
CONTENT_LIMIT = 4000


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    edge_class: str                 # "requirement->code"
    question: str
    score: float | None = None      # 0..1; None: not judged
    verdict: str = "unjudged"       # yes | no | unsure | heuristic | unjudged
    backend: str = ""


@dataclass
class AlignResult:
    scope: list[str]
    fingerprint: str
    nodes: dict[str, str]                       # node id -> kind
    edges: list[Edge] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    backend: str = "none"
    available: bool = False
    unavailable: str = ""                       # why no judge answered, when none did

    def as_dict(self) -> dict[str, Any]:
        return {"scope": self.scope, "fingerprint": self.fingerprint, "nodes": self.nodes,
                "edges": [asdict(e) for e in self.edges], "gaps": self.gaps,
                "backend": self.backend, "available": self.available,
                "unavailable": self.unavailable}


# --------------------------------------------------------------------------- collection


def _changed_since(core: Any) -> list[str]:
    from iaso.boundary.cli import merge_settings

    base = str(merge_settings(core)["default_base"])
    try:
        out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=core.root,
                             capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()] \
        if out.returncode == 0 else []


def default_scope(core: Any) -> list[str]:
    """Every record touched since ``merge.default_base``; every record when none is."""
    index = core.index()
    changed = _changed_since(core)
    touched = {i for ids in core.records_for_paths(changed).values() for i in ids} \
        if changed else set()
    touched |= {i for i, r in index.items() if r.path in set(changed)}
    return sorted(touched & set(index)) or sorted(index)


def collect(core: Any, scope: Sequence[str]) -> tuple[dict[str, str], list[tuple[str, str]],
                                                      list[str]]:
    """``(nodes, edges, gaps)`` along existing links only (deterministic)."""
    index = core.index()
    seeds = [i for i in scope if i in index]
    requirements: set[str] = set()
    intents: set[str] = set()
    features: set[str] = set()
    for record_id in seeds:
        record = index[record_id]
        if record.kind == "requirement":
            requirements.add(record_id)
        elif record.kind == "intent":
            intents.add(record_id)
            requirements |= {r.id for r in index.values() if r.kind == "requirement" and any(
                link.kind == "derives_from" and link.target.record == record_id
                for link in r.links)}
        elif record.kind == "feature":
            features.add(record_id)
            requirements |= {str(m) for m in record.fields.get("requirements") or []
                             if str(m) in index}
            requirements |= {r.id for r in index.values() if r.kind == "requirement"
                             and str(r.fields.get("feature")) == record_id}
    for record_id in sorted(requirements):
        record = index[record_id]
        for link in record.links:
            target = link.target.record
            if link.kind == "derives_from" and target in index \
                    and index[target].kind == "intent":
                intents.add(target)
        feature = str(record.fields.get("feature") or "")
        if feature in index:
            features.add(feature)
    nodes: dict[str, str] = {}
    edges: list[tuple[str, str]] = []
    gaps: list[str] = []
    for i in intents:
        nodes[i] = "intent"
    for f in features:
        nodes[f] = "feature"
    for record_id in sorted(requirements):
        record = index[record_id]
        nodes[record_id] = "requirement"
        parents = [link.target.record for link in record.links if link.kind == "derives_from"
                   and link.target.record in intents]
        for parent in parents:
            edges.append((parent, record_id))
        if not parents:
            gaps.append(f"{record_id} derives from no intent")
        feature = str(record.fields.get("feature") or "")
        if feature in features:
            edges.append((feature, record_id))
        if not record.examples:
            gaps.append(f"{record_id} has no example")
        tested: set[str] = set()
        for example in record.examples:
            node = f"{record_id}/{example.id}"
            nodes[node] = "example"
            edges.append((record_id, node))
        for link in record.links:
            end = link.target.test or link.target.path
            if link.kind == "verified_by" and end:
                nodes[end] = "test"
                if link.example and f"{record_id}/{link.example}" in nodes:
                    edges.append((f"{record_id}/{link.example}", end))
                    tested.add(link.example)
                else:
                    edges.append((record_id, end))
            elif link.kind == "implemented_by" and (link.target.path or link.target.symbol):
                code = link.target.path or str(link.target.symbol)
                nodes[code] = "code"
                edges.append((record_id, code))
        for example in record.examples:
            if example.id not in tested:
                gaps.append(f"{record_id}/{example.id} has no test")
        if not any(link.kind == "implemented_by" for link in record.links):
            gaps.append(f"{record_id} has no code")
    return nodes, sorted(set(edges)), gaps


def fingerprint(core: Any, nodes: Mapping[str, str], edges: Iterable[tuple[str, str]]) -> str:
    index = core.index()
    hashes = []
    for node in sorted(nodes):
        if node in index:
            hashes.append([node, index[node].hash])
        else:
            hashes.append([node, _content_digest(core, node)])
    blob = json.dumps({"nodes": hashes, "edges": sorted(map(list, edges))}, sort_keys=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _content_digest(core: Any, node: str) -> str:
    path = Path(core.root) / node.split("::", 1)[0]
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return "-"


# --------------------------------------------------------------------------- judging


def node_text(core: Any, node: str, kind: str) -> str:
    index = core.index()
    if node in index:
        record = index[node]
        fields = record.fields
        parts = [record.title]
        for key in ("statement", "readback", "quote", "description", "will"):
            value = fields.get(key)
            parts.extend(map(str, value) if isinstance(value, list) else [str(value or "")])
        return " ".join(parts)
    if kind == "example":
        record_id, _, example_id = node.partition("/")
        for example in getattr(index.get(record_id), "examples", ()):
            if example.id == example_id:
                return " ".join((example.given, example.when, example.then,
                                 example.criterion))
        return ""
    path = Path(core.root) / node.split("::", 1)[0]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:CONTENT_LIMIT]
    except OSError:
        text = ""
    return node.replace("/", " ").replace("_", " ") + " " + text


def _backend(core: Any, given: Any) -> tuple[Any, str]:
    """``(the judge or None, why there is none)``: no rule-based judge stands in (INT-029)."""
    if given is not None:
        return given, ""
    if str(getattr(core.config.judgment, "backend", "")).strip().lower() == "disabled":
        return None, "judgment.backend is disabled"
    try:
        from iaso.judgment import JudgmentUnavailable, get_backend

        chosen = get_backend(core, hook=False)
    except JudgmentUnavailable as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001 - "judging unavailable"
        return None, type(exc).__name__
    if str(getattr(chosen, "name", "")) == "disabled":
        return None, "judgment.backend is disabled"
    return chosen, ""


def judge(core: Any, nodes: Mapping[str, str], edges: Sequence[tuple[str, str]],
          backend: Any) -> tuple[list[Edge], str]:
    """One judgment per edge; the edges themselves are never changed."""
    name = str(getattr(backend, "name", "none")) if backend is not None else "none"
    out: list[Edge] = []
    from iaso import progress

    reporter, owned = progress.acquire(core.root, "align")
    try:
        _judge_edges(core, nodes, edges, backend, name, out, reporter)
    finally:
        if owned:
            reporter.done()
    return out, name


STEP_ALIGN = "judging how well the records fit"       # SR-108


def _judge_edges(core: Any, nodes: Mapping[str, str], edges: Sequence[tuple[str, str]],
                 backend: Any, name: str, out: list[Edge], reporter: Any) -> None:
    for count, (source, target) in enumerate(edges, 1):
        reporter.update(STEP_ALIGN, count - 1, len(edges))
        edge_class = (nodes[source], nodes[target])
        question = QUESTIONS.get(edge_class, "Do these two belong together?")
        label = f"{edge_class[0]}->{edge_class[1]}"
        if backend is None:
            out.append(Edge(source, target, label, question))
            continue
        source_text = node_text(core, source, nodes[source])
        target_text = node_text(core, target, nodes[target])
        try:
            judgment = backend.ask(question, f"A: {source_text}\nB: {target_text}",
                                   subject=f"{source}->{target}", action="alignment")
        except Exception:  # noqa: BLE001 - one failed judgment leaves the edge unjudged
            out.append(Edge(source, target, label, question))
            continue
        verdict = str(judgment.verdict)
        probability = getattr(judgment, "probability", None)
        if verdict == "yes":
            score = float(probability if probability is not None else judgment.confidence)
        elif verdict == "no":
            score = 1.0 - float(probability if probability is not None else
                                judgment.confidence)
            score = min(score, 0.5)
        else:
            score = 0.5
        out.append(Edge(source, target, label, question, round(score, 4), verdict,
                        str(judgment.backend)))
        if str(judgment.backend).startswith("jev"):
            core.log_append("events", "judgment", {
                "action": "alignment", "subject": f"{source}->{target}", "verdict": verdict,
                "confidence": judgment.confidence, "probability": probability,
                "backend": judgment.backend, "question": question})


def _weakest_first(edges: Sequence[Edge]) -> list[Edge]:
    return sorted(edges, key=lambda e: (e.score is None, e.score if e.score is not None
                                        else 0.0, e.source, e.target))


def align(core: Any, scope: Sequence[str] | None = None, *, backend: Any = None,
          use_cache: bool = True) -> AlignResult:
    """Collect ``scope`` (default: ``default_scope``), judge each edge, weakest first."""
    scope = sorted(scope) if scope else default_scope(core)
    nodes, edges, gaps = collect(core, scope)
    fp = fingerprint(core, nodes, edges)
    chosen, cause = _backend(core, backend)
    name = str(getattr(chosen, "name", "none")) if chosen is not None else "none"
    cache = state_dir(Path(core.root)) / "cache" / f"align-{fp.split(':')[1][:24]}-{name}.json"
    if use_cache and backend is None and chosen is not None:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            return AlignResult(scope, fp, nodes, [Edge(**e) for e in data["edges"]], gaps,
                               data["backend"], data["available"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
    judged, name = judge(core, nodes, edges, chosen)
    result = AlignResult(scope, fp, nodes, _weakest_first(judged), gaps, name,
                         chosen is not None, cause)
    if backend is None and chosen is not None:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"edges": [asdict(e) for e in result.edges],
                                         "backend": result.backend,
                                         "available": result.available}), encoding="utf-8")
        except OSError:
            pass
    return result


def badge(edge: Edge) -> str:
    """``weak``, ``aligned``, ``unsure`` or ``unjudged`` for the vault and the review."""
    if edge.score is None:
        return "unjudged"
    if edge.verdict == "no" or edge.score < WEAK:
        return "weak"
    if edge.verdict == "unsure":
        return "unsure"
    return "aligned"


def align_lines(result: AlignResult, *, limit: int | None = None) -> list[str]:
    lines = [f"iaso align: {len(result.scope)} record(s) in scope, {len(result.nodes)} "
             f"nodes, {len(result.edges)} edges ({result.fingerprint[:19]})"]
    for gap in result.gaps:
        lines.append(f"gap: {gap}")
    if not result.available:
        why = f"judging unavailable: {result.unavailable}" if result.unavailable \
            else "no judgments available"
        lines.append(f"{why} (edges listed, not judged)")
    else:
        lines.append(f"edges, weakest first ({result.backend}; advisory, edges are never "
                     "changed):")
    edges = result.edges if limit is None else result.edges[:limit]
    for edge in edges:
        score = "-" if edge.score is None else f"{edge.score:.2f}"
        lines.append(f"  {badge(edge):8} {score:>4}  {edge.source} -> {edge.target}  "
                     f"{edge.question}")
    if limit is not None and len(result.edges) > limit:
        lines.append(f"  +{len(result.edges) - limit} more (iaso align)")
    return lines
