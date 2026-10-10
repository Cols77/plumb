"""``plumb understand eval [--fake]``: run each case of ``evalset/{read,judge,clarify}.json``
on the configured dispatcher and write an ``eval-run`` entry (model, prompt digest = digest
of ``agents/*.md`` and ``schemas/*.json``, cases, passed, the clarifier's false-gap rate)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import DispatchError, Job, NoModel

HERE = Path(__file__).resolve().parent
KINDS = ("read", "judge", "clarify")


def load_cases(kind: str) -> list[Mapping[str, Any]]:
    try:
        data = json.loads((HERE / "evalset" / f"{kind}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [c for c in data if isinstance(c, Mapping)] if isinstance(data, list) else []


def prompt_digest() -> str:
    digest = hashlib.sha256()
    for sub, pattern in (("agents", "*.md"), ("schemas", "*.json")):
        for path in sorted((HERE / sub).glob(pattern)):
            digest.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return "sha256:" + digest.hexdigest()


class FakeEvalDispatcher:
    """Answers every case with its own ``expect`` (``--fake``: the harness without a model)."""

    name = "fake"

    def available(self) -> str | None:
        return None

    def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
            on_step: Any) -> Mapping[str, Any]:
        return dict(job.inputs.get("expect") or {})


def run_cases(dispatcher: Any, cases: Sequence[Mapping[str, Any]],
              kind: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for n, case in enumerate(cases):
        expect = dict(case.get("expect") or {})
        job = Job(id=f"eval-{kind}-{n}", kind=kind,
                  inputs={**dict(case.get("inputs") or {}), "expect": expect})
        try:
            answer = dict(dispatcher.run(job, system="", user=json.dumps(job.inputs),
                                         schema={}, on_step=lambda step: None))
            passed = all(answer.get(k) == v for k, v in expect.items())
            false_gap = bool(answer.get("gap")) and not expect.get("gap")
        except DispatchError:
            passed, false_gap = False, False
        results.append({"kind": kind, "case": case.get("name", str(n)), "passed": passed,
                        "false_gap": false_gap})
    return results


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="plumb understand eval")
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    from plumb.api import open_core
    from plumb.paths import find_root

    core = open_core(find_root(Path(args.root or ".")))
    if args.fake:
        dispatcher: Any = FakeEvalDispatcher()
    else:
        from plumb.understand.dispatch import configured

        try:
            dispatcher = configured(core)
        except NoModel as exc:
            print(f"plumb: {exc}", file=sys.stderr)
            return 2
    cases = [r for kind in KINDS for r in run_cases(dispatcher, load_cases(kind), kind)]
    clarify = [r for r in cases if r["kind"] == "clarify"]
    rate = (sum(r["false_gap"] for r in clarify) / len(clarify)) if clarify else 0.0
    passed = sum(1 for r in cases if r["passed"])
    core.log_append("events", "eval-run", {
        "model": "fake" if args.fake else core.config.understand.model,
        "prompt_digest": prompt_digest(), "cases": cases, "passed": passed,
        "false_gap_rate": rate})
    print(f"eval: {len(cases)} cases, {passed} passed")
    return 0
