"""Shared helpers of the HOSTS tests (sp4): a scripted project and a fake verify."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from iaso.approvals import owner_terminal_answer as REAL_TERMINAL_CHECK
from iaso.contracts import FullPending, NodeEvidence, Selection

SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""
DEC1 = """---
id: DEC-001
title: Integers only
question: Should add accept floats?
chosen: integers only
alternatives:
- floats too
matters: true
links:
- kind: decides
  to: SR-001
---
"""


def scripted_judge(monkeypatch, where: Path) -> None:
    """DEC-088: since DEC-060 / SR-174 the stale check waits without a judge, so these tests
    get a scripted one (``IASO_FAKE_DISPATCH``) that says the edit changed the meaning and
    brings it to the owner on a card lacking its consequences, which does not resolve the
    link (SR-116), so the stale hold still blocks."""
    script = where / "judge.json"
    script.write_text(json.dumps({
        "repin": {"verdict": "changed", "reason": "the value changed", "confidence": 0.9},
        "diagnose": {"outcome": "owner", "explanation": "the value changed", "topic": "",
                     "options": ["keep the new value", "undo the edit"]}}), "utf-8")
    monkeypatch.setenv("IASO_FAKE_DISPATCH", str(script))


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def make_project(repo: Path, write_record, *, decision: bool = True) -> Path:
    """SR-001 implemented by src/calc.py (and an unconfirmed DEC that matters), committed."""
    from iaso.api import open_core
    from iaso.contracts import Target

    write_record(repo, SR1)
    if decision:
        write_record(repo, DEC1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "setup")
    return repo


@dataclass
class QuietVerify:
    """A VerifyAPI with no tests: every selection is empty, nothing is pending."""

    calls: list[tuple[str, ...]] = field(default_factory=list)

    def select(self, changed: Sequence[str], *, budget_s: float | None = None) -> Selection:
        self.calls.append(tuple(changed))
        return Selection(changed=tuple(changed), nodes=(), reasons={}, deferred=(),
                         infra_changed=(), doc_only=False, expected_s=0.0)

    def evidence(self, nodes: Iterable[str]) -> Mapping[str, NodeEvidence]:
        return {n: NodeEvidence(n, "none") for n in nodes}

    def full_pending(self) -> FullPending:
        return FullPending(False)

    def tests_for(self, refs: Iterable[str]) -> Mapping[str, tuple[str, ...]]:
        return {r: () for r in refs}


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` except .git, by relative path."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(root).parts}


def approve_in_agent_shell(root: Path, monkeypatch, env: Mapping[str, str]) -> int:
    """``iaso approve SR-001`` as an agent's shell runs it on a host: the environment the
    adapter gives (``env``), no terminal, a piped "y", and the real terminal check."""
    import io

    from iaso import approvals, cli

    monkeypatch.setattr(approvals, "owner_terminal_answer", REAL_TERMINAL_CHECK)
    monkeypatch.delenv("IASO_AGENT_SESSION", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("sys.stdin", io.StringIO("y\ny\n"))
    monkeypatch.chdir(root)
    return cli.main(["approve", "SR-001"])


def approvals_written(root: Path) -> list:
    from iaso.api import open_core

    return list(open_core(root).log_read("events", ["approval"]))
