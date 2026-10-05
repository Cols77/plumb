"""Covering-test selection for a set of changed paths (spec 7.2, ruling R5).

Priority: tests ``verified_by`` requirements whose ``implemented_by`` ends or record files
changed; tests that mention a changed path literally; tests whose import closure reaches a
changed file, nearest first; tests matched by naming. Documentation selects nothing; shared
test infrastructure adds nothing (it makes a full run pending); a changed source file with no
covering test adds a bounded, deterministic sample of the nearest tests; the turn budget
defers the overflow. A selection never names a directory, so it never runs the whole suite.

The infrastructure matcher and documentation rule are extracted from pi-agent-factory's
``coherence/integration/failure_policy.py`` (``InfrastructureMatcher``,
``is_documentation``).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from plumb.contracts import Selection, SelectionReason

_DOC_SUFFIXES = frozenset({".md", ".rst"})
_PRIORITY: Mapping[str, int] = {"verified_by": 0, "literal": 1, "import": 2, "naming": 3,
                                "sample": 4}


def normalize_path(raw: str) -> str | None:
    """A repository-relative POSIX path, or None when unsafe."""
    text = str(raw).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    text = text.rstrip("/")
    if not text or text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        return None
    parts = text.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    return text


def is_documentation(path: str) -> bool:
    """``docs/**`` and ``*.md``/``*.rst`` outside ``.plumb/``."""
    pure = PurePosixPath(path)
    if pure.parts and pure.parts[0] == ".plumb":
        return False
    return pure.parts[0] == "docs" or pure.suffix.lower() in _DOC_SUFFIXES


def matches_infra(path: str, globs: Iterable[str]) -> bool:
    """``**/<name>`` matches that name at any depth; other patterns are fnmatch globs on
    the whole path. Case-insensitive, so a case-insensitive checkout fails toward pending."""
    candidate = path.casefold()
    for pattern in globs:
        folded = str(pattern).casefold()
        if folded.startswith("**/"):
            tail = folded[3:]
            if fnmatch.fnmatchcase(candidate, tail) or fnmatch.fnmatchcase(candidate,
                                                                            "*/" + tail):
                return True
        elif fnmatch.fnmatchcase(candidate, folded):
            return True
    return False


def _strip_root(parts: Sequence[str], roots: Iterable[str]) -> list[str]:
    roots = {r.strip("/") for r in roots}
    if parts and parts[0] in roots:
        return list(parts[1:])
    return list(parts)


def nearest_tests(path: str, tests: Sequence[str], source_dirs: Iterable[str],
                  test_dirs: Iterable[str], limit: int) -> list[str]:
    """The ``limit`` tests nearest ``path`` by directory, deterministically."""
    src_parent = PurePosixPath(path).parent
    dirs = _strip_root(src_parent.parts, source_dirs)

    def rank(test: str) -> tuple[int, str]:
        parent = PurePosixPath(test).parent
        if parent == src_parent:
            return (-1, test)
        tparts = set(_strip_root(parent.parts, test_dirs))
        for k in range(len(dirs)):
            if dirs[len(dirs) - 1 - k] in tparts:
                return (k, test)
        return (len(dirs), test)

    return sorted(tests, key=rank)[:limit]


class _Ordered:
    """Selection entries in priority order; a file absorbs its earlier node entries."""

    def __init__(self) -> None:
        self.items: list[str] = []
        self.reasons: dict[str, SelectionReason] = {}

    def add(self, entry: str, reason: SelectionReason) -> None:
        if entry in self.reasons:
            return
        file = entry.split("::", 1)[0]
        if file in self.reasons:
            return  # the whole file is already selected
        if "::" not in entry:
            nodes = [i for i in self.items if i.startswith(entry + "::")]
            if nodes:
                at = self.items.index(nodes[0])
                first_reason = self.reasons[nodes[0]]
                for n in nodes:
                    self.items.remove(n)
                    del self.reasons[n]
                self.items.insert(at, entry)
                self.reasons[entry] = first_reason
                return
        self.items.append(entry)
        self.reasons[entry] = reason


def expected_duration(entry: str, nodes_of: Callable[[str], list[str]],
                      durations: Mapping[str, float], default_s: float) -> float:
    """Expected seconds: known node durations (parametrized ids summed under their node),
    ``default_s`` once for any unknown remainder."""

    def known(node: str) -> float | None:
        if node in durations:
            return float(durations[node])
        family = [float(v) for k, v in durations.items() if k.startswith(node + "[")]
        return sum(family) if family else None

    if "::" in entry:
        value = known(entry)
        return round(value, 6) if value is not None else default_s
    total = 0.0
    unknown = False
    nodes = nodes_of(entry)
    for node in nodes:
        value = known(node)
        if value is None:
            unknown = True
        else:
            total += value
    if unknown or not nodes:
        total += default_s
    return round(total, 6)


def select_tests(core: Any, tmap: Any, changed: Iterable[str], *,
                 budget_s: float | None = None,
                 durations: Mapping[str, float] | None = None) -> Selection:
    """The covering selection of ``changed`` (spec 7.2)."""
    config = core.config
    vcfg = config.verify
    budget = float(vcfg.turn_budget_s if budget_s is None else budget_s)
    durations = dict(durations or {})
    family: dict[str, float] = {}
    for key, value in durations.items():  # parametrized ids also count for their node
        cut = key.find("[", key.find("::"))
        if "::" in key and cut > 0:
            family[key[:cut]] = family.get(key[:cut], 0.0) + float(value)
    for base, total in family.items():
        durations.setdefault(base, total)
    root = core.root
    norm = []
    for raw in changed:
        rel = normalize_path(raw)
        if rel and rel not in norm:
            norm.append(rel)
    docs = [p for p in norm if is_documentation(p)]
    infra = sorted(p for p in norm if p not in docs and matches_infra(p, vcfg.infra_globs))
    rest = [p for p in norm if p not in docs and p not in infra]
    rest = [p for p in rest if not (root / p).is_dir()]
    test_set = set(tmap.test_files)
    source_dirs = tuple(config.source_dirs)

    def is_source(path: str) -> bool:
        if path.startswith(".plumb/"):
            return False
        return path.endswith(".py") or any(path.startswith(d.rstrip("/") + "/")
                                           for d in source_dirs)

    candidates: list[tuple[int, int, str, str, SelectionReason]] = []
    covered: dict[str, bool] = {p: False for p in rest}
    for path in rest:
        for rid in tmap.implemented.get(path, ()):
            for test in tmap.records.get(rid, ()):
                if test.split("::", 1)[0] in test_set:
                    candidates.append((0, 0, "", test, "verified_by"))
                    covered[path] = True
        for test in tmap.mentions(path):
            candidates.append((1, 0, test, test, "literal"))
            covered[path] = True
        if path in test_set:
            candidates.append((2, 0, path, path, "import"))
            covered[path] = True
        for test, depth in tmap.importers.get(path, {}).items():
            candidates.append((2, depth, test, test, "import"))
            covered[path] = True
        for test in tmap.naming.get(path, ()):
            candidates.append((3, 0, test, test, "naming"))
            covered[path] = True
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    ordered = _Ordered()
    for _, _, _, entry, reason in candidates:
        ordered.add(entry, reason)
    unknown = tuple(p for p in rest if not covered[p] and is_source(p))
    sampled: list[str] = []
    for path in unknown:
        pool = [t for t in tmap.test_files if t not in ordered.reasons]
        for test in nearest_tests(path, pool, source_dirs, config.test_dirs, vcfg.sample_size):
            if len(sampled) >= vcfg.sample_size:
                break
            if test not in ordered.reasons:
                ordered.add(test, "sample")
                sampled.append(test)
    chosen: list[str] = []
    deferred: list[str] = []
    total = 0.0
    for entry in ordered.items:
        cost = expected_duration(entry, tmap.nodes_of, durations, vcfg.default_test_s)
        if deferred or (chosen and total + cost > budget + 1e-9):
            deferred.append(entry)
            continue
        chosen.append(entry)
        total += cost
    return Selection(changed=tuple(norm), nodes=tuple(chosen),
                     reasons={k: v for k, v in ordered.reasons.items()},
                     deferred=tuple(deferred), sampled=tuple(sampled),
                     unknown_coverage=unknown, infra_changed=tuple(infra),
                     doc_only=bool(norm) and len(docs) == len(norm),
                     expected_s=round(total, 6))
