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


def _answers_match(kind: str, answer: Mapping[str, Any], expect: Mapping[str, Any]) -> bool:
    """Whether a model's answer meets a frozen case, the way that kind reads its answer."""
    if kind == "judge":
        from plumb.understand import judge

        return judge.matches(answer, expect)
    if kind == "read":
        got = {str(e.get("id")): e for e in answer.get("entries") or () if isinstance(e, Mapping)}
        wanted = {str(e.get("id")): e for e in expect.get("entries") or ()}
        for name, item in wanted.items():
            if name not in got or got[name].get("answer") != item.get("answer"):
                return False
        # a confirmation nobody asked for is the worst mistake a reader can make
        return not any(e.get("answer") == "accepted" and name not in wanted
                       for name, e in got.items())
    return all(answer.get(k) == v for k, v in expect.items())


def _real_answer(dispatcher: Any, job: Job, kind: str) -> Mapping[str, Any]:
    """What the worker would send for ``job``: the kind's agent prompt, its inputs as the user
    message, its schema; an answer that fails the schema is an error, never a reading."""
    from plumb.understand import agents, schema as schema_check
    from plumb.understand.kinds import KINDS

    module = KINDS[kind]
    answer = dict(dispatcher.run(
        job, system=agents.load(kind),
        user=json.dumps(job.inputs, ensure_ascii=False, sort_keys=True, indent=1),
        schema=module.schema, on_step=lambda step: None))
    found = schema_check.problems(answer, module.schema)
    if found:
        raise DispatchError("schema", "; ".join(found[:3]))
    return answer


def run_cases(dispatcher: Any, cases: Sequence[Mapping[str, Any]],
              kind: str) -> list[dict[str, Any]]:
    """Run each case. The fake dispatcher is handed the expected answer inside the inputs (the
    harness without a model); any other dispatcher gets the real prompt, inputs and schema, and
    never sees the expectation."""
    fake = isinstance(dispatcher, FakeEvalDispatcher)
    results: list[dict[str, Any]] = []
    for n, case in enumerate(cases):
        expect = dict(case.get("expect") or {})
        inputs = dict(case.get("inputs") or {})
        job = Job(id=f"eval-{kind}-{n}", kind=kind, schema=f"{kind}.v1",
                  inputs={**inputs, "expect": expect} if fake else inputs)
        error = ""
        try:
            if fake:
                answer = dict(dispatcher.run(job, system="", user=json.dumps(job.inputs),
                                             schema={}, on_step=lambda step: None))
                passed = all(answer.get(k) == v for k, v in expect.items())
            else:
                try:
                    answer = dict(_real_answer(dispatcher, job, kind))
                except KeyError:                 # a kind with no module: the plain protocol
                    answer = dict(dispatcher.run(job, system="", user=json.dumps(inputs),
                                                 schema={}, on_step=lambda step: None))
                passed = _answers_match(kind, answer, expect)
            false_gap = bool(answer.get("gap")) and not expect.get("gap")
        except DispatchError as exc:
            passed, false_gap, error = False, False, f"{exc.step}: {exc.message}"
        row = {"kind": kind, "case": case.get("name", str(n)), "passed": passed,
               "false_gap": false_gap}
        if error:
            row["error"] = error
        results.append(row)
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
